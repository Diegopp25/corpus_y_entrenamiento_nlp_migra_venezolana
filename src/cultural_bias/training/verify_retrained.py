#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Verifica que los modelos reentrenados cargan con el motor real de la API.

Carga los dos checkpoints con ``BertPairEngine`` (el mismo motor que usa
producción), carga los umbrales con ``load_thresholds`` y hace inferencia sobre
una noticia real del corpus. Sirve como prueba de integración entre
``training/`` y ``api/`` sin tocar los pesos de producción.

Uso (desde la raíz del worktree)::

    python training/verify_retrained.py
    python training/verify_retrained.py --index 5 --device cpu
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent

# Importar el api del worktree (motor real de producción).
sys.path.insert(0, str(REPO_DIR / "api"))

import pandas as pd  # noqa: E402

from app.engine.bert_pair import BertPairEngine, load_thresholds  # noqa: E402
from app.engine.labels import (  # noqa: E402
    FRAME_IDS,
    FRAME_MODEL_ORDER,
    SENTIMENT_LABELS,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Carga los modelos retrenados con BertPairEngine y los prueba "
        "sobre una noticia real del CSV."
    )
    parser.add_argument(
        "--sentiment-dir", default=str(SCRIPT_DIR / "models" / "bert-sentiment-retrained")
    )
    parser.add_argument(
        "--frames-dir", default=str(SCRIPT_DIR / "models" / "bert-frames-retrained")
    )
    parser.add_argument(
        "--thresholds", default=str(SCRIPT_DIR / "artifacts" / "thresholds.json")
    )
    parser.add_argument(
        "--data",
        default=str(REPO_DIR / "Data" / "dataset_migracion_venezolana_labeled.csv"),
    )
    parser.add_argument("--index", type=int, default=0, help="Fila del CSV a analizar.")
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--device", default="cpu", choices=["auto", "cpu", "cuda"])
    args = parser.parse_args(argv)

    print(f"sentiment_dir = {args.sentiment_dir}")
    print(f"frames_dir    = {args.frames_dir}")
    print(f"thresholds    = {args.thresholds}")

    thresholds = load_thresholds(args.thresholds)
    print(f"\nload_thresholds() -> {json.dumps(thresholds, ensure_ascii=False)}")
    if set(thresholds) != set(FRAME_IDS):
        raise SystemExit(
            f"ERROR: thresholds.json no cubre los 7 ids canónicos: {sorted(thresholds)}"
        )

    engine = BertPairEngine(
        sentiment_model_dir=args.sentiment_dir,
        frames_model_dir=args.frames_dir,
        device=args.device,
        max_length=args.max_length,
        thresholds=thresholds,
        sentiment_order=SENTIMENT_LABELS,
        frame_order=FRAME_MODEL_ORDER,
    )
    print(f"\nBertPairEngine cargado en {engine.device} · max_length={engine.max_length}")

    df = pd.read_csv(args.data, encoding="utf-8-sig")
    row = df.iloc[args.index]
    prediction = engine.predict(row["Cuerpo"])

    active_frames = {
        frame_id: round(prob, 4)
        for frame_id, prob in prediction.frames.items()
        if prob >= thresholds.get(frame_id, 0.5)
    }
    print("\n=== noticia analizada ===")
    print(f"ID: {row.get('ID')} | país: {row.get('Pais')} | medio: {row.get('Medio')}")
    print(f"título: {row.get('Titulo')}")
    print(f"etiqueta real sentimiento: {row.get('sentimiento')}")
    print("\nsentimiento (probabilidades):")
    for label, prob in sorted(prediction.sentiment.items(), key=lambda kv: -kv[1]):
        print(f"  {label:9s} {prob:.4f}")
    print("\nencuadres (probabilidad sigmoide):")
    for frame_id, prob in sorted(prediction.frames.items(), key=lambda kv: -kv[1]):
        flag = "  -> activo" if frame_id in active_frames else ""
        print(f"  {frame_id:20s} {prob:.4f}  umbral={thresholds[frame_id]:.2f}{flag}")
    print(f"\nencuadres activos con umbrales: {json.dumps(active_frames, ensure_ascii=False)}")
    if prediction.warnings:
        print(f"advertencias del motor: {prediction.warnings}")

    print("\nOK: los modelos retrenados cargan y predicen con el motor de producción.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
