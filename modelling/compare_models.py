#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Compara los resultados OOF de BETO, RoBERTa y DistilBERT."""

import argparse
import json
from pathlib import Path

import pandas as pd

MODELLING_DIR = Path(__file__).resolve().parent
DEFAULT_METRICS = [
    MODELLING_DIR / "beto" / "models_beto" / "metrics.json",
    MODELLING_DIR / "roberta_es" / "models" / "metrics.json",
    MODELLING_DIR / "distilbert_es" / "models" / "metrics.json",
]
COMPARISON_FIELDS = ("data_path", "seed", "n_folds", "max_len")
REQUIRED_METRICS = (
    ("sent", "macro"),
    ("sent", "micro"),
    ("label", "macro"),
    ("label", "micro"),
)


def build_comparison(results):
    """Valida las condiciones comunes y ordena por F1 macro de temas."""
    if len(results) < 2:
        raise ValueError("Se necesitan al menos dos resultados para comparar.")

    reference_name, reference = results[0]
    for model_name, result in results[1:]:
        for field in COMPARISON_FIELDS:
            if result.get(field) != reference.get(field):
                raise ValueError(
                    f"Condiciones incompatibles entre {reference_name} y "
                    f"{model_name}: {field} no coincide."
                )

    rows = []
    for name, result in results:
        scores = {
            (metric["task"], metric["average"]): metric["f1"]
            for metric in result["metrics"]
        }
        missing = [key for key in REQUIRED_METRICS if key not in scores]
        if missing:
            raise ValueError(f"{name} no contiene métricas requeridas: {missing}")

        rows.append(
            {
                "modelo": result.get("model_label", name),
                "model_name": result.get("model_name"),
                "sent_macro_f1": scores[("sent", "macro")],
                "sent_micro_f1": scores[("sent", "micro")],
                "topics_macro_f1": scores[("label", "macro")],
                "topics_micro_f1": scores[("label", "micro")],
                "cv_seconds": result.get("cv_seconds"),
            }
        )

    return pd.DataFrame(rows).sort_values(
        "topics_macro_f1", ascending=False, ignore_index=True
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metrics",
        nargs="+",
        type=Path,
        default=DEFAULT_METRICS,
        help="Rutas a metrics.json, en el orden BETO, RoBERTa, DistilBERT.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=MODELLING_DIR / "model_comparison.csv",
        help="Ruta del CSV de comparación.",
    )
    args = parser.parse_args()

    results = []
    for path in args.metrics:
        if not path.is_file():
            raise FileNotFoundError(
                f"No se encontró {path}. Ejecuta primero el entrenamiento CV."
            )
        with path.open(encoding="utf-8") as file:
            results.append((path.parent.name, json.load(file)))

    comparison = build_comparison(results)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    comparison.to_csv(args.out, index=False, encoding="utf-8-sig")
    print(comparison.to_string(index=False))
    print(f"\nComparación guardada en: {args.out}")


if __name__ == "__main__":
    main()
