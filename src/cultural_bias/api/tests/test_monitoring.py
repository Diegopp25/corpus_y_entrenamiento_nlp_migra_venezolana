"""Pruebas de las métricas Prometheus y las estadísticas de monitoreo."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import FakeEngine, build_settings

NEGATIVE_TEXT = (
    "La ola de inseguridad crece en la frontera y los ciudadanos exigen más "
    "control policial tras los atracos y homicidios registrados por bandas criminales."
)

STATS_KEYS = {
    "generatedAt",
    "uptimeSeconds",
    "requestsTotal",
    "requestsByStatus",
    "errorsTotal",
    "analysesTotal",
    "analysesByEngine",
    "scrapeJobsTotal",
    "latencyMs",
    "engine",
    "database",
    "storeEventsEnabled",
}


def _seed_analysis(client: TestClient) -> None:
    response = client.post(
        "/v1/analyze",
        json={"text": NEGATIVE_TEXT, "mediaName": "El Tiempo", "title": "Prueba"},
    )
    assert response.status_code == 200, response.text


def test_metrics_prometheus_format(client: TestClient) -> None:
    response = client.get("/metrics")
    assert response.status_code == 200, response.text

    content_type = response.headers["content-type"]
    assert content_type.startswith("text/plain")
    assert "version=0.0.4" in content_type
    assert "charset=utf-8" in content_type

    body = response.text
    assert "# HELP nlp_api_requests_total" in body
    assert "# TYPE nlp_api_requests_total counter" in body
    assert "# TYPE nlp_api_uptime_seconds gauge" in body
    assert "nlp_api_uptime_seconds " in body
    for gauge in (
        "nlp_api_analyses_stored",
        "nlp_api_scrape_jobs_stored",
        "nlp_api_engine_degraded",
    ):
        assert f"# TYPE {gauge} gauge" in body
    assert "nlp_api_analyses_stored 0" in body
    assert "nlp_api_scrape_jobs_stored 0" in body
    assert "nlp_api_engine_degraded 0" in body


def test_metrics_reflect_store_and_analyses(client: TestClient) -> None:
    _seed_analysis(client)

    response = client.get("/metrics")
    assert response.status_code == 200, response.text
    body = response.text

    assert "nlp_api_analyses_stored 1" in body
    assert (
        'nlp_api_analyses_total{engine="fake",sentiment="Negativo"} 1' in body
    )
    # Las peticiones anteriores quedan contadas con sus etiquetas.
    assert "nlp_api_requests_total{" in body
    assert 'path="/v1/analyze"' in body


def test_monitoring_stats(client: TestClient) -> None:
    _seed_analysis(client)

    response = client.get("/v1/monitoring/stats")
    assert response.status_code == 200, response.text
    data = response.json()

    assert set(data) == STATS_KEYS
    assert datetime.fromisoformat(data["generatedAt"].replace("Z", "+00:00"))
    assert data["uptimeSeconds"] >= 0
    assert data["analysesTotal"] == 1
    assert data["analysesByEngine"] == {"fake": 1}
    assert data["scrapeJobsTotal"] == 0
    assert set(data["latencyMs"]) == {"mean", "p50", "p95", "p99"}
    assert data["latencyMs"]["p50"] >= 0

    assert data["engine"]["selected"] == "fake"
    assert data["engine"]["requested"] == "lexicon"
    assert data["engine"]["degraded"] is False

    assert data["database"]["status"] == "ok"
    assert data["database"]["analyses"] == 1
    assert data["database"]["sizeBytes"] >= 0

    assert data["storeEventsEnabled"] is True
    assert data["requestsTotal"] >= 1
    assert data["requestsByStatus"].get("200", 0) >= 1


def test_monitoring_stats_without_store_events(tmp_path: Path) -> None:
    settings = build_settings(tmp_path, store_events=False)
    app = create_app(settings=settings, engine=FakeEngine())
    with TestClient(app) as client:
        _seed_analysis(client)
        response = client.get("/v1/monitoring/stats")
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["storeEventsEnabled"] is False
    # Sin eventos persistidos mandan los contadores en memoria.
    assert data["requestsTotal"] >= 1
    assert data["requestsByStatus"].get("200", 0) >= 1
    assert data["analysesTotal"] == 1
    assert data["database"]["analyses"] == 1


def test_metrics_gauges_after_empty_store(client: TestClient) -> None:
    body = client.get("/metrics").text
    assert "nlp_api_engine_degraded 0" in body
    assert "nlp_api_analyses_stored 0" in body
