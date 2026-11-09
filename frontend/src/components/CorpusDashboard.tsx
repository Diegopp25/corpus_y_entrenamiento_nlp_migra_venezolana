import { useState } from "react"
import { HYPOTHESIS_COMPARATIVE_DATA } from "../data/modelMetrics"
import { ShieldAlertIcon, BriefcaseIcon, SparklesIcon, CompassIcon } from "./Icons"
import { RadarChart } from "./RadarChart"
import type { RadarSeries } from "./RadarChart"

export const CorpusDashboard: React.FC = () => {
  const [selectedView, setSelectedView] = useState<"both" | "colombia" | "mexico">("both")
  const [chartType, setChartType] = useState<"bars" | "radar">("radar")
  const { colombia, mexico } = HYPOTHESIS_COMPARATIVE_DATA

  // Frame list in order
  const frames = [
    "Seguridad",
    "Empleo y economía",
    "Tránsito migratorio",
    "Acceso a servicios",
    "Política migratoria",
    "Integración social",
    "Otros",
  ]

  // Prepare series for Radar Chart
  const radarSeries: RadarSeries[] = []
  if (selectedView === "both" || selectedView === "colombia") {
    radarSeries.push({
      name: "🇨🇴",
      color: "#ef4444",
      fillColor: "rgba(239, 68, 68, 0.25)",
      values: frames.map(
        f => colombia.frameBreakdown.find(item => item.frame === f)?.pct || 0,
      ),
    })
  }
  if (selectedView === "both" || selectedView === "mexico") {
    radarSeries.push({
      name: "🇲🇽",
      color: "#10b981",
      fillColor: "rgba(16, 185, 129, 0.25)",
      values: frames.map(
        f => mexico.frameBreakdown.find(item => item.frame === f)?.pct || 0,
      ),
    })
  }

  return (
    <div className="flex min-w-0 flex-col gap-6 pb-6">
      {/* Hypothesis Statement Card */}
      <section className="rounded-2xl border border-purple-500/15 bg-gradient-to-br from-[#171522]/95 via-[#10131d]/95 to-[#0c0f18]/95 p-5 shadow-xl shadow-black/30 sm:p-6">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2.5">
            <CompassIcon size={22} color="#a855f7" />
            <h2 className="font-['Outfit'] text-base font-semibold tracking-tight text-white">
              Hipótesis Central del Estudio
            </h2>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* Colombia Card */}
          <div className="flex min-w-0 flex-col gap-3 rounded-xl border border-red-500/15 bg-red-500/[0.035] p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-semibold text-slate-100">
                Colombia (Primer Receptor Fronterizo)
              </span>
              <span className="rounded-full border border-white/[0.08] bg-white/[0.04] px-2.5 py-1 text-xs text-slate-300">
                780 Noticias
              </span>
            </div>
            <p className="text-sm leading-relaxed text-slate-300 mb-4">
              <strong>Tendencia observada:</strong> La cobertura mediática asocia
              recurrentemente a la migración con amenazas a la seguridad pública,
              delincuencia organizada y saturación de los sistemas asistenciales.
            </p>
            <div className="inline-flex self-start items-center gap-2 rounded-lg border border-red-500/15 bg-red-500/[0.06] px-3 py-2 text-xs text-slate-200">
              <ShieldAlertIcon size={14} color="#ef4444" />
              <span>
                Encuadre Seguridad: <strong className="text-white">64.2%</strong>{" "}
                (Preponderante)
              </span>
            </div>
          </div>

          {/* Mexico Card */}
          <div className="flex min-w-0 flex-col gap-3 rounded-xl border border-emerald-500/15 bg-emerald-500/[0.035] p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-semibold text-slate-100">
                México (Destino de Tránsito y Asentamiento Secundario)
              </span>
              <span className="rounded-full border border-white/[0.08] bg-white/[0.04] px-2.5 py-1 text-xs text-slate-300">
                640 Noticias
              </span>
            </div>
            <p className="text-sm leading-relaxed text-slate-300 mb-4">
              <strong>Tendencia observada:</strong> La cobertura mediática prioriza la
              condición de tránsito hacia EE.UU. y destaca el aporte como fuerza laboral
              en industrias manufactureras del norte del país.
            </p>
            <div className="inline-flex self-start items-center gap-2 rounded-lg border border-emerald-500/15 bg-emerald-500/[0.06] px-3 py-2 text-xs text-slate-200">
              <BriefcaseIcon size={14} color="#10b981" />
              <span>
                Encuadre Empleo/Economía: <strong className="text-white">58.7%</strong>{" "}
                (Preponderante)
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* Filter tabs */}
      <div className="flex max-w-full gap-1 overflow-x-auto rounded-xl border border-white/[0.07] bg-[#10131d]/75 p-1.5">
        <button
          type="button"
          aria-pressed={selectedView === "both"}
          className={`shrink-0 rounded-lg border px-3 py-2 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-400 ${
            selectedView === "both"
              ? "border-white/[0.1] bg-white/[0.09] text-white"
              : "border-transparent text-slate-400 hover:bg-white/[0.05] hover:text-slate-100"
          }`}
          onClick={() => setSelectedView("both")}
        >
          <span>Comparativa Conjunta (🇨🇴 vs 🇲🇽)</span>
        </button>
        <button
          type="button"
          aria-pressed={selectedView === "colombia"}
          className={`shrink-0 rounded-lg border px-3 py-2 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-400 ${
            selectedView === "colombia"
              ? "border-white/[0.1] bg-white/[0.09] text-white"
              : "border-transparent text-slate-400 hover:bg-white/[0.05] hover:text-slate-100"
          }`}
          onClick={() => setSelectedView("colombia")}
        >
          <span>Medios de Colombia</span>
        </button>
        <button
          type="button"
          aria-pressed={selectedView === "mexico"}
          className={`shrink-0 rounded-lg border px-3 py-2 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-400 ${
            selectedView === "mexico"
              ? "border-white/[0.1] bg-white/[0.09] text-white"
              : "border-transparent text-slate-400 hover:bg-white/[0.05] hover:text-slate-100"
          }`}
          onClick={() => setSelectedView("mexico")}
        >
          <span>Medios de México</span>
        </button>
      </div>

      {/* Visual Comparison: Sentiments */}
      <div className="grid min-w-0 grid-cols-1 gap-5 xl:grid-cols-2">
        {/* Sentiment breakdown */}
        <section className="flex min-w-0 flex-col rounded-2xl border border-white/[0.08] bg-[#10131d]/85 p-5 shadow-xl shadow-black/30 backdrop-blur-md sm:p-6">
          <div className="mb-5 flex flex-wrap items-start justify-between gap-2">
            <h3 className="font-['Outfit'] text-base font-semibold tracking-tight text-white">
              Distribución de Sentimiento por País
            </h3>
          </div>

          <div className="flex flex-col gap-5">
            {/* Colombia */}
            {(selectedView === "both" || selectedView === "colombia") && (
              <div className="flex flex-col gap-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm font-semibold text-slate-200">
                    Medios Colombianos
                  </span>
                  <span className="text-xs font-medium text-red-300">
                    Predominio Negativo (52.4%)
                  </span>
                </div>
                <div className="flex min-h-8 w-full overflow-hidden rounded-lg border border-white/[0.06] bg-white/[0.04]">
                  <div
                    className="flex min-w-0 items-center justify-center overflow-hidden bg-gradient-to-r from-red-700 to-red-500 px-1 text-[10px] font-semibold text-white sm:text-xs"
                    style={{ width: `${colombia.sentimentBreakdown.negativo}%` }}
                    title={`Negativo: ${colombia.sentimentBreakdown.negativo}%`}
                  >
                    {colombia.sentimentBreakdown.negativo}% Neg
                  </div>
                  <div
                    className="flex min-w-0 items-center justify-center overflow-hidden bg-gradient-to-r from-slate-600 to-slate-500 px-1 text-[10px] font-semibold text-white sm:text-xs"
                    style={{ width: `${colombia.sentimentBreakdown.neutro}%` }}
                    title={`Neutro: ${colombia.sentimentBreakdown.neutro}%`}
                  >
                    {colombia.sentimentBreakdown.neutro}% Neu
                  </div>
                  <div
                    className="flex min-w-0 items-center justify-center overflow-hidden bg-gradient-to-r from-emerald-700 to-emerald-500 px-1 text-[10px] font-semibold text-white sm:text-xs"
                    style={{ width: `${colombia.sentimentBreakdown.positivo}%` }}
                    title={`Positivo: ${colombia.sentimentBreakdown.positivo}%`}
                  >
                    {colombia.sentimentBreakdown.positivo}% Pos
                  </div>
                </div>
              </div>
            )}

            {/* Mexico */}
            {(selectedView === "both" || selectedView === "mexico") && (
              <div className="flex flex-col gap-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm font-semibold text-slate-200">
                    Medios Mexicanos
                  </span>
                  <span className="text-xs font-medium text-emerald-300">
                    Equilibrio Positivo / Neutro (68.2%)
                  </span>
                </div>
                <div className="flex min-h-8 w-full overflow-hidden rounded-lg border border-white/[0.06] bg-white/[0.04]">
                  <div
                    className="flex min-w-0 items-center justify-center overflow-hidden bg-gradient-to-r from-red-700 to-red-500 px-1 text-[10px] font-semibold text-white sm:text-xs"
                    style={{ width: `${mexico.sentimentBreakdown.negativo}%` }}
                    title={`Negativo: ${mexico.sentimentBreakdown.negativo}%`}
                  >
                    {mexico.sentimentBreakdown.negativo}% Neg
                  </div>
                  <div
                    className="flex min-w-0 items-center justify-center overflow-hidden bg-gradient-to-r from-slate-600 to-slate-500 px-1 text-[10px] font-semibold text-white sm:text-xs"
                    style={{ width: `${mexico.sentimentBreakdown.neutro}%` }}
                    title={`Neutro: ${mexico.sentimentBreakdown.neutro}%`}
                  >
                    {mexico.sentimentBreakdown.neutro}% Neu
                  </div>
                  <div
                    className="flex min-w-0 items-center justify-center overflow-hidden bg-gradient-to-r from-emerald-700 to-emerald-500 px-1 text-[10px] font-semibold text-white sm:text-xs"
                    style={{ width: `${mexico.sentimentBreakdown.positivo}%` }}
                    title={`Positivo: ${mexico.sentimentBreakdown.positivo}%`}
                  >
                    {mexico.sentimentBreakdown.positivo}% Pos
                  </div>
                </div>
              </div>
            )}
          </div>

          <p className="mt-5 border-t border-white/[0.07] pt-4 text-xs leading-relaxed text-slate-400">
            En Colombia, el sentimiento negativo supera al positivo en una proporción de
            2.7 a 1, motivado por noticias policiales. En México, la cobertura positiva es
            1.6 veces mayor que en Colombia.
          </p>
        </section>

        {/* Framing Contrast Radar/Bars */}
        <section className="flex min-w-0 flex-col rounded-2xl border border-white/[0.08] bg-[#10131d]/85 p-5 shadow-xl shadow-black/30 backdrop-blur-md sm:p-6">
          <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="font-['Outfit'] text-base font-semibold tracking-tight text-white">
                Contraste de los 7 Encuadres Mediáticos
              </h3>
              <span className="text-xs text-slate-500">
                % de presencia en el corpus por país
              </span>
            </div>
            <div className="inline-flex shrink-0 gap-0.5 rounded-lg border border-white/[0.07] bg-[#0b0e17] p-1">
              <button
                type="button"
                aria-pressed={chartType === "radar"}
                className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-400 ${
                  chartType === "radar"
                    ? "bg-white/[0.1] text-white"
                    : "text-slate-400 hover:text-white"
                }`}
                onClick={() => setChartType("radar")}
              >
                Radar
              </button>
              <button
                type="button"
                aria-pressed={chartType === "bars"}
                className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-400 ${
                  chartType === "bars"
                    ? "bg-white/[0.1] text-white"
                    : "text-slate-400 hover:text-white"
                }`}
                onClick={() => setChartType("bars")}
              >
                Barras
              </button>
            </div>
          </div>

          {chartType === "radar" ? (
            <div className="flex min-w-0 flex-col items-center">
              <RadarChart axes={frames} series={radarSeries} size={320} />
              <p className="mt-4 border-t border-white/[0.07] pt-4 text-xs leading-relaxed text-slate-400">
                El gráfico de radar ilustra la asimetría: Colombia muestra un vértice
                pronunciado hacia{" "}
                <strong className="font-semibold text-red-300">Seguridad (64.2%)</strong>,
                mientras que México se expande hacia{" "}
                <strong className="font-semibold text-emerald-300">Empleo (58.7%)</strong>{" "}
                y{" "}
                <strong className="font-semibold text-emerald-300">
                  Tránsito (54.3%)
                </strong>
                .
              </p>
            </div>
          ) : (
            <div className="flex animate-[enterFadeIn_350ms_ease-out] flex-col gap-4">
              {frames.map(frameName => {
                const colScore =
                  colombia.frameBreakdown.find(f => f.frame === frameName)?.pct || 0
                const mexScore =
                  mexico.frameBreakdown.find(f => f.frame === frameName)?.pct || 0
                const diff = Math.round((colScore - mexScore) * 10) / 10

                return (
                  <div key={frameName} className="flex flex-col gap-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-medium text-slate-200">
                        {frameName}
                      </span>
                      <span className="rounded-full border border-white/[0.08] bg-white/[0.04] px-2 py-0.5 text-[10px] text-slate-400">
                        {diff > 0 ? `🇨🇴 +${diff}%` : `🇲🇽 +${Math.abs(diff)}%`}
                      </span>
                    </div>

                    {/* Dual Bar */}
                    <div className="flex flex-col gap-1.5">
                      {(selectedView === "both" || selectedView === "colombia") && (
                        <div className="grid grid-cols-[1.25rem_minmax(0,1fr)_2.5rem] items-center gap-2">
                          <span className="text-xs">🇨🇴</span>
                          <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.07]">
                            <div
                              className="h-full rounded-full bg-gradient-to-r from-red-700 to-red-400 transition-[width] duration-500"
                              style={{ width: `${colScore}%` }}
                            />
                          </div>
                          <span className="text-right text-xs tabular-nums text-slate-400">
                            {colScore}%
                          </span>
                        </div>
                      )}

                      {(selectedView === "both" || selectedView === "mexico") && (
                        <div className="grid grid-cols-[1.25rem_minmax(0,1fr)_2.5rem] items-center gap-2">
                          <span className="text-xs">🇲🇽</span>
                          <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.07]">
                            <div
                              className="h-full rounded-full bg-gradient-to-r from-emerald-700 to-emerald-400 transition-[width] duration-500"
                              style={{ width: `${mexScore}%` }}
                            />
                          </div>
                          <span className="text-right text-xs tabular-nums text-slate-400">
                            {mexScore}%
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </section>
      </div>

      {/* Analytical Conclusions */}
      <section className="rounded-2xl border border-white/[0.08] bg-[#10131d]/85 p-5 shadow-xl shadow-black/30 backdrop-blur-md sm:p-6">
        <div className="mb-10 flex items-center gap-2.5">
          <SparklesIcon size={18} color="#f59e0b" />
          <h3 className="font-['Outfit'] text-base font-semibold tracking-tight text-white">
            Hallazgos Principales de la Investigación
          </h3>
        </div>

        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-[1.75rem_minmax(0,1fr)] items-start gap-3 text-xs leading-relaxed text-slate-300 [&_strong]:text-slate-100">
            <span className="grid size-7 place-items-center rounded-lg border border-orange-500/20 bg-orange-500/10 text-xs font-semibold text-orange-300">
              1
            </span>
            <div>
              <strong>Sesgo de Criminalización en Colombia:</strong> El 64.2% de los
              artículos analizados en medios colombianos (con Revista Semana a la cabeza
              con 74%) contienen menciones directas a operativos policiales, capturas o
              alertas ciudadanas, configurando un marco discursivo donde el migrante es
              primariamente asociado con inseguridad.
            </div>
          </div>

          <div className="grid grid-cols-[1.75rem_minmax(0,1fr)] items-start gap-3 text-xs leading-relaxed text-slate-300 [&_strong]:text-slate-100">
            <span className="grid size-7 place-items-center rounded-lg border border-orange-500/20 bg-orange-500/10 text-xs font-semibold text-orange-300">
              2
            </span>
            <div>
              <strong>Sesgo de Instrumentalización Productiva en México:</strong> Los
              medios mexicanos destacan en un 58.7% el papel de la mano de obra migrante
              en cadenas industriales y pymes, mientras que el 54.3% los sitúa como
              sujetos en tránsito hacia Estados Unidos esperando resoluciones consulares
              en Chiapas y Baja California.
            </div>
          </div>

          <div className="grid grid-cols-[1.75rem_minmax(0,1fr)] items-start gap-3 text-xs leading-relaxed text-slate-300 [&_strong]:text-slate-100">
            <span className="grid size-7 place-items-center rounded-lg border border-orange-500/20 bg-orange-500/10 text-xs font-semibold text-orange-300">
              3
            </span>
            <div>
              <strong>Necesidad de Modelos NLP en Español:</strong> La investigación
              demostró que los benchmarks anglosajones tradicionales incurren en errores
              de falso positivo al etiquetar términos coloquiales y geográficos propios de
              la región andina y norteña, validando la necesidad del fine-tuning de BETO
              con datos locales (RF05).
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}
