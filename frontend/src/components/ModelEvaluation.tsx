import React, { useState } from "react"
import {
  BENCHMARK_MODELS,
  FRAMES_PERFORMANCE,
  SENTIMENT_CONFUSION_MATRIX,
} from "../data/modelMetrics"
import { CpuIcon } from "./Icons"

export const ModelEvaluation: React.FC = () => {
  const [selectedModel, setSelectedModel] = useState<string>(
    BENCHMARK_MODELS[0].modelName,
  )

  return (
    <div className="flex min-w-0 flex-col gap-6 pb-6">
      {/* Model Benchmark Table Card */}
      <section className="min-w-0 rounded-2xl border border-white/[0.08] bg-[#10131d]/85 p-5 shadow-xl shadow-black/30 backdrop-blur-md sm:p-6">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2.5">
            <CpuIcon size={20} color="#3b82f6" />
            <h3 className="font-['Outfit'] text-base font-semibold tracking-tight text-white">
              Comparativa de Arquitecturas NLP
            </h3>
          </div>
          <span className="rounded-full border border-blue-400/20 bg-blue-500/10 px-3 py-1 text-xs font-medium text-blue-200">
            Validado sobre 1,420 artículos
          </span>
        </div>

        <div className="w-full overflow-x-auto rounded-xl border border-white/[0.07]">
          <table className="w-full min-w-[760px] border-collapse text-left">
            <thead className="bg-white/[0.035] text-[10px] uppercase tracking-wider text-slate-400">
              <tr>
                <th className="px-3 py-3 font-semibold">Modelo</th>
                <th className="px-3 py-3 font-semibold">Arquitectura Base</th>
                <th className="px-3 py-3 font-semibold">Exactitud</th>
                <th className="px-3 py-3 font-semibold">Precisión</th>
                <th className="px-3 py-3 font-semibold">Recall</th>
                <th className="px-3 py-3 font-semibold">F1-Score</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.06] text-xs text-slate-300">
              {BENCHMARK_MODELS.map(model => (
                <tr
                  key={model.modelName}
                  className={`cursor-pointer transition-colors hover:bg-white/[0.04] ${
                    selectedModel === model.modelName ? "bg-white/[0.035]" : ""
                  } ${model.isBest ? "bg-blue-500/[0.045] hover:bg-blue-500/[0.08]" : ""}`}
                  onClick={() => setSelectedModel(model.modelName)}
                >
                  <td className="whitespace-nowrap px-3 py-3">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-slate-100">
                        {model.modelName}
                      </span>
                      {model.isBest && (
                        <span className="rounded-full border border-emerald-400/20 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-300">
                          Mejor Desempeño
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-3 py-3 text-slate-400">
                    {model.architecture}
                  </td>
                  <td className="whitespace-nowrap px-3 py-3 tabular-nums">
                    {model.accuracy}%
                  </td>
                  <td className="whitespace-nowrap px-3 py-3 tabular-nums">
                    {model.precision}%
                  </td>
                  <td className="whitespace-nowrap px-3 py-3 tabular-nums">
                    {model.recall}%
                  </td>
                  <td className="whitespace-nowrap px-3 py-3 tabular-nums">
                    <strong className="font-semibold text-indigo-200">
                      {model.f1Score}%
                    </strong>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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

          <div className="w-full overflow-x-auto">
            <div className="mb-2 grid min-w-[360px] grid-cols-[minmax(4rem,0.85fr)_repeat(3,minmax(4.5rem,1fr))] gap-2">
              <span aria-hidden="true" />
              {SENTIMENT_CONFUSION_MATRIX.labels.map(lbl => (
                <span
                  key={lbl}
                  className="self-center text-center text-[10px] font-medium text-slate-400"
                >
                  Pred. {lbl}
                </span>
              ))}
            </div>

            {SENTIMENT_CONFUSION_MATRIX.labels.map((rowLabel, rIdx) => (
              <div
                key={rowLabel}
                className="mb-2 grid min-w-[360px] grid-cols-[minmax(4rem,0.85fr)_repeat(3,minmax(4.5rem,1fr))] gap-2"
              >
                <span className="self-center text-xs font-medium text-slate-400">
                  Real {rowLabel}
                </span>
                {SENTIMENT_CONFUSION_MATRIX.matrix[rIdx].map((val, cIdx) => {
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
          </div>

          <p className="mt-4 border-t border-white/[0.07] pt-3 text-xs leading-relaxed text-slate-400">
            Exactitud global en sentimiento: <strong>89.4%</strong>. La mayor tasa de
            confusión se produce entre textos neutros catalogados como negativos leves.
          </p>
        </section>

        {/* Per-Frame Performance */}
        <section className="min-w-0 rounded-2xl border border-white/[0.08] bg-[#10131d]/85 p-5 shadow-xl shadow-black/30 backdrop-blur-md sm:p-6">
          <div className="mb-5 flex flex-wrap items-start justify-between gap-2">
            <h3 className="font-['Outfit'] text-base font-semibold tracking-tight text-white">
              Desempeño por Encuadre (F1-Score)
            </h3>
            <span className="text-xs text-slate-500">Clasificación Multietiqueta</span>
          </div>

          <div className="flex flex-col gap-4">
            {FRAMES_PERFORMANCE.map(item => (
              <div key={item.frame} className="flex flex-col gap-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-xs font-medium text-slate-200">{item.frame}</span>
                  <div className="flex flex-wrap gap-2 text-[10px] tabular-nums text-slate-400">
                    <span>P: {item.precision}%</span>
                    <span>R: {item.recall}%</span>
                    <strong className="font-semibold text-orange-300">
                      F1: {item.f1}%
                    </strong>
                  </div>
                </div>

                <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.07]">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-violet-600 to-orange-400 transition-[width] duration-500"
                    style={{ width: `${item.f1}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}
