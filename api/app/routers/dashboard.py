"""Dashboard agregado del frontend.

Todos los endpoints son de solo lectura y se calculan a partir de las tablas
del ``Store`` (análisis y jobs) o del CSV etiquetado. Si todavía no hay
análisis guardados las respuestas son deterministas y con ceros, para que el
dashboard pueda arrancar sin datos.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query, Request

from ..deps import get_monitoring, get_settings, get_store
from ..errors import APIError
from ..schemas import (
    AnalysisSummary,
    CorpusDashboard,
    CountryCount,
    DashboardOverview,
    EngineCount,
    FrameTally,
    LatencyStats,
    MediaCount,
    ModelEvaluation,
    ScrapeJobStats,
    SentimentCounts,
    TimeseriesPoint,
    TimeseriesResponse,
)
from ..services.corpus import CorpusError, load_corpus, percentage_counts
from ..services.evaluation import load_evaluation

router = APIRouter(prefix="/v1/dashboard", tags=["dashboard"])

TOP_FRAMES_LIMIT = 5


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="milliseconds")


def _sentiment_counts(raw: dict[str, int]) -> SentimentCounts:
    """Convierte los conteos capitalizados del store al contrato (minúsculas)."""
    return SentimentCounts(
        negativo=int(raw.get("Negativo", raw.get("negativo", 0)) or 0),
        neutro=int(raw.get("Neutro", raw.get("neutro", 0)) or 0),
        positivo=int(raw.get("Positivo", raw.get("positivo", 0)) or 0),
    )


@router.get(
    "/overview",
    response_model=DashboardOverview,
    summary="Agregados generales para el dashboard",
)
def overview(request: Request) -> DashboardOverview:
    store = get_store(request)
    monitoring = get_monitoring(request)
    selection = request.app.state.selection

    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    last_7d = now - timedelta(days=7)

    sentiment_counts = store.sentiment_counts()
    total_analyses = store.count_analyses()
    latency = store.latency_stats()
    frames = store.frame_counts()

    return DashboardOverview(
        generated_at=now,
        total_analyses=total_analyses,
        analyses_today=store.count_analyses(since=_iso(start_of_day)),
        analyses_last_7d=store.count_analyses(since=_iso(last_7d)),
        avg_confidence=store.avg_confidence(),
        sentiment=_sentiment_counts(sentiment_counts),
        sentiment_pct=percentage_counts(sentiment_counts, total_analyses),
        top_frames=[
            FrameTally(frame=row["frame"], percentage=row["percentage"])
            for row in frames[:TOP_FRAMES_LIMIT]
        ],
        countries=[
            CountryCount(
                country=row["country"],
                count=row["count"],
                sentiment=_sentiment_counts(row["sentiment"]),
            )
            for row in store.country_counts()
        ],
        media=[
            MediaCount(
                media=row["media"],
                count=row["count"],
                sentiment=_sentiment_counts(row["sentiment"]),
            )
            for row in store.media_counts()
        ],
        engines=[
            EngineCount(engine=row["engine"], count=row["count"])
            for row in store.engine_counts()
        ],
        latency_ms=LatencyStats(**latency),
        scrape_jobs=ScrapeJobStats(**store.job_stats()),
        uptime_seconds=monitoring.uptime_seconds,
        engine=selection.selected,
        degraded=bool(selection.degraded),
    )


@router.get(
    "/timeseries",
    response_model=TimeseriesResponse,
    summary="Serie diaria de análisis por sentimiento",
)
def timeseries(
    request: Request,
    days: int = Query(default=30, ge=1, le=365, description="Ventana en días"),
) -> TimeseriesResponse:
    rows = get_store(request).daily_sentiment_counts(days)
    return TimeseriesResponse(
        days=days,
        items=[
            TimeseriesPoint(
                date=row["date"],
                total=row["total"],
                negativo=row["negativo"],
                neutro=row["neutro"],
                positivo=row["positivo"],
            )
            for row in rows
        ],
    )


@router.get(
    "/corpus",
    response_model=CorpusDashboard,
    summary="Estadísticas del corpus etiquetado (CSV)",
)
def corpus_dashboard(request: Request) -> CorpusDashboard:
    try:
        return load_corpus(get_settings(request))
    except CorpusError as exc:
        raise APIError(503, "corpus_unavailable", str(exc)) from exc


@router.get(
    "/models",
    response_model=ModelEvaluation,
    summary="Métricas de evaluación de modelos",
)
def models_evaluation(request: Request) -> ModelEvaluation:
    return load_evaluation(get_settings(request))


@router.get(
    "/recent",
    response_model=list[AnalysisSummary],
    summary="Análisis recientes",
)
def recent_analyses(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[AnalysisSummary]:
    rows = get_store(request).list_analyses(limit=limit)
    return [
        AnalysisSummary(
            id=row["id"],
            created_at=row["created_at"],
            title=row["title"],
            media_name=row["media_name"],
            country=row["country"],
            sentiment=row["sentiment"],
            confidence=row["confidence"],
            source=row["source"],
            engine=row["engine"],
            latency_ms=row["latency_ms"],
        )
        for row in rows
    ]
