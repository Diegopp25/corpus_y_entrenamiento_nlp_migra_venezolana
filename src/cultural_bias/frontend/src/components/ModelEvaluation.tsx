import React, { useCallback, useEffect, useState } from "react"
import { describeApiError, getModelEvaluation } from "../services/api"
import type { ConfusionMatrixData, FrameEvaluation, ModelEvaluationData } from "../types"
import { CpuIcon } from "./Icons"

/** Convierte ratios 0–1 del artefacto real a porcentaje 0–100. */
const toPercent = (value: number | null | undefined): number | null => {
  if (value === null || value === undefined || !Number.isFinite(value)) return null
  const pct = value <= 1 ? value * 100 : value
  return Math.round(pct * 10) / 10
}

const formatPercent = (value: number | null | undefined): string => {
  const pct = toPercent(value)
  return pct === null ? "—" : `${pct}%`
}

const ROLE_LABELS: Record<string, string> = {
  sentiment: "Sentimiento (3 clases)",
  frames: "Encuadres (multietiqueta)",
}

/** Lee un número de un objeto `Record<string, unknown>` sin usar `any`. */
function readNumber(source: unknown, key: string): number | null {
  if (!source || typeof source !== "object") return null
  const value = (source as Record<string, unknown>)[key]
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

/** Obtiene la matriz de confusión del artefacto (campo raíz o `sentiment`). */
function extractConfusionMatrix(data: ModelEvaluationData): ConfusionMatrixData | null {
  if (data.confusionMatrix) return data.confusionMatrix
  const candidate = (data.sentiment as { confusionMatrix?: unknown })?.confusionMatrix
  if (
    candidate &&
    typeof candidate === "object" &&
    Array.isArray((candidate as ConfusionMatrixData).labels) &&
    Array.isArray((candidate as ConfusionMatrixData).matrix)
  ) {
    return candidate as ConfusionMatrixData
  }
  return null
}

const frameBarColor = (f1: number): string => {
  if (f1 >= 70) return "from-emerald-600 to-emerald-400"
  if (f1 >= 50) return "from-violet-600 to-orange-400"
  return "from-slate-600 to-slate-400"
}

export const ModelEvaluation: React.FC = () => {
  const [evaluation, setEvaluation] = useState<ModelEvaluationData | null>(null)
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const loadEvaluation = useCallback(async () => {
    setIsLoading(true)
    setErrorMessage(null)
    try {
      const data = await getModelEvaluation()
      setEvaluation(data)
    } catch (error) {
      setEvaluation(null)
      setErrorMessage(describeApiError(error))
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    let alive = true
    setIsLoading(true)
    getModelEvaluation()
      .then(data => {
        if (alive) setEvaluation(data)
      })
      .catch((error: unknown) => {
        if (alive) {
          setEvaluation(null)
          setErrorMessage(describeApiError(error))
        }
      })
      .finally(() => {
        if (alive) setIsLoading(false)
      })
    return () => {
      alive = false
    }
  }, [])

  if (isLoading) {
    return (
      <div className="flex min-w-0 flex-col gap-6 pb-6">
        <section className="flex min-h-[280px] flex-col items-center justify-center gap-3 rounded-2xl border border-white/[0.08] bg-[#10131d]/85 p-6 shadow-xl shadow-black/30 backdrop-blur-md">
          <div className="size-10 animate-spin rounded-full border-2 border-blue-400/30 border-t-blue-400" />
          <p className="text-sm font-semibold text-white">
            Cargando métricas reales del API…
          </p>
          <p className="text-xs text-slate-400">
            GET /v1/dashboard/models · evaluación sobre el corpus etiquetado
          </p>
        </section>
      </div>
    )
  }

  if (errorMessage || !evaluation) {
    return (
      <div className="flex min-w-0 flex-col gap-6 pb-6">
        <section
          role="alert"
          className="rounded-2xl border border-red-500/30 bg-red-500/[0.07] p-6 shadow-xl shadow-black/30"
        >
          <h3 className="mb-2 font-['Outfit'] text-base font-semibold tracking-tight text-red-200">
            No se pudieron cargar las métricas del modelo
          </h3>
          <p className="break-words text-sm leading-relaxed text-red-200/90">
            {errorMessage ?? "El API no devolvió datos de evaluación."}
          </p>
          <p className="mt-2 text-xs text-red-300/70">
            Verifica que el API esté corriendo en{" "}
            <span className="font-mono">
              {import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000"}
            </span>
            .
          </p>
          <button
            type="button"
            className="mt-4 rounded-xl border border-white/[0.12] bg-white/[0.06] px-4 py-2 text-xs font-semibold text-slate-200 transition-all hover:bg-white/[0.12] hover:text-white"
            onClick={() => void loadEvaluation()}
          >
            Reintentar
          </button>
        </section>
      </div>
    )
  }

  if (!evaluation.available) {
    return (
      <div className="flex min-w-0 flex-col gap-6 pb-6">
        <section className="rounded-2xl border border-amber-500/25 bg-amber-500/[0.06] p-6 shadow-xl shadow-black/30">
          <div className="mb-2 flex items-center gap-2.5">
            <CpuIcon size={20} color="#f59e0b" />
            <h3 className="font-['Outfit'] text-base font-semibold tracking-tight text-amber-100">
              Evaluación de modelos no disponible
            </h3>
          </div>
          <p className="text-sm leading-relaxed text-amber-100/90">{evaluation.message}</p>
          <p className="mt-3 border-t border-amber-500/15 pt-3 text-xs text-amber-200/70">
            No se muestran métricas de ejemplo: esta sección solo pinta cifras reales del
            artefacto de evaluación del API.
          </p>
        </section>
      </div>
    )
  }

  const confusionMatrix = extractConfusionMatrix(evaluation)
  const sentimentAccuracy = readNumber(evaluation.sentiment, "accuracy")
  const sentimentMacroF1 = readNumber(evaluation.sentiment, "macroF1")
  const sentimentSamples = readNumber(evaluation.sentiment, "samples") ?? evaluation.sampleSize
  const frames: FrameEvaluation[] = evaluation.frames ?? []
  const generatedAtLabel = evaluation.generatedAt
    ? new Intl.DateTimeFormat("es-CO", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(evaluation.generatedAt))
    : null

  return (
    <div className="flex min-w-0 flex-col gap-6 pb-6">
      {/* Model Benchmark Table Card */}
      <section className="min-w-0 rounded-2xl border border-white/[0.08] bg-[#10131d]/85 p-5 shadow-xl shadow-black/30 backdrop-blur-md sm:p-6">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2.5">
            <CpuIcon size={20} color="#3b82f6" />
            <h3 className="font-['Outfit'] text-base font-semibold tracking-tight text-white">
              Evaluación real de los modelos BETO
            </h3>
          </div>
          <span className="rounded-full border border-blue-400/20 bg-blue-500/10 px-3 py-1 text-xs font-medium text-blue-200">
            {evaluation.sampleSize} artículos del corpus etiquetado
          </span>
        </div>

        <div className="w-full overflow-x-auto rounded-xl border border-white/[0.07]">
          <table className="w-full min-w-[820px] border-collapse text-left">
            <thead className="bg-white/[0.035] text-[10px] uppercase tracking-wider text-slate-400">
              <tr>
                <th className="px-3 py-3 font-semibold">Modelo / Tarea</th>
                <th className="px-3 py-3 font-semibold">Arquitectura base</th>
                <th className="px-3 py-3 font-semibold">Exactitud</th>
                <th className="px-3 py-3 font-semibold">Precisión</th>
                <th className="px-3 py-3 font-semibold">Recall</th>
                <th className="px-3 py-3 font-semibold">F1-Score</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.06] text-xs text-slate-300">
              {evaluation.models.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-3 py-6 text-center text-slate-500">
                    El artefacto de evaluación no incluye filas de modelos.
                  </td>
                </tr>
              )}
              {evaluation.models.map((model, index) => (
                <tr
                  key={`${model.modelName}-${model.role ?? index}`}
                  className={`transition-colors hover:bg-white/[0.04] ${
                    model.isBest ? "bg-blue-500/[0.045] hover:bg-blue-500/[0.08]" : ""
                  }`}
                >
                  <td className="px-3 py-3">
                    <div className="flex flex-col gap-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold text-slate-100">
                          {model.modelName}
                        </span>
                        {model.isBest && (
                          <span className="rounded-full border border-emerald-400/20 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-300">
                            Mejor F1
                          </span>
                        )}
                      </div>
                      <span className="text-[10.5px] text-slate-500">
                        {ROLE_LABELS[model.role ?? ""] ?? model.role ?? "Tarea no indicada"}
                        {model.samples ? ` · ${model.samples} muestras` : ""}
                      </span>
                    </div>
                  </td>
                  <td className="max-w-[320px] px-3 py-3 text-[11.5px] leading-relaxed text-slate-400">
                    {model.architecture}
                  </td>
                  <td className="whitespace-nowrap px-3 py-3 tabular-nums">
                    {formatPercent(model.accuracy)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-3 tabular-nums">
                    {formatPercent(model.precision)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-3 tabular-nums">
                    {formatPercent(model.recall)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-3 tabular-nums">
                    <strong className="font-semibold text-indigo-200">
                      {formatPercent(model.f1Score)}
                    </strong>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="mt-3 text-[11px] leading-relaxed text-slate-500">
          Cifras reales de <span className="font-mono">GET /v1/dashboard/models</span>
          {generatedAtLabel ? ` (generadas el ${generatedAtLabel})` : ""}. El artefacto
          usa ratios 0–1 y aquí se convierten a porcentaje. La exactitud del modelo de
          encuadres es exactitud de subconjunto (las 7 etiquetas deben coincidir), por eso
          es baja; para ese modelo conviene mirar precisión/recall/F1 por etiqueta.
        </p>

        <details className="group mt-3 rounded-xl border border-white/[0.07] bg-white/[0.02] px-3.5 py-2.5">
          <summary className="cursor-pointer list-none text-[11.5px] font-semibold text-slate-400 transition-colors hover:text-slate-200">
            Notas metodológicas del API
          </summary>
          <p className="mt-2 whitespace-pre-line text-[11.5px] leading-relaxed text-slate-400">
            {evaluation.message}
          </p>
        </details>
      </section>

      {/* Two Column Layout: Confusion Matrix + Per-Frame Performance */}
      <div className="grid min-w-0 grid-cols-1 gap-5 xl:grid-cols-2">
        {/* Confusion Matrix */}
        <section className="min-w-0 rounded-2xl border border-white/[0.08] bg-[#10131d]/85 p-5 shadow-xl shadow-black/30 backdrop-blur-md sm:p-6">
          <div className="mb-5 flex flex-wrap items-start justify-between gap-2">
            <h3 className="font-['Outfit'] text-base font-semibold tracking-tight text-white">
              Matriz de Confusión (Sentimiento - BETO)
            </h3>
            <span className="text-xs text-slate-500">
              Filas: Real | Columnas: Predicho
            </span>
          </div>

          {confusionMatrix ? (
            <div className="w-full overflow-x-auto">
              <div className="mb-2 grid min-w-[360px] grid-cols-[minmax(4rem,0.85fr)_repeat(3,minmax(4.5rem,1fr))] gap-2">
                <span aria-hidden="true" />
                {confusionMatrix.labels.map(lbl => (
                  <span
                    key={lbl}
                    className="self-center text-center text-[10px] font-medium text-slate-400"
                  >
                    Pred. {lbl}
                  </span>
                ))}
              </div>

              {confusionMatrix.labels.map((rowLabel, rIdx) => (
                <div
                  key={rowLabel}
                  className="mb-2 grid min-w-[360px] grid-cols-[minmax(4rem,0.85fr)_repeat(3,minmax(4.5rem,1fr))] gap-2"
                >
                  <span className="self-center text-xs font-medium text-slate-400">
                    Real {rowLabel}
                  </span>
                  {(confusionMatrix.matrix[rIdx] ?? []).map((val, cIdx) => {
                    const isDiagonal = rIdx === cIdx
                    return (
                      <div
                        key={cIdx}
                        className={`flex min-h-[4.25rem] flex-col items-center justify-center gap-1 rounded-xl border ${
                          isDiagonal
                            ? "border-emerald-500/20 bg-gradient-to-br from-emerald-500/[0.16] to-emerald-500/[0.04]"
                            : "border-white/[0.06] bg-white/[0.025]"
                        }`}
                      >
                        <span className="text-base font-semibold tabular-nums text-slate-100">
                          {val}
                        </span>
                        <span className="text-[10px] text-slate-500">
                          {isDiagonal ? "Acierto" : "Error"}
                        </span>
                      </div>
                    )
                  })}
                </div>
              ))}

              <p className="mt-4 border-t border-white/[0.07] pt-3 text-xs leading-relaxed text-slate-400">
                Exactitud global en sentimiento:{" "}
                <strong className="text-slate-100">
                  {formatPercent(sentimentAccuracy)}
                </strong>{" "}
                · macro-F1:{" "}
                <strong className="text-slate-100">{formatPercent(sentimentMacroF1)}</strong>{" "}
                · {sentimentSamples} muestras evaluadas.
              </p>
            </div>
          ) : (
            <p className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 text-xs text-slate-500">
              El artefacto de evaluación no incluye matriz de confusión.
            </p>
          )}
        </section>

        {/* Per-Frame Performance */}
        <section className="min-w-0 rounded-2xl border border-white/[0.08] bg-[#10131d]/85 p-5 shadow-xl shadow-black/30 backdrop-blur-md sm:p-6">
          <div className="mb-5 flex flex-wrap items-start justify-between gap-2">
            <h3 className="font-['Outfit'] text-base font-semibold tracking-tight text-white">
              Desempeño por Encuadre (F1-Score)
            </h3>
            <span className="text-xs text-slate-500">
              Clasificación multietiqueta · umbral por encuadre
            </span>
          </div>

          {frames.length === 0 ? (
            <p className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 text-xs text-slate-500">
              El artefacto de evaluación no incluye métricas por encuadre.
            </p>
          ) : (
            <div className="flex flex-col gap-4">
              {frames.map((item, index) => {
                const f1Pct = toPercent(item.f1) ?? 0
                const thresholdPct = toPercent(item.threshold)
                return (
                  <div
                    key={`${item.frame}-${item.frameId ?? index}`}
                    className="flex flex-col gap-2"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-xs font-medium text-slate-200">
                        {item.frame}
                      </span>
                      <div className="flex flex-wrap gap-2 text-[10px] tabular-nums text-slate-400">
                        <span>P: {formatPercent(item.precision)}</span>
                        <span>R: {formatPercent(item.recall)}</span>
                        <strong className="font-semibold text-orange-300">
                          F1: {formatPercent(item.f1)}
                        </strong>
                        <span title="Artículos etiquetados con este encuadre">
                          n={item.support}
                        </span>
                        {thresholdPct !== null && (
                          <span title="Umbral de decisión del encuadre">
                            u={thresholdPct}%
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.07]">
                      <div
                        className={`h-full rounded-full bg-gradient-to-r transition-[width] duration-500 ${frameBarColor(f1Pct)}`}
                        style={{ width: `${Math.max(0, Math.min(100, f1Pct))}%` }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
