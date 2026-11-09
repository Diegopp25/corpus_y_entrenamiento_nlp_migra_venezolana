"""Agregados del corpus etiquetado para el dashboard.

Lee el CSV etiquetado (``settings.corpus_csv_path``) usando solo la librería
estándar (``csv`` + ``datetime``, sin pandas) y lo transforma en el contrato
``CorpusDashboard`` que consume el frontend.

El resultado se cachea por ``(ruta, mtime, tamaño)`` para no releer el archivo
en cada petición; si el CSV cambia en disco la siguiente petición lo recarga.
"""

from __future__ import annotations

import csv
import io
import threading
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from ..config import Settings
from ..engine.labels import FRAMES, FRAME_IDS
from ..schemas import (
    CorpusCountryStats,
    CorpusDashboard,
    FrameTally,
    MonthlyVolumePoint,
    PercentageCounts,
)

SENTIMENT_KEYS = ("negativo", "neutro", "positivo")

# Países que se desglosan en el dashboard del frontend.
_COUNTRY_ALIASES = {"colombia": "Colombia", "mexico": "México"}
_COUNTRY_ORDER = ("Colombia", "México")

# Formatos de fecha admitidos además de ISO 8601.
_DATE_FORMATS = ("%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y")

_MAX_FILESIZE_BYTES = 64 * 1024 * 1024
_CACHE_MAX_ENTRIES = 8


class CorpusError(Exception):
    """El corpus etiquetado falta o no tiene el formato esperado."""


def _normalize(value: str) -> str:
    """Lowercase sin acentos y con separadores ``_`` (para cabeceras/claves)."""
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    cleaned = "".join(char.lower() if char.isalnum() else "_" for char in plain)
    return "_".join(part for part in cleaned.split("_") if part)


# Cabecera normalizada -> frame_id (model_label, etiqueta humana e id).
_FRAME_COLUMNS: dict[str, str] = {}
for _frame_id, _frame_meta in FRAMES.items():
    for _candidate in (_frame_id, _frame_meta["model_label"], _frame_meta["label"]):
        _FRAME_COLUMNS.setdefault(_normalize(_candidate), _frame_id)


def _sentiment_key(value: str) -> str | None:
    normalized = _normalize(value)
    if normalized.startswith("neg"):
        return "negativo"
    if normalized.startswith("neu"):
        return "neutro"
    if normalized.startswith("pos"):
        return "positivo"
    return None


def _country_name(value: str) -> str | None:
    return _COUNTRY_ALIASES.get(_normalize(value))


def _is_flag(value: str) -> bool:
    """Interpreta la marca 0/1 de cada encuadre tolerando formatos comunes."""
    raw = str(value or "").strip().lower()
    if not raw:
        return False
    try:
        return float(raw) > 0
    except ValueError:
        return raw in {"si", "sí", "true", "x"}


def _parse_date(value: str) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _cell(row: list[str], index: int | None) -> str:
    if index is None or index < 0 or index >= len(row):
        return ""
    value = row[index]
    return value.strip() if isinstance(value, str) else str(value).strip()


def _column_index(header: list[str], *names: str) -> int | None:
    normalized = [_normalize(cell) for cell in header]
    for name in names:
        if name in normalized:
            return normalized.index(name)
    return None


def percentage_counts(
    counts: dict[str, int], total: int | None = None
) -> PercentageCounts:
    """Porcentajes de sentimiento que suman exactamente 100 (o 0 si no hay datos).

    Compartido por el dashboard (analyses del store) y el corpus etiquetado para
    que ambos usen el mismo criterio de redondeo (una décima).
    """
    # El store devuelve las etiquetas capitalizadas ("Negativo") y el corpus en
    # minúsculas; se aceptan ambas para compartir el mismo cálculo.
    normalized = {
        key: int(counts.get(key, counts.get(key.capitalize(), 0)) or 0)
        for key in SENTIMENT_KEYS
    }
    base = int(total) if total is not None else sum(normalized.values())
    if base <= 0:
        return PercentageCounts()
    shares = {
        key: round(100.0 * value / base, 1) for key, value in normalized.items()
    }
    remainder = round(100.0 - sum(shares.values()), 1)
    if remainder:
        winner = max(shares, key=lambda key: shares[key])
        shares[winner] = round(shares[winner] + remainder, 1)
    return PercentageCounts(**shares)


def _empty_sentiment() -> dict[str, int]:
    return {key: 0 for key in SENTIMENT_KEYS}


def _frame_breakdown(counts: dict[str, int], total: int) -> list[FrameTally]:
    """Porcentaje de artículos con 1 en cada encuadre, ordenado de mayor a menor."""
    items: list[tuple[float, int, FrameTally]] = []
    for position, frame_id in enumerate(FRAME_IDS):
        hits = int(counts.get(frame_id, 0))
        pct = round(100.0 * hits / total, 1) if total else 0.0
        items.append(
            (pct, position, FrameTally(frame=FRAMES[frame_id]["label"], percentage=pct))
        )
    items.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in items]


def _country_stats(
    accumulator: dict[str, dict[str, Any]]
) -> list[CorpusCountryStats]:
    stats: list[CorpusCountryStats] = []
    for country in _COUNTRY_ORDER:
        data = accumulator.get(country)
        if not data:
            continue
        stats.append(
            CorpusCountryStats(
                country=country,
                total_articles=int(data["total"]),
                sentiment_breakdown=percentage_counts(
                    data["sentiment"], int(data["total"])
                ),
                frame_breakdown=_frame_breakdown(
                    data["frames"], int(data["total"])
                ),
                media=sorted(data["media"]),
            )
        )
    return stats


