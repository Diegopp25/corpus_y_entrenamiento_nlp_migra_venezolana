"""Pruebas sin descargar modelos. Ejecutar:  python -m pytest sentiment_benchmark/tests  (o con `python`)."""
import numpy as np
import pandas as pd

from sentiment_benchmark.labels import class_groups, normalize_gold, normalize_label
from sentiment_benchmark.metrics import fleiss_kappa, majority_vote
from sentiment_benchmark.run_models import aggregate_articles
from sentiment_benchmark.text_utils import chunk_text, mentions_target, split_sentences


def _count(texts):
    return [len(t.split()) for t in texts]


def test_normalize_label_variants():
    assert normalize_label("NEG") == "negativo"
    assert normalize_label("Neutral") == "neutro"
    assert normalize_label("POS") == "positivo"
    assert normalize_label("Negativo") == "negativo"
    assert normalize_label("1 star") == "negativo"
    assert normalize_label("3 stars") == "neutro"
    assert normalize_label("5 stars") == "positivo"
    assert normalize_label("LABEL_0") is None
    assert normalize_gold("+") == "positivo"
    assert normalize_gold("No aplica") == "no_aplica"
    assert normalize_gold("NA") == "no_aplica"


def test_class_groups_stars_and_binary():
    stars = {i: f"{i + 1} star{'s' if i else ''}" for i in range(5)}
    assert dict(class_groups(stars)) == {0: [0, 1], 1: [2], 2: [3, 4]}
    assert dict(class_groups({0: "Negativo", 1: "Positivo"})) == {0: [0], 2: [1]}


def test_class_groups_unknown_label_raises():
    try:
        class_groups({0: "LABEL_0", 1: "LABEL_1"})
    except ValueError:
        return
    raise AssertionError("debía lanzar ValueError")


def test_split_sentences():
    text = "Llegaron cientos. Algunos se quedaron. ¿Y ahora qué? Nadie sabe."
    assert len(split_sentences(text)) == 4


def test_chunks_respect_budget_and_keep_all_words():
    sentences = [" ".join(f"w{i}_{j}" for j in range(12)) + "." for i in range(30)]
    text = " ".join(sentences)
    chunks = chunk_text(text, _count, budget=40)
    assert all(n <= 40 for _, n in chunks)
    assert sum(len(c.split()) for c, _ in chunks) == len(text.split())


def test_overlong_sentence_is_split():
    text = " ".join(f"p{i}" for i in range(500)) + "."
    chunks = chunk_text(text, _count, budget=50)
    assert len(chunks) > 1 and all(n <= 50 for _, n in chunks)
    assert sum(len(c.split()) for c, _ in chunks) == 500


def test_fleiss_perfect_and_majority():
    perfect = pd.DataFrame({"a": ["negativo", "positivo", "neutro"] * 4,
                            "b": ["negativo", "positivo", "neutro"] * 4,
                            "c": ["negativo", "positivo", "neutro"] * 4})
    assert abs(fleiss_kappa(perfect) - 1.0) < 1e-9
    tie = pd.DataFrame({"a": ["negativo"], "b": ["positivo"]})
    assert majority_vote(tie).iloc[0] == "sin_consenso"
    maj = pd.DataFrame({"a": ["negativo"], "b": ["negativo"], "c": ["positivo"]})
    assert majority_vote(maj).iloc[0] == "negativo"


def test_mentions_target():
    assert mentions_target("Miles de migrantes venezolanos llegaron")
    assert mentions_target("la migración irregular")
    assert not mentions_target("El presidente inauguró una carretera")


def test_aggregate_target_only_uses_target_chunks_and_falls_back():
    chunks = pd.DataFrame({
        "article_id": ["a", "a", "b", "b"],
        "n_tokens": [10, 10, 10, 10],
        "mentions_target": [True, False, False, False],
        "p_negativo": [0.1, 0.9, 0.9, 0.9],
        "p_neutro": [0.1, 0.05, 0.05, 0.05],
        "p_positivo": [0.8, 0.05, 0.05, 0.05],
    })
    allc = aggregate_articles(chunks).set_index("article_id")
    tgt = aggregate_articles(chunks, target_only=True).set_index("article_id")
    assert allc.loc["a", "label"] == "negativo"          # promedio de ambos fragmentos
    assert tgt.loc["a", "label"] == "positivo"           # solo el fragmento sobre migrantes
    assert not tgt.loc["a", "fallback_all"]
    assert tgt.loc["b", "fallback_all"] and tgt.loc["b", "label"] == "negativo"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    np.random.seed(0)
