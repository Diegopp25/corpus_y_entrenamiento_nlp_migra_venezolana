import sys
from pathlib import Path
from types import ModuleType

MODEL_DIR = Path(__file__).resolve().parents[1] / "modelling" / "beto"
sys.path.insert(0, str(MODEL_DIR))

import preprocess


def test_clean_text_removes_stopwords_short_and_english_tokens(monkeypatch):
    class FakeToken:
        def __init__(self, text, is_stop=False):
            self.text = text
            self.is_stop = is_stop
            self.is_space = False
            self.is_punct = False
            self.like_num = False
            self.is_alpha = text.isalpha()

    class FakeNlp:
        def __call__(self, text):
            return [
                FakeToken("la", is_stop=True),
                FakeToken("de"),
                FakeToken("migration"),
                FakeToken("migración"),
            ]

    monkeypatch.setattr(preprocess, "_nlp", FakeNlp())
    monkeypatch.setattr(
        preprocess,
        "is_english_word",
        lambda word: word == "migration",
    )

    assert preprocess.clean_text("Texto original") == "migración"


def test_is_english_word_compares_english_and_spanish_frequency(monkeypatch):
    frequencies = {
        ("migration", "en"): 4.5,
        ("migration", "es"): 0.0,
        ("migración", "en"): 0.0,
        ("migración", "es"): 4.0,
    }

    fake_wordfreq = ModuleType("wordfreq")
    fake_wordfreq.zipf_frequency = lambda word, language: frequencies[(word, language)]
    monkeypatch.setitem(sys.modules, "wordfreq", fake_wordfreq)
    preprocess.is_english_word.cache_clear()

    assert preprocess.is_english_word("migration")
    assert not preprocess.is_english_word("migración")
