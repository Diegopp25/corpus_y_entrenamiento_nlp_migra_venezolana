"""Persistencia en SQLite (sin ORM): análisis, jobs de scraping y eventos."""

from __future__ import annotations

import json
import math
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'api',
    engine TEXT NOT NULL DEFAULT '',
    model_version TEXT NOT NULL DEFAULT '',
    model_used TEXT NOT NULL DEFAULT '',
    title TEXT,
    text_hash TEXT NOT NULL DEFAULT '',
    text_chars INTEGER NOT NULL DEFAULT 0,
    media_name TEXT,
    country TEXT NOT NULL DEFAULT 'Desconocido',
    sentiment TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0,
    p_negativo REAL NOT NULL DEFAULT 0,
    p_neutro REAL NOT NULL DEFAULT 0,
    p_positivo REAL NOT NULL DEFAULT 0,
    tokens_count INTEGER NOT NULL DEFAULT 0,
    reading_time_seconds INTEGER NOT NULL DEFAULT 0,
    latency_ms REAL NOT NULL DEFAULT 0,
    truncated INTEGER NOT NULL DEFAULT 0,
    source_url TEXT,
    job_id TEXT,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_analyses_created ON analyses(created_at);
CREATE INDEX IF NOT EXISTS idx_analyses_sentiment ON analyses(sentiment);
CREATE INDEX IF NOT EXISTS idx_analyses_country ON analyses(country);
CREATE INDEX IF NOT EXISTS idx_analyses_source ON analyses(source);
CREATE INDEX IF NOT EXISTS idx_analyses_job ON analyses(job_id);