def _delimiter_for(header_line: str) -> str:
    return ";" if header_line.count(";") > header_line.count(",") else ","


def _read_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    try:
        if path.stat().st_size > _MAX_FILESIZE_BYTES:
            raise CorpusError(
                f"El corpus etiquetado en {path.name} supera el tamaño máximo "
                f"admitido ({_MAX_FILESIZE_BYTES // (1024 * 1024)} MB)"
            )
        raw_text = path.read_text(encoding="utf-8-sig")
    except CorpusError:
        raise
    except UnicodeDecodeError as exc:
        raise CorpusError(
            f"El corpus etiquetado en {path.name} no es un CSV UTF-8 válido"
        ) from exc
    except OSError as exc:
        raise CorpusError(
            f"No se pudo leer el corpus etiquetado en {path.name}: {exc}"
        ) from exc

    if not raw_text.strip():
        raise CorpusError(f"El corpus etiquetado en {path.name} está vacío")

    header_line = raw_text.splitlines()[0]
    try:
        csv.field_size_limit(10_000_000)
    except OverflowError:  # pragma: no cover - plataformas de 32 bits
        pass

    reader = csv.reader(
        io.StringIO(raw_text, newline=""), delimiter=_delimiter_for(header_line)
    )
    try:
        header = [cell.strip() for cell in next(reader)]
        rows = [row for row in reader if row and any(str(cell).strip() for cell in row)]
    except StopIteration as exc:
        raise CorpusError(f"El corpus etiquetado en {path.name} está vacío") from exc
    except csv.Error as exc:
        raise CorpusError(
            f"El corpus etiquetado en {path.name} no es un CSV válido: {exc}"
        ) from exc
    return header, rows


def _build_corpus(path: Path) -> CorpusDashboard:
    header, rows = _read_rows(path)

    sentiment_index = _column_index(header, "sentimiento")
    if sentiment_index is None:
        raise CorpusError(
            "El corpus etiquetado no tiene la columna 'sentimiento'; "
            "se esperaba el CSV anotado de migración venezolana"
        )
    media_index = _column_index(header, "medio")
    country_index = _column_index(header, "pais")
    date_index = _column_index(header, "fecha")

    frame_indexes: dict[str, int] = {}
    for index, name in enumerate(header):
        frame_id = _FRAME_COLUMNS.get(_normalize(name))
        if frame_id and frame_id not in frame_indexes:
            frame_indexes[frame_id] = index

    total_articles = 0
    sentiment_totals = _empty_sentiment()
    frame_totals: dict[str, int] = {frame_id: 0 for frame_id in FRAME_IDS}
    media_names: set[str] = set()
    valid_dates: list[date] = []
    monthly: dict[str, dict[str, int]] = {}
    countries: dict[str, dict[str, Any]] = {}

    for row in rows:
        total_articles += 1
        sentiment = _sentiment_key(_cell(row, sentiment_index))
        if sentiment:
            sentiment_totals[sentiment] += 1

        media = _cell(row, media_index)
        if media:
            media_names.add(media)

        country = _country_name(_cell(row, country_index))
        if country:
            entry = countries.setdefault(
                country,
                {"total": 0, "sentiment": _empty_sentiment(),
                 "frames": {frame_id: 0 for frame_id in FRAME_IDS}, "media": set()},
            )
            entry["total"] += 1
            if sentiment:
                entry["sentiment"][sentiment] += 1
            if media:
                entry["media"].add(media)

        parsed = _parse_date(_cell(row, date_index))
        if parsed is not None:
            valid_dates.append(parsed)
            month = parsed.strftime("%Y-%m")
            bucket = monthly.setdefault(
                month, {"total": 0, "negativo": 0, "neutro": 0, "positivo": 0}
            )
            bucket["total"] += 1
            if sentiment:
                bucket[sentiment] += 1

        for frame_id, index in frame_indexes.items():
            if _is_flag(_cell(row, index)):
                frame_totals[frame_id] += 1
                if country:
                    countries[country]["frames"][frame_id] += 1

    date_range = {
        "from": min(valid_dates).isoformat() if valid_dates else "",
        "to": max(valid_dates).isoformat() if valid_dates else "",
    }

    return CorpusDashboard(
        generated_at=datetime.now(timezone.utc),
        source_file=str(path),
        total_articles=total_articles,
        media_count=len(media_names),
        date_range=date_range,
        sentiment_breakdown=percentage_counts(sentiment_totals, total_articles),
        frame_breakdown=_frame_breakdown(frame_totals, total_articles),
        countries=_country_stats(countries),
        monthly_volume=[
            MonthlyVolumePoint(month=month, **monthly[month])
            for month in sorted(monthly)
        ],
    )


_CACHE: dict[tuple[str, int, int], CorpusDashboard] = {}
_CACHE_LOCK = threading.Lock()


def clear_cache() -> None:
    """Vacía la caché del corpus (útil tras regenerar el CSV)."""
    with _CACHE_LOCK:
        _CACHE.clear()


def load_corpus(settings: Settings) -> CorpusDashboard:
    """Devuelve el dashboard del corpus etiquetado, cacheado por archivo.

    Lanza :class:`CorpusError` si el archivo no existe o no se puede interpretar.
    """
    path = Path(settings.corpus_csv_path)
    try:
        stat = path.stat()
    except OSError as exc:
        raise CorpusError(
            f"No se encontró el corpus etiquetado en {path}"
        ) from exc

    cache_key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
    if cached is not None:
        return cached

    dashboard = _build_corpus(path)

    with _CACHE_LOCK:
        _CACHE[cache_key] = dashboard
        while len(_CACHE) > _CACHE_MAX_ENTRIES:
            _CACHE.pop(next(iter(_CACHE)))
    return dashboard
