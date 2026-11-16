"""Cálculo del sesgo cultural (Colombia vs. México) a partir de los encuadres.

La hipótesis del proyecto es que la prensa colombiana tiende a encuadrar la
migración venezolana desde la seguridad y la institucionalidad, mientras que la
prensa mexicana tiende a encuadrarla desde el tránsito y la economía. Este
módulo traduce las probabilidades de los 7 encuadres a dos puntajes de afinidad
(0-100) y a una etiqueta legible para el dashboard.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..engine.labels import FRAMES

# Pesos de la hipótesis: qué encuadres definen cada lente.
COLOMBIA_WEIGHTS = {
    "seguridad": 0.55,
    "politica_migratoria": 0.25,
    "acceso_servicios": 0.20,
}
MEXICO_WEIGHTS = {
    "empleo_economia": 0.50,
    "transito_migratorio": 0.30,
    "integracion_social": 0.20,
}

# Léxico de resaltado: término -> (bias_type, peso). Se puede completar desde
# ``app/resources/lexicon.json`` (clave "bias_terms").
BiasTerm = tuple[str, float]
BUILTIN_BIAS_TERMS: dict[str, tuple[str, float]] = {
    "inseguridad": ("colombia", 4.2),
    "delincuencia": ("colombia", 4.5),
    "crimen": ("colombia", 4.0),
    "tren de aragua": ("colombia", 5.0),
    "atracos": ("colombia", 3.8),
    "homicidios": ("colombia", 4.0),
    "captura": ("colombia", 3.2),
    "robo": ("colombia", 3.4),
    "policía": ("colombia", 2.5),
    "operativo": ("colombia", 2.8),
    "frontera": ("mexico", 3.2),
    "darién": ("colombia", 4.5),
    "tapachula": ("mexico", 4.8),
    "chiapas": ("mexico", 4.2),
    "cúcuta": ("colombia", 4.2),
    "caminantes": ("colombia", 3.8),
    "albergues": ("mexico", 3.5),
    "estados unidos": ("mexico", 3.4),
    "trabajo": ("mexico", 3.5),
    "empleo": ("mexico", 3.8),
    "oportunidades": ("positive", 3.5),
    "mano de obra": ("mexico", 4.0),
    "fuerza laboral": ("mexico", 4.2),
    "economía": ("mexico", 3.0),
    "productividad": ("positive", 3.6),
    "emprendimiento": ("positive", 3.7),
    "remesas": ("mexico", 3.2),
    "regularización": ("positive", 4.4),
    "estatuto temporal": ("colombia", 4.9),
    "xenofobia": ("negative", 4.5),
    "discriminación": ("negative", 4.0),
    "rechazo": ("negative", 3.8),
    "derechos humanos": ("positive", 4.0),
    "acnur": ("positive", 4.2),
    "niñez": ("positive", 3.8),
    "vulnerabilidad": ("negative", 3.6),
}

_REQUIRED_BUCKETS = set(COLOMBIA_WEIGHTS) | set(MEXICO_WEIGHTS)


def load_bias_terms(lexicon_path: Path | str | None) -> dict[str, tuple[str, float]]:
    terms = dict(BUILTIN_BIAS_TERMS)
    if not lexicon_path:
        return terms
    path = Path(lexicon_path)
    if not path.exists():
        return terms
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return terms
    bias_terms = raw.get("bias_terms") if isinstance(raw, dict) else None
    if isinstance(bias_terms, dict):
        for term, value in bias_terms.items():
            if isinstance(value, dict):
                bias_type = value.get("bias_type")
                weight = value.get("weight")
                if isinstance(bias_type, str) and weight is not None:
                    terms[str(term).lower()] = (bias_type, float(weight))
    return terms


def compute_alignment(frames: dict[str, float]) -> tuple[float, float]:
    """Devuelve (score_colombia, score_mexico) en escala 0-100."""
    colombia = 100.0 * sum(
        weight * float(frames.get(frame_id, 0.0))
        for frame_id, weight in COLOMBIA_WEIGHTS.items()
    )
    mexico = 100.0 * sum(
        weight * float(frames.get(frame_id, 0.0))
        for frame_id, weight in MEXICO_WEIGHTS.items()
    )
    return round(min(100.0, max(0.0, colombia)), 1), round(
        min(100.0, max(0.0, mexico)), 1
    )


def classify_bias(
    frames: dict[str, float],
    text: str,
    bias_terms: dict[str, tuple[str, float]] | None = None,
) -> dict:
    """Construye el objeto ``culturalBias`` del contrato del frontend."""
    terms = bias_terms or BUILTIN_BIAS_TERMS
    colombia_score, mexico_score = compute_alignment(frames)
    dominant = max(frames, key=frames.get) if frames else "otros"
    dominant_meta = FRAMES.get(dominant, FRAMES["otros"])

    if colombia_score >= mexico_score + 8:
        detected = "Colombia (Enfoque Punitivo / Seguridad)"
        reasoning = (
            f"Los encuadres dominantes ({dominant_meta['label'].lower()}) alinean "
            "el texto con el patrón mediático colombiano: seguridad ciudadana, "
            "orden público y presión institucional."
        )
    elif mexico_score >= colombia_score + 8:
        detected = "México (Enfoque Laboral / Tránsito)"
        reasoning = (
            f"Los encuadres dominantes ({dominant_meta['label'].lower()}) alinean "
            "el texto con el patrón mediático mexicano: migración en tránsito y "
            "aporte económico/laboral."
        )
    else:
        detected = "Neutro / Institucional"
        reasoning = (
            "La cobertura equilibra factores institucionales, de tránsito y de "
            "integración sin una inclinación marcada hacia la seguridad ni hacia "
            "la instrumentalización laboral."
        )

    lowered = text.lower()
    highlights = []
    for term, (bias_type, weight) in terms.items():
        if term in lowered:
            highlights.append(
                {"term": term, "bias_type": bias_type, "weight": weight}
            )
    highlights.sort(key=lambda item: item["weight"], reverse=True)

    return {
        "detected_bias": detected,
        "colombia_alignment_score": colombia_score,
        "mexico_alignment_score": mexico_score,
        "reasoning": reasoning,
        "highlighted_terms": highlights[:8],
    }
