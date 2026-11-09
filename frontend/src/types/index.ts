export type SentimentType = "Negativo" | "Neutro" | "Positivo"

export type FrameId =
  | "acceso_servicios"
  | "transito_migratorio"
  | "seguridad"
  | "integracion_social"
  | "politica_migratoria"
  | "empleo_economia"
  | "otros"

export interface FrameScore {
  id: FrameId
  label: string
  score: number // 0 to 100
  isActive: boolean // >= threshold (default 50%)
  description: string
  associatedKeywords: string[]
}

export interface SentimentAnalysis {
  prediction: SentimentType
  confidence: number
  scores: {
    negativo: number
    neutro: number
    positivo: number
  }
  explanation: string
}

export interface CulturalBias {
  detectedBias:
    | "Colombia (Enfoque Punitivo / Seguridad)"
    | "México (Enfoque Laboral / Tránsito)"
    | "Neutro / Institucional"
  colombiaAlignmentScore: number // 0 to 100
  mexicoAlignmentScore: number // 0 to 100
  reasoning: string
  highlightedTerms: Array<{
    term: string
    biasType: "colombia" | "mexico" | "negative" | "positive"
    weight: number
  }>
}

export interface TextAnalysisResult {
  id: string
  text: string
  title?: string
  sourceUrl?: string
  mediaName?: string
  country?: "Colombia" | "México" | "Desconocido"
  dateAnalyzed: string
  sentiment: SentimentAnalysis
  frames: FrameScore[]
  culturalBias: CulturalBias
  tokensCount: number
  readingTimeSeconds: number
  modelUsed: "BETO-v2.1-Spanish" | "RoBERTa-BNE" | "XLM-R-MigraLatam"
}

export interface NewsArticle {
  id: string
  title: string
  snippet: string
  fullText: string
  author: string
  date: string
  media: string
  country: "Colombia" | "México"
  url: string
  category: string
  preAnalyzedResult?: TextAnalysisResult
}

export interface NewsSitePreset {
  id: string
  name: string
  domain: string
  country: "Colombia" | "México"
  flag: string
  category: "Prensa Escrita" | "Medio Digital" | "Televisión/Radio"
  description: string
  logoText: string
  accentColor: string
  articles: NewsArticle[]
}

export interface ScrapingProgress {
  status:
    | "idle"
    | "connecting"
    | "crawling"
    | "cleaning"
    | "analyzing"
    | "completed"
    | "error"
  currentStep: number
  totalSteps: number
  message: string
  articlesFoundCount: number
}

export interface ScrapedSiteSummary {
  siteName: string
  domain: string
  country: "Colombia" | "México" | "Internacional"
  totalAnalyzed: number
  averageSentiment: {
    negativo: number
    neutro: number
    positivo: number
  }
  topFrames: Array<{
    frame: string
    percentage: number
  }>
  biasTendency: string
  hypothesisMatch: "Confirmada (Sesgo esperado)" | "Parcial" | "No concluyente"
  articles: NewsArticle[]
}

export interface ModelMetricData {
  modelName: string
  architecture: string
  accuracy: number
  precision: number
  recall: number
  f1Score: number
  corpusSize: string
  isBest: boolean
}

export interface ConfusionMatrixData {
  labels: string[]
  matrix: number[][] // [real][predicted]
}
