"""Catálogo de etiquetas compartido por los motores de análisis.

Los modelos BETO guardan sus cabezas como ``LABEL_0..N``; aquí se fija la
correspondencia entre el orden de entrenamiento, el nombre en el modelo y el
identificador que consume el frontend.
"""

from __future__ import annotations

SENTIMENT_LABELS = ["Negativo", "Neutro", "Positivo"]

# Orden con el que se entrenó el modelo de encuadres (7 salidas sigmoid).
FRAME_MODEL_ORDER = [
    "Acceso_a_servicios",
    "Empleo_y_economía",
    "Integración_social",
    "Otros",
    "Politica_migratoria",
    "Seguridad",
    "Transito_migratorio",
]

# frame_id (contrato del frontend) -> metadatos
FRAMES: dict[str, dict] = {
    "acceso_servicios": {
        "label": "Acceso a servicios",
        "model_label": "Acceso_a_servicios",
        "description": "Cobertura orientada a salud, educación, vivienda y asistencia social.",
        "keywords": ["salud", "hospitales", "educación", "vacunación", "atención médica"],
        "bias": "colombia",
    },
    "transito_migratorio": {
        "label": "Tránsito migratorio",
        "model_label": "Transito_migratorio",
        "description": "Rutas migratorias, pasos fronterizos, Darién, Tapachula y movilidad.",
        "keywords": ["frontera", "tránsito", "rutas", "caminantes", "albergues"],
        "bias": "mexico",
    },
    "seguridad": {
        "label": "Seguridad",
        "model_label": "Seguridad",
        "description": "Enfoque en orden público, criminalidad, delincuencia y acciones policiales.",
        "keywords": ["delincuencia", "crimen", "policía", "captura", "inseguridad"],
        "bias": "colombia",
    },
    "integracion_social": {
        "label": "Integración social",
        "model_label": "Integración_social",
        "description": "Aspectos de convivencia, xenofobia, acogida comunitaria y asimilación.",
        "keywords": ["xenofobia", "convivencia", "comunidad", "discriminación"],
        "bias": "mexico",
    },
    "politica_migratoria": {
        "label": "Política migratoria",
        "model_label": "Politica_migratoria",
        "description": "Regulación legal, estatutos temporales (PPT), visados y acuerdos de Estado.",
        "keywords": ["regularización", "PPT", "visas", "cancillería", "decreto"],
        "bias": "colombia",
    },
    "empleo_economia": {
        "label": "Empleo y economía",
        "model_label": "Empleo_y_economía",
        "description": "Fuerza laboral, oportunidades de trabajo, aporte económico y comercio.",
        "keywords": ["trabajo", "empleo", "economía", "productividad", "empresas"],
        "bias": "mexico",
    },
    "otros": {
        "label": "Otros",
        "model_label": "Otros",
        "description": "Derechos humanos, cooperación internacional (ONU, ACNUR) y vulnerabilidad.",
        "keywords": ["derechos humanos", "ACNUR", "niñez", "vulnerabilidad"],
        "bias": "positive",
    },
}

FRAME_IDS = list(FRAMES.keys())
FRAME_MODEL_TO_ID = {meta["model_label"]: frame_id for frame_id, meta in FRAMES.items()}

SENTIMENT_EXPLANATIONS = {
    "Negativo": (
        "Predomina una tonalidad de alarma o alerta social, con léxico asociado a "
        "problemáticas, presión institucional o tensiones."
    ),
    "Neutro": (
        "Tono marcadamente informativo y descriptivo, reportando hechos o cifras "
        "sin carga adjetival polarizada."
    ),
    "Positivo": (
        "Predomina una perspectiva constructiva, enfatizando oportunidades laborales, "
        "ayuda humanitaria o integración social exitosa."
    ),
}

MODEL_DISPLAY_NAME = "BETO-migra-ve (sentimiento + encuadres)"
MULTITASK_DISPLAY_NAME = "BETO-migra-ve multitarea (sentimiento + encuadres)"
LEXICON_DISPLAY_NAME = "léxico-MigraVenezuela (baseline)"
