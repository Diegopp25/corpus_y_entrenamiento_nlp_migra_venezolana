/**
 * Cliente TypeScript del API de cobertura mediática de la migración venezolana.
 *
 * Adaptación de `integrations/frontend-api-client.ts` (checkout principal
 * `migra-nlp`) para el frontend real:
 *
 * - Sin dependencias externas (solo `fetch`, navegadores modernos).
 * - Tipos compartidos importados de `src/types` (una sola fuente de verdad).
 * - Base URL: `VITE_API_URL` y, si no está definida, `http://127.0.0.1:8000`.
 * - Header opcional `X-API-Key` a partir de `VITE_API_KEY`.
 * - Errores tipados: `ApiError` con `code` (código del API), `status` (HTTP),
 *   `detail`, `requestId` y `retryAfter`.
 * - `pollJob` sigue el progreso de un job de scraping cada 1,5 s.
 *
 * Uso básico:
 *
 *   import { analyzeText, scanSite, pollJob } from "./api";
 *
 *   const analysis = await analyzeText({ text, title, mediaName });
 *   const accepted = await scanSite({ url: "https://www.eltiempo.com", maxArticles: 4 });
 *   const job = await pollJob(accepted.jobId, (j) => console.log(j.currentStep));
 */

import type {
  AnalysesPage,
  AnalysisSummary,
  AnalyzeRequest,
  AnalyzeUrlRequest,
  ApiErrorPayload,
  BatchAnalyzeRequest,
  BatchAnalyzeResponse,
  CorpusDashboardData,
  DashboardOverview,
  HealthResponse,
  ListAnalysesParams,
  ModelEvaluationData,
  ModelsResponse,
  MonitoringStats,
  NewsArticle,
  ScrapeAccepted,
  ScrapeJobResponse,
  ScrapeJobSummary,
  ScanSiteRequest,
  SourcePreset,
  TextAnalysisResult,
  TimeseriesResponse,
} from "../types"

// ===========================================================================
// 1. Errores tipados
// ===========================================================================

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
  readonly code: string
  readonly status: number
  readonly detail?: unknown
  readonly requestId?: string
  readonly retryAfter?: number

  constructor(
    message: string,
    options: {
      code: string
      status: number
      detail?: unknown
      requestId?: string
      retryAfter?: number
    },
  ) {
    super(message)
    this.name = "ApiError"
    this.code = options.code
    this.status = options.status
    this.detail = options.detail
    this.requestId = options.requestId
    this.retryAfter = options.retryAfter
  }
}

/** `true` si el error viene de una petición cancelada con AbortController. */
export function isAbortError(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    (error as { name?: string }).name === "AbortError"
  )
}

const FRIENDLY_CODES: Record<string, string> = {
  invalid_text: "El texto está vacío o no se puede analizar.",
  rate_limited: "El API recibió demasiadas peticiones. Espera unos segundos y reintenta.",
  engine_error: "El motor de análisis BETO falló al procesar la noticia.",
  invalid_url: "La URL no es válida. Usa el dominio del medio (p. ej. eltiempo.com).",
  url_blocked: "La URL no está permitida por el API (restricción SSRF).",
  unresolvable_host: "No se pudo resolver el dominio del medio.",
  robots_denied: "robots.txt del sitio prohíbe el rastreo automático.",
  scraper_disabled: "El rastreo de sitios está deshabilitado en el API.",
  extraction_failed: "No se pudo extraer el texto de la página.",
  upstream_timeout: "El sitio de noticias tardó demasiado en responder.",
  upstream_unavailable: "El sitio de noticias no está disponible en este momento.",
  invalid_response: "El API devolvió una respuesta inesperada.",
  scrape_job_error: "El trabajo de rastreo terminó con error.",
}

/**
 * Mensaje legible (en español) para mostrar en la UI a partir de un error
 * desconocido. Conserva el `message` real del API y añade una pista amigable
 * cuando el código es conocido.
 */
