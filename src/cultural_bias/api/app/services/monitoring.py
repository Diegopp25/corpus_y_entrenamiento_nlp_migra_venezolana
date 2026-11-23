"""Métricas de monitoreo.

Implementación propia del formato de exposición de Prometheus para no añadir
dependencias. Expone contadores, histogramas de latencia y gauges básicos.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

_LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


def _escape(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class Monitoring:
    def __init__(self) -> None:
        self.started_at = time.time()
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, str, str], int] = defaultdict(int)
        self._analyses: dict[tuple[str, str], int] = defaultdict(int)
        self._scrape: dict[str, int] = defaultdict(int)
        self._engine_errors: dict[str, int] = defaultdict(int)
        self._latency_buckets: dict[tuple[str, float], int] = defaultdict(int)
        self._latency_sum: dict[str, float] = defaultdict(float)
        self._latency_count: dict[str, int] = defaultdict(int)

    # ------------------------------------------------------------ updates
    def observe_request(
        self, method: str, path: str, status_code: int, latency_seconds: float
    ) -> None:
        with self._lock:
            self._requests[(method, path, str(status_code))] += 1
            # Histograma acumulativo: un valor cae en todos los buckets >= latencia.
            for bucket in _LATENCY_BUCKETS:
                if latency_seconds <= bucket:
                    self._latency_buckets[(path, bucket)] += 1
            self._latency_buckets[(path, float("inf"))] += 1
            self._latency_sum[path] += latency_seconds
            self._latency_count[path] += 1

    def inc_analysis(self, engine: str, sentiment: str) -> None:
        with self._lock:
            self._analyses[(engine, sentiment)] += 1

    def inc_scrape(self, status: str) -> None:
        with self._lock:
            self._scrape[status] += 1

    def inc_engine_error(self, engine: str) -> None:
        with self._lock:
            self._engine_errors[engine] += 1

    # ------------------------------------------------------------ lectura
    @property
    def uptime_seconds(self) -> float:
        return round(time.time() - self.started_at, 1)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            total_requests = sum(self._requests.values())
            by_status: dict[str, int] = defaultdict(int)
            for (_, _, status), count in self._requests.items():
                by_status[status] += count
            total_analyses = sum(self._analyses.values())
            by_engine: dict[str, int] = defaultdict(int)
            for (engine, _), count in self._analyses.items():
                by_engine[engine] += count
            return {
                "requests_total": total_requests,
                "requests_by_status": dict(by_status),
                "errors_total": sum(
                    count
                    for (_, _, status), count in self._requests.items()
                    if str(status).startswith("5")
                ),
                "analyses_total": total_analyses,
                "analyses_by_engine": dict(by_engine),
                "scrape_jobs_total": sum(self._scrape.values()),
                "scrape_jobs_by_status": dict(self._scrape),
                "engine_errors_total": sum(self._engine_errors.values()),
                "latency_mean_ms": round(
                    sum(self._latency_sum.values())
                    / max(1, sum(self._latency_count.values()))
                    * 1000,
                    2,
                ),
            }

    def render_prometheus(self, extra_gauges: dict[str, float] | None = None) -> str:
        """Genera texto en formato Prometheus ``text/plain; version=0.0.4``."""
        lines: list[str] = []

        def metric(name: str, help_text: str, kind: str) -> None:
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} {kind}")

        with self._lock:
            requests = dict(self._requests)
            analyses = dict(self._analyses)
            scrape = dict(self._scrape)
            engine_errors = dict(self._engine_errors)
            buckets = dict(self._latency_buckets)
            latency_sum = dict(self._latency_sum)
            latency_count = dict(self._latency_count)

        metric(
            "nlp_api_requests_total",
            "Total de peticiones HTTP atendidas",
            "counter",
        )
        for (method, path, status), count in sorted(requests.items()):
            labels = (
                f'method="{_escape(method)}",path="{_escape(path)}",'
                f'status="{_escape(status)}"'
            )
            lines.append(f"nlp_api_requests_total{{{labels}}} {count}")

        metric(
            "nlp_api_request_duration_seconds",
            "Latencia de peticiones HTTP por ruta",
            "histogram",
        )
        for path in sorted(latency_count):
            for bucket in _LATENCY_BUCKETS:
                count = buckets.get((path, bucket), 0)
                lines.append(
                    f'nlp_api_request_duration_seconds_bucket{{path="{_escape(path)}",'
                    f'le="{bucket}"}} {count}'
                )
            infinite = buckets.get((path, float("inf")), 0)
            lines.append(
                f'nlp_api_request_duration_seconds_bucket{{path="{_escape(path)}",'
                f'le="+Inf"}} {infinite}'
            )
            lines.append(
                f'nlp_api_request_duration_seconds_sum{{path="{_escape(path)}"}} '
                f"{latency_sum.get(path, 0.0):.6f}"
            )
            lines.append(
                f'nlp_api_request_duration_seconds_count{{path="{_escape(path)}"}} '
                f"{latency_count.get(path, 0)}"
            )

        metric(
            "nlp_api_analyses_total",
            "Análisis de texto realizados por motor y sentimiento",
            "counter",
        )
        for (engine, sentiment), count in sorted(analyses.items()):
            lines.append(
                f'nlp_api_analyses_total{{engine="{_escape(engine)}",'
                f'sentiment="{_escape(sentiment)}"}} {count}'
            )

        metric(
            "nlp_api_scrape_jobs_total",
            "Jobs de scraping iniciados por estado",
            "counter",
        )
        for status, count in sorted(scrape.items()):
            lines.append(
                f'nlp_api_scrape_jobs_total{{status="{_escape(status)}"}} {count}'
            )

        metric(
            "nlp_api_engine_errors_total",
            "Errores de inferencia por motor",
            "counter",
        )
        for engine, count in sorted(engine_errors.items()):
            lines.append(
                f'nlp_api_engine_errors_total{{engine="{_escape(engine)}"}} {count}'
            )

        metric("nlp_api_uptime_seconds", "Segundos desde el arranque", "gauge")
        lines.append(f"nlp_api_uptime_seconds {self.uptime_seconds}")

        for name, value in (extra_gauges or {}).items():
            metric(name, name.replace("_", " "), "gauge")
            lines.append(f"{name} {float(value)}")

        return "\n".join(lines) + "\n"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
