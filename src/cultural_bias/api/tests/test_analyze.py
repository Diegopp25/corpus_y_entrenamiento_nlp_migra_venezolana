"""Pruebas del endpoint principal de análisis."""

from __future__ import annotations

import pytest

TEXT = (
    "La ola de inseguridad crece en la frontera y los ciudadanos exigen más "
    "control policial tras los atracos y homicidios registrados por bandas "
    "criminales en la ciudad."
)


def test_analyze_returns_frontend_contract(client):
    response = client.post(
        "/v1/analyze",
        json={"text": TEXT, "title": "Prueba", "mediaName": "El Tiempo"},
    )
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["sentiment"]["prediction"] == "Negativo"
    assert data["sentiment"]["confidence"] > 50
    assert data["sentiment"]["scores"]["negativo"] > 50
    assert abs(sum(data["sentiment"]["scores"].values()) - 100.0) < 0.11
    assert data["country"] == "Colombia"
    assert len(data["frames"]) == 7
    assert data["frames"][0]["id"] == "seguridad"
    assert data["frames"][0]["isActive"] is True
    assert data["frames"][0]["score"] > 90
    assert data["culturalBias"]["detectedBias"].startswith("Colombia")
    assert data["culturalBias"]["highlightedTerms"]
    assert data["tokensCount"] > 20
    assert data["readingTimeSeconds"] >= 5
    assert data["meta"]["engine"] == "fake"
    assert data["meta"]["persisted"] is True


def test_analyze_infers_mexico_from_url(client):
    response = client.post(
        "/v1/analyze",
        json={
            "text": "Los migrantes llegan a la frontera y encuentran trabajo y oportunidades en la industria.",
            "sourceUrl": "https://www.milenio.com/estados/migrantes-empleo",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["country"] == "México"
    assert data["mediaName"] == "Milenio"
    assert data["sentiment"]["prediction"] == "Positivo"


def test_analyze_empty_text_fails(client):
    response = client.post("/v1/analyze", json={"text": "   "})
    assert response.status_code == 422


def test_analyze_too_long_fails(client):
    response = client.post("/v1/analyze", json={"text": "a" * 20_001})
    assert response.status_code == 422


def test_analyze_batch(client):
    response = client.post(
        "/v1/analyze/batch",
        json={
            "items": [
                {"text": TEXT},
                {"text": "Los migrantes encuentran trabajo y oportunidades en la industria."},
            ]
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert [item["sentiment"]["prediction"] for item in data["results"]] == [
        "Negativo",
        "Positivo",
    ]


def test_analyze_batch_limit(client):
    response = client.post(
        "/v1/analyze/batch",
        json={"items": [{"text": "texto de prueba " * 5} for _ in range(51)]},
    )
    assert response.status_code == 422


def test_history_lists_and_retrieves(client):
    created = client.post("/v1/analyze", json={"text": TEXT}).json()
    listing = client.get("/v1/analyses", params={"limit": 10})
    assert listing.status_code == 200
    payload = listing.json()
    assert payload["total"] >= 1
    assert payload["items"][0]["id"] == created["id"]

    detail = client.get(f"/v1/analyses/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == created["id"]
    assert "_textHash" not in detail.json()

    missing = client.get("/v1/analyses/no-existe")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("La inseguridad y la delincuencia preocupan a la ciudadanía.", "Negativo"),
        ("El empleo y las oportunidades atraen a los migrantes.", "Positivo"),
        ("El gobierno presentó un informe con cifras del programa.", "Neutro"),
    ],
)
def test_sentiment_matches_expected(client, text, expected):
    response = client.post("/v1/analyze", json={"text": text})
    assert response.status_code == 200
    assert response.json()["sentiment"]["prediction"] == expected
