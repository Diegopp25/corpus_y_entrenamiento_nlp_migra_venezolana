/**
 * Cliente TypeScript del API de cobertura mediática de la migración venezolana.
 *
 * - Sin dependencias externas (solo `fetch`, disponible en navegadores y Node 18+).
 * - Tipos espejo de `frontend-extract/src/types/index.ts` + los tipos de los
 *   endpoints de dashboard, monitoreo e ingesta de noticias.
 * - Base URL configurable con `VITE_API_URL` (por defecto http://localhost:8000).
 * - Header opcional `X-API-Key` (`VITE_API_KEY`), requerido solo si el API
 *   arranca con `NLP_API_KEY` definida.
 * - Errores tipados: `ApiError` con `code` (código del API) y `status` (HTTP).
 * - Helper `pollJob` para seguir el progreso del scraping cada 1,5 s.
 *
 * Uso básico:
 *
 *   import { analyzeText, scanSite, pollJob, getOverview } from "./api";
 *
 *   const analysis = await analyzeText({ text, title, mediaName });
 *   const accepted = await scanSite({ url: "https://www.eltiempo.com", maxArticles: 4 });
 *   const summary = await pollJob(accepted.jobId, (job) => console.log(job.currentStep));
 *   const overview = await getOverview();
 *
 * Copia este archivo a `src/services/api.ts` del frontend (ver docs/FRONTEND.md).
 */

// ===========================================================================
// 1. Tipos espejo del frontend (frontend-extract/src/types/index.ts)
// ===========================================================================

export type SentimentType = "Negativo" | "Neutro" | "Positivo";

export type FrameId =
  | "acceso_servicios"
  | "transito_migratorio"
  | "seguridad"
  | "integracion_social"
  | "politica_migratoria"
  | "empleo_economia"
  | "otros";

export type BiasType = "colombia" | "mexico" | "negative" | "positive";

export type DetectedBias =
  | "Colombia (Enfoque Punitivo / Seguridad)"
  | "México (Enfoque Laboral / Tránsito)"
  | "Neutro / Institucional";

/** País tal como lo acepta/devuelve el API (México normaliza "Mexico" -> "México"). */
export type CountryName =
  | "Colombia"
  | "México"
  | "Mexico"
  | "Internacional"
  | "Desconocido";

export interface FrameScore {
  id: FrameId;
  label: string;
  score: number; // 0..100
  isActive: boolean; // score >= umbral del encuadre
  description: string;
  associatedKeywords: string[];
}

export interface SentimentAnalysis {
  prediction: SentimentType;
  confidence: number; // 0..100
  scores: {
    negativo: number;
    neutro: number;
    positivo: number;
  };
  explanation: string;
}

export interface CulturalBias {
  detectedBias: DetectedBias;
  colombiaAlignmentScore: number; // 0..100
  mexicoAlignmentScore: number; // 0..100
  reasoning: string;
  highlightedTerms: Array<{
    term: string;
    biasType: BiasType;
    weight: number;
  }>;
}

/** Metadatos extra que agrega el API (no existían en el front simulado). */
export interface AnalysisMeta {
  engine: string;
  requestedEngine: string;
  degraded: boolean;
  modelVersion: string;
  sentimentModel: string;
  framesModel: string;
  preprocessing: string;
  latencyMs: number;
  truncated: boolean;
  warnings: string[];
  persisted: boolean;
  source: string;
  jobId: string | null;
}

export interface TextAnalysisResult {
  id: string;
  text: string;
  title?: string | null;
  sourceUrl?: string | null;
  mediaName?: string | null;
  country?: CountryName;
  /** ISO 8601 en UTC, p. ej. "2026-11-09T18:58:59.572713Z". */
  dateAnalyzed: string;
  sentiment: SentimentAnalysis;
  frames: FrameScore[];
  culturalBias: CulturalBias;
  tokensCount: number;
  readingTimeSeconds: number;
  /**
   * El API devuelve el nombre real del motor, p. ej.
   * "BETO-migra-ve (sentimiento + encuadres)" o
   * "léxico-MigraVenezuela (baseline)".
   */
  modelUsed: string;
  meta?: AnalysisMeta;
}

