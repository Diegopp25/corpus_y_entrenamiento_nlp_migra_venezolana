// ===========================================================================
// Tipos del dominio de análisis (contrato real del API, camelCase)
//
// Estos tipos son la fuente única de verdad para la UI y para
// `src/services/api.ts` (que los importa y reexporta). Reflejan las respuestas
// reales de la API FastAPI en `http://127.0.0.1:8000` (ver docs/API.md del
// checkout principal `migra-nlp`).
// ===========================================================================

// ---------------------------------------------------------------------------
// 1. Análisis de texto (/v1/analyze)
// ---------------------------------------------------------------------------

export type SentimentType = "Negativo" | "Neutro" | "Positivo"

export type FrameId =
  | "acceso_servicios"
  | "transito_migratorio"
  | "seguridad"
  | "integracion_social"
  | "politica_migratoria"
  | "empleo_economia"
  | "otros"

export type BiasType = "colombia" | "mexico" | "negative" | "positive"

export type DetectedBias =
  | "Colombia (Enfoque Punitivo / Seguridad)"
  | "México (Enfoque Laboral / Tránsito)"
  | "Neutro / Institucional"

/**
 * País tal como lo acepta/devuelve el API (normaliza "Mexico" -> "México").
 * En respuestas guardadas puede llegar `null`.
 */
export type CountryName =
  | "Colombia"
  | "México"
  | "Mexico"
  | "Internacional"
  | "Desconocido"

export interface FrameScore {
  id: FrameId
  label: string
  score: number // 0..100
  isActive: boolean // score >= umbral del encuadre
  description: string
  /**
   * El API devuelve un array en `/v1/analyze`, pero el resumen del scraper
   * (`/v1/sources/jobs/{id}`) lo serializa como una cadena separada por
   * espacios. La UI actual no lo usa; se contemplan ambos formatos.
   */
  associatedKeywords: string[] | string
}

export interface SentimentAnalysis {
  prediction: SentimentType
  confidence: number // 0..100
  scores: {
    negativo: number
    neutro: number
    positivo: number
  }
  explanation: string
}

export interface CulturalBias {
  detectedBias: DetectedBias
  colombiaAlignmentScore: number // 0..100
  mexicoAlignmentScore: number // 0..100
  reasoning: string
  highlightedTerms: Array<{
    term: string
    biasType: BiasType
    weight: number
  }>
}

/** Metadatos que agrega el API (no existían en el front simulado). */
export interface AnalysisMeta {
  engine: string
  requestedEngine: string
  degraded: boolean
  modelVersion: string
  sentimentModel: string
  framesModel: string
  preprocessing: string
  latencyMs: number
  truncated: boolean
  warnings: string[]
  persisted: boolean
  source: string
  jobId: string | null
}

export interface TextAnalysisResult {
  id: string
  text: string
  title?: string | null
  sourceUrl?: string | null
  mediaName?: string | null
  country?: CountryName | null
  /** ISO 8601 en UTC, p. ej. "2026-11-09T18:58:59.572713Z". */
  dateAnalyzed: string
  sentiment: SentimentAnalysis
  frames: FrameScore[]
  culturalBias: CulturalBias
  tokensCount: number
  readingTimeSeconds: number
  /** Nombre real del motor, p. ej. "BETO-migra-ve (sentimiento + encuadres)". */
  modelUsed: string
  meta?: AnalysisMeta
}

export interface NewsArticle {
  id: string
  title: string
  snippet: string
  fullText: string
  author: string
  date: string
  media: string
  country: string
  url: string
  category: string
  preAnalyzedResult?: TextAnalysisResult | null
}

/** Preset local de presentación (incluye artículos de ejemplo en el mock). */
export interface NewsSitePreset {
  id: string
  name: string
  domain: string
  country: "Colombia" | "México"
  flag: string
  category: "Prensa Escrita" | "Medio Digital" | "Televisión/Radio"
  description: string
  logoText: string
  accentColor: string
  articles: NewsArticle[]
}

/** Preset real devuelto por `GET /v1/sources/presets` (sin artículos). */
export interface SourcePreset {
  id: string
  name: string
  domain: string
  country: string
  category: string
  description: string
  flag: string
  logoText: string
  accentColor: string
}

// ---------------------------------------------------------------------------
// 2. Ingesta de noticias (/v1/sources)
// ---------------------------------------------------------------------------

