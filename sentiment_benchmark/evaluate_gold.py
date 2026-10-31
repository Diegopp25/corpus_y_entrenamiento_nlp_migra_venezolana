"""Evalúa cada modelo contra tus etiquetas manuales (tono HACIA los migrantes) y los ordena.

Uso:
    python -m sentiment_benchmark.evaluate_gold --gold ruta/dataset_..._labeled.csv            # results/full/target
    python -m sentiment_benchmark.evaluate_gold --gold ruta/dataset_..._labeled.csv --run full # tono general de la nota
    python -m sentiment_benchmark.evaluate_gold --gold ruta/dataset_..._labeled.csv --medios Milenio

El CSV debe tener la etiqueta (`label_manual` o `sentimiento`: negativo/neutro/positivo/no_aplica,
en cualquier capitalización) y una forma de identificar la nota: la columna `URL` (recomendado) o
`article_id`/`ID`. Con `URL` la unión es por texto y no depende de cómo se numeraron las notas
(aquí los IDs empiezan en articulo_0 y los del CSV etiquetado en articulo_1: unir por ID las
desplazaría una fila). `--medios` restringe la evaluación a esos medios.
Las notas `no_aplica` se excluyen de la evaluación (un modelo no puede saber que la nota no trata
de migrantes), pero se cuentan. Con pocas notas los intervalos de confianza serán anchos.

Además escribe gold_tone_by_medio.csv: cómo etiquetaron las personas el tono por medio/país,
que es la base para discutir diferencias de sesgo entre Colombia y México.
"""
from __future__ import annotations

import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score  # noqa: E402

from sentiment_benchmark.analyze import INK, MUTED, SURFACE, load_predictions  # noqa: E402
from sentiment_benchmark.config import CLASSES, DATA_CSV, RESULTS_DIR  # noqa: E402
from sentiment_benchmark.data import load_corpus  # noqa: E402
from sentiment_benchmark.labels import NO_APLICA, normalize_gold  # noqa: E402
from sentiment_benchmark.metrics import bootstrap_ci, macro_f1, majority_vote  # noqa: E402


def load_gold(path, corpus: pd.DataFrame | None = None) -> pd.DataFrame:
    g = pd.read_csv(path)
    g = g.rename(columns={"sentimiento": "label_manual", "ID": "article_id"})
    if "label_manual" not in g.columns:
        raise SystemExit("El CSV necesita una columna `label_manual` o `sentimiento`.")
    if "URL" in g.columns and corpus is not None:
        url_to_id = corpus.set_index("URL")["article_id"]
        g["article_id"] = g["URL"].map(url_to_id)
        lost = int(g["article_id"].isna().sum())
        if lost:
            print(f"AVISO: {lost} filas del CSV etiquetado no están (por URL) en el corpus y se omiten.")
        g = g[g["article_id"].notna()].copy()
    elif "article_id" not in g.columns:
        raise SystemExit("El CSV necesita la columna `URL` o `article_id`.")
    g = g[g["label_manual"].notna() & (g["label_manual"].astype(str).str.strip() != "")].copy()
    g["gold"] = g["label_manual"].map(normalize_gold)
    bad = g[g["gold"].isna()]
    if len(bad):
        raise SystemExit(f"Etiquetas no reconocidas en {len(bad)} filas, p. ej.: {bad['label_manual'].head(3).tolist()}")
    if "encuadre" not in g.columns:
        g["encuadre"] = ""
    g["encuadre"] = g["encuadre"].fillna("").astype(str).str.strip().str.lower()
    return g.set_index("article_id")[["gold", "encuadre"]]