export interface NewsArticle {
  id: string;
  title: string;
  snippet: string;
  fullText: string;
  author: string;
  date: string;
  media: string;
  country: string;
  url: string;
  category: string;
  preAnalyzedResult?: TextAnalysisResult | null;
}

export interface FrameTally {
  frame: string;
  percentage: number;
}

export type HypothesisMatch =
  | "Confirmada (Sesgo esperado)"
  | "Parcial"
  | "No concluyente";

export interface ScrapedSiteSummary {
  siteName: string;
  domain: string;
  country: string;
  totalAnalyzed: number;
  averageSentiment: {
    negativo: number;
    neutro: number;
    positivo: number;
  };
  topFrames: FrameTally[];
  biasTendency: string;
  hypothesisMatch: HypothesisMatch;
  articles: NewsArticle[];
  generatedAt?: string | null;
}

export interface ModelMetricData {
  modelName: string;
  architecture: string;
  role?: string;
  accuracy?: number | null;
  precision?: number | null;
  recall?: number | null;
  f1Score?: number | null;
  samples?: number | null;
  isBest: boolean;
}

export interface ConfusionMatrixData {
  labels: string[];
  matrix: number[][]; // [real][predicho]
}

// ===========================================================================
// 2. Tipos de la ingesta de noticias (/v1/sources)
// ===========================================================================

export type ScrapeStatus =
  | "idle"
  | "queued"
  | "connecting"
  | "crawling"
  | "cleaning"
  | "analyzing"
  | "completed"
  | "error";

export interface SourcePreset {
  id: string;
  name: string;
  domain: string;
  country: string;
  /** "Prensa Escrita" | "Medio Digital" */
  category: string;
  description: string;
  /** Emoji de bandera del país (campo de presentación del frontend). */
  flag: string;
  /** Texto corto para el logo (p. ej. "EL TIEMPO"). */
  logoText: string;
  /** Color de acento hex (p. ej. "#1e40af"). */
  accentColor: string;
}

/** Body de POST /v1/sources/scan (camelCase y snake_case aceptados). */
export interface ScanSiteRequest {
  url: string;
  maxArticles?: number; // 1..10, por defecto 4
  keywords?: string[];
  country?: CountryName;
  respectRobots?: boolean;
  analyze?: boolean; // por defecto true
}

/** Respuesta 202 de POST /v1/sources/scan. */
export interface ScrapeAccepted {
  jobId: string;
  status: ScrapeStatus;
  statusUrl: string;
  pollAfterSeconds: number; // 1.5 por defecto
}

export interface JobStep {
  step: number;
  totalSteps: number;
  message: string;
  at: string;
}

/** Progreso tal como lo pinta el front (compatible con ScrapingProgress). */
export interface ScrapingProgress {
  status: ScrapeStatus;
  currentStep: number;
  totalSteps: number;
  message: string;
  articlesFoundCount: number;
  articlesAnalyzedCount?: number;
}

/** Respuesta de GET /v1/sources/jobs/{jobId}. */
export interface ScrapeJobResponse {
  jobId: string;
  status: ScrapeStatus;
  currentStep: number;
  totalSteps: number;
  message: string;
  articlesFoundCount: number;
  articlesAnalyzedCount: number;
  createdAt?: string | null;
  updatedAt?: string | null;
  error?: string | null;
  steps: JobStep[];
  summary?: ScrapedSiteSummary | null;
}

/**
 * Entrada de GET /v1/sources/jobs (lista resumida).
 * Ojo: aquí el id se llama `id` (no `jobId`) y los contadores no llevan sufijo
 * `Count`; es lo que devuelve el router de ingesta.
 */
export interface ScrapeJobSummary {
  id: string;
  url: string;
  domain: string;
  status: ScrapeStatus;
  currentStep: number;
  totalSteps: number;
  message: string;
  articlesFound: number;
  articlesAnalyzed: number;
  error?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}

/**
 * Body de POST /v1/sources/analyze-url.
 * El servidor valida con el mismo modelo que `/scan`, pero solo usa
 * `url`, `country` y `respectRobots`; el resto se ignora.
 */
export interface AnalyzeUrlRequest {
  url: string;
  country?: CountryName;
  respectRobots?: boolean;
}

