"""Gestor de trabajos (jobs) de ingesta de noticias.

Cada ``POST /v1/sources/scan`` crea un trabajo que se ejecuta en un hilo del
``ThreadPoolExecutor`` y persiste su progreso en la tabla ``scrape_jobs`` de
SQLite (mediante :class:`~app.services.store.Store`). El contrato del frontend
usa cinco pasos:

1. ``connecting``  — validación de URL y ``robots.txt``.
2. ``crawling``    — descubrimiento en portada, feeds RSS/Atom y sitemaps.
3. ``cleaning``    — extracción/limpieza del cuerpo de cada noticia.
4. ``analyzing``   — análisis de sentimiento, encuadres y sesgo.
5. ``completed``   — resumen agregado del sitio (o ``error`` si algo falla).

El gestor es testeable sin red: acepta un ``fetcher`` o un ``scraper``
inyectados, y expone ``wait(job_id)`` para que los tests esperen el final del
trabajo de forma determinista.
"""

from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable

from ..config import Settings
from ..schemas import (
    JobStep,
    NewsArticle,
    ScrapeRequest,
    TextAnalysisResult,
)
from .analysis import AnalysisService, normalize_country
from .fetching import FetchError, SupportsGet
from .scraper import (
    ExtractedArticle,
    NewsScraper,
    ScraperError,
    build_news_article,
    build_summary,
    normalize_date,
)
from .site_catalog import domain_from_url
from .store import Store

logger = logging.getLogger(__name__)

#: Pasos del contrato del frontend.
TOTAL_STEPS = 5
STEP_CONNECTING = 1
STEP_CRAWLING = 2
STEP_CLEANING = 3
STEP_ANALYZING = 4
STEP_COMPLETED = 5

_FINISHED_STATUSES = {"completed", "error"}


