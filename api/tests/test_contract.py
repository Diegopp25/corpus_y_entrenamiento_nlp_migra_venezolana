"""Pruebas de contrato: los JSON deben calzar con los tipos del frontend."""

from __future__ import annotations

TEXT = (
    "La ola de inseguridad crece y los ciudadanos exigen más control en las "
    "calles tras los atracos registrados por bandas criminales."
)

SENTIMENT_KEYS = {"prediction", "confidence", "scores", "explanation"}
FRAME_KEYS = {"id", "label", "score", "isActive", "description", "associatedKeywords"}
BIAS_KEYS = {
    "detectedBias",
    "colombiaAlignmentScore",
    "mexicoAlignmentScore",
    "reasoning",
    "highlightedTerms",
}
RESULT_KEYS = {
    "id",
    "text",
    "title",
    "sourceUrl",
    "mediaName",
    "country",
    "dateAnalyzed",
    "sentiment",
    "frames",
    "culturalBias",
    "tokensCount",
    "readingTimeSeconds",
    "modelUsed",
    "meta",
}


def test_result_keys_match_frontend_types(client):
    data = client.post("/v1/analyze", json={"text": TEXT}).json()
    assert set(data) == RESULT_KEYS
    assert set(data["sentiment"]) == SENTIMENT_KEYS
    assert set(data["sentiment"]["scores"]) == {"negativo", "neutro", "positivo"}
    assert set(data["frames"][0]) == FRAME_KEYS
    assert set(data["culturalBias"]) == BIAS_KEYS
    assert set(data["culturalBias"]["highlightedTerms"][0]) == {
        "term",
        "biasType",
        "weight",
    }
    assert data["modelUsed"] in {
        "BETO-migra-ve (sentimiento + encuadres)",
        "BETO-migra-ve multitarea (sentimiento + encuadres)",
        "léxico-MigraVenezuela (baseline)",
        "motor-falso-de-pruebas",
    }


def test_frame_ids_match_frontend(client):
    data = client.post("/v1/analyze", json={"text": TEXT}).json()
    expected = {
        "acceso_servicios",
        "transito_migratorio",
        "seguridad",
        "integracion_social",
        "politica_migratoria",
        "empleo_economia",
        "otros",
    }
    assert {frame["id"] for frame in data["frames"]} == expected
    scores = [frame["score"] for frame in data["frames"]]
    assert scores == sorted(scores, reverse=True)


def test_country_conflation_mexico(client):
    data = client.post(
        "/v1/analyze",
        json={"text": TEXT, "country": "Mexico"},
    ).json()
    assert data["country"] == "México"


def test_camel_case_requests_are_accepted(client):
    snake = client.post(
        "/v1/analyze",
        json={"text": TEXT, "source_url": "https://eltiempo.com/x"},
    )
    camel = client.post(
        "/v1/analyze",
        json={"text": TEXT, "sourceUrl": "https://eltiempo.com/x"},
    )
    assert snake.status_code == 200
    assert camel.status_code == 200
    assert snake.json()["sourceUrl"] == camel.json()["sourceUrl"]
