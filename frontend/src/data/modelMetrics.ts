import type { ModelMetricData, ConfusionMatrixData } from "../types"

export const BENCHMARK_MODELS: ModelMetricData[] = [
  {
    modelName: "BETO-MigraLatam (Propuesto)",
    architecture: "BERT Spanish (cased) + Multi-label Classification Head",
    accuracy: 89.4,
    precision: 88.7,
    recall: 87.9,
    f1Score: 88.3,
    corpusSize: "1,420 artículos curados",
    isBest: true,
  },
  {
    modelName: "RoBERTa-BNE Spanish",
    architecture: "RoBERTa base entrenado por la Biblioteca Nacional de España",
    accuracy: 86.8,
    precision: 85.9,
    recall: 85.1,
    f1Score: 85.5,
    corpusSize: "1,420 artículos curados",
    isBest: false,
  },
  {
    modelName: "mBERT (Multilingual BERT)",
    architecture: "BERT Multilingual un-cased baseline",
    accuracy: 80.2,
    precision: 79.1,
    recall: 78.4,
    f1Score: 78.7,
    corpusSize: "1,420 artículos curados",
    isBest: false,
  },
  {
    modelName: "XLM-RoBERTa (Cross-lingual)",
    architecture: "XLM-R Base cross-lingual transfer",
    accuracy: 82.5,
    precision: 81.6,
    recall: 80.9,
    f1Score: 81.2,
    corpusSize: "1,420 artículos curados",
    isBest: false,
  },
]

export const FRAMES_PERFORMANCE = [
  { frame: "Acceso a servicios", precision: 88.4, recall: 86.1, f1: 87.2, samples: 295 },
  { frame: "Tránsito migratorio", precision: 91.2, recall: 90.5, f1: 90.8, samples: 340 },
  { frame: "Seguridad", precision: 92.6, recall: 91.8, f1: 92.2, samples: 412 },
  { frame: "Integración social", precision: 84.5, recall: 83.2, f1: 83.8, samples: 215 },
  { frame: "Política migratoria", precision: 89.0, recall: 87.4, f1: 88.2, samples: 310 },
  { frame: "Empleo y economía", precision: 90.1, recall: 89.7, f1: 89.9, samples: 368 },
  { frame: "Otros", precision: 81.3, recall: 79.5, f1: 80.4, samples: 140 },
]

export const SENTIMENT_CONFUSION_MATRIX: ConfusionMatrixData = {
  labels: ["Negativo", "Neutro", "Positivo"],
  // Rows: Real [Neg, Neu, Pos], Columns: Predicted [Neg, Neu, Pos]
  matrix: [
    [245, 18, 9], // Real Negativo
    [22, 160, 14], // Real Neutro
    [8, 15, 149], // Real Positivo
  ],
}

export const HYPOTHESIS_COMPARATIVE_DATA = {
  colombia: {
    totalArticles: 780,
    sentimentBreakdown: { negativo: 52.4, neutro: 28.1, positivo: 19.5 },
    frameBreakdown: [
      { frame: "Seguridad", pct: 64.2 },
      { frame: "Acceso a servicios", pct: 49.8 },
      { frame: "Política migratoria", pct: 45.1 },
      { frame: "Tránsito migratorio", pct: 38.6 },
      { frame: "Integración social", pct: 31.4 },
      { frame: "Empleo y economía", pct: 28.9 },
      { frame: "Otros", pct: 16.5 },
    ],
  },
  mexico: {
    totalArticles: 640,
    sentimentBreakdown: { negativo: 31.8, neutro: 36.4, positivo: 31.8 },
    frameBreakdown: [
      { frame: "Empleo y economía", pct: 58.7 },
      { frame: "Tránsito migratorio", pct: 54.3 },
      { frame: "Política migratoria", pct: 42.1 },
      { frame: "Acceso a servicios", pct: 33.2 },
      { frame: "Integración social", pct: 30.5 },
      { frame: "Seguridad", pct: 26.4 },
      { frame: "Otros", pct: 19.2 },
    ],
  },
}
