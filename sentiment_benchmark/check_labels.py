"""Verifica que las etiquetas estén unidas al texto correcto (¿se pueden predecir desde el texto?).

Uso:
    python -m sentiment_benchmark.check_labels ruta/dataset_migracion_venezolana_labeled.csv

Para cada medio entrena un clasificador sencillo (TF-IDF + regresión logística) con validación
cruzada y calcula el AUC de cada columna temática binaria (Seguridad, Política migratoria, ...).
AUC 0.5 = azar. Si las etiquetas de un medio están unidas a la nota equivocada, ese medio se queda
cerca (o por debajo) de 0.5 mientras los demás salen claramente por encima.

Es un diagnóstico, no una prueba: umbrales orientativos y muestras pequeñas. Un AUC medio alto
indica coherencia; uno bajo debe revisarse leyendo a mano algunas notas contra su etiqueta.
Las columnas temáticas se usan porque el tema es más fácil de predecir desde el texto que el tono.
"""
from __future__ import annotations

import argparse
import warnings

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import RepeatedStratifiedKFold
from sklearn.pipeline import make_pipeline

NON_TOPIC = {"ID", "article_id", "Titulo", "URL", "Autor", "Medio", "Pais", "Fecha", "Cuerpo",
             "sentimiento", "label_manual", "encuadre", "notas", "texto"}
MIN_POS = 8  # mínimo de notas con y sin el tema para calcular AUC


def topic_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in NON_TOPIC and set(df[c].dropna().unique()) <= {0, 1}]


def cv_auc(texts: np.ndarray, y: np.ndarray, seed: int = 0, repeats: int = 3) -> float:
    rs = RepeatedStratifiedKFold(n_splits=4, n_repeats=repeats, random_state=seed)
    aucs = []
    for tr, te in rs.split(texts, y):
        if len(set(y[te])) < 2:
            continue
        model = make_pipeline(
            TfidfVectorizer(sublinear_tf=True, ngram_range=(1, 2), min_df=2, max_df=0.9),
            LogisticRegression(C=5, max_iter=2000, class_weight="balanced"),
        )
        model.fit(texts[tr], y[tr])
        aucs.append(roc_auc_score(y[te], model.predict_proba(texts[te])[:, 1]))
    return float(np.mean(aucs))


def topic_auc_table(df: pd.DataFrame, group_col: str = "Medio", topics: list[str] | None = None) -> pd.DataFrame:
    """AUC por tema (filas) y grupo (columnas). NaN si el tema tiene muy pocos casos."""
    topics = topics or topic_columns(df)
    texto = (df["Titulo"].fillna("") + ". " + df["Cuerpo"].fillna("")).to_numpy()
    out = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for grp, idx in df.groupby(group_col).groups.items():
            pos = df.index.get_indexer(idx)
            col = {}
            for t in topics:
                y = df[t].to_numpy()[pos].astype(int)
                n1 = int(y.sum())
                col[t] = cv_auc(texto[pos], y) if n1 >= MIN_POS and len(y) - n1 >= MIN_POS else np.nan
            out[grp] = col
    return pd.DataFrame(out)


def verdict(mean_auc: float) -> str:
    if np.isnan(mean_auc):
        return "no evaluable (pocos casos por tema)"
    if mean_auc >= 0.65:
        return "coherente con el texto"
    if mean_auc >= 0.55:
        return "dudoso: señal débil, revisar a mano"
    return "SIN relación con el texto: probable desalineación o etiquetas al azar"


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("labeled_csv")
    p.add_argument("--group-col", default="Medio")
    args = p.parse_args(argv)

    df = pd.read_csv(args.labeled_csv).reset_index(drop=True)
    for c in ("Titulo", "Cuerpo", args.group_col):
        if c not in df.columns:
            raise SystemExit(f"Falta la columna {c!r}: el CSV debe traer el texto junto a las etiquetas.")
    topics = topic_columns(df)
    if not topics:
        raise SystemExit("No encontré columnas temáticas binarias (0/1).")
    table = topic_auc_table(df, args.group_col, topics)

    print(f"Notas: {len(df)} | grupos ({args.group_col}): {df[args.group_col].value_counts().to_dict()}")
    print("AUC por tema con validación cruzada (0.5 = azar; '-' = muy pocos casos)\n")
    shown = table.copy()
    print(shown.map(lambda v: "-" if np.isnan(v) else f"{v:.2f}").to_string())
    print()
    for grp in table.columns:
        m = float(np.nanmean(table[grp])) if table[grp].notna().any() else float("nan")
        print(f"{grp:<12} AUC medio {m:.2f}  ->  {verdict(m)}")


if __name__ == "__main__":
    main()
