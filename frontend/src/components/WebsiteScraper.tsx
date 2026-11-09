import React, { useEffect, useRef, useState } from "react"
import { SAMPLE_NEWS_SITES } from "../data/sampleNewsWebsites"
import {
  scrapeNewsSite,
  exportCorpusToCSV,
  exportCorpusToJSON,
} from "../services/newsScraperService"
import { describeApiError, getSourcePresets, isAbortError } from "../services/api"
import type {
  NewsArticle,
  ScrapedSiteSummary,
  ScrapingProgress,
  SourcePreset,
} from "../types"
import { FramesBarChart } from "./FramesBarChart"
import { SentimentGauge } from "./SentimentGauge"
import { CulturalBiasCard } from "./CulturalBiasCard"
import {
  GlobeIcon,
  SearchIcon,
  RefreshCwIcon,
  DownloadIcon,
  ExternalLinkIcon,
  FileTextIcon,
  SparklesIcon,
} from "./Icons"

interface WebsiteScraperProps {
  onSendToAnalyzer?: (text: string) => void
}

/**
 * Presets locales de respaldo (solo presentación: nombre/dominio/bandera).
 * Los artículos ya no se usan: el contenido real sale del job de rastreo.
 * Se reemplazan por `GET /v1/sources/presets` cuando el API responde.
 */
const FALLBACK_PRESETS: SourcePreset[] = SAMPLE_NEWS_SITES.map(site => ({
  id: site.id,
  name: site.name,
  domain: site.domain,
  country: site.country,
  category: site.category,
  description: site.description,
  flag: site.flag,
  logoText: site.logoText,
  accentColor: site.accentColor,
}))

const STATUS_LABELS: Record<ScrapingProgress["status"], string> = {
  idle: "En espera",
  queued: "En cola",
  connecting: "Conectando",
  crawling: "Rastreando noticias",
  cleaning: "Limpiando contenido",
  analyzing: "Analizando con BETO",
  completed: "Completado",
  error: "Error",
}

const TOTAL_STEPS = 5