export type ScrapeStatus =
  | "idle"
  | "queued"
  | "connecting"
  | "crawling"
  | "cleaning"
  | "analyzing"
  | "completed"
  | "error"

export interface ScrapingProgress {
  status: ScrapeStatus
  currentStep: number
  totalSteps: number
  message: string
  articlesFoundCount: number
  articlesAnalyzedCount?: number
}

export interface JobStep {
  step: number
  totalSteps: number
  message: string
  at: string
}

export interface FrameTally {
  frame: string
  percentage: number
}

export type HypothesisMatch =
  | "Confirmada (Sesgo esperado)"
  | "Parcial"
  | "No concluyente"

export interface ScrapedSiteSummary {
  siteName: string
  domain: string
  country: string
  totalAnalyzed: number
  averageSentiment: {
    negativo: number
    neutro: number
    positivo: number
  }
  topFrames: FrameTally[]
  biasTendency: string
  hypothesisMatch: HypothesisMatch
  articles: NewsArticle[]
  generatedAt?: string | null
}

/** Body de `POST /v1/sources/scan` (camelCase y snake_case aceptados). */
export interface ScanSiteRequest {
  url: string
  maxArticles?: number // 1..10, por defecto 4
  keywords?: string[]
  country?: CountryName
  respectRobots?: boolean
  analyze?: boolean // por defecto true
}

/** Respuesta 202 de `POST /v1/sources/scan`. */
export interface ScrapeAccepted {
  jobId: string
  status: ScrapeStatus
  statusUrl: string
  pollAfterSeconds: number // 1.5 por defecto
}

/** Respuesta de `GET /v1/sources/jobs/{jobId}`. */
export interface ScrapeJobResponse {
  jobId: string
  status: ScrapeStatus
  currentStep: number
  totalSteps: number
  message: string
  articlesFoundCount: number
  articlesAnalyzedCount: number
  createdAt?: string | null
  updatedAt?: string | null
  error?: string | null
  steps: JobStep[]
  summary?: ScrapedSiteSummary | null
}

/**
 * Entrada de `GET /v1/sources/jobs` (lista resumida).
 * Ojo: aquí el id se llama `id` y los contadores no llevan sufijo `Count`.
 */
export interface ScrapeJobSummary {
  id: string
  url: string
  domain: string
  status: ScrapeStatus
  currentStep: number
  totalSteps: number
  message: string
  articlesFound: number
  articlesAnalyzed: number
  error?: string | null
  createdAt?: string | null
  updatedAt?: string | null
}

/** Body de `POST /v1/sources/analyze-url`. */
export interface AnalyzeUrlRequest {
  url: string
  country?: CountryName
  respectRobots?: boolean
}

// ---------------------------------------------------------------------------
// 3. Historial de análisis (/v1/analyses)
// ---------------------------------------------------------------------------

export interface AnalyzeRequest {
  text: string
  title?: string
  sourceUrl?: string
  mediaName?: string
  country?: CountryName
  language?: string
}

export interface BatchAnalyzeRequest {
  items: AnalyzeRequest[] // 1..50
}

export interface BatchAnalyzeResponse {
  count: number
  results: TextAnalysisResult[]
}

export interface AnalysisSummary {
  id: string
  createdAt: string
  title?: string | null
  mediaName?: string | null
  country: string
  sentiment: SentimentType
  confidence: number
  source: string
  engine: string
  latencyMs: number
}

export interface AnalysesPage {
  total: number
  limit: number
  offset: number
  items: AnalysisSummary[]
}

export interface ListAnalysesParams {
  limit?: number // 1..100
  offset?: number
  sentiment?: SentimentType
  country?: string
  source?: string
  since?: string // ISO 8601
}

// ---------------------------------------------------------------------------
// 4. Dashboard y monitoreo
// ---------------------------------------------------------------------------

export interface SentimentDistribution {
  negativo: number
  neutro: number
  positivo: number
}

export type SentimentCounts = SentimentDistribution
export type PercentageCounts = SentimentDistribution

export interface CountryCount {
  country: string
  count: number
  sentiment: SentimentCounts
}

export interface MediaCount {
  media: string
  count: number
  sentiment: SentimentCounts
}

export interface EngineCount {
  engine: string
  count: number
}

export interface LatencyStats {
  count: number
  mean: number
  p50: number
  p95: number
  p99: number
}

export interface ScrapeJobStats {
  total: number
  completed: number
  error: number
  running: number
}

