import {
  ApiError,
  describeApiError,
  getScrapeJob,
  isAbortError,
  pollJob,
  scanSite,
} from "./api"
import type { NewsArticle, ScrapedSiteSummary, ScrapingProgress } from "../types"

export interface ScrapingOptions {
  url: string
  maxArticles?: number
  keywords?: string[]
  /** El API todavía no filtra por rango de fechas; se conserva por compatibilidad. */
  dateRange?: string
  onProgress?: (progress: ScrapingProgress) => void
  /** Cancelación externa (AbortController) para cortar el polling al desmontar. */
  signal?: AbortSignal
}

const DEFAULT_TOTAL_STEPS = 5

/**
 * Escanea un sitio de noticias real: crea un job en `POST /v1/sources/scan` y
 * sigue su progreso con `GET /v1/sources/jobs/{jobId}` cada ~1,5 s.
 *
 * `onProgress` se llama con cada respuesta del job y con el estado inicial en
 * cola. Resuelve con el `summary` real cuando el job termina correctamente y
 * lanza un `ApiError` legible si el job termina en `status === "error"`.
 */
export async function scrapeNewsSite(options: ScrapingOptions): Promise<ScrapedSiteSummary> {
  const { url, maxArticles = 4, keywords, onProgress, signal } = options
  const cleanUrl = url.trim()
  if (!cleanUrl) {
    throw new ApiError("Ingresa la URL de un medio de noticias para rastrear.", {
      code: "invalid_url",
      status: 422,
    })
  }

  const notify = (progress: ScrapingProgress) => onProgress?.(progress)

  let accepted
  try {
    accepted = await scanSite({
      url: cleanUrl,
      maxArticles,
      ...(keywords && keywords.length > 0 ? { keywords } : {}),
    })
  } catch (error) {
    notify({
      status: "error",
      currentStep: 0,
      totalSteps: DEFAULT_TOTAL_STEPS,
      message: describeApiError(error),
      articlesFoundCount: 0,
    })
    throw error
  }

  notify({
    status: accepted.status,
    currentStep: 0,
    totalSteps: DEFAULT_TOTAL_STEPS,
    message: "Trabajo de rastreo en cola…",
    articlesFoundCount: 0,
  })

  let job
  try {
    job = await pollJob(      accepted.jobId,
      (current) => {
        notify({
          status: current.status,
          currentStep: current.currentStep,
          totalSteps: current.totalSteps,
          message: current.message,
          articlesFoundCount: current.articlesFoundCount,
          articlesAnalyzedCount: current.articlesAnalyzedCount,
        })
      },
      {
        // el API recomienda 1,5 s (accepted.pollAfterSeconds)
        intervalMs: Math.round((accepted.pollAfterSeconds ?? 1.5) * 1000),
        timeoutMs: 5 * 60 * 1000,
        signal,
      },
    )
  } catch (error) {
    if (isAbortError(error)) {
      notify({
        status: "idle",
        currentStep: 0,
        totalSteps: DEFAULT_TOTAL_STEPS,
        message: "Rastreo cancelado.",
        articlesFoundCount: 0,
      })
      throw error
    }
    notify({
      status: "error",
      currentStep: 0,
      totalSteps: DEFAULT_TOTAL_STEPS,
      message: describeApiError(error),
      articlesFoundCount: 0,
    })
    throw error
  }

  // El API puede marcar el job como `completed` unas décimas antes de adjuntar
  // el `summary`: reintenta brevemente la consulta para no fallar por esa carrera.
  for (let attempt = 0; attempt < 5 && !job.summary; attempt += 1) {
    await delay(500, signal)
    if (signal?.aborted) throw new DOMException("Abortado", "AbortError")
    job = await getScrapeJob(job.jobId)
    if (job.status === "error") {
      throw new ApiError(job.error || "El trabajo de rastreo terminó con error", {
        code: "scrape_job_error",
        status: 200,
        detail: job,
      })
    }
  }

  if (!job.summary) {
    throw new ApiError(
      "El trabajo de rastreo terminó sin un resumen del sitio. Intenta de nuevo.",
      { code: "scrape_job_error", status: 200, detail: job },
    )
  }

  return job.summary
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
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

/** Exporta el corpus real (artículos del job) a CSV. */
export function exportCorpusToCSV(articles: NewsArticle[]): string {
  const headers = [
    "ID",
    "Medio",
    "País",
    "Fecha",
    "Título",
    "Sentimiento",
    "Encuadre Dominante",
    "URL",
  ]
  const rows = articles.map((article) => {
    const sentiment = article.preAnalyzedResult?.sentiment.prediction ?? "N/A"
    const topFrame = article.preAnalyzedResult?.frames[0]?.label ?? article.category
    const cleanTitle = `"${article.title.replace(/"/g, '""')}"`
    return [
      article.id,
      article.media,
      article.country,
      article.date,
      cleanTitle,
      sentiment,
      topFrame,
      article.url,
    ].join(",")
  })

  return [headers.join(","), ...rows].join("\n")
}

/** Exporta el resumen real del sitio (artículos + agregados) a JSON. */
export function exportCorpusToJSON(summary: ScrapedSiteSummary): string {
  return JSON.stringify(summary, null, 2)
}
