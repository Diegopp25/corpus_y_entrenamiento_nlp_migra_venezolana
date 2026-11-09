#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Balanceo + reentrenamiento reproducible de las cabezas BETO del proyecto.

Este script entrena DOS modelos single-task ``BertForSequenceClassification``
(sentimiento de 3 clases y encuadres multi-etiqueta de 7 salidas) partiendo de
los checkpoints BETO que están en producción, y los evalúa con validación
cruzada honesta: en cada fold hay train / validación / test disjuntos, el early
stopping y los umbrales se eligen SOLO con validación y las métricas que se
reportan salen del test de cada fold.

Decisiones importantes (ver ``training/README.md``):

* ``Data/dataset_balanced.csv`` es el corpus de 156 artículos con *oversampling*
  (79/79/79): solo tiene 116 artículos únicos, el resto son copias. Si se usa
  tal cual en CV, el mismo artículo aparece en train y en test (fuga). Aquí se
  deduplica por texto y se usa el corpus único de 156 artículos.
* El baseline son los modelos actuales de Desktop, evaluados en los MISMOS
  folds de test y con el MISMO ``max_len`` que los modelos reentrenados, para
  que la comparación sea manzana con manzana.
* Los modelos base ya vieron este corpus cuando se entrenaron; no podemos
  des-contaminar los pesos iniciales. Esto se documenta como limitación.

Uso típico (desde la raíz del worktree)::

    PYTHONPATH=api python training/train_models.py \
        --folds 5 --epochs 3 --max-len 384 --batch-size 8 --lr 2e-5 \
        --sent-model-dir C:/Users/diego/Desktop/proyecto/modelo_sentimiento \
        --frames-model-dir C:/Users/diego/Desktop/proyecto/modelo_encuadre

