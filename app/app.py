"""Dashboard y API de análisis de noticias con BETO."""

import html
import math
import sys
import threading
from pathlib import Path

import gradio as gr
import pandas as pd
import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BETO_DIR = PROJECT_ROOT / "modelling" / "beto"
MODEL_PATH = BETO_DIR / "models_beto" / "beto_multitask.pt"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(BETO_DIR))

from extraction.extraction_la_cronica_mexico import extraer_cronica_mexico  # noqa: E402
from infer import load_model, predict_texts  # noqa: E402

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
MAX_TEXT_LENGTH = 100_000
MAX_SCRAPE_ARTICLES = 30

_classifier = None
_classifier_lock = threading.Lock()
_inference_lock = threading.Lock()


def _get_classifier():
    global _classifier

    if _classifier is None:
        with _classifier_lock:
            if _classifier is None:
                if not MODEL_PATH.is_file():
                    raise FileNotFoundError(
                        f"No se encontró el checkpoint BETO: {MODEL_PATH}"
                    )
                _classifier = load_model(MODEL_PATH, DEVICE)

    return _classifier


def analyze_texts(texts):
    """Analiza una lista de noticias y devuelve predicciones estructuradas."""
    if not texts:
        raise ValueError("Ingresa al menos una noticia para analizar.")

    cleaned_inputs = []
    for index, text in enumerate(texts, start=1):
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"La noticia {index} está vacía.")
        if len(text) > MAX_TEXT_LENGTH:
            raise ValueError(
                f"La noticia {index} supera el máximo de {MAX_TEXT_LENGTH:,} caracteres."
            )
        cleaned_inputs.append(text.strip())

    model, tokenizer, checkpoint = _get_classifier()
    with _inference_lock:
        predictions = predict_texts(
            cleaned_inputs,
            model,
            tokenizer,
            checkpoint,
            DEVICE,
            batch_size=8,
        )

    sentiments = {value: key for key, value in checkpoint["sent_map"].items()}
    labels = checkpoint["label_cols"]
    thresholds = checkpoint["thresholds"]
    results = []

    for text, (_, prediction) in zip(cleaned_inputs, predictions.iterrows()):
        sentiment_scores = {
            name: float(prediction[f"p_{name}"]) for name in sentiments.values()
        }
        label_results = [
            {
                "name": label,
                "probability": float(prediction[f"p_{label}"]),
                "threshold": float(thresholds[label]),
                "detected": bool(prediction[label]),
            }
            for label in labels
        ]
        label_results.sort(key=lambda item: item["probability"], reverse=True)

        results.append(
            {
                "sentiment": str(prediction["sentimiento"]),
                "sentiment_probabilities": sentiment_scores,
                "labels": label_results,
                "word_count": len(text.split()),
                "notice": (
                    "Texto breve: el modelo se entrenó con noticias completas."
                    if len(text.split()) < 30
                    else None
                ),
            }
        )

    return results


def _render_analysis(result):
    sentiment = html.escape(result["sentiment"])
    sentiment_rows = "".join(
        (
            '<div class="score-row">'
            f'<span>{html.escape(name.replace("_", " "))}</span>'
            f'<strong>{score:.1%}</strong></div>'
            '<div class="score-track"><span style="width:'
            f'{max(0, min(100, score * 100)):.1f}%"></span></div>'
        )
        for name, score in result["sentiment_probabilities"].items()
    )
    labels = "".join(
        (
            '<div class="label-card">'
            '<div class="label-heading">'
            f'<span>{html.escape(item["name"].replace("_", " "))}</span>'
            f'<span class="badge {"detected" if item["detected"] else "not-detected"}">'
            f'{"Detectado" if item["detected"] else "No detectado"}</span>'
            '</div><div class="score-track"><span style="width:'
            f'{max(0, min(100, item["probability"] * 100)):.1f}%"></span></div>'
            f'<small>{item["probability"]:.1%} de confianza · umbral {item["threshold"]:.1%}</small>'
            '</div>'
        )
        for item in result["labels"]
    )
    notice = (
        f'<p class="notice">{html.escape(result["notice"])}</p>'
        if result["notice"]
        else ""
    )

    return (
        '<section class="result-panel">'
        '<div class="result-title"><div><span class="eyebrow">CLASE PREDICHA</span>'
        f'<h2>{sentiment}</h2></div><span class="word-count">'
        f'{result["word_count"]} palabras</span></div>'
        f'{notice}<div class="result-columns"><div><h3>Probabilidad por clase</h3>'
        f'{sentiment_rows}</div><div><h3>Encuadres detectados</h3>{labels}</div></div>'
        '</section>'
    )


