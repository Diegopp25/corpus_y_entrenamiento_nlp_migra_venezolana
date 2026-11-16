# Migrar el frontend al API

Guía paso a paso para que `frontend-extract` (React + Vite + TypeScript) deje de
usar datos simulados y consuma el API real. Al terminar:

- `src/services/nlpAnalyzer.ts` ya no simula el análisis: llama a `POST /v1/analyze`.
- `src/services/newsScraperService.ts` ya no inventa artículos: lanza
  `POST /v1/sources/scan` y hace polling del job.
- `src/data/modelMetrics.ts` (métricas hardcodeadas) se reemplaza por
  `GET /v1/dashboard/models` y `GET /v1/dashboard/corpus`.
- Los tipos de `src/types/index.ts` reflejan el contrato real (camelCase).

El cliente TypeScript listo para usar está en
[`integrations/frontend-api-client.ts`](../integrations/frontend-api-client.ts).
Es un archivo **sin dependencias** (solo `fetch`). El contrato completo de cada
endpoint está en [`docs/API.md`](./API.md).

---

## 0. Prerrequisitos

1. **API corriendo**. Desde `api/`:

   ```powershell
   Copy-Item .env.example .env   # primera vez; ajusta NLP_SENTIMENT_MODEL_DIR, etc.
   .\scripts\run_dev.ps1 -Reload
   # o: .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
   ```

   Verifica `http://localhost:8000/v1/health`. Sin pesos BETO el API arranca en
   modo **léxico** (`engine.selected = "lexicon"`, `degraded = true` solo si se
   forzó un motor); para integrar el frontend alcanza.

2. **CORS**. Por defecto `NLP_CORS_ORIGINS=["*"]`. Si prefieres restringirlo, en
   `api/.env` (¡ojo: es una variable de tipo lista, pydantic-settings exige JSON
   válido, **no** una lista separada por comas!):

   ```text
   NLP_CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
   ```

   Nota: `allow_credentials=False`; no se usan cookies. El API expone
   `X-Request-ID` y `X-Process-Time-Ms` al navegador.

3. **API key (opcional)**. Si el API define `NLP_API_KEY`, todas las peticiones
   deben llevar `X-API-Key` (salvo `/`, `/v1/health`, `/metrics` y la
   documentación). En el frontend se configura con `VITE_API_KEY`
   (**ojo**: las variables `VITE_*` quedan en el bundle; úsalo solo para demo
   local, en producción pone un proxy que inyecte la clave).

4. **Dependencias**: ninguna nueva. No hace falta `axios` ni librerías de
   polling.

---

## 1. Crear `src/services/api.ts`

Copia el cliente del repo al frontend:

```powershell
Copy-Item ..\migra-nlp\integrations\frontend-api-client.ts .\src\services\api.ts
```

El archivo ya incluye:

- tipos espejo de `src/types/index.ts` y de dashboard/monitoreo;
- `ApiError` con `code`, `status`, `detail`, `requestId` y `retryAfter`;
- funciones: `analyzeText`, `analyzeBatch`, `getAnalysis`, `listAnalyses`,
  `getSourcePresets`, `scanSite`, `getScrapeJob`, `getScrapeJobs`, `analyzeUrl`,
  `getOverview`, `getTimeseries`, `getCorpusDashboard`, `getModelEvaluation`,
  `getRecentAnalyses`, `getMonitoringStats`, `getHealth`, `getMetadata`,
  `getModels`, `getMetrics` y `pollJob`;
- base URL por `VITE_API_URL`, header `X-API-Key` por `VITE_API_KEY`.

### 1.1 Variables de entorno

Crea `.env.local` en la raíz del frontend:

```text
VITE_API_URL=http://localhost:8000
# Solo si el API tiene NLP_API_KEY definida:
# VITE_API_KEY=la-clave
# Timeout por petición en ms (opcional, por defecto 30000):
# VITE_API_TIMEOUT_MS=45000
```

Vite expone `import.meta.env`; el cliente ya lo lee, así que no hay que tocar
`vite.config.ts`. Si necesitas tipar el entorno, `src/vite-env.d.ts`:

```ts
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string
  readonly VITE_API_KEY?: string
  readonly VITE_API_TIMEOUT_MS?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
```

### 1.2 Tipos: `src/types/index.ts`

El cliente es autocontenido (define sus propios tipos), así que **funciona
aunque no toques los tipos**. Recomendado para no duplicar:

