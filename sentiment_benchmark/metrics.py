"""Métricas de acuerdo y evaluación."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score, f1_score

from sentiment_benchmark.config import CLASSES


def fleiss_kappa(labels: pd.DataFrame) -> float:
    """Kappa de Fleiss. `labels`: filas = notas, columnas = evaluadores (modelos), valores = clase."""
    table = np.stack([(labels == c).sum(axis=1).to_numpy() for c in CLASSES], axis=1).astype(float)
    n_raters = table.sum(axis=1)[0]
    if n_raters < 2:
        return float("nan")
    p_j = table.sum(axis=0) / table.sum()
    p_i = ((table**2).sum(axis=1) - n_raters) / (n_raters * (n_raters - 1))
    p_e = (p_j**2).sum()
    return float((p_i.mean() - p_e) / (1 - p_e)) if p_e < 1 else float("nan")


def pairwise_agreement(labels: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Matrices de % de coincidencia y kappa de Cohen entre cada par de modelos."""
    cols = list(labels.columns)
    pct = pd.DataFrame(index=cols, columns=cols, dtype=float)
    kappa = pd.DataFrame(index=cols, columns=cols, dtype=float)
    for a in cols:
        for b in cols:
            pct.loc[a, b] = float((labels[a] == labels[b]).mean())
            kappa.loc[a, b] = 1.0 if a == b else float(cohen_kappa_score(labels[a], labels[b], labels=CLASSES))
    return pct, kappa


def majority_vote(labels: pd.DataFrame) -> pd.Series:
    """Etiqueta más votada; 'sin_consenso' si hay empate en el primer lugar."""

    def vote(row: pd.Series) -> str:
        counts = row.value_counts()
        if len(counts) > 1 and counts.iloc[0] == counts.iloc[1]:
            return "sin_consenso"
        return counts.index[0]

    return labels.apply(vote, axis=1)


def bootstrap_ci(y_true, y_pred, metric, n_boot: int = 1000, seed: int = 0) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    n = len(y_true)
    vals = [metric(y_true[i], y_pred[i]) for i in (rng.integers(0, n, n) for _ in range(n_boot))]
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def macro_f1(y_true, y_pred) -> float:
    return float(f1_score(y_true, y_pred, labels=CLASSES, average="macro", zero_division=0))
