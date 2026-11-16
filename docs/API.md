# API — contrato de referencia

API HTTP del proyecto **Cultural Bias / migración venezolana**. Analiza
cobertura mediática de la migración venezolana en Colombia y México: sentimiento
(BETO), encuadres noticiosos (7 etiquetas), sesgo cultural (hipótesis
Colombia–México), ingesta de sitios de noticias, dashboard agregado y monitoreo.

- **Base URL local:** `http://localhost:8000`
- **Prefijo de negocio:** `/v1`
- **Formato:** JSON UTF-8. Los campos de request/response van en **camelCase**
  (los endpoints aceptan además snake_case en las peticiones, porque los modelos
  Pydantic usan `populate_by_name=True`).
- **Documentación interactiva:** `GET /docs` (Swagger UI), `GET /redoc`,
  `GET /openapi.json`.
- **Versión del contrato:** 1.0.0 (`meta.version`/`/v1/health`).

El contrato está implementado en `api/app/schemas.py` y en los routers de
`api/app/routers/`. Los tipos espejo para TypeScript están en
`integrations/frontend-api-client.ts` y en el frontend original
(`frontend-extract/src/types/index.ts`).

---

## 1. Convenciones

### 1.1 Cabeceras

| Cabecera | Dirección | Descripción |
| --- | --- | --- |
| `Content-Type: application/json` | request | Obligatoria cuando hay body. |
| `Accept: application/json` | request | Recomendada. |
| `X-API-Key: <clave>` | request | Autenticación opcional (ver 1.2). También se acepta `Authorization: Bearer <clave>`. |
| `X-Request-ID` | request/response | Si el cliente lo envía se respeta; si no, el API genera uno (`uuid4` corto). Vuelve siempre en la respuesta. |
| `X-Process-Time-Ms` | response | Tiempo de proceso del servidor en milisegundos. |
| `Retry-After` | response (429) | Segundos recomendados antes de reintentar. |

### 1.2 Autenticación (opcional)

La autenticación se activa solo si el servidor define `NLP_API_KEY`.

- Endpoints **exentos** incluso con API key activa: `GET /`, `GET /v1/health`,
  `GET /metrics`, `/docs`, `/redoc`, `/openapi.json`, `/favicon.ico`.
- El resto exige `X-API-Key: <clave>` (o `Authorization: Bearer <clave>`).
- Una clave ausente o distinta devuelve `401 unauthorized`.
- El CORS permite cualquier origen por defecto (`NLP_CORS_ORIGINS=["*"]`); para
  producción conviene restringirlo al dominio del frontend. Las variables de
  lista se definen en **JSON** (`["http://localhost:5173"]`), no como CSV.
- `/metrics` se deja sin clave a propósito para que Prometheus pueda hacer
  scraping: solo expone agregados, no datos de negocio.

### 1.3 Rate limit

- Por defecto `NLP_RATE_LIMIT_REQUESTS=120` peticiones por
  `NLP_RATE_LIMIT_WINDOW_SECONDS=60`, contadas por IP del cliente o por prefijo
  de API key si se envía.
- Al superarlo: `429 rate_limited` + cabecera `Retry-After`.
- Los endpoints exentos de autenticación (`/`, `/v1/health`, `/metrics`, docs)
  tampoco consumen cuota; las peticiones `OPTIONS` (preflight CORS) se ignoran.

### 1.4 Formato uniforme de error

Todos los errores de negocio devuelven el mismo sobre:

```json
{
  "error": {
    "code": "not_found",
    "message": "No existe el análisis analisis-123",
    "detail": null
  }
}
```

`detail` puede ser `null`, un objeto (p. ej. `{"url": "..."}`) o la lista de
errores de validación de Pydantic en `validation_error`.

### 1.5 Códigos HTTP usados

| Código | Significado | Cuándo |
| --- | --- | --- |
| `200` | OK | Petición correcta (también en jobs con `status="error"`: el error del job va en su cuerpo). |
| `202` | Accepted | `POST /v1/sources/scan` creó un job asíncrono. |
| `401` | Unauthorized | API key ausente o inválida (`unauthorized`). |
| `403` | Forbidden | `robots_denied`: robots.txt prohíbe el rastreo. |
| `404` | Not Found | Análisis/job inexistente (`not_found`) o página remota 404. |
| `422` | Unprocessable Entity | Body inválido (`validation_error`), texto inválido (`invalid_text`), lote grande (`batch_too_large`), URL inválida/bloqueada/extracción fallida. |
| `429` | Too Many Requests | Rate limit (`rate_limited`). |
| `500` | Internal Server Error | `internal_error`, `invalid_payload`. |
| `503` | Service Unavailable | Motor NLP (`engine_error`), scraper deshabilitado (`scraper_disabled`), corpus no disponible (`corpus_unavailable`), fallos del sitio remoto (`upstream_*`). |

---

## 2. Resumen de endpoints

| Método | Ruta | Auth | Respuesta | Descripción |
| --- | --- | --- | --- | --- |
| `GET` | `/` | exento | objeto | Información del servicio y mapa de endpoints. |
| `GET` | `/v1/health` | exento | `HealthResponse` | Estado, motor, modelos y base de datos. |
| `GET` | `/v1/models` | sí | `ModelsResponse` | Catálogo de modelos, etiquetas y umbrales. |
| `POST` | `/v1/analyze` | sí | `TextAnalysisResult` | Analiza un texto. |
| `POST` | `/v1/analyze/batch` | sí | `BatchAnalyzeResponse` | Analiza hasta 50 textos. |
| `GET` | `/v1/analyses` | sí | `AnalysesPage` | Historial paginado de análisis. |
| `GET` | `/v1/analyses/{analysis_id}` | sí | `TextAnalysisResult` | Recupera un análisis guardado. |
| `GET` | `/v1/sources/presets` | sí | `SourcePreset[]` | Medios de noticias preconfigurados. |
| `POST` | `/v1/sources/scan` | sí | `ScrapeAccepted` (202) | Lanza rastreo + análisis de un sitio. |
| `GET` | `/v1/sources/jobs` | sí | `ScrapeJobSummary[]` | Lista resumida de jobs de ingesta. |
| `GET` | `/v1/sources/jobs/{job_id}` | sí | `ScrapeJobResponse` | Progreso detallado de un job. |
| `POST` | `/v1/sources/analyze-url` | sí | `NewsArticle` | Extrae y analiza **una** noticia en línea. |
| `GET` | `/v1/dashboard/overview` | sí | `DashboardOverview` | Agregados generales del dashboard. |
| `GET` | `/v1/dashboard/timeseries` | sí | `TimeseriesResponse` | Serie diaria de análisis por sentimiento. |
| `GET` | `/v1/dashboard/corpus` | sí | `CorpusDashboard` | Estadísticas del CSV etiquetado. |
| `GET` | `/v1/dashboard/models` | sí | `ModelEvaluation` | Métricas de evaluación de modelos. |
| `GET` | `/v1/dashboard/recent` | sí | `AnalysisSummary[]` | Últimos análisis. |
| `GET` | `/v1/monitoring/stats` | sí | `MonitoringStats` | Estadísticas internas del servicio. |
| `GET` | `/metrics` | exento | texto Prometheus | Métricas para Prometheus. |

