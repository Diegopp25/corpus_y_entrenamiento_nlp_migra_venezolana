"""Análisis de textos: individual, por lotes e historial."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query, Request

from ..config import Settings
from ..deps import get_analysis_service, get_settings, get_store
from ..errors import APIError
from ..schemas import (
    AnalysesPage,
    AnalyzeRequest,
    AnalysisSummary,
    BatchAnalyzeRequest,
    BatchAnalyzeResponse,
    TextAnalysisResult,
)

router = APIRouter(prefix="/v1", tags=["análisis"])


@router.post(
    "/analyze",
    response_model=TextAnalysisResult,
    summary="Analiza un texto (sentimiento + encuadres + sesgo cultural)",
)
def analyze(payload: AnalyzeRequest, request: Request) -> TextAnalysisResult:
    service = get_analysis_service(request)
    try:
        return service.analyze_request(payload, source="api")
    except ValueError as exc:
        raise APIError(422, "invalid_text", str(exc)) from exc
    except RuntimeError as exc:
        raise APIError(503, "engine_error", str(exc)) from exc


@router.post(
    "/analyze/batch",
    response_model=BatchAnalyzeResponse,
    summary="Analiza varios textos en una sola petición",
)
def analyze_batch(payload: BatchAnalyzeRequest, request: Request) -> BatchAnalyzeResponse:
    settings: Settings = get_settings(request)
    if len(payload.items) > settings.max_batch_items:
        raise APIError(
            422,
            "batch_too_large",
            f"El lote supera el máximo de {settings.max_batch_items} textos",
        )
    service = get_analysis_service(request)
    try:
        results = service.analyze_many(payload.items, source="api")
    except ValueError as exc:
        raise APIError(422, "invalid_text", str(exc)) from exc
    except RuntimeError as exc:
        raise APIError(503, "engine_error", str(exc)) from exc
    return BatchAnalyzeResponse(count=len(results), results=results)


@router.get(
    "/analyses",
    response_model=AnalysesPage,
    summary="Historial de análisis (para el dashboard)",
)
def list_analyses(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sentiment: str | None = Query(default=None, pattern="^(Negativo|Neutro|Positivo)$"),
    country: str | None = None,
    source: str | None = None,
    since: datetime | None = None,
) -> AnalysesPage:
    store = get_store(request)
    since_iso = since.isoformat() if since else None
    rows = store.list_analyses(
        limit=limit,
        offset=offset,
        sentiment=sentiment,
        country=country,
        source=source,
        since=since_iso,
    )
    total = store.count_analyses(
        since=since_iso, sentiment=sentiment, country=country, source=source
    )
    items = [
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
    return AnalysesPage(total=total, limit=limit, offset=offset, items=items)


@router.get(
    "/analyses/{analysis_id}",
    response_model=TextAnalysisResult,
    summary="Recupera un análisis guardado",
)
def get_analysis(analysis_id: str, request: Request) -> TextAnalysisResult:
    payload = get_store(request).get_analysis(analysis_id)
    if not payload:
        raise APIError(404, "not_found", f"No existe el análisis {analysis_id}")
    payload.pop("_truncated", None)
    payload.pop("_textHash", None)
    try:
        return TextAnalysisResult.model_validate(payload)
    except Exception as exc:  # pragma: no cover - datos ya validados al guardar
        raise APIError(
            500, "invalid_payload", "El análisis guardado no se pudo reconstruir"
        ) from exc
