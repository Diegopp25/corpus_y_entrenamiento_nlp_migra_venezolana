"""Carga del corpus."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from sentiment_benchmark.config import DATA_CSV


def load_corpus(path: Path | str = DATA_CSV, limit: int | None = None, seed: int = 42) -> pd.DataFrame:
    """Lee el CSV unificado y devuelve las notas con cuerpo no vacío.

    Agrega `article_id` (articulo_<índice original del CSV>). Con `limit`, toma una
    muestra aleatoria reproducible (útil para pruebas rápidas).
    """
    df = pd.read_csv(path)
    if "Unnamed: 0" in df.columns:
        df = df.rename(columns={"Unnamed: 0": "idx"})
    else:
        df.insert(0, "idx", range(len(df)))
    df["article_id"] = "articulo_" + df["idx"].astype(int).astype(str)
    df["Cuerpo"] = df["Cuerpo"].fillna("").astype(str).str.strip()
    df = df[df["Cuerpo"] != ""].copy()
    if limit is not None and limit < len(df):
        df = df.sample(limit, random_state=seed).sort_values("idx")
    return df.reset_index(drop=True)
