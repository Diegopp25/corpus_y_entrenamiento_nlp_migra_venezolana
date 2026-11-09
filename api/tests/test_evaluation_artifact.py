"""Valida los artefactos de evaluación (``evaluation.json`` y ``thresholds.json``).

Estas pruebas NO cargan torch ni los pesos BETO: solo verifican que los
artefactos generados por ``api/scripts/evaluate_models.py`` existen, parsean,
cumplen el contrato pydantic ``ModelEvaluation`` de ``app/schemas.py`` y que los
umbrales persistidos son coherentes (ids canónicos y valores en (0, 1)).

Si los artefactos no existen todavía, la prueba se omite con un mensaje claro:
genera primero los artefactos con::

    .\\api\\.venv\\Scripts\\python.exe api\\scripts\\evaluate_models.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.engine.labels import FRAME_IDS, FRAMES, SENTIMENT_LABELS
from app.schemas import ModelEvaluation

API_DIR = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = API_DIR / "artifacts"
EVALUATION_PATH = ARTIFACTS_DIR / "evaluation.json"
THRESHOLDS_PATH = ARTIFACTS_DIR / "thresholds.json"

GENERATION_HINT = (
    "Artefactos ausentes. Genéralos con: "
    r".\api\.venv\Scripts\python.exe api\scripts\evaluate_models.py"
)

#: Mismo grid que `api/scripts/evaluate_models.py`: 0.20-0.95, paso 0.05.
THRESHOLD_GRID = [round(0.20 + 0.05 * step, 2) for step in range(16)]
TOP_LEVEL_CAMEL_KEYS = (
    "generatedAt",
    "sampleSize",
    "engine",
    "models",
    "sentiment",
    "frames",
    "confusionMatrix",
    "thresholds",
    "available",
    "message",
)


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - defensivo
        pytest.fail(f"No se pudo leer {path}: {exc}")


@pytest.fixture(scope="module")
def evaluation_file() -> dict:
    if not EVALUATION_PATH.exists():
        pytest.skip(f"Falta {EVALUATION_PATH}. {GENERATION_HINT}")
    return _load_json(EVALUATION_PATH)


@pytest.fixture(scope="module")
def thresholds_file() -> dict:
    if not THRESHOLDS_PATH.exists():
        pytest.skip(f"Falta {THRESHOLDS_PATH}. {GENERATION_HINT}")
    return _load_json(THRESHOLDS_PATH)


@pytest.fixture(scope="module")
def evaluation(evaluation_file: dict) -> ModelEvaluation:
    try:
        return ModelEvaluation.model_validate(evaluation_file)
    except Exception as exc:  # noqa: BLE001 - el mensaje importa en el reporte
        pytest.fail(f"evaluation.json no cumple el contrato ModelEvaluation: {exc}")


# ---------------------------------------------------------------------------
# Contrato y forma general
# ---------------------------------------------------------------------------
def test_evaluation_json_existe_y_es_json_valido() -> None:
    if not EVALUATION_PATH.exists():
        pytest.skip(f"Falta {EVALUATION_PATH}. {GENERATION_HINT}")
    doc = _load_json(EVALUATION_PATH)
    assert isinstance(doc, dict), "evaluation.json debe ser un objeto JSON"


def test_evaluation_usa_camel_case_del_contrato(evaluation_file: dict) -> None:
    for key in TOP_LEVEL_CAMEL_KEYS:
        assert key in evaluation_file, f"Falta la clave camelCase {key!r}"
    for snake in ("generated_at", "sample_size", "is_best", "f1_score"):
        assert snake not in evaluation_file, f"evaluation.json no debe usar {snake!r}"


def test_evaluation_valida_contra_pydantic(evaluation: ModelEvaluation) -> None:
    assert evaluation.available is True
    assert evaluation.engine == "bert_pair"
    assert evaluation.message.strip(), "message no debe estar vacío"
    assert evaluation.sample_size > 0
    assert evaluation.generated_at is not None
    generated = evaluation.generated_at
    assert isinstance(generated, datetime)
    assert generated.tzinfo is not None, "generatedAt debe incluir zona horaria"
    assert generated.utcoffset() == timezone.utc.utcoffset(None)


# ---------------------------------------------------------------------------
# Modelos evaluados
# ---------------------------------------------------------------------------
def test_models_incluyen_los_beto_reales(evaluation: ModelEvaluation) -> None:
    assert len(evaluation.models) >= 2
    roles = {metric.role for metric in evaluation.models}
    assert "sentiment" in roles
    assert "frames" in roles

    real_entries = [
        metric
        for metric in evaluation.models
        if metric.model_name == "BETO-migra-ve (sentimiento + encuadres)"
    ]
    assert len(real_entries) >= 2, (
        "Se esperaban las dos cabezas BETO reales (sentimiento y encuadres) "
        f"con el nombre canónico; models: {[m.model_name for m in evaluation.models]}"
    )
    for metric in evaluation.models:
        assert metric.architecture.strip()
        assert metric.samples == evaluation.sample_size
        if metric.f1_score is not None:
            assert 0.0 <= metric.f1_score <= 1.0
        if metric.accuracy is not None:
            assert 0.0 <= metric.accuracy <= 1.0

    best = [metric for metric in evaluation.models if metric.is_best]
    assert len(best) == 1, "Debe haber exactamente un modelo marcado como isBest"


# ---------------------------------------------------------------------------
# Sentimiento
# ---------------------------------------------------------------------------
def test_sentiment_metricas_coherentes(evaluation: ModelEvaluation) -> None:
    sentiment = evaluation.sentiment
    for key in ("accuracy", "macroF1", "perClass", "confusionMatrix", "samples"):
        assert key in sentiment, f"sentiment.{key} es obligatorio"

    assert sentiment["samples"] == evaluation.sample_size
    assert 0.0 <= sentiment["accuracy"] <= 1.0
    assert 0.0 <= sentiment["macroF1"] <= 1.0

    per_class = sentiment["perClass"]
    assert set(per_class) == set(SENTIMENT_LABELS)
    total_support = 0
    for label, metrics in per_class.items():
        for key in ("precision", "recall", "f1", "support"):
            assert key in metrics, f"perClass[{label}] sin {key}"
        assert 0.0 <= metrics["precision"] <= 1.0
        assert 0.0 <= metrics["recall"] <= 1.0
        assert 0.0 <= metrics["f1"] <= 1.0
        assert isinstance(metrics["support"], int)
        total_support += metrics["support"]
    assert total_support == evaluation.sample_size


def test_evaluation_confusion_matrix_3x3(evaluation: ModelEvaluation) -> None:
    matrix = evaluation.confusion_matrix
    assert matrix is not None
    assert list(matrix.labels) == list(SENTIMENT_LABELS)
    assert len(matrix.matrix) == 3
    assert all(len(row) == 3 for row in matrix.matrix)
    assert all(isinstance(value, int) and value >= 0 for row in matrix.matrix for value in row)
    assert sum(sum(row) for row in matrix.matrix) == evaluation.sample_size

    # Coherencia entre la matriz anidada en sentiment y la de primer nivel.
    nested = evaluation.sentiment["confusionMatrix"]
    assert nested["labels"] == matrix.labels
    assert nested["matrix"] == matrix.matrix
    assert evaluation.sentiment["accuracy"] == pytest.approx(
        sum(matrix.matrix[i][i] for i in range(3)) / evaluation.sample_size,
        abs=1e-3,  # el artefacto redondea a 4 decimales
    )


# ---------------------------------------------------------------------------
# Encuadres
# ---------------------------------------------------------------------------
def test_frames_completos_y_metricas_validas(evaluation: ModelEvaluation) -> None:
    assert len(evaluation.frames) == len(FRAME_IDS)
    assert {frame.frame_id for frame in evaluation.frames} == set(FRAME_IDS)
    assert [frame.frame_id for frame in evaluation.frames] == list(FRAME_IDS)

    for frame in evaluation.frames:
        assert frame.frame == FRAMES[frame.frame_id]["label"]
        assert 0.0 <= frame.precision <= 1.0
        assert 0.0 <= frame.recall <= 1.0
        assert 0.0 <= frame.f1 <= 1.0
        assert 0 <= frame.support <= evaluation.sample_size
        assert 0.0 < frame.threshold < 1.0
        assert 0.20 - 1e-9 <= frame.threshold <= 0.95 + 1e-9
        assert round(frame.threshold, 2) in THRESHOLD_GRID


# ---------------------------------------------------------------------------
# Umbrales: evaluation.json y thresholds.json deben coincidir
# ---------------------------------------------------------------------------
def test_thresholds_coherentes(
    evaluation: ModelEvaluation, thresholds_file: dict
) -> None:
    assert isinstance(thresholds_file, dict), "thresholds.json debe ser un objeto JSON"
    assert set(thresholds_file) == set(FRAME_IDS), (
        "thresholds.json debe tener los 7 ids canónicos; "
        f"encontrado: {sorted(thresholds_file)}"
    )
    for frame_id, value in thresholds_file.items():
        assert isinstance(value, (int, float)) and not isinstance(value, bool)
        assert 0.0 < float(value) < 1.0, f"Umbral fuera de (0, 1) para {frame_id}: {value}"

    assert set(evaluation.thresholds) == set(FRAME_IDS)
    for frame in evaluation.frames:
        assert evaluation.thresholds[frame.frame_id] == pytest.approx(
            float(thresholds_file[frame.frame_id]), abs=1e-9
        )
        assert evaluation.thresholds[frame.frame_id] == pytest.approx(
            frame.threshold, abs=1e-9
        )


def test_politica_de_umbrales_documentada(evaluation: ModelEvaluation) -> None:
    """Política: max F1 con precisión>=0.50 y recall>=0.20 (grid 0.20-0.95).

    Los frames que quedan fuera del punto de operación (no alcanzan ambas
    restricciones) deben estar documentados en ``message`` con la frase
    "se prioriza precisión".
    """
    for frame in evaluation.frames:
        satisfies = (
            frame.precision + 1e-9 >= 0.50 and frame.recall + 1e-9 >= 0.20
        )
        if satisfies:
            continue
        assert frame.frame in evaluation.message, (
            f"El frame {frame.frame!r} no cumple la política de umbral "
            "(precisión>=0.50 y recall>=0.20) y no aparece documentado en message"
        )
        assert "se prioriza precisión" in evaluation.message, (
            "Los frames en fallback deben documentarse como 'se prioriza precisión'"
        )


def test_message_declara_alcance_y_limitacion(evaluation: ModelEvaluation) -> None:
    """Transparencia: alcance completo del corpus, solapamiento y latencia."""
    message = evaluation.message
    assert str(evaluation.sample_size) in message
    assert "corpus etiquetado completo" in message
    assert "solapamiento" in message
    assert "fuera de muestra" in message
    assert "latencia media" in message


def test_generated_at_es_reciente(evaluation: ModelEvaluation) -> None:
    """Un artefacto viejo (> 30 días) probablemente no refleja los modelos actuales."""
    generated = evaluation.generated_at
    assert generated is not None
    age_days = (datetime.now(timezone.utc) - generated).total_seconds() / 86_400
    assert age_days < 30, f"evaluation.json tiene {age_days:.1f} días; regenera el artefacto"