export const WebsiteScraper: React.FC<WebsiteScraperProps> = ({ onSendToAnalyzer }) => {
  const [urlInput, setUrlInput] = useState<string>("eltiempo.com")
  const [maxArticles, setMaxArticles] = useState<number>(3)
  const [isScraping, setIsScraping] = useState<boolean>(false)
  const [progress, setProgress] = useState<ScrapingProgress | null>(null)
  const [scrapedData, setScrapedData] = useState<ScrapedSiteSummary | null>(null)
  const [selectedArticle, setSelectedArticle] = useState<NewsArticle | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [presets, setPresets] = useState<SourcePreset[]>(FALLBACK_PRESETS)
  const [presetsFromApi, setPresetsFromApi] = useState<boolean>(false)
  const abortRef = useRef<AbortController | null>(null)

  // Carga los medios indexados reales del API; si falla, usa la lista local.
  useEffect(() => {
    let alive = true
    getSourcePresets()
      .then(data => {
        if (!alive) return
        if (Array.isArray(data) && data.length > 0) {
          setPresets(data)
          setPresetsFromApi(true)
        }
      })
      .catch(() => {
        /* el API puede no estar disponible aún; se conserva la lista local */
      })
    return () => {
      alive = false
    }
  }, [])

  // Cancela el polling si el componente se desmonta.
  useEffect(() => () => abortRef.current?.abort(), [])

  const handleStartScrape = async (overrideUrl?: string) => {
    const targetUrl = (overrideUrl || urlInput).trim()
    if (!targetUrl || isScraping) return

    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setIsScraping(true)
    setSelectedArticle(null)
    setScrapedData(null)
    setErrorMessage(null)
    setProgress({
      status: "queued",
      currentStep: 0,
      totalSteps: TOTAL_STEPS,
      message: `Solicitando rastreo de ${targetUrl.replace(/^https?:\/\//, "")} al API…`,
      articlesFoundCount: 0,
    })

    try {
      const summary = await scrapeNewsSite({
        url: targetUrl,
        maxArticles,
        onProgress: p => setProgress(p),
        signal: controller.signal,
      })
      setScrapedData(summary)
      if (summary.articles.length > 0) {
        setSelectedArticle(summary.articles[0])
      }
    } catch (error) {
      if (isAbortError(error)) return
      setErrorMessage(describeApiError(error))
    } finally {
      if (abortRef.current === controller) abortRef.current = null
      setIsScraping(false)
    }
  }

  const handleSelectPreset = (siteUrl: string) => {
    setUrlInput(siteUrl)
    void handleStartScrape(siteUrl)
  }

  const handleDownloadCSV = () => {
    if (!scrapedData) return
    const csv = exportCorpusToCSV(scrapedData.articles)
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" })
    const url = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = `corpus_${scrapedData.siteName.toLowerCase()}_${Date.now()}.csv`
    link.click()
    URL.revokeObjectURL(url)
  }

  const handleDownloadJSON = () => {
    if (!scrapedData) return
    const jsonStr = exportCorpusToJSON(scrapedData)
    const blob = new Blob([jsonStr], { type: "application/json;charset=utf-8;" })
    const url = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = `corpus_${scrapedData.siteName.toLowerCase()}_${Date.now()}.json`
    link.click()
    URL.revokeObjectURL(url)
  }

  const colombiaPresets = presets.filter(
    preset => preset.country === "Colombia",
  )
  const mexicoPresets = presets.filter(
    preset => preset.country === "México" || preset.country === "Mexico",
  )
  const otherPresets = presets.filter(
    preset =>
      preset.country !== "Colombia" &&
      preset.country !== "México" &&
      preset.country !== "Mexico",
  )
  const generatedAtLabel = scrapedData?.generatedAt
    ? new Intl.DateTimeFormat("es-CO", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(scrapedData.generatedAt))
    : null

  return (
    <div className="max-w-4xl mx-auto w-full flex flex-col gap-7">
      {/* Search and configuration Card */}
      <div className="bg-[#10131d]/85 backdrop-blur-md border border-white/[0.08] rounded-3xl p-6 sm:p-7 shadow-2xl shadow-black/50 transition-all hover:border-white/[0.14]">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <div className="flex items-center gap-2.5">
            <GlobeIcon size={20} color="#3b82f6" />
            <h2 className="font-['Outfit'] text-[17px] font-semibold text-white tracking-tight">
              Portal de Noticias a Analizar
            </h2>
          </div>
          <span className="text-[11px] text-slate-500">
            Rastreo y análisis reales vía API
          </span>
        </div>

        {/* Input box */}
        <div className="flex flex-col md:flex-row gap-3.5 mb-5">
          <div className="flex-1 flex items-center bg-[#0c0e15] border border-white/[0.08] focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-500/20 rounded-xl px-4 h-12 transition-all">
            <span className="text-slate-500 text-sm font-mono select-none">https://</span>
            <input
              type="text"
              className="flex-1 bg-transparent border-none text-white pl-1.5 text-[14.5px] outline-none"
              value={urlInput}
              onChange={e => setUrlInput(e.target.value)}
              placeholder="eltiempo.com, semana.com, eluniversal.com.mx..."
              disabled={isScraping}
              onKeyDown={e => {
                if (e.key === "Enter") void handleStartScrape()
              }}
            />
          </div>

          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <label
                htmlFor="max-articles-select"
                className="text-xs text-slate-400 whitespace-nowrap"
              >
                Artículos:
              </label>
              <select
                id="max-articles-select"
                aria-label="Artículos a procesar"
                className="bg-[#141824] text-slate-200 border border-white/[0.08] rounded-xl py-2.5 px-3.5 text-xs outline-none"
                value={maxArticles}
                onChange={e => setMaxArticles(Number(e.target.value))}
                disabled={isScraping}
              >
                <option value={2}>2 (Rápido)</option>
                <option value={3}>3 (Recomendado)</option>
                <option value={5}>5 (Profundo)</option>
              </select>
            </div>

            <button
              type="button"
              className="bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-400 hover:to-orange-500 text-white font-bold py-3 px-5 rounded-xl text-sm inline-flex items-center justify-center gap-2 shadow-lg shadow-orange-500/35 hover:shadow-orange-500/50 transition-all whitespace-nowrap disabled:opacity-45 disabled:cursor-not-allowed"
              onClick={() => void handleStartScrape()}
              disabled={!urlInput.trim() || isScraping}
            >
              {isScraping ? (
                <>
                  <RefreshCwIcon size={16} className="animate-spin" />
                  <span>Analizando...</span>
                </>
              ) : (
                <>
                  <SearchIcon size={16} />
                  <span>Descargar y Analizar</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Error de rastreo / conexión con el API */}
        {errorMessage && (
          <div
            role="alert"
            className="mb-5 rounded-xl border border-red-500/35 bg-red-500/10 px-4 py-3 text-[13px] leading-relaxed text-red-200"
          >
            <p className="font-semibold">No se pudo completar el rastreo</p>
            <p className="break-words text-red-200/90">{errorMessage}</p>
            <button
              type="button"
              className="mt-2 text-[11.5px] font-semibold text-red-200 underline decoration-red-400/50 hover:text-white"
              onClick={() => void handleStartScrape()}
            >
              Reintentar con la misma URL
            </button>
          </div>
        )}

        {/* Preset Outlets Quick Selector */}
        <div className="border-t border-white/[0.07] pt-4 flex flex-col gap-3.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              O selecciona un medio indexado:
            </span>
            <span className="text-[11px] text-slate-500">
              {presetsFromApi
                ? "Medios del API (solo rellenan la URL; el contenido se rastrea en vivo)"
                : "Lista local de respaldo (el contenido se rastrea en vivo)"}
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="flex flex-col gap-2">
              <span className="text-xs font-semibold text-slate-300">
                Medios de Colombia:
              </span>
              <div className="flex flex-wrap gap-2">
                {colombiaPresets.map(site => (
                  <button
                    key={site.id}
                    type="button"
                    className={`bg-white/[0.035] hover:bg-white/[0.07] border border-white/[0.07] hover:border-white/[0.16] rounded-lg px-3 py-1.5 inline-flex items-center gap-2 text-xs text-slate-200 transition-all ${
                      urlInput.includes(site.domain)
                        ? "bg-blue-500/20 border-blue-500/40 text-blue-300 font-semibold"
                        : ""
                    }`}
                    onClick={() => handleSelectPreset(site.domain)}
                    disabled={isScraping}
                    title={site.description}
                  >
                    <span>{site.flag}</span>
                    <span>{site.name}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <span className="text-xs font-semibold text-slate-300">
                Medios de México:
              </span>
              <div className="flex flex-wrap gap-2">
                {mexicoPresets.map(site => (
                  <button
                    key={site.id}
                    type="button"
                    className={`bg-white/[0.035] hover:bg-white/[0.07] border border-white/[0.07] hover:border-white/[0.16] rounded-lg px-3 py-1.5 inline-flex items-center gap-2 text-xs text-slate-200 transition-all ${
                      urlInput.includes(site.domain)
                        ? "bg-blue-500/20 border-blue-500/40 text-blue-300 font-semibold"
                        : ""
                    }`}
                    onClick={() => handleSelectPreset(site.domain)}
                    disabled={isScraping}
                    title={site.description}
                  >
                    <span>{site.flag}</span>
                    <span>{site.name}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
          {otherPresets.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {otherPresets.map(site => (
                <button
                  key={site.id}
                  type="button"
                  className="bg-white/[0.035] hover:bg-white/[0.07] border border-white/[0.07] hover:border-white/[0.16] rounded-lg px-3 py-1.5 inline-flex items-center gap-2 text-xs text-slate-200 transition-all"
                  onClick={() => handleSelectPreset(site.domain)}
                  disabled={isScraping}
                  title={site.description}
                >
                  <span>{site.flag}</span>
                  <span>{site.name}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Live Scraping Stepper & Progress */}
        {isScraping && progress && (
          <div className="mt-5 bg-[#0b0e17] border border-white/[0.07] rounded-xl p-4 animate-enter">
            <div className="flex items-center gap-2.5 mb-3 text-xs sm:text-[13.5px] flex-wrap">
              <RefreshCwIcon size={15} className="animate-spin" color="#3b82f6" />
              <span className="font-bold text-blue-400">
                {progress.currentStep > 0
                  ? `Paso ${progress.currentStep} de ${progress.totalSteps}:`
                  : "Preparando el rastreo:"}
              </span>
              <span className="text-slate-300 truncate">{progress.message}</span>
            </div>
            <div className="w-full h-1.5 bg-white/[0.08] rounded-full overflow-hidden mb-3">
              <div
                className="h-full bg-blue-500 rounded-full transition-all duration-300"
                style={{
                  width: `${
                    progress.totalSteps > 0
                      ? (progress.currentStep / progress.totalSteps) * 100
                      : 0
                  }%`,
                }}
              />
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <span
                className={`text-[11px] px-2.5 py-0.5 rounded border ${
                  progress.currentStep >= 1
                    ? "bg-blue-500/15 text-blue-300 border-blue-500/35"
                    : "bg-white/[0.04] text-slate-500 border-white/[0.06]"
                }`}
              >
                1. Conexión
              </span>
              <span
                className={`text-[11px] px-2.5 py-0.5 rounded border ${
                  progress.currentStep >= 2
                    ? "bg-blue-500/15 text-blue-300 border-blue-500/35"
                    : "bg-white/[0.04] text-slate-500 border-white/[0.06]"
                }`}
              >
                2. Rastreo RSS
              </span>
              <span
                className={`text-[11px] px-2.5 py-0.5 rounded border ${
                  progress.currentStep >= 3
                    ? "bg-blue-500/15 text-blue-300 border-blue-500/35"
                    : "bg-white/[0.04] text-slate-500 border-white/[0.06]"
                }`}
              >
                3. Limpieza
              </span>
              <span
                className={`text-[11px] px-2.5 py-0.5 rounded border ${
                  progress.currentStep >= 4
                    ? "bg-blue-500/15 text-blue-300 border-blue-500/35"
                    : "bg-white/[0.04] text-slate-500 border-white/[0.06]"
                }`}
              >
                4. Inferencia BETO
              </span>
              <span
                className={`text-[11px] px-2.5 py-0.5 rounded border ${
                  progress.currentStep >= 5
                    ? "bg-blue-500/15 text-blue-300 border-blue-500/35"
                    : "bg-white/[0.04] text-slate-500 border-white/[0.06]"
                }`}
              >
                5. Métricas
              </span>
              <span className="ml-auto text-[11px] text-slate-500">
                Estado: {STATUS_LABELS[progress.status] ?? progress.status} ·{" "}
                {progress.articlesFoundCount} encontradas
                {typeof progress.articlesAnalyzedCount === "number"
                  ? ` · ${progress.articlesAnalyzedCount} analizadas`
                  : ""}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Results View */}
      {scrapedData && !isScraping && (
        <div className="flex flex-col gap-6 animate-enter">
          {/* Summary Banner */}
          <div className="bg-[#10131d]/85 backdrop-blur-md border border-white/[0.08] rounded-3xl p-6 sm:p-7 shadow-2xl">
            <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
              <div className="flex items-center gap-3 flex-wrap">
                <span className="bg-white/[0.06] text-slate-200 text-xs font-semibold px-2.5 py-1 rounded-md">
                  {scrapedData.country === "Colombia"
                    ? "🇨🇴 Colombia"
                    : scrapedData.country === "México" || scrapedData.country === "Mexico"
                      ? "🇲🇽 México"
                      : "🌐 Internacional"}
                </span>
                <h2 className="font-['Outfit'] text-2xl font-bold text-white">
                  {scrapedData.siteName}
                </h2>
                <a
                  href={`https://${scrapedData.domain}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300"
                >
                  <span>{scrapedData.domain}</span>
                  <ExternalLinkIcon size={13} />
                </a>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="bg-white/[0.05] hover:bg-white/[0.09] text-slate-300 hover:text-white border border-white/[0.08] rounded-xl text-xs font-medium px-3.5 py-2 inline-flex items-center gap-1.5 transition-all"
                  onClick={handleDownloadCSV}
                  title="Descargar dataset en CSV"
                >
                  <DownloadIcon size={14} />
                  <span>CSV</span>
                </button>
                <button
                  type="button"
                  className="bg-white/[0.05] hover:bg-white/[0.09] text-slate-300 hover:text-white border border-white/[0.08] rounded-xl text-xs font-medium px-3.5 py-2 inline-flex items-center gap-1.5 transition-all"
                  onClick={handleDownloadJSON}
                  title="Descargar reporte en JSON"
                >
                  <DownloadIcon size={14} />
                  <span>JSON</span>
                </button>
              </div>
            </div>

            {generatedAtLabel && (
              <p className="mb-4 -mt-2 text-[11px] text-slate-500">
                Rastreo real generado el {generatedAtLabel}. Los artículos y métricas de
                esta vista provienen del job del API, no de datos de ejemplo.
              </p>
            )}

            {/* Metrics cards row */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5">
              <div className="bg-[#0c0f18]/80 border border-white/[0.06] rounded-xl p-3.5 flex flex-col gap-1">
                <span className="text-[10.5px] font-semibold uppercase text-slate-500 tracking-wider">
                  Noticias Analizadas
                </span>
                <span className="text-2xl font-extrabold text-white">
                  {scrapedData.totalAnalyzed}
                </span>
                <span className="text-[11px] text-slate-400">Extraídas y analizadas</span>
              </div>

              <div className="bg-[#0c0f18]/80 border border-white/[0.06] rounded-xl p-3.5 flex flex-col gap-1">
                <span className="text-[10.5px] font-semibold uppercase text-slate-500 tracking-wider">
                  Sentimiento Medio
                </span>
                <div className="flex items-center gap-2 text-xs font-bold mt-1">
                  <span className="text-red-400">
                    {scrapedData.averageSentiment.negativo}%
                  </span>
                  <span className="text-slate-400">•</span>
                  <span className="text-slate-400">
                    {scrapedData.averageSentiment.neutro}%
                  </span>
                  <span className="text-slate-400">•</span>
                  <span className="text-emerald-400">
                    {scrapedData.averageSentiment.positivo}%
                  </span>
                </div>
              </div>

              <div className="bg-[#0c0f18]/80 border border-white/[0.06] rounded-xl p-3.5 flex flex-col gap-1">
                <span className="text-[10.5px] font-semibold uppercase text-slate-500 tracking-wider">
                  Encuadre Dominante
                </span>
                <span className="text-[15px] font-bold text-purple-300 truncate">
                  {scrapedData.topFrames[0]?.frame || "General"}
                </span>
                <span className="text-[11px] text-slate-400">
                  {scrapedData.topFrames[0]?.percentage ?? 0}% de presencia
                </span>
              </div>

              <div className="bg-[#0c0f18]/80 border border-orange-500/20 rounded-xl p-3.5 flex flex-col gap-1">
                <span className="text-[10.5px] font-semibold uppercase text-slate-500 tracking-wider">
                  Hipótesis de Grado
                </span>
                <span className="text-xs font-bold text-orange-400 truncate">
                  {scrapedData.hypothesisMatch}
                </span>
                <span className="text-[11px] text-slate-400 truncate">
                  {scrapedData.biasTendency}
                </span>
              </div>
            </div>
          </div>

          {/* Dual Columns: Articles Feed + Selected Article Deep Dive */}
          <div className="grid grid-cols-1 md:grid-cols-[1fr_1.05fr] gap-6">
            {/* Left: Feed of Scraped Articles */}
            <div className="flex flex-col gap-3">
              <div className="mb-1">
                <h3 className="font-['Outfit'] text-[16px] font-semibold text-white">
                  Noticias Recopiladas ({scrapedData.articles.length})
                </h3>
                <span className="text-xs text-slate-500">
                  Haz clic para inspeccionar cada artículo. Verifica su pertinencia
                  temática: el crawler del API puede incluir noticias no relacionadas.
                </span>
              </div>

              <div className="flex flex-col gap-3">
                {scrapedData.articles.map(article => {
                  const isSelected = selectedArticle?.id === article.id
                  const sentiment = article.preAnalyzedResult?.sentiment
                  const topFrame = article.preAnalyzedResult?.frames[0]

                  return (
                    <div
                      key={article.id}
                      className={`bg-[#10131d]/85 backdrop-blur-md border rounded-2xl p-4 sm:p-5 transition-all cursor-pointer ${
                        isSelected
                          ? "border-blue-500/60 bg-[#141a29]/95 shadow-lg shadow-blue-500/10"
                          : "border-white/[0.08] hover:border-white/[0.18]"
                      }`}
                      onClick={() => setSelectedArticle(article)}
                    >
                      <div className="flex items-center gap-2 text-[11px] text-slate-500 mb-1.5">
                        <span>{article.date}</span>
                        <span>•</span>
                        <span>{article.author}</span>
                      </div>

                      <h4 className="text-[14.5px] font-semibold text-white leading-snug mb-2">
                        {article.title}
                      </h4>
                      <p className="text-xs text-slate-400 line-clamp-2 leading-relaxed mb-3">
                        {article.snippet}
                      </p>

                      <div className="flex items-center gap-2 flex-wrap">
                        {sentiment && (
                          <span
                            className={`text-[10.5px] font-bold px-2 py-0.5 rounded border ${
                              sentiment.prediction === "Negativo"
                                ? "bg-red-500/15 text-red-300 border-red-500/30"
                                : sentiment.prediction === "Positivo"
                                  ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                                  : "bg-slate-500/15 text-slate-300 border-slate-500/30"
                            }`}
                          >
                            {sentiment.prediction} ({sentiment.confidence}%)
                          </span>
                        )}
                        {topFrame && (
                          <span className="bg-purple-500/10 border border-purple-500/25 text-purple-300 text-[10.5px] px-2 py-0.5 rounded">
                            {topFrame.label} ({topFrame.score}%)
                          </span>
                        )}

                        {onSendToAnalyzer && (
                          <button
                            type="button"
                            className="ml-auto text-[11px] font-semibold text-orange-400 hover:text-orange-300 bg-orange-500/10 hover:bg-orange-500/20 border border-orange-500/25 px-2.5 py-1 rounded inline-flex items-center gap-1 transition-all"
                            onClick={e => {
                              e.stopPropagation()
                              onSendToAnalyzer(article.fullText)
                            }}
                            title="Llevar texto al editor individual"
                          >
                            <span>Abrir</span>
                            <SparklesIcon size={12} />
                          </button>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Right: Deep Analysis of Selected Article */}
            <div className="flex flex-col gap-5">
              {selectedArticle?.preAnalyzedResult ? (
                <div className="flex flex-col gap-5">
                  <div className="bg-[#0e111a]/90 border border-white/[0.08] rounded-2xl p-4 sm:p-5">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-blue-400">
                      Inspección de Noticia
                    </span>
                    <h3 className="font-['Outfit'] text-[16px] font-bold text-white mt-1 mb-2 leading-snug">
                      {selectedArticle.title}
                    </h3>
                    <div className="flex items-center gap-2 text-xs text-slate-400 flex-wrap">
                      <span>
                        Medio:{" "}
                        <strong className="text-white">{selectedArticle.media}</strong>
                      </span>
                      <span>•</span>
                      <span>
                        País:{" "}
                        <strong className="text-white">{selectedArticle.country}</strong>
                      </span>
                      <span>•</span>
                      <a
                        href={selectedArticle.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-400 hover:text-blue-300 inline-flex items-center gap-1"
                      >
                        Enlace original <ExternalLinkIcon size={12} />
                      </a>
                    </div>
                  </div>

                  <SentimentGauge
                    sentiment={selectedArticle.preAnalyzedResult.sentiment}
                  />
                  <FramesBarChart
                    frames={selectedArticle.preAnalyzedResult.frames}
                    threshold={50.0}
                  />
                  <CulturalBiasCard
                    bias={selectedArticle.preAnalyzedResult.culturalBias}
                    mediaName={selectedArticle.media}
                  />

                  <div className="bg-[#10131d]/85 backdrop-blur-md border border-white/[0.08] rounded-2xl p-4 sm:p-5">
                    <h4 className="text-xs font-semibold text-white uppercase tracking-wider mb-2">
                      Texto Extraído por el API
                    </h4>
                    <p className="text-xs text-slate-300 leading-relaxed max-h-48 overflow-y-auto pr-1">
                      {selectedArticle.fullText}
                    </p>
                  </div>
                </div>
              ) : (
                <div className="bg-[#10131d]/85 border border-white/[0.08] rounded-2xl p-12 text-center text-slate-500 flex flex-col items-center justify-center gap-2">
                  <FileTextIcon size={36} color="#64748b" />
                  <p className="text-xs">
                    Selecciona una noticia para ver el análisis detallado.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
