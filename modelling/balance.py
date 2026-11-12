"""Muestra los pesos de clase calculados sobre el dataset sin duplicar filas.

El entrenamiento calcula estos pesos de nuevo usando solo cada partición train.
"""

import pandas as pd

# ==========================================================
# CONFIG
# ==========================================================

INPUT_FILE = "data/dataset_preprocessed.csv"

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

# ==========================================================
# PESOS MULTICLASE Y MULTILABEL
# ==========================================================

df = pd.read_csv(INPUT_FILE)

sentiment_counts = df[SENTIMENT_COLUMN].value_counts()
weights_sentiment = (
    len(df) / (len(sentiment_counts) * sentiment_counts)
).to_dict()

print("\nPesos sentimiento:")
print(weights_sentiment)

# ==========================================================
# POS_WEIGHT MULTILABEL
# ==========================================================

weights_multilabel = {}

for col in MULTILABEL_COLUMNS:

    positives = df[col].sum()
    negatives = len(df) - positives
    pos_weight = negatives / positives if positives and negatives else 1.0

    weights_multilabel[col] = float(pos_weight)

print("\nPesos multilabel:")
print(weights_multilabel)