CREATE TABLE IF NOT EXISTS analysis_frames (
    analysis_id TEXT NOT NULL,
    frame_id TEXT NOT NULL,
    label TEXT NOT NULL,
    score REAL NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (analysis_id, frame_id),
    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_frames_frame ON analysis_frames(frame_id);

CREATE TABLE IF NOT EXISTS scrape_jobs (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    url TEXT NOT NULL,
    domain TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued',
    current_step INTEGER NOT NULL DEFAULT 0,
    total_steps INTEGER NOT NULL DEFAULT 5,
    message TEXT NOT NULL DEFAULT '',
    articles_found INTEGER NOT NULL DEFAULT 0,
    articles_analyzed INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    request_json TEXT NOT NULL DEFAULT '{}',
    steps_json TEXT NOT NULL DEFAULT '[]',
    summary_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON scrape_jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON scrape_jobs(status);

CREATE TABLE IF NOT EXISTS api_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    request_id TEXT NOT NULL DEFAULT '',
    method TEXT NOT NULL DEFAULT '',
    path TEXT NOT NULL DEFAULT '',
    status_code INTEGER NOT NULL DEFAULT 0,
    latency_ms REAL NOT NULL DEFAULT 0,
    client TEXT NOT NULL DEFAULT '',
    engine TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_events_created ON api_events(created_at);
"""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None = None) -> str:
    return (value or utcnow()).isoformat(timespec="milliseconds")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(pct / 100 * len(ordered)) - 1))
    return round(float(ordered[index]), 2)


class Store:
    """Repositorio thread-safe con una conexión por operación (WAL)."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()

    # ---------------------------------------------------------------- infra
    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def init_schema(self) -> None:
        with self._write_lock, self._connect() as connection:
            connection.executescript(SCHEMA)

    def ping(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def size_bytes(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0

    # ------------------------------------------------------------ analisis
    def save_analysis(
        self,
        payload: dict[str, Any],
        frames: list[dict[str, Any]],
        *,
        source: str = "api",
        engine: str = "",
        model_version: str = "",
        model_used: str = "",
        latency_ms: float = 0.0,
        job_id: str | None = None,
    ) -> bool:
        analysis_id = str(payload["id"])
        sentiment = payload.get("sentiment", {})
        scores = sentiment.get("scores", {})
        row = (
            analysis_id,
            payload.get("dateAnalyzed") or payload.get("date_analyzed") or iso(),
            source,
            engine,
            model_version,
            model_used,
            payload.get("title"),
            payload.get("_textHash", ""),
            len(str(payload.get("text", ""))),
            payload.get("mediaName") or payload.get("media_name"),
            payload.get("country") or "Desconocido",
            sentiment.get("prediction", "Neutro"),
            float(sentiment.get("confidence", 0.0)),
            float(scores.get("negativo", 0.0)),
            float(scores.get("neutro", 0.0)),
            float(scores.get("positivo", 0.0)),
            int(payload.get("tokensCount") or payload.get("tokens_count") or 0),
            int(payload.get("readingTimeSeconds") or payload.get("reading_time_seconds") or 0),
            float(latency_ms),
            1 if payload.get("_truncated") else 0,
            payload.get("sourceUrl") or payload.get("source_url"),
            job_id,
            _json(payload),
        )
        try:
            with self._write_lock, self._connect() as connection:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO analyses (
                        id, created_at, source, engine, model_version, model_used,
                        title, text_hash, text_chars, media_name, country, sentiment,
                        confidence, p_negativo, p_neutro, p_positivo, tokens_count,
                        reading_time_seconds, latency_ms, truncated, source_url,
                        job_id, payload_json
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    row,
                )
                connection.execute(
                    "DELETE FROM analysis_frames WHERE analysis_id = ?", (analysis_id,)
                )
                connection.executemany(
                    """
                    INSERT OR REPLACE INTO analysis_frames
                        (analysis_id, frame_id, label, score, is_active)
                    VALUES (?,?,?,?,?)
                    """,
                    [
                        (
                            analysis_id,
                            frame["id"],
                            frame.get("label", frame["id"]),
                            float(frame.get("score", 0.0)),
                            1 if frame.get("isActive") or frame.get("is_active") else 0,
                        )
                        for frame in frames
                    ],
                )
            return True
        except sqlite3.Error:
            return False

    def get_analysis(self, analysis_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM analyses WHERE id = ?", (analysis_id,)
            ).fetchone()
        if row is None:
            return None
        return _loads(row["payload_json"], None)

    def list_analyses(
        self,
        limit: int = 20,
        offset: int = 0,
        *,
        sentiment: str | None = None,
        country: str | None = None,
        source: str | None = None,
        since: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if sentiment:
            clauses.append("sentiment = ?")
            params.append(sentiment)
        if country:
            clauses.append("country = ?")
            params.append(country)
        if source:
            clauses.append("source = ?")
            params.append(source)
        if since:
            clauses.append("created_at >= ?")
            params.append(since)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT id, created_at, title, media_name, country, sentiment, confidence,
                   source, engine, latency_ms, tokens_count
            FROM analyses {where}
            ORDER BY created_at DESC LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def count_analyses(
        self,
        *,
        since: str | None = None,
        sentiment: str | None = None,
        country: str | None = None,
        source: str | None = None,
    ) -> int:
        clauses: list[str] = []
        params: list[Any] = []
        if since:
            clauses.append("created_at >= ?")
            params.append(since)
        if sentiment:
            clauses.append("sentiment = ?")
            params.append(sentiment)
        if country:
            clauses.append("country = ?")
            params.append(country)
        if source:
            clauses.append("source = ?")
            params.append(source)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT COUNT(*) AS total FROM analyses {where}", params
            ).fetchone()
        return int(row["total"]) if row else 0

    def sentiment_counts(self, since: str | None = None) -> dict[str, int]:
        params: list[Any] = []
        where = ""
        if since:
            where = "WHERE created_at >= ?"
            params.append(since)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT sentiment, COUNT(*) AS total FROM analyses {where} "
                "GROUP BY sentiment",
                params,
            ).fetchall()
        counts = {"Negativo": 0, "Neutro": 0, "Positivo": 0}
        for row in rows:
            if row["sentiment"] in counts:
                counts[row["sentiment"]] = int(row["total"])
        return counts

    def frame_counts(self, since: str | None = None) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ""
        if since:
            where = "AND a.created_at >= ?"
            params.append(since)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT f.frame_id, f.label, COUNT(*) AS total
                FROM analysis_frames f
                JOIN analyses a ON a.id = f.analysis_id
                WHERE f.is_active = 1 {where}
                GROUP BY f.frame_id, f.label
                ORDER BY total DESC
                """,
                params,
            ).fetchall()
            total_row = connection.execute(
                f"SELECT COUNT(*) AS total FROM analyses a WHERE 1=1 {where}", params
            ).fetchone()
        total = int(total_row["total"]) if total_row else 0
        return [
            {
                "frame": row["label"],
                "frame_id": row["frame_id"],
                "count": int(row["total"]),
                "percentage": round(100.0 * int(row["total"]) / total, 1) if total else 0.0,
            }
            for row in rows
        ]

    def country_counts(self, since: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ""
        if since:
            where = "WHERE created_at >= ?"
            params.append(since)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT country, sentiment, COUNT(*) AS total
                FROM analyses {where}
                GROUP BY country, sentiment
                ORDER BY total DESC
                """,
                params,
            ).fetchall()
        aggregated: dict[str, dict[str, Any]] = {}
        for row in rows:
            entry = aggregated.setdefault(
                row["country"],
                {"country": row["country"], "count": 0,
                 "sentiment": {"Negativo": 0, "Neutro": 0, "Positivo": 0}},
            )
            entry["count"] += int(row["total"])
            if row["sentiment"] in entry["sentiment"]:
                entry["sentiment"][row["sentiment"]] = int(row["total"])
        ordered = sorted(aggregated.values(), key=lambda item: item["count"], reverse=True)
        return ordered[:limit]

    def media_counts(self, since: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = "WHERE media_name IS NOT NULL AND media_name != ''"
        if since:
            where += " AND created_at >= ?"
            params.append(since)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT media_name, sentiment, COUNT(*) AS total
                FROM analyses {where}
                GROUP BY media_name, sentiment
                """,
                params,
            ).fetchall()
        aggregated: dict[str, dict[str, Any]] = {}
        for row in rows:
            entry = aggregated.setdefault(
                row["media_name"],
                {"media": row["media_name"], "count": 0,
                 "sentiment": {"Negativo": 0, "Neutro": 0, "Positivo": 0}},
            )
            entry["count"] += int(row["total"])
            if row["sentiment"] in entry["sentiment"]:
                entry["sentiment"][row["sentiment"]] = int(row["total"])
        ordered = sorted(aggregated.values(), key=lambda item: item["count"], reverse=True)
        return ordered[:limit]

    def engine_counts(self, since: str | None = None) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ""
        if since:
            where = "WHERE created_at >= ?"
            params.append(since)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT engine, COUNT(*) AS total FROM analyses {where} "
                "GROUP BY engine ORDER BY total DESC",
                params,
            ).fetchall()
        return [{"engine": row["engine"] or "desconocido", "count": int(row["total"])} for row in rows]

    def latency_stats(self, since: str | None = None) -> dict[str, float]:
        params: list[Any] = []
        where = ""
        if since:
            where = "WHERE created_at >= ?"
            params.append(since)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT latency_ms FROM analyses {where}", params
            ).fetchall()
        values = [float(row["latency_ms"]) for row in rows if row["latency_ms"]]
        if not values:
            return {"count": 0, "mean": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0}
        return {
            "count": len(values),
            "mean": round(sum(values) / len(values), 2),
            "p50": _percentile(values, 50),
            "p95": _percentile(values, 95),
            "p99": _percentile(values, 99),
        }

    def avg_confidence(self, since: str | None = None) -> float:
        params: list[Any] = []
        where = ""
        if since:
            where = "WHERE created_at >= ?"
            params.append(since)
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT AVG(confidence) AS value FROM analyses {where}", params
            ).fetchone()
        return round(float(row["value"]), 1) if row and row["value"] is not None else 0.0

    def daily_sentiment_counts(self, days: int = 30) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT substr(created_at, 1, 10) AS day,
                       sentiment, COUNT(*) AS total
                FROM analyses
                WHERE created_at >= datetime('now', ?)
                GROUP BY day, sentiment
                ORDER BY day ASC
                """,
                (f"-{int(days)} days",),
            ).fetchall()
        aggregated: dict[str, dict[str, Any]] = {}
        for row in rows:
            entry = aggregated.setdefault(
                row["day"],
                {"date": row["day"], "total": 0, "negativo": 0, "neutro": 0, "positivo": 0},
            )
            key = str(row["sentiment"]).lower()
            if key in ("negativo", "neutro", "positivo"):
                entry[key] += int(row["total"])
            entry["total"] += int(row["total"])
        return list(aggregated.values())

    # -------------------------------------------------------------- jobs
    def create_job(
        self,
        job_id: str,
        url: str,
        domain: str,
        request: dict[str, Any],
        total_steps: int = 5,
    ) -> None:
        now = iso()
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO scrape_jobs
                    (id, created_at, updated_at, url, domain, status, current_step,
                     total_steps, message, request_json)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (job_id, now, now, url, domain, "queued", 0, total_steps,
                 "Trabajo en cola", _json(request)),
            )

    def update_job(self, job_id: str, **fields: Any) -> None:
        if not fields:
            return
        allowed = {
            "status", "current_step", "total_steps", "message", "articles_found",
            "articles_analyzed", "error", "summary_json", "steps_json", "domain",
        }
        assignments = []
        params: list[Any] = []
        for key, value in fields.items():
            if key not in allowed:
                continue
            assignments.append(f"{key} = ?")
            params.append(_json(value) if key in ("summary_json", "steps_json") else value)
        if not assignments:
            return
        assignments.append("updated_at = ?")
        params.append(iso())
        params.append(job_id)
        with self._write_lock, self._connect() as connection:
            connection.execute(
                f"UPDATE scrape_jobs SET {', '.join(assignments)} WHERE id = ?", params
            )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM scrape_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        if row is None:
            return None
        job = dict(row)
        job["request"] = _loads(job.pop("request_json", "{}"), {})
        job["steps"] = _loads(job.pop("steps_json", "[]"), [])
        job["summary"] = _loads(job.pop("summary_json", None), None)
        return job

    def list_jobs(self, limit: int = 20, status: str | None = None) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ""
        if status:
            where = "WHERE status = ?"
            params.append(status)
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT id, created_at, updated_at, url, domain, status, current_step, "
                f"total_steps, message, articles_found, articles_analyzed, error "
                f"FROM scrape_jobs {where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def job_stats(self) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS total FROM scrape_jobs GROUP BY status"
            ).fetchall()
        stats = {"total": 0, "completed": 0, "error": 0, "running": 0}
        for row in rows:
            total = int(row["total"])
            stats["total"] += total
            status = row["status"]
            if status == "completed":
                stats["completed"] += total
            elif status == "error":
                stats["error"] += total
            elif status in ("queued", "connecting", "crawling", "cleaning", "analyzing"):
                stats["running"] += total
        return stats

    def prune_jobs(self, ttl_hours: int = 24) -> None:
        with self._write_lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM scrape_jobs WHERE created_at < datetime('now', ?)",
                (f"-{int(ttl_hours)} hours",),
            )

    # ------------------------------------------------------------ eventos
    def record_event(
        self,
        *,
        request_id: str,
        method: str,
        path: str,
        status_code: int,
        latency_ms: float,
        client: str = "",
        engine: str = "",
    ) -> None:
        try:
            with self._write_lock, self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO api_events
                        (created_at, request_id, method, path, status_code,
                         latency_ms, client, engine)
                    VALUES (?,?,?,?,?,?,?,?)
                    """,
                    (iso(), request_id, method, path, status_code,
                     float(latency_ms), client, engine),
                )
        except sqlite3.Error:
            pass

    def event_stats(self, since: str | None = None) -> dict[str, Any]:
        params: list[Any] = []
        where = ""
        if since:
            where = "WHERE created_at >= ?"
            params.append(since)
        with self._connect() as connection:
            total_row = connection.execute(
                f"SELECT COUNT(*) AS total FROM api_events {where}", params
            ).fetchone()
            status_rows = connection.execute(
                f"SELECT status_code, COUNT(*) AS total FROM api_events {where} "
                "GROUP BY status_code",
                params,
            ).fetchall()
            latency_rows = connection.execute(
                f"SELECT latency_ms FROM api_events {where}", params
            ).fetchall()
        latencies = [float(row["latency_ms"]) for row in latency_rows]
        return {
            "total": int(total_row["total"]) if total_row else 0,
            "by_status": {
                str(row["status_code"]): int(row["total"]) for row in status_rows
            },
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
            "p99": _percentile(latencies, 99),
        }

    def prune_events(self, days: int = 30) -> None:
        with self._write_lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM api_events WHERE created_at < datetime('now', ?)",
                (f"-{int(days)} days",),
            )
