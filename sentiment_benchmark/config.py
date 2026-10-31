"""Configuración central: rutas, clases y registro de modelos."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT = PACKAGE_DIR.parent

DATA_CSV = ROOT / "Data" / "dataset_migracion_venezolana.csv"
RESULTS_DIR = PACKAGE_DIR / "results"

# Clases canónicas: todos los modelos se convierten a este orden.
CLASSES = ["negativo", "neutro", "positivo"]
PROB_COLS = [f"p_{c}" for c in CLASSES]

# Tope de tokens por fragmento (además del límite propio de cada modelo).
CHUNK_TOKEN_CAP = 256

# Colores: negativo (cálido), neutro (gris), positivo (frío). Par divergente.
CLASS_COLORS = {"negativo": "#B5532A", "neutro": "#9AA0A6", "positivo": "#2A6F97"}


@dataclass(frozen=True)
class ModelSpec:
    key: str
    hf_id: str
    kind: str  # "classifier" (cabeza de clasificación) | "nli" (zero-shot por inferencia)
    description: str
    notes: str = ""
    # Solo si la etiqueta del modelo no se reconoce sola: {etiqueta_original: clase_canónica}
    label_map: dict = field(default_factory=dict)
    # Solo modelos NLI: hipótesis propias por clase (si vacío, se usa NLI_HYPOTHESES)
    hypotheses: dict = field(default_factory=dict)
    # Tokenizador alternativo si el del propio modelo no carga (mismo vocabulario)
    tokenizer_id: str = ""


# Hipótesis para el modelo NLI zero-shot sobre el tono GENERAL del texto (editables).
NLI_HYPOTHESES = {
    "negativo": "El tono de este texto es negativo.",
    "neutro": "El tono de este texto es neutro.",
    "positivo": "El tono de este texto es positivo.",
}

# Hipótesis dirigidas: tono HACIA los migrantes venezolanos (lo que se etiqueta a mano).
NLI_HYPOTHESES_TARGET = {
    "negativo": "El texto presenta a los migrantes venezolanos de forma negativa.",
    "neutro": "El texto presenta a los migrantes venezolanos de forma neutral.",
    "positivo": "El texto presenta a los migrantes venezolanos de forma positiva.",
}

MODELS: dict[str, ModelSpec] = {
    "robertuito": ModelSpec(
        key="robertuito",
        hf_id="pysentimiento/robertuito-sentiment-analysis",
        kind="classifier",
        description="RoBERTuito afinado en TASS 2020 (~5k tuits en español). Etiquetas NEG/NEU/POS.",
        notes="Ventana de ~128 tokens (max_position_embeddings=130). Entrenado en tuits.",
    ),
    "beto": ModelSpec(
        key="beto",
        hf_id="finiteautomata/beto-sentiment-analysis",
        kind="classifier",
        description="BETO afinado en TASS 2020 (tuits). Etiquetas NEG/NEU/POS.",
        notes="Su ficha avisa que será retirado; si falla la descarga se omite.",
    ),
    "xlmr_twitter": ModelSpec(
        key="xlmr_twitter",
        hf_id="cardiffnlp/twitter-xlm-roberta-base-sentiment",
        kind="classifier",
        description="XLM-R base preentrenado con ~198M tuits y afinado en sentimiento en 8 idiomas (incl. español).",
        notes="Multilingüe; dominio tuits. Su repo solo trae un tokenizador SentencePiece que a veces no se convierte; si falla se usa el de xlm-roberta-base (mismo vocabulario).",
        tokenizer_id="FacebookAI/xlm-roberta-base",
    ),
    "distil_multi": ModelSpec(
        key="distil_multi",
        hf_id="lxyuan/distilbert-base-multilingual-cased-sentiments-student",
        kind="classifier",
        description="DistilBERT multilingüe destilado de un clasificador zero-shot mDeBERTa-NLI "
        "(dataset tyqiangz/multilingual-sentiments).",
        notes="Etiquetas generadas por el modelo maestro, no por humanos.",
    ),
    "nlptown_stars": ModelSpec(
        key="nlptown_stars",
        hf_id="nlptown/bert-base-multilingual-uncased-sentiment",
        kind="classifier",
        description="BERT multilingüe que predice 1-5 estrellas (reseñas de productos; ~50k en español).",
        notes="Se agrupa: 1-2 estrellas = negativo, 3 = neutro, 4-5 = positivo. Dominio reseñas.",
    ),
    "roberta_bne_imdb": ModelSpec(
        key="roberta_bne_imdb",
        hf_id="edumunozsala/roberta_bne_sentiment_analysis_es",
        kind="classifier",
        description="RoBERTa-BNE (MarIA base) afinado con reseñas de cine IMDb en español (binario).",
        notes="Solo Negativo/Positivo: nunca predice 'neutro'. Dominio reseñas de cine.",
    ),
    "mdeberta_nli": ModelSpec(
        key="mdeberta_nli",
        hf_id="MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7",
        kind="nli",
        description="mDeBERTa-v3 afinado en NLI multilingüe, usado como clasificador zero-shot "
        "(probabilidad de 'entailment' de una hipótesis por clase).",
        notes="No fue entrenado en sentimiento; tres pasadas por fragmento (más lento).",
    ),
    "mdeberta_nli_target": ModelSpec(
        key="mdeberta_nli_target",
        hf_id="MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7",
        kind="nli",
        description="Mismo mDeBERTa-NLI, pero con hipótesis sobre cómo se presenta a los migrantes "
        "venezolanos. Es el único candidato que puede expresar el tono HACIA el grupo.",
        notes="Mismo modelo que mdeberta_nli: solo cambia la hipótesis. Editar NLI_HYPOTHESES_TARGET.",
        hypotheses=NLI_HYPOTHESES_TARGET,
    ),
}