`/metrics` está exento de autenticación a propósito: Prometheus puede hacer
scraping sin configurar la API key.

---

## 3. Análisis de textos

### 3.1 `POST /v1/analyze`

Analiza un texto y **persiste** el resultado en SQLite (el `id` generado sirve
para consultarlo después con `GET /v1/analyses/{id}`).

#### Request

| Campo | Tipo | Obligatorio | Límites | Descripción |
| --- | --- | --- | --- | --- |
| `text` | string | sí | 1–20 000 caracteres, no solo espacios | Texto de la noticia o comentario. Se limpia de HTML, URLs y emojis antes de analizar. |
| `title` | string \| null | no | ≤ 500 | Titular. |
| `sourceUrl` | string \| null | no | ≤ 2 000 | URL de origen. **Se usa para inferir el país y el medio.** |
| `mediaName` | string \| null | no | ≤ 200 | Medio de comunicación. También se usa para inferir país/medio. |
| `country` | string \| null | no | `Colombia`, `México`, `Mexico`, `Internacional`, `Desconocido` | Si falta, se infiere de `sourceUrl`/`mediaName`. `Mexico` se normaliza a `México`. |
| `language` | string | no | por defecto `"es"` | Aceptado por compatibilidad; el análisis es en español. |

Ejemplo:

```bash
curl -s http://localhost:8000/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "text": "La ola de inseguridad en la frontera preocupa a los habitantes de Cúcuta. Las autoridades reportaron atracos y homicidios atribuidos a bandas criminales.",
    "title": "Crece la preocupación por seguridad en la frontera",
    "sourceUrl": "https://www.eltiempo.com/colombia/seguridad-frontera",
    "mediaName": "El Tiempo"
  }'
```

#### Response `200` — `TextAnalysisResult`

Ejemplo real (motor BETO; se abrevian `frames` a 2 de 7 y `highlightedTerms` a 3):

```json
{
  "id": "analisis-4b3136b279d14fc2",
  "text": "La ola de inseguridad en la frontera preocupa a los habitantes de Cúcuta. Las autoridades reportaron atracos y homicidios atribuidos a bandas criminales.",
  "title": "Crece la preocupación por seguridad en la frontera",
  "sourceUrl": "https://www.eltiempo.com/colombia/seguridad-frontera",
  "mediaName": "El Tiempo",
  "country": "Colombia",
  "dateAnalyzed": "2026-11-09T18:58:59.572713Z",
  "sentiment": {
    "prediction": "Negativo",
    "confidence": 41.6,
    "scores": { "negativo": 41.6, "neutro": 38.4, "positivo": 20.0 },
    "explanation": "Predomina una tonalidad de alarma o alerta social, con léxico asociado a problemáticas, presión institucional o tensiones."
  },
  "frames": [
    {
      "id": "otros",
      "label": "Otros",
      "score": 53.6,
      "isActive": true,
      "description": "Derechos humanos, cooperación internacional (ONU, ACNUR) y vulnerabilidad.",
      "associatedKeywords": ["derechos humanos", "ACNUR", "niñez", "vulnerabilidad"]
    },
    {
      "id": "empleo_economia",
      "label": "Empleo y economía",
      "score": 51.6,
      "isActive": true,
      "description": "Fuerza laboral, oportunidades de trabajo, aporte económico y comercio.",
      "associatedKeywords": ["trabajo", "empleo", "economía", "productividad", "empresas"]
    }
  ],
  "culturalBias": {
    "detectedBias": "Neutro / Institucional",
    "colombiaAlignmentScore": 40.6,
    "mexicoAlignmentScore": 40.8,
    "reasoning": "La cobertura equilibra factores institucionales, de tránsito y de integración sin una inclinación marcada hacia la seguridad ni hacia la instrumentalización laboral.",
    "highlightedTerms": [
      { "term": "darién", "biasType": "colombia", "weight": 4.5 },
      { "term": "regularización", "biasType": "positive", "weight": 4.4 },
      { "term": "inseguridad", "biasType": "colombia", "weight": 4.2 }
    ]
  },
  "tokensCount": 66,
  "readingTimeSeconds": 20,
  "modelUsed": "BETO-migra-ve (sentimiento + encuadres)",
  "meta": {
    "engine": "bert_pair",
    "requestedEngine": "auto",
    "degraded": false,
    "modelVersion": "1.0",
    "sentimentModel": "beto-sentimiento",
    "framesModel": "beto-encuadres",
    "preprocessing": "bert-tokenizer",
    "latencyMs": 381.48,
    "truncated": false,
    "warnings": ["Baja confianza del clasificador de sentimiento."],
    "persisted": true,
    "source": "api",
    "jobId": null
  }
}
```

> `isActive` depende de `api/artifacts/thresholds.json`: con los umbrales
> optimizados actuales (`seguridad: 0.2`, `transito_migratorio: 0.2`,
> `politica_migratoria: 0.45`, …) un encuadre con `score` 33.7 ya puede estar
> activo. Si no existe `thresholds.json` se usa `NLP_FRAME_THRESHOLD` (0.5).

##### Detalle de `TextAnalysisResult`

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `id` | string | `analisis-` + 16 hex. Clave para el historial. |
| `text` | string | Texto **ya limpio** (HTML/URLs/emoji fuera). Puede ser más corto que el enviado. |
| `title` | string \| null | Titular recibido. |
| `sourceUrl` | string \| null | URL recibida. |
| `mediaName` | string \| null | Medio recibido o inferido del dominio (catálogo de medios conocidos). |
| `country` | string | `Colombia` \| `México` \| `Internacional` \| `Desconocido`. |
| `dateAnalyzed` | string ISO 8601 | UTC, con microsegundos y sufijo `Z`. |
| `sentiment` | objeto | Ver abajo. |
| `frames` | array (7) | Siempre los 7 encuadres, **ordenados por `score` descendente**. |
| `culturalBias` | objeto | Ver abajo. |
| `tokensCount` | int | Palabras del texto limpio (`\w`+). |
| `readingTimeSeconds` | int | `max(5, ceil(palabras / 200 * 60))`. |
| `modelUsed` | string | Nombre legible del motor: `BETO-migra-ve (sentimiento + encuadres)`, `BETO-migra-ve multitarea (sentimiento + encuadres)` o `léxico-MigraVenezuela (baseline)`. |
| `meta` | objeto | Diagnóstico (ver abajo). |

`sentiment`:

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `prediction` | `"Negativo"` \| `"Neutro"` \| `"Positivo"` | Clase ganadora. |
| `confidence` | number 0–100 | Porcentaje de la clase ganadora (igual al score correspondiente). |
| `scores.negativo` / `.neutro` / `.positivo` | number | Porcentajes que **suman exactamente 100.0** (±0.1 por redondeo). |
| `explanation` | string | Explicación fija en español de la clase. |

`frames[]`:

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `id` | string | `acceso_servicios`, `transito_migratorio`, `seguridad`, `integracion_social`, `politica_migratoria`, `empleo_economia`, `otros`. |
| `label` | string | Etiqueta humana (`"Acceso a servicios"`, …). |
| `score` | number 0–100 | Probabilidad × 100, una décima. |
| `isActive` | boolean | `score/100 >= umbral` (umbral de `artifacts/thresholds.json` o `NLP_FRAME_THRESHOLD`, por defecto 0.5). |
| `description` | string | Descripción del encuadre. |
| `associatedKeywords` | string[] | Palabras clave del catálogo. |