1. Copia al `src/types/index.ts` los bloques 1–4 del cliente (tipos espejo).
2. En `api.ts`, importa los tipos desde `../types` y borra los duplicados.

Si prefieres el camino rápido, no cambies nada al principio; luego
desduplica. Los cambios de tipos que sí o sí necesitas en los componentes:

| Tipo actual | Qué ajustar |
| --- | --- |
| `TextAnalysisResult.modelUsed` | Pasa de unión de 3 strings a `string` (el API devuelve el nombre del motor real). |
| `TextAnalysisResult` | Agregar `meta?: AnalysisMeta` (opcional). `dateAnalyzed` sigue siendo `string`, ahora ISO 8601. |
| `TextAnalysisResult.country` | Agregar `"Internacional"`. |
| `NewsSitePreset` | El API devuelve `SourcePreset` con `flag/logoText/accentColor` y las mismas categorías; solo falta `articles` (se obtiene escaneando). |
| `ModelMetricData` | `accuracy/precision/recall/f1Score` pueden ser `null`; `corpusSize` deja de venir del API (`samples` numérico). |

---

## 2. Reemplazar `nlpAnalyzer.ts`

El API hace exactamente lo que simulaba `analyzeNewsText`, pero **es asíncrono**
y el resultado incluye `meta` y fechas ISO.

`src/services/nlpAnalyzer.ts` nuevo:

```ts
import { analyzeText } from "./api";
import type { TextAnalysisResult } from "../types";

export interface AnalyzeMetadata {
  title?: string;
  sourceUrl?: string;
  mediaName?: string;
  country?: "Colombia" | "México" | "Mexico" | "Internacional" | "Desconocido";
}

/**
 * Analiza un texto con el API real.
 * Mantiene el nombre que ya usan los componentes; ahora devuelve una Promise.
 */
export async function analyzeNewsText(
  text: string,
  metadata?: AnalyzeMetadata,
): Promise<TextAnalysisResult> {
  return analyzeText({
    text,
    title: metadata?.title,
    sourceUrl: metadata?.sourceUrl,
    mediaName: metadata?.mediaName,
    country: metadata?.country,
  });
}
```

### 2.1 Ajustar el componente que lo usa

En `src/components/SingleAnalyzer.tsx` (línea ~67) el resultado pasa a ser
`await`:

```ts
// antes
const result = analyzeNewsText(text, { title, sourceUrl, mediaName, country })
setResult(result)

// después
try {
  setLoading(true)
  setError(null)
  const result = await analyzeNewsText(text, { title, sourceUrl, mediaName, country })
  setResult(result)
} catch (err) {
  setError(err instanceof ApiError ? err.message : "No se pudo analizar el texto")
} finally {
  setLoading(false)
}
```

Importa `ApiError` desde `./api` y muestra `error.code`/`error.detail` si quieres
mensajes más finos (`invalid_text`, `rate_limited`, `engine_error`…).

### 2.2 Diferencias esperadas al mostrar el resultado

| Campo | Antes (simulado) | Ahora (API) |
| --- | --- | --- |
| `id` | `analisis-<timestamp>-<random>` | `analisis-<16 hex>` persistido en SQLite. |
| `dateAnalyzed` | Texto preformateado `"09 de noviembre de 2026, 13:58"` | ISO 8601 UTC (`"2026-11-09T18:58:59.572713Z"`). Formatear en la UI. |
| `modelUsed` | `"BETO-v2.1-Spanish"` | `"BETO-migra-ve (sentimiento + encuadres)"` (o `"léxico-MigraVenezuela (baseline)"`). |
| `country` | 3 valores | Puede ser `"Internacional"`. |
| `meta` | no existía | Motor, latencia, `warnings[]`, `truncated`, `persisted`, `jobId`… |
| `sentiment.confidence` | número | Igual: 0–100, coincide con el score ganador. |
| `frames` | 7, orden descendente | Igual (umbrales reales de `artifacts/thresholds.json`). |

Formateador sugerido (crea `src/utils/date.ts`):

```ts
export function formatAnalysisDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return new Intl.DateTimeFormat("es-CO", {
    dateStyle: "long",
    timeStyle: "short",
  }).format(date)
}
```

> `POST /v1/analyze` **guarda** el resultado. Si quieres abrir un análisis
> después (recarga, historial), usa `getAnalysis(id)`.

---

## 3. Reemplazar `newsScraperService.ts`

