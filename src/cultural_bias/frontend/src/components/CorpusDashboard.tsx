import React, { useEffect, useState } from "react"
import { describeApiError, getCorpusDashboard } from "../services/api"
import type {
  CorpusCountryStats,
  CorpusDashboardData,
  PercentageCounts,
} from "../types"
import { ShieldAlertIcon, BriefcaseIcon, SparklesIcon, CompassIcon } from "./Icons"
import { RadarChart } from "./RadarChart"
import type { RadarSeries } from "./RadarChart"

const normalizeText = (value: string): string =>
  value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()

const findCountry = (
  countries: CorpusCountryStats[],
  name: "colombia" | "mexico",
): CorpusCountryStats | undefined =>
  countries.find(country => normalizeText(country.country) === name)

type SentimentKey = keyof PercentageCounts

const SENTIMENT_LABELS: Record<SentimentKey, string> = {
  negativo: "Negativo",
  neutro: "Neutro",
  positivo: "Positivo",
}

const SENTIMENT_TEXT_CLASS: Record<SentimentKey, string> = {
  negativo: "text-red-300",
  neutro: "text-slate-300",
  positivo: "text-emerald-300",
}

interface DominantSentiment {
  key: SentimentKey
  label: string
  pct: number
}

const dominantSentiment = (breakdown: PercentageCounts): DominantSentiment => {
  const keys: SentimentKey[] = ["negativo", "neutro", "positivo"]
  const winner = keys.reduce(
    (best, key) => (breakdown[key] > breakdown[best] ? key : best),
    keys[0],
  )
  return { key: winner, label: SENTIMENT_LABELS[winner], pct: breakdown[winner] }
}

const dominantFrame = (country: CorpusCountryStats | undefined) => {
  if (!country || country.frameBreakdown.length === 0) return null
  return country.frameBreakdown.reduce((best, item) =>
    item.percentage > best.percentage ? item : best,
  )
}

const negativePositiveRatio = (breakdown: PercentageCounts): string => {
  if (breakdown.positivo <= 0) return "—"
  return (breakdown.negativo / breakdown.positivo).toFixed(1)
}

const formatDateRange = (range: Record<string, string>): string => {
  const from = range.from
  const to = range.to
  if (!from && !to) return "fechas no disponibles"
  return `${from || "?"} → ${to || "?"}`
}

