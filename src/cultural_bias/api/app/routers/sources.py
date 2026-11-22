"""Ingesta de sitios de noticias: presets, escaneos asíncronos y análisis de una URL.

Endpoints (prefijo ``/v1/sources``):

* ``GET  /presets``        — medios de noticias preconfigurados.
* ``POST /scan``           — lanza un trabajo de rastreo + análisis (202).
* ``GET  /jobs``           — lista resumida de trabajos.
* ``GET  /jobs/{job_id}``  — estado detallado de un trabajo (404 si no existe).
* ``POST /analyze-url``    — extrae UNA noticia y la analiza en línea.

Los endpoints que hacen I/O de red son ``async`` y delegan el trabajo
bloqueante en ``run_in_threadpool`` para no detener el event loop.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Query, Request
from starlette.concurrency import run_in_threadpool

from ..deps import get_analysis_service, get_settings, get_store
from ..errors import APIError
from ..schemas import (
    CamelModel,
    JobStep,
    NewsArticle,
    ScrapeAccepted,
    ScrapeJobResponse,
    ScrapeRequest,
    ScrapedSiteSummary,
    ScrapeStatus,
    SourcePreset,
)
from ..services.analysis import normalize_country
from ..services.fetching import FetchError
from ..services.jobs import TOTAL_STEPS, get_jobs_manager, get_scraper
from ..services.scraper import RobotsDeniedError, ScraperError
from ..services.site_catalog import KNOWN_SITES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/sources", tags=["ingesta de noticias"])

#: Traducción de códigos de :class:`FetchError` a ``(status, code)`` del API.
_FETCH_ERROR_STATUS: dict[str, tuple[int, str]] = {
    "invalid_scheme": (422, "invalid_url"),
    "invalid_url": (422, "invalid_url"),
    "blocked_url": (422, "url_blocked"),
    "dns_error": (422, "unresolvable_host"),
    "not_found": (404, "not_found"),
    "http_error": (503, "upstream_error"),
    "connection_error": (503, "upstream_unavailable"),
    "timeout": (503, "upstream_timeout"),
    "response_too_large": (503, "response_too_large"),
    "too_many_redirects": (503, "too_many_redirects"),
    "empty_response": (503, "upstream_error"),
    "invalid_redirect": (503, "upstream_error"),
}

#: Traducción de códigos de :class:`ScraperError` a ``(status, code)`` del API.
_SCRAPER_ERROR_STATUS: dict[str, tuple[int, str]] = {
    "robots_denied": (403, "robots_denied"),
    "extraction_failed": (422, "extraction_failed"),
    "invalid_content": (422, "invalid_content"),
    "scraper_error": (503, "scraper_error"),
}


class ScrapeJobListEntry(CamelModel):
    """Entrada resumida del listado de trabajos de ingesta.

    ``schemas.py`` no define un modelo para la lista (es propiedad del Lead),
    así que se declara aquí sin tocar el contrato compartido.
    """

    id: str
    url: str
    domain: str = ""
    status: ScrapeStatus = "queued"
    current_step: int = 0
    total_steps: int = TOTAL_STEPS
    message: str = ""
    articles_found: int = 0
    articles_analyzed: int = 0
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# Conversión de errores a respuestas del API
# ---------------------------------------------------------------------------
def _fetch_error_to_api(exc: FetchError) -> APIError:
    status, code = _FETCH_ERROR_STATUS.get(exc.code, (503, "fetch_error"))
    detail = {"url": exc.url} if exc.url else None
    return APIError(status, code, exc.message, detail)


def _scraper_error_to_api(exc: ScraperError) -> APIError:
    status, code = _SCRAPER_ERROR_STATUS.get(exc.code, (422, exc.code or "scraper_error"))
    detail = {"url": exc.url} if exc.url else None
    return APIError(status, code, exc.message, detail)


# ---------------------------------------------------------------------------
# Conversión de jobs persistidos a contrato
# ---------------------------------------------------------------------------
def _to_job_response(job: dict) -> ScrapeJobResponse:
    steps: list[JobStep] = []
    for raw_step in job.get("steps") or []:
        if not isinstance(raw_step, dict):
            continue
        try:
            steps.append(JobStep.model_validate(raw_step))
        except Exception:  # pragma: no cover - datos viejos o corruptos
            logger.warning("Paso de job inválido en %s: %s", job.get("id"), raw_step)
    summary: ScrapedSiteSummary | None = None
    raw_summary = job.get("summary")
    if isinstance(raw_summary, dict):
        try:
            summary = ScrapedSiteSummary.model_validate(raw_summary)
        except Exception:  # pragma: no cover - datos viejos o corruptos
            logger.warning("Resumen inválido en el job %s", job.get("id"))
    return ScrapeJobResponse(
        job_id=str(job.get("id", "")),
        status=job.get("status", "queued"),
        current_step=int(job.get("current_step") or 0),
        total_steps=int(job.get("total_steps") or TOTAL_STEPS),
        message=job.get("message") or "",
        articles_found_count=int(job.get("articles_found") or 0),
        articles_analyzed_count=int(job.get("articles_analyzed") or 0),
        created_at=job.get("created_at"),
        updated_at=job.get("updated_at"),
        error=job.get("error"),
        steps=steps,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get(
    "/presets",
    response_model=list[SourcePreset],
    summary="Medios de noticias preconfigurados",
)
def list_presets() -> list[SourcePreset]:
    """Catálogo de medios conocidos (``site_catalog.KNOWN_SITES``)."""
    return [SourcePreset(**site.as_dict()) for site in KNOWN_SITES]


@router.post(
    "/scan",
    response_model=ScrapeAccepted,
    status_code=202,
    summary="Inicia el rastreo y análisis de un sitio de noticias",
)
async def scan_site(payload: ScrapeRequest, request: Request) -> ScrapeAccepted:
    """Crea un job en segundo plano y devuelve su id para consultar el progreso."""
    settings = get_settings(request)
    if not settings.scraper_enabled:
        raise APIError(
            503,
            "scraper_disabled",
            "La ingesta de noticias está deshabilitada en este servidor (NLP_SCRAPER_ENABLED=false).",
        )
    max_articles = min(payload.max_articles, settings.scraper_max_articles, 10)
    if max_articles < 1:
        raise APIError(
            422,
            "invalid_max_articles",
            "maxArticles debe ser mayor o igual a 1.",
        )
    scan_request = payload.model_copy(update={"max_articles": max_articles})
    manager = await run_in_threadpool(get_jobs_manager, request.app)
    job_id = await run_in_threadpool(manager.submit, scan_request)
    logger.info(
        "Escaneo aceptado | job=%s | url=%s | max_articles=%s",
        job_id,
        scan_request.url,
        max_articles,
    )
    return ScrapeAccepted(
        job_id=job_id,
        status="queued",
        status_url=f"/v1/sources/jobs/{job_id}",
    )


@router.get(
    "/jobs",
    response_model=list[ScrapeJobListEntry],
    summary="Lista resumida de trabajos de ingesta",
)
def list_jobs(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100, description="Máximo de jobs a devolver"),
) -> list[ScrapeJobListEntry]:
    rows = get_store(request).list_jobs(limit=limit)
    return [ScrapeJobListEntry.model_validate(row) for row in rows]


@router.get(
    "/jobs/{job_id}",
    response_model=ScrapeJobResponse,
    summary="Estado detallado de un trabajo de ingesta",
)
def get_job(job_id: str, request: Request) -> ScrapeJobResponse:
    job = get_store(request).get_job(job_id)
    if job is None:
        raise APIError(404, "not_found", f"No existe el trabajo de ingesta {job_id}")
    return _to_job_response(job)


@router.post(
    "/analyze-url",
    response_model=NewsArticle,
    summary="Extrae y analiza una noticia concreta en línea",
)
async def analyze_url(payload: ScrapeRequest, request: Request) -> NewsArticle:
    """Descarga una sola noticia, extrae su texto y devuelve el análisis completo."""
    settings = get_settings(request)
    if not settings.scraper_enabled:
        raise APIError(
            503,
            "scraper_disabled",
            "La ingesta de noticias está deshabilitada en este servidor (NLP_SCRAPER_ENABLED=false).",
        )
    scraper = await run_in_threadpool(get_scraper, request.app)
    analysis = get_analysis_service(request)
    country = normalize_country(payload.country)
    try:
        return await run_in_threadpool(
            scraper.analyze_url,
            analysis,
            payload.url,
            respect_robots=payload.respect_robots,
            country=country,
        )
    except RobotsDeniedError as exc:
        raise APIError(
            403, "robots_denied", exc.message, {"url": exc.url}
        ) from exc
    except ScraperError as exc:
        raise _scraper_error_to_api(exc) from exc
    except FetchError as exc:
        raise _fetch_error_to_api(exc) from exc
    except ValueError as exc:
        raise APIError(422, "invalid_text", str(exc)) from exc
    except RuntimeError as exc:
        raise APIError(503, "engine_error", str(exc)) from exc