class JobManager:
    """Orquesta los trabajos de ingesta en hilos y persiste su progreso."""

    def __init__(
        self,
        settings: Settings,
        store: Store,
        analysis: AnalysisService,
        *,
        scraper: NewsScraper | None = None,
        fetcher: SupportsGet | None = None,
        monitoring: object | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.analysis = analysis
        self.monitoring = monitoring
        if scraper is None:
            scraper = NewsScraper(settings, fetcher=fetcher)
        self.scraper = scraper
        workers = max(1, int(settings.scraper_max_jobs_in_parallel))
        self._executor = ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="scrape-job"
        )
        self._lock = threading.Lock()
        self._events: dict[str, threading.Event] = {}

    # ------------------------------------------------------------------ API
    def submit(self, request: ScrapeRequest) -> str:
        """Registra el trabajo y lo lanza en segundo plano; devuelve su id."""
        self.prune()
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        domain = domain_from_url(request.url)
        self.store.create_job(
            job_id,
            request.url,
            domain,
            request.model_dump(by_alias=True, mode="json"),
            total_steps=TOTAL_STEPS,
        )
        event = threading.Event()
        with self._lock:
            self._events[job_id] = event
        self._inc("queued")
        self._executor.submit(self._run, job_id, request, event)
        logger.info("Job de ingesta %s encolado para %s", job_id, request.url)
        return job_id

    def get(self, job_id: str) -> dict[str, Any] | None:
        return self.store.get_job(job_id)

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.store.list_jobs(limit=limit)

    def wait(self, job_id: str, timeout: float = 10.0) -> bool:
        """Espera a que el trabajo termine (pensado para tests)."""
        with self._lock:
            event = self._events.get(job_id)
        if event is not None:
            return event.wait(timeout)
        job = self.store.get_job(job_id)
        return bool(job and job.get("status") in _FINISHED_STATUSES)

    def prune(self) -> None:
        """Elimina trabajos viejos según ``scraper_job_ttl_hours``."""
        try:
            self.store.prune_jobs(ttl_hours=self.settings.scraper_job_ttl_hours)
        except Exception:  # pragma: no cover - defensivo
            logger.warning("No se pudieron limpiar los jobs viejos", exc_info=True)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
        targets = (self.scraper, getattr(self.scraper, "fetcher", None))
        for target in targets:
            close = getattr(target, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # pragma: no cover - defensivo
                    logger.debug("Error cerrando recursos del scraper", exc_info=True)

    # ------------------------------------------------------------- interno
    def _inc(self, status: str) -> None:
        inc = getattr(self.monitoring, "inc_scrape", None)
        if callable(inc):
            try:
                inc(status)
            except Exception:  # pragma: no cover - defensivo
                logger.debug("No se pudo registrar la métrica del job", exc_info=True)

    def _run(
        self, job_id: str, request: ScrapeRequest, event: threading.Event
    ) -> None:
        steps: list[dict[str, Any]] = []

        def announce(step: int, status: str, message: str) -> None:
            steps.append(
                JobStep(
                    step=step,
                    total_steps=TOTAL_STEPS,
                    message=message,
                    at=datetime.now(timezone.utc),
                ).model_dump(mode="json")
            )
            self.store.update_job(
                job_id,
                status=status,
                current_step=step,
                total_steps=TOTAL_STEPS,
                message=message,
                steps_json=list(steps),
            )

        try:
            summary = self._execute(job_id, request, announce)
        except (FetchError, ScraperError) as exc:
            self._fail(job_id, exc.message)
        except Exception as exc:  # pragma: no cover - salvavidas del hilo
            logger.exception("El job %s falló de forma inesperada", job_id)
            self._fail(job_id, f"Error inesperado durante la ingesta: {exc}")
        else:
            self.store.update_job(
                job_id,
                status="completed",
                current_step=STEP_COMPLETED,
                message=(
                    f"Análisis completado: {summary.total_analyzed} noticias "
                    f"analizadas de {summary.site_name}"
                ),
                summary_json=summary.model_dump(by_alias=True, mode="json"),
                articles_analyzed=summary.total_analyzed,
            )
            self._inc("completed")
            logger.info(
                "Job %s completado | sitio=%s | noticias=%s",
                job_id,
                summary.domain,
                len(summary.articles),
            )
        finally:
            event.set()
            with self._lock:
                self._events.pop(job_id, None)

    def _execute(
        self,
        job_id: str,
        request: ScrapeRequest,
        announce: Callable[[int, str, str], None],
    ):
        domain = domain_from_url(request.url) or request.url
        respect = request.respect_robots

        announce(
            STEP_CONNECTING,
            "connecting",
            f"Conectando con {domain} y verificando robots.txt",
        )
        self.scraper.check_robots(request.url, respect_robots=respect)

        announce(
            STEP_CRAWLING,
            "crawling",
            f"Buscando noticias de migración en {domain} (feeds, sitemaps y portada)",
        )
        discovery = self.scraper.discover(
            request.url,
            max_articles=request.max_articles,
            keywords=request.keywords or None,
            respect_robots=respect,
        )
        self.store.update_job(job_id, articles_found=len(discovery.entries))
        if not discovery.entries:
            logger.info("Sin noticias candidatas en %s", domain)

        announce(
            STEP_CLEANING,
            "cleaning",
            f"Limpiando el contenido de {len(discovery.entries)} noticias encontradas",
        )
        target_country = normalize_country(request.country)
        extracted: list[ExtractedArticle] = []
        for entry in discovery.entries:
            try:
                extracted.append(
                    self.scraper.extract(
                        entry.url,
                        respect_robots=respect,
                        country=target_country,
                        date_hint=(
                            normalize_date(entry.published) if entry.published else None
                        ),
                    )
                )
            except (FetchError, ScraperError) as exc:
                logger.info("Se descarta la noticia %s: %s", entry.url, exc)
        if discovery.entries and not extracted:
            logger.warning(
                "Ninguna noticia de %s se pudo extraer; puede que el sitio "
                "requiera JavaScript o haya cambiado su HTML.",
                domain,
            )

        announce(
            STEP_ANALYZING,
            "analyzing",
            f"Analizando {len(extracted)} noticias con el motor NLP",
        )
        articles: list[NewsArticle] = []
        analyses: list[TextAnalysisResult] = []
        for article in extracted:
            result: TextAnalysisResult | None = None
            if request.analyze:
                try:
                    result = self.scraper.analyze_extracted(
                        article, self.analysis, job_id=job_id
                    )
                except (ValueError, RuntimeError) as exc:
                    logger.warning(
                        "No se pudo analizar %s: %s", article.canonical_url, exc
                    )
                    continue
            articles.append(build_news_article(article, result))
            if result is not None:
                analyses.append(result)
            self.store.update_job(job_id, articles_analyzed=len(analyses))

        summary = build_summary(
            site_name=discovery.site_name,
            domain=discovery.domain or domain_from_url(request.url),
            country=target_country or discovery.country,
            articles=articles,
            analyses=analyses,
        )
        announce(
            STEP_COMPLETED,
            "completed",
            (
                f"Resumen generado: {summary.total_analyzed} noticias analizadas "
                f"de {summary.site_name}"
            ),
        )
        return summary

    def _fail(self, job_id: str, message: str) -> None:
        logger.warning("El job %s terminó con error: %s", job_id, message)
        self.store.update_job(
            job_id,
            status="error",
            message="La ingesta terminó con error",
            error=message,
        )
        self._inc("error")


# ---------------------------------------------------------------------------
# Cableado perezoso sobre ``app.state`` (main.py es propiedad del Lead)
# ---------------------------------------------------------------------------
_manager_lock = threading.Lock()
_scraper_lock = threading.Lock()
_fetcher_lock = threading.Lock()


def get_fetcher(app) -> SupportsGet:  # type: ignore[no-untyped-def]
    """Devuelve (y cachea en ``app.state``) el descargador HTTP de la app."""
    fetcher = getattr(app.state, "fetcher", None)
    if fetcher is not None:
        return fetcher
    from .fetching import Fetcher

    with _fetcher_lock:
        fetcher = getattr(app.state, "fetcher", None)
        if fetcher is None:
            fetcher = Fetcher(app.state.settings)
            app.state.fetcher = fetcher
    return fetcher


def get_scraper(app) -> NewsScraper:  # type: ignore[no-untyped-def]
    """Devuelve (y cachea en ``app.state``) el scraper de la app."""
    scraper = getattr(app.state, "scraper", None)
    if scraper is not None:
        return scraper
    with _scraper_lock:
        scraper = getattr(app.state, "scraper", None)
        if scraper is None:
            scraper = NewsScraper(app.state.settings, fetcher=get_fetcher(app))
            app.state.scraper = scraper
    return scraper


def get_jobs_manager(app) -> JobManager:  # type: ignore[no-untyped-def]
    """Devuelve (y cachea en ``app.state``) el gestor de jobs de la app."""
    manager = getattr(app.state, "jobs", None)
    if manager is not None:
        return manager
    with _manager_lock:
        manager = getattr(app.state, "jobs", None)
        if manager is None:
            manager = JobManager(
                app.state.settings,
                app.state.store,
                app.state.analysis,
                scraper=get_scraper(app),
                monitoring=getattr(app.state, "monitoring", None),
            )
            app.state.jobs = manager
    return manager