`culturalBias`:

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `detectedBias` | string | `Colombia (Enfoque Punitivo / Seguridad)`, `México (Enfoque Laboral / Tránsito)` o `Neutro / Institucional`. |
| `colombiaAlignmentScore` | number 0–100 | Afinidad con el patrón colombiano (pesos sobre los 7 encuadres). |
| `mexicoAlignmentScore` | number 0–100 | Afinidad con el patrón mexicano. |
| `reasoning` | string | Justificación en español. Se asigna sesgo cuando un score supera al otro por ≥ 8 puntos. |
| `highlightedTerms[]` | array (≤ 8) | Términos del texto detectados en el léxico de sesgo. `biasType`: `colombia` \| `mexico` \| `negative` \| `positive`; `weight` numérico. |

`meta`:

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `engine` | string | `bert_pair`, `multitask` o `lexicon`. |
| `requestedEngine` | string | `NLP_ENGINE` configurado (`auto`, …). |
| `degraded` | boolean | `true` si se pidió un motor y se cayó al léxico. |
| `modelVersion` | string | Versión del motor. |
| `sentimentModel` / `framesModel` | string | Nombres de los modelos BETO cargados (vacío en léxico). |
| `preprocessing` | string | `bert-tokenizer`, `lexicon`, etc. |
| `latencyMs` | number | Latencia de la inferencia (sin red). |
| `truncated` | boolean | El texto superó `NLP_MAX_LENGTH` tokens y se truncó. |
| `warnings` | string[] | Avisos: texto corto (< 30 palabras), baja confianza (< 0.45), truncado, motor degradado. |
| `persisted` | boolean | `false` si no se pudo guardar en SQLite. |
| `source` | string | `api` o `scraper`. |
| `jobId` | string \| null | Job de ingesta que originó el análisis, si aplica. |

> **Nota de comportamiento:** si el texto limpio supera `NLP_MAX_TEXT_CHARS`
> (20 000 por defecto) se recorta; el campo `text` de la respuesta es el texto
> recortado y `meta.truncated` indica el truncado por tokens del modelo.

Códigos: `200`, `401`, `422` (`validation_error`, `invalid_text`),
`429`, `503` (`engine_error`), `500`.

---

### 3.2 `POST /v1/analyze/batch`

Analiza varios textos en una sola petición (secuencial, mismo motor).

#### Request

| Campo | Tipo | Obligatorio | Descripción |
| --- | --- | --- | --- |
| `items` | `AnalyzeRequest[]` | sí | 1–50 elementos (`NLP_MAX_BATCH_ITEMS`, tope duro 50). |

```bash
curl -s http://localhost:8000/v1/analyze/batch \
  -H "Content-Type: application/json" \
  -d '{"items":[
        {"text":"La inseguridad preocupa a los ciudadanos.","title":"Nota 1"},
        {"text":"Los migrantes encuentran trabajo en la industria.","mediaName":"Milenio"}
      ]}'
```

#### Response `200` — `BatchAnalyzeResponse`

```json
{
  "count": 2,
  "results": [
    { "id": "analisis-…", "text": "La inseguridad preocupa a los ciudadanos.", "sentiment": { "prediction": "Negativo" } },
    { "id": "analisis-…", "text": "Los migrantes encuentran trabajo en la industria.", "sentiment": { "prediction": "Positivo" } }
  ]
}
```

(ejemplo abreviado: cada elemento de `results` es un `TextAnalysisResult` completo).

Códigos: `200`; `422` (`batch_too_large` si supera `NLP_MAX_BATCH_ITEMS`,
`invalid_text`, `validation_error`); `401`; `429`; `503` (`engine_error`).

---

### 3.3 `GET /v1/analyses`

Historial paginado, ordenado por fecha descendente.

| Query param | Tipo | Default | Descripción |
| --- | --- | --- | --- |
| `limit` | int 1–100 | 20 | Tamaño de página. |
| `offset` | int ≥ 0 | 0 | Desplazamiento. |
| `sentiment` | string | — | `Negativo`, `Neutro` o `Positivo`. |
| `country` | string | — | Filtro exacto por país (p. ej. `Colombia`). |
| `source` | string | — | Origen (`api`, `scraper`). |
| `since` | ISO 8601 datetime | — | Solo análisis creados desde esa fecha. |

```bash
curl -s "http://localhost:8000/v1/analyses?limit=2&sentiment=Negativo"
```

Response `200` — `AnalysesPage`:

```json
{
  "total": 3,
  "limit": 2,
  "offset": 0,
  "items": [
    {
      "id": "analisis-d282d5899e9d4ca7",
      "createdAt": "2026-11-09T18:59:00.223702Z",
      "title": "Mano de obra migrante en la industria",
      "mediaName": "Milenio",
      "country": "México",
      "sentiment": "Negativo",
      "confidence": 57.0,
      "source": "api",
      "engine": "bert_pair",
      "latencyMs": 254.79
    }
  ]
}
```

`AnalysisSummary`: `id`, `createdAt` (ISO 8601), `title`, `mediaName`,
`country`, `sentiment`, `confidence`, `source`, `engine`, `latencyMs`.

Códigos: `200`, `401`, `422` (`validation_error` en query), `429`.

---

### 3.4 `GET /v1/analyses/{analysis_id}`

Devuelve el `TextAnalysisResult` completo guardado (mismo shape que
`POST /v1/analyze`), sin las claves internas `_truncated`/`_textHash`.

```bash
curl -s http://localhost:8000/v1/analyses/analisis-d282d5899e9d4ca7
```

Códigos: `200`, `401`, `404` (`not_found`: `"No existe el análisis …"`), `429`.

---

## 4. Ingesta de noticias (`/v1/sources`)

Flujo típico: `presets` → `scan` (202) → polling de `jobs/{id}` cada 1,5 s →
`summary` al completar. El progreso persiste en SQLite (`scrape_jobs`), así que
sobrevive a reinicios del API.

### 4.1 `GET /v1/sources/presets`

Catálogo de medios conocidos (`site_catalog.KNOWN_SITES`): 8 medios de Colombia
y México. Response `200` — `SourcePreset[]`:

```json
[
  {
    "id": "el-tiempo",
    "name": "El Tiempo",
    "domain": "eltiempo.com",
    "country": "Colombia",
    "category": "Prensa Escrita",
    "description": "Diario de mayor circulación en Colombia. Cobertura nacional con énfasis en políticas públicas, frontera y convivencia urbana.",
    "flag": "🇨🇴",
    "logoText": "EL TIEMPO",
    "accentColor": "#1e40af"
  }
]
```

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `id` | string | Identificador estable (`el-tiempo`, `semana`, `el-espectador`, `el-universal-mx`, `milenio`, `reforma`, `el-heraldo-co`, `la-jornada`). |
| `name` | string | Nombre del medio. |
| `domain` | string | Dominio (sin `www.`). |
| `country` | string | `Colombia` \| `México`. |
| `category` | string | `Prensa Escrita` \| `Medio Digital` (mismas cadenas que el tipo `NewsSitePreset` del frontend). |
| `description` | string | Texto descriptivo. |
| `flag` | string | Emoji de bandera del país (`🇨🇴`/`🇲🇽`). |
| `logoText` | string | Texto corto para el logo (p. ej. `"EL TIEMPO"`). |
| `accentColor` | string | Color de acento en hex (p. ej. `"#1e40af"`). |

