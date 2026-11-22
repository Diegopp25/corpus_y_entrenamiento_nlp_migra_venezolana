"""Métricas Prometheus y estadísticas internas de monitoreo."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from ..deps import get_monitoring, get_settings, get_store
from ..schemas import DatabaseInfo, EngineInfo, MonitoringStats

router = APIRouter(tags=["monitoreo"])

PROMETHEUS_MEDIA_TYPE = "text/plain; version=0.0.4; charset=utf-8"


@router.get(
    "/metrics",
    response_class=PlainTextResponse,
    summary="Métricas en formato Prometheus",
    description=(
        "Expone contadores de peticiones, histograma de latencia, análisis por "
        "motor/sentimiento y gauges del store (análisis guardados, jobs de "
        "scraping y estado degradado del motor)."
    ),
)
def metrics(request: Request) -> PlainTextResponse:
    store = get_store(request)
    monitoring = get_monitoring(request)
    selection = request.app.state.selection
    job_stats = store.job_stats()

    gauges = {
        "nlp_api_analyses_stored": float(store.count_analyses()),
        "nlp_api_scrape_jobs_stored": float(job_stats["total"]),
        "nlp_api_engine_degraded": 1.0 if selection.degraded else 0.0,
    }
    return PlainTextResponse(
        content=monitoring.render_prometheus(gauges),
        media_type=PROMETHEUS_MEDIA_TYPE,
    )


@router.get(
    "/v1/monitoring/stats",
    response_model=MonitoringStats,
    summary="Estadísticas internas del servicio",
)
def stats(request: Request) -> MonitoringStats:
    settings = get_settings(request)
    store = get_store(request)
    monitoring = get_monitoring(request)
    selection = request.app.state.selection

    snapshot = monitoring.snapshot()
    requests_total = int(snapshot.get("requests_total", 0))
    requests_by_status = {
        str(status): int(count)
        for status, count in snapshot.get("requests_by_status", {}).items()
    }
    errors_total = int(snapshot.get("errors_total", 0))
    latency_ms = {
        "mean": float(snapshot.get("latency_mean_ms", 0.0)),
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
    }

    # Con eventos persistidos usamos el histórico de SQLite (sobrevive reinicios);
    # si están deshabilitados o aún no hay filas, mandan los contadores en memoria.
    if settings.store_events:
        events = store.event_stats()
        if events["total"]:
            requests_total = int(events["total"])
            requests_by_status = {
                str(status): int(count)
                for status, count in events["by_status"].items()
            }
            errors_total = sum(
                count
                for status, count in requests_by_status.items()
                if status.startswith("5")
            )
            latency_ms.update(
                {
                    "p50": float(events["p50"]),
                    "p95": float(events["p95"]),
                    "p99": float(events["p99"]),
                }
            )

    database_ok = store.ping()
    return MonitoringStats(
        generated_at=datetime.now(timezone.utc),
        uptime_seconds=monitoring.uptime_seconds,
        requests_total=requests_total,
        requests_by_status=requests_by_status,
        errors_total=errors_total,
        analyses_total=int(snapshot.get("analyses_total", 0)),
        analyses_by_engine={
            str(engine): int(count)
            for engine, count in snapshot.get("analyses_by_engine", {}).items()
        },
        scrape_jobs_total=int(snapshot.get("scrape_jobs_total", 0)),
        latency_ms=latency_ms,
        engine=EngineInfo(
            requested=selection.requested,
            selected=selection.selected,
            degraded=bool(selection.degraded),
            reason=selection.reason,
        ),
        database=DatabaseInfo(
            status="ok" if database_ok else "error",
            path=str(settings.database_path),
            analyses=store.count_analyses(),
            size_bytes=store.size_bytes(),
        ),
        store_events_enabled=bool(settings.store_events),
    )