export function describeApiError(error: unknown): string {
  if (error instanceof ApiError) {
    const message = error.message.trim()
    // Los mensajes del API suelen ser autosuficientes; solo se añade la pista
    // amigable cuando el mensaje es corto o genérico.
    if (message.length >= 30) return message
    const hint = FRIENDLY_CODES[error.code]
    if (hint) return message ? `${message} ${hint}` : hint
    return message || `Error del API (${error.code}, HTTP ${error.status})`
  }
  if (error instanceof Error && error.message) return error.message
  return "Ocurrió un error inesperado al comunicarse con el API."
}

// ===========================================================================
// 2. Configuración y transporte
// ===========================================================================

const DEFAULT_BASE_URL = "http://127.0.0.1:8000"

interface ViteEnv {
  VITE_API_URL?: string
  VITE_API_KEY?: string
  VITE_API_TIMEOUT_MS?: string
}

function readViteEnv(): ViteEnv {
  // Acceso estático a import.meta.env.*: Vite sustituye estas expresiones en
  // build e inyecta los valores en dev. (El acceso dinámico `import.meta.env`
  // no funciona ni en el bundle de producción ni en SSR.)
  try {
    return {
      VITE_API_URL: import.meta.env.VITE_API_URL,
      VITE_API_KEY: import.meta.env.VITE_API_KEY,
      VITE_API_TIMEOUT_MS: import.meta.env.VITE_API_TIMEOUT_MS,
    }
  } catch {
    // Entornos sin Vite (p. ej. Node): se usan los valores por defecto.
    return {}
  }
}

/** Normaliza "http://host:puerto/" -> "http://host:puerto". */
function normalizeBaseUrl(value: string | undefined): string {
  const base = (value ?? "").trim()
  if (!base) return DEFAULT_BASE_URL
  return base.replace(/\/+$/, "")
}

export interface ApiClientOptions {
  /** Base URL del API; por defecto `VITE_API_URL` o http://127.0.0.1:8000. */
  baseUrl?: string
  /** API key opcional (header `X-API-Key`); por defecto `VITE_API_KEY`. */
  apiKey?: string
  /** Timeout de cada petición en ms; por defecto `VITE_API_TIMEOUT_MS` o 30000. */
  timeoutMs?: number
  /** Implementación de fetch (inyectable en tests). */
  fetchImpl?: typeof fetch
}

function parseTimeout(value: string | undefined): number {
  if (!value) return 30_000
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 30_000
}

/** Construye un query string; omite `undefined`, `null` y cadenas vacías. */
function buildQuery(params: object): string {
  const search = new URLSearchParams()
  for (const [key, raw] of Object.entries(params)) {
    const value = raw as string | number | boolean | null | undefined
    if (value === undefined || value === null || value === "") continue
    search.set(key, String(value))
  }
  const query = search.toString()
  return query ? `?${query}` : ""
}

export interface PollJobOptions {
  /** Intervalo entre sondeos en ms (por defecto 1500). */
  intervalMs?: number
  /** Tiempo máximo de espera en ms (por defecto 300000 = 5 min). */
  timeoutMs?: number
  /** Cancelación externa. */
  signal?: AbortSignal
}

export interface ApiClient {
  readonly baseUrl: string
  request<T>(path: string, init?: RequestInit): Promise<T>
  analyzeText(payload: AnalyzeRequest): Promise<TextAnalysisResult>
  analyze(payload: AnalyzeRequest): Promise<TextAnalysisResult>
  analyzeBatch(payload: BatchAnalyzeRequest): Promise<BatchAnalyzeResponse>
  getAnalysis(analysisId: string): Promise<TextAnalysisResult>
  listAnalyses(params?: ListAnalysesParams): Promise<AnalysesPage>
  getSourcePresets(): Promise<SourcePreset[]>
  scanSite(payload: ScanSiteRequest): Promise<ScrapeAccepted>
  getScrapeJob(jobId: string): Promise<ScrapeJobResponse>
  getScrapeJobs(limit?: number): Promise<ScrapeJobSummary[]>
  analyzeUrl(payload: AnalyzeUrlRequest): Promise<NewsArticle>
  getOverview(): Promise<DashboardOverview>
  getTimeseries(days?: number): Promise<TimeseriesResponse>
  getCorpusDashboard(): Promise<CorpusDashboardData>
  getModelEvaluation(): Promise<ModelEvaluationData>
  getRecentAnalyses(limit?: number): Promise<AnalysisSummary[]>
  getMonitoringStats(): Promise<MonitoringStats>
  getHealth(): Promise<HealthResponse>
  getMetadata(): Promise<ModelsResponse>
  getModels(): Promise<ModelsResponse>
  getMetrics(): Promise<string>
  pollJob(
    jobId: string,
    onProgress?: (job: ScrapeJobResponse) => void,
    options?: PollJobOptions,
  ): Promise<ScrapeJobResponse>
}