> El único campo de `NewsSitePreset` que el API **no** envía es `articles`: los
> artículos se obtienen de un escaneo real (`POST /v1/sources/scan`) o de
> `POST /v1/sources/analyze-url`.

### 4.2 `POST /v1/sources/scan` → `202`

Crea un job de rastreo + extracción + análisis. Devuelve de inmediato; el trabajo
corre en un hilo del servidor.

#### Request — `ScrapeRequest`

| Campo | Tipo | Default | Descripción |
| --- | --- | --- | --- |
| `url` | string 3–2000 | — | URL del sitio. Si no trae esquema se asume `https://`. |
| `maxArticles` | int 1–10 | 4 | Máximo de noticias; se recorta a `min(maxArticles, NLP_SCRAPER_MAX_ARTICLES, 10)`. |
| `keywords` | string[] | `[]` | Filtro de migración; vacío = palabras clave del servidor (`NLP_SCRAPER_KEYWORDS`). |
| `country` | string \| null | `null` | Fuerza el país de las noticias; si falta se infiere. |
| `respectRobots` | boolean \| null | `null` | `null` = usar `NLP_SCRAPER_RESPECT_ROBOTS`. |
| `analyze` | boolean | `true` | Si es `false` solo extrae artículos, sin análisis NLP. |

```bash
curl -s -X POST http://localhost:8000/v1/sources/scan \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.eltiempo.com","maxArticles":4,"keywords":["migración","venezolanos"]}'
```

#### Response `202` — `ScrapeAccepted`

```json
{
  "jobId": "job-3f2b9c1a77de",
  "status": "queued",
  "statusUrl": "/v1/sources/jobs/job-3f2b9c1a77de",
  "pollAfterSeconds": 1.5
}
```

Códigos: `202`; `401`; `422` (`validation_error`, `invalid_max_articles`);
`429`; `503` (`scraper_disabled`).

### 4.3 `GET /v1/sources/jobs/{job_id}`

Estado detallado del job. Response `200` — `ScrapeJobResponse`:

```json
{
  "jobId": "job-3f2b9c1a77de",
  "status": "analyzing",
  "currentStep": 4,
  "totalSteps": 5,
  "message": "Analizando 3 noticias con el motor NLP",
  "articlesFoundCount": 3,
  "articlesAnalyzedCount": 2,
  "createdAt": "2026-11-09T19:10:00.123000Z",
  "updatedAt": "2026-11-09T19:10:04.456000Z",
  "error": null,
  "steps": [
    { "step": 1, "totalSteps": 5, "message": "Conectando con eltiempo.com y verificando robots.txt", "at": "2026-11-09T19:10:00.130000Z" },
    { "step": 2, "totalSteps": 5, "message": "Buscando noticias de migración en eltiempo.com (feeds, sitemaps y portada)", "at": "2026-11-09T19:10:01.240000Z" },
    { "step": 3, "totalSteps": 5, "message": "Limpiando el contenido de 3 noticias encontradas", "at": "2026-11-09T19:10:02.301000Z" },
    { "step": 4, "totalSteps": 5, "message": "Analizando 3 noticias con el motor NLP", "at": "2026-11-09T19:10:03.412000Z" }
  ],
  "summary": null
}
```

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `jobId` | string | `job-` + 12 hex. |
| `status` | string | `idle` \| `queued` \| `connecting` \| `crawling` \| `cleaning` \| `analyzing` \| `completed` \| `error`. |
| `currentStep` | int | Paso actual (0–5). |
| `totalSteps` | int | Siempre 5. |
| `message` | string | Mensaje legible del paso. |
| `articlesFoundCount` | int | Noticias descubiertas. |
| `articlesAnalyzedCount` | int | Noticias analizadas. |
| `createdAt` / `updatedAt` | ISO 8601 \| null | Marcas de tiempo. |
| `error` | string \| null | Motivo si `status="error"`. |
| `steps[]` | `JobStep[]` | Histórico de pasos: `{step, totalSteps, message, at}`. |
| `summary` | `ScrapedSiteSummary` \| null | Resumen agregado cuando `status="completed"`. |

Los 5 pasos del contrato del frontend son: `connecting` (URL + robots.txt),
`crawling` (portada, RSS/Atom, sitemaps), `cleaning` (extracción del cuerpo),
`analyzing` (NLP) y `completed`/`error`.

> Si el job termina con `status="error"`, el `GET` sigue devolviendo `200` y el
> motivo viaja en `error`. No hay 4xx/5xx por fallos de red durante el rastreo.

Códigos: `200`, `401`, `404` (`not_found`), `429`.

### 4.4 `GET /v1/sources/jobs`

Lista resumida de jobs (orden `createdAt` descendente).

| Query param | Tipo | Default | Descripción |
| --- | --- | --- | --- |
| `limit` | int 1–100 | 20 | Máximo de jobs. |

Response `200` — `ScrapeJobSummary[]`:

```json
[
  {
    "id": "job-3f2b9c1a77de",
    "url": "https://www.eltiempo.com",
    "domain": "eltiempo.com",
    "status": "completed",
    "currentStep": 5,
    "totalSteps": 5,
    "message": "Resumen generado: 3 noticias analizadas de El Tiempo",
    "articlesFound": 3,
    "articlesAnalyzed": 3,
    "error": null,
    "createdAt": "2026-11-09T19:10:00.123000Z",
    "updatedAt": "2026-11-09T19:10:06.789000Z"
  }
]
```

> Ojo: en la lista el id se llama `id` (no `jobId`) y los contadores son
> `articlesFound` / `articlesAnalyzed` (sin sufijo `Count`), a diferencia de
> `ScrapeJobResponse`.

Códigos: `200`, `401`, `422`, `429`.

### 4.5 `POST /v1/sources/analyze-url`

Descarga **una** página de noticia, extrae su texto principal y la analiza en
línea. Body: mismo `ScrapeRequest` de `/scan`, pero solo se usan `url`,
`country` y `respectRobots` (los demás campos se ignoran).

```bash
curl -s -X POST http://localhost:8000/v1/sources/analyze-url \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.eltiempo.com/colombia/seguridad-frontera"}'
```

Response `200` — `NewsArticle` (con `preAnalyzedResult`):

```json
{
  "id": "noticia-0e3ab9f1c2d4",
  "title": "Crece la preocupación por seguridad en la frontera",
  "snippet": "Las autoridades reportaron atracos y homicidios…",
  "fullText": "La ola de inseguridad en la frontera preocupa a los habitantes de Cúcuta…",
  "author": "Redacción El Tiempo",
  "date": "2026-11-08",
  "media": "El Tiempo",
  "country": "Colombia",
  "url": "https://www.eltiempo.com/colombia/seguridad-frontera",
  "category": "Seguridad",
  "preAnalyzedResult": { "id": "analisis-…" }
}
```