El flujo cambia de «esperar 3 s y devolver datos mock» a **crear un job y
seguirlo con polling**.

### 3.1 Función `scrapeNewsSite`

`src/services/newsScraperService.ts` nuevo:

```ts
import { ApiError, pollJob, scanSite } from "./api";
import type { ScrapedSiteSummary, ScrapingProgress } from "../types";

export interface ScrapingOptions {
  url: string;
  maxArticles?: number;
  keywords?: string[];
  dateRange?: string;          // no lo usa el API todavía (se conserva por compatibilidad)
  onProgress?: (progress: ScrapingProgress) => void;
  signal?: AbortSignal;        // para cancelar desde el componente
}

export async function scrapeNewsSite(
  options: ScrapingOptions,
): Promise<ScrapedSiteSummary> {
  const { url, maxArticles = 4, keywords, onProgress, signal } = options;

  let accepted;
  try {
    accepted = await scanSite({ url, maxArticles, keywords });
  } catch (err) {
    onProgress?.({
      status: "error",
      currentStep: 0,
      totalSteps: 5,
      message: err instanceof ApiError ? err.message : "No se pudo iniciar el escaneo",
      articlesFoundCount: 0,
    });
    throw err;
  }

  onProgress?.({
    status: accepted.status,          // "queued"
    currentStep: 0,
    totalSteps: 5,
    message: "Trabajo en cola…",
    articlesFoundCount: 0,
  });

  const job = await pollJob(
    accepted.jobId,
    (job) => {
      onProgress?.({
        status: job.status,
        currentStep: job.currentStep,
        totalSteps: job.totalSteps,
        message: job.message,
        articlesFoundCount: job.articlesFoundCount,
      });
    },
    {
      // el API recomienda 1,5 s (accepted.pollAfterSeconds)
      intervalMs: Math.round((accepted.pollAfterSeconds ?? 1.5) * 1000),
      timeoutMs: 5 * 60 * 1000,
      signal,
    },
  );

  if (!job.summary) {
    throw new ApiError("El job terminó sin resumen de sitio", {
      code: "scrape_job_error",
      status: 200,
      detail: job,
    });
  }
  return job.summary;
}
```

Convenciones del job (las pinta la UI existente):

1. `queued` → 2. `connecting` → 3. `crawling` → 4. `cleaning` → 5. `analyzing`
→ `completed` (o `error`). Cada paso trae `message`, `currentStep` y
`totalSteps = 5`.

`pollJob(jobId, onProgress, opts)`:

- consulta `GET /v1/sources/jobs/{jobId}` cada `intervalMs` (1500 ms por
  defecto);
- llama `onProgress(job)` con **cada** respuesta;
- resuelve con el `ScrapeJobResponse` cuando `status === "completed"`;
- lanza `ApiError` con `code: "scrape_job_error"` y `detail: job` cuando
  `status === "error"` (el server expone el motivo en `job.error`);
- admite `signal` (AbortController) y `timeoutMs` (5 min por defecto).

### 3.2 Cancelar el polling al desmontar

En `src/components/WebsiteScraper.tsx`:

```ts
const abortRef = useRef<AbortController | null>(null)

async function handleScrape() {
  abortRef.current?.abort()
  const controller = new AbortController()
  abortRef.current = controller
  try {
    const summary = await scrapeNewsSite({
      url,
      maxArticles,
      onProgress: setProgress,
      signal: controller.signal,
    })
    setSummary(summary)
  } catch (err) {
    if ((err as Error)?.name === "AbortError") return
    // ApiError trae el motivo real: robots_denied, url_blocked, upstream_timeout…
    setProgress((p) => p && { ...p, status: "error", message: (err as Error).message })
  }
}

useEffect(() => () => abortRef.current?.abort(), [])
```

### 3.3 `analyzeUrl` (analizar una noticia concreta)

Si el flujo necesita «pegar una URL y analizarla» sin rastrear el sitio entero:

```ts
import { analyzeUrl } from "./api";

const article = await analyzeUrl({ url });
// article.preAnalyzedResult es un TextAnalysisResult completo
```

`POST /v1/sources/analyze-url` devuelve un `NewsArticle` (con
`preAnalyzedResult`), no un `TextAnalysisResult` directo.

### 3.4 Presets de medios

`getSourcePresets()` devuelve `SourcePreset[]` reales (8 medios):

