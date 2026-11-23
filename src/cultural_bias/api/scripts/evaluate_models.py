#!/usr/bin/env python
"""Evaluación real de los modelos BETO del proyecto (sentimiento + encuadres).

Este script corre el MISMO motor que usará el API en producción
(``app.engine.bert_pair.BertPairEngine``) sobre el corpus etiquetado, calcula
métricas de clasificación y escribe dos artefactos que consume el dashboard:

* ``api/artifacts/evaluation.json``: contrato ``ModelEvaluation`` de
  ``app/schemas.py`` (camelCase, validable con pydantic).
* ``api/artifacts/thresholds.json``: ``{frame_id: umbral_óptimo}`` con los ids
  canónicos del frontend (``seguridad``, ``empleo_economia``, ...). El motor
  de producción los carga con ``load_thresholds`` al arrancar.

Uso reproducible desde la raíz del repositorio::

    # Windows (venv del API con torch/transformers)
    .\\api\\.venv\\Scripts\\python.exe api\\scripts\\evaluate_models.py

    # Linux/macOS
    api/.venv/bin/python api/scripts/evaluate_models.py

    # Variantes útiles
    ... --sample-size 250 --batch-size 8
    ... --csv Data/dataset_migracion_venezolana_labeled.csv
    ... --sentiment-model-dir C:\\ruta\\modelo_sentimiento --frames-model-dir C:\\ruta\\modelo_encuadre

Supuestos documentados (validados por el Lead y reconfirmados con esta muestra):

1. Los modelos esperan **texto crudo** (columna ``Cuerpo`` completa). Con el
   texto lematizado de ``dataset_preprocessed.csv``/``texto_procesado`` la
   accuracy de sentimiento cae a ~50 % y los encuadres a AUC ~0.6: el modelo se
   entrenó con noticias completas. El motor limpia HTML/URLs internamente con
   ``clean_text``, pero no lematiza.
2. Orden de salida del modelo de sentimiento: ``[Negativo, Neutro, Positivo]``.
3. Orden de salida del modelo de encuadres (7 salidas sigmoide):
   ``[Acceso_a_servicios, Empleo_y_economía, Integración_social, Otros,
   Politica_migratoria, Seguridad, Transito_migratorio]``.
4. La muestra es **estratificada por sentimiento** con ``random_state`` fijo
   (42 por defecto) para que la evaluación sea reproducible. Si el corpus tiene
   menos filas que ``--sample-size`` se evalúa el corpus completo y se avisa.
5. **Política de umbral por encuadre** (grid ``0.20..0.95``, paso 0.05):
   1) maximizar F1 *sujeto a* ``precisión >= 0.50`` y ``recall >= 0.20``;
   2) si ningún umbral cumple ambas, se prioriza la precisión: mayor
      precisión con desempate por mayor F1, documentado como "sin punto de
      operación con precisión>=0.5; se prioriza precisión";
   3) si ni siquiera se alcanza precisión 0.50 en el grid, el umbral queda en
      ``0.50`` por defecto (también documentado). Ese umbral de operación es el
      que se persiste en ``thresholds.json`` y evita que el dashboard marque
      casi todo como activo en los frames raros.
6. **Transparencia**: ``evaluation.json`` declara en ``message`` que la
   evaluación usa el corpus etiquetado completo (156 artículos) y que, al no
   disponerse del split de entrenamiento del modelo, las métricas pueden estar
   influidas por solapamiento con los datos de entrenamiento: no son una
   estimación limpia fuera de muestra. ``frames[]`` reporta P/R/F1 en el
   umbral de operación; ``models[]`` guarda las métricas macro a umbral 0.50.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import sys
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

API_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = API_DIR.parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from app.engine.base import EngineUnavailable  # noqa: E402
from app.engine.bert_pair import BertPairEngine, model_dir_ready  # noqa: E402
from app.engine.labels import (  # noqa: E402
    FRAME_IDS,
    FRAME_MODEL_ORDER,
    FRAMES,
    MODEL_DISPLAY_NAME,
    SENTIMENT_LABELS,
)
from app.schemas import (  # noqa: E402
    ConfusionMatrix,
    FrameEvaluation,
    ModelEvaluation,
    ModelMetric,
)

# ---------------------------------------------------------------------------
# Valores por defecto
# ---------------------------------------------------------------------------
DEFAULT_CSV = "Data/dataset_migracion_venezolana_labeled.csv"
DEFAULT_OUTPUT = str(API_DIR / "artifacts" / "evaluation.json")
DEFAULT_THRESHOLDS_OUTPUT = str(API_DIR / "artifacts" / "thresholds.json")
DEFAULT_SENTIMENT_DIR = Path.home() / "Desktop" / "proyecto" / "modelo_sentimiento"
DEFAULT_FRAMES_DIR = Path.home() / "Desktop" / "proyecto" / "modelo_encuadre"
DEFAULT_RANDOM_STATE = 42
DEFAULT_BATCH_SIZE = 8
DEFAULT_SAMPLE_SIZE = 250
DEFAULT_MAX_LENGTH = 512

#: Grid de búsqueda del umbral de operación por encuadre (0.20-0.95, paso 0.05).
THRESHOLD_GRID: tuple[float, ...] = tuple(
    round(0.20 + 0.05 * step, 2) for step in range(16)
)

#: Política del umbral de operación: maximizar F1 con un punto de operación
#: razonable (evita que el dashboard marque casi todo como activo en frames
#: raros con recall 1.0 y precisión 0.2).
MIN_PRECISION_AT_OPERATING_POINT = 0.50
MIN_RECALL_AT_OPERATING_POINT = 0.20

#: Motivos de fallback del umbral de operación por frame.
FALLBACK_PRIORITY_PRECISION = "priority_precision"  # sin recall, se prioriza P
FALLBACK_DEFAULT_05 = "default_05"  # ni siquiera se alcanza P=0.50 en el grid

SENTIMENT_ALIASES = {
    "negativo": "Negativo",
    "negative": "Negativo",
    "neg": "Negativo",
    "neutro": "Neutro",
    "neutral": "Neutro",
    "neu": "Neutro",
    "positivo": "Positivo",
    "positive": "Positivo",
    "pos": "Positivo",
}

TEXT_COLUMN_CANDIDATES = ("cuerpo", "texto", "body", "text")
SENTIMENT_COLUMN_CANDIDATES = ("sentimiento", "sentiment", "label")

#: Ruta absoluta contra la que se resuelven los paths relativos del CLI.
_PATH_BASES = (Path.cwd(), REPO_DIR, API_DIR)


# ---------------------------------------------------------------------------
# Utilidades de normalización / paths
# ---------------------------------------------------------------------------
def normalize_header(value: str) -> str:
    """Normaliza un nombre de columna: sin BOM, mojibake reparado, NFC, casefold."""
    text = str(value or "").strip().lstrip("\ufeff")
    repaired = _repair_mojibake(text)
    return unicodedata.normalize("NFC", repaired).casefold()


def _repair_mojibake(value: str) -> str:
    """Repara clásicos ``Empleo_y_economÃ­a`` (UTF-8 leído como latin-1)."""
    try:
        candidate = value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value
    return candidate if candidate != value else value


def resolve_cli_path(raw: str) -> Path:
    """Resuelve un path relativo probando cwd, raíz del repo y carpeta api/."""
    path = Path(str(raw)).expanduser()
    if path.is_absolute():
        return path
    for base in _PATH_BASES:
        candidate = (base / path).resolve()
        if candidate.exists():
            return candidate
    return (Path.cwd() / path).resolve()


def _to_binary(value: Any) -> int | None:
    """Convierte una celda 0/1 (tolerante a ``"1.0"``, ``"true"``, ``"sí"``)."""
    if value is None:
        return None
    text = str(value).strip().casefold()
    if text in {"", "nan", "none", "null"}:
        return 0
    if text in {"1", "1.0", "true", "si", "sí", "s", "yes", "y"}:
        return 1
    if text in {"0", "0.0", "false", "no", "n"}:
        return 0
    try:
        return 1 if float(text) >= 0.5 else 0
    except (TypeError, ValueError):
        return None


def clean_sentiment(value: Any) -> str | None:
    text = unicodedata.normalize("NFC", str(value or "").strip()).casefold()
    return SENTIMENT_ALIASES.get(text)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def round4(value: float) -> float:
    return round(float(value), 4)


# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------
def build_frame_column_map(fieldnames: Iterable[str]) -> dict[str, str]:
    """Mapea ``frame_id`` -> nombre real de la columna en el CSV."""
    known: dict[str, str] = {}
    for frame_id, meta in FRAMES.items():
        for token in (frame_id, meta["model_label"], meta["label"]):
            known[normalize_header(token)] = frame_id

    mapping: dict[str, str] = {}
    for column in fieldnames:
        frame_id = known.get(normalize_header(column))
        if frame_id is not None:
            mapping.setdefault(frame_id, column)

    missing = [frame_id for frame_id in FRAME_IDS if frame_id not in mapping]
    if missing:
        raise SystemExit(
            "El CSV no contiene columnas para estos encuadres: "
            + ", ".join(missing)
            + "\nColumnas encontradas: "
            + ", ".join(str(name) for name in fieldnames)
        )
    return mapping


def pick_column(fieldnames: Iterable[str], candidates: Iterable[str]) -> str | None:
    normalized = {normalize_header(name): name for name in fieldnames}
    for candidate in candidates:
        column = normalized.get(normalize_header(candidate))
        if column is not None:
            return column
    return None


def load_corpus(csv_path: Path) -> list[dict[str, Any]]:
    """Lee el CSV etiquetado y devuelve filas listas para evaluar (texto crudo)."""
    if not csv_path.exists():
        raise SystemExit(f"No existe el CSV: {csv_path}")

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        if not fieldnames:
            raise SystemExit(f"El CSV no tiene cabecera: {csv_path}")

        frame_columns = build_frame_column_map(fieldnames)
        text_column = pick_column(fieldnames, TEXT_COLUMN_CANDIDATES)
        sentiment_column = pick_column(fieldnames, SENTIMENT_COLUMN_CANDIDATES)
        if text_column is None or sentiment_column is None:
            raise SystemExit(
                "No se encontraron las columnas de texto y/o sentimiento. "
                f"Columnas: {', '.join(fieldnames)}"
            )

        rows: list[dict[str, Any]] = []
        skipped = 0
        for record in reader:
            text = (record.get(text_column) or "").strip()
            sentiment = clean_sentiment(record.get(sentiment_column))
            frames: dict[str, int] = {}
            for frame_id, column in frame_columns.items():
                value = _to_binary(record.get(column))
                if value is None:
                    frames = {}
                    break
                frames[frame_id] = value
            if not text or sentiment is None or not frames:
                skipped += 1
                continue
            rows.append(
                {
                    "id": str(record.get("ID") or record.get("id") or len(rows)),
                    "text": text,
                    "sentiment": sentiment,
                    "frames": frames,
                }
            )

    if not rows:
        raise SystemExit(f"No quedaron filas válidas en {csv_path}")
    rows.sort(key=lambda row: row["id"])
    if skipped:
        print(f"[corpus] {skipped} fila(s) descartada(s) por datos incompletos.")
    return rows


def stratified_sample(
    rows: list[dict[str, Any]],
    sample_size: int,
    random_state: int = DEFAULT_RANDOM_STATE,
) -> list[dict[str, Any]]:
    """Muestra estratificada por sentimiento con asignación proporcional determinista."""
    groups: dict[str, list[dict[str, Any]]] = {label: [] for label in SENTIMENT_LABELS}
    for row in rows:
        groups[row["sentiment"]].append(row)

    total = len(rows)
    if sample_size >= total:
        return list(rows)

    expected = {
        label: sample_size * len(group) / total for label, group in groups.items()
    }
    counts = {label: int(math.floor(value)) for label, value in expected.items()}
    remainder = sample_size - sum(counts.values())
    order = sorted(
        groups,
        key=lambda label: (-(expected[label] - counts[label]), -len(groups[label])),
    )
    for label in order:
        if remainder <= 0:
            break
        if counts[label] < len(groups[label]):
            counts[label] += 1
            remainder -= 1

    # Garantiza representación de cada clase no vacía cuando hay presupuesto.
    non_empty = sum(1 for group in groups.values() if group)
    for label, group in groups.items():
        if group and counts[label] == 0 and sample_size >= non_empty:
            donor = max(
                (lab for lab in groups if counts[lab] > 1),
                key=lambda lab: counts[lab],
                default=None,
            )
            if donor is not None:
                counts[donor] -= 1
                counts[label] = 1

    rng = random.Random(random_state)
    sample: list[dict[str, Any]] = []
    for label in SENTIMENT_LABELS:
        group = groups[label]
        if not group:
            continue
        take = min(counts[label], len(group))
        sample.extend(group if take >= len(group) else rng.sample(group, take))
    sample.sort(key=lambda row: row["id"])
    return sample


# ---------------------------------------------------------------------------
# Métricas (sin sklearn para que el script solo dependa de torch/transformers)
# ---------------------------------------------------------------------------
def precision_recall_f1(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def sentiment_metrics(
    rows: list[dict[str, Any]], predictions: list[Any]
) -> tuple[dict[str, Any], list[list[int]]]:
    """Accuracy, macro-F1, P/R/F1 por clase y matriz de confusión 3x3."""
    y_true = [row["sentiment"] for row in rows]
    y_pred = [
        max(prediction.sentiment.items(), key=lambda item: item[1])[0]
        for prediction in predictions
    ]

    n_labels = len(SENTIMENT_LABELS)
    matrix = [[0] * n_labels for _ in range(n_labels)]
    for truth, predicted in zip(y_true, y_pred):
        matrix[SENTIMENT_LABELS.index(truth)][SENTIMENT_LABELS.index(predicted)] += 1

    samples = len(rows)
    per_class: dict[str, dict[str, float | int]] = {}
    f1_scores: list[float] = []
    precision_scores: list[float] = []
    recall_scores: list[float] = []
    for index, label in enumerate(SENTIMENT_LABELS):
        tp = matrix[index][index]
        fp = sum(matrix[row_index][index] for row_index in range(n_labels) if row_index != index)
        fn = sum(matrix[index][column] for column in range(n_labels) if column != index)
        precision, recall, f1 = precision_recall_f1(tp, fp, fn)
        per_class[label] = {
            "precision": round4(precision),
            "recall": round4(recall),
            "f1": round4(f1),
            "support": sum(matrix[index]),
        }
        precision_scores.append(precision)
        recall_scores.append(recall)
        f1_scores.append(f1)

    accuracy = sum(matrix[i][i] for i in range(n_labels)) / samples if samples else 0.0
    result = {
        "accuracy": round4(accuracy),
        "macroF1": round4(sum(f1_scores) / n_labels),
        "macroPrecision": round4(sum(precision_scores) / n_labels),
        "macroRecall": round4(sum(recall_scores) / n_labels),
        "perClass": per_class,
        "confusionMatrix": {
            "labels": list(SENTIMENT_LABELS),
            "matrix": matrix,
        },
        "samples": samples,
    }
    return result, matrix


def _prf_at_threshold(
    y_true: list[int], y_score: list[float], threshold: float
) -> tuple[float, float, float, int]:
    tp = fp = fn = 0
    for truth, score in zip(y_true, y_score):
        predicted = 1 if score >= threshold else 0
        if predicted and truth:
            tp += 1
        elif predicted and not truth:
            fp += 1
        elif not predicted and truth:
            fn += 1
    precision, recall, f1 = precision_recall_f1(tp, fp, fn)
    return precision, recall, f1, sum(y_true)


def frame_metrics(
    rows: list[dict[str, Any]], predictions: list[Any]
) -> tuple[
    list[dict[str, Any]], dict[str, float], dict[str, float], dict[str, dict[str, Any]]
]:
    """P/R/F1 por encuadre en el umbral de operación elegido y a 0.5.

    Política del umbral de operación (grid 0.20-0.95, paso 0.05):

    1. Se maximiza F1 *sujeto a* ``precisión >= 0.50`` y ``recall >= 0.20``.
    2. Si ningún umbral cumple ambas restricciones, se prioriza la precisión:
       se elige el umbral con mayor precisión (desempate por mayor F1) y el
       frame se documenta como "sin punto de operación con precisión>=0.5; se
       prioriza precisión".
    3. Si ni siquiera se alcanza precisión 0.50 en el grid, el umbral queda en
       0.50 por defecto (también documentado).

    Devuelve ``(filas por frame, umbrales, métricas macro a 0.5, información de
    fallback por frame)``.
    """
    y_true = {frame_id: [row["frames"][frame_id] for row in rows] for frame_id in FRAME_IDS}
    y_score = {
        frame_id: [float(prediction.frames[frame_id]) for prediction in predictions]
        for frame_id in FRAME_IDS
    }

    frame_rows: list[dict[str, Any]] = []
    thresholds: dict[str, float] = {}
    macro_at_05: list[tuple[float, float, float]] = []
    fallback_info: dict[str, dict[str, Any]] = {}

    for frame_id in FRAME_IDS:
        truth = y_true[frame_id]
        scores = y_score[frame_id]
        support = sum(truth)

        candidates: list[tuple[float, float, float, float]] = []
        for threshold in THRESHOLD_GRID:
            precision, recall, f1, _ = _prf_at_threshold(truth, scores, threshold)
            candidates.append((threshold, precision, recall, f1))

        def f1_key(
            candidate: tuple[float, float, float, float],
        ) -> tuple[float, float, float]:
            # Mayor F1; a igualdad, umbral más cercano a 0.50 y luego más bajo.
            return (
                round(candidate[3], 9),
                -abs(candidate[0] - 0.5),
                -candidate[0],
            )

        def precision_key(
            candidate: tuple[float, float, float, float],
        ) -> tuple[float, float, float, float]:
            # Mayor precisión; a igualdad, mayor F1 y umbral más cercano a 0.50.
            return (
                round(candidate[1], 9),
                round(candidate[3], 9),
                -abs(candidate[0] - 0.5),
                -candidate[0],
            )

        compliant = [
            candidate
            for candidate in candidates
            if candidate[1] + 1e-12 >= MIN_PRECISION_AT_OPERATING_POINT
            and candidate[2] + 1e-12 >= MIN_RECALL_AT_OPERATING_POINT
        ]
        if compliant:
            best = max(compliant, key=f1_key)
            fallback_reason: str | None = None
        else:
            precision_ok = [
                candidate
                for candidate in candidates
                if candidate[1] + 1e-12 >= MIN_PRECISION_AT_OPERATING_POINT
            ]
            if precision_ok:
                # No hay punto de operación que cumpla recall, pero sí precisión:
                # se prioriza la precisión para no marcar casi todo como activo.
                best = max(precision_ok, key=precision_key)
                fallback_reason = FALLBACK_PRIORITY_PRECISION
            else:
                # Ni la precisión 0.50 se alcanza en el grid: umbral por defecto.
                best = next(
                    candidate for candidate in candidates if abs(candidate[0] - 0.5) < 1e-9
                )
                fallback_reason = FALLBACK_DEFAULT_05

        best_threshold, precision, recall, f1 = best
        if fallback_reason is not None:
            best_precision_choice = max(candidates, key=precision_key)
            fallback_info[frame_id] = {
                "reason": fallback_reason,
                "threshold": best_threshold,
                "precision": round4(precision),
                "recall": round4(recall),
                "f1": round4(f1),
                "maxPrecisionInGrid": round4(best_precision_choice[1]),
                "thresholdAtMaxPrecision": best_precision_choice[0],
                "recallAtMaxPrecision": round4(best_precision_choice[2]),
            }

        precision_05, recall_05, f1_05, _ = _prf_at_threshold(truth, scores, 0.5)
        macro_at_05.append((precision_05, recall_05, f1_05))

        thresholds[frame_id] = best_threshold
        frame_rows.append(
            {
                "frame": FRAMES[frame_id]["label"],
                "frameId": frame_id,
                "precision": round4(precision),
                "recall": round4(recall),
                "f1": round4(f1),
                "support": support,
                "threshold": best_threshold,
                # Información para stdout (no forma parte del contrato):
                # None = punto de operación válido; si no, motivo del fallback.
                "fallbackReason": fallback_reason,
                "maxPrecisionInGrid": (
                    round4(fallback_info[frame_id]["maxPrecisionInGrid"])
                    if frame_id in fallback_info
                    else None
                ),
                # Métricas de referencia al umbral por defecto (stdout).
                "precisionAt05": round4(precision_05),
                "recallAt05": round4(recall_05),
                "f1At05": round4(f1_05),
            }
        )

    n_frames = len(FRAME_IDS)
    macro = {
        "precision": sum(item[0] for item in macro_at_05) / n_frames,
        "recall": sum(item[1] for item in macro_at_05) / n_frames,
        "f1": sum(item[2] for item in macro_at_05) / n_frames,
    }
    return frame_rows, thresholds, macro, fallback_info


def frames_exact_match_accuracy(
    rows: list[dict[str, Any]], predictions: list[Any], threshold: float = 0.5
) -> float:
    """Fracción de artículos cuyo vector binario de 7 encuadres coincide exacto."""
    hits = 0
    for row, prediction in zip(rows, predictions):
        if all(
            int(prediction.frames[frame_id] >= threshold) == row["frames"][frame_id]
            for frame_id in FRAME_IDS
        ):
            hits += 1
    return hits / len(rows) if rows else 0.0


# ---------------------------------------------------------------------------
# Ejecución
# ---------------------------------------------------------------------------
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evalúa los modelos BETO reales (sentimiento + 7 encuadres) sobre el "
            "corpus etiquetado y escribe evaluation.json + thresholds.json."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--csv",
        default=DEFAULT_CSV,
        help="CSV etiquetado (texto crudo en la columna Cuerpo).",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=DEFAULT_SAMPLE_SIZE,
        help="Tamaño de la muestra estratificada por sentimiento.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Tamaño de lote para predict_batch.",
    )
    parser.add_argument(
        "--sentiment-model-dir",
        default=os.environ.get("NLP_SENTIMENT_MODEL_DIR") or str(DEFAULT_SENTIMENT_DIR),
        help="Carpeta del modelo de sentimiento (save_pretrained).",
    )
    parser.add_argument(
        "--frames-model-dir",
        default=os.environ.get("NLP_FRAMES_MODEL_DIR") or str(DEFAULT_FRAMES_DIR),
        help="Carpeta del modelo de encuadres (save_pretrained).",
    )
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Ruta de evaluation.json.")
    parser.add_argument(
        "--thresholds-output",
        default=DEFAULT_THRESHOLDS_OUTPUT,
        help="Ruta de thresholds.json.",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=DEFAULT_RANDOM_STATE,
        help="Semilla de la muestra estratificada.",
    )
    parser.add_argument(
        "--device",
        default="auto",
        help="Dispositivo de inferencia: auto, cpu o cuda.",
    )
    parser.add_argument(
        "--max-length",
        type=int,
        default=DEFAULT_MAX_LENGTH,
        help="Longitud máxima de tokens del tokenizador BERT.",
    )
    args = parser.parse_args(argv)
    if args.sample_size < 1:
        parser.error("--sample-size debe ser >= 1")
    if args.batch_size < 1:
        parser.error("--batch-size debe ser >= 1")
    return args


def load_engine(args: argparse.Namespace) -> BertPairEngine:
    sentiment_dir = resolve_cli_path(args.sentiment_model_dir)
    frames_dir = resolve_cli_path(args.frames_model_dir)

    missing: list[str] = []
    if not model_dir_ready(sentiment_dir):
        missing.append(f"sentimiento: {sentiment_dir}")
    if not model_dir_ready(frames_dir):
        missing.append(f"encuadres: {frames_dir}")
    if missing:
        raise SystemExit(
            "No se encuentran los pesos BETO (se esperan model.safetensors/"
            "pytorch_model.bin + tokenizer.json/vocab.txt).\n  - "
            + "\n  - ".join(missing)
            + "\nUsa --sentiment-model-dir/--frames-model-dir o las variables "
            "NLP_SENTIMENT_MODEL_DIR/NLP_FRAMES_MODEL_DIR."
        )

    started = time.perf_counter()
    try:
        engine = BertPairEngine(
            sentiment_model_dir=sentiment_dir,
            frames_model_dir=frames_dir,
            device=args.device,
            max_length=args.max_length,
        )
    except EngineUnavailable as exc:
        raise SystemExit(f"No se pudo cargar el motor BETO: {exc}") from exc
    engine.load_seconds = time.perf_counter() - started  # atributo informativo
    return engine


def predict_with_latency(
    engine: BertPairEngine, texts: list[str], batch_size: int
) -> tuple[list[Any], list[float]]:
    """Predice por lotes con ``predict_batch`` y mide latencia por artículo (ms)."""
    predictions: list[Any] = []
    latencies_ms: list[float] = []
    for start in range(0, len(texts), batch_size):
        chunk = texts[start : start + batch_size]
        started = time.perf_counter()
        chunk_predictions = engine.predict_batch(chunk, batch_size=len(chunk))
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        per_article = elapsed_ms / len(chunk)
        latencies_ms.extend([per_article] * len(chunk))
        predictions.extend(chunk_predictions)
    return predictions, latencies_ms


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


def build_evaluation(
    rows: list[dict[str, Any]],
    sentiment: dict[str, Any],
    matrix: list[list[int]],
    frame_rows: list[dict[str, Any]],
    thresholds: dict[str, float],
    frames_macro_05: dict[str, float],
    frames_accuracy_05: float,
    latency_ms: list[float],
    fallback_info: dict[str, dict[str, Any]],
    total_corpus: int,
    device: str = "cpu",
) -> ModelEvaluation:
    sample_size = len(rows)
    mean_latency = sum(latency_ms) / len(latency_ms) if latency_ms else 0.0

    sentiment_metric = ModelMetric(
        model_name=MODEL_DISPLAY_NAME,
        architecture=(
            "BERT base español (BETO) afinado · clasificador de 3 clases de sentimiento"
        ),
        role="sentiment",
        accuracy=sentiment["accuracy"],
        precision=sentiment["macroPrecision"],
        recall=sentiment["macroRecall"],
        f1_score=sentiment["macroF1"],
        samples=sample_size,
        is_best=True,
    )
    frames_metric = ModelMetric(
        model_name=MODEL_DISPLAY_NAME,
        architecture=(
            "BERT base español (BETO) afinado · 7 salidas multi-etiqueta (sigmoide)"
        ),
        role="frames",
        accuracy=round4(frames_accuracy_05),
        precision=round4(frames_macro_05["precision"]),
        recall=round4(frames_macro_05["recall"]),
        f1_score=round4(frames_macro_05["f1"]),
        samples=sample_size,
        is_best=False,
    )

    scope = (
        f"los {sample_size} artículos del corpus etiquetado completo"
        if sample_size == total_corpus
        else (
            f"una muestra de {sample_size} de {total_corpus} artículos del "
            "corpus etiquetado"
        )
    )
    fallback_note = ""
    if fallback_info:
        docs: list[str] = []
        for frame_id, info in fallback_info.items():
            label = FRAMES[frame_id]["label"]
            if info["reason"] == FALLBACK_DEFAULT_05:
                docs.append(
                    f"{label}: sin punto de operación con precisión>=0.5; se prioriza "
                    "precisión, pero la precisión máxima del grid es "
                    f"{info['maxPrecisionInGrid']:.2f} < 0.50, así que el umbral queda "
                    f"en {info['threshold']:.2f} por defecto (P {info['precision']:.2f}, "
                    f"R {info['recall']:.2f}, F1 {info['f1']:.2f})"
                )
            else:
                docs.append(
                    f"{label}: sin punto de operación con precisión>=0.5; se prioriza "
                    f"precisión (umbral {info['threshold']:.2f}, P {info['precision']:.2f}, "
                    f"R {info['recall']:.2f}, F1 {info['f1']:.2f})"
                )
        fallback_note = " Fallbacks documentados: " + "; ".join(docs) + "."
    message = (
        f"Evaluación real sobre {scope} con texto crudo (columna Cuerpo) usando el "
        f"motor de producción BertPairEngine en {device.upper()} (latencia media "
        f"{mean_latency:.0f} ms/artículo). Al no disponerse del split de entrenamiento "
        "del modelo, las métricas pueden estar influidas por solapamiento con los "
        "datos de entrenamiento: no son una estimación limpia fuera de muestra. "
        f"Sentimiento: accuracy {sentiment['accuracy']:.3f}, macro-F1 "
        f"{sentiment['macroF1']:.3f}. Encuadres: política de umbral en el grid "
        "0.20-0.95 (persistido en thresholds.json): se maximiza F1 sujeto a "
        "precisión>=0.50 y recall>=0.20; si ningún umbral cumple ambas se prioriza "
        "la precisión (mayor precisión, desempate por mayor F1) y si ni así se "
        "alcanza precisión 0.50 el umbral queda en 0.50 por defecto. Las métricas "
        f"macro a umbral 0.50 aparecen en models[].{fallback_note}"
    )

    evaluation = ModelEvaluation(
        generated_at=datetime.now(timezone.utc),
        sample_size=sample_size,
        engine="bert_pair",
        models=[sentiment_metric, frames_metric],
        sentiment=sentiment,
        frames=[
            FrameEvaluation(
                frame=item["frame"],
                frame_id=item["frameId"],
                precision=item["precision"],
                recall=item["recall"],
                f1=item["f1"],
                support=item["support"],
                threshold=item["threshold"],
            )
            for item in frame_rows
        ],
        confusion_matrix=ConfusionMatrix(
            labels=list(SENTIMENT_LABELS), matrix=matrix
        ),
        thresholds=dict(thresholds),
        available=True,
        message=message,
    )
    # ``frames[]`` solo persiste los campos del contrato; las banderas
    # internas (hasOperatingPoint, métricas @0.50) se usan en stdout y en el
    # message, no viajan al JSON.
    return evaluation


def print_summary(
    sample: list[dict[str, Any]],
    sentiment: dict[str, Any],
    matrix: list[list[int]],
    frame_rows: list[dict[str, Any]],
    thresholds: dict[str, float],
    latency_ms: list[float],
    load_seconds: float,
    evaluation_path: Path,
    thresholds_path: Path,
    total_corpus: int,
    fallback_info: dict[str, dict[str, Any]],
) -> None:
    distribution = defaultdict(int)
    for row in sample:
        distribution[row["sentiment"]] += 1

    print("=" * 78)
    print("EVALUACIÓN REAL BETO - migración venezolana (texto crudo)")
    print("=" * 78)
    print(f"Corpus etiquetado : {total_corpus} filas")
    print(f"Muestra evaluada  : {len(sample)} filas (estratificada por sentimiento)")
    print(
        "Distribución      : "
        + ", ".join(f"{label}={distribution.get(label, 0)}" for label in SENTIMENT_LABELS)
    )
    print(f"Tiempo de carga   : {load_seconds:.1f} s")
    if latency_ms:
        print(
            "Latencia art.     : "
            f"media={sum(latency_ms) / len(latency_ms):.0f} ms, "
            f"p50={percentile(latency_ms, 0.50):.0f} ms, "
            f"p95={percentile(latency_ms, 0.95):.0f} ms"
        )

    print("-" * 78)
    print("SENTIMIENTO (3 clases)")
    print(
        f"accuracy={sentiment['accuracy']:.4f}  macro-F1={sentiment['macroF1']:.4f}  "
        f"macro-P={sentiment['macroPrecision']:.4f}  macro-R={sentiment['macroRecall']:.4f}"
    )
    print(f"{'clase':<12}{'precision':>10}{'recall':>10}{'f1':>10}{'support':>10}")
    for label in SENTIMENT_LABELS:
        metrics = sentiment["perClass"][label]
        print(
            f"{label:<12}{metrics['precision']:>10.3f}{metrics['recall']:>10.3f}"
            f"{metrics['f1']:>10.3f}{metrics['support']:>10d}"
        )
    print("Matriz de confusión (filas=real, columnas=predicho):")
    print(f"{'':<12}" + "".join(f"{label:>12}" for label in SENTIMENT_LABELS))
    for index, label in enumerate(SENTIMENT_LABELS):
        print(f"{label:<12}" + "".join(f"{value:>12d}" for value in matrix[index]))

    print("-" * 78)
    print(
        "ENCUADRES (7 salidas sigmoide; grid 0.20-0.95; política: max F1 con "
        "precisión>=0.50 y recall>=0.20; si no, se prioriza precisión)"
    )
    print(
        f"{'frame':<26}{'P@op':>8}{'R@op':>8}{'F1@op':>8}{'F1@0.5':>8}"
        f"{'support':>9}{'umbral':>8}"
    )
    for item in frame_rows:
        marker = "" if item.get("fallbackReason") is None else " *"
        print(
            f"{item['frame']:<26}{item['precision']:>8.3f}{item['recall']:>8.3f}"
            f"{item['f1']:>8.3f}{item['f1At05']:>8.3f}{item['support']:>9d}"
            f"{item['threshold']:>8.2f}{marker}"
        )
    print("Umbrales de operación:", ", ".join(f"{key}={value:.2f}" for key, value in thresholds.items()))
    if fallback_info:
        print("* Fallbacks (frames sin punto de operación con precisión>=0.50 y recall>=0.20):")
        for frame_id, info in fallback_info.items():
            label = FRAMES[frame_id]["label"]
            if info["reason"] == FALLBACK_DEFAULT_05:
                print(
                    f"    - {label}: sin punto de operación con precisión>=0.5; se "
                    f"prioriza precisión, pero ni así se alcanza 0.50 (máx. precisión "
                    f"en grid={info['maxPrecisionInGrid']:.3f} @ umbral "
                    f"{info['thresholdAtMaxPrecision']:.2f}). Umbral por defecto "
                    f"{info['threshold']:.2f} -> P {info['precision']:.3f}, "
                    f"R {info['recall']:.3f}, F1 {info['f1']:.3f}"
                )
            else:
                print(
                    f"    - {label}: sin punto de operación con precisión>=0.5; se "
                    f"prioriza precisión -> umbral {info['threshold']:.2f} -> "
                    f"P {info['precision']:.3f}, R {info['recall']:.3f}, "
                    f"F1 {info['f1']:.3f} (máx. precisión en grid "
                    f"{info['maxPrecisionInGrid']:.3f} @ {info['thresholdAtMaxPrecision']:.2f})"
                )
    else:
        print("Todos los frames tienen punto de operación con precisión>=0.50 y recall>=0.20.")

    print("-" * 78)
    print(f"Artefactos escritos:\n  - {evaluation_path}\n  - {thresholds_path}")
    if sentiment["accuracy"] < 0.70:
        print(
            "ADVERTENCIA: accuracy de sentimiento por debajo de 0.70 (esperado ~0.80 "
            "con texto crudo). Revisa que se esté evaluando Cuerpo sin lematizar."
        )
    print("=" * 78)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    csv_path = resolve_cli_path(args.csv)
    output_path = resolve_cli_path(args.output)
    thresholds_output_path = resolve_cli_path(args.thresholds_output)

    corpus = load_corpus(csv_path)
    sample = stratified_sample(corpus, args.sample_size, args.random_state)
    if args.sample_size > len(corpus):
        print(
            f"[muestra] --sample-size={args.sample_size} > filas del corpus "
            f"({len(corpus)}); se evalúa el corpus completo."
        )

    engine = load_engine(args)
    texts = [row["text"] for row in sample]
    predictions, latency_ms = predict_with_latency(engine, texts, args.batch_size)

    sentiment, matrix = sentiment_metrics(sample, predictions)
    frame_rows, thresholds, frames_macro_05, fallback_info = frame_metrics(
        sample, predictions
    )
    frames_accuracy_05 = frames_exact_match_accuracy(sample, predictions, 0.5)

    evaluation = build_evaluation(
        rows=sample,
        sentiment=sentiment,
        matrix=matrix,
        frame_rows=frame_rows,
        thresholds=thresholds,
        frames_macro_05=frames_macro_05,
        frames_accuracy_05=frames_accuracy_05,
        latency_ms=latency_ms,
        fallback_info=fallback_info,
        total_corpus=len(corpus),
        device=str(engine.device),
    )
    # Se serializa con pydantic (by_alias=True) para garantizar camelCase y que
    # el JSON valide contra ModelEvaluation. Las métricas @0.5 no se persisten
    # por frame (el contrato solo admite P/R/F1 en el umbral de `threshold`);
    # van en models[] y en el resumen por stdout.
    evaluation_payload = evaluation.model_dump(by_alias=True, mode="json")

    write_json(output_path, evaluation_payload)
    write_json(
        thresholds_output_path,
        {frame_id: round(float(thresholds[frame_id]), 2) for frame_id in FRAME_IDS},
    )

    print_summary(
        sample=sample,
        sentiment=sentiment,
        matrix=matrix,
        frame_rows=frame_rows,
        thresholds=thresholds,
        latency_ms=latency_ms,
        load_seconds=float(getattr(engine, "load_seconds", 0.0)),
        evaluation_path=output_path,
        thresholds_path=thresholds_output_path,
        total_corpus=len(corpus),
        fallback_info=fallback_info,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