def plot_ranking(table: pd.DataFrame, path) -> None:
    t = table.sort_values("macro_f1")
    fig, ax = plt.subplots(figsize=(6.4, 0.45 * len(t) + 1.6), facecolor=SURFACE)
    y = range(len(t))
    ax.hlines(y, t["f1_ci_low"], t["f1_ci_high"], color="#9AA0A6", linewidth=2)
    ax.scatter(t["macro_f1"], y, s=46, color="#2A6F97", edgecolor=SURFACE, linewidth=1.5, zorder=3)
    ax.set_yticks(list(y), t.index, fontsize=9, color=INK)
    ax.set_xlim(0, 1)
    ax.set_xlabel("Macro-F1 (punto) con IC 95% por bootstrap (línea)", fontsize=9, color=MUTED)
    ax.grid(axis="x", color="#E5E7EB", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0, colors=MUTED)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.set_title(f"Macro-F1 contra etiquetas manuales (n={int(t['n'].iloc[0])})", loc="left",
                 fontsize=10, color=INK)
    fig.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", default="full/target")
    p.add_argument("--gold", required=True, help="CSV etiquetado (con URL y sentimiento/label_manual)")
    p.add_argument("--data", default=str(DATA_CSV))
    p.add_argument("--n-boot", type=int, default=1000)
    p.add_argument("--medios", default="", help="Evaluar solo estos medios (coma), p. ej. Milenio")
    args = p.parse_args(argv)

    run_dir = RESULTS_DIR / args.run
    corpus = load_corpus(args.data)
    gold_all = load_gold(args.gold, corpus).join(corpus.set_index("article_id")[["Medio", "Pais"]])
    if args.medios:
        keep = [m.strip() for m in args.medios.split(",") if m.strip()]
        gold_all = gold_all[gold_all["Medio"].isin(keep)]
        if gold_all.empty:
            raise SystemExit(f"Ninguna nota etiquetada pertenece a {keep}.")
        print(f"Evaluando solo: {', '.join(keep)} ({len(gold_all)} notas etiquetadas)")

    # Qué dijeron las personas, por medio (incluye no_aplica)
    tone = pd.crosstab(gold_all["Medio"], gold_all["gold"])
    tone_pct = (tone.drop(columns=[NO_APLICA], errors="ignore")
                .pipe(lambda d: d.div(d.sum(axis=1), axis=0) * 100).round(1).add_suffix("_pct"))
    pd.concat([tone, tone_pct], axis=1).to_csv(run_dir / "gold_tone_by_medio.csv")
    if (gold_all["encuadre"] != "").any():
        pd.crosstab(gold_all.loc[gold_all["encuadre"] != "", "encuadre"],
                    gold_all.loc[gold_all["encuadre"] != "", "Medio"]).to_csv(run_dir / "gold_encuadre_by_medio.csv")

    n_na = int((gold_all["gold"] == NO_APLICA).sum())
    gold = gold_all.loc[gold_all["gold"] != NO_APLICA, "gold"]

    preds = load_predictions(run_dir)
    labels = pd.DataFrame({k: v["label"] for k, v in preds.items()})
    common = gold.index.intersection(labels.index)
    if len(common) == 0:
        raise SystemExit("Ninguna nota etiquetada coincide con las predicciones (¿mismo --run?).")
    y = gold.loc[common]
    L = labels.loc[common].copy()
    L["consenso_mayoria"] = majority_vote(labels.loc[common])

    rows = []
    for model in L.columns:
        pred = L[model]
        lo, hi = bootstrap_ci(y.to_numpy(), pred.to_numpy(), macro_f1, n_boot=args.n_boot)
        per_class = f1_score(y, pred, labels=CLASSES, average=None, zero_division=0)
        rows.append({
            "model": model, "n": len(y),
            "accuracy": accuracy_score(y, pred), "macro_f1": macro_f1(y, pred),
            "f1_ci_low": lo, "f1_ci_high": hi,
            **{f"f1_{c}": v for c, v in zip(CLASSES, per_class)},
        })
        cm = pd.DataFrame(confusion_matrix(y, pred, labels=CLASSES),
                          index=[f"real_{c}" for c in CLASSES], columns=[f"pred_{c}" for c in CLASSES])
        cm.to_csv(run_dir / f"confusion_{model}.csv")
    table = pd.DataFrame(rows).set_index("model").sort_values("macro_f1", ascending=False).round(3)
    table.to_csv(run_dir / "gold_evaluation.csv")
    plot_ranking(table, run_dir / "gold_macro_f1.png")

    print(f"Notas etiquetadas: {len(gold_all)} | no_aplica (excluidas): {n_na} | evaluadas: {len(y)}")
    print(f"Distribución humana (evaluadas): {y.value_counts().to_dict()}")
    print("\nTono humano por medio:")
    print(pd.concat([tone, tone_pct], axis=1).to_string())
    if len(y) < 50:
        print("\nAVISO: con menos de ~50 notas las diferencias entre modelos suelen no ser significativas.")
    print("\nModelos contra etiquetas manuales:")
    print(table.to_string())
    print(f"\nArchivos escritos en {run_dir}")


if __name__ == "__main__":
    main()