```ts
const presets = await getSourcePresets()
// { id, name, domain, country, category, description, flag, logoText, accentColor }
```

Coincide con `NewsSitePreset` salvo por `articles`:

- **sí** trae `flag`, `logoText` y `accentColor`, con las mismas categorías
  (`"Prensa Escrita"` / `"Medio Digital"`) que el tipo del frontend: puedes
  reemplazar `SAMPLE_NEWS_SITES` por estos presets casi directamente;
- **no** trae `articles`: los artículos salen de un escaneo real
  (`scanSite` + `pollJob`) o de `analyzeUrl` para una sola noticia. Si la UI
  necesita un estado inicial, deja `articles: []` hasta que el usuario escanee.

`exportCorpusToCSV` y `exportCorpusToJSON` son funciones puras: puedes dejarlas
tal cual en `newsScraperService.ts` o moverlas a `src/utils/exportCorpus.ts`.

---

## 4. Dashboard: reemplazar `src/data/modelMetrics.ts`

Los cuatro exports hardcodeados (`BENCHMARK_MODELS`, `FRAMES_PERFORMANCE`,
`SENTIMENT_CONFUSION_MATRIX`, `HYPOTHESIS_COMPARATIVE_DATA`) se reemplazan por
dos llamadas:

- `getModelEvaluation()` → `GET /v1/dashboard/models`
- `getCorpusDashboard()` → `GET /v1/dashboard/corpus`

> **Datos reales, no maqueta.** `modelMetrics.ts` dice «1.420 artículos curados»
> y muestra ~89 % de accuracy: son cifras ficticias de la maqueta. El corpus
> etiquetado real tiene **156 artículos** (79 Neutro, 44 Negativo, 33 Positivo;
> 77 Colombia, 79 México), con accuracy de sentimiento ≈ 0.789 y macro-F1
> ≈ 0.777. Además, como no se guardó el split de entrenamiento, la evaluación
> puede solaparse con datos de entrenamiento: preséntala como indicador interno,
> no como benchmark independiente.

Crea `src/services/metrics.ts` con adaptadores **para no reescribir los
componentes**:

```ts
import { getCorpusDashboard, getModelEvaluation } from "./api";
import type {
  ConfusionMatrixData,
  ModelMetricData,
} from "../types";

// El artefacto actual escribe ratios 0–1; el front pintaba porcentajes 0–100.
const toPct = (value: number | null | undefined): number => {
  if (value === null || value === undefined) return 0;
  return value <= 1 ? Math.round(value * 1000) / 10 : Math.round(value * 10) / 10;
};

export interface FramePerformanceRow {
  frame: string;
  precision: number;
  recall: number;
  f1: number;
  samples: number;
}

export async function loadBenchmarkModels(): Promise<ModelMetricData[]> {
  const evaluation = await getModelEvaluation();
  if (!evaluation.available) return [];
  return evaluation.models.map((model) => ({
    modelName: model.modelName,
    architecture: model.architecture,
    accuracy: toPct(model.accuracy),
    precision: toPct(model.precision),
    recall: toPct(model.recall),
    f1Score: toPct(model.f1Score),
    corpusSize: model.samples ? `${model.samples} muestras` : "—",
    isBest: model.isBest,
  }));
}

export async function loadFramesPerformance(): Promise<FramePerformanceRow[]> {
  const evaluation = await getModelEvaluation();
  if (!evaluation.available) return [];
  return evaluation.frames.map((frame) => ({
    frame: frame.frame,
    precision: toPct(frame.precision),
    recall: toPct(frame.recall),
    f1: toPct(frame.f1),
    samples: frame.support,
  }));
}

export async function loadConfusionMatrix(): Promise<ConfusionMatrixData | null> {
  const evaluation = await getModelEvaluation();
  return evaluation.confusionMatrix ?? null;
}

export interface HypothesisCountryData {
  totalArticles: number;
  sentimentBreakdown: { negativo: number; neutro: number; positivo: number };
  frameBreakdown: Array<{ frame: string; pct: number }>;
}

export async function loadHypothesisData(): Promise<{
  colombia: HypothesisCountryData | null;
  mexico: HypothesisCountryData | null;
}> {
  const corpus = await getCorpusDashboard();
  const pick = (country: string): HypothesisCountryData | null => {
    const row = corpus.countries.find((item) => item.country === country);
    if (!row) return null;
    return {
      totalArticles: row.totalArticles,
      sentimentBreakdown: row.sentimentBreakdown,
      frameBreakdown: row.frameBreakdown.map((entry) => ({
        frame: entry.frame,
        pct: entry.percentage,
      })),
    };
  };
  return { colombia: pick("Colombia"), mexico: pick("México") };
}
```