def analyze_news(text):
    result = analyze_texts([text])[0]
    return _render_analysis(result), result


def _validate_scrape_limit(limit):
    if isinstance(limit, bool) or not isinstance(limit, (int, float)):
        raise ValueError("El límite debe ser un número entero entre 1 y 30.")
    numeric_limit = float(limit)
    if not math.isfinite(numeric_limit) or not numeric_limit.is_integer():
        raise ValueError("El límite debe ser un número entero entre 1 y 30.")
    if not 1 <= numeric_limit <= MAX_SCRAPE_ARTICLES:
        raise ValueError(f"El límite debe estar entre 1 y {MAX_SCRAPE_ARTICLES}.")
    return int(numeric_limit)


def scrape_and_analyze(limit):
    limit = _validate_scrape_limit(limit)
    articles = extraer_cronica_mexico(limite=limit)
    usable = []

    def field_text(article, name):
        value = article.get(name, "")
        return "" if pd.isna(value) else str(value)

    for _, article in articles.iterrows():
        body = article.get("Cuerpo", "")
        if pd.isna(body) or not str(body).strip():
            continue
        usable.append(
            {
                "title": field_text(article, "Titulo"),
                "url": field_text(article, "URL"),
                "date": field_text(article, "Fecha"),
                "text": str(body),
            }
        )

    if not usable:
        return (
            '<div class="empty-state">No se encontraron artículos con texto para analizar. '
            "Intenta de nuevo más tarde.</div>",
            [],
            {"source": "La Crónica de Hoy", "total": 0, "articles": []},
        )

    results = analyze_texts([article["text"] for article in usable])
    rows = []
    response_articles = []

    for article, result in zip(usable, results):
        detected_labels = [
            label["name"] for label in result["labels"] if label["detected"]
        ]
        rows.append(
            [
                article["title"],
                article["date"],
                result["sentiment"],
                ", ".join(detected_labels) or "Sin encuadres sobre el umbral",
                article["url"],
            ]
        )
        response_articles.append(
            {
                "title": article["title"],
                "url": article["url"],
                "date": article["date"],
                "analysis": result,
            }
        )

    sentiment_counts = {}
    for result in results:
        sentiment_counts[result["sentiment"]] = (
            sentiment_counts.get(result["sentiment"], 0) + 1
        )

    summary = (
        '<div class="scrape-summary"><span class="eyebrow">LA CRÓNICA DE HOY</span>'
        f'<h2>{len(rows)} noticias analizadas</h2><p>'
        f'{html.escape(" · ".join(f"{name}: {count}" for name, count in sentiment_counts.items()))}'
        "</p></div>"
    )
    return (
        summary,
        rows,
        {
            "source": "La Crónica de Hoy",
            "total": len(rows),
            "sentiment_counts": sentiment_counts,
            "articles": response_articles,
        },
    )


