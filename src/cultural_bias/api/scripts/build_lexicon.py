"""Genera el léxico de respaldo a partir del corpus etiquetado.

Uso (desde la raíz del repo):
    api/.venv/Scripts/python.exe api/scripts/build_lexicon.py \
        --csv Data/dataset_migracion_venezolana_labeled.csv \
        --output api/app/resources/lexicon.json

El resultado es un JSON con tres bloques:
* ``sentiment``: término -> peso log-odds por clase (Negativo/Neutro/Positivo).
* ``frames``: frame_id -> término -> peso log-odds frente al resto.
* ``bias_terms``: término -> {"bias_type", "weight"} para resaltar en el texto.

Se usa cuando no hay pesos BETO disponibles (CI, equipos sin GPU/modelos).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

FRAME_COLUMNS = {
    "Acceso_a_servicios": "acceso_servicios",
    "Empleo_y_economía": "empleo_economia",
    "Integración_social": "integracion_social",
    "Otros": "otros",
    "Politica_migratoria": "politica_migratoria",
    "Seguridad": "seguridad",
    "Transito_migratorio": "transito_migratorio",
}

STOPWORDS = {
    "para", "como", "pero", "porque", "sobre", "entre", "desde", "hasta",
    "donde", "cuando", "también", "aunque", "mientras", "según", "tras",
    "este", "esta", "estos", "estas", "ese", "esa", "esos", "esas", "aquel",
    "sus", "más", "menos", "muy", "sin", "con", "por", "los", "las", "del",
    "que", "una", "unos", "unas", "ser", "fue", "son", "han", "hay", "sus",
    "the", "and", "for", "with", "from", "that", "this", "was", "were",
}

_WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+")


def normalize_term(term: str) -> str:
    term = unicodedata.normalize("NFKD", term.lower())
    return "".join(char for char in term if not unicodedata.combining(char))


def tokenize(text: str) -> list[str]:
    terms = [normalize_term(token) for token in _WORD_RE.findall(text or "")]
    return [term for term in terms if len(term) >= 3 and term not in STOPWORDS]


def log_odds(positive: Counter, negative: Counter, vocab_size: int, alpha: float = 0.5) -> dict[str, float]:
    pos_total = sum(positive.values()) or 1
    neg_total = sum(negative.values()) or 1
    scores: dict[str, float] = {}
    for term in set(positive) | set(negative):
        pos_rate = (positive.get(term, 0) + alpha) / (pos_total + alpha * vocab_size)
        neg_rate = (negative.get(term, 0) + alpha) / (neg_total + alpha * vocab_size)
        scores[term] = math.log(pos_rate / neg_rate)
    return scores


def top_weights(scores: dict[str, float], limit: int, minimum: float = 0.15) -> dict[str, float]:
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]
    return {
        term: round(max(minimum, min(2.5, weight)), 3)
        for term, weight in ranked
        if weight > 0
    }


def build(csv_path: Path) -> dict:
    sentiment_counts: dict[str, Counter] = {
        "Negativo": Counter(),
        "Neutro": Counter(),
        "Positivo": Counter(),
    }
    sentiment_docs: dict[str, Counter] = {
        "Negativo": Counter(),
        "Neutro": Counter(),
        "Positivo": Counter(),
    }
    frame_counts: dict[str, dict[str, Counter]] = {
        frame_id: {"si": Counter(), "no": Counter()} for frame_id in FRAME_COLUMNS.values()
    }
    frame_docs: dict[str, dict[str, Counter]] = {
        frame_id: {"si": Counter(), "no": Counter()} for frame_id in FRAME_COLUMNS.values()
    }
    rows = 0

    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        frame_lookup = {
            source: target for source, target in FRAME_COLUMNS.items() if source in fieldnames
        }
        if not frame_lookup:
            raise SystemExit(
                f"No se encontraron columnas de encuadre en {csv_path}. "
                f"Columnas: {fieldnames}"
            )
        for row in reader:
            body = row.get("Cuerpo") or ""
            if not body:
                continue
            rows += 1
            sentiment = (row.get("sentimiento") or "").strip().capitalize()
            tokens = tokenize(body)
            unique = set(tokens)
            if sentiment in sentiment_counts:
                sentiment_counts[sentiment].update(tokens)
                sentiment_docs[sentiment].update(unique)
            for source, frame_id in frame_lookup.items():
                try:
                    is_positive = float(row.get(source) or 0) >= 0.5
                except ValueError:
                    is_positive = False
                bucket = "si" if is_positive else "no"
                frame_counts[frame_id][bucket].update(tokens)
                frame_docs[frame_id][bucket].update(unique)

    vocabulary = set()
    for counter in sentiment_counts.values():
        vocabulary.update(counter)
    vocab_size = len(vocabulary) or 1

    def supported_terms(doc_counters: list[Counter], minimum_docs: int = 2) -> set[str]:
        """Términos que aparecen en al menos ``minimum_docs`` documentos."""
        supported: set[str] = set()
        for counter in doc_counters:
            supported.update(
                term for term, count in counter.items() if count >= minimum_docs
            )
        return supported

    sentiment_lexicon: dict[str, dict[str, float]] = {}
    all_sentiment_docs = [sentiment_docs[label] for label in sentiment_counts]
    sentiment_supported = supported_terms(all_sentiment_docs, minimum_docs=2)
    # Descartar términos demasiado frecuentes (ruido genérico del corpus).
    generic = {
        term
        for term, count in Counter(
            {term: sum(c[term] for c in all_sentiment_docs) for term in sentiment_supported}
        ).items()
        if count > max(10, 0.45 * rows)
    }
    for label, counter in sentiment_counts.items():
        rest = Counter()
        for other_label, other_counter in sentiment_counts.items():
            if other_label != label:
                rest.update(other_counter)
        scores = log_odds(counter, rest, vocab_size)
        filtered = {
            term: score
            for term, score in scores.items()
            if term in sentiment_supported and term not in generic
        }
        sentiment_lexicon[label] = top_weights(filtered, limit=120)

    frames_lexicon: dict[str, dict[str, float]] = {}
    for frame_id, buckets in frame_counts.items():
        if not buckets["si"]:
            continue
        scores = log_odds(buckets["si"], buckets["no"], vocab_size)
        supported = supported_terms(
            [frame_docs[frame_id]["si"], frame_docs[frame_id]["no"]], minimum_docs=2
        )
        filtered = {term: score for term, score in scores.items() if term in supported}
        frames_lexicon[frame_id] = top_weights(filtered, limit=70)

    bias_terms: dict[str, dict] = {}
    for frame_id, terms in frames_lexicon.items():
        if frame_id in ("seguridad", "politica_migratoria", "acceso_servicios"):
            bias_type = "colombia"
        elif frame_id in ("empleo_economia", "transito_migratorio", "integracion_social"):
            bias_type = "mexico"
        else:
            bias_type = "positive"
        for term, weight in list(terms.items())[:20]:
            bias_terms[term] = {
                "bias_type": bias_type,
                "weight": round(2.0 + weight * 1.5, 2),
            }

    return {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source_csv": str(csv_path),
            "rows": rows,
            "vocabulary": vocab_size,
            "method": "log-odds con suavizado de Laplace (alpha=0.5), df>=2, sin genéricos",
        },
        "sentiment": sentiment_lexicon,
        "frames": frames_lexicon,
        "bias_terms": bias_terms,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("Data/dataset_migracion_venezolana_labeled.csv"),
        help="CSV etiquetado del corpus",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("api/app/resources/lexicon.json"),
        help="Ruta del JSON de salida",
    )
    args = parser.parse_args()
    if not args.csv.exists():
        raise SystemExit(f"No existe el CSV: {args.csv}")
    lexicon = build(args.csv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(lexicon, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(
        f"OK -> {args.output} | filas={lexicon['meta']['rows']} | "
        f"vocabulario={lexicon['meta']['vocabulary']} | "
        f"sentimiento={len(lexicon['sentiment'])} clases | "
        f"encuadres={len(lexicon['frames'])}"
    )


if __name__ == "__main__":
    main()
