import React, { useState, useRef } from "react"
import type { TextAnalysisResult } from "../types"
import { PRELOADED_EXAMPLES } from "../data/sampleNewsWebsites"
import {
  analyzeNewsText,
  collectAnalysisWarnings,
  formatAnalysisDate,
} from "../services/nlpAnalyzer"
import { describeApiError, isAbortError } from "../services/api"
import { SentimentGauge } from "./SentimentGauge"
import { FramesBarChart } from "./FramesBarChart"
import { CulturalBiasCard } from "./CulturalBiasCard"
import {
  UploadCloudIcon,
  Trash2Icon,
  SparklesIcon,
  FileTextIcon,
  BrainIcon,
  ArrowLeftIcon,
} from "./Icons"

interface SingleAnalyzerProps {
  initialText?: string
}

export const SingleAnalyzer: React.FC<SingleAnalyzerProps> = ({ initialText }) => {
  const defaultText =
    initialText ||
    "Los migrantes venezolanos llegan a la ciudad en busca de trabajo y oportunidades para sus familias."

  const [text, setText] = useState<string>(defaultText)
  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false)
  const [analysisResult, setAnalysisResult] = useState<TextAnalysisResult | null>(null)
  const [loadingStepText, setLoadingStepText] = useState<string>("Enviando texto al API...")
  const [loadingProgress, setLoadingProgress] = useState<number>(20)
  const [isDragging, setIsDragging] = useState<boolean>(false)
  const [dragFileName, setDragFileName] = useState<string | null>(null)
  const [highlightMode, setHighlightMode] = useState<boolean>(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [previousInitialText, setPreviousInitialText] = useState(initialText)

  // Sync changed prop values during render without an effect-triggered cascading render.
  if (initialText && initialText !== previousInitialText) {
    setPreviousInitialText(initialText)
    setText(initialText)
    setAnalysisResult(null)
    setErrorMessage(null)
  }

  const handleAnalyze = async () => {
    const cleanText = text.trim()
    if (!cleanText || isAnalyzing) return

    setIsAnalyzing(true)
    setAnalysisResult(null)
    setErrorMessage(null)
    setLoadingProgress(20)
    setLoadingStepText("Normalizando texto y enviándolo al motor BETO del API...")

    // Mensajes de espera mientras el API responde: no sustituyen datos reales.
    const secondStep = window.setTimeout(() => {
      setLoadingProgress(55)
      setLoadingStepText("Ejecutando modelos BETO de sentimiento y encuadres...")
    }, 700)
    const thirdStep = window.setTimeout(() => {
      setLoadingProgress(85)
      setLoadingStepText("Calculando el diagnóstico de sesgo cultural...")
    }, 1600)

    try {
      const result = await analyzeNewsText(cleanText, {
        ...(dragFileName ? { title: dragFileName } : {}),
      })
      setLoadingProgress(100)
      setLoadingStepText("Análisis completado con datos del API.")
      setAnalysisResult(result)
    } catch (error) {
      if (!isAbortError(error)) {
        setErrorMessage(describeApiError(error))
      }
    } finally {
      window.clearTimeout(secondStep)
      window.clearTimeout(thirdStep)
      setIsAnalyzing(false)
    }
  }

  const handleClear = () => {
    setText("")
    setAnalysisResult(null)
    setDragFileName(null)
    setErrorMessage(null)
  }

  const handleReturnToEdit = () => {
    setAnalysisResult(null)
    setErrorMessage(null)
  }

  const handleSelectExample = (exText: string) => {
    setText(exText)
    setDragFileName(null)
    setAnalysisResult(null)
    setErrorMessage(null)
  }

  const handleTextChange = (value: string) => {
    setText(value)
    if (errorMessage) setErrorMessage(null)
  }

  // Drag and drop handlers
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0]
      readFileContent(file)
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0]
      readFileContent(file)
    }
  }

  const readFileContent = (file: File) => {
    const reader = new FileReader()
    reader.onload = event => {
      const content = event.target?.result as string
      if (content) {
        setText(content)
        setDragFileName(file.name)
        setAnalysisResult(null)
        setErrorMessage(null)
      }
    }
    reader.readAsText(file)
  }

  const wordCount = text.trim() ? text.trim().split(/\s+/).length : 0
  const charCount = text.length
  const warnings = analysisResult ? collectAnalysisWarnings(analysisResult) : []

  return (
    <div className="max-w-4xl mx-auto w-full flex flex-col gap-7">
      {/* 1. INITIAL STATE: Show Text Input Card when not yet analyzed or editing */}
      {!analysisResult && !isAnalyzing && (
        <div className="bg-[#10131d]/85 backdrop-blur-md border border-white/[0.08] rounded-3xl p-6 sm:p-7 shadow-2xl shadow-black/50 transition-all hover:border-white/[0.14] flex flex-col animate-enter">
          <div className="flex items-center justify-between mb-3.5 flex-wrap gap-2">
            <label
              htmlFor="news-input"
              className="text-[14.5px] font-semibold text-white"
            >
              Texto de la noticia
            </label>

            <div className="flex items-center gap-2.5">
              {dragFileName && (
                <span className="inline-flex items-center gap-1.5 bg-orange-500/10 border border-orange-500/30 text-orange-400 text-xs px-2.5 py-1 rounded-md">
                  <FileTextIcon size={13} />
                  {dragFileName}
                </span>
              )}
              <button
                type="button"
                className="inline-flex items-center gap-1.5 text-xs text-slate-300 bg-white/[0.04] border border-white/[0.08] hover:border-white/20 hover:bg-white/[0.08] hover:text-white px-3 py-1.5 rounded-lg transition-all"
                onClick={() => fileInputRef.current?.click()}
                title="Cargar archivo .txt, .md, .json"
              >
                <UploadCloudIcon size={14} />
                <span>Subir archivo</span>
              </button>
              <input
                type="file"
                ref={fileInputRef}
                style={{ display: "none" }}
                accept=".txt,.md,.json,.csv"
                onChange={handleFileChange}
              />
            </div>
          </div>

          {errorMessage && (
            <div
              role="alert"
              className="mb-3 rounded-xl border border-red-500/35 bg-red-500/10 px-4 py-3 text-[13px] leading-relaxed text-red-200 flex items-start gap-2.5"
            >
              <span className="mt-0.5 size-2 shrink-0 rounded-full bg-red-400" />
              <div className="min-w-0">
                <p className="font-semibold text-red-200">No se pudo analizar la noticia</p>
                <p className="text-red-200/90 break-words">{errorMessage}</p>
                <p className="mt-1 text-[11.5px] text-red-300/70">
                  Revisa que el API esté corriendo en{" "}
                  <span className="font-mono">
                    {import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000"}
                  </span>
                  .
                </p>
              </div>
            </div>
          )}

          {/* Dropzone wrapping Textarea */}
          <div
            className={`relative rounded-xl transition-all ${
              isDragging ? "ring-2 ring-dashed ring-orange-500 bg-orange-500/[0.04]" : ""
            }`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            {isDragging && (
              <div className="absolute inset-0 bg-[#0c0e15]/95 backdrop-blur-sm rounded-xl flex flex-col items-center justify-center gap-2.5 z-20 pointer-events-none">
                <UploadCloudIcon size={38} color="#f97316" />
                <p className="text-sm font-semibold text-orange-400">
                  Arrastra y suelta tu archivo de texto aquí
                </p>
              </div>
            )}
            <textarea
              id="news-input"
              className="w-full bg-[#0c0e15] text-slate-100 border border-white/[0.08] focus:border-orange-500 focus:ring-2 focus:ring-orange-500/20 rounded-xl p-4 sm:p-4.5 text-[14.5px] leading-relaxed resize-y min-h-[140px] outline-none transition-all placeholder:text-slate-600"
              rows={5}
              value={text}
              onChange={e => handleTextChange(e.target.value)}
              placeholder="Escribe o pega aquí el cuerpo de una noticia sobre migración venezolana, o arrastra un archivo..."
            />
          </div>

          {/* Bottom meta */}
          <div className="flex items-center justify-between mt-2.5 mb-4 text-xs text-slate-500">
            <div className="flex items-center gap-1.5">
              <span>{wordCount} palabras</span>
              <span className="opacity-40">•</span>
              <span>{charCount} caracteres</span>
            </div>
          </div>

          {/* Actions Row: Limpiar and Analizar noticia */}
          <div className="flex items-center gap-3 mb-5">
            <button
              type="button"
              className="flex-1 bg-white/[0.05] hover:bg-white/[0.09] text-slate-300 hover:text-white border border-white/[0.08] hover:border-white/[0.18] py-3 px-4 rounded-xl text-sm font-semibold inline-flex items-center justify-center gap-2 transition-all disabled:opacity-35 disabled:cursor-not-allowed"
              onClick={handleClear}
              disabled={!text || isAnalyzing}
            >
              <Trash2Icon size={15} />
              <span>Limpiar</span>
            </button>

            <button
              type="button"
              className="flex-[1.5] bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-400 hover:to-orange-500 text-white font-bold py-3 px-5 rounded-xl text-[14.5px] inline-flex items-center justify-center gap-2 shadow-lg shadow-orange-500/35 hover:shadow-orange-500/50 hover:-translate-y-0.5 active:translate-y-0 transition-all disabled:opacity-45 disabled:cursor-not-allowed disabled:transform-none disabled:shadow-none"
              onClick={handleAnalyze}
              disabled={!text.trim() || isAnalyzing}
            >
              <SparklesIcon size={16} />
              <span>Analizar noticia</span>
            </button>
          </div>

          {/* Examples Section */}
          <div className="border-t border-white/[0.07] pt-4">
            <div className="mb-2.5">
              <span className="text-slate-500 text-xs font-semibold uppercase tracking-wider">
                Ejemplos rápidos:
              </span>
            </div>

            <div className="flex flex-wrap gap-2">
              {PRELOADED_EXAMPLES.map(ex => (
                <button
                  key={ex.id}
                  type="button"
                  className="bg-white/[0.035] hover:bg-white/[0.07] border border-white/[0.07] hover:border-white/[0.16] rounded-lg px-3 py-1.5 text-left transition-all max-w-full"
                  onClick={() => handleSelectExample(ex.text)}
                  title={ex.text}
                >
                  <span className="block text-xs sm:text-[12.5px] text-slate-300 truncate max-w-[340px]">
                    {ex.snippet}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* 2. LOADING STATE: Neural analyzing screen while the API responds */}
      {isAnalyzing && (
        <div className="bg-gradient-to-b from-[#141826]/90 to-[#0e111b]/90 backdrop-blur-md border border-orange-500/25 rounded-3xl p-10 sm:p-12 text-center shadow-2xl shadow-orange-500/10 flex flex-col items-center justify-center animate-enter">
          <div className="w-16 h-16 rounded-full bg-orange-500/10 border border-orange-500/35 flex items-center justify-center mb-5 shadow-lg shadow-orange-500/25">
            <BrainIcon size={34} color="#f97316" className="animate-pulse-brain" />
          </div>

          <h3 className="font-['Outfit'] text-xl font-bold text-white mb-2">
            Analizando noticia con modelos BETO
          </h3>
          <p className="text-sm text-slate-400 mb-6 min-h-[20px]">{loadingStepText}</p>

          <div className="w-full max-w-md h-1.5 bg-white/[0.08] rounded-full overflow-hidden mb-5">
            <div
              className="h-full bg-gradient-to-r from-orange-500 to-orange-600 rounded-full transition-all duration-400 shadow-md shadow-orange-500/50"
              style={{ width: `${loadingProgress}%` }}
            />
          </div>

          <div className="flex flex-wrap justify-center gap-2">
            <span
              className={`text-[11px] font-semibold px-2.5 py-1 rounded-full border transition-all ${
                loadingProgress >= 25
                  ? "bg-orange-500/15 text-orange-300 border-orange-500/35"
                  : "bg-white/[0.04] text-slate-500 border-white/[0.06]"
              }`}
            >
              1. Envío al API
            </span>
            <span
              className={`text-[11px] font-semibold px-2.5 py-1 rounded-full border transition-all ${
                loadingProgress >= 50
                  ? "bg-orange-500/15 text-orange-300 border-orange-500/35"
                  : "bg-white/[0.04] text-slate-500 border-white/[0.06]"
              }`}
            >
              2. Sentimiento
            </span>
            <span
              className={`text-[11px] font-semibold px-2.5 py-1 rounded-full border transition-all ${
                loadingProgress >= 80
                  ? "bg-orange-500/15 text-orange-300 border-orange-500/35"
                  : "bg-white/[0.04] text-slate-500 border-white/[0.06]"
              }`}
            >
              3. Encuadres
            </span>
            <span
              className={`text-[11px] font-semibold px-2.5 py-1 rounded-full border transition-all ${
                loadingProgress >= 100
                  ? "bg-orange-500/15 text-orange-300 border-orange-500/35"
                  : "bg-white/[0.04] text-slate-500 border-white/[0.06]"
              }`}
            >
              4. Sesgo cultural
            </span>
          </div>
        </div>
      )}

      {/* 3. RESULTS STATE: When analyzed, textarea is hidden and full info is displayed */}
      {analysisResult && !isAnalyzing && (
        <div className="flex flex-col gap-6 w-full animate-enter">
          {/* Top card: Analyzed News Quote with option to edit or analyze another */}
          <div className="bg-gradient-to-b from-[#131723]/90 to-[#0d101a]/90 backdrop-blur-md border border-white/[0.08] rounded-2xl p-5 sm:p-6 shadow-xl flex flex-col gap-4">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399]" />
                <span className="text-xs font-bold uppercase tracking-wider text-white">
                  Noticia Analizada
                </span>
              </div>

              <div className="flex items-center gap-2.5 flex-wrap">
                <button
                  type="button"
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-purple-300 bg-purple-500/10 hover:bg-purple-500/20 border border-purple-500/25 px-3 py-1.5 rounded-lg transition-all"
                  onClick={() => setHighlightMode(!highlightMode)}
                >
                  <SparklesIcon size={13} color="#a855f7" />
                  <span>
                    {highlightMode ? "Ocultar marcadores" : "Ver términos identificados"}
                  </span>
                </button>

                <button
                  type="button"
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-200 bg-white/[0.06] hover:bg-white/[0.12] border border-white/[0.12] hover:border-white/25 px-3.5 py-1.5 rounded-lg transition-all"
                  onClick={handleReturnToEdit}
                  title="Volver a editar o analizar otra noticia"
                >
                  <ArrowLeftIcon size={14} />
                  <span>Analizar otra noticia / Editar</span>
                </button>
              </div>
            </div>

            {/* Displaying the analyzed text body */}
            <div className="bg-[#0a0c13]/70 border border-white/[0.05] border-l-4 border-l-orange-500 rounded-xl p-4">
              {highlightMode ? (
                <p className="text-[14px] leading-relaxed text-slate-300">
                  {text.split(/\s+/).map((word, i) => {
                    const clean = word.toLowerCase().replace(/[.,;:]/g, "")
                    const match = analysisResult.culturalBias.highlightedTerms.find(t =>
                      clean.includes(t.term),
                    )
                    if (match) {
                      const tagColor =
                        match.biasType === "colombia"
                          ? "bg-red-500/20 text-red-300 border-red-500/40"
                          : match.biasType === "mexico"
                            ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                            : match.biasType === "negative"
                              ? "bg-orange-500/20 text-orange-300 border-orange-500/40"
                              : "bg-blue-500/20 text-blue-300 border-blue-500/40"

                      return (
                        <span
                          key={i}
                          className={`px-1.5 py-0.5 rounded font-semibold border inline-block ${tagColor}`}
                          title={`Sesgo: ${match.biasType} (+${match.weight})`}
                        >
                          {word}{" "}
                        </span>
                      )
                    }
                    return <span key={i}>{word} </span>
                  })}
                </p>
              ) : (
                <p className="text-[14.5px] leading-relaxed text-slate-300">“{text}”</p>
              )}
            </div>

            <div className="flex items-center gap-2 text-[11.5px] text-slate-500 flex-wrap">
              <span>{wordCount} palabras analizadas</span>
              <span className="opacity-40">•</span>
              <span>Modelo: {analysisResult.modelUsed}</span>
              <span className="opacity-40">•</span>
              <span>
                Analizado: {formatAnalysisDate(analysisResult.dateAnalyzed)}
              </span>
              {analysisResult.country && (
                <>
                  <span className="opacity-40">•</span>
                  <span>País: {analysisResult.country}</span>
                </>
              )}
            </div>

            {warnings.length > 0 && (
              <div className="rounded-xl border border-amber-500/25 bg-amber-500/[0.07] px-4 py-3 text-[12px] leading-relaxed text-amber-200/90">
                <p className="font-semibold text-amber-200 mb-1">
                  Avisos del motor de análisis
                </p>
                <ul className="list-disc list-inside space-y-0.5">
                  {warnings.map(warning => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Grid with Sentiment and Frames */}
          <div className="grid grid-cols-1 md:grid-cols-[1fr_1.1fr] gap-6">
            <SentimentGauge sentiment={analysisResult.sentiment} />
            <FramesBarChart frames={analysisResult.frames} threshold={50.0} />
          </div>

          {/* Full-width Cultural Bias Diagnostic */}
          <CulturalBiasCard
            bias={analysisResult.culturalBias}
            mediaName={analysisResult.mediaName ?? undefined}
          />
        </div>
      )}
    </div>
  )
}
