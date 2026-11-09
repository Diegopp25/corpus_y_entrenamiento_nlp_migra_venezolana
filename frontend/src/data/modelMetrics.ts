/**
 * NOTA DE MIGRACIÓN
 * ----------------
 * Este módulo contenía las métricas simuladas del frontend:
 *
 * - `BENCHMARK_MODELS` (accuracy ~89 % sobre "1.420 artículos curados")
 * - `FRAMES_PERFORMANCE`
 * - `SENTIMENT_CONFUSION_MATRIX`
 * - `HYPOTHESIS_COMPARATIVE_DATA` (780/640 noticias por país)
 *
 * Todos esos datos eran ficticios y ya se eliminaron. Las cifras que muestra
 * la UI ahora provienen del API real:
 *
 * - `GET /v1/dashboard/models`  -> `ModelEvaluationData` (artefacto real sobre
 *   los 156 artículos del corpus etiquetado; métricas 0–1).
 * - `GET /v1/dashboard/corpus`  -> `CorpusDashboardData` (CSV etiquetado real:
 *   156 artículos, 77 Colombia / 79 México).
 *
 * Los tipos de contrato viven en `src/types/index.ts`; el cliente HTTP en
 * `src/services/api.ts`. Este archivo se conserva únicamente como referencia
 * documental para quien busque las constantes antiguas.
 */

export {}
