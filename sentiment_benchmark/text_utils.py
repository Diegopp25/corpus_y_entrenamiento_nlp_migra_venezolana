"""Troceo de notas en fragmentos que caben en la ventana de cada modelo."""
from __future__ import annotations

import re
from typing import Callable

# Corta después de . ! ? … si lo que sigue parece inicio de oración.
_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+(?=[¿¡\"“«(]?[A-ZÁÉÍÓÚÑÜ0-9])")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]


def _split_long_sentence(sentence: str, n_tokens: int, budget: int) -> list[tuple[str, int]]:
    """Parte una oración más larga que el presupuesto en trozos de palabras."""
    words = sentence.split()
    per_piece = max(1, int(len(words) * budget / n_tokens * 0.9))
    pieces = []
    for i in range(0, len(words), per_piece):
        part = words[i : i + per_piece]
        est = max(1, min(budget, round(n_tokens * len(part) / len(words))))
        pieces.append((" ".join(part), est))
    return pieces


def chunk_text(
    text: str,
    count_tokens: Callable[[list[str]], list[int]],
    budget: int,
) -> list[tuple[str, int]]:
    """Agrupa oraciones consecutivas hasta `budget` tokens.

    Devuelve [(texto_del_fragmento, n_tokens_aproximado), ...].
    `count_tokens` recibe una lista de textos y devuelve sus longitudes en tokens (sin especiales).
    """
    sentences = split_sentences(text)
    if not sentences:
        return []
    counts = count_tokens(sentences)

    chunks: list[tuple[str, int]] = []
    current: list[str] = []
    current_n = 0

    def flush() -> None:
        nonlocal current, current_n
        if current:
            chunks.append((" ".join(current), current_n))
            current, current_n = [], 0

    for sentence, n in zip(sentences, counts):
        if n > budget:
            flush()
            chunks.extend(_split_long_sentence(sentence, n, budget))
            continue
        if current_n + n > budget:
            flush()
        current.append(sentence)
        current_n += n
    flush()
    return chunks


# Heurística: fragmento que habla del grupo objetivo (migrantes venezolanos).
# Incluye "venezolan*" que también captura notas sobre Venezuela como país: es un filtro
# aproximado, no una garantía. Ajusta la lista si ves falsos positivos.
TARGET_RE = re.compile(r"venezolan|migrant|migraci|refugiad|caminante|diáspora|éxodo", re.IGNORECASE)


def mentions_target(text: str) -> bool:
    return bool(TARGET_RE.search(text))
