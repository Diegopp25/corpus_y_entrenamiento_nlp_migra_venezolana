import React from "react"
import type { CulturalBias } from "../types"
import { CompassIcon, ShieldAlertIcon, BriefcaseIcon, SparklesIcon } from "./Icons"

interface CulturalBiasCardProps {
  bias: CulturalBias
  mediaName?: string
}

export const CulturalBiasCard: React.FC<CulturalBiasCardProps> = ({
  bias,
  mediaName,
}) => {
  const {
    detectedBias,
    colombiaAlignmentScore,
    mexicoAlignmentScore,
    reasoning,
    highlightedTerms,
  } = bias

  const isColombiaDominant = colombiaAlignmentScore > mexicoAlignmentScore + 5
  const isMexicoDominant = mexicoAlignmentScore > colombiaAlignmentScore + 5

  return (
    <div className="bg-gradient-to-b from-[#141826]/90 to-[#0e111b]/90 backdrop-blur-md border border-orange-500/20 rounded-2xl p-5 sm:p-7 shadow-xl shadow-black/50 transition-all hover:border-orange-500/35">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div className="flex items-center gap-2.5">
          <CompassIcon size={19} color="#f97316" />
          <h3 className="font-['Outfit'] text-[17px] font-semibold text-white tracking-tight">
            Diagnóstico de Sesgo Cultural
          </h3>
        </div>
        <span className="bg-orange-500/10 border border-orange-500/30 text-orange-400 text-xs font-semibold px-3 py-1 rounded-full">
          {detectedBias}
        </span>
      </div>

      <p className="text-[12.5px] text-slate-300 leading-relaxed bg-white/[0.03] border border-white/[0.07] p-3.5 rounded-xl mb-5">
        <strong className="text-white">Hipótesis de Grado:</strong> Medios de{" "}
        <strong className="text-red-400">Colombia</strong> tienden a encuadrar la
        migración como generadora de inseguridad y delincuencia, mientras que en{" "}
        <strong className="text-emerald-400">México</strong> se destaca el lente
        económico/laboral y de tránsito internacional.
      </p>

      {/* Alignment Meters */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5 mb-5">
        {/* Medidor Colombia */}
        <div
          className={`bg-[#0e111a]/80 border rounded-xl p-3.5 flex flex-col gap-2 transition-all ${
            isColombiaDominant
              ? "border-red-500/40 shadow-lg shadow-red-500/10"
              : "border-white/[0.07]"
          }`}
        >
          <div className="flex items-center justify-between text-xs font-semibold">
            <span className="text-slate-200">Sesgo Colombia</span>
            <span className="text-sm font-bold text-white">
              {colombiaAlignmentScore}%
            </span>
          </div>
          <div className="w-full h-2 bg-white/[0.06] rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-blue-500 to-red-500 rounded-full transition-all duration-700"
              style={{ width: `${Math.min(100, colombiaAlignmentScore)}%` }}
            />
          </div>
          <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
            <ShieldAlertIcon size={13} color="#ef4444" />
            <span>Enfoque Punitivo / Seguridad</span>
          </div>
        </div>

        {/* Medidor México */}
        <div
          className={`bg-[#0e111a]/80 border rounded-xl p-3.5 flex flex-col gap-2 transition-all ${
            isMexicoDominant
              ? "border-emerald-500/40 shadow-lg shadow-emerald-500/10"
              : "border-white/[0.07]"
          }`}
        >
          <div className="flex items-center justify-between text-xs font-semibold">
            <span className="text-slate-200">Sesgo México</span>
            <span className="text-sm font-bold text-white">{mexicoAlignmentScore}%</span>
          </div>
          <div className="w-full h-2 bg-white/[0.06] rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-emerald-500 to-orange-500 rounded-full transition-all duration-700"
              style={{ width: `${Math.min(100, mexicoAlignmentScore)}%` }}
            />
          </div>
          <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
            <BriefcaseIcon size={13} color="#10b981" />
            <span>Enfoque Laboral / Tránsito</span>
          </div>
        </div>
      </div>

      {/* Reasoning Box */}
      <div className="bg-[#0b0d14]/75 border border-white/[0.06] rounded-xl p-4 mb-4">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-purple-300 mb-2">
          <SparklesIcon size={14} color="#a855f7" />
          <span>Interpretación del Modelo BETO</span>
        </div>
        <p className="text-[13px] text-slate-300 leading-relaxed">{reasoning}</p>
        {mediaName && (
          <p className="text-[11.5px] text-slate-500 mt-4">
            Fuente detectada: <strong className="text-slate-400">{mediaName}</strong>
          </p>
        )}
      </div>

      {/* Terms Chips */}
      {highlightedTerms.length > 0 && (
        <div className="flex flex-col gap-2">
          <span className="text-xs text-slate-400">
            Términos léxicos de mayor peso detectados:
          </span>
          <div className="flex flex-wrap gap-1.5">
            {highlightedTerms.map((t, idx) => {
              const chipColor =
                t.biasType === "colombia"
                  ? "bg-red-500/15 text-red-300 border-red-500/30"
                  : t.biasType === "mexico"
                    ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                    : t.biasType === "negative"
                      ? "bg-orange-500/15 text-orange-300 border-orange-500/30"
                      : "bg-blue-500/15 text-blue-300 border-blue-500/30"

              return (
                <span
                  key={idx}
                  className={`text-[11.5px] px-2.5 py-1 rounded-md border inline-flex items-center gap-1 font-medium ${chipColor}`}
                >
                  {t.term}
                  <span className="text-[10px] opacity-70">+{t.weight}</span>
                </span>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
