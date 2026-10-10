"""Genera la muestra de notas para etiquetar a mano (el 'gold' del benchmark).

Uso:
    python -m sentiment_benchmark.make_annotation_sample --n 60

Crea annotations/annotation_sample.csv con tres columnas para rellenar:
    label_manual  negativo | neutro | positivo | no_aplica   (también vale - / 0 / + / na)
    encuadre      opcional: categoría de cómo se enmarca a los migrantes (ver la guía)
    notas         opcional: dudas o citas que justifican la etiqueta

Lee annotations/GUIA_ETIQUETADO.md antes de empezar: se etiqueta el TONO HACIA los migrantes
venezolanos, no el tono general de la nota. Si dos personas anotan, usa una copia del archivo
por persona y corre `python -m sentiment_benchmark.annotator_agreement a.csv b.csv`.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from sentiment_benchmark.config import ANNOTATION_SAMPLE_CSV, DATA_CSV
from sentiment_benchmark.data import load_corpus


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--n", type=int, default=60, help="Total de notas (se reparte por medio)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--data", default=str(DATA_CSV))
    p.add_argument("--out", default=str(ANNOTATION_SAMPLE_CSV))
    args = p.parse_args(argv)

    df = load_corpus(args.data)
    medios = sorted(df["Medio"].unique())
    per_medio = max(1, args.n // len(medios))
    parts = [g.sample(min(per_medio, len(g)), random_state=args.seed) for _, g in df.groupby("Medio")]
    sample = pd.concat(parts).sort_values(["Medio", "idx"]).reset_index(drop=True)
    out = sample[["article_id", "Medio", "Pais", "Fecha", "Titulo", "URL"]].copy()
    out["cuerpo"] = sample["Cuerpo"]  # nota completa: el tono hacia el grupo puede estar al final
    out["label_manual"] = ""
    out["encuadre"] = ""
    out["notas"] = ""

    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"{len(out)} notas ({per_medio} por medio) -> {path}")
    print("Lee annotations/GUIA_ETIQUETADO.md, rellena `label_manual` y corre: "
          "python -m sentiment_benchmark.evaluate_gold")


if __name__ == "__main__":
    main()