`NewsArticle`:

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `id` | string | `noticia-` + 12 hex (hash de la URL canónica). |
| `title` | string | Titular extraído. |
| `snippet` | string | Resumen / meta descripción. |
| `fullText` | string | Cuerpo limpio de la noticia. |
| `author` | string | Autor si se detecta. |
| `date` | string | Fecha normalizada `YYYY-MM-DD`. Se toma de la página (`article:published_time`, JSON-LD `datePublished` o `<time datetime>`); en escaneos de sitio, si la página no declara fecha se usa el `pubDate` del feed/sitemap como respaldo. Vacía si no se detecta (en `analyze-url` suelto no hay respaldo de feed). |
| `media` | string | Nombre del medio (catálogo o dominio). |
| `country` | string | País inferido o forzado. |
| `url` | string | URL canónica. |
| `category` | string | Sección declarada por la página (`article:section` / JSON-LD `articleSection`) o del request; cadena vacía si no hay. |
| `preAnalyzedResult` | `TextAnalysisResult` \| null | Análisis completo (mismo contrato de `/v1/analyze`; `meta.source="scraper"`). |

Códigos: `200`; `401`; `403` (`robots_denied`); `404` (`not_found` si la página
remota devuelve 404); `422` (`invalid_url`, `url_blocked` — SSRF a IP
privada/loopback/link-local/metadata, `unresolvable_host`, `extraction_failed`
—cuerpo con menos de 80 palabras o página sin texto—, `invalid_content`,
`invalid_text`, `validation_error`); `429`; `503` (`scraper_disabled`,
`engine_error`, `upstream_error`, `upstream_unavailable`, `upstream_timeout`,
`response_too_large`, `too_many_redirects`, `scraper_error`).

### 4.6 `ScrapedSiteSummary` (resumen del job completado)

Se entrega en `ScrapeJobResponse.summary` y coincide con el tipo homónimo del
frontend (`ScrapedSiteSummary`), más `generatedAt`.

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `siteName` | string | Nombre del sitio. |
| `domain` | string | Dominio normalizado. |
| `country` | string | País del resumen (`Colombia` \| `México` \| `Internacional` \| `Desconocido`). |
| `totalAnalyzed` | int | Noticias analizadas. |
| `averageSentiment` | `{negativo, neutro, positivo}` | Promedio en porcentaje (0–100) de los scores de sentimiento de los artículos analizados; puede no sumar exactamente 100 por redondeo. |
| `topFrames` | `{frame, percentage}[]` | Porcentaje medio de cada encuadre, ordenado de mayor a menor. |
| `biasTendency` | string | Texto de tendencia de sesgo según el encuadre dominante (o el país si no hay análisis). Valores posibles en la tabla siguiente. |
| `hypothesisMatch` | string | `Confirmada (Sesgo esperado)` \| `Parcial` \| `No concluyente` (regla abajo). |
| `articles` | `NewsArticle[]` | Artículos con `preAnalyzedResult`. |
| `generatedAt` | ISO 8601 \| null | Momento de generación (solo lo agrega el API). |

Valores de `biasTendency` según el encuadre dominante:

| Encuadre dominante | `biasTendency` |
| --- | --- |
| `seguridad` | `Enfoque Punitivo / Seguridad y Alerta Ciudadana` |
| `politica_migratoria` | `Enfoque Institucional / Política Migratoria` |
| `empleo_economia`, `transito_migratorio` | `Enfoque de Integración Laboral y Tránsito Migratorio` |
| `integracion_social` | `Enfoque de Integración Social y Convivencia` |
| `acceso_servicios` | `Enfoque de Acceso a Servicios y Derechos` |
| `otros` | `Enfoque de Derechos Humanos y Cooperación` |
| sin artículos analizados | Texto esperado del país si se conoce —Colombia: `Enfoque Punitivo / Seguridad y Alerta Ciudadana`; México: `Enfoque de Integración Laboral y Tránsito Migratorio`—; si el país es desconocido: `Enfoque Neutro / Informativo Institucional` |

`hypothesisMatch` se calcula con la hipótesis del proyecto:

- `Confirmada (Sesgo esperado)`: el encuadre dominante pertenece a los esperados
  del país —Colombia: `seguridad`, `politica_migratoria`; México:
  `empleo_economia`, `transito_migratorio`;
- `Parcial`: alguno de esos encuadres aparece en el top 3 pero no es el dominante;
- `No concluyente`: no hay encuadre dominante, país desconocido o no coincide.

Ejemplo (abreviado a un artículo y dos encuadres):

```json
{
  "siteName": "El Tiempo",
  "domain": "eltiempo.com",
  "country": "Colombia",
  "totalAnalyzed": 3,
  "averageSentiment": { "negativo": 44.1, "neutro": 33.2, "positivo": 22.7 },
  "topFrames": [
    { "frame": "Seguridad", "percentage": 61.3 },
    { "frame": "Política migratoria", "percentage": 48.9 }
  ],
  "biasTendency": "Enfoque Punitivo / Seguridad y Alerta Ciudadana",
  "hypothesisMatch": "Confirmada (Sesgo esperado)",
  "articles": [
    {
      "id": "noticia-0e3ab9f1c2d4",
      "title": "Crece la preocupación por seguridad en la frontera",
      "snippet": "…",
      "fullText": "…",
      "author": "Redacción El Tiempo",
      "date": "2026-11-08",
      "media": "El Tiempo",
      "country": "Colombia",
      "url": "https://www.eltiempo.com/colombia/seguridad-frontera",
      "category": "Seguridad",
      "preAnalyzedResult": { "id": "analisis-…" }
    }
  ],
  "generatedAt": "2026-11-09T19:10:06.789000Z"
}
```

---

## 5. Dashboard (`/v1/dashboard`)

Todos los endpoints son de solo lectura y toleran bases vacías (devuelven ceros
en lugar de error). Están pensados para reemplazar los datos hardcodeados de
`frontend-extract/src/data/modelMetrics.ts`.

### 5.1 `GET /v1/dashboard/overview`

Agregados sobre los análisis guardados en SQLite. Response `200` —
`DashboardOverview`:

