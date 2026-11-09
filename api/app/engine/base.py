"""Interfaz común de los motores de análisis."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any


class EngineUnavailable(RuntimeError):
    """El motor solicitado no puede cargarse (faltan pesos o dependencias)."""


@dataclass
class ModelDescriptor:
    name: str
    role: str
    available: bool
    loaded: bool = False
    architecture: str = ""
    path: str = ""
    max_length: int = 0
    device: str = ""
    labels: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RawPrediction:
    """Salida cruda del motor, antes de aplicar el contrato del API."""

    sentiment: dict[str, float]  # {"Negativo": p, "Neutro": p, "Positivo": p}
    frames: dict[str, float]  # frame_id -> probabilidad 0..1
    model_name: str
    model_version: str = ""
    warnings: list[str] = field(default_factory=list)
    preprocessing: str = "raw"
    truncated: bool = False


class AnalysisEngine(ABC):
    """Contrato mínimo que cumplen el motor BETO, el multitarea y el léxico."""

    name: str = "base"
    version: str = "0"
    display_name: str = "motor"

    @property
    @abstractmethod
    def models(self) -> list[ModelDescriptor]:
        """Modelos que usa este motor (para /v1/health y /v1/models)."""

    @abstractmethod
    def predict(self, text: str) -> RawPrediction:
        """Analiza un texto ya limpio con ``clean_text``."""

    def predict_batch(self, texts: list[str], **kwargs: Any) -> list[RawPrediction]:
        """Predicción por lotes; los motores pueden sobrescribirla."""
        return [self.predict(text) for text in texts]

    def unload(self) -> None:  # pragma: no cover - se usa en tests
        """Libera memoria si el backend lo permite."""

    #: Umbral por encuadre (0..1). Vacío = usar ``NLP_FRAME_THRESHOLD``.
    thresholds: dict[str, float] = {}
