"""Orquestación del análisis: motor -> contrato del frontend -> persistencia."""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from ..config import Settings
from ..engine import AnalysisEngine, RawPrediction
from ..engine.labels import (
    FRAMES,
    FRAME_IDS,
    SENTIMENT_EXPLANATIONS,
    SENTIMENT_LABELS,
)
from ..engine.text import clean_text, count_words, reading_time_seconds
from ..schemas import (
    AnalyzeRequest,
    AnalysisMeta,
    CulturalBias,
    FrameScore,
    SentimentAnalysis,
    SentimentScores,
    TextAnalysisResult,
)
from . import cultural
from .monitoring import Monitoring
from .site_catalog import infer_country, infer_media_name
from .store import Store

logger = logging.getLogger(__name__)

_MIN_WORDS = 30

_COUNTRY_ALIASES = {
    "colombia": "Colombia",
    "méxico": "México",
    "mexico": "México",
    "mx": "México",
    "internacional": "Internacional",
    "desconocido": "Desconocido",
    "": "Desconocido",
}


def normalize_country(value: str | None) -> str | None:
    if value is None:
        return None
    return _COUNTRY_ALIASES.get(value.strip().lower(), value.strip())


def _percentages(probabilities: dict[str, float]) -> dict[str, float]:
    """Convierte probabilidades 0..1 en porcentajes que suman exactamente 100."""
    scores = {
        label.lower(): round(float(probabilities.get(label, 0.0)) * 100, 1)
        for label in SENTIMENT_LABELS
    }
    remainder = round(100.0 - sum(scores.values()), 1)
    winner = max(scores, key=scores.get)
    scores[winner] = round(scores[winner] + remainder, 1)
    return scores


