"""Pruebas del empaquetado de modelos para despliegues (Railway/Render)."""

from __future__ import annotations

import zipfile
from pathlib import Path

from scripts.prepare_models import models_ready, prepare_models


def _fake_model(root: Path, folder: str) -> Path:
    model_dir = root / folder
    model_dir.mkdir(parents=True)
    (model_dir / "config.json").write_text('{"model_type": "bert"}', encoding="utf-8")
    (model_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
    (model_dir / "model.safetensors").write_bytes(b"fake-weights")
    return model_dir


def _build_archive(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    _fake_model(source, "modelo_sentimiento")
    _fake_model(source, "modelo_encuadre")
    archive = tmp_path / "modelos_beto.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for path in source.rglob("*"):
            bundle.write(path, path.relative_to(source))
    return archive


def test_prepare_models_extracts_and_maps(tmp_path, monkeypatch):
    archive = _build_archive(tmp_path)
    models_dir = tmp_path / "models"
    monkeypatch.setenv("NLP_MODELS_ARCHIVE_URL", archive.as_uri())
    monkeypatch.setenv("NLP_MODELS_DIR", str(models_dir))
    monkeypatch.delenv("NLP_SENTIMENT_MODEL_DIR", raising=False)
    monkeypatch.delenv("NLP_FRAMES_MODEL_DIR", raising=False)
    monkeypatch.delenv("NLP_ENGINE", raising=False)
    monkeypatch.delenv("NLP_REQUIRE_MODELS", raising=False)

    assert prepare_models() is True
    assert models_ready(models_dir)
    assert (models_dir / "bert-sentiment" / "model.safetensors").exists()
    assert (models_dir / "bert-frames" / "model.safetensors").exists()
    assert str(models_dir / "bert-sentiment") in __import__("os").environ["NLP_SENTIMENT_MODEL_DIR"]
    assert __import__("os").environ["NLP_ENGINE"] == "bert_pair"


def test_prepare_models_without_url_keeps_lexicon(tmp_path, monkeypatch):
    monkeypatch.delenv("NLP_MODELS_ARCHIVE_URL", raising=False)
    monkeypatch.setenv("NLP_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.delenv("NLP_REQUIRE_MODELS", raising=False)
    assert prepare_models() is False
    assert not (tmp_path / "models" / "bert-sentiment").exists()


def test_prepare_models_skips_when_already_ready(tmp_path, monkeypatch):
    models_dir = tmp_path / "models"
    _fake_model(models_dir, "bert-sentiment")
    _fake_model(models_dir, "bert-frames")
    monkeypatch.setenv("NLP_MODELS_DIR", str(models_dir))
    monkeypatch.setenv("NLP_MODELS_ARCHIVE_URL", "https://example.com/never.zip")
    monkeypatch.delenv("NLP_SENTIMENT_MODEL_DIR", raising=False)
    monkeypatch.delenv("NLP_FRAMES_MODEL_DIR", raising=False)
    assert prepare_models() is True