// ===========================================================================
// 3. Tipos de análisis e historial (/v1/analyze y /v1/analyses)
// ===========================================================================

export interface AnalyzeRequest {
  text: string;
  title?: string;
  sourceUrl?: string;
  mediaName?: string;
  country?: CountryName;
  language?: string;
}

export interface BatchAnalyzeRequest {
  items: AnalyzeRequest[]; // 1..50
}

export interface BatchAnalyzeResponse {
  count: number;
  results: TextAnalysisResult[];
}

export interface AnalysisSummary {
  id: string;
  createdAt: string;
  title?: string | null;
  mediaName?: string | null;
  country: string;
  sentiment: SentimentType;
  confidence: number;
  source: string;
  engine: string;
  latencyMs: number;
}

export interface AnalysesPage {
  total: number;
  limit: number;
  offset: number;
  items: AnalysisSummary[];
}

export interface ListAnalysesParams {
  limit?: number; // 1..100
  offset?: number;
  sentiment?: SentimentType;
  country?: string;
  source?: string;
  since?: string; // ISO 8601
}

// ===========================================================================
// 4. Tipos de dashboard y monitoreo
// ===========================================================================

export interface SentimentCounts {
  negativo: number;
  neutro: number;
  positivo: number;
}

export interface PercentageCounts {
  negativo: number;
  neutro: number;
  positivo: number;
}

export interface CountryCount {
  country: string;
  count: number;
  sentiment: SentimentCounts;
}

export interface MediaCount {
  media: string;
  count: number;
  sentiment: SentimentCounts;
}

export interface EngineCount {
  engine: string;
  count: number;
}

export interface LatencyStats {
  count: number;
  mean: number;
  p50: number;
  p95: number;
  p99: number;
}

export interface ScrapeJobStats {
  total: number;
  completed: number;
  error: number;
  running: number;
}

/** GET /v1/dashboard/overview */
export interface DashboardOverview {
  generatedAt: string;
  totalAnalyses: number;
  analysesToday: number;
  analysesLast7d: number;
  avgConfidence: number;
  sentiment: SentimentCounts;
  sentimentPct: PercentageCounts;
  topFrames: FrameTally[];
  countries: CountryCount[];
  media: MediaCount[];
  engines: EngineCount[];
  latencyMs: LatencyStats;
  scrapeJobs: ScrapeJobStats;
  uptimeSeconds: number;
  engine: string;
  degraded: boolean;
}

export interface TimeseriesPoint {
  date: string; // YYYY-MM-DD
  total: number;
  negativo: number;
  neutro: number;
  positivo: number;
}

/** GET /v1/dashboard/timeseries?days=30 */
export interface TimeseriesResponse {
  days: number;
  items: TimeseriesPoint[];
}

export interface CorpusCountryStats {
  country: string;
  totalArticles: number;
  sentimentBreakdown: PercentageCounts;
  frameBreakdown: FrameTally[];
  media: string[];
}

export interface MonthlyVolumePoint {
  month: string;
  total: number;
  negativo: number;
  neutro: number;
  positivo: number;
}

/** GET /v1/dashboard/corpus */
export interface CorpusDashboard {
  generatedAt: string;
  sourceFile: string;
  totalArticles: number;
  mediaCount: number;
  dateRange: Record<string, string>;
  sentimentBreakdown: PercentageCounts;
  frameBreakdown: FrameTally[];
  countries: CorpusCountryStats[];
  monthlyVolume: MonthlyVolumePoint[];
}

export interface FrameEvaluation {
  frame: string;
  frameId?: string | null;
  precision: number;
  recall: number;
  f1: number;
  support: number;
  threshold: number;
}

/** GET /v1/dashboard/models */
export interface ModelEvaluation {
  generatedAt?: string | null;
  sampleSize: number;
  engine: string;
  models: ModelMetricData[];
  sentiment: Record<string, unknown>;
  frames: FrameEvaluation[];
  confusionMatrix?: ConfusionMatrixData | null;
  thresholds: Record<string, number>;
  available: boolean;
  message: string;
}

export interface ModelInfo {
  name: string;
  role: string;
  available: boolean;
  loaded: boolean;
  architecture: string;
  path: string;
  maxLength: number;
  device: string;
  labels: string[];
}

