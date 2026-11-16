"""Motor de respaldo léxico.

Se usa cuando no hay pesos BETO disponibles (por ejemplo en CI o en una
máquina recién clonada). Los pesos del léxico se generan a partir del corpus
etiquetado con ``api/scripts/build_lexicon.py`` y viven en
``api/app/resources/lexicon.json``. Si el archivo no existe, el motor usa un
léxico mínimo integrado para no romper el API.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

from .base import AnalysisEngine, ModelDescriptor, RawPrediction
from .labels import (
    FRAME_IDS,
    LEXICON_DISPLAY_NAME,
    SENTIMENT_LABELS,
)
from .text import count_words, normalize_for_match

_TOKEN_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñü]+")

_FALLBACK_LEXICON: dict[str, dict] = {
    "sentiment": {
        "Negativo": {
            "inseguridad": 1.4, "delincuencia": 1.5, "crimen": 1.3, "robo": 1.2,
            "homicidio": 1.3, "xenofobia": 1.4, "discriminación": 1.2,
            "crisis": 1.1, "deportación": 0.9, "amenaza": 1.2, "violencia": 1.3,
            "pobreza": 1.1, "rechazo": 1.1, "irregular": 0.8, "saturación": 1.1,
        },
        "Positivo": {
            "oportunidad": 1.3, "oportunidades": 1.3, "empleo": 1.2, "trabajo": 1.0,
            "integración": 1.2, "solidaridad": 1.3, "ayuda": 1.0, "éxito": 1.2,
            "bienestar": 1.1, "regularización": 1.0, "educación": 0.7,
            "crecimiento": 1.0, "emprendimiento": 1.1, "acogida": 1.1,
        },
        "Neutro": {"informe": 0.6, "cifras": 0.6, "según": 0.5, "anunció": 0.4},
    },
    "frames": {
        "acceso_servicios": {
            "salud": 1.5, "hospital": 1.4, "hospitales": 1.4, "educación": 1.5,
            "colegio": 1.0, "colegios": 1.0, "vivienda": 1.1, "vacunación": 1.3,
            "atención": 0.8, "servicios": 0.8,
        },
        "transito_migratorio": {
            "frontera": 1.6, "tránsito": 1.4, "darién": 1.7, "tapachula": 1.6,
            "chiapas": 1.4, "caminantes": 1.4, "albergue": 1.1, "albergues": 1.1,
            "ruta": 0.9, "rutas": 0.9, "caravana": 1.4,
        },
        "seguridad": {
            "seguridad": 1.6, "inseguridad": 1.6, "delincuencia": 1.7, "crimen": 1.5,
            "banda": 1.4, "captura": 1.2, "policía": 1.3, "homicidio": 1.5,
            "robo": 1.4, "atracos": 1.5, "tren de aragua": 1.9,
        },
        "integracion_social": {
            "integración": 1.6, "convivencia": 1.4, "comunidad": 1.1,
            "xenofobia": 1.7, "discriminación": 1.5, "rechazo": 1.2,
            "asimilación": 1.2, "acogida": 1.2,
        },
        "politica_migratoria": {
            "regularización": 1.7, "estatuto": 1.5, "ppt": 1.8, "visa": 1.3,
            "visas": 1.3, "decreto": 1.2, "cancillería": 1.5, "migración": 1.0,
            "gobierno": 0.5, "política": 0.9,
        },
        "empleo_economia": {
            "empleo": 1.7, "trabajo": 1.4, "economía": 1.4, "productividad": 1.5,
            "empresas": 1.1, "remesas": 1.4, "salario": 1.2, "mano de obra": 1.8,
            "fuerza laboral": 1.9, "emprendimiento": 1.5,
        },
        "otros": {
            "derechos humanos": 1.7, "acnur": 1.6, "onu": 1.3, "niñez": 1.3,
            "vulnerabilidad": 1.2, "testimonios": 1.0,
        },
    },
    "bias_terms": {},
}


class LexiconEngine(AnalysisEngine):
    name = "lexicon"
    version = "1.0"
    display_name = LEXICON_DISPLAY_NAME

    def __init__(self, lexicon_path: Path | str | None = None) -> None:
        self._path = Path(lexicon_path) if lexicon_path else None
        self._lexicon = self._load()
        self._available = True

    def _load(self) -> dict:
        if self._path and self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "sentiment" in data:
                    # El léxico derivado del corpus se combina con el curado:
                    # el curado manda en los términos conocidos y el derivado
                    # aporta vocabulario específico con peso atenuado.
                    merged = json.loads(json.dumps(_FALLBACK_LEXICON))
                    for label, terms in data.get("sentiment", {}).items():
                        target = merged["sentiment"].setdefault(label, {})
                        for term, weight in terms.items():
                            target.setdefault(term, round(min(1.0, float(weight) * 0.45), 3))
                    for frame_id, terms in data.get("frames", {}).items():
                        target = merged["frames"].setdefault(frame_id, {})
                        for term, weight in terms.items():
                            target.setdefault(term, round(min(1.0, float(weight) * 0.45), 3))
                    if isinstance(data.get("bias_terms"), dict):
                        merged["bias_terms"] = data["bias_terms"]
                    return merged
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass
        return _FALLBACK_LEXICON

    @property
    def models(self) -> list[ModelDescriptor]:
        return [
            ModelDescriptor(
                name="lexicon-fallback",
                role="analisis",
                available=self._available,
                loaded=True,
                architecture="Baseline léxico derivado del corpus etiquetado",
                path=str(self._path or "integrado"),
                labels=SENTIMENT_LABELS,
            )
        ]

    def predict(self, text: str) -> RawPrediction:
        normalized = normalize_for_match(text)
        tokens = _TOKEN_RE.findall(normalized)
        words = count_words(text)

        # --- sentimiento: log-odds acumulados por clase ---
        scores = {label: 0.0 for label in SENTIMENT_LABELS}
        for label in SENTIMENT_LABELS:
            vocabulary = self._lexicon["sentiment"].get(label, {})
            for term, weight in vocabulary.items():
                term_norm = normalize_for_match(term)
                occurrences = normalized.count(term_norm)
                if occurrences:
                    scores[label] += float(weight) * min(occurrences, 5)
        # suavizado para evitar saturaciones
        scores = {label: value / (1.0 + abs(value)) for label, value in scores.items()}
        shifted = {label: math.exp(value) for label, value in scores.items()}
        total = sum(shifted.values()) or 1.0
        sentiment = {label: shifted[label] / total for label in SENTIMENT_LABELS}

        # --- encuadres: sigmoid de la evidencia léxica ---
        frames: dict[str, float] = {}
        for frame_id in FRAME_IDS:
            vocabulary = self._lexicon["frames"].get(frame_id, {})
            evidence = 0.0
            for term, weight in vocabulary.items():
                occurrences = normalized.count(normalize_for_match(term))
                if occurrences:
                    evidence += float(weight) * min(occurrences, 4)
            probability = 1.0 / (1.0 + math.exp(-(evidence - 1.2)))
            frames[frame_id] = probability

        warnings = []
        if words < 30:
            warnings.append(
                "Texto corto (menos de 30 palabras): el resultado del motor léxico "
                "es orientativo."
            )

        return RawPrediction(
            sentiment=sentiment,
            frames=frames,
            model_name=LEXICON_DISPLAY_NAME,
            model_version=self.version,
            warnings=warnings,
            preprocessing="lexicon",
        )