```json
{
  "generatedAt": "2026-11-09T19:04:30.077551Z",
  "totalAnalyses": 3,
  "analysesToday": 3,
  "analysesLast7d": 3,
  "avgConfidence": 42.7,
  "sentiment": { "negativo": 1, "neutro": 1, "positivo": 1 },
  "sentimentPct": { "negativo": 33.4, "neutro": 33.3, "positivo": 33.3 },
  "topFrames": [
    { "frame": "Empleo y economía", "percentage": 66.7 },
    { "frame": "Tránsito migratorio", "percentage": 66.7 },
    { "frame": "Política migratoria", "percentage": 33.3 },
    { "frame": "Seguridad", "percentage": 33.3 }
  ],
  "countries": [
    { "country": "Colombia", "count": 2, "sentiment": { "negativo": 1, "neutro": 1, "positivo": 0 } }
  ],
  "media": [
    { "media": "El Tiempo", "count": 1, "sentiment": { "negativo": 1, "neutro": 0, "positivo": 0 } }
  ],
  "engines": [{ "engine": "lexicon", "count": 3 }],
  "latencyMs": { "count": 3, "mean": 1.54, "p50": 1.6, "p95": 1.6, "p99": 1.6 },
  "scrapeJobs": { "total": 0, "completed": 0, "error": 0, "running": 0 },
  "uptimeSeconds": 0.2,
  "engine": "lexicon",
  "degraded": false
}
```

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `generatedAt` | ISO 8601 | Momento de cálculo. |
| `totalAnalyses` | int | Total de análisis guardados. |
| `analysesToday` | int | Análisis desde las 00:00 UTC. |
| `analysesLast7d` | int | Análisis de los últimos 7 días. |
| `avgConfidence` | number | Confianza media (0–100), una décima. |
| `sentiment` | counts | Conteos por sentimiento. |
| `sentimentPct` | percentages | Porcentajes que suman 100 (o ceros). |
| `topFrames` | `FrameTally[]` | **Máximo 5** encuadres activos más frecuentes (porcentaje sobre análisis totales). |
| `countries` | `CountryCount[]` | Hasta 10 países con desglose de sentimiento. |
| `media` | `MediaCount[]` | Hasta 10 medios con desglose de sentimiento. |
| `engines` | `EngineCount[]` | Análisis por motor. |
| `latencyMs` | `LatencyStats` | `count`, `mean`, `p50`, `p95`, `p99` de la latencia de análisis. |
| `scrapeJobs` | `ScrapeJobStats` | `total`, `completed`, `error`, `running`. |
| `uptimeSeconds` | number | Segundos desde el arranque. |
| `engine` | string | Motor seleccionado. |
| `degraded` | boolean | Motor degradado. |

Códigos: `200`, `401`, `429`.

### 5.2 `GET /v1/dashboard/timeseries`

| Query param | Tipo | Default | Descripción |
| --- | --- | --- | --- |
| `days` | int 1–365 | 30 | Ventana en días. |

Response `200` — `TimeseriesResponse`:

```json
{
  "days": 30,
  "items": [
    { "date": "2026-11-09", "total": 3, "negativo": 1, "neutro": 1, "positivo": 1 }
  ]
}
```

Solo se incluyen días con datos; `date` es `YYYY-MM-DD`. Códigos: `200`, `401`,
`422`, `429`.

### 5.3 `GET /v1/dashboard/corpus`

Estadísticas del CSV etiquetado del corpus
(`NLP_CORPUS_CSV_PATH`, por defecto
`Data/dataset_migracion_venezolana_labeled.csv`). El resultado se cachea por
ruta + `mtime` + tamaño.

Response `200` — `CorpusDashboard`:

```json
{
  "generatedAt": "2026-11-09T19:04:30.201821Z",
  "sourceFile": "…\\Data\\dataset_migracion_venezolana_labeled.csv",
  "totalArticles": 156,
  "mediaCount": 2,
  "dateRange": { "from": "2018-07-25", "to": "2026-09-04" },
  "sentimentBreakdown": { "negativo": 28.2, "neutro": 50.6, "positivo": 21.2 },
  "frameBreakdown": [
    { "frame": "Política migratoria", "percentage": 62.8 },
    { "frame": "Tránsito migratorio", "percentage": 34.0 }
  ],
  "countries": [
    {
      "country": "Colombia",
      "totalArticles": 77,
      "sentimentBreakdown": { "negativo": 20.8, "neutro": 44.1, "positivo": 35.1 },
      "frameBreakdown": [
        { "frame": "Política migratoria", "percentage": 70.1 },
        { "frame": "Empleo y economía", "percentage": 32.5 }
      ],
      "media": ["Semana"]
    }
  ],
  "monthlyVolume": [
    { "month": "2018-07", "total": 1, "negativo": 1, "neutro": 0, "positivo": 0 }
  ]
}
```

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `generatedAt` | ISO 8601 | Momento del cálculo. |
| `sourceFile` | string | Ruta absoluta del CSV usado. |
| `totalArticles` | int | Filas del CSV con cuerpo. |
| `mediaCount` | int | Medios distintos. |
| `dateRange` | `{from, to}` | Rango de fechas (`YYYY-MM-DD`, vacío si no hay fechas válidas). |
| `sentimentBreakdown` | percentages | Porcentajes por sentimiento (suman 100). |
| `frameBreakdown` | `FrameTally[]` | % de artículos con cada encuadre marcado (7 filas). |
| `countries[]` | `CorpusCountryStats[]` | Desglose por país: `country`, `totalArticles`, `sentimentBreakdown`, `frameBreakdown`, `media[]`. |
| `monthlyVolume[]` | `{month, total, negativo, neutro, positivo}[]` | Volumen por mes `YYYY-MM`. |

Códigos: `200`, `401`, `429`, `503` (`corpus_unavailable` si falta el CSV o no
tiene la columna `sentimiento`).

### 5.4 `GET /v1/dashboard/models`

Métricas reales de evaluación leídas de `api/artifacts/evaluation.json`
(generado por `api/scripts/evaluate_models.py`). Si el artefacto no existe,
responde **200** con `available=false` y un `message` explicativo.

Response `200` — `ModelEvaluation` (con artefacto real actual, `sampleSize=156`):

```json
{
  "generatedAt": "2026-11-09T19:02:51.743193Z",
  "sampleSize": 156,
  "engine": "bert_pair",
  "models": [
    {
      "modelName": "BETO-migra-ve (sentimiento + encuadres)",
      "architecture": "BERT base español (BETO) afinado · clasificador de 3 clases de sentimiento",
      "role": "sentiment",
      "accuracy": 0.7885,
      "precision": 0.7679,
      "recall": 0.7919,
      "f1Score": 0.7768,
      "samples": 156,
      "isBest": true
    }
  ],
  "sentiment": {
    "accuracy": 0.7885,
    "macroF1": 0.7768,
    "macroPrecision": 0.7679,
    "macroRecall": 0.7919,
    "perClass": {
      "Negativo": { "precision": 0.7556, "recall": 0.7727, "f1": 0.764, "support": 44 }
    },
    "confusionMatrix": { "labels": ["Negativo", "Neutro", "Positivo"], "matrix": [[34, 7, 3], [7, 62, 10], [4, 2, 27]] },
    "samples": 156
  },
  "frames": [
    {
      "frame": "Acceso a servicios",
      "frameId": "acceso_servicios",
      "precision": 0.5556,
      "recall": 0.6667,
      "f1": 0.6061,
      "support": 45,
      "threshold": 0.5
    }
  ],
  "confusionMatrix": { "labels": ["Negativo", "Neutro", "Positivo"], "matrix": [[34, 7, 3], [7, 62, 10], [4, 2, 27]] },
  "thresholds": { "seguridad": 0.2 },
  "available": true,
  "message": "Evaluación real sobre 156 artículos del corpus etiquetado con texto crudo (Cuerpo). …"
}
```

