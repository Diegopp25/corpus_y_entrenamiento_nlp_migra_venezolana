"""Pruebas del motor léxico (respaldo) y de la selección automática de motor."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.engine import LexiconEngine, build_engine
from app.main import create_app
from tests.conftest import build_settings

TEXT = (
    "La inseguridad y la delincuencia preocupan a los ciudadanos en la frontera: "
    "los atracos y homicidios registrados por bandas criminales han aumentado, "
    "mientras las autoridades policiales anuncian operativos y capturas."
)


def test_lexicon_engine_direct():
    engine = LexiconEngine()
    prediction = engine.predict(TEXT)
    assert set(prediction.sentiment) == {"Negativo", "Neutro", "Positivo"}
    assert abs(sum(prediction.sentiment.values()) - 1.0) < 0.01
    assert len(prediction.frames) == 7
    assert max(prediction.frames, key=prediction.frames.get) == "seguridad"
    assert prediction.sentiment["Negativo"] > prediction.sentiment["Positivo"]


def test_lexicon_engine_via_api(tmp_path: Path):
    settings = build_settings(tmp_path, engine="lexicon")
    app = create_app(settings=settings)
    with TestClient(app) as client:
        response = client.post("/v1/analyze", json={"text": TEXT})
        assert response.status_code == 200
        data = response.json()
        assert data["meta"]["engine"] == "lexicon"
        assert data["meta"]["degraded"] is False
        assert data["sentiment"]["prediction"] == "Negativo"
        assert len(data["frames"]) == 7
        assert data["modelUsed"] == "léxico-MigraVenezuela (baseline)"


def test_auto_falls_back_and_flags_degraded(tmp_path: Path):
    settings = build_settings(
        tmp_path,
        engine="auto",
        sentiment_model_dir=tmp_path / "no-existe-sent",
        frames_model_dir=tmp_path / "no-existe-frames",
        multitask_model_dir=tmp_path / "no-existe-multi",
    )
    selection = build_engine(settings)
    assert selection.selected == "lexicon"
    assert selection.degraded is True
    assert "léxico" in selection.reason or "baseline" in selection.reason
