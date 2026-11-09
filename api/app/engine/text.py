"""Utilidades de limpieza y conteo de texto (sin dependencias pesadas)."""

from __future__ import annotations

import html
import math
import re
import unicodedata

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\u2600-\u27BF"
    "\uFE0F"
    "]+",
    flags=re.UNICODE,
)
_SPACES_RE = re.compile(r"[ \t\r\f\v]+")
_NEWLINES_RE = re.compile(r"\n{3,}")
_WORD_RE = re.compile(r"[0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+")


def clean_text(text: str) -> str:
    """Limpia HTML, URLs y espacios. No elimina tildes ni mayúsculas."""
    text = str(text or "")
    text = html.unescape(text)
    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = _URL_RE.sub(" ", text)
    text = _EMOJI_RE.sub(" ", text)
    text = _SPACES_RE.sub(" ", text)
    text = _NEWLINES_RE.sub("\n\n", text)
    return text.strip()


def strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_for_match(text: str) -> str:
    return strip_accents(text).lower()


def count_words(text: str) -> int:
    return len(_WORD_RE.findall(text))


def reading_time_seconds(text: str, words_per_minute: int = 200) -> int:
    words = count_words(text)
    return max(5, math.ceil(words / words_per_minute * 60))


def truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "…"
