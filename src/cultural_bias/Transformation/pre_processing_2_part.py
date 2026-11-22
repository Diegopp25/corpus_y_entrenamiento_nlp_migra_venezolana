# preprocess.py

import re
import pandas as pd
import spacy
from pathlib import Path

# ==========================================================
# CONFIG
# ==========================================================

# Raíz del proyecto
ROOT_DIR = Path(__file__).resolve().parents[1]

# Archivos de entrada y salida
INPUT_FILE = ROOT_DIR / "data" / "dataset_migracion_venezolana_labeled.csv"
OUTPUT_FILE = ROOT_DIR / "data" / "dataset_preprocessed.csv"

TEXT_COLUMN = "Cuerpo"

# ==========================================================
# SPACY
# ==========================================================

nlp = spacy.load(
    "es_core_news_lg",
    disable=["parser"]
)

# ==========================================================
# REGEX
# ==========================================================

URL_PATTERN = re.compile(r"https?://\S+|www\.\S+")
EMOJI_PATTERN = re.compile(
    "["
    u"\U0001F600-\U0001F64F"
    u"\U0001F300-\U0001F5FF"
    u"\U0001F680-\U0001F6FF"
    u"\U0001F1E0-\U0001F1FF"
    "]+",
    flags=re.UNICODE
)

# ==========================================================
# DICCIONARIO INGLÉS
# ==========================================================

ENGLISH_WORDS = {
    "the","and","for","with","from","that","this","these","those",
    "will","would","have","has","had","been","being","are","is",
    "was","were","of","to","in","on","at","by","about","into",
    "new","time","news","after","before","over","under",
    "it","its","they","their","them","he","she","his","her",
    "you","your","we","our","us","who","what","when","where",
    "why","how","can","could","may","might","said","says"
}

# ==========================================================
# LIMPIEZA PREVIA
# ==========================================================

def basic_clean(text):

    text = str(text)

    text = URL_PATTERN.sub(" ", text)

    text = EMOJI_PATTERN.sub(" ", text)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ==========================================================
# PREPROCESS SPACY
# ==========================================================

def preprocess_doc(text):

    text = basic_clean(text)

    doc = nlp(text)

    tokens = []

    for token in doc:

        # espacios
        if token.is_space:
            continue

        # puntuación
        if token.is_punct:
            continue

        # números
        if token.like_num:
            continue

        # stopwords
        if token.is_stop:
            continue

        # nombres propios
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


# ==========================================================
# MAIN
# ==========================================================

def main():

    print("Leyendo dataset...")

    df = pd.read_csv(INPUT_FILE)

    print(f"Registros: {len(df):,}")

    df["texto_procesado"] = (
        df[TEXT_COLUMN]
        .fillna("")
        .astype(str)
        .apply(preprocess_doc)
    )

    # eliminar vacíos
    df = df[df["texto_procesado"].str.len() > 0]

    print(f"Registros finales: {len(df):,}")

    Path(OUTPUT_FILE).parent.mkdir(
        parents=True,
        exist_ok=True
    )

    df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    print(f"Guardado en: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()