#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Recalcula los umbrales finales a partir de las predicciones de validación.

La corrida de ``train_models.py`` guarda en ``artifacts/cv_folds/fold_*.json``
las probabilidades de validación y de test de cada fold. Con esos datos este
script:

1. recalcula los umbrales con el protocolo del piso de precisión (estricto),
2. aplica la salvaguarda anti-sobreajuste (si el umbral con piso empeora el F1
   frente a 0.5 en la misma validación, se conserva 0.5),
3. calcula también los umbrales F1-óptimos sin piso,
4. reescribe ``artifacts/thresholds.json`` con los umbrales recomendados,
   guarda las variantes estrictas en artefactos aparte, y
5. anexa a ``artifacts/retraining_evaluation.json`` las métricas de validación y
   de test de cada variante.

Es útil para auditar los umbrales sin volver a entrenar (~5 s en CPU).

Uso:
    python training/recompute_thresholds.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import train_models as tm

SCRIPT_DIR = Path(__file__).resolve().parent
ARTIFACTS = SCRIPT_DIR / "artifacts"


def load_folds():
    paths = sorted((ARTIFACTS / "cv_folds").glob("fold_*.json"))
    if not paths:
        raise SystemExit(
            f"No hay predicciones por fold en {ARTIFACTS / 'cv_folds'}. "
            "Ejecuta antes training/train_models.py."
        )
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def max_f1_thresholds(y_true, probs, grid, keys, index_of):
    """Umbral que maximiza F1 por etiqueta, sin piso de precisión."""
    thresholds = {}
    for key in keys:
        j = index_of[key]
        y = y_true[:, j].astype(int)
        p = probs[:, j]
        best = None
        for t in grid:
            metrics = tm._binary_metrics_at(p, y, t)
            candidate = (metrics["f1"], metrics["precision"], t)
            if best is None or candidate > best:
                best = candidate
        thresholds[key] = float(best[2])
    return thresholds


def main() -> int:
    folds = load_folds()
    evaluation_path = ARTIFACTS / "retraining_evaluation.json"
    if not evaluation_path.exists():
        raise SystemExit(f"Falta {evaluation_path}")
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))

    keys = folds[0]["frames"]["canonical_keys"]
    index_of = folds[0]["frames"]["canonical_to_model_index"]
    grid_cfg = evaluation["config"]["threshold_grid"]
    precision_floor = float(grid_cfg["precision_floor"])
    grid = [
        round(grid_cfg["min"] + i * grid_cfg["step"], 2)
        for i in range(
            int(round((grid_cfg["max"] - grid_cfg["min"]) / grid_cfg["step"])) + 1
        )
    ]
    print(f"folds={len(folds)} grid={grid} piso_precision={precision_floor}")

    val_true = np.concatenate([np.array(f["frames"]["true_val"]) for f in folds], axis=0)
    val_probs = np.concatenate([np.array(f["frames"]["val_probs"]) for f in folds], axis=0)
    print(f"predicciones de validación agrupadas: n={val_true.shape[0]}")

    floor_thresholds, _ = tm.select_thresholds(
        val_true.astype(int), val_probs, grid, precision_floor
    )
    guarded, guard_info = tm.guard_thresholds(
        floor_thresholds, val_true.astype(int), val_probs
    )
    alt_thresholds = max_f1_thresholds(val_true, val_probs, grid, keys, index_of)
    defaults = {key: 0.5 for key in keys}

    pooled_validation = {
        "n": int(val_true.shape[0]),
        "at_0.5": tm.frames_report(val_true, val_probs, defaults),
        "con_piso_precision_estricto": tm.frames_report(
            val_true, val_probs, floor_thresholds
        ),
        "finales_con_guarda": tm.frames_report(val_true, val_probs, guarded),
        "alt_max_f1": tm.frames_report(val_true, val_probs, alt_thresholds),
    }

    # Métricas de test por fold con los umbrales finales (con guarda).
    guarded_fold_reports = []
    for fold in folds:
        y_true = np.array(fold["frames"]["true_test"])
        probs = np.array(fold["frames"]["test_probs"])
        guarded_fold_reports.append(tm.frames_report(y_true, probs, guarded))
    guarded_cv = {
        "per_fold_macro_f1": [r["macro_f1"] for r in guarded_fold_reports],
        "macro_f1": tm.mean_std([r["macro_f1"] for r in guarded_fold_reports]),
        "macro_precision": tm.mean_std(
            [r["macro_precision"] for r in guarded_fold_reports]
        ),
        "macro_recall": tm.mean_std([r["macro_recall"] for r in guarded_fold_reports]),
        "per_label": {
            key: {
                "f1": tm.mean_std(
                    [r["per_label"][key]["f1"] for r in guarded_fold_reports]
                ),
                "precision": tm.mean_std(
                    [r["per_label"][key]["precision"] for r in guarded_fold_reports]
                ),
                "recall": tm.mean_std(
                    [r["per_label"][key]["recall"] for r in guarded_fold_reports]
                ),
            }
            for key in keys
        },
    }

    evaluation["final_thresholds"] = {key: float(guarded[key]) for key in keys}
    evaluation["final_thresholds_guarda_info"] = guard_info
    evaluation["final_thresholds_precision_floor_estricto"] = {
        key: float(floor_thresholds[key]) for key in keys
    }
    evaluation["final_thresholds_alt_max_f1"] = {
        key: float(alt_thresholds[key]) for key in keys
    }
    evaluation["pooled_validation_thresholds"] = pooled_validation
    evaluation["guarded_thresholds_cv"] = guarded_cv
    evaluation["thresholds_postprocesado"] = True
    evaluation["thresholds_postproceso_info"] = (
        "Umbrales finales recalculados de artifacts/cv_folds/fold_*.json con "
        "training/recompute_thresholds.py: se aplicó la salvaguarda de conservar "
        "0.5 cuando el umbral con piso de precisión empeora el F1 en la misma "
        "validación. Las variantes estrictas quedan en artefactos aparte."
    )
    evaluation_path.write_text(
        json.dumps(tm.round_floats(evaluation), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    tm.write_json(
        ARTIFACTS / "thresholds.json",
        {key: float(guarded[key]) for key in keys},
    )
    tm.write_json(
        ARTIFACTS / "thresholds_precision_floor_estricto.json",
        {key: float(floor_thresholds[key]) for key in keys},
    )
    tm.write_json(
        ARTIFACTS / "thresholds_alt_max_f1.json",
        {key: float(alt_thresholds[key]) for key in keys},
    )

    def summary(report):
        return round(report["macro_f1"], 4)

    print("\nResumen (macro-F1 en validación agrupada):")
    print(f"  @0.5                              {summary(pooled_validation['at_0.5'])}")
    print(
        "  piso de precisión estricto        "
        f"{summary(pooled_validation['con_piso_precision_estricto'])}"
    )
    print(
        "  finales con guarda (recommended)  "
        f"{summary(pooled_validation['finales_con_guarda'])}"
    )
    print(
        "  alt F1-óptimo sin piso            "
        f"{summary(pooled_validation['alt_max_f1'])}"
    )
    print("\numbrales recomendados:", guarded)
    print("umbrales piso estricto:", floor_thresholds)
    print("umbrales alt max-F1:", alt_thresholds)
    print(
        "\ntest CV con umbrales recomendados: macro-F1 "
        f"{guarded_cv['macro_f1']['mean']:.3f} ± {guarded_cv['macro_f1']['std']:.3f}"
    )
    print(f"\nArtefactos actualizados en {ARTIFACTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