class AnalysisService:
    def __init__(
        self,
        engine: AnalysisEngine,
        store: Store,
        settings: Settings,
        monitoring: Monitoring,
        *,
        requested_engine: str = "auto",
        degraded: bool = False,
        reason: str = "",
    ) -> None:
        self.engine = engine
        self.store = store
        self.settings = settings
        self.monitoring = monitoring
        self.requested_engine = requested_engine
        self.degraded = degraded
        self.reason = reason
        self._bias_terms = cultural.load_bias_terms(settings.lexicon_path)

    # ------------------------------------------------------------------
    def analyze_request(
        self,
        request: AnalyzeRequest,
        *,
        source: str = "api",
        job_id: str | None = None,
    ) -> TextAnalysisResult:
        return self.analyze_text(
            request.text,
            title=request.title,
            source_url=request.source_url,
            media_name=request.media_name,
            country=request.country,
            source=source,
            job_id=job_id,
        )

    def analyze_text(
        self,
        text: str,
        *,
        title: str | None = None,
        source_url: str | None = None,
        media_name: str | None = None,
        country: str | None = None,
        source: str = "api",
        job_id: str | None = None,
    ) -> TextAnalysisResult:
        cleaned = clean_text(text)
        if not cleaned:
            raise ValueError("El texto no contiene contenido analizable")
        if len(cleaned) > self.settings.max_text_chars:
            cleaned = cleaned[: self.settings.max_text_chars]

        started = time.perf_counter()
        try:
            prediction = self.engine.predict(cleaned)
        except Exception as exc:  # pragma: no cover - depende del backend
            self.monitoring.inc_engine_error(self.engine.name)
            logger.exception("Fallo del motor %s", self.engine.name)
            raise RuntimeError(f"Error del motor de análisis: {exc}") from exc
        latency_ms = round((time.perf_counter() - started) * 1000, 2)

        resolved_country = normalize_country(country)
        if not resolved_country:
            resolved_country = infer_country(url=source_url, media_name=media_name)
        resolved_media = media_name or infer_media_name(url=source_url)

        result = self._build_result(
            cleaned,
            prediction,
            title=title,
            source_url=source_url,
            media_name=resolved_media,
            country=resolved_country,
            latency_ms=latency_ms,
            source=source,
            job_id=job_id,
        )

        payload = result.model_dump(by_alias=True, mode="json")
        payload["_truncated"] = result.meta.truncated
        payload["_textHash"] = hashlib.sha1(cleaned.encode("utf-8")).hexdigest()
        persisted = self.store.save_analysis(
            payload,
            [frame.model_dump(by_alias=True, mode="json") for frame in result.frames],
            source=source,
            engine=result.meta.engine,
            model_version=result.meta.model_version,
            model_used=result.model_used,
            latency_ms=result.meta.latency_ms,
            job_id=job_id,
        )
        result.meta.persisted = persisted
        self.monitoring.inc_analysis(result.meta.engine, result.sentiment.prediction)
        return result

    # ------------------------------------------------------------------
    def _build_result(
        self,
        text: str,
        prediction: RawPrediction,
        *,
        title: str | None,
        source_url: str | None,
        media_name: str | None,
        country: str,
        latency_ms: float,
        source: str,
        job_id: str | None,
    ) -> TextAnalysisResult:
        sentiment_scores = _percentages(prediction.sentiment)
        prediction_label = max(
            SENTIMENT_LABELS,
            key=lambda label: prediction.sentiment.get(label, 0.0),
        )
        confidence = sentiment_scores[prediction_label.lower()]

        warnings: list[str] = []
        for warning in prediction.warnings:
            if warning not in warnings:
                warnings.append(warning)
        if count_words(text) < _MIN_WORDS:
            short = (
                "Texto corto (menos de 30 palabras): el modelo se entrenó con "
                "noticias completas y el resultado es orientativo."
            )
            if short not in warnings:
                warnings.insert(0, short)

        frames: list[FrameScore] = []
        for frame_id in FRAME_IDS:
            probability = float(prediction.frames.get(frame_id, 0.0))
            threshold = float(
                self.engine.thresholds.get(frame_id, self.settings.frame_threshold)
            )
            meta = FRAMES[frame_id]
            frames.append(
                FrameScore(
                    id=frame_id,
                    label=meta["label"],
                    score=round(probability * 100, 1),
                    is_active=probability >= threshold,
                    description=meta["description"],
                    associated_keywords=list(meta["keywords"]),
                )
            )
        frames.sort(key=lambda frame: frame.score, reverse=True)

        bias_payload = cultural.classify_bias(
            prediction.frames, text, self._bias_terms
        )

        models = {descriptor.role: descriptor for descriptor in self.engine.models}

        meta = AnalysisMeta(
            engine=self.engine.name,
            requested_engine=self.requested_engine,
            degraded=self.degraded,
            model_version=prediction.model_version or self.engine.version,
            sentiment_model=getattr(models.get("sentiment"), "name", ""),
            frames_model=getattr(models.get("frames"), "name", ""),
            preprocessing=prediction.preprocessing,
            latency_ms=latency_ms,
            truncated=prediction.truncated,
            warnings=warnings,
            persisted=False,
            source=source,
            job_id=job_id,
        )

        return TextAnalysisResult(
            id=f"analisis-{uuid.uuid4().hex[:16]}",
            text=text,
            title=title,
            source_url=source_url,
            media_name=media_name,
            country=country,  # type: ignore[arg-type]
            date_analyzed=datetime.now(timezone.utc),
            sentiment=SentimentAnalysis(
                prediction=prediction_label,  # type: ignore[arg-type]
                confidence=confidence,
                scores=SentimentScores(**sentiment_scores),
                explanation=SENTIMENT_EXPLANATIONS[prediction_label],
            ),
            frames=frames,
            cultural_bias=CulturalBias(**bias_payload),
            tokens_count=count_words(text),
            reading_time_seconds=reading_time_seconds(text),
            model_used=self.engine.display_name,
            meta=meta,
        )

    # ------------------------------------------------------------------
    def analyze_many(
        self,
        items: list[AnalyzeRequest],
        *,
        source: str = "api",
    ) -> list[TextAnalysisResult]:
        results: list[TextAnalysisResult] = []
        for item in items:
            results.append(self.analyze_request(item, source=source))
        return results
