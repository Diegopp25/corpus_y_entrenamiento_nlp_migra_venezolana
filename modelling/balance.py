# balance.py

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.utils import resample
from sklearn.utils.class_weight import compute_class_weight

# ==========================================================
# CONFIG
# ==========================================================

INPUT_FILE = "data/dataset_preprocessed.csv"
OUTPUT_FILE = "data/dataset_balanced.csv"

SENTIMENT_COLUMN = "sentimiento"

# columnas multilabel binarias
MULTILABEL_COLUMNS = [
    "Acceso_a_servicios",
    "Empleo_y_economía",
    "Integración_social",
    "Otros",
    "Politica_migratoria",
    "Seguridad",
    "Transito_migratorio",
]

RANDOM_STATE = 66

# ==========================================================
# BALANCEO MULTICLASE
# ==========================================================

df = pd.read_csv(INPUT_FILE)

print("\nDistribución original:")
print(df[SENTIMENT_COLUMN].value_counts())

max_class_size = df[SENTIMENT_COLUMN].value_counts().max()

balanced_parts = []

for sentiment in df[SENTIMENT_COLUMN].unique():

    subset = df[df[SENTIMENT_COLUMN] == sentiment]

    balanced_subset = resample(
        subset,
        replace=True,
        n_samples=max_class_size,
        random_state=RANDOM_STATE,
    )

    balanced_parts.append(balanced_subset)

df_balanced = pd.concat(
    balanced_parts,
    ignore_index=True
)

df_balanced = df_balanced.sample(
    frac=1,
    random_state=RANDOM_STATE
).reset_index(drop=True)

print("\nDistribución balanceada:")
print(df_balanced[SENTIMENT_COLUMN].value_counts())

# ==========================================================
# PESOS MULTICLASE
# ==========================================================

sentiment_classes = np.sort(
    df_balanced[SENTIMENT_COLUMN].unique()
)

sentiment_weights = compute_class_weight(
    class_weight="balanced",
    classes=sentiment_classes,
    y=df_balanced[SENTIMENT_COLUMN]
)

weights_sentiment = {
    cls: float(weight)
    for cls, weight in zip(
        sentiment_classes,
        sentiment_weights
    )
}

print("\nPesos sentimiento:")
print(weights_sentiment)

# ==========================================================
# POS_WEIGHT MULTILABEL
# ==========================================================

weights_multilabel = {}

for col in MULTILABEL_COLUMNS:

    positives = df_balanced[col].sum()
    negatives = len(df_balanced) - positives

    pos_weight = negatives / max(positives, 1)

    weights_multilabel[col] = float(pos_weight)

print("\nPesos multilabel:")
print(weights_multilabel)

# ==========================================================
# GUARDAR
# ==========================================================

Path(OUTPUT_FILE).parent.mkdir(
    parents=True,
    exist_ok=True
)

df_balanced.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8-sig"
)

print(f"\nDataset guardado en: {OUTPUT_FILE}")