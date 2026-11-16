import json
import sys
from pathlib import Path

import gradio as gr
import numpy as np
import torch
import torch.nn as nn
from transformers import AutoModel, AutoTokenizer

# ==========================================================
# CONFIG
# ==========================================================

MODEL_NAME = "dccuchile/bert-base-spanish-wwm-cased"

BASE_DIR = Path(__file__).resolve().parent
TRANSFORMATION_DIR = BASE_DIR.parent / "Transformation"
MODEL_DIR = TRANSFORMATION_DIR / "models" / "multitask_beto"

# mismo preprocesamiento que el entrenamiento
sys.path.insert(0, str(TRANSFORMATION_DIR))
from text_utils import get_nlp, preprocess_doc  # noqa: E402

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

MAX_LEN = 256
THRESHOLD = 0.5
MIN_TOKENS = 15   # por debajo, el texto procesado es demasiado corto

ENCUADRES = [
    "Acceso_a_servicios",
    "Empleo_y_economía",
    "Integración_social",
    "Otros",
    "Politica_migratoria",
    "Seguridad",
    "Transito_migratorio",
]

with open(MODEL_DIR / "sentiment_classes.json", "r", encoding="utf-8") as f:
    SENTIMIENTOS = json.load(f)

# umbral por encuadre (lo genera train_multitask.py); si no existe, usa THRESHOLD
THRESHOLDS_PATH = MODEL_DIR / "thresholds.json"

if THRESHOLDS_PATH.exists():
    with open(THRESHOLDS_PATH, "r", encoding="utf-8") as f:
        _thr = json.load(f)
    THRESHOLDS = {n: float(_thr.get(n, THRESHOLD)) for n in ENCUADRES}
else:
    THRESHOLDS = {n: THRESHOLD for n in ENCUADRES}

print("Umbrales:", THRESHOLDS)

# ==========================================================
# MODELO (idéntico al de entrenamiento)
# ==========================================================

class MultiTaskBERT(nn.Module):

    def __init__(self, model_name, num_sentiment_classes, num_labels):
        super().__init__()

        self.encoder = AutoModel.from_pretrained(model_name)
        hidden = self.encoder.config.hidden_size

        self.dropout = nn.Dropout(0.2)
        self.sentiment_head = nn.Linear(hidden, num_sentiment_classes)
        self.multilabel_head = nn.Linear(hidden, num_labels)

    def forward(self, input_ids, attention_mask):
        outputs = self.encoder(
            input_ids=input_ids, attention_mask=attention_mask
        )
        cls = self.dropout(outputs.last_hidden_state[:, 0])

        return self.sentiment_head(cls), self.multilabel_head(cls)


# ==========================================================
# CARGA
# ==========================================================

print("Cargando spaCy...")
get_nlp()

print("Cargando tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR))

print("Construyendo modelo...")
model = MultiTaskBERT(MODEL_NAME, len(SENTIMIENTOS), len(ENCUADRES))
model.load_state_dict(
    torch.load(MODEL_DIR / "model.pt", map_location=DEVICE)
)
model.to(DEVICE)
model.eval()

print("Modelo cargado correctamente.")

# ==========================================================
# PREDICT
# ==========================================================

@torch.no_grad()
def predict(processed_text):
    encoded = tokenizer(
        processed_text,
        truncation=True,
        max_length=MAX_LEN,
        return_tensors="pt",
    )

    sentiment_logits, multilabel_logits = model(
        encoded["input_ids"].to(DEVICE),
        encoded["attention_mask"].to(DEVICE),
    )

    sentiment_probs = torch.softmax(sentiment_logits, dim=-1)[0].cpu().numpy()
    multilabel_probs = torch.sigmoid(multilabel_logits)[0].cpu().numpy()

    return sentiment_probs, multilabel_probs


# ==========================================================
# ANALISIS
# ==========================================================

def analizar(texto):
    texto = (texto or "").strip()

    if not texto:
        msg = "Escribe una noticia."
        return msg, msg, ""

    processed = preprocess_doc(texto)
    n_tokens = len(processed.split())

    if n_tokens == 0:
        msg = "El texto quedó vacío tras el preprocesamiento. Pega el cuerpo completo de la noticia."
        return msg, msg, ""

    aviso = ""
    if n_tokens < MIN_TOKENS:
        aviso = (
            f"<p>⚠️ Texto muy corto tras el preprocesamiento "
            f"({n_tokens} palabras). El resultado puede no ser fiable.</p>"
        )

    sentiment_probs, multilabel_probs = predict(processed)

    ganador = SENTIMIENTOS[int(np.argmax(sentiment_probs))]

    sentimiento_html = aviso + f"<h3>{ganador}</h3>"
    for nombre, prob in zip(SENTIMIENTOS, sentiment_probs):
        sentimiento_html += f"<p>{nombre}: {prob * 100:.2f}%</p>"

    pares = sorted(
        zip(ENCUADRES, multilabel_probs), key=lambda x: x[1], reverse=True
    )

    encuadre_html = ""
    for nombre, prob in pares:
        umbral = THRESHOLDS[nombre]
        estado = "✅" if prob >= umbral else "❌"
        encuadre_html += (
            f"<p>{estado} {nombre}: {prob * 100:.2f}% "
            f"(umbral {umbral:.2f})</p>"
        )

    return sentimiento_html, encuadre_html, processed


# ==========================================================
# UI
# ==========================================================

with gr.Blocks() as demo:

    gr.Markdown("# Detector de Migración Venezolana")

    texto = gr.Textbox(lines=12, label="Texto de la noticia (cuerpo completo)")
    boton = gr.Button("Analizar")

    salida_sent = gr.HTML()
    salida_labels = gr.HTML()

    salida_proc = gr.Textbox(
        label="Texto procesado que ve el modelo",
        lines=4,
        interactive=False,
    )

    boton.click(
        fn=analizar,
        inputs=texto,
        outputs=[salida_sent, salida_labels, salida_proc],
    )

if __name__ == "__main__":
    demo.launch()