### 4.1 `ModelEvaluation.tsx`

Hoy importa las constantes y las renderiza de forma síncrona. Pasa a estado
asíncrono:

```tsx
const [benchmark, setBenchmark] = useState<ModelMetricData[]>([])
const [frames, setFrames] = useState<FramePerformanceRow[]>([])
const [matrix, setMatrix] = useState<ConfusionMatrixData | null>(null)
const [evaluation, setEvaluation] = useState<ModelEvaluation | null>(null)

useEffect(() => {
  let alive = true
  Promise.all([getModelEvaluation()])
    .then(([data]) => {
      if (!alive) return
      setEvaluation(data)
      setBenchmark(data.models.map(/* … ver metrics.ts … */))
      // o directamente: setBenchmark(await loadBenchmarkModels())
    })
    .catch(() => setEvaluation(null))
  return () => { alive = false }
}, [])
```

Si `evaluation.available === false` (no hay `artifacts/evaluation.json`), muestra
`evaluation.message` y un estado vacío en vez de la tabla. El mensaje real del
API es claro: *"No hay artefacto de evaluación en …/api/artifacts/evaluation.json.
Ejecuta la evaluación de modelos (api/scripts/evaluate_models.py) para
generarlo."*

### 4.2 `CorpusDashboard.tsx`

Sustituye `HYPOTHESIS_COMPARATIVE_DATA` por `loadHypothesisData()`:

```tsx
const [hypothesis, setHypothesis] = useState<Awaited<ReturnType<typeof loadHypothesisData>> | null>(null)

useEffect(() => {
  loadHypothesisData().then(setHypothesis).catch(() => setHypothesis(null))
}, [])
```

- `frameBreakdown` del corpus es un array de `{ frame, percentage }`; el
  componente mock usaba `{ frame, pct }` → el adaptador lo convierte.
- Los porcentajes del corpus también son 0–100 (no ratios).

### 4.3 KPIs, series y actividad reciente

Con los endpoints nuevos puedes reemplazar datos estáticos del resto del
dashboard:

| UI | Llamada | Datos |
| --- | --- | --- |
| Tarjetas KPI (`total analizados`, sentimiento medio, confianza) | `getOverview()` | `totalAnalyses`, `sentimentPct`, `avgConfidence`, `analysesToday`, `analysesLast7d`. |
| Gráfico de líneas / volumen temporal | `getTimeseries(days)` | `items[]` con `date`, `total`, `negativo`, `neutro`, `positivo`. |
| Actividad reciente | `getRecentAnalyses(limit)` | `AnalysisSummary[]`. |
| Comparativa Colombia vs. México | `getCorpusDashboard()` | `countries[]`, `frameBreakdown`, `monthlyVolume[]`. |
| Salud del sistema (badge «BETO activo») | `getHealth()` | `engine.selected`, `models[]`, `degraded`, `database`. |
| Página técnica de monitoreo | `getMonitoringStats()`, `getMetrics()` | contadores, latencias, texto Prometheus. |

Ejemplo de tarjeta con `useEffect`/`useState` (o `@tanstack/react-query` si
prefieres, no es obligatorio):

```tsx
useEffect(() => {
  getOverview()
    .then(setOverview)
    .catch((err) => setError(err instanceof ApiError ? err.message : "Sin datos"))
}, [])
```

> Todos los endpoints de dashboard toleran base vacía: devuelven ceros/listas
> vacías en vez de error, así que el dashboard arranca sin haber analizado nada.

---

## 5. Manejo de errores

Todas las funciones lanzan `ApiError`:

```ts
import { ApiError } from "./api";

try {
  await scanSite({ url })
} catch (err) {
  if (err instanceof ApiError) {
    switch (err.code) {
      case "robots_denied":      // 403
      case "url_blocked":        // 422 SSRF
      case "invalid_url":        // 422
      case "scraper_disabled":   // 503
      case "rate_limited":       // 429; respeta err.retryAfter si existe
        break;
      case "network_error":      // status 0: API caído o CORS mal configurado
        break;
    }
  }
}
```

Notas:

