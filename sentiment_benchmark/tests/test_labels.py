"""Pruebas del verificador de etiquetas y de la unión por URL (sin descargar modelos)."""
import numpy as np
import pandas as pd

from sentiment_benchmark.check_labels import topic_auc_table, topic_columns
from sentiment_benchmark.evaluate_gold import load_gold

WORDS = {"Seguridad": "policía delito captura", "Empleo": "trabajo salario empleo"}


def _synthetic(n=80, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        has = {t: int(rng.random() < 0.4) for t in WORDS}
        body = " ".join(w for t, ws in WORDS.items() if has[t] for w in ws.split())
        body += " " + " ".join(rng.choice(["ruta", "ciudad", "gobierno", "frontera", "vuelo", "norte"], 8))
        rows.append({"Titulo": f"nota {i}", "Cuerpo": body, "Medio": "X", **has})
    return pd.DataFrame(rows)


def test_topic_columns_ignores_text_and_sentiment():
    df = _synthetic().assign(sentimiento="Neutro", URL="u")
    assert set(topic_columns(df)) == set(WORDS)


def test_aligned_labels_score_high_and_shuffled_score_near_chance():
    df = _synthetic()
    aligned = topic_auc_table(df).loc[list(WORDS), "X"]
    assert (aligned > 0.85).all()
    # Con ~80 notas el AUC de un solo tema varía mucho por azar (0.4-0.7), por eso el
    # veredicto usa el promedio de varios temas; aquí se promedia además entre barajados.
    means = []
    for seed in range(6):
        shuffled = df.copy()
        rng = np.random.default_rng(seed)
        for t in WORDS:
            shuffled[t] = rng.permutation(df[t].to_numpy())
        means.append(float(topic_auc_table(shuffled).loc[list(WORDS), "X"].mean()))
    assert float(np.mean(means)) < 0.6


def test_load_gold_joins_by_url_not_by_id_and_accepts_aliases():
    corpus = pd.DataFrame({"article_id": ["articulo_0", "articulo_1", "articulo_2"],
                           "URL": ["u0", "u1", "u2"]})
    # El CSV etiquetado numera desde 1: ID articulo_1 corresponde a la URL u0.
    gold = pd.DataFrame({"ID": ["articulo_1", "articulo_2", "articulo_3"],
                         "URL": ["u0", "u1", "u2"],
                         "sentimiento": ["Neutro", "Negativo", "Positivo"]})
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "g.csv")
        gold.to_csv(path, index=False)
        g = load_gold(path, corpus)
    assert g.loc["articulo_0", "gold"] == "neutro"
    assert g.loc["articulo_1", "gold"] == "negativo"
    assert g.loc["articulo_2", "gold"] == "positivo"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
