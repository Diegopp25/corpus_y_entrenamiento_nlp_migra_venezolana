"""Compara los modelos entre sí (sin etiquetas humanas): distribución, acuerdo y consenso.

Uso:
    python -m sentiment_benchmark.analyze                 # lee results/full/target
    python -m sentiment_benchmark.analyze --run full      # tono general de la nota
    python -m sentiment_benchmark.analyze --run dummy/target

IMPORTANTE: acuerdo entre modelos NO es exactitud. Para saber cuál acierta más hay que
etiquetar una muestra a mano y correr `python -m sentiment_benchmark.evaluate_gold`.
"""
from __future__ import annotations

import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

from sentiment_benchmark.config import CLASS_COLORS, CLASSES, DATA_CSV, RESULTS_DIR  # noqa: E402
from sentiment_benchmark.data import load_corpus  # noqa: E402
from sentiment_benchmark.metrics import fleiss_kappa, majority_vote, pairwise_agreement  # noqa: E402

SURFACE = "#FFFFFF"
INK = "#1F2328"
MUTED = "#6B7280"


def load_predictions(run_dir) -> dict[str, pd.DataFrame]:
    preds = {}
    for f in sorted(run_dir.glob("articles_*.csv")):
        preds[f.stem.replace("articles_", "")] = pd.read_csv(f).set_index("article_id")
    if not preds:
        raise SystemExit(f"No hay articles_*.csv en {run_dir}. Corre primero run_models.")
    return preds


def plot_label_distribution(long: pd.DataFrame, path) -> None:
    medios = sorted(long["Medio"].unique())
    models = (
        long.assign(neg=(long["label"] == "negativo"))
        .groupby("model")["neg"].mean().sort_values().index.tolist()
    )
    fig, axes = plt.subplots(1, len(medios), figsize=(5.2 * len(medios), 0.5 * len(models) + 2.2),
                             sharey=True, facecolor=SURFACE)
    axes = np.atleast_1d(axes)
    for ax, medio in zip(axes, medios):
        sub = long[long["Medio"] == medio]
        shares = (sub.groupby(["model", "label"]).size().unstack(fill_value=0)
                  .reindex(index=models, columns=CLASSES, fill_value=0))
        shares = shares.div(shares.sum(axis=1), axis=0) * 100
        left = np.zeros(len(models))
        for c in CLASSES:
            vals = shares[c].to_numpy()
            ax.barh(models, vals, left=left, color=CLASS_COLORS[c], edgecolor=SURFACE,
                    linewidth=1.5, height=0.62, label=c)
            for y, (v, l) in enumerate(zip(vals, left)):
                if v >= 8:
                    ax.text(l + v / 2, y, f"{v:.0f}%", ha="center", va="center", fontsize=8,
                            color=INK if c == "neutro" else "white")
            left += vals
        ax.set_xlim(0, 100)
        ax.set_title(f"{medio} (n={sub['article_id'].nunique()})", loc="left", fontsize=10, color=INK)
        ax.set_xlabel("% de notas", color=MUTED, fontsize=9)
        ax.tick_params(colors=MUTED, labelsize=9, length=0)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color("#D0D5DB")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, frameon=False, fontsize=9)
    fig.suptitle("Etiqueta predicha por cada modelo, por medio", x=0.01, ha="left", fontsize=11,
                 color=INK, y=1.02)
    fig.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def plot_kappa_heatmap(kappa: pd.DataFrame, path) -> None:
    n = len(kappa)
    fig, ax = plt.subplots(figsize=(0.9 * n + 2.6, 0.8 * n + 1.6), facecolor=SURFACE)
    im = ax.imshow(kappa.to_numpy(dtype=float), cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(n), kappa.columns, rotation=35, ha="right", fontsize=9, color=MUTED)
    ax.set_yticks(range(n), kappa.index, fontsize=9, color=MUTED)
    for i in range(n):
        for j in range(n):
            v = kappa.iloc[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=9,
                    color="white" if v > 0.55 else INK)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title("Acuerdo entre modelos (kappa de Cohen; 1 = idénticos, 0 = azar)",
                 loc="left", fontsize=10, color=INK)
    fig.colorbar(im, ax=ax, fraction=0.04, pad=0.03)
    fig.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", default="full/target",
                   help="Subcarpeta de results/: full/target (tono hacia migrantes, por defecto), "
                        "full (tono general), limit_N/target, dummy/target")
    p.add_argument("--data", default=str(DATA_CSV))
    args = p.parse_args(argv)

    run_dir = RESULTS_DIR / args.run
    preds = load_predictions(run_dir)
    meta = load_corpus(args.data).set_index("article_id")[["Medio", "Pais", "Fecha", "Titulo"]]

    labels = pd.DataFrame({k: v["label"] for k, v in preds.items()}).dropna()
    polarity = pd.DataFrame({k: v["polarity"] for k, v in preds.items()}).loc[labels.index]
    labels_meta = labels.join(meta)

    # 1) Distribución de etiquetas por modelo y medio
    long = labels.reset_index().melt(id_vars="article_id", var_name="model", value_name="label")
    long = long.merge(meta[["Medio"]].reset_index(), on="article_id")
    dist = (long.groupby(["model", "Medio", "label"]).size().unstack(fill_value=0)
            .reindex(columns=CLASSES, fill_value=0))
    dist_pct = dist.div(dist.sum(axis=1), axis=0).mul(100).round(1)
    dist_pct.to_csv(run_dir / "label_distribution_pct.csv")

    # 2) Acuerdo entre pares y global
    pct, kappa = pairwise_agreement(labels)
    pct.round(3).to_csv(run_dir / "pairwise_agreement_pct.csv")
    kappa.round(3).to_csv(run_dir / "pairwise_kappa.csv")
    fk = fleiss_kappa(labels) if labels.shape[1] >= 2 else float("nan")

    # 3) Consenso por mayoría y cercanía de cada modelo al consenso
    consensus = majority_vote(labels)
    decided = consensus != "sin_consenso"
    vs_consensus = pd.Series({m: float((labels.loc[decided, m] == consensus[decided]).mean())
                              for m in labels.columns}).sort_values(ascending=False)
    labels_meta.assign(consenso=consensus).to_csv(run_dir / "labels_and_consensus.csv")
    vs_consensus.round(3).to_csv(run_dir / "agreement_with_consensus.csv", header=["coincidencia"])

    # 4) Correlación de la polaridad (p_pos - p_neg) entre modelos
    polarity.corr(method="spearman").round(3).to_csv(run_dir / "polarity_spearman.csv")

    # 5) Gráficos
    plot_label_distribution(long, run_dir / "label_distribution.png")
    if labels.shape[1] >= 2:
        plot_kappa_heatmap(kappa, run_dir / "kappa_heatmap.png")

    # Resumen en consola
    print(f"Notas comparadas: {len(labels)} | modelos: {', '.join(labels.columns)}")
    print(f"Kappa de Fleiss (todos los modelos): {fk:.3f}")
    print(f"Notas sin consenso (empate): {(~decided).sum()} de {len(labels)}")
    print("\nCoincidencia de cada modelo con el consenso de mayoría:")
    print(vs_consensus.round(3).to_string())
    print("\nDistribución (% de notas) por modelo y medio:")
    print(dist_pct.to_string())
    print(f"\nArchivos escritos en {run_dir}")


if __name__ == "__main__":
    main()
