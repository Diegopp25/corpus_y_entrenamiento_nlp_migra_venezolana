"""Contratos Pydantic del API.

Los nombres de los campos se exponen en camelCase para que coincidan
exactamente con los tipos TypeScript del frontend
(``frontend/src/types/index.ts``). Internamente se usa snake_case.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_TEXT_CHARS = 20_000

SentimentLabel = Literal["Negativo", "Neutro", "Positivo"]
CountryName = Literal["Colombia", "México", "Mexico", "Internacional", "Desconocido"]
FrameId = Literal[
    "acceso_servicios",
    "transito_migratorio",
    "seguridad",
    "integracion_social",
    "politica_migratoria",
    "empleo_economia",
    "otros",
]
BiasLabel = Literal[
    "Colombia (Enfoque Punitivo / Seguridad)",
    "México (Enfoque Laboral / Tránsito)",
    "Neutro / Institucional",
]


def to_camel(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(part.capitalize() for part in tail)


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="allow",
        str_strip_whitespace=True,
    )


# ---------------------------------------------------------------------------
# Análisis de textos
# ---------------------------------------------------------------------------
class SentimentScores(CamelModel):
    negativo: float = 0.0
    neutro: float = 0.0
    positivo: float = 0.0


class SentimentAnalysis(CamelModel):
    prediction: SentimentLabel
    confidence: float = Field(ge=0, le=100)
    scores: SentimentScores
    explanation: str


class FrameScore(CamelModel):
    id: FrameId
    label: str
    score: float = Field(ge=0, le=100)
    is_active: bool
    description: str
    associated_keywords: list[str] = Field(default_factory=list)


class HighlightedTerm(CamelModel):
    term: str
    bias_type: Literal["colombia", "mexico", "negative", "positive"]
    weight: float


class CulturalBias(CamelModel):
    detected_bias: BiasLabel
    colombia_alignment_score: float = Field(ge=0, le=100)
    mexico_alignment_score: float = Field(ge=0, le=100)
    reasoning: str
    highlighted_terms: list[HighlightedTerm] = Field(default_factory=list)


class AnalysisMeta(CamelModel):
    engine: str
    requested_engine: str = "auto"
    degraded: bool = False
    model_version: str = ""
    sentiment_model: str = ""
    frames_model: str = ""
    preprocessing: str = "raw"
    latency_ms: float = 0.0
    truncated: bool = False
    warnings: list[str] = Field(default_factory=list)
    persisted: bool = True
    source: str = "api"
    job_id: str | None = None


class TextAnalysisResult(CamelModel):
    id: str
    text: str
    title: str | None = None
    source_url: str | None = None
    media_name: str | None = None
    country: CountryName = "Desconocido"
    date_analyzed: datetime
    sentiment: SentimentAnalysis
    frames: list[FrameScore]
    cultural_bias: CulturalBias
    tokens_count: int
    reading_time_seconds: int
    model_used: str
    meta: AnalysisMeta


class AnalyzeRequest(CamelModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    title: str | None = Field(default=None, max_length=500)
    source_url: str | None = Field(default=None, max_length=2000)
    media_name: str | None = Field(default=None, max_length=200)
    country: CountryName | None = None
    language: str = "es"

    @field_validator("text")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("El texto no puede estar vacío")
        return value


class BatchAnalyzeRequest(CamelModel):
    items: list[AnalyzeRequest] = Field(min_length=1, max_length=50)


class BatchAnalyzeResponse(CamelModel):
    count: int
    results: list[TextAnalysisResult]


class AnalysisSummary(CamelModel):
    id: str
    created_at: datetime
    title: str | None = None
    media_name: str | None = None
    country: str = "Desconocido"
    sentiment: SentimentLabel
    confidence: float
    source: str = "api"
    engine: str = ""
    latency_ms: float = 0.0


class AnalysesPage(CamelModel):
    total: int
    limit: int
    offset: int
    items: list[AnalysisSummary]


# ---------------------------------------------------------------------------
# Ingesta de sitios de noticias
# ---------------------------------------------------------------------------
class ScrapeRequest(CamelModel):
    url: str = Field(min_length=3, max_length=2000)
    max_articles: int = Field(default=4, ge=1, le=10)
    keywords: list[str] = Field(default_factory=list)
    country: CountryName | None = None
    respect_robots: bool | None = None
    analyze: bool = True

    @field_validator("url")
    @classmethod
    def _with_scheme(cls, value: str) -> str:
        value = value.strip()
        if "://" not in value:
            value = f"https://{value}"
        return value


class NewsArticle(CamelModel):
    id: str
    title: str
    snippet: str = ""
    full_text: str = ""
    author: str = ""
    date: str = ""
    media: str = ""
    country: str = "Desconocido"
    url: str = ""
    category: str = ""
    pre_analyzed_result: TextAnalysisResult | None = None


class FrameTally(CamelModel):
    frame: str
    percentage: float


class ScrapedSiteSummary(CamelModel):
    site_name: str
    domain: str
    country: str
    total_analyzed: int
    average_sentiment: SentimentScores
    top_frames: list[FrameTally]
    bias_tendency: str
    hypothesis_match: Literal["Confirmada (Sesgo esperado)", "Parcial", "No concluyente"]
    articles: list[NewsArticle]
    generated_at: datetime | None = None


class JobStep(CamelModel):
    step: int
    total_steps: int
    message: str
    at: datetime


ScrapeStatus = Literal[
    "idle",
    "queued",
    "connecting",
    "crawling",
    "cleaning",
    "analyzing",
    "completed",
    "error",
]


class ScrapeJobResponse(CamelModel):
    job_id: str
    status: ScrapeStatus
    current_step: int
    total_steps: int
    message: str = ""
    articles_found_count: int = 0
    articles_analyzed_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    error: str | None = None
    steps: list[JobStep] = Field(default_factory=list)
    summary: ScrapedSiteSummary | None = None


class ScrapeAccepted(CamelModel):
    job_id: str
    status: ScrapeStatus = "queued"
    status_url: str
    poll_after_seconds: float = 1.5


class SourcePreset(CamelModel):
    id: str
    name: str
    domain: str
    country: str
    category: str = "Medio digital"
    description: str = ""
    # Campos de presentación que usa el frontend (NewsSitePreset)
    flag: str = ""
    logo_text: str = ""
    accent_color: str = ""


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
class SentimentCounts(CamelModel):
    negativo: int = 0
    neutro: int = 0
    positivo: int = 0


class PercentageCounts(CamelModel):
    negativo: float = 0.0
    neutro: float = 0.0
    positivo: float = 0.0


class CountryCount(CamelModel):
    country: str
    count: int
    sentiment: SentimentCounts


class MediaCount(CamelModel):
    media: str
    count: int
    sentiment: SentimentCounts


class EngineCount(CamelModel):
    engine: str
    count: int


class LatencyStats(CamelModel):
    count: int = 0
    mean: float = 0.0
    p50: float = 0.0
    p95: float = 0.0
    p99: float = 0.0


class ScrapeJobStats(CamelModel):
    total: int = 0
    completed: int = 0
    error: int = 0
    running: int = 0


class DashboardOverview(CamelModel):
    generated_at: datetime
    total_analyses: int
    analyses_today: int
    analyses_last_7d: int
    avg_confidence: float
    sentiment: SentimentCounts
    sentiment_pct: PercentageCounts
    top_frames: list[FrameTally]
    countries: list[CountryCount]
    media: list[MediaCount]
    engines: list[EngineCount]
    latency_ms: LatencyStats
    scrape_jobs: ScrapeJobStats
    uptime_seconds: float
    engine: str
    degraded: bool


class TimeseriesPoint(CamelModel):
    date: str
    total: int
    negativo: int
    neutro: int
    positivo: int


class TimeseriesResponse(CamelModel):
    days: int
    items: list[TimeseriesPoint]


class CorpusCountryStats(CamelModel):
    country: str
    total_articles: int
    sentiment_breakdown: PercentageCounts
    frame_breakdown: list[FrameTally]
    media: list[str] = Field(default_factory=list)


class MonthlyVolumePoint(CamelModel):
    month: str
    total: int
    negativo: int
    neutro: int
    positivo: int


class CorpusDashboard(CamelModel):
    generated_at: datetime
    source_file: str
    total_articles: int
    media_count: int
    date_range: dict[str, str]
    sentiment_breakdown: PercentageCounts
    frame_breakdown: list[FrameTally]
    countries: list[CorpusCountryStats]
    monthly_volume: list[MonthlyVolumePoint]


class ModelMetric(CamelModel):
    model_name: str
    architecture: str
    role: str
    accuracy: float | None = None
    precision: float | None = None
    recall: float | None = None
    f1_score: float | None = None
    samples: int | None = None
    is_best: bool = False


class FrameEvaluation(CamelModel):
    frame: str
    frame_id: str | None = None
    precision: float
    recall: float
    f1: float
    support: int
    threshold: float = 0.5


class ConfusionMatrix(CamelModel):
    labels: list[str]
    matrix: list[list[int]]


class ModelEvaluation(CamelModel):
    generated_at: datetime | None = None
    sample_size: int = 0
    engine: str = ""
    models: list[ModelMetric] = Field(default_factory=list)
    sentiment: dict[str, Any] = Field(default_factory=dict)
    frames: list[FrameEvaluation] = Field(default_factory=list)
    confusion_matrix: ConfusionMatrix | None = None
    thresholds: dict[str, float] = Field(default_factory=dict)
    available: bool = False
    message: str = ""


# ---------------------------------------------------------------------------
# Monitoreo / salud
# ---------------------------------------------------------------------------
class ModelInfo(CamelModel):
    name: str
    role: str
    available: bool
    loaded: bool = False
    architecture: str = ""
    path: str = ""
    max_length: int = 0
    device: str = ""
    labels: list[str] = Field(default_factory=list)


class EngineInfo(CamelModel):
    requested: str
    selected: str
    degraded: bool
    reason: str = ""


class DatabaseInfo(CamelModel):
    status: str
    path: str
    analyses: int = 0
    size_bytes: int = 0


class HealthResponse(CamelModel):
    status: Literal["ok", "degraded"]
    version: str
    environment: str
    uptime_seconds: float
    started_at: datetime
    engine: EngineInfo
    models: list[ModelInfo]
    database: DatabaseInfo
    scraper_enabled: bool


class ModelsResponse(CamelModel):
    engine: EngineInfo
    models: list[ModelInfo]
    sentiment_labels: list[str]
    frame_labels: list[dict[str, Any]]
    thresholds: dict[str, float]
    evaluation_available: bool


class MonitoringStats(CamelModel):
    generated_at: datetime
    uptime_seconds: float
    requests_total: int
    requests_by_status: dict[str, int]
    errors_total: int
    analyses_total: int
    analyses_by_engine: dict[str, int]
    scrape_jobs_total: int
    latency_ms: dict[str, float]
    engine: EngineInfo
    database: DatabaseInfo
    store_events_enabled: bool


# ---------------------------------------------------------------------------
# Errores
# ---------------------------------------------------------------------------
class ErrorDetail(CamelModel):
    code: str
    message: str
    detail: Any | None = None


class ErrorResponse(CamelModel):
    error: ErrorDetail
