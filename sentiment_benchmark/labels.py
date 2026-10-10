"""Normalización de etiquetas de modelos a las clases canónicas."""
from __future__ import annotations

import re

from sentiment_benchmark.config import CLASSES

_STARS = re.compile(r"^\s*([1-5])\s*(star|estrella)", re.IGNORECASE)


def normalize_label(raw: str) -> str | None:
    """Devuelve 'negativo' | 'neutro' | 'positivo', o None si no se reconoce.

    Reconoce NEG/NEU/POS, negative/neutral/positive, Negativo/Positivo y '1 star'..'5 stars'.
    """
    s = str(raw).strip().lower()
    m = _STARS.match(s)
    if m:
        n = int(m.group(1))
        return CLASSES[0] if n <= 2 else CLASSES[1] if n == 3 else CLASSES[2]
    if s.startswith("neg"):
        return "negativo"
    if s.startswith("neu"):
        return "neutro"
    if s.startswith("pos"):
        return "positivo"
    return None


NO_APLICA = "no_aplica"


def normalize_gold(raw: str) -> str | None:
    """Etiquetas manuales: negativo/neutro/positivo/no_aplica (y abreviaturas '-', '0', '+', 'na')."""
    s = str(raw).strip().lower().replace(" ", "_")
    if s in {"no_aplica", "noaplica", "na", "n/a", "n.a."}:
        return NO_APLICA
    return {"-": "negativo", "0": "neutro", "+": "positivo"}.get(s) or normalize_label(s)


def class_groups(id2label: dict, label_map: dict | None = None) -> list[tuple[int, list[int]]]:
    """Agrupa los índices de salida del modelo por clase canónica.

    Devuelve [(índice_de_clase_canónica, [índices_de_logit, ...]), ...].
    Lanza ValueError si alguna etiqueta no se reconoce (p. ej. 'LABEL_0'):
    en ese caso hay que declarar `label_map` en config.py.
    """
    label_map = label_map or {}
    groups: dict[str, list[int]] = {c: [] for c in CLASSES}
    for idx, raw in id2label.items():
        cls = label_map.get(raw) or label_map.get(str(raw)) or normalize_label(str(raw))
        if cls is None:
            raise ValueError(
                f"Etiqueta no reconocida {raw!r} (id2label={id2label}). "
                "Agrega un `label_map` al ModelSpec en config.py."
            )
        groups[cls].append(int(idx))
    return [(CLASSES.index(c), ids) for c, ids in groups.items() if ids]
