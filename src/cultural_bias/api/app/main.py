"""Aplicación FastAPI: composición de routers, middlewares y ciclo de vida."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .config import Settings, get_settings
from .engine import AnalysisEngine, EngineSelection, build_engine
from .errors import install_exception_handlers
from .middleware import AccessMiddleware
from .routers import analyze, dashboard, health, monitoring, sources
from .services.analysis import AnalysisService
from .services.monitoring import Monitoring
from .services.store import Store

logger = logging.getLogger(__name__)


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def create_app(
    settings: Settings | None = None,
    engine: AnalysisEngine | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    if engine is not None:
        selection = EngineSelection(
            engine=engine,
            requested=settings.engine,
            selected=engine.name,
            degraded=False,
            reason="motor inyectado (tests)",
        )
    else:
        selection = build_engine(settings)

    store = Store(settings.database_path)
    monitoring_service = Monitoring()
    analysis_service = AnalysisService(
        selection.engine,
        store,
        settings,
        monitoring_service,
        requested_engine=selection.requested,
        degraded=selection.degraded,
        reason=selection.reason,
    )

    @asynccontextmanager
    async def lifespan(_application: FastAPI):
        settings.ensure_directories()
        store.init_schema()
        store.prune_events(days=30)
        store.prune_jobs(ttl_hours=settings.scraper_job_ttl_hours)
        logger.info(
            "API lista | motor=%s | degradado=%s | modelos=%s | db=%s",
            selection.selected,
            selection.degraded,
            [descriptor.name for descriptor in selection.engine.models],
            settings.database_path,
        )
        try:
            yield
        finally:
            # Cierre ordenado de recursos perezosos registrados por los servicios
            # (scraper: executor/httpx). Se hace por duck-typing para no acoplar
            # main.py a los servicios opcionales.
            for resource_name in ("jobs", "scraper", "fetcher"):
                resource = getattr(_application.state, resource_name, None)
                closer = getattr(resource, "close", None) or getattr(
                    resource, "shutdown", None
                )
                if callable(closer):
                    try:
                        closer()
                    except Exception:  # pragma: no cover - mejor esfuerzo
                        logger.warning("No se pudo cerrar %s", resource_name)
            selection.engine.unload()

    docs_url = "/docs" if settings.docs_enabled else None
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "API de análisis de cobertura mediática de la migración venezolana "
            "en Colombia y México. Incluye análisis de sentimiento y encuadres "
            "con modelos BETO, ingesta automática de noticias y endpoints de "
            "dashboard y monitoreo."
        ),
        docs_url=docs_url,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
        contact={
            "name": "Proyecto Cultural Bias — migración venezolana",
            "url": "https://github.com/Diegopp25/corpus_y_entrenamiento_nlp_migra_venezolana",
        },
        license_info={"name": "MIT"},
        openapi_tags=[
            {"name": "análisis", "description": "Análisis de sentimiento, encuadres y sesgo cultural."},
            {"name": "ingesta de noticias", "description": "Descubrimiento y análisis automático de sitios de noticias."},
            {"name": "dashboard", "description": "Agregados para el dashboard del frontend."},
            {"name": "monitoreo", "description": "Métricas Prometheus y estadísticas internas."},
            {"name": "salud y modelos", "description": "Estado del servicio y modelos cargados."},
        ],
    )

    app.state.settings = settings
    app.state.store = store
    app.state.selection = selection
    app.state.engine = selection.engine
    app.state.monitoring = monitoring_service
    app.state.analysis = analysis_service

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Process-Time-Ms", "Retry-After"],
    )
    app.add_middleware(
        AccessMiddleware,
        settings=settings,
        monitoring=monitoring_service,
        store=store,
        engine_name=selection.selected,
    )
    install_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(analyze.router)
    app.include_router(sources.router)
    app.include_router(dashboard.router)
    app.include_router(monitoring.router)

    @app.get("/", tags=["salud y modelos"], summary="Información del servicio")
    def root() -> dict[str, Any]:
        return {
            "service": settings.app_name,
            "version": __version__,
            "environment": settings.environment,
            "docs": docs_url or "deshabilitado",
            "endpoints": {
                "analizar": "/v1/analyze",
                "analizar_lote": "/v1/analyze/batch",
                "historial": "/v1/analyses",
                "sitios": "/v1/sources/presets",
                "escanear_sitio": "/v1/sources/scan",
                "dashboard": "/v1/dashboard/overview",
                "monitoreo": "/v1/monitoring/stats",
                "metricas_prometheus": "/metrics",
                "salud": "/v1/health",
            },
        }

    return app


app = create_app()

if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
