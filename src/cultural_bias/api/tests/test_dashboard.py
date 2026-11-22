"""Pruebas de los endpoints del dashboard agregado."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import FakeEngine, build_settings

NEGATIVE_TEXT = (
    "La ola de inseguridad crece en la frontera y los ciudadanos exigen más "
    "control policial tras los atracos y homicidios registrados por bandas criminales."
)
POSITIVE_TEXT = (
    "Los migrantes encuentran trabajo y oportunidades de empleo en la industria "
    "y aportan a la economía de las ciudades que los reciben."
)
NEUTRAL_TEXT = (
    "El gobierno presentó este martes un informe con cifras oficiales sobre el "
    "programa de atención a la población migrante."
)

OVERVIEW_KEYS = {
    "generatedAt",
    "totalAnalyses",
    "analysesToday",
    "analysesLast7d",
    "avgConfidence",
    "sentiment",
    "sentimentPct",
    "topFrames",
    "countries",
    "media",
    "engines",
    "latencyMs",
    "scrapeJobs",
    "uptimeSeconds",
    "engine",
    "degraded",
}
LATENCY_KEYS = {"count", "mean", "p50", "p95", "p99"}
SUMMARY_KEYS = {
    "id",
    "createdAt",
    "title",
    "mediaName",
    "country",
    "sentiment",
    "confidence",
    "source",
    "engine",
    "latencyMs",
}
MODEL_METRIC_KEYS = {
    "modelName",
    "architecture",
    "role",
    "accuracy",
    "precision",
    "recall",
    "f1Score",
    "samples",
    "isBest",
}
FRAME_EVALUATION_KEYS = {
    "frame",
    "frameId",
    "precision",
    "recall",
    "f1",
    "support",
    "threshold",
}

CORPUS_HEADER = [
    "ID",
    "Titulo",
    "URL",
    "Autor",
    "Medio",
    "Pais",
    "Fecha",
    "Cuerpo",
    "sentimiento",
    "Acceso_a_servicios",
    "Empleo_y_economía",
    "Integración_social",
    "Otros",
    "Politica_migratoria",
    "Seguridad",
    "Transito_migratorio",
]

CORPUS_ROWS = [
    ["articulo_1", "A", "https://x/1", "Autor", "Semana", "Colombia",
     "2025-01-15", "cuerpo", "Negativo", "1", "0", "0", "0", "0", "1", "0"],
    ["articulo_2", "B", "https://x/2", "Autor", "El Tiempo", "Colombia",
     "2025-02-10", "cuerpo", "Neutro", "0", "0", "0", "0", "1", "0", "0"],
    ["articulo_3", "C", "https://x/3", "Autor", "Milenio", "México",
     "2025-02-20", "cuerpo", "Positivo", "0", "1", "0", "0", "0", "0", "1"],
    ["articulo_4", "D", "https://x/4", "Autor", "Reforma", "México",
     "2025-03-05", "cuerpo", "Negativo", "1", "0", "0", "0", "0", "0", "0"],
    ["articulo_5", "E", "https://x/5", "Autor", "El Universal", "México",
     "2025-03-15", "cuerpo", "Neutro", "0", "0", "0", "0", "0", "1", "0"],
]


def _write_corpus(tmp_path: Path) -> Path:
    path = tmp_path / "corpus_prueba.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CORPUS_HEADER)
        writer.writerows(CORPUS_ROWS)
    return path


def _seed_analyses(client: TestClient) -> None:
    payloads = [
        {"text": NEGATIVE_TEXT, "title": "Inseguridad", "mediaName": "El Tiempo",
         "country": "Colombia"},
        {"text": POSITIVE_TEXT, "title": "Empleo", "mediaName": "Milenio",
         "country": "México"},
        {"text": NEUTRAL_TEXT, "title": "Informe", "mediaName": "El Tiempo",
         "country": "Colombia"},
    ]
    for payload in payloads:
        response = client.post("/v1/analyze", json=payload)
        assert response.status_code == 200, response.text


def test_overview_without_data(client: TestClient) -> None:
    response = client.get("/v1/dashboard/overview")
    assert response.status_code == 200, response.text
    data = response.json()

    assert set(data) == OVERVIEW_KEYS
    assert data["totalAnalyses"] == 0
    assert data["analysesToday"] == 0
    assert data["analysesLast7d"] == 0
    assert data["avgConfidence"] == 0
    assert data["sentiment"] == {"negativo": 0, "neutro": 0, "positivo": 0}
    assert data["sentimentPct"] == {"negativo": 0.0, "neutro": 0.0, "positivo": 0.0}
    assert data["topFrames"] == []
    assert data["countries"] == []
    assert data["media"] == []
    assert data["engines"] == []
    assert set(data["latencyMs"]) == LATENCY_KEYS
    assert data["latencyMs"]["count"] == 0
    assert data["scrapeJobs"] == {"total": 0, "completed": 0, "error": 0, "running": 0}
    assert data["uptimeSeconds"] >= 0
    assert data["engine"] == "fake"
    assert data["degraded"] is False
    assert datetime.fromisoformat(data["generatedAt"].replace("Z", "+00:00"))


def test_overview_with_data(client: TestClient) -> None:
    _seed_analyses(client)

    response = client.get("/v1/dashboard/overview")
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["totalAnalyses"] == 3
    assert data["analysesToday"] == 3
    assert data["analysesLast7d"] == 3
    assert 0 < data["avgConfidence"] <= 100
    assert data["sentiment"] == {"negativo": 1, "neutro": 1, "positivo": 1}
    assert sum(data["sentimentPct"].values()) == pytest.approx(100.0, abs=0.11)

    labels = {item["frame"] for item in data["topFrames"]}
    assert {"Seguridad", "Empleo y economía", "Integración social"} <= labels
    for item in data["topFrames"]:
        assert set(item) == {"frame", "percentage"}
        assert 0 < item["percentage"] <= 100
    assert len(data["topFrames"]) <= 5

    countries = {item["country"]: item for item in data["countries"]}
    assert set(countries) == {"Colombia", "México"}
    for item in data["countries"]:
        assert set(item) == {"country", "count", "sentiment"}
        assert set(item["sentiment"]) == {"negativo", "neutro", "positivo"}
    assert countries["Colombia"]["count"] == 2
    assert countries["Colombia"]["sentiment"] == {
        "negativo": 1, "neutro": 1, "positivo": 0
    }
    assert countries["México"]["count"] == 1
    assert countries["México"]["sentiment"] == {
        "negativo": 0, "neutro": 0, "positivo": 1
    }

    media = {item["media"]: item for item in data["media"]}
    assert set(media) == {"El Tiempo", "Milenio"}
    assert media["El Tiempo"]["count"] == 2
    for item in data["media"]:
        assert set(item) == {"media", "count", "sentiment"}

    assert data["engines"] == [{"engine": "fake", "count": 3}]

    latency = data["latencyMs"]
    assert set(latency) == LATENCY_KEYS
    assert latency["count"] == 3
    assert latency["mean"] > 0
    assert 0 < latency["p50"] <= latency["p95"] <= latency["p99"]

    assert data["scrapeJobs"]["total"] == 0
    assert data["engine"] == "fake"
    assert data["degraded"] is False


def test_timeseries(client: TestClient) -> None:
    _seed_analyses(client)

    response = client.get("/v1/dashboard/timeseries", params={"days": 7})
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["days"] == 7
    assert set(data["items"][0]) == {"date", "total", "negativo", "neutro", "positivo"}
    assert sum(item["total"] for item in data["items"]) == 3
    for item in data["items"]:
        assert len(item["date"]) == 10
        assert item["total"] == item["negativo"] + item["neutro"] + item["positivo"]


def test_timeseries_defaults_and_validation(client: TestClient) -> None:
    default = client.get("/v1/dashboard/timeseries")
    assert default.status_code == 200
    assert default.json()["days"] == 30

    assert client.get("/v1/dashboard/timeseries", params={"days": 0}).status_code == 422
    assert (
        client.get("/v1/dashboard/timeseries", params={"days": 366}).status_code == 422
    )


def test_corpus_dashboard(tmp_path: Path) -> None:
    corpus_path = _write_corpus(tmp_path)
    settings = build_settings(tmp_path, corpus_csv_path=corpus_path)
    app = create_app(settings=settings, engine=FakeEngine())
    with TestClient(app) as client:
        response = client.get("/v1/dashboard/corpus")
        assert response.status_code == 200, response.text
        data = response.json()

        assert data["sourceFile"].endswith("corpus_prueba.csv")
        assert datetime.fromisoformat(data["generatedAt"].replace("Z", "+00:00"))
        assert data["totalArticles"] == 5
        assert data["mediaCount"] == 5
        assert data["dateRange"] == {"from": "2025-01-15", "to": "2025-03-15"}

        sentiment = data["sentimentBreakdown"]
        assert sentiment == {"negativo": 40.0, "neutro": 40.0, "positivo": 20.0}
        assert sum(sentiment.values()) == pytest.approx(100.0, abs=0.11)

        frames = {item["frame"]: item["percentage"] for item in data["frameBreakdown"]}
        assert len(frames) == 7
        assert frames["Acceso a servicios"] == 40.0
        assert frames["Seguridad"] == 40.0
        assert frames["Política migratoria"] == 20.0
        assert frames["Empleo y economía"] == 20.0
        assert frames["Tránsito migratorio"] == 20.0
        assert frames["Integración social"] == 0.0
        assert frames["Otros"] == 0.0

        countries = {item["country"]: item for item in data["countries"]}
        assert list(countries) == ["Colombia", "México"]
        colombia = countries["Colombia"]
        assert colombia["totalArticles"] == 2
        assert colombia["media"] == ["El Tiempo", "Semana"]
        assert colombia["sentimentBreakdown"] == {
            "negativo": 50.0, "neutro": 50.0, "positivo": 0.0
        }
        assert len(colombia["frameBreakdown"]) == 7
        mexico = countries["México"]
        assert mexico["totalArticles"] == 3
        assert mexico["media"] == ["El Universal", "Milenio", "Reforma"]
        assert mexico["sentimentBreakdown"] == {
            "negativo": 33.4, "neutro": 33.3, "positivo": 33.3
        }

        assert data["monthlyVolume"] == [
            {"month": "2025-01", "total": 1, "negativo": 1, "neutro": 0, "positivo": 0},
            {"month": "2025-02", "total": 2, "negativo": 0, "neutro": 1, "positivo": 1},
            {"month": "2025-03", "total": 2, "negativo": 1, "neutro": 1, "positivo": 0},
        ]

        # El segundo GET reutiliza la caché y devuelve exactamente lo mismo.
        cached = client.get("/v1/dashboard/corpus")
        assert cached.status_code == 200
        assert cached.json() == data


def test_corpus_missing_file(tmp_path: Path) -> None:
    settings = build_settings(tmp_path, corpus_csv_path=tmp_path / "no-existe.csv")
    app = create_app(settings=settings, engine=FakeEngine())
    with TestClient(app) as client:
        response = client.get("/v1/dashboard/corpus")
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "corpus_unavailable"
    assert "No se encontró" in error["message"]


def test_corpus_corrupt_file(tmp_path: Path) -> None:
    broken = tmp_path / "corpus_roto.csv"
    broken.write_text("ID,Titulo\n1,Sin columnas de sentimiento\n", encoding="utf-8")
    settings = build_settings(tmp_path, corpus_csv_path=broken)
    app = create_app(settings=settings, engine=FakeEngine())
    with TestClient(app) as client:
        response = client.get("/v1/dashboard/corpus")
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "corpus_unavailable"
    assert "sentimiento" in error["message"]


def test_models_without_artifact(client: TestClient) -> None:
    response = client.get("/v1/dashboard/models")
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["available"] is False
    assert data["message"]
    assert data["models"] == []
    assert data["frames"] == []
    assert data["sampleSize"] == 0


def _write_evaluation(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_models_with_artifact(tmp_path: Path) -> None:
    artifact = {
        "generatedAt": "2026-11-01T10:00:00+00:00",
        "sampleSize": 120,
        "engine": "bert_pair",
        "models": [
            {
                "modelName": "BETO-MigraLatam (Propuesto)",
                "architecture": "BERT Spanish + Multi-label",
                "role": "sentiment",
                "accuracy": 89.4,
                "precision": 88.7,
                "recall": 87.9,
                "f1Score": 88.3,
                "samples": 120,
                "isBest": True,
            }
        ],
        "sentiment": {"accuracy": 89.4, "samples": 120},
        "frames": [
            {
                "frame": "Seguridad",
                "frameId": "seguridad",
                "precision": 92.6,
                "recall": 91.8,
                "f1": 92.2,
                "support": 40,
                "threshold": 0.55,
            }
        ],
        "confusionMatrix": {
            "labels": ["Negativo", "Neutro", "Positivo"],
            "matrix": [[238, 20, 14], [21, 152, 23], [9, 16, 154]],
        },
        "thresholds": {"seguridad": 0.55},
        "available": True,
        "message": "Métricas reales del modelo",
    }
    evaluation_path = _write_evaluation(tmp_path / "evaluation.json", artifact)
    settings = build_settings(tmp_path, evaluation_path=evaluation_path)
    app = create_app(settings=settings, engine=FakeEngine())
    with TestClient(app) as client:
        response = client.get("/v1/dashboard/models")
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["available"] is True
    assert data["message"] == "Métricas reales del modelo"
    assert data["sampleSize"] == 120
    assert data["engine"] == "bert_pair"
    assert data["generatedAt"].startswith("2026-11-01")
    assert set(data["models"][0]) == MODEL_METRIC_KEYS
    assert data["models"][0]["modelName"] == "BETO-MigraLatam (Propuesto)"
    assert data["models"][0]["f1Score"] == 88.3
    assert data["models"][0]["isBest"] is True
    assert set(data["frames"][0]) == FRAME_EVALUATION_KEYS
    assert data["frames"][0]["frameId"] == "seguridad"
    assert data["frames"][0]["support"] == 40
    assert data["confusionMatrix"]["labels"] == ["Negativo", "Neutro", "Positivo"]
    assert data["confusionMatrix"]["matrix"][0][0] == 238
    assert data["thresholds"] == {"seguridad": 0.55}


def test_models_accepts_snake_case_artifact(tmp_path: Path) -> None:
    artifact = {
        "generated_at": "2026-10-01T08:00:00",
        "sample_size": 30,
        "models": [
            {"model_name": "mBERT", "architecture": "BERT", "f1_score": 78.7}
        ],
        "frames": [
            {
                "frame": "Tránsito migratorio",
                "frame_id": "transito_migratorio",
                "precision": 91.2,
                "recall": 90.5,
                "f1_score": 90.8,
                "support": 34,
            }
        ],
        "confusion_matrix": {"labels": ["A", "B"], "matrix": [[3, 1], [0, 4]]},
        "thresholds": {"transito_migratorio": 0.4},
    }
    evaluation_path = _write_evaluation(tmp_path / "evaluation.json", artifact)
    settings = build_settings(tmp_path, evaluation_path=evaluation_path)
    app = create_app(settings=settings, engine=FakeEngine())
    with TestClient(app) as client:
        response = client.get("/v1/dashboard/models")
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["available"] is True
    assert data["sampleSize"] == 30
    assert data["models"][0]["modelName"] == "mBERT"
    assert data["models"][0]["f1Score"] == 78.7
    assert data["frames"][0]["frameId"] == "transito_migratorio"
    assert data["frames"][0]["f1"] == 90.8
    assert data["frames"][0]["threshold"] == 0.5
    assert data["thresholds"] == {"transito_migratorio": 0.4}


def test_models_with_corrupt_artifact(tmp_path: Path) -> None:
    evaluation_path = tmp_path / "evaluation.json"
    evaluation_path.write_text("esto no es json", encoding="utf-8")
    settings = build_settings(tmp_path, evaluation_path=evaluation_path)
    app = create_app(settings=settings, engine=FakeEngine())
    with TestClient(app) as client:
        response = client.get("/v1/dashboard/models")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["available"] is False
    assert data["message"]


def test_recent_analyses(client: TestClient) -> None:
    _seed_analyses(client)

    response = client.get("/v1/dashboard/recent", params={"limit": 2})
    assert response.status_code == 200, response.text
    items = response.json()
    assert len(items) == 2
    for item in items:
        assert set(item) == SUMMARY_KEYS
        assert datetime.fromisoformat(item["createdAt"].replace("Z", "+00:00"))
    assert items[0]["createdAt"] >= items[1]["createdAt"]

    limited = client.get("/v1/dashboard/recent", params={"limit": 1})
    assert len(limited.json()) == 1

    assert client.get("/v1/dashboard/recent", params={"limit": 0}).status_code == 422
