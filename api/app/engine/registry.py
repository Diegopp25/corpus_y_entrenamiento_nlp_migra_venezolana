"""Selección del motor de análisis según configuración y disponibilidad."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Settings
from .base import AnalysisEngine, EngineUnavailable
from .bert_pair import BertPairEngine, load_thresholds, model_dir_ready
from .lexicon import LexiconEngine
from .multitask import MultitaskEngine

logger = logging.getLogger(__name__)


@dataclass
class EngineSelection:
    engine: AnalysisEngine
    requested: str
    selected: str
    degraded: bool = False
    reason: str = ""
    warnings: list[str] = field(default_factory=list)


def _multitask_ready(directory: Path | None) -> bool:
    if not directory:
        return False
    directory = Path(directory)
    return (directory / "model.pt").exists() and (
        (directory / "sentiment_classes.json").exists()
    )


def build_engine(settings: Settings) -> EngineSelection:
    """Construye el motor: BETO real, multitarea o léxico de respaldo.

    En modo ``auto`` intenta BETO par -> BETO multitarea -> léxico.
    Si se fuerza un motor, falla con un mensaje claro cuando no está disponible.
    """
    requested = settings.engine
    thresholds = load_thresholds(settings.thresholds_path)
    attempts: list[str] = []

    def _bert_pair() -> EngineSelection:
        engine = BertPairEngine(
            sentiment_model_dir=settings.sentiment_model_dir,
            frames_model_dir=settings.frames_model_dir,
            device=settings.device,
            max_length=settings.max_length,
            thresholds=thresholds,
        )
        return EngineSelection(engine=engine, requested=requested, selected=engine.name)

    def _multitask() -> EngineSelection:
        engine = MultitaskEngine(
            model_dir=settings.multitask_model_dir,
            device=settings.device,
            max_length=settings.max_length,
            thresholds=thresholds,
            preprocess_with_spacy=settings.preprocess_with_spacy,
        )
        return EngineSelection(engine=engine, requested=requested, selected=engine.name)

    def _lexicon(reason: str = "") -> EngineSelection:
        return EngineSelection(
            engine=LexiconEngine(settings.lexicon_path),
            requested=requested,
            selected="lexicon",
            degraded=requested != "lexicon",
            reason=reason,
        )

    if requested == "bert_pair":
        try:
            return _bert_pair()
        except EngineUnavailable as exc:
            raise EngineUnavailable(
                f"NLP_ENGINE=bert_pair pero los modelos no están disponibles: {exc}. "
                f"Configura NLP_SENTIMENT_MODEL_DIR y NLP_FRAMES_MODEL_DIR."
            ) from exc

    if requested == "multitask":
        try:
            return _multitask()
        except EngineUnavailable as exc:
            raise EngineUnavailable(
                f"NLP_ENGINE=multitask pero el modelo no está disponible: {exc}"
            ) from exc

    if requested == "lexicon":
        return _lexicon()

    # auto
    if model_dir_ready(settings.sentiment_model_dir) and model_dir_ready(
        settings.frames_model_dir
    ):
        try:
            return _bert_pair()
        except EngineUnavailable as exc:
            attempts.append(f"beto: {exc}")
            logger.warning("No se pudo cargar BETO, se intenta el respaldo: %s", exc)
    else:
        attempts.append(
            f"beto: faltan pesos en {settings.sentiment_model_dir} o "
            f"{settings.frames_model_dir}"
        )

    if _multitask_ready(settings.multitask_model_dir):
        try:
            return _multitask()
        except EngineUnavailable as exc:
            attempts.append(f"multitarea: {exc}")
    else:
        attempts.append("multitarea: no hay model.pt")

    reason = (
        "Sin modelos entrenados disponibles; se usa el baseline léxico. "
        + " | ".join(attempts)
    )
    logger.warning(reason)
    selection = _lexicon(reason=reason)
    selection.warnings.append(reason)
    return selection
