# app_distilbert.py
#
# Interfaz para el modelo multitarea (sentimiento + encuadres) entrenado con
# train_cv.py / train_multitask.py. Debe estar en la misma carpeta que
# text_utils.py y models/.
#
# Uso (desde la raíz del proyecto, con el entorno .venv_gpu activo):
#     python modelling/app_distilbert.py

import json
from pathlib import Path

import gradio as gr
import numpy as np
import torch
import torch.nn as nn
from transformers import AutoConfig, AutoModel, AutoTokenizer

import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELLING_DIR = PROJECT_ROOT / "modelling"

sys.path.insert(0, str(MODELLING_DIR))
from text_utils import basic_clean

MODEL_DIR = MODELLING_DIR / "models" / "multitask_beto_headtail"

# ==========================================================
# CONFIG  (mantener igual que en el entrenamiento)
# ==========================================================

MODEL_NAME = "dccuchile/bert-base-spanish-wwm-cased"
MAX_LEN = 512


DEFAULT_THRESHOLD = 0.5
MIN_WORDS = 30

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

ENCUADRES = [
    "Acceso_a_servicios",
    "Empleo_y_economía",
    "Integración_social",
    "Otros",
    "Politica_migratoria",
    "Seguridad",
    "Transito_migratorio",
]

# ==========================================================
# ARCHIVOS DEL MODELO
# ==========================================================

for name in ("model.pt", "sentiment_classes.json"):
    if not (MODEL_DIR / name).exists():
        raise FileNotFoundError(
            f"Falta {MODEL_DIR / name}. Entrena primero el modelo "
            f"(train_cv.py con TRAIN_FINAL=True, o train_multitask.py)."
        )

with open(MODEL_DIR / "sentiment_classes.json", "r", encoding="utf-8") as f:
    SENTIMIENTOS = json.load(f)

thr_path = MODEL_DIR / "thresholds.json"

if thr_path.exists():
    with open(thr_path, "r", encoding="utf-8") as f:
        _thr = json.load(f)
    THRESHOLDS = {n: float(_thr.get(n, DEFAULT_THRESHOLD)) for n in ENCUADRES}
else:
    THRESHOLDS = {n: DEFAULT_THRESHOLD for n in ENCUADRES}

# ==========================================================
# MODELO (idéntico al del entrenamiento)
# ==========================================================

class MultiTaskBERT(nn.Module):

    def __init__(self, config, num_sentiment_classes, num_labels):
        super().__init__()

        # solo la arquitectura: los pesos vienen de model.pt
        self.encoder = AutoModel.from_config(config)
        hidden_size = self.encoder.config.hidden_size

        self.dropout = nn.Dropout(0.2)
        self.sentiment_head = nn.Linear(hidden_size, num_sentiment_classes)
        self.multilabel_head = nn.Linear(hidden_size, num_labels)

    def forward(self, input_ids, attention_mask):
        outputs = self.encoder(
            input_ids=input_ids, attention_mask=attention_mask
        )
        cls_embedding = self.dropout(outputs.last_hidden_state[:, 0])

        return (
            self.sentiment_head(cls_embedding),
            self.multilabel_head(cls_embedding),
        )


print(f"Dispositivo: {DEVICE}")
print("Cargando tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR))

print("Construyendo modelo...")
config = AutoConfig.from_pretrained(MODEL_NAME)
model = MultiTaskBERT(config, len(SENTIMIENTOS), len(ENCUADRES))

model.load_state_dict(
    torch.load(MODEL_DIR / "model.pt", map_location=DEVICE, weights_only=True)
)
model.to(DEVICE)
model.eval()

print("Modelo cargado.")
print("Umbrales:", THRESHOLDS)

# ==========================================================
# PREDICCIÓN
# ==========================================================

@torch.no_grad()
def predict(text):
    encoded = tokenizer(
        text,
        truncation=True,
        max_length=MAX_LEN,
        return_tensors="pt",
    )

    s_logits, m_logits = model(
        encoded["input_ids"].to(DEVICE),
        encoded["attention_mask"].to(DEVICE),
    )

    s_probs = torch.softmax(s_logits, dim=-1)[0].cpu().numpy()
    m_probs = torch.sigmoid(m_logits)[0].cpu().numpy()

    return s_probs, m_probs


def count_tokens(text):
    """Tokens que tendría el texto completo (sin truncar)."""
    return len(
        tokenizer(text, truncation=False, verbose=False)["input_ids"]
    )


def analizar(texto):
    texto = (texto or "").strip()

    if not texto:
        return {}, [], "Pega el texto de una noticia."

    limpio = basic_clean(texto)
    n_words = len(limpio.split())

    if n_words == 0:
        return {}, [], "El texto quedó vacío tras la limpieza."

    s_probs, m_probs = predict(limpio)

    # ---- sentimiento ----
    sentimiento = {
        nombre: float(p) for nombre, p in zip(SENTIMIENTOS, s_probs)
    }

    # ---- encuadres ----
    filas = []
    for nombre, prob in zip(ENCUADRES, m_probs):
        umbral = THRESHOLDS[nombre]
        filas.append(
            [
                nombre,
                round(float(prob) * 100, 1),
                round(umbral * 100, 0),
                "✅" if prob >= umbral else "—",
            ]
        )

    filas.sort(key=lambda r: r[1], reverse=True)

    # ---- avisos ----
    avisos = []

    full_len = count_tokens(limpio)
    if full_len > MAX_LEN:
        leido = MAX_LEN / full_len * 100
        avisos.append(
            f"⚠️ El texto tiene {full_len} tokens y el modelo solo lee los "
            f"primeros {MAX_LEN} (≈{leido:.0f}% del texto)."
        )
    else:
        avisos.append(f"El modelo leyó el texto completo ({full_len} tokens).")

    if n_words < MIN_WORDS:
        avisos.append(
            f"⚠️ Texto muy corto ({n_words} palabras): el resultado puede no "
            f"ser fiable. El modelo se entrenó con noticias completas."
        )

    return sentimiento, filas, "\n\n".join(avisos)


# ==========================================================
# UI
# ==========================================================

with gr.Blocks(title="Detector de Migración Venezolana") as demo:

    gr.Markdown(
        "# Detector de Migración Venezolana\n"
        "Pega el **cuerpo completo** de una noticia para estimar su "
        "sentimiento y sus encuadres temáticos."
    )

    texto = gr.Textbox(
        lines=14,
        label="Texto de la noticia",
        placeholder="Pega aquí el cuerpo de la noticia...",
    )

    boton = gr.Button("Analizar", variant="primary")

    with gr.Row():
        salida_sent = gr.Label(label="Sentimiento", num_top_classes=3)

        salida_enc = gr.Dataframe(
            headers=["Encuadre", "Probabilidad (%)", "Umbral (%)", "Detectado"],
            datatype=["str", "number", "number", "str"],
            label="Encuadres",
            interactive=False,
        )

    salida_info = gr.Markdown()

    boton.click(
        fn=analizar,
        inputs=texto,
        outputs=[salida_sent, salida_enc, salida_info],
    )

if __name__ == "__main__":
    demo.launch()