> **Unidades:** el API devuelve el artefacto **tal cual lo escribe**
> `api/scripts/evaluate_models.py`; la versión actual usa **ratios 0–1** para
> `accuracy`, `precision`, `recall`, `f1Score`, `f1` y los `thresholds`. El
> frontend simulado esperaba porcentajes 0–100: la guía de `docs/FRONTEND.md`
> incluye un adaptador que multiplica por 100 cuando el valor es ≤ 1.
> `sentiment` es un objeto libre (el artefacto puede traer más claves).
>
> **Alcance real (transparencia):** la evaluación actual se hizo sobre los
> **156 artículos etiquetados** de `Data/dataset_migracion_venezolana_labeled.csv`
> (79 Neutro, 44 Negativo, 33 Positivo; 77 Colombia, 79 México), **no** sobre
> 1.420: ese número y las métricas de la maqueta del front (`modelMetrics.ts`)
> son ficticios. Sentimiento: accuracy ≈ 0.789 y macro-F1 ≈ 0.777; encuadres con
> F1 variable (0.14–0.82) según la clase. Como no se conservó el split de
> entrenamiento, **puede haber solapamiento entre evaluación y entrenamiento**:
> las cifras son un indicador interno, no un benchmark independiente. El front
> debe reemplazar `modelMetrics.ts` por `GET /v1/dashboard/models`.

Sin artefacto (caso de un clon recién descargado):

```json
{
  "generatedAt": null,
  "sampleSize": 0,
  "engine": "",
  "models": [],
  "sentiment": {},
  "frames": [],
  "confusionMatrix": null,
  "thresholds": {},
  "available": false,
  "message": "No hay artefacto de evaluación en …\\api\\artifacts\\evaluation.json. Ejecuta la evaluación de modelos (api/scripts/evaluate_models.py) para generarlo."
}
```

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `generatedAt` | ISO 8601 \| null | Fecha de la evaluación. |
| `sampleSize` | int | Muestra evaluada. |
| `engine` | string | Motor evaluado. |
| `models[]` | `ModelMetric[]` | Benchmark de modelos (`modelName`, `architecture`, `role`, `accuracy`, `precision`, `recall`, `f1Score`, `samples`, `isBest`). |
| `sentiment` | objeto libre | Métricas de sentimiento del artefacto (accuracy, macroF1, perClass, confusionMatrix…). |
| `frames[]` | `FrameEvaluation[]` | P/R/F1 por encuadre, `support`, `threshold`. |
| `confusionMatrix` | `{labels, matrix}` \| null | Matriz real×predicho. |
| `thresholds` | `{frame_id: float}` | Umbrales óptimos. |
| `available` | boolean | `false` si no hay artefacto válido. |
| `message` | string | Mensaje legible. |

Códigos: `200`, `401`, `429`.

### 5.5 `GET /v1/dashboard/recent`

| Query param | Tipo | Default | Descripción |
| --- | --- | --- | --- |
| `limit` | int 1–100 | 20 | Análisis a devolver. |

Response `200` — `AnalysisSummary[]` (mismo objeto que `items` de
`/v1/analyses`). Códigos: `200`, `401`, `422`, `429`.

---

## 6. Salud, modelos y monitoreo

### 6.1 `GET /v1/health`

No requiere API key. Response `200` (o `degraded` en `status`) — `HealthResponse`:

```json
{
  "status": "ok",
  "version": "1.0.0",
  "environment": "dev",
  "uptimeSeconds": 1.4,
  "startedAt": "2026-11-09T18:58:58.883824Z",
  "engine": { "requested": "bert_pair", "selected": "bert_pair", "degraded": false, "reason": "" },
  "models": [
    {
      "name": "beto-sentimiento",
      "role": "sentiment",
      "available": true,
      "loaded": true,
      "architecture": "BERT base español (BETO) + clasificador de 3 clases",
      "path": "C:\\…\\modelo_sentimiento",
      "maxLength": 512,
      "device": "cpu",
      "labels": ["Negativo", "Neutro", "Positivo"]
    }
  ],
  "database": { "status": "ok", "path": "C:\\…\\api\\data\\api.db", "analyses": 3, "sizeBytes": 4096 },
  "scraperEnabled": true
}
```

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `status` | `"ok"` \| `"degraded"` | Degradado si el motor está degradado, la DB falla o no hay modelos. |
| `version` | string | Versión del API. |
| `environment` | string | `dev` \| `test` \| `prod`. |
| `uptimeSeconds` | number | Segundos desde el arranque. |
| `startedAt` | ISO 8601 | Inicio del proceso. |
| `engine` | `EngineInfo` | `{requested, selected, degraded, reason}`. |
| `models[]` | `ModelInfo[]` | Modelos cargados: `name`, `role`, `available`, `loaded`, `architecture`, `path`, `maxLength`, `device`, `labels`. |
| `database` | `DatabaseInfo` | `{status, path, analyses, sizeBytes}`. |
| `scraperEnabled` | boolean | `NLP_SCRAPER_ENABLED`. |

### 6.2 `GET /v1/models`

Catálogo de modelos, etiquetas y umbrales. Response `200` — `ModelsResponse`:

```json
{
  "engine": { "requested": "bert_pair", "selected": "bert_pair", "degraded": false, "reason": "" },
  "models": [
    {
      "name": "beto-sentimiento",
      "role": "sentiment",
      "available": true,
      "loaded": true,
      "architecture": "BERT base español (BETO) + clasificador de 3 clases",
      "path": "C:\\…\\modelo_sentimiento",
      "maxLength": 512,
      "device": "cpu",
      "labels": ["Negativo", "Neutro", "Positivo"]
    }
  ],
  "sentimentLabels": ["Negativo", "Neutro", "Positivo"],
  "frameLabels": [
    {
      "id": "acceso_servicios",
      "label": "Acceso a servicios",
      "model_label": "Acceso_a_servicios",
      "description": "Cobertura orientada a salud, educación, vivienda y asistencia social.",
      "keywords": ["salud", "hospitales", "educación", "vacunación", "atención médica"],
      "threshold": 0.5
    }
  ],
  "thresholds": {
    "acceso_servicios": 0.5,
    "transito_migratorio": 0.2,
    "seguridad": 0.2,
    "integracion_social": 0.25,
    "politica_migratoria": 0.45,
    "empleo_economia": 0.3,
    "otros": 0.3
  },
  "evaluationAvailable": true
}
```

> **Ojo (discrepancia conocida):** `frameLabels[]` **no** es un modelo
> camelCase; el router lo construye como `dict` con las claves `id`, `label`,
> `model_label` (snake_case), `description`, `keywords` y `threshold`. Los
> clientes deben leer `model_label` (o ignorarlo). El cliente TypeScript ya lo
> refleja así (`FrameLabelInfo`).

Códigos: `200`, `401`, `429`.

### 6.3 `GET /metrics`

Métricas en formato Prometheus (`text/plain; version=0.0.4; charset=utf-8`),
implementadas sin dependencias externas. No es JSON.

Métricas expuestas:

| Métrica | Tipo | Etiquetas | Descripción |
| --- | --- | --- | --- |
| `nlp_api_requests_total` | counter | `method`, `path`, `status` | Peticiones HTTP atendidas. |
| `nlp_api_request_duration_seconds` | histogram | `path`, `le` | Latencia por ruta (buckets 0.005–10 s, +Inf). |
| `nlp_api_analyses_total` | counter | `engine`, `sentiment` | Análisis NLP por motor y sentimiento. |
| `nlp_api_scrape_jobs_total` | counter | `status` | Jobs de ingesta iniciados/terminados por estado. |
| `nlp_api_engine_errors_total` | counter | `engine` | Errores de inferencia. |
| `nlp_api_uptime_seconds` | gauge | — | Segundos desde el arranque. |
| `nlp_api_analyses_stored` | gauge | — | Análisis guardados en SQLite. |
| `nlp_api_scrape_jobs_stored` | gauge | — | Jobs de ingesta guardados. |
| `nlp_api_engine_degraded` | gauge | — | 1 si el motor está degradado. |

