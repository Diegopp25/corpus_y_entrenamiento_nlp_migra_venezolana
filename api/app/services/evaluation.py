"""Artefacto de evaluación de modelos (``api/artifacts/evaluation.json``).

El script de evaluación de modelos escribe un JSON con las métricas reales de
BETO. Este módulo lo adapta al contrato ``ModelEvaluation`` del API de forma
tolerante: si el archivo no existe (o está incompleto/corrupto) se devuelve una
respuesta ``available=False`` con un mensaje claro, nunca un error 500.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import Settings
from ..schemas import (
    ConfusionMatrix,
    FrameEvaluation,
    ModelEvaluation,
    ModelMetric,
)


def _pick(mapping: dict[str, Any], *names: str) -> Any:
    """Primer valor no nulo de una lista de claves alternativas."""
    for name in names:
        if name in mapping and mapping[name] is not None:
            return mapping[name]
    return None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _number(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _integer(value: Any, default: int = 0) -> int:
    number = _number(value, None)
    return int(number) if number is not None else default


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "si", "sí", "yes"}
    return bool(value)


def _to_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _model_metric(item: Any) -> ModelMetric | None:
    data = _as_dict(item)
    if not data:
        return None
    return ModelMetric(
        model_name=_text(
            _pick(data, "model_name", "modelName", "name", "model"),
            "modelo-sin-nombre",
        ),
        architecture=_text(_pick(data, "architecture", "arquitectura")),
        role=_text(_pick(data, "role", "rol")),
        accuracy=_number(_pick(data, "accuracy", "exactitud")),
        precision=_number(_pick(data, "precision", "precisión")),
        recall=_number(_pick(data, "recall", "exhaustividad")),
        f1_score=_number(_pick(data, "f1_score", "f1Score", "f1")),
        samples=(
            None
            if _pick(data, "samples", "sample_size", "sampleSize", "n") is None
            else _integer(_pick(data, "samples", "sample_size", "sampleSize", "n"))
        ),
        is_best=_flag(_pick(data, "is_best", "isBest", "best")),
    )


def _frame_evaluation(item: Any) -> FrameEvaluation | None:
    data = _as_dict(item)
    if not data:
        return None
    frame_id = _pick(data, "frame_id", "frameId")
    frame = _pick(data, "frame", "frame_name", "frameName", "name", "label")
    return FrameEvaluation(
        frame=_text(frame, _text(frame_id, "Encuadre")),
        frame_id=_text(frame_id) or None,
        precision=_number(_pick(data, "precision", "precisión"), 0.0) or 0.0,
        recall=_number(_pick(data, "recall", "exhaustividad"), 0.0) or 0.0,
        f1=_number(_pick(data, "f1", "f1_score", "f1Score"), 0.0) or 0.0,
        support=_integer(_pick(data, "support", "samples", "sample_size", "sampleSize")),
        threshold=_number(_pick(data, "threshold", "umbral"), 0.5) or 0.5,
    )


def _confusion_matrix(value: Any) -> ConfusionMatrix | None:
    data = _as_dict(value)
    labels = data.get("labels")
    matrix = data.get("matrix")
    if not isinstance(labels, list) or not isinstance(matrix, list) or not matrix:
        return None
    rows: list[list[int]] = []
    for row in matrix:
        if isinstance(row, (list, tuple)):
            rows.append([_integer(cell) for cell in row])
    if not rows:
        return None
    return ConfusionMatrix(labels=[str(label) for label in labels], matrix=rows)


def _thresholds(value: Any) -> dict[str, float]:
    thresholds: dict[str, float] = {}
    for key, raw in _as_dict(value).items():
        number = _number(raw)
        if number is not None:
            thresholds[str(key)] = number
    return thresholds


def _adapt(raw: dict[str, Any]) -> ModelEvaluation:
    sentiment = _as_dict(
        _pick(raw, "sentiment", "sentiment_metrics", "sentimentMetrics")
    )
    confusion_raw = _pick(raw, "confusion_matrix", "confusionMatrix")
    if confusion_raw is None and sentiment:
        confusion_raw = _pick(sentiment, "confusion_matrix", "confusionMatrix")

    models = [
        metric
        for metric in (
            _model_metric(item)
            for item in _as_list(
                _pick(raw, "models", "benchmark", "benchmarks",
                      "model_metrics", "modelMetrics")
            )
        )
        if metric is not None
    ]
    frames = [
        evaluation
        for evaluation in (
            _frame_evaluation(item)
            for item in _as_list(
                _pick(raw, "frames", "frame_evaluation", "frameEvaluation",
                      "frames_performance", "framesPerformance")
            )
        )
        if evaluation is not None
    ]

    available = _flag(raw.get("available", True))
    default_message = (
        "Métricas de evaluación disponibles"
        if available
        else "El artefacto de evaluación no reporta métricas disponibles"
    )
    return ModelEvaluation(
        generated_at=_to_datetime(
            _pick(raw, "generated_at", "generatedAt", "date", "timestamp")
        ),
        sample_size=_integer(
            _pick(raw, "sample_size", "sampleSize", "samples", "n_samples", "nSamples")
        ),
        engine=_text(_pick(raw, "engine", "model", "model_name", "modelName")),
        models=models,
        sentiment=sentiment,
        frames=frames,
        confusion_matrix=_confusion_matrix(confusion_raw),
        thresholds=_thresholds(_pick(raw, "thresholds", "umbrales")),
        available=available,
        message=_text(raw.get("message"), default_message),
    )


def unavailable(message: str) -> ModelEvaluation:
    return ModelEvaluation(available=False, message=message)


def load_evaluation(settings: Settings) -> ModelEvaluation:
    """Carga el artefacto de evaluación; si falla devuelve ``available=False``."""
    path = Path(settings.evaluation_path)
    if not path.exists():
        return unavailable(
            f"No hay artefacto de evaluación en {path}. Ejecuta la evaluación "
            "de modelos (api/scripts/evaluate_models.py) para generarlo."
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return unavailable(
            f"No se pudo leer el artefacto de evaluación {path.name}: {exc}"
        )
    if not isinstance(raw, dict):
        return unavailable(
            f"El artefacto de evaluación {path.name} no tiene el formato esperado "
            "(se esperaba un objeto JSON)"
        )
    try:
        return _adapt(raw)
    except (TypeError, ValueError) as exc:  # pragma: no cover - datos muy raros
        return unavailable(
            f"El artefacto de evaluación {path.name} es inconsistente: {exc}"
        )