export interface EngineInfo {
  requested: string;
  selected: string;
  degraded: boolean;
  reason: string;
}

export interface DatabaseInfo {
  status: string;
  path: string;
  analyses: number;
  sizeBytes: number;
}

/** GET /v1/health */
export interface HealthResponse {
  status: "ok" | "degraded";
  version: string;
  environment: string;
  uptimeSeconds: number;
  startedAt: string;
  engine: EngineInfo;
  models: ModelInfo[];
  database: DatabaseInfo;
  scraperEnabled: boolean;
}

/**
 * GET /v1/models.
 * Ojo: `frameLabels` son objetos "crudos" del router (los genera el endpoint,
 * no un modelo camelCase): usan `model_label` en snake_case.
 */
export interface FrameLabelInfo {
  id: FrameId;
  label: string;
  model_label: string;
  description: string;
  keywords: string[];
  threshold: number;
}

export interface ModelsResponse {
  engine: EngineInfo;
  models: ModelInfo[];
  sentimentLabels: string[];
  frameLabels: FrameLabelInfo[];
  thresholds: Record<string, number>;
  evaluationAvailable: boolean;
}

/** GET /v1/monitoring/stats */
export interface MonitoringStats {
  generatedAt: string;
  uptimeSeconds: number;
  requestsTotal: number;
  requestsByStatus: Record<string, number>;
  errorsTotal: number;
  analysesTotal: number;
  analysesByEngine: Record<string, number>;
  scrapeJobsTotal: number;
  latencyMs: Record<string, number>;
  engine: EngineInfo;
  database: DatabaseInfo;
  storeEventsEnabled: boolean;
}

// ===========================================================================
// 5. Errores tipados
// ===========================================================================

export interface ApiErrorPayload {
  error: {
    code: string;
    message: string;
    detail?: unknown;
  };
}

/**
 * Error uniforme del API.
 *
 * Códigos habituales del servidor (todos llegan en `{ error: { code, message, detail } }`):
 * - `validation_error` (422): el body no cumple el contrato.
 * - `invalid_text` (422): texto vacío o no analizable.
 * - `batch_too_large` (422).
 * - `unauthorized` (401): falta/sobra API key.
 * - `rate_limited` (429): demasiadas peticiones (mira `retryAfter`).
 * - `not_found` (404): análisis, job o página remota inexistente.
 * - `engine_error` (503): fallo del motor de análisis.
 * - `internal_error` (500).
 *
 * Ingesta de noticias (/v1/sources):
 * - `invalid_url` (422), `url_blocked` (422, SSRF), `unresolvable_host` (422),
 *   `extraction_failed` (422), `invalid_content` (422), `invalid_max_articles` (422).
 * - `robots_denied` (403): robots.txt prohíbe el rastreo.
 * - `scraper_disabled` (503): NLP_SCRAPER_ENABLED=false.
 * - `upstream_error`, `upstream_unavailable`, `upstream_timeout`,
 *   `response_too_large`, `too_many_redirects`, `scraper_error` (503): fallos del sitio.
 *
 * Además, el propio cliente usa `network_error` (status 0), `timeout`,
 * `invalid_response` y `scrape_job_error` (job terminó en `status="error"`).
 */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly detail?: unknown;
  readonly requestId?: string;
  readonly retryAfter?: number;

  constructor(
    message: string,
    options: {
      code: string;
      status: number;
      detail?: unknown;
      requestId?: string;
      retryAfter?: number;
    },
  ) {
    super(message);
    this.name = "ApiError";
    this.code = options.code;
    this.status = options.status;
    this.detail = options.detail;
    this.requestId = options.requestId;
    this.retryAfter = options.retryAfter;
  }
}

// ===========================================================================
// 6. Configuración y transporte
// ===========================================================================

const DEFAULT_BASE_URL = "http://localhost:8000";

interface ViteEnv {
  VITE_API_URL?: string;
  VITE_API_KEY?: string;
  VITE_API_TIMEOUT_MS?: string;
}

function readViteEnv(): ViteEnv {
  // `import.meta.env` solo existe con Vite; se lee sin tipos de Vite para que
  // este archivo también funcione en Node o en tests.
  const meta = import.meta as unknown as { env?: ViteEnv } | undefined;
  return meta?.env ?? {};
}

