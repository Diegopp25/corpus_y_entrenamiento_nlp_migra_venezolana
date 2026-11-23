"""Pruebas de salud, catálogo de modelos y middlewares."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import build_settings


def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["service"]
    assert response.json()["endpoints"]["analizar"] == "/v1/analyze"


def test_health(client):
    response = client.get("/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in {"ok", "degraded"}
    assert data["engine"]["selected"] == "fake"
    assert data["models"][0]["role"] == "sentiment"
    assert data["database"]["status"] == "ok"


def test_models_catalog(client):
    response = client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert data["sentimentLabels"] == ["Negativo", "Neutro", "Positivo"]
    assert len(data["frameLabels"]) == 7
    assert len(data["thresholds"]) == 7
    assert data["evaluationAvailable"] is False


def test_request_id_header(client):
    response = client.get("/v1/health", headers={"X-Request-ID": "abc123"})
    assert response.headers["X-Request-ID"] == "abc123"
    assert "X-Process-Time-Ms" in response.headers


def test_api_key_protection(tmp_path: Path):
    settings = build_settings(tmp_path, api_key="secreto")
    app = create_app(settings=settings)
    with TestClient(app) as client:
        assert client.get("/v1/health").status_code == 200
        assert client.post("/v1/analyze", json={"text": "texto"}).status_code == 401
        assert (
            client.post(
                "/v1/analyze",
                json={"text": "texto de prueba " * 10},
                headers={"X-API-Key": "secreto"},
            ).status_code
            == 200
        )
        assert (
            client.get(
                "/v1/analyses", headers={"Authorization": "Bearer secreto"}
            ).status_code
            == 200
        )


def test_rate_limit(tmp_path: Path):
    settings = build_settings(
        tmp_path, rate_limit_requests=2, rate_limit_window_seconds=60
    )
    app = create_app(settings=settings)
    with TestClient(app) as client:
        body = {"text": "texto de prueba " * 10}
        assert client.post("/v1/analyze", json=body).status_code == 200
        assert client.post("/v1/analyze", json=body).status_code == 200
        limited = client.post("/v1/analyze", json=body)
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "rate_limited"
        assert "Retry-After" in limited.headers
