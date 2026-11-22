# text_utils.py
# Preprocesamiento ÚNICO compartido entre entrenamiento y la app.
# Es idéntico a preprocess_doc / basic_clean de pre_processing_2_part.py.
# Si cambias algo aquí, hay que regenerar texto_procesado y reentrenar.

import re

import spacy

URL_PATTERN = re.compile(r"https?://\S+|www\.\S+")
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "]+",
    flags=re.UNICODE,
)

ENGLISH_WORDS = {
    "the", "and", "for", "with", "from", "that", "this", "these", "those",
    "will", "would", "have", "has", "had", "been", "being", "are", "is",
    "was", "were", "of", "to", "in", "on", "at", "by", "about", "into",
    "new", "time", "news", "after", "before", "over", "under",
    "it", "its", "they", "their", "them", "he", "she", "his", "her",
    "you", "your", "we", "our", "us", "who", "what", "when", "where",
    "why", "how", "can", "could", "may", "might", "said", "says",
}

_nlp = None


def get_nlp():
    """Carga spaCy una sola vez (lazy)."""
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("es_core_news_lg", disable=["parser"])
    return _nlp


def basic_clean(text):
    text = str(text)
    text = URL_PATTERN.sub(" ", text)
    text = EMOJI_PATTERN.sub(" ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def preprocess_doc(text):
    text = basic_clean(text)
    doc = get_nlp()(text)

    tokens = []

    for token in doc:
        if token.is_space:
            continue
        if token.is_punct:
            continue
        if token.like_num:
            continue
        if token.is_stop:
            continue
        if token.pos_ == "PROPN":
            continue

        lemma = token.lemma_.lower().strip()

        if not lemma:
            continue
        if len(lemma) < 3:
            continue
        if not lemma.isalpha():
            continue
        if lemma in ENGLISH_WORDS:
            continue

        tokens.append(lemma)

    return " ".join(tokens)