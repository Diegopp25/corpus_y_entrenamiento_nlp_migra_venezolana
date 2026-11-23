"""Motor multitarea del repositorio (``model.pt`` + spaCy).

Replica la arquitectura ``MultiTaskBERT`` de ``app/app.py``: un encoder BETO con
dos cabezas lineales (sentimiento y encuadres). Solo se usa si existe
``NLP_MULTITASK_MODEL_DIR/model.pt``; el par de modelos BETO es la opción
recomendada.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from .base import AnalysisEngine, EngineUnavailable, ModelDescriptor, RawPrediction
from .labels import FRAME_IDS, FRAME_MODEL_ORDER, MULTITASK_DISPLAY_NAME
from .text import clean_text

logger = logging.getLogger(__name__)

_ENGLISH_WORDS = {
    "the", "and", "for", "with", "from", "that", "this", "these", "those",
    "will", "would", "have", "has", "had", "been", "being", "are", "is",
    "was", "were", "of", "to", "in", "on", "at", "by", "about", "into",
    "new", "time", "news", "after", "before", "over", "under",
}


class MultitaskEngine(AnalysisEngine):
    name = "multitask"
    version = "1.0"
    display_name = MULTITASK_DISPLAY_NAME

    def __init__(
        self,
        model_dir: Path | str,
        device: str = "auto",
        max_length: int = 512,
        thresholds: dict[str, float] | None = None,
        preprocess_with_spacy: bool = True,
    ) -> None:
        directory = Path(model_dir)
        weights = directory / "model.pt"
        if not weights.exists():
            raise EngineUnavailable(f"No se encontró {weights}")
        try:
            import torch
            import torch.nn as nn
            from transformers import AutoConfig, AutoModel, AutoTokenizer
        except ImportError as exc:  # pragma: no cover
            raise EngineUnavailable(
                "Faltan torch/transformers. Instala api/requirements-models.txt"
            ) from exc

        self._torch = torch
        self.model_dir = directory
        self.max_length = max_length

        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = torch.device(device)

        classes_path = directory / "sentiment_classes.json"
        if not classes_path.exists():
            raise EngineUnavailable(f"Falta {classes_path}")
        self._sentiment_labels = json.loads(classes_path.read_text(encoding="utf-8"))
        self._frame_labels = list(FRAME_MODEL_ORDER)

        config = AutoConfig.from_pretrained("dccuchile/bert-base-spanish-wwm-cased")
        hidden = config.hidden_size

        class MultiTaskBERT(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.encoder = AutoModel.from_config(config)
                self.dropout = nn.Dropout(0.2)
                self.sentiment_head = nn.Linear(hidden, len(self._sentiment_labels))
                self.multilabel_head = nn.Linear(hidden, len(self._frame_labels))

            def forward(self, input_ids, attention_mask):  # type: ignore[no-untyped-def]
                outputs = self.encoder(
                    input_ids=input_ids, attention_mask=attention_mask
                )
                cls = self.dropout(outputs.last_hidden_state[:, 0])
                return self.sentiment_head(cls), self.multilabel_head(cls)

        self._tokenizer = AutoTokenizer.from_pretrained(str(directory))
        self._model = MultiTaskBERT()
        state = torch.load(weights, map_location="cpu", weights_only=True)
        self._model.load_state_dict(state)
        self._model.to(self.device).eval()

        self._nlp = None
        if preprocess_with_spacy:
            try:
                import spacy

                self._nlp = spacy.load("es_core_news_lg", disable=["parser"])
            except Exception as exc:  # pragma: no cover - opcional
                logger.warning("spaCy es_core_news_lg no disponible: %s", exc)

        self.thresholds = dict(thresholds or {})

    @property
    def models(self) -> list[ModelDescriptor]:
        return [
            ModelDescriptor(
                name="beto-multitarea",
                role="sentiment+frames",
                available=True,
                loaded=True,
                architecture="BETO + dos cabezas (3 clases + 7 multi-etiqueta)",
                path=str(self.model_dir),
                max_length=self.max_length,
                device=str(self.device),
                labels=list(self._sentiment_labels) + list(self._frame_labels),
            )
        ]

    def _preprocess(self, text: str) -> str:
        if self._nlp is None:
            return clean_text(text)
        doc = self._nlp(clean_text(text))
        tokens: list[str] = []
        for token in doc:
            if token.is_space or token.is_punct or token.like_num or token.is_stop:
                continue
            if token.pos_ == "PROPN":
                continue
            lemma = token.lemma_.lower().strip()
            if len(lemma) < 3 or not lemma.isalpha() or lemma in _ENGLISH_WORDS:
                continue
            tokens.append(lemma)
        return " ".join(tokens)

    def predict(self, text: str) -> RawPrediction:
        processed = self._preprocess(text)
        if not processed:
            processed = clean_text(text)
        torch = self._torch
        with torch.no_grad():
            encoded = self._tokenizer(
                processed,
                truncation=True,
                max_length=self.max_length,
                return_tensors="pt",
            )
            sentiment_logits, frame_logits = self._model(
                encoded["input_ids"].to(self.device),
                encoded["attention_mask"].to(self.device),
            )
            sentiment_probs = (
                torch.softmax(sentiment_logits.float(), dim=-1)[0].cpu().tolist()
            )
            frame_probs = torch.sigmoid(frame_logits.float())[0].cpu().tolist()

        sentiment = dict(zip(self._sentiment_labels, map(float, sentiment_probs)))
        frames = dict(zip(FRAME_IDS, map(float, frame_probs)))
        warnings = []
        if len(processed.split()) < 15:
            warnings.append("Texto muy corto tras el preprocesamiento.")
        return RawPrediction(
            sentiment=sentiment,
            frames=frames,
            model_name=MULTITASK_DISPLAY_NAME,
            model_version=self.version,
            warnings=warnings,
            preprocessing="spacy-lemmas" if self._nlp is not None else "clean",
        )
