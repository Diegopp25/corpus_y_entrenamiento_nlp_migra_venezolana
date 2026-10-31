"""Acuerdo entre dos anotadores (kappa de Cohen) y lista de desacuerdos para discutir.

Uso:
    python -m sentiment_benchmark.annotator_agreement anotador_a.csv anotador_b.csv

Cada CSV debe tener `article_id` y `label_manual`. Se comparan solo las notas etiquetadas
por ambos. Un kappa bajo indica que la guía es ambigua: ajústala antes de seguir etiquetando.
Escribe la lista de desacuerdos en desacuerdos.csv (cambia la ruta con --out).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from sklearn.metrics import cohen_kappa_score

from sentiment_benchmark.config import CLASSES
from sentiment_benchmark.labels import NO_APLICA, normalize_gold


def _load(path: str, suffix: str) -> pd.DataFrame:
    d = pd.read_csv(path)
    d = d[d["label_manual"].notna() & (d["label_manual"].astype(str).str.strip() != "")].copy()
    d["label"] = d["label_manual"].map(normalize_gold)
    if d["label"].isna().any():
        raise SystemExit(f"{path}: etiquetas no reconocidas: {d.loc[d['label'].isna(), 'label_manual'].tolist()[:5]}")
    keep = [c for c in ["article_id", "Medio", "Titulo"] if c in d.columns]
    return d[keep + ["label", "notas"]].rename(columns={"label": f"label_{suffix}", "notas": f"notas_{suffix}"})


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file_a")
    p.add_argument("file_b")
    p.add_argument("--out", default="desacuerdos.csv")
    args = p.parse_args(argv)

    a, b = _load(args.file_a, "a"), _load(args.file_b, "b")
    m = a.merge(b.drop(columns=[c for c in ["Medio", "Titulo"] if c in b.columns]), on="article_id")
    if m.empty:
        raise SystemExit("Los dos archivos no comparten notas etiquetadas.")
    labels = CLASSES + [NO_APLICA]
    kappa = cohen_kappa_score(m["label_a"], m["label_b"], labels=labels)
    agree = (m["label_a"] == m["label_b"]).mean()
    print(f"Notas comparadas: {len(m)} | coincidencia: {agree:.0%} | kappa de Cohen: {kappa:.2f}")
    print("(referencia habitual: <0.40 bajo, 0.40-0.60 moderado, 0.60-0.80 bueno, >0.80 muy bueno)")
    print(pd.crosstab(m["label_a"], m["label_b"], rownames=["A"], colnames=["B"]).to_string())
    diff = m[m["label_a"] != m["label_b"]]
    out = Path(args.out)
    diff.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\n{len(diff)} desacuerdos -> {out}")


if __name__ == "__main__":
    main()
