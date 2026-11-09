import { ApiError, analyzeText } from "./api"
import type { CountryName, TextAnalysisResult } from "../types"

export interface AnalyzeMetadata {
  title?: string
  sourceUrl?: string
  mediaName?: string
  country?: CountryName
}

/**
 * Analiza un texto con el API real (`POST /v1/analyze`).
 *
 * El análisis local simulado (`VOCABULARY_RULES`, frames inventados) se
 * eliminó: ahora el resultado es el `TextAnalysisResult` que devuelve el motor
 * BETO del servidor, con `meta` (motor, latencia, warnings) y fechas ISO 8601.
 *
 * Mantiene el nombre que ya importaba `SingleAnalyzer`, pero ahora es asíncrona.
 */
export async function analyzeNewsText(
  text: string,
  metadata?: AnalyzeMetadata,
): Promise<TextAnalysisResult> {
  const trimmed = text.trim()
  if (!trimmed) {
    throw new ApiError("El texto está vacío: pega o escribe una noticia para analizarla.", {
      code: "invalid_text",
      status: 422,
    })
  }

  return analyzeText({
    text: trimmed,
    ...(metadata?.title ? { title: metadata.title } : {}),
    ...(metadata?.sourceUrl ? { sourceUrl: metadata.sourceUrl } : {}),
    ...(metadata?.mediaName ? { mediaName: metadata.mediaName } : {}),
    ...(metadata?.country ? { country: metadata.country } : {}),
  })
}

/**
 * Formatea la fecha ISO 8601 que devuelve el API para mostrarla en la UI.
 * Si el valor no es una fecha válida, se devuelve tal cual.
 */
export function formatAnalysisDate(isoDate: string): string {
  const date = new Date(isoDate)
  if (Number.isNaN(date.getTime())) return isoDate
  return new Intl.DateTimeFormat("es-CO", {
    dateStyle: "long",
    timeStyle: "short",
  }).format(date)
}

/** Une y deduplica los avisos que devuelve el motor en `meta.warnings`. */
export function collectAnalysisWarnings(result: TextAnalysisResult): string[] {
  const warnings = result.meta?.warnings ?? []
  return Array.from(new Set(warnings.filter((warning) => warning.trim().length > 0)))
}