/** `GET /v1/dashboard/overview` */
export interface DashboardOverview {
  generatedAt: string
  totalAnalyses: number
  analysesToday: number
  analysesLast7d: number
  avgConfidence: number
  sentiment: SentimentCounts
  sentimentPct: PercentageCounts
  topFrames: FrameTally[]
  countries: CountryCount[]
  media: MediaCount[]
  engines: EngineCount[]
  latencyMs: LatencyStats
  scrapeJobs: ScrapeJobStats
  uptimeSeconds: number
  engine: string
  degraded: boolean
}

export interface TimeseriesPoint {
  date: string // YYYY-MM-DD
  total: number
  negativo: number
  neutro: number
  positivo: number
}

/** `GET /v1/dashboard/timeseries?days=30` */
export interface TimeseriesResponse {
  days: number
  items: TimeseriesPoint[]
}

export interface CorpusCountryStats {
  country: string
  totalArticles: number
  sentimentBreakdown: PercentageCounts
  frameBreakdown: FrameTally[]
  media: string[]
}

export interface MonthlyVolumePoint {
  month: string
  total: number
  negativo: number
  neutro: number
  positivo: number
}

/** `GET /v1/dashboard/corpus` (CSV etiquetado real: 156 artículos). */
export interface CorpusDashboardData {
  generatedAt: string
  sourceFile: string
  totalArticles: number
  mediaCount: number
  dateRange: Record<string, string>
  sentimentBreakdown: PercentageCounts
  frameBreakdown: FrameTally[]
  countries: CorpusCountryStats[]
  monthlyVolume: MonthlyVolumePoint[]
}

/** Métricas de un modelo/rol (ratios 0–1 en el artefacto real). */
export interface ModelMetricData {
  modelName: string
  architecture: string
  role?: string | null
  accuracy?: number | null
  precision?: number | null
  recall?: number | null
  f1Score?: number | null
  samples?: number | null
  isBest: boolean
}

export interface ConfusionMatrixData {
  labels: string[]
  matrix: number[][] // [real][predicho]
}

export interface FrameEvaluation {
  frame: string
  frameId?: string | null
  precision: number
  recall: number
  f1: number
  support: number
  threshold: number
}

/** `GET /v1/dashboard/models` (artefacto real `evaluation.json`). */
export interface ModelEvaluationData {
  generatedAt?: string | null
  sampleSize: number
  engine: string
  models: ModelMetricData[]
  sentiment: Record<string, unknown>
  frames: FrameEvaluation[]
  confusionMatrix?: ConfusionMatrixData | null
  thresholds: Record<string, number>
  available: boolean
  message: string
}

export interface ModelInfo {
  name: string
  role: string
  available: boolean
  loaded: boolean
  architecture: string
  path: string
  maxLength: number
  device: string
  labels: string[]
}

export interface EngineInfo {
  requested: string
  selected: string
  degraded: boolean
  reason: string
}

export interface DatabaseInfo {
  status: string
  path: string
  analyses: number
  sizeBytes: number
}

/** `GET /v1/health` */
export interface HealthResponse {
  status: "ok" | "degraded"
  version: string
  environment: string
  uptimeSeconds: number
  startedAt: string
  engine: EngineInfo
  models: ModelInfo[]
  database: DatabaseInfo
  scraperEnabled: boolean
}

/** `GET /v1/models` */
export interface FrameLabelInfo {
  id: FrameId
  label: string
  model_label: string
  description: string
  keywords: string[]
  threshold: number
}

export interface ModelsResponse {
  engine: EngineInfo
  models: ModelInfo[]
  sentimentLabels: string[]
  frameLabels: FrameLabelInfo[]
  thresholds: Record<string, number>
  evaluationAvailable: boolean
}

/** `GET /v1/monitoring/stats` */
export interface MonitoringStats {
  generatedAt: string
  uptimeSeconds: number
  requestsTotal: number
  requestsByStatus: Record<string, number>
  errorsTotal: number
  analysesTotal: number
  analysesByEngine: Record<string, number>
  scrapeJobsTotal: number
  latencyMs: Record<string, number>
  engine: EngineInfo
  database: DatabaseInfo
  storeEventsEnabled: boolean
}

// ---------------------------------------------------------------------------
// 5. Peticiones y utilidades del cliente
// ---------------------------------------------------------------------------

export interface ApiErrorPayload {
  error: {
    code: string
    message: string
    detail?: unknown
  }
}
