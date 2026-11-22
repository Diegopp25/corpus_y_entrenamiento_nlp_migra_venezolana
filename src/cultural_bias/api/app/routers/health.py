"""Salud del servicio, modelos cargados y catálogo de etiquetas."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request

from ..config import Settings
from ..deps import get_monitoring, get_settings, get_store
from ..engine.labels import FRAMES, FRAME_IDS, SENTIMENT_LABELS
from ..schemas import (
    DatabaseInfo,
    EngineInfo,
    HealthResponse,
    ModelInfo,
    ModelsResponse,
)

router = APIRouter(prefix="/v1", tags=["salud y modelos"])


@router.get("/health", response_model=HealthResponse, summary="Estado del servicio")
def health(request: Request) -> HealthResponse:
    settings: Settings = get_settings(request)
    store = get_store(request)
    monitoring = get_monitoring(request)
    selection = request.app.state.selection
    database_ok = store.ping()

    models = [
        ModelInfo(
            name=descriptor.name,
            role=descriptor.role,
            available=descriptor.available,
            loaded=descriptor.loaded,
            architecture=descriptor.architecture,
            path=descriptor.path,
            max_length=descriptor.max_length,
            device=descriptor.device,
            labels=descriptor.labels,
        )
        for descriptor in selection.engine.models
    ]
    degraded = selection.degraded or not database_ok or not selection.engine.models
    return HealthResponse(
        status="degraded" if degraded else "ok",
        version=settings.version,
        environment=settings.environment,
        uptime_seconds=monitoring.uptime_seconds,
        started_at=datetime.fromtimestamp(monitoring.started_at, tz=timezone.utc),
        engine=EngineInfo(
            requested=selection.requested,
            selected=selection.selected,
            degraded=selection.degraded,
            reason=selection.reason,
        ),
        models=models,
        database=DatabaseInfo(
            status="ok" if database_ok else "error",
            path=str(settings.database_path),
            analyses=store.count_analyses(),
            size_bytes=store.size_bytes(),
        ),
        scraper_enabled=settings.scraper_enabled,
    )


@router.get("/models", response_model=ModelsResponse, summary="Modelos y umbrales")
def models(request: Request) -> ModelsResponse:
    settings: Settings = get_settings(request)
    selection = request.app.state.selection
    thresholds = {
        frame_id: float(
            selection.engine.thresholds.get(frame_id, settings.frame_threshold)
        )
        for frame_id in FRAME_IDS
    }
    frame_labels = [
        {
            "id": frame_id,
            "label": FRAMES[frame_id]["label"],
            "model_label": FRAMES[frame_id]["model_label"],
            "description": FRAMES[frame_id]["description"],
            "keywords": FRAMES[frame_id]["keywords"],
            "threshold": thresholds[frame_id],
        }
        for frame_id in FRAME_IDS
    ]
    return ModelsResponse(
        engine=EngineInfo(
            requested=selection.requested,
            selected=selection.selected,
            degraded=selection.degraded,
            reason=selection.reason,
        ),
        models=[
            ModelInfo(
                name=descriptor.name,
                role=descriptor.role,
                available=descriptor.available,
                loaded=descriptor.loaded,
                architecture=descriptor.architecture,
                path=descriptor.path,
                max_length=descriptor.max_length,
                device=descriptor.device,
                labels=descriptor.labels,
            )
            for descriptor in selection.engine.models
        ],
        sentiment_labels=SENTIMENT_LABELS,
        frame_labels=frame_labels,
        thresholds=thresholds,
        evaluation_available=settings.evaluation_path.exists(),
    )
