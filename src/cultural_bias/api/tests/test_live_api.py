"""Tests de conectividad contra una API ya desplegada.

Se saltan por defecto. Para ejecutarlos:

    LIVE_API_URL=https://20-226-99-99.sslip.io pytest tests/test_live_api.py -q
"""

from __future__ import annotations

import os

import httpx
import pytest

BASE_URL = os.environ.get("LIVE_API_URL", "").rstrip("/")
pytestmark = pytest.mark.skipif(
    not BASE_URL, reason="definir LIVE_API_URL para probar una API desplegada"
)

TEXT = (
    "El gobierno anunció un nuevo permiso de residencia para los migrantes "
    "venezolanos que llegaron este año y buscan trabajo."
)


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=90) as http:
        yield http


def test_live_health_reports_real_engine(client):
    response = client.get("/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["engine"]["selected"] == "bert_pair"
    assert body["engine"]["degraded"] is False
    assert all(model["loaded"] for model in body["models"])


def test_live_openapi_has_endpoints(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/v1/analyze" in paths
    assert "/v1/health" in paths


def test_live_analyze_returns_sentiment_and_frames(client):
    response = client.post("/v1/analyze", json={"text": TEXT, "language": "es"})
    assert response.status_code == 200
    body = response.json()
    assert body["sentiment"]["prediction"] in {"Negativo", "Neutro", "Positivo"}
    assert 0 <= body["sentiment"]["confidence"] <= 100
    assert body["frames"], "la respuesta debe traer encuadres"


def test_live_dashboard_and_metrics(client):
    dashboard = client.get("/v1/dashboard/models")
    assert dashboard.status_code == 200
    assert dashboard.json()["engine"] == "bert_pair"

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "nlp_" in metrics.text
