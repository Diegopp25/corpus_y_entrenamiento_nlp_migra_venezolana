"""Scorers: envuelven un modelo y exponen la misma interfaz.

Interfaz (duck typing):
    scorer.budget                      -> tokens de contenido por fragmento
    scorer.count_tokens(list[str])     -> list[int]
    scorer.predict(list[str], batch)   -> ndarray (n, 3) con probabilidades en el orden CLASSES

`torch` y `transformers` se importan de forma perezosa, así el resto del paquete
(troceo, análisis) funciona sin ellos.
"""
from __future__ import annotations

import re

import numpy as np

from sentiment_benchmark.config import CHUNK_TOKEN_CAP, CLASSES, NLI_HYPOTHESES, ModelSpec
from sentiment_benchmark.labels import class_groups

_ROBERTA_LIKE = {"roberta", "xlm-roberta", "camembert", "longformer"}


def usable_length(tokenizer, config, cap: int = CHUNK_TOKEN_CAP) -> int:
    """Longitud máxima de secuencia (con tokens especiales) que el modelo admite de verdad.

    Los modelos tipo RoBERTa reservan 2 posiciones (p. ej. RoBERTuito: 130 -> 128).
    """
    limits = [cap]
    max_pos = getattr(config, "max_position_embeddings", None)
    if max_pos:
        offset = 2 if getattr(config, "model_type", "") in _ROBERTA_LIKE else 0
        limits.append(int(max_pos) - offset)
    tok_max = getattr(tokenizer, "model_max_length", None)
    if tok_max and tok_max < 100_000:
        limits.append(int(tok_max))
    return min(limits)


def resolve_device(torch, requested: str = "auto") -> str:
    if requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    mps = getattr(torch.backends, "mps", None)
    if mps is not None and mps.is_available():
        return "mps"
    return "cpu"


class _HFBase:
    def __init__(self, spec: ModelSpec, device: str = "auto"):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        from transformers import logging as hf_logging

        hf_logging.set_verbosity_error()
        self.torch = torch
        self.spec = spec
        self.device = resolve_device(torch, device)
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(spec.hf_id)
        except Exception as exc:
            if not spec.tokenizer_id:
                raise
            print(f"[{spec.key}] el tokenizador del modelo no cargó ({type(exc).__name__}); "
                  f"uso {spec.tokenizer_id}")
            self.tokenizer = AutoTokenizer.from_pretrained(spec.tokenizer_id)
        self.model = AutoModelForSequenceClassification.from_pretrained(spec.hf_id)
        self.model.to(self.device).eval()
        self.max_tokens = usable_length(self.tokenizer, self.model.config)

    def count_tokens(self, texts: list[str]) -> list[int]:
        ids = self.tokenizer(texts, add_special_tokens=False, return_attention_mask=False)["input_ids"]
        return [len(x) for x in ids]

    def _batches(self, texts: list[str], batch_size: int):
        """Itera por lotes ordenados por longitud (menos relleno); entrega índices originales."""
        order = np.argsort([len(t) for t in texts], kind="stable")
        for start in range(0, len(texts), batch_size):
            yield order[start : start + batch_size]


class HFClassifierScorer(_HFBase):
    """Modelo con cabeza de clasificación (NEG/NEU/POS, 1-5 estrellas, Negativo/Positivo...)."""

    def __init__(self, spec: ModelSpec, device: str = "auto"):
        super().__init__(spec, device)
        self.groups = class_groups(self.model.config.id2label, spec.label_map)
        self.budget = self.max_tokens - self.tokenizer.num_special_tokens_to_add(pair=False)

    def predict(self, texts: list[str], batch_size: int = 16) -> np.ndarray:
        torch = self.torch
        out = np.zeros((len(texts), len(CLASSES)), dtype=np.float64)
        for idx in self._batches(texts, batch_size):
            batch = [texts[i] for i in idx]
            enc = self.tokenizer(
                batch,
                truncation=True,
                max_length=self.max_tokens,
                padding=True,
                return_tensors="pt",
            ).to(self.device)
            with torch.inference_mode():
                logits = self.model(**enc).logits
            probs = torch.softmax(logits.float(), dim=-1).cpu().numpy()
            for class_idx, logit_ids in self.groups:
                out[idx, class_idx] = probs[:, logit_ids].sum(axis=1)
        return out


