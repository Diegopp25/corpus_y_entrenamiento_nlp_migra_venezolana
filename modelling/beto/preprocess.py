#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""T-01 · Preprocesamiento: constantes, limpieza de texto, carga, folds y DataLoaders.

`prepare_text` es exactamente lo que ve el modelo; infer.py usa la misma función.

Uso (revisión rápida del dataset):
    python preprocess.py
    python preprocess.py --data ruta/al.csv --text_col Cuerpo
"""

import argparse
from collections import Counter
from functools import lru_cache
from pathlib import Path
import re

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader, Dataset

T_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA = T_DIR.parent / "data" / "dataset_migracion_venezolana_labeled.csv"

LABEL_COLS = [
    "Acceso_a_servicios",
    "Empleo_y_economía",
    # "Integración_social",
    # "Otros",
    "Politica_migratoria",
    "Seguridad",
    "Transito_migratorio",
]

SENT_COL = "sentimiento"
SENT2ID = {"Negativo": 0, "Neutro": 1, "Positivo": 2}
ID2SENT = {v: k for k, v in SENT2ID.items()}
MIN_TOKEN_LENGTH = 3

_nlp = None


# =========================================================
# TEXTO
# =========================================================

def clean_text(text):
    text = str(text)
    text = re.sub(r"\s+", " ", text)
    doc = _get_nlp()(text.strip())

    tokens = []
    for token in doc:
        if token.is_space or token.is_stop:
            continue
        if token.is_alpha:
            if (
                len(token.text) < MIN_TOKEN_LENGTH
                or is_english_word(token.text.lower())
            ):
                continue
        tokens.append(token.text)

    return " ".join(tokens)


def _get_nlp():
    global _nlp
    if _nlp is None:
        import spacy

        _nlp = spacy.load("es_core_news_lg", disable=["parser", "ner"])
    return _nlp


@lru_cache(maxsize=50000)
def is_english_word(word):
    from wordfreq import zipf_frequency

    english_frequency = zipf_frequency(word, "en")
    spanish_frequency = zipf_frequency(word, "es")
    return english_frequency > 0 and english_frequency > spanish_frequency


def head_tail(text, head=1500, tail=1500):
    text = str(text)
    if len(text) <= head + tail:
        return text
    return text[:head] + "\n\n" + text[-tail:]


def prepare_text(text):
    return head_tail(clean_text(text))


# =========================================================
# DATOS
# =========================================================

def load_data(data_path, text_col):
    df = pd.read_csv(data_path, encoding="utf-8-sig")

    cols = [text_col] + [SENT_COL] + LABEL_COLS
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas: {missing}")

    df = df.dropna(subset=[text_col, SENT_COL]).copy()

    df[SENT_COL] = df[SENT_COL].astype(str).str.strip().str.capitalize()
    df["sent_id"] = df[SENT_COL].map(SENT2ID).astype(int)

    df[LABEL_COLS] = df[LABEL_COLS].fillna(0).astype(int)

    df["text_prep"] = df[text_col].map(prepare_text)
    df = df[df["text_prep"].str.len() > 0].reset_index(drop=True)

    return df


def describe(df, name):
    s = Counter(df[SENT_COL])
    l = df[LABEL_COLS].sum().astype(int).to_dict()
    print(f"[{name}] n={len(df)} | sentimiento={dict(s)} | labels={l}")


# =========================================================
# PESOS DE PÉRDIDA Y FOLDS
# =========================================================

def compute_loss_weights(train_df):
    sentiment_counts = np.bincount(
        train_df["sent_id"].to_numpy(dtype=int),
        minlength=len(SENT2ID),
    )
    present_classes = sentiment_counts > 0
    sentiment_weights = np.zeros(len(SENT2ID), dtype=np.float32)
    sentiment_weights[present_classes] = (
        len(train_df)
        / (present_classes.sum() * sentiment_counts[present_classes])
    )

    labels = train_df[LABEL_COLS].to_numpy(dtype=np.float64)
    positives = labels.sum(axis=0)
    negatives = len(train_df) - positives
    pos_weights = np.ones(len(LABEL_COLS), dtype=np.float32)
    has_both_classes = (positives > 0) & (negatives > 0)
    pos_weights[has_both_classes] = (
        negatives[has_both_classes] / positives[has_both_classes]
    )

    return sentiment_weights, pos_weights


def build_multilabel_target(df):
    sent_part = pd.get_dummies(df[SENT_COL]).values
    label_part = df[LABEL_COLS].values
    return np.hstack([sent_part, label_part])


def make_splits(df, n_folds, seed):
    """MultilabelStratifiedKFold si iterstrat está instalado; si no, StratifiedKFold por sentimiento."""
    try:
        from iterstrat.ml_stratifiers import MultilabelStratifiedKFold

        X = np.zeros(len(df))
        Y = build_multilabel_target(df)
        splitter = MultilabelStratifiedKFold(n_splits=n_folds, shuffle=True, random_state=seed)
        return list(splitter.split(X, Y))

    except ImportError:
        from sklearn.model_selection import StratifiedKFold

        splitter = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=seed)
        return list(splitter.split(df, df["sent_id"]))


# =========================================================
# DATASET / DATALOADER
# =========================================================

class NewsDataset(Dataset):
    def __init__(self, df, tokenizer, max_len):
        self.texts = df["text_prep"].tolist()
        self.sent = df["sent_id"].values
        self.labels = df[LABEL_COLS].values.astype(np.float32)
        self.tok = tokenizer
        self.max_len = max_len

    def __len__(self):
        return len(self.texts)

    def __getitem__(self, idx):
        enc = self.tok(
            self.texts[idx],
            truncation=True,
            max_length=self.max_len,
            padding=False,
            return_tensors="pt",
        )
        return {
            "input_ids": enc["input_ids"][0],
            "attention_mask": enc["attention_mask"][0],
            "sent": torch.tensor(self.sent[idx], dtype=torch.long),
            "labels": torch.tensor(self.labels[idx], dtype=torch.float),
        }


def collate_fn(batch):
    max_len = max(len(x["input_ids"]) for x in batch)

    ids, masks, sent, labels = [], [], [], []

    for row in batch:
        pad = max_len - len(row["input_ids"])
        ids.append(torch.cat([row["input_ids"], torch.zeros(pad, dtype=torch.long)]))
        masks.append(torch.cat([row["attention_mask"], torch.zeros(pad, dtype=torch.long)]))
        sent.append(row["sent"])
        labels.append(row["labels"])

    return {
        "input_ids": torch.stack(ids),
        "attention_mask": torch.stack(masks),
        "sent": torch.stack(sent),
        "labels": torch.stack(labels),
    }


def make_loader(df, tokenizer, max_len, batch_size, shuffle):
    ds = NewsDataset(df, tokenizer, max_len)
    return DataLoader(
        ds,
        batch_size=batch_size,
        shuffle=shuffle,
        collate_fn=collate_fn,
        pin_memory=True,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Revisión rápida del dataset")
    p.add_argument("--data", default=str(DEFAULT_DATA))
    p.add_argument("--text_col", default="Cuerpo")
    a = p.parse_args()

    describe(load_data(a.data, a.text_col), "dataset completo")