Salidas:
* ``training/models/bert-sentiment-retrained/`` (save_pretrained)
* ``training/models/bert-frames-retrained/``
* ``training/artifacts/retraining_evaluation.json``
* ``training/artifacts/thresholds.json`` (ids canónicos)
* ``training/artifacts/cv_folds/fold_*.json`` (predicciones por fold)
"""

from __future__ import annotations

import argparse
import gc
import html
import json
import math
import os
import random
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.utils.class_weight import compute_class_weight
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# --------------------------------------------------------------------------
# Constantes del contrato de etiquetas (deben coincidir con api/app/engine/labels.py)
# --------------------------------------------------------------------------
SENTIMENT_LABELS = ["Negativo", "Neutro", "Positivo"]
SENT2ID = {label: i for i, label in enumerate(SENTIMENT_LABELS)}

# Orden con el que se entrenó el checkpoint de encuadres (7 salidas sigmoide).
FRAME_MODEL_ORDER = [
    "Acceso_a_servicios",
    "Empleo_y_economía",
    "Integración_social",
    "Otros",
    "Politica_migratoria",
    "Seguridad",
    "Transito_migratorio",
]
# frame_id canónico que consume el frontend / thresholds.json
FRAME_CANONICAL = [
    "acceso_servicios",
    "transito_migratorio",
    "seguridad",
    "integracion_social",
    "politica_migratoria",
    "empleo_economia",
    "otros",
]
FRAME_MODEL_TO_CANONICAL = {
    "Acceso_a_servicios": "acceso_servicios",
    "Empleo_y_economía": "empleo_economia",
    "Integración_social": "integracion_social",
    "Otros": "otros",
    "Politica_migratoria": "politica_migratoria",
    "Seguridad": "seguridad",
    "Transito_migratorio": "transito_migratorio",
}
CANONICAL_TO_MODEL = {v: k for k, v in FRAME_MODEL_TO_CANONICAL.items()}
# índice de cada frame_id canónico dentro del vector de logits del checkpoint
CANONICAL_TO_MODEL_INDEX = {
    canonical: FRAME_MODEL_ORDER.index(model_label)
    for canonical, model_label in CANONICAL_TO_MODEL.items()
}

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
DEFAULT_DATA = [
    REPO_DIR / "Data" / "dataset_balanced.csv",
    REPO_DIR / "Data" / "dataset_migracion_venezolana_labeled.csv",
]
DEFAULT_SENT_MODEL = Path(r"C:\Users\diego\Desktop\proyecto\modelo_sentimiento")
DEFAULT_FRAMES_MODEL = Path(r"C:\Users\diego\Desktop\proyecto\modelo_encuadre")
DEFAULT_PRODUCTION_THRESHOLDS = REPO_DIR / "api" / "artifacts" / "thresholds.json"

# Limpieza idéntica en espíritu a api/app/engine/text.py clean_text (HTML+URLs+espacios)
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]+", flags=re.UNICODE
)
_SPACES_RE = re.compile(r"[ \t\r\f\v]+")
_NEWLINES_RE = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    """Limpia HTML/URLs/espacios sin quitar tildes ni mayúsculas (como producción)."""
    text = str(text or "")
    text = html.unescape(text)
    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = _URL_RE.sub(" ", text)
    text = _EMOJI_RE.sub(" ", text)
    text = _SPACES_RE.sub(" ", text)
    text = _NEWLINES_RE.sub("\n\n", text)
    return text.strip()


# --------------------------------------------------------------------------
# Utilidades generales
# --------------------------------------------------------------------------
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def mean_std(values) -> dict:
    """Media y desviación típica muestral (ddof=1) ignorando None."""
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return {"mean": None, "std": None, "n": 0}
    std = float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0
    return {"mean": float(np.mean(vals)), "std": std, "n": len(vals)}


def round_floats(obj, ndigits: int = 6):
    """Redondea recursivamente floats para que el JSON sea legible."""
    if isinstance(obj, float):
        return round(obj, ndigits)
    if isinstance(obj, dict):
        return {k: round_floats(v, ndigits) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [round_floats(v, ndigits) for v in obj]
    if isinstance(obj, np.floating):
        return round(float(obj), ndigits)
    if isinstance(obj, np.integer):
        return int(obj)
    return obj


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(round_floats(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# --------------------------------------------------------------------------
# Argumentos
# --------------------------------------------------------------------------
def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Balanceo (class weights + pos_weight) y reentrenamiento BETO "
        "con validación cruzada honesta.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--data",
        nargs="+",
        default=[str(path) for path in DEFAULT_DATA],
        help="CSV(s) del corpus (se cargan con utf-8-sig y se deduplican).",
    )
    p.add_argument("--text-col", default="Cuerpo")
    p.add_argument("--sent-col", default="sentimiento")

    # modelo base (checkpoints actuales de producción)
    p.add_argument("--sent-model-dir", default=str(DEFAULT_SENT_MODEL))
    p.add_argument("--frames-model-dir", default=str(DEFAULT_FRAMES_MODEL))

    # CV
    p.add_argument("--folds", type=int, default=5)
    p.add_argument("--val-fraction", type=float, default=0.2,
                   help="Fracción (del train+val de cada fold) reservada para validación/early stopping.")
    p.add_argument("--seed", type=int, default=42)

    # entrenamiento
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--max-len", type=int, default=384)
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--eval-batch-size", type=int, default=16)
    p.add_argument("--lr", type=float, default=2e-5)
    p.add_argument("--weight-decay", type=float, default=0.01)
    p.add_argument("--warmup-ratio", type=float, default=0.1)
    p.add_argument("--patience", type=int, default=2,
                   help="Épocas sin mejora de macro-F1 de validación antes de parar.")
    p.add_argument("--max-pos-weight", type=float, default=20.0,
                   help="Tope del pos_weight por encuadre (evita pesos explosivos).")
    p.add_argument("--num-threads", type=int, default=8)
    p.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])

    # umbrales
    p.add_argument("--threshold-min", type=float, default=0.2)
    p.add_argument("--threshold-max", type=float, default=0.8)
    p.add_argument("--threshold-step", type=float, default=0.05)
    p.add_argument("--precision-floor", type=float, default=0.5,
                   help="Piso de precisión al elegir el umbral F1-óptimo en validación.")
    p.add_argument("--production-thresholds", default=str(DEFAULT_PRODUCTION_THRESHOLDS),
                   help="thresholds.json actuales, solo como referencia de baseline.")

    # salida
    p.add_argument("--out-dir", default=str(SCRIPT_DIR / "models"))
    p.add_argument("--artifacts-dir", default=str(SCRIPT_DIR / "artifacts"))
    p.add_argument("--max-rows", type=int, default=0,
                   help="Smoke test: usa como máximo N artículos únicos (0 = todos).")
    p.add_argument("--skip-final", action="store_true",
                   help="No entrenar los modelos finales (solo CV).")
    p.add_argument("--log-file", default="",
                   help="Además de stdout, escribe el log a este archivo.")

    return p.parse_args(argv)


# --------------------------------------------------------------------------
# Carga y balance del corpus
# --------------------------------------------------------------------------
def load_corpus(paths, text_col: str, sent_col: str, max_rows: int = 0):
    """Carga, valida y deduplica el corpus. Devuelve (df, informe)."""
    frames = []
    per_file = {}
    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            raise FileNotFoundError(f"No existe el CSV: {path}")
        df = pd.read_csv(path, encoding="utf-8-sig")
        missing = [
            col
            for col in [text_col, sent_col, *FRAME_MODEL_ORDER]
            if col not in df.columns
        ]
        if missing:
            raise ValueError(f"{path.name}: faltan columnas {missing}")
        df = df.copy()
        df["__source"] = path.stem
        frames.append(df)
        per_file[path.name] = int(len(df))

    df = pd.concat(frames, ignore_index=True, sort=False)
    n_raw = len(df)

    df[text_col] = df[text_col].astype(str).map(clean_text)
    df = df[df[text_col].str.len() > 0].copy()

    sentiment = df[sent_col].astype(str).str.strip().str.capitalize()
    unknown = sorted(set(sentiment.unique()) - set(SENTIMENT_LABELS))
    if unknown:
        raise ValueError(f"Etiquetas de sentimiento desconocidas: {unknown}")
    df["sent_id"] = sentiment.map(SENT2ID).astype(int)

    for col in FRAME_MODEL_ORDER:
        values = pd.to_numeric(df[col], errors="coerce")
        invalid = values.isna() | ~values.isin([0, 1])
        if invalid.any():
            raise ValueError(
                f"La columna de encuadre {col!r} tiene {int(invalid.sum())} valores "
                "que no son 0/1 o nulos."
            )
        df[col] = values.astype(int)

    # Deduplicación por contenido: el mismo texto no puede caer en train y test.
    dup_mask = df.duplicated(subset=[text_col], keep="first")
    n_dups = int(dup_mask.sum())
    conflicts = 0
    if n_dups:
        grouped = df.groupby(text_col, sort=False)
        for _, group in grouped:
            if len(group) > 1:
                same_sent = group["sent_id"].nunique() == 1
                same_frames = group[FRAME_MODEL_ORDER].drop_duplicates().shape[0] == 1
                if not (same_sent and same_frames):
                    conflicts += 1
    df = df[~dup_mask].reset_index(drop=True)

    if max_rows and len(df) > max_rows:
        df = df.sample(n=max_rows, random_state=0).reset_index(drop=True)

    frame_matrix = df[FRAME_MODEL_ORDER].to_numpy(dtype=np.int64)
    info = {
        "archivos": per_file,
        "filas_leidas": n_raw,
        "duplicados_texto_eliminados": n_dups,
        "grupos_duplicados_con_etiquetas_en_conflicto": conflicts,
        "articulos_unicos": int(len(df)),
        "muestra_por_archivo_tras_dedup": df["__source"].value_counts().to_dict(),
        "sentimiento": {
            label: int((df["sent_id"] == idx).sum())
            for idx, label in enumerate(SENTIMENT_LABELS)
        },
        "por_pais": df["Pais"].value_counts().to_dict() if "Pais" in df else {},
        "sentimiento_por_pais": (
            pd.crosstab(df["Pais"], df["sent_id"])
            .rename(columns={i: label for i, label in enumerate(SENTIMENT_LABELS)})
            .to_dict()
            if "Pais" in df
            else {}
        ),
        "encuadres_soporte": {
            canonical: int(frame_matrix[:, CANONICAL_TO_MODEL_INDEX[canonical]].sum())
            for canonical in FRAME_CANONICAL
        },
        "encuadres_porcentaje": {
            canonical: round(
                100.0 * frame_matrix[:, CANONICAL_TO_MODEL_INDEX[canonical]].mean(), 2
            )
            for canonical in FRAME_CANONICAL
        },
        "encuadres_por_articulo": (
            pd.Series(frame_matrix.sum(axis=1)).value_counts().sort_index().to_dict()
        ),
    }
    return df, info


# --------------------------------------------------------------------------
# Splits
# --------------------------------------------------------------------------
def make_splits(df, folds: int, seed: int, val_fraction: float):
    y = df["sent_id"].to_numpy()
    counts = Counter(y.tolist())
    if min(counts.values()) < folds:
        new_folds = max(2, min(folds, min(counts.values())))
        print(
            f"[aviso] la clase minoritaria tiene {min(counts.values())} ejemplos; "
            f"se reduce folds de {folds} a {new_folds}",
            flush=True,
        )
        folds = new_folds
    skf = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    splits = []
    for fold, (train_val_idx, test_idx) in enumerate(
        skf.split(np.zeros(len(y)), y), start=1
    ):
        train_idx, val_idx = train_test_split(
            train_val_idx,
            test_size=val_fraction,
            random_state=seed * 1000 + fold,
            stratify=y[train_val_idx],
        )
        splits.append(
            {
                "fold": fold,
                "train": np.sort(train_idx),
                "val": np.sort(val_idx),
                "test": np.sort(test_idx),
            }
        )
    return splits, folds


# --------------------------------------------------------------------------
# Tokenización / datasets
# --------------------------------------------------------------------------
def encode_texts(texts, tokenizer, max_len: int):
    batch = tokenizer(
        list(texts),
        truncation=True,
        max_length=max_len,
        padding=False,
        return_attention_mask=True,
    )
    return [
        {"input_ids": ids, "attention_mask": mask}
        for ids, mask in zip(batch["input_ids"], batch["attention_mask"])
    ]


class ListDataset(Dataset):
    def __init__(self, encodings, labels):
        self.encodings = encodings
        self.labels = labels

    def __len__(self):
        return len(self.encodings)

    def __getitem__(self, idx):
        item = dict(self.encodings[idx])
        item["label"] = self.labels[idx]
        return item


def make_collate(pad_token_id: int):
    def collate(batch):
        max_len = max(len(item["input_ids"]) for item in batch)
        input_ids = torch.full(
            (len(batch), max_len), pad_token_id, dtype=torch.long
        )
        attention = torch.zeros((len(batch), max_len), dtype=torch.long)
        for row, item in enumerate(batch):
            length = len(item["input_ids"])
            input_ids[row, :length] = torch.tensor(item["input_ids"], dtype=torch.long)
            attention[row, :length] = torch.tensor(
                item["attention_mask"], dtype=torch.long
            )
        labels = np.array([item["label"] for item in batch])
        return {
            "input_ids": input_ids,
            "attention_mask": attention,
            "labels": torch.tensor(labels),
        }

    return collate


def build_loader(encodings, labels, batch_size, shuffle, pad_token_id, seed=0):
    dataset = ListDataset(encodings, labels)
    generator = torch.Generator()
    generator.manual_seed(seed)
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        collate_fn=make_collate(pad_token_id),
        num_workers=0,
        generator=generator if shuffle else None,
    )


# --------------------------------------------------------------------------
# Predicción / métricas
# --------------------------------------------------------------------------
@torch.inference_mode()
def predict_probs(model, loader, device, kind: str) -> np.ndarray:
    """kind: 'sentiment' (softmax) o 'frames' (sigmoid). Orden estable."""
    model.eval()
    outputs = []
    for batch in loader:
        logits = model(
            input_ids=batch["input_ids"].to(device),
            attention_mask=batch["attention_mask"].to(device),
        ).logits.float()
        if kind == "sentiment":
            probs = torch.softmax(logits, dim=-1)
        else:
            probs = torch.sigmoid(logits)
        outputs.append(probs.cpu().numpy())
    return np.concatenate(outputs, axis=0)


def sentiment_report(y_true, probs) -> dict:
    pred = np.argmax(probs, axis=-1)
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, pred, labels=[0, 1, 2], zero_division=0
    )
    per_class = {
        label: {
            "precision": float(precision[i]),
            "recall": float(recall[i]),
            "f1": float(f1[i]),
            "support": int(support[i]),
        }
        for i, label in enumerate(SENTIMENT_LABELS)
    }
    matrix = confusion_matrix(y_true, pred, labels=[0, 1, 2])
    return {
        "accuracy": float(accuracy_score(y_true, pred)),
        "macro_f1": float(f1_score(y_true, pred, average="macro", zero_division=0)),
        "macro_precision": float(np.mean(precision)),
        "macro_recall": float(np.mean(recall)),
        "per_class": per_class,
        "confusion_matrix": {
            "labels": SENTIMENT_LABELS,
            "matrix": matrix.tolist(),
        },
        "support": int(len(y_true)),
    }


def frame_threshold_grid(args) -> list:
    n = int(round((args.threshold_max - args.threshold_min) / args.threshold_step)) + 1
    return [round(args.threshold_min + i * args.threshold_step, 2) for i in range(n)]


def select_thresholds(y_true, probs, grid, precision_floor, keys=FRAME_CANONICAL):
    """Elige un umbral por encuadre SOLO con los datos pasados (validación).

    Criterio: entre los umbrales del grid que alcanzan precisión >= piso, el de
    mayor F1 (desempate por mayor precisión y luego mayor umbral). Si ninguno
    alcanza el piso, se deja 0.5 y se marca fallback (sin punto de operación).
    """
    thresholds, meta = {}, {}
    for key in keys:
        j = CANONICAL_TO_MODEL_INDEX[key]
        y = y_true[:, j].astype(int)
        p = probs[:, j]
        positives = int(y.sum())
        if positives == 0:
            thresholds[key] = 0.5
            meta[key] = {
                "threshold": 0.5,
                "fallback": True,
                "reason": "sin_positivos_en_validacion",
                "support": 0,
            }
            continue
        best = None
        best_any = None
        for t in grid:
            pred = p >= t
            tp = int(np.logical_and(pred, y == 1).sum())
            n_pred = int(pred.sum())
            prec = tp / n_pred if n_pred else 0.0
            rec = tp / positives
            f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
            candidate = (f1, prec, t)
            if best_any is None or candidate > best_any:
                best_any = candidate
            if prec >= precision_floor and (best is None or candidate > best):
                best = candidate
        if best is None:
            _, prec_max, t_max = best_any
            thresholds[key] = 0.5
            meta[key] = {
                "threshold": 0.5,
                "fallback": True,
                "reason": "ningun_umbral_alcanza_piso_precision",
                "precision_floor": precision_floor,
                "max_precision_observada": float(prec_max),
                "threshold_max_precision": float(t_max),
                "support": positives,
            }
        else:
            f1_best, prec_best, t_best = best
            thresholds[key] = float(t_best)
            meta[key] = {
                "threshold": float(t_best),
                "fallback": False,
                "precision_validacion": float(prec_best),
                "f1_validacion": float(f1_best),
                "support": positives,
            }
    return thresholds, meta


def frames_report(y_true, probs, thresholds, keys=FRAME_CANONICAL) -> dict:
    per_label = {}
    precisions, recalls, f1s = [], [], []
    predicted = {}
    for key in keys:
        j = CANONICAL_TO_MODEL_INDEX[key]
        y = y_true[:, j].astype(int)
        pred = (probs[:, j] >= thresholds[key]).astype(int)
        predicted[key] = pred
        tp = int(np.logical_and(pred == 1, y == 1).sum())
        n_pred = int(pred.sum())
        positives = int(y.sum())
        prec = tp / n_pred if n_pred else 0.0
        rec = tp / positives if positives else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        per_label[key] = {
            "precision": float(prec),
            "recall": float(rec),
            "f1": float(f1),
            "support": positives,
            "threshold": float(thresholds[key]),
            "predicted_positives": n_pred,
        }
        precisions.append(prec)
        recalls.append(rec)
        f1s.append(f1)
    return {
        "per_label": per_label,
        "macro_precision": float(np.mean(precisions)),
        "macro_recall": float(np.mean(recalls)),
        "macro_f1": float(np.mean(f1s)),
        "micro_f1": float(
            f1_score(
                y_true[:, [CANONICAL_TO_MODEL_INDEX[key] for key in keys]].astype(int).ravel(),
                np.stack([predicted[key] for key in keys], axis=1).ravel(),
                zero_division=0,
            )
        ),
        "support": int(y_true.shape[0]),
    }


# --------------------------------------------------------------------------
# Entrenamiento
# --------------------------------------------------------------------------
def _binary_metrics_at(probs, y, threshold: float) -> dict:
    pred = probs >= threshold
    tp = int(np.logical_and(pred, y == 1).sum())
    n_pred = int(pred.sum())
    positives = int(y.sum())
    precision = tp / n_pred if n_pred else 0.0
    recall = tp / positives if positives else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return {
        "threshold": float(threshold),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "predicted_positives": n_pred,
        "support": positives,
    }


def guard_thresholds(thresholds, y_true, probs, keys=FRAME_CANONICAL):
    """Salvaguarda contra el sobreajuste de umbrales en validaciones pequeñas.

    El protocolo pide el umbral F1-óptimo sujeto a un piso de precisión. Con 156
    artículos, ese piso puede empujar el umbral a valores altos que suben la
    precisión pero hunden el recall (p. ej. umbral 0.65 con recall 0.05). Por
    eso, si el umbral elegido con el piso tiene peor F1 que el umbral por
    defecto 0.5 **en la misma validación**, se conserva 0.5. Los umbrales
    estrictos se guardan igualmente en un artefacto aparte para trazabilidad.
    """
    guarded, info = {}, {}
    for key in keys:
        index = CANONICAL_TO_MODEL_INDEX[key]
        y = y_true[:, index].astype(int)
        p = probs[:, index]
        at_default = _binary_metrics_at(p, y, 0.5)
        at_floor = _binary_metrics_at(p, y, thresholds[key])
        if thresholds[key] != 0.5 and at_floor["f1"] < at_default["f1"]:
            guarded[key] = 0.5
            info[key] = {
                "threshold_piso_precision": thresholds[key],
                "f1_con_piso": at_floor["f1"],
                "f1_at_0.5": at_default["f1"],
                "decision": "0.5 (el piso de precisión empeora el F1 en validación)",
            }
        else:
            guarded[key] = float(thresholds[key])
            info[key] = {
                "threshold_piso_precision": thresholds[key],
                "f1_con_piso": at_floor["f1"],
                "f1_at_0.5": at_default["f1"],
                "decision": "umbral con piso de precisión",
            }
    return guarded, info


def _make_scheduler(optimizer, total_steps: int, warmup_ratio: float):
    warmup = max(1, int(total_steps * warmup_ratio))

    def lr_lambda(step: int) -> float:
        if step < warmup:
            return step / max(1, warmup)
        return max(0.0, (total_steps - step) / max(1, total_steps - warmup))

    return torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)


def train_sentiment_model(train_enc, y_train, val_enc, y_val, args, device):
    set_seed(args.seed)
    model = AutoModelForSequenceClassification.from_pretrained(
        str(args.sent_model_dir)
    ).to(device)
    model.config.num_labels = len(SENTIMENT_LABELS)
    model.config.id2label = {i: label for i, label in enumerate(SENTIMENT_LABELS)}
    model.config.label2id = {label: i for i, label in enumerate(SENTIMENT_LABELS)}

    train_loader = build_loader(
        train_enc, y_train, args.batch_size, True, 1, seed=args.seed
    )
    val_loader = build_loader(
        val_enc, y_val, args.eval_batch_size, False, 1
    )
    class_weights = compute_class_weight(
        class_weight="balanced", classes=np.arange(len(SENTIMENT_LABELS)), y=y_train
    )
    print(
        f"    [sentimiento] class_weights={np.round(class_weights, 3).tolist()}",
        flush=True,
    )
    criterion = nn.CrossEntropyLoss(
        weight=torch.tensor(class_weights, dtype=torch.float, device=device)
    )
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=args.lr, weight_decay=args.weight_decay
    )
    total_steps = max(1, len(train_loader) * args.epochs)
    scheduler = _make_scheduler(optimizer, total_steps, args.warmup_ratio)

    best_state, best_score, bad_epochs = None, -1.0, 0
    for epoch in range(1, args.epochs + 1):
        started = time.time()
        model.train()
        losses = []
        for batch in train_loader:
            optimizer.zero_grad()
            logits = model(
                input_ids=batch["input_ids"].to(device),
                attention_mask=batch["attention_mask"].to(device),
            ).logits
            loss = criterion(logits, batch["labels"].to(device))
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            losses.append(float(loss.item()))
        val_probs = predict_probs(model, val_loader, device, "sentiment")
        score = float(
            f1_score(y_val, np.argmax(val_probs, axis=1), average="macro", zero_division=0)
        )
        print(
            f"    [sentimiento] época {epoch}/{args.epochs} "
            f"loss={np.mean(losses):.4f} macro_f1_val={score:.4f} "
            f"({time.time() - started:.1f}s)",
            flush=True,
        )
        if score > best_score:
            best_score = score
            best_state = {
                key: value.detach().cpu().clone()
                for key, value in model.state_dict().items()
            }
            bad_epochs = 0
        else:
            bad_epochs += 1
            if bad_epochs >= args.patience:
                print(
                    f"    [sentimiento] early stopping (sin mejora en "
                    f"{args.patience} época/s)",
                    flush=True,
                )
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    return model, best_score


def train_frames_model(train_enc, y_train, val_enc, y_val, args, device):
    set_seed(args.seed)
    model = AutoModelForSequenceClassification.from_pretrained(
        str(args.frames_model_dir)
    ).to(device)
    model.config.num_labels = len(FRAME_MODEL_ORDER)
    model.config.problem_type = "multi_label_classification"
    model.config.id2label = {
        i: label for i, label in enumerate(FRAME_MODEL_ORDER)
    }
    model.config.label2id = {
        label: i for i, label in enumerate(FRAME_MODEL_ORDER)
    }

    train_loader = build_loader(
        train_enc, y_train, args.batch_size, True, 1, seed=args.seed
    )
    val_loader = build_loader(
        val_enc, y_val, args.eval_batch_size, False, 1
    )
    positives = y_train.sum(axis=0).astype(float)
    negatives = y_train.shape[0] - positives
    pos_weight = np.where(
        positives > 0, np.clip(negatives / np.maximum(positives, 1.0), 1.0, args.max_pos_weight), 1.0
    )
    print(
        "    [encuadres] pos_weight="
        + str(
            {
                canonical: round(
                    float(pos_weight[CANONICAL_TO_MODEL_INDEX[canonical]]), 3
                )
                for canonical in FRAME_CANONICAL
            }
        ),
        flush=True,
    )
    criterion = nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor(pos_weight, dtype=torch.float, device=device)
    )
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=args.lr, weight_decay=args.weight_decay
    )
    total_steps = max(1, len(train_loader) * args.epochs)
    scheduler = _make_scheduler(optimizer, total_steps, args.warmup_ratio)

    best_state, best_score, bad_epochs = None, -1.0, 0
    for epoch in range(1, args.epochs + 1):
        started = time.time()
        model.train()
        losses = []
        for batch in train_loader:
            optimizer.zero_grad()
            logits = model(
                input_ids=batch["input_ids"].to(device),
                attention_mask=batch["attention_mask"].to(device),
            ).logits
            loss = criterion(logits, batch["labels"].to(device))
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            losses.append(float(loss.item()))
        val_probs = predict_probs(model, val_loader, device, "frames")
        pred = (val_probs >= 0.5).astype(int)
        score = float(
            f1_score(
                y_val.astype(int).ravel(),
                pred.ravel(),
                average="macro",
                zero_division=0,
            )
        )
        print(
            f"    [encuadres] época {epoch}/{args.epochs} "
            f"loss={np.mean(losses):.4f} macro_f1_val@0.5={score:.4f} "
            f"({time.time() - started:.1f}s)",
            flush=True,
        )
        if score > best_score:
            best_score = score
            best_state = {
                key: value.detach().cpu().clone()
                for key, value in model.state_dict().items()
            }
            bad_epochs = 0
        else:
            bad_epochs += 1
            if bad_epochs >= args.patience:
                print(
                    f"    [encuadres] early stopping (sin mejora en "
                    f"{args.patience} época/s)",
                    flush=True,
                )
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    return model, best_score


# --------------------------------------------------------------------------
# Baseline (modelos actuales de Desktop)
# --------------------------------------------------------------------------
def build_baseline_predictions(df, tokenizers, max_len, args, device):
    """Predice con los modelos actuales sobre todos los artículos (una sola vez)."""
    sent_tokenizer, frames_tokenizer = tokenizers
    texts = df["texto"].tolist()
    sent_enc = encode_texts(texts, sent_tokenizer, max_len)
    frames_enc = encode_texts(texts, frames_tokenizer, max_len)

    print("[baseline] cargando modelos actuales de Desktop...", flush=True)
    sent_model = AutoModelForSequenceClassification.from_pretrained(
        str(args.sent_model_dir)
    ).to(device).eval()
    frames_model = AutoModelForSequenceClassification.from_pretrained(
        str(args.frames_model_dir)
    ).to(device).eval()

    pad_id = int(sent_model.config.pad_token_id or 1)
    sent_loader = build_loader(
        sent_enc, np.zeros(len(texts), dtype=int), args.eval_batch_size, False, pad_id
    )
    frames_loader = build_loader(
        frames_enc,
        np.zeros((len(texts), len(FRAME_MODEL_ORDER)), dtype=float),
        args.eval_batch_size,
        False,
        pad_id,
    )
    sent_probs = predict_probs(sent_model, sent_loader, device, "sentiment")
    frames_probs = predict_probs(frames_model, frames_loader, device, "frames")
    del sent_model, frames_model
    gc.collect()
    if device.type == "cuda":
        torch.cuda.empty_cache()
    return sent_probs, frames_probs


# --------------------------------------------------------------------------
# Evaluación de un fold
# --------------------------------------------------------------------------
def evaluate_fold(
    *,
    fold,
    df,
    idx_train,
    idx_val,
    idx_test,
    sent_tokenizer,
    frames_tokenizer,
    baseline_sent_probs,
    baseline_frames_probs,
    production_thresholds,
    args,
    device,
    grid,
):
    fold_dir = Path(args.artifacts_dir) / "cv_folds"
    fold_dir.mkdir(parents=True, exist_ok=True)
    texts = df["texto"].tolist()
    y_sent = df["sent_id"].to_numpy()
    y_frames = df[FRAME_MODEL_ORDER].to_numpy(dtype=np.int64)

    print(
        f"[fold {fold}] train={len(idx_train)} val={len(idx_val)} test={len(idx_test)}",
        flush=True,
    )
    train_texts = [texts[i] for i in idx_train]
    val_texts = [texts[i] for i in idx_val]
    test_texts = [texts[i] for i in idx_test]

    # --- sentimiento -----------------------------------------------------
    print(f"[fold {fold}] sentimiento: tokenizando y entrenando", flush=True)
    train_enc_s = encode_texts(train_texts, sent_tokenizer, args.max_len)
    val_enc_s = encode_texts(val_texts, sent_tokenizer, args.max_len)
    test_enc_s = encode_texts(test_texts, sent_tokenizer, args.max_len)
    sent_model, sent_val_score = train_sentiment_model(
        train_enc_s,
        y_sent[idx_train],
        val_enc_s,
        y_sent[idx_val],
        args,
        device,
    )
    pad_id = int(sent_model.config.pad_token_id or 1)
    val_loader_s = build_loader(
        val_enc_s, y_sent[idx_val], args.eval_batch_size, False, pad_id
    )
    test_loader_s = build_loader(
        test_enc_s, y_sent[idx_test], args.eval_batch_size, False, pad_id
    )
    sent_val_probs = predict_probs(sent_model, val_loader_s, device, "sentiment")
    sent_test_probs = predict_probs(sent_model, test_loader_s, device, "sentiment")
    sent_val = sentiment_report(y_sent[idx_val], sent_val_probs)
    sent_test = sentiment_report(y_sent[idx_test], sent_test_probs)
    print(
        f"[fold {fold}] sentimiento test: acc={sent_test['accuracy']:.3f} "
        f"macro_f1={sent_test['macro_f1']:.3f}",
        flush=True,
    )
    del sent_model, train_enc_s, val_enc_s, test_enc_s, val_loader_s, test_loader_s
    gc.collect()

    # --- encuadres -------------------------------------------------------
    print(f"[fold {fold}] encuadres: tokenizando y entrenando", flush=True)
    train_enc_f = encode_texts(train_texts, frames_tokenizer, args.max_len)
    val_enc_f = encode_texts(val_texts, frames_tokenizer, args.max_len)
    test_enc_f = encode_texts(test_texts, frames_tokenizer, args.max_len)
    frames_model, frames_val_score = train_frames_model(
        train_enc_f,
        y_frames[idx_train].astype(float),
        val_enc_f,
        y_frames[idx_val].astype(float),
        args,
        device,
    )
    pad_id = int(frames_model.config.pad_token_id or 1)
    val_loader_f = build_loader(
        val_enc_f,
        y_frames[idx_val].astype(float),
        args.eval_batch_size,
        False,
        pad_id,
    )
    test_loader_f = build_loader(
        test_enc_f,
        y_frames[idx_test].astype(float),
        args.eval_batch_size,
        False,
        pad_id,
    )
    frames_val_probs = predict_probs(frames_model, val_loader_f, device, "frames")
    frames_test_probs = predict_probs(frames_model, test_loader_f, device, "frames")

    # umbrales elegidos SOLO en validación del fold
    tuned_thresholds, tuned_meta = select_thresholds(
        y_frames[idx_val].astype(int),
        frames_val_probs,
        grid,
        args.precision_floor,
    )
    defaults = {key: 0.5 for key in FRAME_CANONICAL}
    frames_val_report = frames_report(
        y_frames[idx_val], frames_val_probs, tuned_thresholds
    )
    frames_test_tuned = frames_report(
        y_frames[idx_test], frames_test_probs, tuned_thresholds
    )
    frames_test_at_05 = frames_report(
        y_frames[idx_test], frames_test_probs, defaults
    )
    if production_thresholds:
        prod = {key: production_thresholds.get(key, 0.5) for key in FRAME_CANONICAL}
        frames_test_production = frames_report(
            y_frames[idx_test], frames_test_probs, prod
        )
    else:
        frames_test_production = None
    print(
        f"[fold {fold}] encuadres test: macro_f1@0.5="
        f"{frames_test_at_05['macro_f1']:.3f} macro_f1_umbrales_validacion="
        f"{frames_test_tuned['macro_f1']:.3f}",
        flush=True,
    )
    del frames_model, train_enc_f, val_enc_f, test_enc_f, val_loader_f, test_loader_f
    gc.collect()

    # --- baseline en el MISMO test --------------------------------------
    base_sent_test = sentiment_report(
        y_sent[idx_test], baseline_sent_probs[idx_test]
    )
    base_frames_val_probs = baseline_frames_probs[idx_val]
    base_frames_test_probs = baseline_frames_probs[idx_test]
    base_thresholds, base_meta = select_thresholds(
        y_frames[idx_val].astype(int),
        base_frames_val_probs,
        grid,
        args.precision_floor,
    )
    base_frames_test_at_05 = frames_report(
        y_frames[idx_test], base_frames_test_probs, defaults
    )
    base_frames_test_tuned = frames_report(
        y_frames[idx_test], base_frames_test_probs, base_thresholds
    )
    if production_thresholds:
        prod = {key: production_thresholds.get(key, 0.5) for key in FRAME_CANONICAL}
        base_frames_test_production = frames_report(
            y_frames[idx_test], base_frames_test_probs, prod
        )
    else:
        base_frames_test_production = None

    message = (
        f"[fold {fold}] baseline test: sent_acc={base_sent_test['accuracy']:.3f} "
        f"sent_macro_f1={base_sent_test['macro_f1']:.3f} "
        f"frames_macro_f1@0.5={base_frames_test_at_05['macro_f1']:.3f}"
    )
    print(message, flush=True)

    # --- predicciones a disco -------------------------------------------
    predictions = {
        "fold": fold,
        "n_train": int(len(idx_train)),
        "n_val": int(len(idx_val)),
        "n_test": int(len(idx_test)),
        "ids_test": df["ID"].iloc[idx_test].tolist(),
        "ids_val": df["ID"].iloc[idx_val].tolist(),
        "sentiment": {
            "true_test": y_sent[idx_test].tolist(),
            "test_probs": sent_test_probs.tolist(),
            "true_val": y_sent[idx_val].tolist(),
            "val_probs": sent_val_probs.tolist(),
            "labels": SENTIMENT_LABELS,
        },
        "frames": {
            "model_order": FRAME_MODEL_ORDER,
            "canonical_keys": FRAME_CANONICAL,
            "canonical_to_model_index": CANONICAL_TO_MODEL_INDEX,
            "umbrales_thresholds_json_keys": "canonical",
            "true_test": y_frames[idx_test].tolist(),
            "test_probs": frames_test_probs.tolist(),
            "true_val": y_frames[idx_val].tolist(),
            "val_probs": frames_val_probs.tolist(),
            "thresholds_validation": tuned_thresholds,
        },
        "baseline_frames_thresholds_validation": base_thresholds,
        "reports": {
            "sentiment_val": sent_val,
            "sentiment_test": sent_test,
            "sentiment_test_baseline": base_sent_test,
            "frames_val": frames_val_report,
            "frames_test_at_0.5": frames_test_at_05,
            "frames_test_tuned": frames_test_tuned,
            "frames_test_production_thresholds": frames_test_production,
            "frames_test_baseline_at_0.5": base_frames_test_at_05,
            "frames_test_baseline_tuned": base_frames_test_tuned,
            "frames_test_baseline_production_thresholds": base_frames_test_production,
        },
        "thresholds_validation_meta": tuned_meta,
        "baseline_thresholds_validation_meta": base_meta,
        "early_stopping": {
            "sentiment_best_val_macro_f1": sent_val_score,
            "frames_best_val_macro_f1_at_0.5": frames_val_score,
        },
    }
    write_json(fold_dir / f"fold_{fold}.json", predictions)

    return {
        "fold": fold,
        "n_train": int(len(idx_train)),
        "n_val": int(len(idx_val)),
        "n_test": int(len(idx_test)),
        "sentiment": sent_test,
        "sentiment_baseline": base_sent_test,
        "frames_at_0.5": frames_test_at_05,
        "frames_tuned": frames_test_tuned,
        "frames_baseline_at_0.5": base_frames_test_at_05,
        "frames_baseline_tuned": base_frames_test_tuned,
        "frames_production_thresholds": frames_test_production,
        "frames_baseline_production_thresholds": base_frames_test_production,
        "thresholds_validation": tuned_thresholds,
        "baseline_thresholds_validation": base_thresholds,
        "val_probs": {
            "sentiment": sent_val_probs,
            "frames": frames_val_probs,
        },
        "val_true": {
            "sentiment": y_sent[idx_val],
            "frames": y_frames[idx_val],
        },
        "early_stopping": {
            "sentiment_best_val_macro_f1": sent_val_score,
            "frames_best_val_macro_f1_at_0.5": frames_val_score,
        },
    }


# --------------------------------------------------------------------------
# Agregación de resultados
# --------------------------------------------------------------------------
def aggregate_cv(fold_results, grid, precision_floor, args):
    sent_acc = [r["sentiment"]["accuracy"] for r in fold_results]
    sent_f1 = [r["sentiment"]["macro_f1"] for r in fold_results]
    base_acc = [r["sentiment_baseline"]["accuracy"] for r in fold_results]
    base_f1 = [r["sentiment_baseline"]["macro_f1"] for r in fold_results]

    per_class = {}
    per_class_baseline = {}
    for label in SENTIMENT_LABELS:
        per_class[label] = {
            metric: mean_std([r["sentiment"]["per_class"][label][metric] for r in fold_results])
            for metric in ("precision", "recall", "f1")
        }
        per_class_baseline[label] = {
            metric: mean_std(
                [r["sentiment_baseline"]["per_class"][label][metric] for r in fold_results]
            )
            for metric in ("precision", "recall", "f1")
        }

    confusion = np.sum(
        [np.array(r["sentiment"]["confusion_matrix"]["matrix"]) for r in fold_results],
        axis=0,
    ).tolist()
    confusion_base = np.sum(
        [
            np.array(r["sentiment_baseline"]["confusion_matrix"]["matrix"])
            for r in fold_results
        ],
        axis=0,
    ).tolist()

    frames = {}
    frames_baseline = {}
    for key in FRAME_CANONICAL:
        retrained = [r["frames_tuned"]["per_label"][key] for r in fold_results]
        at05 = [r["frames_at_0.5"]["per_label"][key] for r in fold_results]
        baseline_tuned = [
            r["frames_baseline_tuned"]["per_label"][key] for r in fold_results
        ]
        baseline_at05 = [
            r["frames_baseline_at_0.5"]["per_label"][key] for r in fold_results
        ]
        thresholds_used = [r["thresholds_validation"][key] for r in fold_results]
        frames[key] = {
            "support_mean": mean_std([x["support"] for x in at05]),
            "at_0.5": {
                "precision": mean_std([x["precision"] for x in at05]),
                "recall": mean_std([x["recall"] for x in at05]),
                "f1": mean_std([x["f1"] for x in at05]),
            },
            "tuned": {
                "precision": mean_std([x["precision"] for x in retrained]),
                "recall": mean_std([x["recall"] for x in retrained]),
                "f1": mean_std([x["f1"] for x in retrained]),
            },
            "threshold_fold": mean_std(thresholds_used),
            "threshold_values": thresholds_used,
        }
        frames_baseline[key] = {
            "support_mean": mean_std([x["support"] for x in baseline_at05]),
            "at_0.5": {
                "precision": mean_std([x["precision"] for x in baseline_at05]),
                "recall": mean_std([x["recall"] for x in baseline_at05]),
                "f1": mean_std([x["f1"] for x in baseline_at05]),
            },
            "tuned": {
                "precision": mean_std([x["precision"] for x in baseline_tuned]),
                "recall": mean_std([x["recall"] for x in baseline_tuned]),
                "f1": mean_std([x["f1"] for x in baseline_tuned]),
            },
            "threshold_fold": mean_std(
                [r["baseline_thresholds_validation"][key] for r in fold_results]
            ),
        }

    frames_macro = {
        "at_0.5": {
            metric: mean_std([r["frames_at_0.5"][f"macro_{metric}"] for r in fold_results])
            for metric in ("precision", "recall", "f1")
        },
        "tuned": {
            metric: mean_std([r["frames_tuned"][f"macro_{metric}"] for r in fold_results])
            for metric in ("precision", "recall", "f1")
        },
    }
    frames_macro_baseline = {
        "at_0.5": {
            metric: mean_std(
                [r["frames_baseline_at_0.5"][f"macro_{metric}"] for r in fold_results]
            )
            for metric in ("precision", "recall", "f1")
        },
        "tuned": {
            metric: mean_std(
                [r["frames_baseline_tuned"][f"macro_{metric}"] for r in fold_results]
            )
            for metric in ("precision", "recall", "f1")
        },
    }

    def paired_delta(retrained_vals, baseline_vals, metric):
        deltas = [a - b for a, b in zip(retrained_vals, baseline_vals)]
        return {
            "metric": metric,
            "mean_delta": mean_std(deltas),
            "folds_improved": int(sum(1 for d in deltas if d > 0)),
            "folds_total": len(deltas),
            "per_fold": [round(float(d), 6) for d in deltas],
        }

    delta = {
        "sentiment_accuracy": paired_delta(sent_acc, base_acc, "accuracy"),
        "sentiment_macro_f1": paired_delta(sent_f1, base_f1, "macro_f1"),
        "frames_macro_f1_at_0.5": paired_delta(
            [r["frames_at_0.5"]["macro_f1"] for r in fold_results],
            [r["frames_baseline_at_0.5"]["macro_f1"] for r in fold_results],
            "frames_macro_f1@0.5",
        ),
        "frames_macro_f1_tuned": paired_delta(
            [r["frames_tuned"]["macro_f1"] for r in fold_results],
            [r["frames_baseline_tuned"]["macro_f1"] for r in fold_results],
            "frames_macro_f1_umbrales",
        ),
    }

    return {
        "n_folds": len(fold_results),
        "sentiment": {
            "accuracy": mean_std(sent_acc),
            "macro_f1": mean_std(sent_f1),
            "macro_precision": mean_std(
                [r["sentiment"]["macro_precision"] for r in fold_results]
            ),
            "macro_recall": mean_std(
                [r["sentiment"]["macro_recall"] for r in fold_results]
            ),
            "per_class": per_class,
            "confusion_matrix_sum": {
                "labels": SENTIMENT_LABELS,
                "matrix": confusion,
            },
        },
        "sentiment_baseline": {
            "accuracy": mean_std(base_acc),
            "macro_f1": mean_std(base_f1),
            "macro_precision": mean_std(
                [r["sentiment_baseline"]["macro_precision"] for r in fold_results]
            ),
            "macro_recall": mean_std(
                [r["sentiment_baseline"]["macro_recall"] for r in fold_results]
            ),
            "per_class": per_class_baseline,
            "confusion_matrix_sum": {
                "labels": SENTIMENT_LABELS,
                "matrix": confusion_base,
            },
        },
        "frames": frames,
        "frames_baseline": frames_baseline,
        "frames_macro": frames_macro,
        "frames_macro_baseline": frames_macro_baseline,
        "delta": delta,
    }


# --------------------------------------------------------------------------
# Entrenamiento final con todos los datos
# --------------------------------------------------------------------------
def train_final_models(df, tokenizers, args, device, grid):
    sent_tokenizer, frames_tokenizer = tokenizers
    texts = df["texto"].tolist()
    y_sent = df["sent_id"].to_numpy()
    y_frames = df[FRAME_MODEL_ORDER].to_numpy(dtype=float)

    out_dir = Path(args.out_dir)
    sent_out = out_dir / "bert-sentiment-retrained"
    frames_out = out_dir / "bert-frames-retrained"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("[final] entrenando sentimiento con todos los datos", flush=True)
    sentiment_enc = encode_texts(texts, sent_tokenizer, args.max_len)
    sent_model, _ = train_sentiment_model(
        sentiment_enc, y_sent, sentiment_enc, y_sent, args, device
    )
    sent_model.save_pretrained(str(sent_out))
    sent_tokenizer.save_pretrained(str(sent_out))
    print(f"[final] sentimiento guardado en {sent_out}", flush=True)

    print("[final] entrenando encuadres con todos los datos", flush=True)
    frames_enc = encode_texts(texts, frames_tokenizer, args.max_len)
    frames_model, _ = train_frames_model(
        frames_enc, y_frames, frames_enc, y_frames, args, device
    )
    frames_model.save_pretrained(str(frames_out))
    frames_tokenizer.save_pretrained(str(frames_out))
    print(f"[final] encuadres guardado en {frames_out}", flush=True)

    # sanity in-sample (NO es una estimación fuera de muestra; solo comprueba que
    # el modelo entrenó y que guarda/carga bien).
    pad_id = int(sent_model.config.pad_token_id or 1)
    sent_loader = build_loader(
        sentiment_enc, y_sent, args.eval_batch_size, False, pad_id
    )
    sent_probs = predict_probs(sent_model, sent_loader, device, "sentiment")
    frames_loader = build_loader(
        frames_enc, y_frames, args.eval_batch_size, False, pad_id
    )
    frames_probs = predict_probs(frames_model, frames_loader, device, "frames")
    defaults = {key: 0.5 for key in FRAME_CANONICAL}
    in_sample = {
        "advertencia": (
            "Métricas IN-SAMPLE sobre los mismos datos de entrenamiento; no usar "
            "para decidir si el modelo mejora. La estimación honesta es la CV."
        ),
        "sentiment": sentiment_report(y_sent, sent_probs),
        "frames_at_0.5": frames_report(y_frames, frames_probs, defaults),
    }
    del sent_model, frames_model, sent_loader, frames_loader
    gc.collect()
    return {
        "sentiment_dir": str(sent_out),
        "frames_dir": str(frames_out),
        "in_sample": in_sample,
    }


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main(argv=None) -> int:
    args = parse_args(argv)
    if args.log_file:
        log_path = Path(args.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        class Tee:
            def __init__(self, *streams):
                self.streams = streams

            def write(self, data):
                for stream in self.streams:
                    stream.write(data)
                    stream.flush()

            def flush(self):
                for stream in self.streams:
                    stream.flush()

        log_handle = open(log_path, "w", encoding="utf-8")
        sys.stdout = Tee(sys.stdout, log_handle)
        sys.stderr = Tee(sys.stderr, log_handle)

    started_at = time.time()
    torch.set_num_threads(args.num_threads)
    set_seed(args.seed)
    device = (
        torch.device("cuda" if torch.cuda.is_available() else "cpu")
        if args.device == "auto"
        else torch.device(args.device)
    )
    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    Path(args.artifacts_dir).mkdir(parents=True, exist_ok=True)
    grid = frame_threshold_grid(args)

    print("=" * 78, flush=True)
    print("Reentrenamiento BETO · balanceo por pesos + validación cruzada", flush=True)
    print("=" * 78, flush=True)
    print(f"dispositivo={device} hilos_torch={torch.get_num_threads()}", flush=True)
    print(
        f"config: folds={args.folds} epochs={args.epochs} max_len={args.max_len} "
        f"batch={args.batch_size} lr={args.lr} seed={args.seed}",
        flush=True,
    )
    print(f"datos={args.data}", flush=True)
    print(f"modelo_sentimiento={args.sent_model_dir}", flush=True)
    print(f"modelo_encuadres={args.frames_model_dir}", flush=True)

    # 1. corpus
    df, data_info = load_corpus(args.data, args.text_col, args.sent_col, args.max_rows)
    df["texto"] = df[args.text_col]
    print(
        f"[datos] filas leídas={data_info['filas_leidas']} "
        f"duplicados eliminados={data_info['duplicados_texto_eliminados']} "
        f"artículos únicos={data_info['articulos_unicos']}",
        flush=True,
    )
    print(f"[datos] sentimiento={data_info['sentimiento']}", flush=True)
    print(f"[datos] encuadres={data_info['encuadres_soporte']}", flush=True)

    # 2. tokenizers
    sent_tokenizer = AutoTokenizer.from_pretrained(str(args.sent_model_dir))
    frames_tokenizer = AutoTokenizer.from_pretrained(str(args.frames_model_dir))

    # 3. baseline actual sobre TODO el corpus (se reutiliza por fold)
    base_sent_probs, base_frames_probs = build_baseline_predictions(
        df, (sent_tokenizer, frames_tokenizer), args.max_len, args, device
    )
    write_json(
        Path(args.artifacts_dir) / "baseline_predictions.json",
        {
            "generated_at": utc_now(),
            "ids": df["ID"].tolist(),
            "sentiment_labels": SENTIMENT_LABELS,
            "frames_model_order": FRAME_MODEL_ORDER,
            "frames_canonical_keys": FRAME_CANONICAL,
            "sentiment_probs": base_sent_probs.tolist(),
            "frames_probs": base_frames_probs.tolist(),
            "sentiment_true": df["sent_id"].tolist(),
            "frames_true": df[FRAME_MODEL_ORDER].to_numpy(dtype=int).tolist(),
        },
    )

    production_thresholds = None
    prod_path = Path(args.production_thresholds) if args.production_thresholds else None
    if prod_path and prod_path.exists():
        try:
            raw = json.loads(prod_path.read_text(encoding="utf-8"))
            production_thresholds = {
                key: float(raw[key]) for key in FRAME_CANONICAL if key in raw
            }
            print(
                f"[baseline] thresholds de producción cargados de {prod_path}",
                flush=True,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"[aviso] no se pudieron leer thresholds de producción: {exc}", flush=True)

    # 4. splits
    splits, folds = make_splits(df, args.folds, args.seed, args.val_fraction)
    fold_results = []
    progress_path = Path(args.artifacts_dir) / "cv_progress.json"

    for split in splits:
        fold_started = time.time()
        result = evaluate_fold(
            fold=split["fold"],
            df=df,
            idx_train=split["train"],
            idx_val=split["val"],
            idx_test=split["test"],
            sent_tokenizer=sent_tokenizer,
            frames_tokenizer=frames_tokenizer,
            baseline_sent_probs=base_sent_probs,
            baseline_frames_probs=base_frames_probs,
            production_thresholds=production_thresholds,
            args=args,
            device=device,
            grid=grid,
        )
        fold_results.append(result)
        write_json(
            progress_path,
            {
                "updated_at": utc_now(),
                "folds_completed": len(fold_results),
                "folds_total": folds,
                "elapsed_seconds": round(time.time() - started_at, 1),
                "folds": [
                    {
                        "fold": r["fold"],
                        "sentiment_test_accuracy": r["sentiment"]["accuracy"],
                        "sentiment_test_macro_f1": r["sentiment"]["macro_f1"],
                        "frames_macro_f1@0.5": r["frames_at_0.5"]["macro_f1"],
                        "frames_macro_f1_tuned": r["frames_tuned"]["macro_f1"],
                        "baseline_sentiment_macro_f1": r["sentiment_baseline"]["macro_f1"],
                        "baseline_frames_macro_f1@0.5": r["frames_baseline_at_0.5"][
                            "macro_f1"
                        ],
                    }
                    for r in fold_results
                ],
            },
        )
        print(
            f"[fold {split['fold']}] terminado en {time.time() - fold_started:.1f}s",
            flush=True,
        )

    # 5. agregación CV
    cv = aggregate_cv(fold_results, grid, args.precision_floor, args)

    # 6. umbrales finales: SOLO con las predicciones de validación de todos los folds
    pooled_val_true = np.concatenate([r["val_true"]["frames"] for r in fold_results], axis=0)
    pooled_val_probs = np.concatenate([r["val_probs"]["frames"] for r in fold_results], axis=0)
    floor_thresholds, final_thresholds_meta = select_thresholds(
        pooled_val_true.astype(int), pooled_val_probs, grid, args.precision_floor
    )
    # salvaguarda anti-sobreajuste: si el umbral con piso empeora el F1 frente a
    # 0.5 en la misma validación, se conserva 0.5 (ver guard_thresholds).
    final_thresholds, thresholds_guard_info = guard_thresholds(
        floor_thresholds, pooled_val_true.astype(int), pooled_val_probs
    )
    defaults = {key: 0.5 for key in FRAME_CANONICAL}
    pooled_validation = {
        "n": int(pooled_val_true.shape[0]),
        "at_0.5": frames_report(pooled_val_true, pooled_val_probs, defaults),
        "con_piso_precision_estricto": frames_report(
            pooled_val_true, pooled_val_probs, floor_thresholds
        ),
        "finales_con_guarda": frames_report(
            pooled_val_true, pooled_val_probs, final_thresholds
        ),
    }
    write_json(
        Path(args.artifacts_dir) / "thresholds.json",
        {key: float(final_thresholds[key]) for key in FRAME_CANONICAL},
    )
    write_json(
        Path(args.artifacts_dir) / "thresholds_precision_floor_estricto.json",
        {key: float(floor_thresholds[key]) for key in FRAME_CANONICAL},
    )
    print(f"[umbrales] finales (con guarda)={final_thresholds}", flush=True)
    print(f"[umbrales] piso de precisión estricto={floor_thresholds}", flush=True)

    # 7. modelos finales
    final_info = None
    if not args.skip_final:
        final_info = train_final_models(
            df,
            (sent_tokenizer, frames_tokenizer),
            args,
            device,
            grid,
        )
        write_json(
            Path(args.out_dir) / "training_config.json",
            {
                "generated_at": utc_now(),
                "config": vars(args),
                "data_info": data_info,
                "final_thresholds": final_thresholds,
            },
        )

    # 8. artefacto principal
    elapsed = time.time() - started_at
    evaluation = {
        "generated_at": utc_now(),
        "elapsed_seconds": round(elapsed, 1),
        "config": {
            "folds": folds,
            "epochs": args.epochs,
            "max_len": args.max_len,
            "batch_size": args.batch_size,
            "eval_batch_size": args.eval_batch_size,
            "lr": args.lr,
            "weight_decay": args.weight_decay,
            "warmup_ratio": args.warmup_ratio,
            "patience": args.patience,
            "max_pos_weight": args.max_pos_weight,
            "val_fraction": args.val_fraction,
            "seed": args.seed,
            "num_threads": args.num_threads,
            "device": str(device),
            "threshold_grid": {
                "min": args.threshold_min,
                "max": args.threshold_max,
                "step": args.threshold_step,
                "precision_floor": args.precision_floor,
            },
            "sent_model_dir": str(args.sent_model_dir),
            "frames_model_dir": str(args.frames_model_dir),
            "data": [str(path) for path in args.data],
        },
        "data": data_info,
        "procedimiento": {
            "corpus": (
                "Se cargan los CSV con utf-8-sig, se validan etiquetas y se "
                "deduplica por texto. dataset_balanced.csv solo aporta 116 "
                "artículos únicos (79/79/79 es oversampling con reemplazo); el "
                "corpus único final es de 156 artículos."
            ),
            "cv": (
                "StratifiedKFold por sentimiento. De cada fold se aparta un test "
                "intacto; el resto se divide train/validación (estratificado). "
                "El early stopping usa macro-F1 de validación y los umbrales de "
                "encuadres se eligen SOLO con validación; las métricas reportadas "
                "salen del test de cada fold."
            ),
            "balanceo": (
                "sentimiento: CrossEntropyLoss ponderada (class_weight='balanced'); "
                "encuadres: BCEWithLogitsLoss con pos_weight=negativos/positivos "
                "por etiqueta (topado en max_pos_weight)."
            ),
            "baseline": (
                "Los checkpoints actuales de Desktop se evalúan en los mismos "
                "folds de test y con el mismo max_len que los reentrenados. Sus "
                "umbrales también se eligen con la validación de cada fold."
            ),
            "limitacion_principal": (
                "Los checkpoints base ya fueron entrenados con este corpus, así "
                "que los pesos iniciales están contaminados: la CV mide la "
                "ganancia de reajustar/balancear, no el rendimiento de un modelo "
                "entrenado desde cero. El baseline tiene la misma contaminación, "
                "por lo que el delta sigue siendo comparable."
            ),
        },
        "cv": cv,
        "final_thresholds": {
            key: float(final_thresholds[key]) for key in FRAME_CANONICAL
        },
        "final_thresholds_precision_floor_estricto": {
            key: float(floor_thresholds[key]) for key in FRAME_CANONICAL
        },
        "final_thresholds_guarda_info": thresholds_guard_info,
        "pooled_validation_thresholds": pooled_validation,
        "final_thresholds_validation_meta": final_thresholds_meta,
        "folds": [
            {
                "fold": r["fold"],
                "n_train": r["n_train"],
                "n_val": r["n_val"],
                "n_test": r["n_test"],
                "sentiment_test": r["sentiment"],
                "sentiment_test_baseline": r["sentiment_baseline"],
                "frames_test_at_0.5": r["frames_at_0.5"],
                "frames_test_tuned": r["frames_tuned"],
                "frames_test_baseline_at_0.5": r["frames_baseline_at_0.5"],
                "frames_test_baseline_tuned": r["frames_baseline_tuned"],
                "frames_test_production_thresholds": r["frames_production_thresholds"],
                "frames_test_baseline_production_thresholds": r[
                    "frames_baseline_production_thresholds"
                ],
                "thresholds_validation": r["thresholds_validation"],
                "baseline_thresholds_validation": r["baseline_thresholds_validation"],
                "early_stopping": r["early_stopping"],
            }
            for r in fold_results
        ],
        "final_models": final_info,
        "production_reference": {
            "thresholds_path": str(prod_path) if prod_path else None,
            "thresholds": production_thresholds,
        },
    }
    write_json(Path(args.artifacts_dir) / "retraining_evaluation.json", evaluation)

    # 9. resumen por consola
    print("\n" + "=" * 78, flush=True)
    print("RESUMEN CV (media ± desv. entre folds, test fuera de muestra)", flush=True)
    print("=" * 78, flush=True)
    print(
        f"sentimiento accuracy: retrenado "
        f"{cv['sentiment']['accuracy']['mean']:.4f} ± "
        f"{cv['sentiment']['accuracy']['std']:.4f} | baseline "
        f"{cv['sentiment_baseline']['accuracy']['mean']:.4f} ± "
        f"{cv['sentiment_baseline']['accuracy']['std']:.4f}",
        flush=True,
    )
    print(
        f"sentimiento macro-F1: retrenado "
        f"{cv['sentiment']['macro_f1']['mean']:.4f} ± "
        f"{cv['sentiment']['macro_f1']['std']:.4f} | baseline "
        f"{cv['sentiment_baseline']['macro_f1']['mean']:.4f} ± "
        f"{cv['sentiment_baseline']['macro_f1']['std']:.4f}",
        flush=True,
    )
    print(
        f"encuadres macro-F1 @0.5: retrenado "
        f"{cv['frames_macro']['at_0.5']['f1']['mean']:.4f} ± "
        f"{cv['frames_macro']['at_0.5']['f1']['std']:.4f} | baseline "
        f"{cv['frames_macro_baseline']['at_0.5']['f1']['mean']:.4f} ± "
        f"{cv['frames_macro_baseline']['at_0.5']['f1']['std']:.4f}",
        flush=True,
    )
    print(
        f"encuadres macro-F1 umbrales: retrenado "
        f"{cv['frames_macro']['tuned']['f1']['mean']:.4f} ± "
        f"{cv['frames_macro']['tuned']['f1']['std']:.4f} | baseline "
        f"{cv['frames_macro_baseline']['tuned']['f1']['mean']:.4f} ± "
        f"{cv['frames_macro_baseline']['tuned']['f1']['std']:.4f}",
        flush=True,
    )
    print(f"umbrales finales: {final_thresholds}", flush=True)
    if final_info:
        print(
            f"modelos finales: {final_info['sentiment_dir']} | "
            f"{final_info['frames_dir']}",
            flush=True,
        )
    print(f"artefactos: {Path(args.artifacts_dir)}", flush=True)
    print(f"tiempo total: {elapsed:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