class HFNLIScorer(_HFBase):
    """Zero-shot por NLI: una hipótesis por clase; softmax sobre los logits de 'entailment'."""

    def __init__(self, spec: ModelSpec, device: str = "auto"):
        super().__init__(spec, device)
        id2label = self.model.config.id2label
        ent = [int(i) for i, lab in id2label.items() if str(lab).lower().startswith("entail")]
        if not ent:
            raise ValueError(f"No encontré la etiqueta 'entailment' en id2label={id2label}")
        self.entailment_idx = ent[0]
        hyps = spec.hypotheses or NLI_HYPOTHESES
        self.hypotheses = [hyps[c] for c in CLASSES]
        hyp_len = max(len(x) for x in self.tokenizer(self.hypotheses, add_special_tokens=False)["input_ids"])
        self.budget = self.max_tokens - self.tokenizer.num_special_tokens_to_add(pair=True) - hyp_len

    def predict(self, texts: list[str], batch_size: int = 16) -> np.ndarray:
        torch = self.torch
        k = len(self.hypotheses)
        out = np.zeros((len(texts), k), dtype=np.float64)
        for idx in self._batches(texts, batch_size):
            batch = [texts[i] for i in idx]
            premises = [t for t in batch for _ in range(k)]
            hypotheses = self.hypotheses * len(batch)
            enc = self.tokenizer(
                premises,
                hypotheses,
                truncation="only_first",
                max_length=self.max_tokens,
                padding=True,
                return_tensors="pt",
            ).to(self.device)
            with torch.inference_mode():
                logits = self.model(**enc).logits[:, self.entailment_idx]
            probs = torch.softmax(logits.float().view(len(batch), k), dim=-1).cpu().numpy()
            out[idx] = probs
        return out


# ---------------------------------------------------------------------------
# Scorer de juguete: SOLO para probar el pipeline sin descargar modelos.
# No es un modelo de sentimiento válido; no lo uses para sacar conclusiones.
# ---------------------------------------------------------------------------
_NEG = {"crisis", "crimen", "violencia", "pobreza", "xenofobia", "muerte", "muertos", "ilegal",
        "discriminación", "rechazo", "delito", "problema", "hambre", "frontera", "deportados"}
_POS = {"apoyo", "ayuda", "oportunidad", "integración", "solidaridad", "protección", "regularización",
        "aporte", "esperanza", "logro", "acogida", "trabajo", "derechos"}


class LexiconDummyScorer:
    """`noise_seed` > 0 añade ruido a los logits para simular modelos que discrepan."""

    def __init__(self, noise_seed: int = 0):
        self.budget = 120
        self.noise_seed = noise_seed

    def count_tokens(self, texts: list[str]) -> list[int]:
        return [len(t.split()) for t in texts]

    def predict(self, texts: list[str], batch_size: int = 16) -> np.ndarray:
        out = np.zeros((len(texts), 3))
        rng = np.random.default_rng(self.noise_seed)
        for i, t in enumerate(texts):
            words = re.findall(r"\w+", t.lower())
            neg = sum(w in _NEG for w in words)
            pos = sum(w in _POS for w in words)
            logits = np.array([neg, 0.5, pos], dtype=float)
            if self.noise_seed:
                logits = logits + rng.normal(0, 0.8, size=3)
            e = np.exp(logits - logits.max())
            out[i] = e / e.sum()
        return out


DUMMY_KEYS = {"dummy_a": 0, "dummy_b": 1, "dummy_c": 2}


def build_scorer(key: str, spec: ModelSpec | None, backend: str = "hf", device: str = "auto"):
    if backend == "dummy":
        return LexiconDummyScorer(noise_seed=DUMMY_KEYS[key])
    if spec.kind == "nli":
        return HFNLIScorer(spec, device)
    return HFClassifierScorer(spec, device)