export const CorpusDashboard: React.FC = () => {
  const [selectedView, setSelectedView] = useState<"both" | "colombia" | "mexico">("both")
  const [chartType, setChartType] = useState<"bars" | "radar">("radar")
  const [data, setData] = useState<CorpusDashboardData | null>(null)
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState<number>(0)

  useEffect(() => {
    let alive = true
    setIsLoading(true)
    setErrorMessage(null)
    getCorpusDashboard()
      .then(corpus => {
        if (alive) setData(corpus)
      })
      .catch((error: unknown) => {
        if (alive) {
          setData(null)
          setErrorMessage(describeApiError(error))
        }
      })
      .finally(() => {
        if (alive) setIsLoading(false)
      })
    return () => {
      alive = false
    }
  }, [reloadKey])

  if (isLoading) {
    return (
      <div className="flex min-w-0 flex-col gap-6 pb-6">
        <section className="flex min-h-[280px] flex-col items-center justify-center gap-3 rounded-2xl border border-white/[0.08] bg-[#10131d]/85 p-6 shadow-xl shadow-black/30 backdrop-blur-md">
          <div className="size-10 animate-spin rounded-full border-2 border-orange-400/30 border-t-orange-400" />
          <p className="text-sm font-semibold text-white">
            Cargando estadísticas del corpus real…
          </p>
          <p className="text-xs text-slate-400">
            GET /v1/dashboard/corpus · CSV etiquetado del proyecto
          </p>
        </section>
      </div>
    )
  }

  if (errorMessage || !data) {
    return (
      <div className="flex min-w-0 flex-col gap-6 pb-6">
        <section
          role="alert"
          className="rounded-2xl border border-red-500/30 bg-red-500/[0.07] p-6 shadow-xl shadow-black/30"
        >
          <h3 className="mb-2 font-['Outfit'] text-base font-semibold tracking-tight text-red-200">
            No se pudieron cargar las estadísticas del corpus
          </h3>
          <p className="break-words text-sm leading-relaxed text-red-200/90">
            {errorMessage ?? "El API no devolvió datos del corpus."}
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
            onClick={() => setReloadKey(key => key + 1)}
          >
            Reintentar
          </button>
        </section>
      </div>
    )
  }

  const colombia = findCountry(data.countries, "colombia")
  const mexico = findCountry(data.countries, "mexico")
  const frames = data.frameBreakdown.map(item => item.frame)
  const topFrame = data.frameBreakdown[0] ?? null
  const overallSentiment = dominantSentiment(data.sentimentBreakdown)
  const colombiaDominantFrame = dominantFrame(colombia)
  const mexicoDominantFrame = dominantFrame(mexico)
  const colombiaSentiment = colombia ? dominantSentiment(colombia.sentimentBreakdown) : null
  const mexicoSentiment = mexico ? dominantSentiment(mexico.sentimentBreakdown) : null
  const mediaNames = Array.from(
    new Set(data.countries.flatMap(country => country.media)),
  ).filter(Boolean)

  // Prepare series for Radar Chart
  const radarSeries: RadarSeries[] = []
  if (colombia && (selectedView === "both" || selectedView === "colombia")) {
    radarSeries.push({
      name: "🇨🇴",
      color: "#ef4444",
      fillColor: "rgba(239, 68, 68, 0.25)",
      values: frames.map(
        frame =>
          colombia.frameBreakdown.find(item => item.frame === frame)?.percentage ?? 0,
      ),
    })
  }
  if (mexico && (selectedView === "both" || selectedView === "mexico")) {
    radarSeries.push({
      name: "🇲🇽",
      color: "#10b981",
      fillColor: "rgba(16, 185, 129, 0.25)",
      values: frames.map(
        frame =>
          mexico.frameBreakdown.find(item => item.frame === frame)?.percentage ?? 0,
      ),
    })
  }

  const maxMonthlyTotal = Math.max(
    1,
    ...data.monthlyVolume.map(point => point.total),
  )

  const renderSentimentBar = (
    country: CorpusCountryStats,
    label: string,
  ) => {
    const breakdown = country.sentimentBreakdown
    const dominant = dominantSentiment(breakdown)
    return (
      <div className="flex flex-col gap-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm font-semibold text-slate-200">
            {label} ({country.totalArticles} noticias)
          </span>
          <span className={`text-xs font-medium ${SENTIMENT_TEXT_CLASS[dominant.key]}`}>
            Predominio {dominant.label} ({dominant.pct}%)
          </span>
        </div>
        <div className="flex min-h-8 w-full overflow-hidden rounded-lg border border-white/[0.06] bg-white/[0.04]">
          <div
            className="flex min-w-0 items-center justify-center overflow-hidden bg-gradient-to-r from-red-700 to-red-500 px-1 text-[10px] font-semibold text-white sm:text-xs"
            style={{ width: `${breakdown.negativo}%` }}
            title={`Negativo: ${breakdown.negativo}%`}
          >
            {breakdown.negativo}% Neg
          </div>
          <div
            className="flex min-w-0 items-center justify-center overflow-hidden bg-gradient-to-r from-slate-600 to-slate-500 px-1 text-[10px] font-semibold text-white sm:text-xs"
            style={{ width: `${breakdown.neutro}%` }}
            title={`Neutro: ${breakdown.neutro}%`}
          >
            {breakdown.neutro}% Neu
          </div>
          <div
            className="flex min-w-0 items-center justify-center overflow-hidden bg-gradient-to-r from-emerald-700 to-emerald-500 px-1 text-[10px] font-semibold text-white sm:text-xs"
            style={{ width: `${breakdown.positivo}%` }}
            title={`Positivo: ${breakdown.positivo}%`}
          >
            {breakdown.positivo}% Pos
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-w-0 flex-col gap-6 pb-6">
      {/* Hypothesis Statement Card */}
      <section className="rounded-2xl border border-purple-500/15 bg-gradient-to-br from-[#171522]/95 via-[#10131d]/95 to-[#0c0f18]/95 p-5 shadow-xl shadow-black/30 sm:p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2.5">
            <CompassIcon size={22} color="#a855f7" />
            <h2 className="font-['Outfit'] text-base font-semibold tracking-tight text-white">
              Hipótesis Central del Estudio
            </h2>
          </div>
          <span className="rounded-full border border-white/[0.08] bg-white/[0.04] px-2.5 py-1 text-xs text-slate-300">
            {data.totalArticles} artículos · {data.mediaCount} medios
          </span>
        </div>

        <p className="mb-4 rounded-xl border border-white/[0.06] bg-white/[0.02] px-3.5 py-2.5 text-[11.5px] leading-relaxed text-slate-400">
          Datos del corpus etiquetado real (<span className="font-mono">GET /v1/dashboard/corpus</span>
          ): {formatDateRange(data.dateRange)} · medios:{" "}
          {mediaNames.length > 0 ? mediaNames.join(", ") : "sin medios registrados"}.
          Los porcentajes comparan la presencia de cada encuadre/sentimiento dentro del
          corpus, no son una estimación poblacional.
        </p>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* Colombia Card */}
          <div className="flex min-w-0 flex-col gap-3 rounded-xl border border-red-500/15 bg-red-500/[0.035] p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-semibold text-slate-100">
                Colombia (Primer Receptor Fronterizo)
              </span>
              <span className="rounded-full border border-white/[0.08] bg-white/[0.04] px-2.5 py-1 text-xs text-slate-300">
                {colombia ? `${colombia.totalArticles} Noticias` : "Sin datos"}
              </span>
            </div>
            {colombia && colombiaDominantFrame ? (
              <>
                <p className="text-sm leading-relaxed text-slate-300">
                  <strong>Tendencia observada:</strong> el encuadre con mayor presencia es{" "}
                  <strong className="text-white">{colombiaDominantFrame.frame}</strong> (
                  {colombiaDominantFrame.percentage}%). El sentimiento negativo representa{" "}
                  {colombia.sentimentBreakdown.negativo}% y el positivo{" "}
                  {colombia.sentimentBreakdown.positivo}%.
                </p>
                <div className="inline-flex self-start items-center gap-2 rounded-lg border border-red-500/15 bg-red-500/[0.06] px-3 py-2 text-xs text-slate-200">
                  {normalizeText(colombiaDominantFrame.frame).includes("seguridad") ? (
                    <ShieldAlertIcon size={14} color="#ef4444" />
                  ) : (
                    <BriefcaseIcon size={14} color="#ef4444" />
                  )}
                  <span>
                    Encuadre dominante:{" "}
                    <strong className="text-white">
                      {colombiaDominantFrame.frame} ({colombiaDominantFrame.percentage}%)
                    </strong>
                  </span>
                </div>
              </>
            ) : (
              <p className="text-sm leading-relaxed text-slate-400">
                El corpus no contiene filas etiquetadas para Colombia.
              </p>
            )}
          </div>

          {/* Mexico Card */}
          <div className="flex min-w-0 flex-col gap-3 rounded-xl border border-emerald-500/15 bg-emerald-500/[0.035] p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-semibold text-slate-100">
                México (Destino de Tránsito y Asentamiento Secundario)
              </span>
              <span className="rounded-full border border-white/[0.08] bg-white/[0.04] px-2.5 py-1 text-xs text-slate-300">
                {mexico ? `${mexico.totalArticles} Noticias` : "Sin datos"}
              </span>
            </div>
            {mexico && mexicoDominantFrame ? (
              <>
                <p className="text-sm leading-relaxed text-slate-300">
                  <strong>Tendencia observada:</strong> el encuadre con mayor presencia es{" "}
                  <strong className="text-white">{mexicoDominantFrame.frame}</strong> (
                  {mexicoDominantFrame.percentage}%). El sentimiento negativo representa{" "}
                  {mexico.sentimentBreakdown.negativo}% y el positivo{" "}
                  {mexico.sentimentBreakdown.positivo}%.
                </p>
                <div className="inline-flex self-start items-center gap-2 rounded-lg border border-emerald-500/15 bg-emerald-500/[0.06] px-3 py-2 text-xs text-slate-200">
                  {normalizeText(mexicoDominantFrame.frame).includes("empleo") ? (
                    <BriefcaseIcon size={14} color="#10b981" />
                  ) : (
                    <ShieldAlertIcon size={14} color="#10b981" />
                  )}
                  <span>
                    Encuadre dominante:{" "}
                    <strong className="text-white">
                      {mexicoDominantFrame.frame} ({mexicoDominantFrame.percentage}%)
                    </strong>
                  </span>
                </div>
              </>
            ) : (
              <p className="text-sm leading-relaxed text-slate-400">
                El corpus no contiene filas etiquetadas para México.
              </p>
            )}
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
            <span className="text-xs text-slate-500">Corpus etiquetado del CSV</span>
          </div>

          <div className="flex flex-col gap-5">
            {(selectedView === "both" || selectedView === "colombia") &&
              (colombia ? (
                renderSentimentBar(colombia, "Medios Colombianos")
              ) : (
                <p className="text-xs text-slate-500">
                  Sin datos de Colombia en el corpus.
                </p>
              ))}

            {(selectedView === "both" || selectedView === "mexico") &&
              (mexico ? (
                renderSentimentBar(mexico, "Medios Mexicanos")
              ) : (
                <p className="text-xs text-slate-500">Sin datos de México en el corpus.</p>
              ))}
          </div>

          <p className="mt-5 border-t border-white/[0.07] pt-4 text-xs leading-relaxed text-slate-400">
            En todo el corpus el sentimiento dominante es{" "}
            <strong className="text-slate-100">
              {overallSentiment.label} ({overallSentiment.pct}%)
            </strong>
            {colombia && mexico && colombiaSentiment && mexicoSentiment ? (
              <>
                . Colombia tiende a <strong className="text-slate-100">{colombiaSentiment.label}</strong>{" "}
                ({colombiaSentiment.pct}%) con una razón negativo/positivo de{" "}
                <strong className="text-slate-100">
                  {negativePositiveRatio(colombia.sentimentBreakdown)}
                </strong>
                ; México tiende a{" "}
                <strong className="text-slate-100">{mexicoSentiment.label}</strong> (
                {mexicoSentiment.pct}%) con una razón de{" "}
                <strong className="text-slate-100">
                  {negativePositiveRatio(mexico.sentimentBreakdown)}
                </strong>
                .
              </>
            ) : (
              "."
            )}
          </p>
        </section>

        {/* Framing Contrast Radar/Bars */}
        <section className="flex min-w-0 flex-col rounded-2xl border border-white/[0.08] bg-[#10131d]/85 p-5 shadow-xl shadow-black/30 backdrop-blur-md sm:p-6">
          <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="font-['Outfit'] text-base font-semibold tracking-tight text-white">
                Contraste de los {frames.length} Encuadres Mediáticos
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

          {frames.length === 0 ? (
            <p className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 text-xs text-slate-500">
              El corpus no reporta encuadres.
            </p>
          ) : chartType === "radar" ? (
            <div className="flex min-w-0 flex-col items-center">
              {radarSeries.length > 0 ? (
                <RadarChart axes={frames} series={radarSeries} size={320} />
              ) : (
                <p className="py-8 text-xs text-slate-500">
                  Sin país seleccionado con datos en el corpus.
                </p>
              )}
              <p className="mt-4 border-t border-white/[0.07] pt-4 text-xs leading-relaxed text-slate-400">
                {colombiaDominantFrame && mexicoDominantFrame ? (
                  <>
                    Colombia muestra su mayor presencia en{" "}
                    <strong className="font-semibold text-red-300">
                      {colombiaDominantFrame.frame} ({colombiaDominantFrame.percentage}%)
                    </strong>
                    , mientras que México la muestra en{" "}
                    <strong className="font-semibold text-emerald-300">
                      {mexicoDominantFrame.frame} ({mexicoDominantFrame.percentage}%)
                    </strong>
                    . Los ejes son porcentajes de artículos con el encuadre marcado.
                  </>
                ) : (
                  "Selecciona ambos países para comparar sus encuadres."
                )}
              </p>
            </div>
          ) : (
            <div className="flex animate-[enterFadeIn_350ms_ease-out] flex-col gap-4">
              {frames.map(frameName => {
                const colScore =
                  colombia?.frameBreakdown.find(item => item.frame === frameName)
                    ?.percentage ?? 0
                const mexScore =
                  mexico?.frameBreakdown.find(item => item.frame === frameName)
                    ?.percentage ?? 0
                const diff = Math.round((colScore - mexScore) * 10) / 10

                return (
                  <div key={frameName} className="flex flex-col gap-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-medium text-slate-200">
                        {frameName}
                      </span>
                      <span className="rounded-full border border-white/[0.08] bg-white/[0.04] px-2 py-0.5 text-[10px] text-slate-400">
                        {diff >= 0 ? `🇨🇴 +${diff}%` : `🇲🇽 +${Math.abs(diff)}%`}
                      </span>
                    </div>

                    {/* Dual Bar */}
                    <div className="flex flex-col gap-1.5">
                      {colombia && (selectedView === "both" || selectedView === "colombia") && (
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

                      {mexico && (selectedView === "both" || selectedView === "mexico") && (
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

      {/* Monthly volume from the real corpus */}
      <section className="rounded-2xl border border-white/[0.08] bg-[#10131d]/85 p-5 shadow-xl shadow-black/30 backdrop-blur-md sm:p-6">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 className="font-['Outfit'] text-base font-semibold tracking-tight text-white">
              Volumen Mensual del Corpus
            </h3>
            <span className="text-xs text-slate-500">
              Artículos etiquetados por mes · {formatDateRange(data.dateRange)}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-[10.5px] text-slate-400">
            <span className="inline-flex items-center gap-1.5">
              <span className="size-2 rounded-full bg-red-500/80" /> Negativo
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="size-2 rounded-full bg-slate-500/80" /> Neutro
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="size-2 rounded-full bg-emerald-500/80" /> Positivo
            </span>
          </div>
        </div>

        {data.monthlyVolume.length === 0 ? (
          <p className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 text-xs text-slate-500">
            El corpus no reporta volumen mensual.
          </p>
        ) : (
          <>
            <div className="flex h-[180px] items-end gap-[3px] overflow-x-auto pb-1">
              {data.monthlyVolume.map(point => {
                const totalHeight = Math.max(
                  point.total > 0 ? 6 : 2,
                  Math.round((point.total / maxMonthlyTotal) * 150),
                )
                const share = point.total > 0 ? 100 / point.total : 0
                return (
                  <div
                    key={point.month}
                    className="group flex min-w-[10px] flex-1 flex-col items-center justify-end gap-1"
                    title={`${point.month}: ${point.total} artículos (neg: ${point.negativo}, neu: ${point.neutro}, pos: ${point.positivo})`}
                  >
                    <div
                      className="flex w-full flex-col justify-end overflow-hidden rounded-sm bg-white/[0.04] transition-opacity group-hover:opacity-90"
                      style={{ height: `${totalHeight}px` }}
                    >
                      {point.negativo > 0 && (
                        <div
                          className="w-full bg-red-500/80"
                          style={{ height: `${point.negativo * share}%` }}
                        />
                      )}
                      {point.neutro > 0 && (
                        <div
                          className="w-full bg-slate-500/80"
                          style={{ height: `${point.neutro * share}%` }}
                        />
                      )}
                      {point.positivo > 0 && (
                        <div
                          className="w-full bg-emerald-500/80"
                          style={{ height: `${point.positivo * share}%` }}
                        />
                      )}
                    </div>
                    <span className="h-3 whitespace-nowrap text-[8.5px] tabular-nums text-slate-500">
                      {point.month.slice(2)}
                    </span>
                  </div>
                )
              })}
            </div>
            <p className="mt-3 border-t border-white/[0.07] pt-3 text-[11px] leading-relaxed text-slate-500">
              Cada barra apilada representa un mes del CSV etiquetado; la altura total es
              el número de artículos y los segmentos, su sentimiento. Pasa el cursor por
              una barra para ver los conteos exactos.
            </p>
          </>
        )}
      </section>

      {/* Analytical Conclusions (derived from the API data) */}
      <section className="rounded-2xl border border-white/[0.08] bg-[#10131d]/85 p-5 shadow-xl shadow-black/30 backdrop-blur-md sm:p-6">
        <div className="mb-6 flex items-center gap-2.5">
          <SparklesIcon size={18} color="#f59e0b" />
          <h3 className="font-['Outfit'] text-base font-semibold tracking-tight text-white">
            Hallazgos Principales del Corpus Real
          </h3>
        </div>

        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-[1.75rem_minmax(0,1fr)] items-start gap-3 text-xs leading-relaxed text-slate-300 [&_strong]:text-slate-100">
            <span className="grid size-7 place-items-center rounded-lg border border-orange-500/20 bg-orange-500/10 text-xs font-semibold text-orange-300">
              1
            </span>
            <div>
              <strong>Encuadre dominante del corpus:</strong>{" "}
              {topFrame ? (
                <>
                  <strong>{topFrame.frame}</strong> aparece en el{" "}
                  <strong>{topFrame.percentage}%</strong> de los {data.totalArticles}{" "}
                  artículos etiquetados, seguido por{" "}
                  {data.frameBreakdown
                    .slice(1, 3)
                    .map(item => `${item.frame} (${item.percentage}%)`)
                    .join(" y ")}
                  .
                </>
              ) : (
                "el API no reporta encuadres para el corpus."
              )}
            </div>
          </div>

          <div className="grid grid-cols-[1.75rem_minmax(0,1fr)] items-start gap-3 text-xs leading-relaxed text-slate-300 [&_strong]:text-slate-100">
            <span className="grid size-7 place-items-center rounded-lg border border-orange-500/20 bg-orange-500/10 text-xs font-semibold text-orange-300">
              2
            </span>
            <div>
              <strong>Contraste Colombia vs. México:</strong>{" "}
              {colombiaDominantFrame && mexicoDominantFrame ? (
                <>
                  en Colombia predomina{" "}
                  <strong>{colombiaDominantFrame.frame}</strong> (
                  {colombiaDominantFrame.percentage}%) y en México{" "}
                  <strong>{mexicoDominantFrame.frame}</strong> (
                  {mexicoDominantFrame.percentage}%). Los encuadres se miden como
                  porcentaje de artículos del país donde la etiqueta está activa.
                </>
              ) : (
                "el corpus actual no contiene ambos países, así que no se puede contrastar."
              )}
            </div>
          </div>

          <div className="grid grid-cols-[1.75rem_minmax(0,1fr)] items-start gap-3 text-xs leading-relaxed text-slate-300 [&_strong]:text-slate-100">
            <span className="grid size-7 place-items-center rounded-lg border border-orange-500/20 bg-orange-500/10 text-xs font-semibold text-orange-300">
              3
            </span>
            <div>
              <strong>Sentimiento del corpus:</strong>{" "}
              {data.sentimentBreakdown.negativo}% negativo,{" "}
              {data.sentimentBreakdown.neutro}% neutro y{" "}
              {data.sentimentBreakdown.positivo}% positivo. El corpus cubre{" "}
              {data.mediaCount} medio(s) (
              {mediaNames.length > 0 ? mediaNames.join(", ") : "sin medios"}) entre{" "}
              {formatDateRange(data.dateRange)}.
            </div>
          </div>
        </div>

        <p className="mt-5 border-t border-white/[0.07] pt-4 text-[11px] leading-relaxed text-slate-500">
          <strong className="text-slate-400">Alcance y limitaciones:</strong> el CSV
          etiquetado actual contiene {data.totalArticles} artículos de {data.mediaCount}{" "}
          medio(s), por lo que las comparaciones describen este corpus concreto y no una
          muestra probabilística de la cobertura nacional. Las etiquetas provienen del
          dataset del proyecto, no de los análisis en vivo de las otras pestañas.
        </p>
      </section>
    </div>
  )
}