/**
 * Crea un cliente con configuración propia. Lo normal es importar las funciones
 * sueltas (ya configuradas), pero los tests pueden usar `createApiClient`.
 */
export function createApiClient(options: ApiClientOptions = {}): ApiClient {
  const env = readViteEnv()
  const baseUrl = normalizeBaseUrl(options.baseUrl ?? env.VITE_API_URL ?? DEFAULT_BASE_URL)
  const apiKey = options.apiKey ?? env.VITE_API_KEY
  const timeoutMs = options.timeoutMs ?? parseTimeout(env.VITE_API_TIMEOUT_MS)
  const fetchImpl: typeof fetch =
    options.fetchImpl ?? ((...args: Parameters<typeof fetch>) => globalThis.fetch(...args))

  async function parseError(response: Response): Promise<ApiError> {
    const requestId = response.headers.get("X-Request-ID") ?? undefined
    const retryAfterHeader = response.headers.get("Retry-After")
    const parsedRetryAfter = retryAfterHeader ? Number(retryAfterHeader) : undefined
    const retryAfter =
      parsedRetryAfter !== undefined && Number.isFinite(parsedRetryAfter)
        ? parsedRetryAfter
        : undefined
    let code = `http_${response.status}`
    let message = `Error HTTP ${response.status} en ${response.url}`
    let detail: unknown
    try {
      const body = (await response.json()) as Partial<ApiErrorPayload>
      if (body?.error && typeof body.error === "object") {
        code = String(body.error.code ?? code)
        message = String(body.error.message ?? message)
        detail = body.error.detail
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
    })
  }

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const url = path.startsWith("http") ? path : `${baseUrl}${path}`
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), timeoutMs)
    const signal = init.signal ? anySignal([init.signal, controller.signal]) : controller.signal

    const headers = new Headers(init.headers)
    headers.set("Accept", "application/json")
    if (init.body !== undefined && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json")
    }
    if (apiKey) headers.set("X-API-Key", apiKey)

    let response: Response
    try {
      response = await fetchImpl(url, { ...init, headers, signal })
    } catch (error) {
      const aborted = (error as { name?: string })?.name === "AbortError"
      throw new ApiError(
        aborted
          ? `La petición a ${path} superó el timeout de ${timeoutMs} ms`
          : `No se pudo conectar con el API en ${baseUrl}. Verifica que esté corriendo y que VITE_API_URL sea correcta.`,
        { code: aborted ? "timeout" : "network_error", status: 0, detail: error },
      )
    } finally {
      clearTimeout(timer)
    }

    if (!response.ok) throw await parseError(response)

    if (response.status === 204) return undefined as T
    const text = await response.text()
    if (!text) return undefined as T
    try {
      return JSON.parse(text) as T
    } catch (error) {
      throw new ApiError(`Respuesta no JSON del API en ${path}`, {
        code: "invalid_response",
        status: response.status,
        detail: error,
      })
    }
  }

  async function getText(path: string): Promise<string> {
    const response = await fetchImpl(`${baseUrl}${path}`, {
      headers: apiKey ? { "X-API-Key": apiKey } : undefined,
    })
    if (!response.ok) throw await parseError(response)
    return response.text()
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

    getCorpusDashboard: () => request<CorpusDashboardData>("/v1/dashboard/corpus"),

    getModelEvaluation: () => request<ModelEvaluationData>("/v1/dashboard/models"),

    getRecentAnalyses: (limit = 20) =>
      request<AnalysisSummary[]>(`/v1/dashboard/recent${buildQuery({ limit })}`),

    // ----------------------------- monitoreo ------------------------------
    getMonitoringStats: () => request<MonitoringStats>("/v1/monitoring/stats"),

    getHealth: () => request<HealthResponse>("/v1/health"),

    getMetadata: () => request<ModelsResponse>("/v1/models"),

    getModels: () => request<ModelsResponse>("/v1/models"),

    /** Texto plano en formato Prometheus (`text/plain; version=0.0.4`). */
    getMetrics: () => getText("/metrics"),

    // ------------------------------- polling ------------------------------
    pollJob: (jobId, onProgress, pollOptions = {}) =>
      pollJobWith(client, jobId, onProgress, pollOptions),
  }

  return client
}