Extracto real:

```text
# HELP nlp_api_requests_total Total de peticiones HTTP atendidas
# TYPE nlp_api_requests_total counter
nlp_api_requests_total{method="GET",path="/v1/dashboard/overview",status="200"} 1
nlp_api_requests_total{method="POST",path="/v1/analyze",status="200"} 3
# HELP nlp_api_request_duration_seconds Latencia de peticiones HTTP por ruta
# TYPE nlp_api_request_duration_seconds histogram
nlp_api_request_duration_seconds_bucket{path="/v1/analyze",le="0.025"} 3
nlp_api_request_duration_seconds_bucket{path="/v1/analyze",le="+Inf"} 3
nlp_api_request_duration_seconds_sum{path="/v1/analyze"} 0.047201
nlp_api_request_duration_seconds_count{path="/v1/analyze"} 3
```

Las rutas con id se normalizan a `/v1/analyses/{id}` y
`/v1/sources/jobs/{id}` para no explotar las series.

### 6.4 `GET /v1/monitoring/stats`

Estadísticas internas. Response `200` — `MonitoringStats`:

```json
{
  "generatedAt": "2026-11-09T19:04:30.165461Z",
  "uptimeSeconds": 0.2,
  "requestsTotal": 7,
  "requestsByStatus": { "200": 7 },
  "errorsTotal": 0,
  "analysesTotal": 3,
  "analysesByEngine": { "lexicon": 3 },
  "scrapeJobsTotal": 0,
  "latencyMs": { "mean": 15.7, "p50": 12.69, "p95": 40.26, "p99": 40.26 },
  "engine": { "requested": "lexicon", "selected": "lexicon", "degraded": false, "reason": "" },
  "database": { "status": "ok", "path": "…\\api.db", "analyses": 3, "sizeBytes": 4096 },
  "storeEventsEnabled": true
}
```

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `generatedAt` | ISO 8601 | Momento del snapshot. |
| `uptimeSeconds` | number | Segundos desde el arranque. |
| `requestsTotal` | int | Peticiones contadas (histórico de `api_events` si `storeEventsEnabled`, si no en memoria). |
| `requestsByStatus` | `{"200": n, …}` | Peticiones por código HTTP (claves string). |
| `errorsTotal` | int | Respuestas 5xx. |
| `analysesTotal` | int | Análisis hechos en este proceso. |
| `analysesByEngine` | `{engine: n}` | Análisis por motor. |
| `scrapeJobsTotal` | int | Jobs iniciados en este proceso. |
| `latencyMs` | `{mean, p50, p95, p99}` | Latencias HTTP en ms. |
| `engine` | `EngineInfo` | Motor seleccionado. |
| `database` | `DatabaseInfo` | Estado de SQLite. |
| `storeEventsEnabled` | boolean | Si se persisten eventos (`NLP_STORE_EVENTS`). |

Códigos: `200`, `401`, `429`.

---

## 7. Compatibilidad con el frontend

El API se diseñó contra `frontend-extract/src/types/index.ts`. Casi todo calza
1:1 en camelCase; estas son las diferencias a tener en cuenta al migrar:

| Tema | Frontend simulado | API |
| --- | --- | --- |
| `dateAnalyzed` | Texto preformateado (`"09 de noviembre de 2026, 13:58"`) | **ISO 8601 UTC** (`"2026-11-09T18:58:59.572713Z"`). Formatear en la UI con `Intl.DateTimeFormat`/`toLocaleString`. |
| `modelUsed` | Unión fija `"BETO-v2.1-Spanish" \| "RoBERTa-BNE" \| "XLM-R-MigraLatam"` | `string`: `"BETO-migra-ve (sentimiento + encuadres)"`, `"BETO-migra-ve multitarea (sentimiento + encuadres)"` o `"léxico-MigraVenezuela (baseline)"`. |
| `country` | `"Colombia" \| "México" \| "Desconocido"` | Además admite `"Internacional"`. |
| `TextAnalysisResult` | Sin `meta` | Agrega `meta` (motor, latencia, warnings, `persisted`, `jobId`…). El resto de campos es idéntico. |
| `NewsSitePreset` | Incluye `flag`, `logoText`, `accentColor`, `articles` | `SourcePreset` **sí** incluye `flag`, `logoText`, `accentColor` y usa las mismas categorías (`"Prensa Escrita"`/`"Medio Digital"`); solo falta `articles`, que se obtiene escaneando (`/v1/sources/scan`). |
| `ScrapingProgress` | `articlesFoundCount` | Igual, más `articlesAnalyzedCount`, `steps[]`, `error` y `summary` en el job. |
| `ScrapedSiteSummary` | Sin `generatedAt` | Agrega `generatedAt`. Resto igual. |
| `ModelMetricData` | `corpusSize: string` (texto comercial) | `ModelMetric`: `samples?: number` y `role?: string`; sin `corpusSize`. `accuracy/precision/recall/f1Score` pueden ser `null`. |
| `ConfusionMatrixData` | `matrix: number[][]` | Igual (`labels` + `matrix`). |
| `BENCHMARK_MODELS`, `FRAMES_PERFORMANCE`, `SENTIMENT_CONFUSION_MATRIX`, `HYPOTHESIS_COMPARATIVE_DATA` | Hardcodeados en `data/modelMetrics.ts` | Reemplazables por `GET /v1/dashboard/models` (benchmark + frames + matriz) y `GET /v1/dashboard/corpus` (comparativa por país). |

En `docs/FRONTEND.md` está la guía de migración paso a paso.

---

## 8. Ejemplos rápidos (curl)

```bash
# Salud
curl -s http://localhost:8000/v1/health

# Análisis individual
curl -s -X POST http://localhost:8000/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"text":"La inseguridad preocupa a los ciudadanos en la frontera.","mediaName":"El Tiempo"}'

# Lote
curl -s -X POST http://localhost:8000/v1/analyze/batch \
  -H "Content-Type: application/json" \
  -d '{"items":[{"text":"La inseguridad preocupa."},{"text":"El empleo crece."}]}'

# Presets y escaneo de un sitio
curl -s http://localhost:8000/v1/sources/presets
curl -s -X POST http://localhost:8000/v1/sources/scan \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.eltiempo.com","maxArticles":4}'

# Polling del job (repetir hasta status completed/error)
curl -s http://localhost:8000/v1/sources/jobs/job-3f2b9c1a77de

# Una noticia concreta
curl -s -X POST http://localhost:8000/v1/sources/analyze-url \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.eltiempo.com/colombia/seguridad-frontera"}'

# Dashboard y monitoreo
curl -s http://localhost:8000/v1/dashboard/overview
curl -s "http://localhost:8000/v1/dashboard/timeseries?days=30"
curl -s http://localhost:8000/v1/dashboard/corpus
curl -s http://localhost:8000/v1/dashboard/models
curl -s http://localhost:8000/v1/monitoring/stats
curl -s http://localhost:8000/metrics

# Con API key activa, añadir a todas:
#   -H "X-API-Key: $NLP_API_KEY"
```