- `rate_limited` trae `Retry-After`; el API hoy solo expone `X-Request-ID` y
  `X-Process-Time-Ms` por CORS, así que `err.retryAfter` puede venir `undefined`
  en el navegador. Usa una espera fija (p. ej. 2 s) como respaldo.
- `network_error` suele significar API apagada o CORS mal configurado: revisa
  `NLP_CORS_ORIGINS` y la URL de `VITE_API_URL`.
- Códigos `validation_error` (422) incluyen `detail` con la lista de Pydantic.
- Los jobs **no** fallan por HTTP: si el rastreo falla, `status="error"` y el
  motivo en `job.error`; `pollJob` lo convierte en `ApiError` con
  `code: "scrape_job_error"` y `detail` = job completo.

---

## 6. Resumen de diferencias esperadas

| Tema | Antes (mock) | Ahora (API) |
| --- | --- | --- |
| Análisis | síncrono, `analyzeNewsText(...)` devolvía valor | **asíncrono**, devuelve `Promise<TextAnalysisResult>`; hay que `await`. |
| `dateAnalyzed` | texto formateado en español | ISO 8601 UTC; formatear en UI. |
| Motor | unión fija | `modelUsed` string con el nombre real; `meta.engine` (`bert_pair`/`multitask`/`lexicon`). |
| Scraping | simulado con `setTimeout`, artículos inventados | **job real**: `scanSite` (202) + `pollJob` (cada 1,5 s, 5 pasos). |
| Progreso | mensajes mock | `status`, `currentStep`, `totalSteps`, `message`, `articlesFoundCount`, más `articlesAnalyzedCount`/`steps`/`error`/`summary`. |
| Artículos | del dataset `SAMPLE_NEWS_SITES` | extraídos del sitio real (`NewsArticle` con `preAnalyzedResult`). |
| Presets | `NewsSitePreset` con logo/bandera/colores y `articles` mock | `SourcePreset` con los mismos campos de presentación (`flag`, `logoText`, `accentColor`, `category`), pero **sin** `articles`. |
| Métricas de modelos | constantes hardcodeadas 89 %… | `GET /v1/dashboard/models` (artefacto real, ratios 0–1) o vacío con `message`. |
| Corpus | constantes hardcodeadas | `GET /v1/dashboard/corpus` (CSV real, cacheado). |
| Fallos | nunca fallaba | `ApiError` tipado; estados UI de error/loading. |
| CORS | no aplicaba | `NLP_CORS_ORIGINS`; `credentials: false`. |
| API key | no existía | `VITE_API_KEY` opcional (solo demo; no para producción). |

---

## 7. Checklist de verificación

1. `http://localhost:8000/docs` abre y lista todos los endpoints.
2. `GET /v1/health` responde `status: "ok"` (o `"degraded"` con léxico forzado).
3. `SingleAnalyzer`: analizar un texto devuelve tarjetas con sentimiento,
   7 encuadres y sesgo cultural; el resultado persiste (`id` recuperable con
   `GET /v1/analyses/{id}`).
4. `WebsiteScraper`: al escanear un medio, el progreso pasa por 5 pasos
   (~1,5 s entre sondeos) y al final muestra el resumen con artículos reales.
5. Cancelar/cerrar el componente durante el polling no deja peticiones colgadas
   (AbortController).
6. `ModelEvaluation`: con `api/artifacts/evaluation.json` muestra métricas
   reales; sin el artefacto muestra el `message` y estado vacío.
7. `CorpusDashboard`: los datos vienen del CSV (`sourceFile` visible en la UI si
   quieres mostrarlo).
8. Errores: apagar el API y comprobar que la UI muestra «No se pudo conectar con
   el API» (o un mensaje equivalente) en vez de romperse.
9. Con `NLP_API_KEY` activa: la app envía `X-API-Key` y recibe 401 si falta.

---

## 8. Pendientes conocidos

- El API aún no filtra por `dateRange` en `/v1/sources/scan` (el mock tenía ese
  campo): se puede ignorar o filtrar en la UI.
- Los presets del API no traen `articles` (solo metadatos y presentación): los
  artículos salen de un escaneo real.
- `Retry-After` no está en `expose_headers` del CORS: para leerlo desde el
  navegador habría que agregarlo en `api/app/main.py` (propiedad del Lead).
- `modelUsed` ya no es una unión cerrada: si algún componente compara por
  igualdad con `"BETO-v2.1-Spanish"`, hay que actualizarlo.