/** Normaliza "http://host:puerto/" -> "http://host:puerto". */
function normalizeBaseUrl(value: string | undefined): string {
  const base = (value ?? "").trim();
  if (!base) return DEFAULT_BASE_URL;
  return base.replace(/\/+$/, "");
}

export interface ApiClientOptions {
  /** Base URL del API; por defecto `VITE_API_URL` o http://localhost:8000. */
  baseUrl?: string;
  /** API key opcional (header `X-API-Key`); por defecto `VITE_API_KEY`. */
  apiKey?: string;
  /** Timeout de cada petición en ms; por defecto `VITE_API_TIMEOUT_MS` o 30000. */
  timeoutMs?: number;
  /** Implementación de fetch (inyectable en tests). */
  fetchImpl?: typeof fetch;
}

/**
 * Construye un query string a partir de un objeto plano; omite `undefined`,
 * `null` y cadenas vacías.
 */
function buildQuery(params: object): string {
  const search = new URLSearchParams();
  for (const [key, raw] of Object.entries(params)) {
    const value = raw as string | number | boolean | null | undefined;
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

export interface ApiClient {
  readonly baseUrl: string;
  request<T>(path: string, init?: RequestInit): Promise<T>;
  analyzeText(payload: AnalyzeRequest): Promise<TextAnalysisResult>;
  analyze(payload: AnalyzeRequest): Promise<TextAnalysisResult>;
  analyzeBatch(payload: BatchAnalyzeRequest): Promise<BatchAnalyzeResponse>;
  getAnalysis(analysisId: string): Promise<TextAnalysisResult>;
  listAnalyses(params?: ListAnalysesParams): Promise<AnalysesPage>;
  getSourcePresets(): Promise<SourcePreset[]>;
  scanSite(payload: ScanSiteRequest): Promise<ScrapeAccepted>;
  getScrapeJob(jobId: string): Promise<ScrapeJobResponse>;
  getScrapeJobs(limit?: number): Promise<ScrapeJobSummary[]>;
  analyzeUrl(payload: AnalyzeUrlRequest): Promise<NewsArticle>;
  getOverview(): Promise<DashboardOverview>;
  getTimeseries(days?: number): Promise<TimeseriesResponse>;
  getCorpusDashboard(): Promise<CorpusDashboard>;
  getModelEvaluation(): Promise<ModelEvaluation>;
  getRecentAnalyses(limit?: number): Promise<AnalysisSummary[]>;
  getMonitoringStats(): Promise<MonitoringStats>;
  getHealth(): Promise<HealthResponse>;
  getMetadata(): Promise<ModelsResponse>;
  getModels(): Promise<ModelsResponse>;
  getMetrics(): Promise<string>;
  pollJob(
    jobId: string,
    onProgress?: (job: ScrapeJobResponse) => void,
    options?: PollJobOptions,
  ): Promise<ScrapeJobResponse>;
}

export interface PollJobOptions {
  /** Intervalo entre sondeos en ms (por defecto 1500). */
  intervalMs?: number;
  /** Tiempo máximo de espera en ms (por defecto 300000 = 5 min). */
  timeoutMs?: number;
  /** Cancelación externa. */
  signal?: AbortSignal;
}

/**
 * Crea un cliente con configuración propia. Lo normal es importar las funciones
 * sueltas (ya configuradas), pero los tests pueden usar `createApiClient`.
 */
export function createApiClient(options: ApiClientOptions = {}): ApiClient {
  const env = readViteEnv();
  const baseUrl = normalizeBaseUrl(
    options.baseUrl ?? env.VITE_API_URL ?? DEFAULT_BASE_URL,
  );
  const apiKey = options.apiKey ?? env.VITE_API_KEY;
  const timeoutMs =
    options.timeoutMs ??
    (env.VITE_API_TIMEOUT_MS ? Number(env.VITE_API_TIMEOUT_MS) : 30_000);
  const fetchImpl: typeof fetch =
    options.fetchImpl ??
    ((...args: Parameters<typeof fetch>) => globalThis.fetch(...args));

  async function parseError(response: Response): Promise<ApiError> {
    const requestId = response.headers.get("X-Request-ID") ?? undefined;
    const retryAfterHeader = response.headers.get("Retry-After");
    const parsedRetryAfter = retryAfterHeader ? Number(retryAfterHeader) : undefined;
    const retryAfter =
      parsedRetryAfter !== undefined && Number.isFinite(parsedRetryAfter)
        ? parsedRetryAfter
        : undefined;
    let code = `http_${response.status}`;
    let message = `Error HTTP ${response.status} en ${response.url}`;
    let detail: unknown;
    try {
      const body = (await response.json()) as Partial<ApiErrorPayload>;
      if (body?.error && typeof body.error === "object") {
        code = String(body.error.code ?? code);
        message = String(body.error.message ?? message);
        detail = body.error.detail;
      }
    } catch {
      // respuesta sin JSON (p. ej. 502 de un proxy): se conserva el mensaje genérico
    }
    return new ApiError(message, {
      code,
      status: response.status,
      detail,
      requestId,
      retryAfter,
    });
  }

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const url = path.startsWith("http") ? path : `${baseUrl}${path}`;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const signal = init.signal
      ? anySignal([init.signal, controller.signal])
      : controller.signal;

    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");
    if (init.body !== undefined && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    if (apiKey) headers.set("X-API-Key", apiKey);

    let response: Response;
    try {
      response = await fetchImpl(url, { ...init, headers, signal });
    } catch (error) {
      const aborted = (error as { name?: string })?.name === "AbortError";
      throw new ApiError(
        aborted
          ? `La petición a ${path} superó el timeout de ${timeoutMs} ms`
          : `No se pudo conectar con el API en ${baseUrl}`,
        { code: aborted ? "timeout" : "network_error", status: 0, detail: error },
      );
    } finally {
      clearTimeout(timer);
    }

    if (!response.ok) throw await parseError(response);

    if (response.status === 204) return undefined as T;
    const text = await response.text();
    if (!text) return undefined as T;
    try {
      return JSON.parse(text) as T;
    } catch (error) {
      throw new ApiError(`Respuesta no JSON del API en ${path}`, {
        code: "invalid_response",
        status: response.status,
        detail: error,
      });
    }
  }

  async function getText(path: string): Promise<string> {
    const response = await fetchImpl(`${baseUrl}${path}`, {
      headers: apiKey ? { "X-API-Key": apiKey } : undefined,
    });
    if (!response.ok) throw await parseError(response);
    return response.text();
  }

  const client: ApiClient = {
    baseUrl,
    request,

    // ----------------------------- análisis ------------------------------
    analyzeText: (payload) =>
      request<TextAnalysisResult>("/v1/analyze", {
        method: "POST",
        body: JSON.stringify(payload),
      }),

    analyze: (payload) =>
      request<TextAnalysisResult>("/v1/analyze", {
        method: "POST",
        body: JSON.stringify(payload),
      }),

    analyzeBatch: (payload) =>
      request<BatchAnalyzeResponse>("/v1/analyze/batch", {
        method: "POST",
        body: JSON.stringify(payload),
      }),

    getAnalysis: (analysisId) =>
      request<TextAnalysisResult>(`/v1/analyses/${encodeURIComponent(analysisId)}`),

    listAnalyses: (params = {}) =>
      request<AnalysesPage>(`/v1/analyses${buildQuery({ ...params })}`),

    // -------------------------- ingesta de noticias -----------------------
    getSourcePresets: () => request<SourcePreset[]>("/v1/sources/presets"),

    scanSite: (payload) =>
      request<ScrapeAccepted>("/v1/sources/scan", {
        method: "POST",
        body: JSON.stringify(payload),
      }),

    getScrapeJob: (jobId) =>
      request<ScrapeJobResponse>(`/v1/sources/jobs/${encodeURIComponent(jobId)}`),

    getScrapeJobs: (limit = 20) =>
      request<ScrapeJobSummary[]>(`/v1/sources/jobs${buildQuery({ limit })}`),

    analyzeUrl: (payload) =>
      request<NewsArticle>("/v1/sources/analyze-url", {
        method: "POST",
        body: JSON.stringify(payload),
      }),

    // ------------------------------ dashboard -----------------------------
    getOverview: () => request<DashboardOverview>("/v1/dashboard/overview"),

    getTimeseries: (days = 30) =>
      request<TimeseriesResponse>(`/v1/dashboard/timeseries${buildQuery({ days })}`),

    getCorpusDashboard: () => request<CorpusDashboard>("/v1/dashboard/corpus"),

    getModelEvaluation: () => request<ModelEvaluation>("/v1/dashboard/models"),

    getRecentAnalyses: (limit = 20) =>
      request<AnalysisSummary[]>(
        `/v1/dashboard/recent${buildQuery({ limit })}`,
      ),

    // ----------------------------- monitoreo ------------------------------
    getMonitoringStats: () =>
      request<MonitoringStats>("/v1/monitoring/stats"),

    getHealth: () => request<HealthResponse>("/v1/health"),

    getMetadata: () => request<ModelsResponse>("/v1/models"),

    getModels: () => request<ModelsResponse>("/v1/models"),

    /** Texto plano en formato Prometheus (`text/plain; version=0.0.4`). */
    getMetrics: () => getText("/metrics"),

    // ------------------------------- polling ------------------------------
    pollJob: (jobId, onProgress, pollOptions = {}) =>
      pollJobWith(client, jobId, onProgress, pollOptions),
  };

  return client;
}

/** Combina varias señales de aborto (AbortSignal.any no está en todos los navegadores). */
function anySignal(signals: AbortSignal[]): AbortSignal {
  const controller = new AbortController();
  const onAbort = () => controller.abort();
  for (const signal of signals) {
    if (signal.aborted) {
      controller.abort();
      break;
    }
    signal.addEventListener("abort", onAbort, { once: true });
  }
  return controller.signal;
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Abortado", "AbortError"));
      return;
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(new DOMException("Abortado", "AbortError"));
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

async function pollJobWith(
  client: ApiClient,
  jobId: string,
  onProgress?: (job: ScrapeJobResponse) => void,
  options: PollJobOptions = {},
): Promise<ScrapeJobResponse> {
  const intervalMs = options.intervalMs ?? 1500;
  const deadline = Date.now() + (options.timeoutMs ?? 5 * 60 * 1000);
  let last: ScrapeJobResponse | null = null;

  for (;;) {
    if (options.signal?.aborted) {
      throw new DOMException("Abortado", "AbortError");
    }
    last = await client.getScrapeJob(jobId);
    onProgress?.(last);

    if (last.status === "completed") return last;
    if (last.status === "error") {
      throw new ApiError(last.error || "El trabajo de scraping terminó con error", {
        code: "scrape_job_error",
        status: 200,
        detail: last,
      });
    }
    if (Date.now() > deadline) {
      throw new ApiError(
        `El job ${jobId} no terminó en el tiempo esperado (${options.timeoutMs ?? 300_000} ms)`,
        { code: "timeout", status: 0, detail: last },
      );
    }
    await sleep(intervalMs, options.signal);
  }
}

// ===========================================================================
// 7. Cliente por defecto y funciones sueltas (las que usa el frontend)
// ===========================================================================

/** Cliente singleton configurado con VITE_API_URL / VITE_API_KEY. */
export const api = createApiClient();

export const analyzeText = api.analyzeText;
export const analyze = api.analyze;
export const analyzeBatch = api.analyzeBatch;
export const getAnalysis = api.getAnalysis;
export const listAnalyses = api.listAnalyses;
export const getSourcePresets = api.getSourcePresets;
export const scanSite = api.scanSite;
export const getScrapeJob = api.getScrapeJob;
export const getScrapeJobs = api.getScrapeJobs;
export const analyzeUrl = api.analyzeUrl;
export const getOverview = api.getOverview;
export const getTimeseries = api.getTimeseries;
export const getCorpusDashboard = api.getCorpusDashboard;
export const getModelEvaluation = api.getModelEvaluation;
export const getRecentAnalyses = api.getRecentAnalyses;
export const getMonitoringStats = api.getMonitoringStats;
export const getHealth = api.getHealth;
export const getMetadata = api.getMetadata;
export const getModels = api.getModels;
export const getMetrics = api.getMetrics;
export const pollJob = api.pollJob;
