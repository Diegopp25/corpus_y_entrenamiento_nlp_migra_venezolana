"""Fixtures compartidas de la suite de pruebas."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parent.parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

# Evita que el ``app = create_app()`` de app.main cargue los pesos BETO reales
# (y que escriba la BD de desarrollo) al importar el módulo durante los tests.
os.environ.setdefault("NLP_ENGINE", "lexicon")
os.environ.setdefault("NLP_DATABASE_PATH", str(API_DIR / "data" / "tests-import.db"))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.engine import AnalysisEngine, ModelDescriptor, RawPrediction  # noqa: E402
from app.engine.labels import FRAME_IDS, FRAME_MODEL_ORDER  # noqa: E402
from app.main import create_app  # noqa: E402


class FakeEngine(AnalysisEngine):
    """Motor determinista para pruebas: no carga torch ni modelos reales."""

    name = "fake"
    version = "1.0-test"
    display_name = "motor-falso-de-pruebas"
    thresholds: dict[str, float] = {}

    def __init__(self) -> None:
        self.calls = 0

    @property
    def models(self) -> list[ModelDescriptor]:
        return [
            ModelDescriptor(
                name="fake-sentiment",
                role="sentiment",
                available=True,
                loaded=True,
                architecture="fake",
                labels=["Negativo", "Neutro", "Positivo"],
            ),
            ModelDescriptor(
                name="fake-frames",
                role="frames",
                available=True,
                loaded=True,
                architecture="fake",
                labels=list(FRAME_MODEL_ORDER),
            ),
        ]

    def predict(self, text: str) -> RawPrediction:
        self.calls += 1
        lowered = text.lower()
        frames = {frame_id: 0.08 for frame_id in FRAME_IDS}
        if "inseguridad" in lowered or "delincuencia" in lowered or "crimen" in lowered:
            sentiment = {"Negativo": 0.82, "Neutro": 0.11, "Positivo": 0.07}
            frames["seguridad"] = 0.93
            frames["politica_migratoria"] = 0.24
        elif "trabajo" in lowered or "empleo" in lowered or "oportunidades" in lowered:
            sentiment = {"Negativo": 0.06, "Neutro": 0.16, "Positivo": 0.78}
            frames["empleo_economia"] = 0.91
            frames["integracion_social"] = 0.22
        elif "salud" in lowered or "educación" in lowered:
            sentiment = {"Negativo": 0.12, "Neutro": 0.62, "Positivo": 0.26}
            frames["acceso_servicios"] = 0.88
        else:
            sentiment = {"Negativo": 0.22, "Neutro": 0.58, "Positivo": 0.20}
            frames["integracion_social"] = 0.55
        total = sum(sentiment.values())
        sentiment = {key: value / total for key, value in sentiment.items()}
        return RawPrediction(
            sentiment=sentiment,
            frames=frames,
            model_name="motor-falso-de-pruebas",
            model_version=self.version,
            warnings=[],
            preprocessing="test",
        )


@pytest.fixture
def fake_engine() -> FakeEngine:
    return FakeEngine()


def build_settings(tmp_path: Path, **overrides) -> Settings:
    defaults = dict(
        _env_file=None,
        environment="test",
        engine="lexicon",
        database_path=tmp_path / "test.db",
        thresholds_path=tmp_path / "thresholds.json",
        evaluation_path=tmp_path / "evaluation.json",
        artifacts_dir=tmp_path,
        api_key=None,
        rate_limit_requests=10_000,
        rate_limit_window_seconds=60,
        scraper_enabled=False,
        store_events=True,
        docs_enabled=True,
    )
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return build_settings(tmp_path)


@pytest.fixture
def app(settings: Settings, fake_engine: FakeEngine):
    return create_app(settings=settings, engine=fake_engine)


@pytest.fixture
def client(app) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def store(client: TestClient):
    return client.app.state.store


@pytest.fixture
def analysis_service(client: TestClient):
    return client.app.state.analysis