/** Combina varias señales de aborto (AbortSignal.any no está en todos los navegadores). */
function anySignal(signals: AbortSignal[]): AbortSignal {
  const controller = new AbortController()
  const onAbort = () => controller.abort()
  for (const signal of signals) {
    if (signal.aborted) {
      controller.abort()
      break
    }
    signal.addEventListener("abort", onAbort, { once: true })
  }
  return controller.signal
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Abortado", "AbortError"))
      return
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort)
      resolve()
    }, ms)
    const onAbort = () => {
      clearTimeout(timer)
      reject(new DOMException("Abortado", "AbortError"))
    }
    signal?.addEventListener("abort", onAbort, { once: true })
  })
}

async function pollJobWith(
  client: ApiClient,
  jobId: string,
  onProgress?: (job: ScrapeJobResponse) => void,
  options: PollJobOptions = {},
): Promise<ScrapeJobResponse> {
  const intervalMs = options.intervalMs ?? 1500
  const deadline = Date.now() + (options.timeoutMs ?? 5 * 60 * 1000)
  let last: ScrapeJobResponse | null = null

  for (;;) {
    if (options.signal?.aborted) {
      throw new DOMException("Abortado", "AbortError")
    }
    last = await client.getScrapeJob(jobId)
    onProgress?.(last)

    if (last.status === "completed") return last
    if (last.status === "error") {
      throw new ApiError(last.error || "El trabajo de scraping terminó con error", {
        code: "scrape_job_error",
        status: 200,
        detail: last,
      })
    }
    if (Date.now() > deadline) {
      throw new ApiError(
        `El job ${jobId} no terminó en el tiempo esperado (${options.timeoutMs ?? 300_000} ms)`,
        { code: "timeout", status: 0, detail: last },
      )
    }
    await sleep(intervalMs, options.signal)
  }
}

// ===========================================================================
// 3. Cliente por defecto y funciones sueltas (las que usa el frontend)
// ===========================================================================

/** Cliente singleton configurado con VITE_API_URL / VITE_API_KEY. */
export const api = createApiClient()

export const analyzeText = api.analyzeText
export const analyze = api.analyze
export const analyzeBatch = api.analyzeBatch
export const getAnalysis = api.getAnalysis
export const listAnalyses = api.listAnalyses
export const getSourcePresets = api.getSourcePresets
export const scanSite = api.scanSite
export const getScrapeJob = api.getScrapeJob
export const getScrapeJobs = api.getScrapeJobs
export const analyzeUrl = api.analyzeUrl
export const getOverview = api.getOverview
export const getTimeseries = api.getTimeseries
export const getCorpusDashboard = api.getCorpusDashboard
export const getModelEvaluation = api.getModelEvaluation
export const getRecentAnalyses = api.getRecentAnalyses
export const getMonitoringStats = api.getMonitoringStats
export const getHealth = api.getHealth
export const getMetadata = api.getMetadata
export const getModels = api.getModels
export const getMetrics = api.getMetrics
export const pollJob = api.pollJob
