"""Configuración central del API.

Todas las variables se pueden definir por entorno con el prefijo ``NLP_``
(por ejemplo ``NLP_ENGINE=bert_pair``) o en un archivo ``api/.env``.
Las rutas relativas se resuelven contra la carpeta ``api/``.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = API_DIR.parent

_PATHS = (
    "sentiment_model_dir",
    "frames_model_dir",
    "multitask_model_dir",
    "thresholds_path",
    "evaluation_path",
    "lexicon_path",
    "database_path",
    "artifacts_dir",
    "corpus_csv_path",
)

DEFAULT_KEYWORDS = [
    "migración",
    "migrante",
    "migrantes",
    "venezolano",
    "venezolanos",
    "venezolana",
    "venezolanas",
    "frontera",
    "fronterizo",
    "éxodo",
    "refugiado",
    "refugiados",
    "regularización",
    "deportación",
    "deportados",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NLP_",
        env_file=(str(API_DIR / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        # Desactivamos la decodificación JSON automática de listas para aceptar
        # tanto NLP_CORS_ORIGINS=* / a,b como ["a","b"] en el .env.
        enable_decoding=False,
    )

    # ----------------------------- aplicación -----------------------------
    app_name: str = "API de cobertura mediática de la migración venezolana"
    version: str = "1.0.0"
    environment: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"
    docs_enabled: bool = True

    # ----------------------------- seguridad ------------------------------
    api_key: str | None = None
    cors_origins: list[str] = ["*"]
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60
    max_text_chars: int = 20_000
    max_batch_items: int = 50
    store_events: bool = True

    # ----------------------------- modelos --------------------------------
    engine: Literal["auto", "bert_pair", "multitask", "lexicon"] = "auto"
    sentiment_model_dir: Path = API_DIR / "models" / "bert-sentiment"
    frames_model_dir: Path = API_DIR / "models" / "bert-frames"
    multitask_model_dir: Path = REPO_DIR / "models_beto" / "multitask_beto"
    device: str = "auto"
    max_length: int = 512
    frame_threshold: float = 0.5
    thresholds_path: Path = API_DIR / "artifacts" / "thresholds.json"
    evaluation_path: Path = API_DIR / "artifacts" / "evaluation.json"
    lexicon_path: Path = API_DIR / "app" / "resources" / "lexicon.json"
    preprocess_with_spacy: bool = True

    # --------------------------- persistencia -----------------------------
    database_path: Path = API_DIR / "data" / "api.db"
    artifacts_dir: Path = API_DIR / "artifacts"
    corpus_csv_path: Path = REPO_DIR / "Data" / "dataset_migracion_venezolana_labeled.csv"

    # ------------------------------ scraper -------------------------------
    scraper_enabled: bool = True
    scraper_respect_robots: bool = True
    scraper_user_agent: str = (
        "MigraVenezuelaBot/1.0 (+https://github.com/Diegopp25/"
        "corpus_y_entrenamiento_nlp_migra_venezolana)"
    )
    scraper_timeout_seconds: float = 20.0
    scraper_max_articles: int = 8
    scraper_max_response_bytes: int = 5_000_000
    scraper_allow_private_networks: bool = False
    scraper_keywords: list[str] = DEFAULT_KEYWORDS
    scraper_max_jobs_in_parallel: int = 2
    scraper_job_ttl_hours: int = 24

    # --------------------------- normalización ----------------------------
    @field_validator("cors_origins", "scraper_keywords", mode="before")
    @classmethod
    def _split_csv_or_json(cls, value: object) -> object:
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            if raw.startswith("["):
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    pass
            return [item.strip() for item in raw.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _resolve_relative_paths(self) -> "Settings":
        for field_name in _PATHS:
            value = getattr(self, field_name)
            if value is None:
                continue
            path = Path(value)
            if not path.is_absolute():
                path = (API_DIR / path).resolve()
            setattr(self, field_name, path)
        for field_name in ("sentiment_model_dir", "frames_model_dir", "multitask_model_dir"):
            value = getattr(self, field_name)
            if value is not None:
                setattr(self, field_name, Path(value).resolve())
        return self

    # ------------------------------ helpers -------------------------------
    @property
    def is_prod(self) -> bool:
        return self.environment == "prod"

    @property
    def auth_enabled(self) -> bool:
        return bool(self.api_key)

    def ensure_directories(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