CSS = """
.gradio-container { max-width: 1180px !important; margin: auto !important; }
body, .gradio-container { background: #f5f7fb !important; color: #172033 !important; }
.hero { background: linear-gradient(120deg,#102a43,#174c66); color: white; padding: 34px 40px; border-radius: 22px; margin: 10px 0 22px; }
.hero h1 { font-size: 32px; margin: 7px 0; color: white; }
.hero p { color: #d3e4ef; margin: 0; }
.eyebrow { color: #78d6c6; font-size: 11px; font-weight: 700; letter-spacing: 1.4px; }
.hero-cards { display: grid; grid-template-columns: repeat(3,1fr); gap: 12px; margin-top: 24px; }
.hero-card { background: #ffffff16; border: 1px solid #ffffff20; padding: 14px 16px; border-radius: 13px; }
.hero-card strong { display: block; font-size: 18px; margin-bottom: 4px; }
.hero-card span { font-size: 12px; color: #d3e4ef; }
.tab-nav button { border-radius: 10px !important; }
.result-panel, .scrape-summary { background: white; border: 1px solid #e6ebf2; border-radius: 18px; padding: 24px; margin-top: 12px; box-shadow: 0 8px 24px #1720330a; }
.result-title { display:flex; align-items:center; justify-content:space-between; }
.result-title h2, .scrape-summary h2 { margin: 5px 0 18px; font-size: 26px; }
.word-count { color: #64748b; font-size: 13px; background:#f1f5f9; padding:7px 11px; border-radius:20px; }
.result-columns { display:grid; grid-template-columns:1fr 1.3fr; gap:30px; }
.result-panel h3 { font-size: 15px; margin: 12px 0 15px; }
.score-row, .label-heading { display:flex; justify-content:space-between; gap:10px; font-size:13px; margin: 10px 0 5px; }
.score-track { height:7px; background:#edf1f6; border-radius:8px; overflow:hidden; }
.score-track span { display:block; height:100%; background:linear-gradient(90deg,#2c8a9e,#48bea8); border-radius:8px; }
.label-card { margin-bottom:15px; }
.label-card small { color:#718096; font-size:11px; display:block; margin-top:5px; }
.badge { border-radius:20px; padding:4px 9px; font-size:10px; white-space:nowrap; }
.detected { color:#087a61; background:#e4f7f1; }
.not-detected { color:#64748b; background:#f1f5f9; }
.notice { background:#fff7e6; border-left:3px solid #f0ad3d; padding:10px 12px; color:#7c5a17; font-size:13px; }
.empty-state { background:white; padding:20px; border-radius:14px; color:#64748b; }
.scrape-summary p { color:#526176; font-size:13px; }
@media (max-width: 700px) { .hero { padding:24px; } .hero h1 {font-size:25px;} .hero-cards,.result-columns {grid-template-columns:1fr;} }
"""

with gr.Blocks(
    title="Cultural Bias | Detector de sesgos",
) as demo:
    gr.HTML(
        '<header class="hero"><span class="eyebrow">CULTURAL BIAS · OBSERVATORIO DE MEDIOS</span>'
        "<h1>Análisis de cobertura migratoria</h1>"
        "<p>Detecta clases de sentimiento y encuadres sobre migración venezolana en noticias.</p>"
        '<div class="hero-cards"><div class="hero-card"><strong>BETO</strong><span>Modelo de análisis multitarea</span></div>'
        '<div class="hero-card"><strong>3 clases</strong><span>Negativo · Neutro · Positivo</span></div>'
        '<div class="hero-card"><strong>5 encuadres</strong><span>Temas detectados con umbrales propios</span></div></div></header>'
    )

    with gr.Tabs():
        with gr.Tab("Analizar noticia"):
            gr.Markdown("### Análisis manual\nPega el cuerpo de una noticia para consultar la clase y los encuadres predichos.")
            news_text = gr.Textbox(
                label="Texto de la noticia",
                placeholder="Pega aquí el texto completo de la noticia…",
                lines=10,
                max_lines=18,
            )
            analyze_button = gr.Button("Analizar noticia", variant="primary")
            analysis_view = gr.HTML()
            with gr.Accordion("Ver respuesta estructurada de la API", open=False):
                analysis_json = gr.JSON(label="Predicción")
            analyze_button.click(
                fn=analyze_news,
                inputs=news_text,
                outputs=[analysis_view, analysis_json],
                api_name="analizar_noticia",
            )

        with gr.Tab("Recolectar de La Crónica"):
            gr.Markdown(
                "### Scraper de La Crónica de Hoy\n"
                "Busca noticias relacionadas con migración venezolana y analiza el texto extraído. "
                "La recolección puede tardar según la respuesta del sitio."
            )
            scrape_limit = gr.Slider(
                minimum=1,
                maximum=MAX_SCRAPE_ARTICLES,
                step=1,
                value=10,
                label="Máximo de artículos por búsqueda",
            )
            scrape_button = gr.Button("Buscar y analizar noticias", variant="primary")
            scrape_summary = gr.HTML()
            scrape_table = gr.Dataframe(
                headers=["Título", "Fecha", "Clase", "Encuadres detectados", "URL"],
                datatype=["str", "str", "str", "str", "str"],
                interactive=False,
                label="Noticias analizadas",
            )
            with gr.Accordion("Ver respuesta estructurada de la API", open=False):
                scrape_json = gr.JSON(label="Resultados")
            scrape_button.click(
                fn=scrape_and_analyze,
                inputs=scrape_limit,
                outputs=[scrape_summary, scrape_table, scrape_json],
                api_name="recolectar_cronica",
            )


if __name__ == "__main__":
    demo.launch(
        css=CSS,
        theme=gr.themes.Soft(primary_hue="teal", neutral_hue="slate"),
    )
