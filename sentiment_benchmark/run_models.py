"""Corre los modelos de sentimiento sobre el corpus y guarda predicciones.

Uso (desde la raíz del repo):
    python -m sentiment_benchmark.run_models                      # los 8 modelos, corpus completo
    python -m sentiment_benchmark.run_models --models robertuito,xlmr_twitter
    python -m sentiment_benchmark.run_models --limit 20           # prueba rápida
    python -m sentiment_benchmark.run_models --backend dummy      # prueba del pipeline (modelos de juguete)

Cada fragmento se puntúa una sola vez y se agrega de DOS maneras:
    results/<run>/            todos los fragmentos de la nota (tono general del texto)
    results/<run>/target/     solo los fragmentos que mencionan migrantes/venezolanos
                              (aproxima el tono HACIA el grupo; si una nota no tiene
                              ninguno, se usa toda la nota y se marca fallback_all=True)

Archivos: chunks_<modelo>.csv, articles_<modelo>.csv, run_summary.json
"""
from __future__ import annotations

import argparse
import json
import time
import traceback

import numpy as np
import pandas as pd

from sentiment_benchmark.backends import DUMMY_KEYS, build_scorer
from sentiment_benchmark.config import CLASSES, DATA_CSV, MODELS, PROB_COLS, RESULTS_DIR
from sentiment_benchmark.data import load_corpus
from sentiment_benchmark.text_utils import chunk_text, mentions_target


def _progress(iterable, desc: str):
    try:
        from tqdm import tqdm

        return tqdm(iterable, desc=desc)
    except ImportError:
        return iterable


def build_chunks(df: pd.DataFrame, scorer) -> pd.DataFrame:
    rows = []
    for row in _progress(list(df.itertuples(index=False)), "troceando"):
        for k, (text, n_tokens) in enumerate(chunk_text(row.Cuerpo, scorer.count_tokens, scorer.budget)):
            rows.append({
                "article_id": row.article_id,
                "chunk_idx": k,
                "n_tokens": n_tokens,
                "mentions_target": mentions_target(text),
                "text": text,
            })
    return pd.DataFrame(rows)


def aggregate_articles(chunks: pd.DataFrame, target_only: bool = False) -> pd.DataFrame:
    """Promedio de probabilidades por nota, ponderado por tokens del fragmento.

    Con `target_only`, solo cuentan los fragmentos que mencionan al grupo objetivo; si una
    nota no tiene ninguno se usa toda la nota (fallback_all=True).
    """
    rows = []
    for article_id, g in chunks.groupby("article_id", sort=False):
        n_target = int(g["mentions_target"].sum())
        used, fallback = g, False
        if target_only:
            if n_target > 0:
                used = g[g["mentions_target"]]
            else:
                fallback = True
        w = used["n_tokens"].to_numpy(dtype=float)
        w = w / w.sum() if w.sum() > 0 else np.full(len(used), 1 / len(used))
        probs = (used[PROB_COLS].to_numpy() * w[:, None]).sum(axis=0)
        rows.append({
            "article_id": article_id, **dict(zip(PROB_COLS, probs)),
            "n_chunks": len(used), "n_target_chunks": n_target, "fallback_all": fallback,
        })
    art = pd.DataFrame(rows)
    art["label"] = [CLASSES[i] for i in art[PROB_COLS].to_numpy().argmax(axis=1)]
    art["polarity"] = art["p_positivo"] - art["p_negativo"]
    return art


def run_one(key: str, df: pd.DataFrame, out_dir, args) -> float:
    spec = MODELS.get(key)
    if spec is None and args.backend != "dummy":
        raise KeyError(f"Modelo desconocido: {key}. Opciones: {list(MODELS)}")
    t0 = time.time()
    scorer = build_scorer(key, spec, args.backend, args.device)
    chunks = build_chunks(df, scorer)
    print(f"[{key}] {len(df)} notas -> {len(chunks)} fragmentos (presupuesto {scorer.budget} tokens)")
    probs = scorer.predict(chunks["text"].tolist(), batch_size=args.batch_size)
    chunks[PROB_COLS] = probs
    chunks.drop(columns=["text"]).to_csv(out_dir / f"chunks_{key}.csv", index=False)
    aggregate_articles(chunks).to_csv(out_dir / f"articles_{key}.csv", index=False)
    target = aggregate_articles(chunks, target_only=True)
    target.to_csv(out_dir / "target" / f"articles_{key}.csv", index=False)
    print(f"[{key}] notas sin ningún fragmento sobre migrantes (usan toda la nota): "
          f"{int(target['fallback_all'].sum())} de {len(target)}")
    return time.time() - t0


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--models", default="all", help="Claves separadas por coma o 'all'")
    p.add_argument("--data", default=str(DATA_CSV))
    p.add_argument("--limit", type=int, default=None, help="Muestra aleatoria de N notas")
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--device", default="auto", help="auto | cpu | cuda | mps")
    p.add_argument("--backend", choices=["hf", "dummy"], default="hf")
    p.add_argument("--force", action="store_true", help="Recalcular aunque exista el resultado")
    args = p.parse_args(argv)

    df = load_corpus(args.data, limit=args.limit)
    if args.backend == "dummy":
        keys = list(DUMMY_KEYS)
        run_name = "dummy"
    else:
        keys = list(MODELS) if args.models == "all" else [k.strip() for k in args.models.split(",") if k.strip()]
        run_name = f"limit_{args.limit}" if args.limit else "full"
    out_dir = RESULTS_DIR / run_name
    (out_dir / "target").mkdir(parents=True, exist_ok=True)

    summary = {"n_articles": len(df), "seconds": {}, "failed": {}}
    for key in keys:
        if (out_dir / f"articles_{key}.csv").exists() and (out_dir / "target" / f"articles_{key}.csv").exists() \
                and not args.force:
            print(f"[{key}] ya existe, se omite (usa --force para recalcular)")
            continue
        try:
            summary["seconds"][key] = round(run_one(key, df, out_dir, args), 1)
        except Exception as exc:  # un modelo caído no debe tumbar a los demás
            summary["failed"][key] = f"{type(exc).__name__}: {exc}"
            print(f"[{key}] FALLÓ: {exc}")
            traceback.print_exc()
    (out_dir / "run_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nListo. Resultados en {out_dir} (y {out_dir / 'target'})")
    if summary["failed"]:
        print("Modelos que fallaron:", ", ".join(summary["failed"]))


if __name__ == "__main__":
    main()
