"""Motor BETO real: dos cabezas de clasificación sobre BETO español.

Espera dos carpetas con el formato ``save_pretrained`` de Hugging Face:

* ``sentiment_model_dir``: BertForSequenceClassification de 3 salidas.
* ``frames_model_dir``: BertForSequenceClassification de 7 salidas (sigmoide).

Los pesos no viven en el repositorio (pesan ~440 MB cada uno). Se configuran
con ``NLP_SENTIMENT_MODEL_DIR`` y ``NLP_FRAMES_MODEL_DIR``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

from .base import AnalysisEngine, EngineUnavailable, ModelDescriptor, RawPrediction
from .labels import (
    FRAME_IDS,
    FRAME_MODEL_ORDER,
    MODEL_DISPLAY_NAME,
    SENTIMENT_LABELS,
)
from .text import clean_text, count_words

logger = logging.getLogger(__name__)

_TRANSFORMERS_ENV = {
    "TRANSFORMERS_VERBOSITY": "error",
    "HF_HUB_DISABLE_PROGRESS_BARS": "1",
    "TOKENIZERS_PARALLELISM": "false",
}

_MODEL_FILES = ("model.safetensors", "pytorch_model.bin", "model.pt")


def model_dir_ready(path: Path | str | None) -> bool:
    if not path:
        return False
    directory = Path(path)
    if not directory.is_dir():
        return False
    has_weights = any((directory / name).exists() for name in _MODEL_FILES)
    has_tokenizer = (directory / "tokenizer.json").exists() or (
        directory / "vocab.txt"
    ).exists()
    return has_weights and has_tokenizer


class BertPairEngine(AnalysisEngine):
    name = "bert_pair"
    version = "1.0"
    display_name = MODEL_DISPLAY_NAME

    def __init__(
        self,
        sentiment_model_dir: Path | str,
        frames_model_dir: Path | str,
        device: str = "auto",
        max_length: int = 512,
        thresholds: dict[str, float] | None = None,
        sentiment_order: Iterable[str] | None = None,
        frame_order: Iterable[str] | None = None,
    ) -> None:
        for key, value in _TRANSFORMERS_ENV.items():
            import os

            os.environ.setdefault(key, value)
        try:
            import torch
            from transformers import (
                AutoModelForSequenceClassification,
                AutoTokenizer,
            )
        except ImportError as exc:  # pragma: no cover - depende del entorno
            raise EngineUnavailable(
                "Faltan torch/transformers. Instala api/requirements-models.txt"
            ) from exc

        self._torch = torch
        self.sentiment_dir = Path(sentiment_model_dir)
        self.frames_dir = Path(frames_model_dir)
        if not model_dir_ready(self.sentiment_dir):
            raise EngineUnavailable(
                f"No hay pesos de sentimiento en {self.sentiment_dir}"
            )
        if not model_dir_ready(self.frames_dir):
            raise EngineUnavailable(
                f"No hay pesos de encuadres en {self.frames_dir}"
            )

        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = torch.device(device)
        self.max_length = max_length
        self._sentiment_order = list(sentiment_order or SENTIMENT_LABELS)
        self._frame_order = list(frame_order or FRAME_MODEL_ORDER)

        try:
            logger.info("Cargando BETO (sentimiento) desde %s", self.sentiment_dir)
            self._sentiment_tokenizer = AutoTokenizer.from_pretrained(
                str(self.sentiment_dir)
            )
            self._sentiment_model = (
                AutoModelForSequenceClassification.from_pretrained(str(self.sentiment_dir))
                .to(self.device)
                .eval()
            )
            logger.info("Cargando BETO (encuadres) desde %s", self.frames_dir)
            self._frames_tokenizer = AutoTokenizer.from_pretrained(str(self.frames_dir))
            self._frames_model = (
                AutoModelForSequenceClassification.from_pretrained(str(self.frames_dir))
                .to(self.device)
                .eval()
            )
        except Exception as exc:  # pragma: no cover - depende de los pesos
            raise EngineUnavailable(f"No se pudieron cargar los modelos BETO: {exc}") from exc

        n_sentiment = int(self._sentiment_model.config.num_labels)
        n_frames = int(self._frames_model.config.num_labels)
        if n_sentiment != len(self._sentiment_order):
            raise EngineUnavailable(
                f"El modelo de sentimiento tiene {n_sentiment} salidas y se "
                f"esperaban {len(self._sentiment_order)}"
            )
        if n_frames != len(self._frame_order):
            raise EngineUnavailable(
                f"El modelo de encuadres tiene {n_frames} salidas y se "
                f"esperaban {len(self._frame_order)}"
            )

        self.thresholds = dict(thresholds or {})

    # ------------------------------------------------------------------
    @property
    def models(self) -> list[ModelDescriptor]:
        return [
            ModelDescriptor(
                name="beto-sentimiento",
                role="sentiment",
                available=True,
                loaded=True,
                architecture="BERT base español (BETO) + clasificador de 3 clases",
                path=str(self.sentiment_dir),
                max_length=self.max_length,
                device=str(self.device),
                labels=list(self._sentiment_order),
            ),
            ModelDescriptor(
                name="beto-encuadres",
                role="frames",
                available=True,
                loaded=True,
                architecture="BERT base español (BETO) + 7 salidas multi-etiqueta",
                path=str(self.frames_dir),
                max_length=self.max_length,
                device=str(self.device),
                labels=list(self._frame_order),
            ),
        ]

    # ------------------------------------------------------------------
    def predict(self, text: str) -> RawPrediction:
        return self.predict_batch([text])[0]

    def predict_batch(
        self, texts: list[str], batch_size: int = 8
    ) -> list[RawPrediction]:
        results: list[RawPrediction] = []
        for start in range(0, len(texts), batch_size):
            chunk = texts[start : start + batch_size]
            results.extend(self._predict_chunk(chunk))
        return results

    def _predict_chunk(self, texts: list[str]) -> list[RawPrediction]:
        clean = [clean_text(text) for text in texts]
        torch = self._torch
        with torch.no_grad():
            sentiment_inputs = self._sentiment_tokenizer(
                clean,
                truncation=True,
                max_length=self.max_length,
                padding=True,
                return_tensors="pt",
            )
            sentiment_probs = torch.softmax(
                self._sentiment_model(
                    **{key: value.to(self.device) for key, value in sentiment_inputs.items()}
                ).logits.float(),
                dim=-1,
            ).cpu().tolist()

            frames_inputs = self._frames_tokenizer(
                clean,
                truncation=True,
                max_length=self.max_length,
                padding=True,
                return_tensors="pt",
            )
            frames_probs = torch.sigmoid(
                self._frames_model(
                    **{key: value.to(self.device) for key, value in frames_inputs.items()}
                ).logits.float()
            ).cpu().tolist()

        predictions: list[RawPrediction] = []
        for text, sentiment_row, frames_row in zip(clean, sentiment_probs, frames_probs):
            sentiment = {
                label: float(prob) for label, prob in zip(self._sentiment_order, sentiment_row)
            }
            frames = {
                FRAME_IDS[FRAME_MODEL_ORDER.index(label)]: float(prob)
                for label, prob in zip(self._frame_order, frames_row)
            }
            predictions.append(
                RawPrediction(
                    sentiment=sentiment,
                    frames=frames,
                    model_name=MODEL_DISPLAY_NAME,
                    model_version=self.version,
                    warnings=self._warnings(text, max(sentiment.values())),
                    preprocessing="bert-tokenizer",
                    truncated=self._truncated(text),
                )
            )
        return predictions

    def _truncated(self, text: str) -> bool:
        try:
            ids = self._sentiment_tokenizer(
                text, truncation=False, add_special_tokens=False
            )["input_ids"]
            return len(ids) > self.max_length
        except Exception:  # pragma: no cover - tokenizador defensivo
            return False

    def _warnings(self, text: str, confidence: float) -> list[str]:
        warnings: list[str] = []
        words = count_words(text)
        if words < 30:
            warnings.append(
                "Texto corto (menos de 30 palabras): el modelo se entrenó con "
                "noticias completas, el resultado es orientativo."
            )
        if self._truncated(text):
            warnings.append(
                f"El texto supera los {self.max_length} tokens y fue truncado: "
                "el modelo solo leyó el inicio."
            )
        if confidence < 0.45:
            warnings.append("Baja confianza del clasificador de sentimiento.")
        return warnings

    def unload(self) -> None:  # pragma: no cover - solo en apagado
        self._sentiment_model = None
        self._frames_model = None


def load_thresholds(path: Path | str | None) -> dict[str, float]:
    """Carga umbrales por encuadre aceptando ids canónicos o etiquetas del modelo."""
    from .labels import FRAMES, FRAME_MODEL_TO_ID

    if not path:
        return {}
    file_path = Path(path)
    if not file_path.exists():
        return {}
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    thresholds: dict[str, float] = {}
    for key, value in raw.items():
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if not 0.0 < number < 1.0:
            continue
        frame_id = key if key in FRAMES else FRAME_MODEL_TO_ID.get(key)
        if frame_id is None:
            # aceptar el label humano ("Empleo y economía")
            for mode_id, meta in FRAMES.items():
                if key == meta["label"]:
                    frame_id = mode_id
                    break
        if frame_id:
            thresholds[frame_id] = number
    return thresholds
