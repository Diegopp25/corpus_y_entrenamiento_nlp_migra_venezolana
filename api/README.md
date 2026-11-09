# API — cobertura mediática de la migración venezolana

API HTTP (FastAPI) del proyecto **Cultural Bias**. Expone el análisis de
sentimiento, encuadres noticiosos y sesgo cultural (hipótesis Colombia–México)
sobre noticias de la migración venezolana, además de la ingesta automática de
medios, un dashboard agregado y métricas de monitoreo.

- Contrato detallado: [`docs/API.md`](../docs/API.md)
- Guía del frontend: [`docs/FRONTEND.md`](../docs/FRONTEND.md)
- Operación/despliegue: [`docs/OPERACIONES.md`](../docs/OPERACIONES.md)
- Cliente TypeScript: [`integrations/frontend-api-client.ts`](../integrations/frontend-api-client.ts)

---

## Arquitectura

```text
                    ┌──────────────────────────────────────────────┐
HTTP/JSON  ────────▶│ FastAPI (app/main.py)                        │
                    │  middlewares: request-id, API key, rate      │
                    │  limit, métricas, CORS                       │
                    │                                              │
                    │  routers/                                    │
                    │   ├── health.py     /v1/health, /v1/models   │
                    │   ├── analyze.py     /v1/analyze, /analyses  │
                    │   ├── sources.py     /v1/sources/*           │
                    │   ├── dashboard.py   /v1/dashboard/*         │
                    │   └── monitoring.py  /metrics, /v1/monitoring│
                    │                                              │
                    │  engine/                                     │
                    │   ├── BertPairEngine   2 × BETO (sentimiento │
                    │   │                    + 7 encuadres)        │
                    │   ├── MultitaskEngine  BETO multitarea       │
                    │   └── LexiconEngine    baseline léxico       │
                    │                                              │
                    │  services/  analysis, cultural, scraper,     │
                    │             jobs, corpus, evaluation, store  │
                    └───────────────┬──────────────────────────────┘
                                    │
              ┌─────────────────────┼─────────────────────────┐
              ▼                     ▼                         ▼
      SQLite (data/api.db)   artifacts/*.json          models/ (pesos)
      análisis, jobs,        thresholds.json            BETO (fuera del repo)
      eventos (WAL)          evaluation.json
```

- **Motor:** `auto` intenta BETO par (sentimiento + encuadres) → BETO
  multitarea → léxico. Sin pesos (CI, equipo nuevo) arranca en modo léxico.
- **Persistencia:** SQLite sin ORM (`services/store.py`), modo WAL, una conexión
  por operación. Guarda análisis, jobs de ingesta y eventos de acceso.
- **Contrato:** los modelos Pydantic de `app/schemas.py` se serializan en
  **camelCase** para calzar con `frontend-extract/src/types/index.ts`.
- **Sin dependencias de modelos pesadas** para arrancar: fastapi, uvicorn,
  pydantic, httpx, beautifulsoup4, lxml y trafilatura (si falta trafilatura, el
  scraper degrada a BeautifulSoup y luego a la stdlib).

---

## Requisitos

- Python **3.12** (probado también en 3.13/3.14; el CI usa 3.12).
- Windows PowerShell 5.1+ o Linux/macOS con bash.
- Para inferencia real: pesos BETO (~440 MB por modelo) y, opcionalmente, GPU.
- No hace falta Node ni base de datos externa.

---

## Instalación (CPU / sin modelos)

```powershell
cd api

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

Copy-Item .env.example .env
.\scripts\run_dev.ps1 -Reload
```

Abre <http://localhost:8000/docs>. Sin pesos configurados el motor `auto` usa el
**léxico** (`api/app/resources/lexicon.json`), suficiente para desarrollo, CI y
pruebas del frontend.

### Tests

```powershell
cd api
.\.venv\Scripts\python.exe -m pytest tests -q
# Solo los que no requieren pesos ni red:
.\.venv\Scripts\python.exe -m pytest tests -q -m "not real_models and not network"
```

---

## Instalación con modelos BETO (GPU/CPU)

1. Instala PyTorch para tu CUDA (o CPU) desde el selector oficial de PyTorch:

   ```powershell
   # ejemplo CUDA 12.1; ajusta a tu driver
   .\.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cu121
   ```

2. Instala el resto de dependencias de modelos:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements-models.txt
   ```

3. Coloca los pesos y configura `.env` (ver siguiente sección).
4. Verifica en <http://localhost:8000/v1/health>:
   `engine.selected="bert_pair"`, `engine.degraded=false` y dos modelos en
   `models[]` con `loaded=true`.

### Dónde colocar los pesos

Los pesos **no viven en el repositorio** (`.gitignore` excluye `api/models/`,
`*.pt`, `*.pth`, `*.ckpt`). Se configuran con rutas absolutas:

| Variable | Contenido |
| --- | --- |
| `NLP_SENTIMENT_MODEL_DIR` | Carpeta `save_pretrained` del modelo de sentimiento (3 salidas: Negativo/Neutro/Positivo). |
| `NLP_FRAMES_MODEL_DIR` | Carpeta `save_pretrained` del modelo de 7 encuadres (sigmoide). |
| `NLP_MULTITASK_MODEL_DIR` | (Alternativa) carpeta con `model.pt` + `sentiment_classes.json`. |

Cada carpeta debe tener `config.json`, los pesos
(`model.safetensors` | `pytorch_model.bin` | `model.pt`) y el tokenizador
(`tokenizer.json` o `vocab.txt`).

```text
api/models/
├── bert-sentiment/   →  NLP_SENTIMENT_MODEL_DIR=api/models/bert-sentiment
├── bert-frames/      →  NLP_FRAMES_MODEL_DIR=api/models/bert-frames
└── multitask_beto/   →  NLP_MULTITASK_MODEL_DIR=api/models/multitask_beto
```

> Convención del proyecto: en el equipo los pesos están fuera del repo, p. ej.
> `C:\Users\<usuario>\Desktop\proyecto\modelo_sentimiento` y
> `...\modelo_encuadre`. Cada quien ajusta las rutas en su `api/.env` (que está
> ignorado por git).

---

## Configuración (`.env`)

Copia [`api/.env.example`](.env.example) a `api/.env`. Las variables tienen
prefijo `NLP_` y se pueden definir también como variables de entorno del
sistema. Resumen de las más importantes:

| Variable | Default | Descripción |
| --- | --- | --- |
| `NLP_ENVIRONMENT` | `dev` | `dev`/`test`/`prod`. |
| `NLP_LOG_LEVEL` | `INFO` | Nivel de logging. |
| `NLP_DOCS_ENABLED` | `true` | Expone `/docs`, `/redoc`, `/openapi.json`. |
| `NLP_API_KEY` | (vacío) | Si se define, exige `X-API-Key` (salvo `/`, `/v1/health`, `/metrics` y docs). |
| `NLP_CORS_ORIGINS` | `["*"]` | Orígenes permitidos, **array JSON** (p. ej. `["http://localhost:5173"]`). |
| `NLP_RATE_LIMIT_REQUESTS` / `_WINDOW_SECONDS` | `120` / `60` | Rate limit por cliente. |
| `NLP_MAX_TEXT_CHARS` / `NLP_MAX_BATCH_ITEMS` | `20000` / `50` | Límites de análisis. |
| `NLP_ENGINE` | `auto` | `auto`\|`bert_pair`\|`multitask`\|`lexicon`. |
| `NLP_DEVICE` | `auto` | `auto`\|`cpu`\|`cuda`. |
| `NLP_MAX_LENGTH` | `512` | Tokens máximos para BETO. |
| `NLP_FRAME_THRESHOLD` | `0.5` | Umbral por defecto de encuadre (si no hay `thresholds.json`). |
| `NLP_SENTIMENT_MODEL_DIR` / `NLP_FRAMES_MODEL_DIR` | `api/models/...` | Rutas a los pesos. |
| `NLP_THRESHOLDS_PATH` | `artifacts/thresholds.json` | Umbrales óptimos por encuadre. |
| `NLP_EVALUATION_PATH` | `artifacts/evaluation.json` | Métricas para `/v1/dashboard/models`. |
| `NLP_LEXICON_PATH` | `app/resources/lexicon.json` | Léxico de respaldo. |
| `NLP_DATABASE_PATH` | `data/api.db` | SQLite (WAL). |
| `NLP_CORPUS_CSV_PATH` | `../Data/dataset_migracion_venezolana_labeled.csv` | CSV del dashboard de corpus. |
| `NLP_SCRAPER_ENABLED` | `true` | Habilita `/v1/sources/*`. |
| `NLP_SCRAPER_RESPECT_ROBOTS` | `true` | Respeta robots.txt. |
| `NLP_SCRAPER_TIMEOUT_SECONDS` | `20` | Timeout por descarga. |
| `NLP_SCRAPER_MAX_ARTICLES` | `8` | Tope de artículos por escaneo. |
| `NLP_SCRAPER_ALLOW_PRIVATE_NETWORKS` | `false` | Guard anti-SSRF. |
| `NLP_SCRAPER_MAX_JOBS_IN_PARALLEL` | `2` | Hilos de ingesta. |
| `NLP_SCRAPER_JOB_TTL_HOURS` | `24` | Limpieza de jobs viejos. |

Todas las variables y comentarios: [`api/.env.example`](.env.example).

---

## Arranque

Desde `api/`:

```powershell
# Desarrollo (recarga automática)
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# Equivalente con el script de ayuda (usa .venv, carga .env y muestra URLs)
.\scripts\run_dev.ps1 -Reload
.\scripts\run_dev.ps1 -Port 8080 -Reload -Engine lexicon

# Producción (sin reload)
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- API: <http://localhost:8000>
- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- OpenAPI: <http://localhost:8000/openapi.json>
- Health: <http://localhost:8000/v1/health>
- Métricas: <http://localhost:8000/metrics>

`run_dev.ps1` usa `api/.venv` si existe (si no, el `python` del PATH), carga
`api/.env` y permite forzar el motor con `-Engine`.

---

## Ejemplos curl

```bash
# Salud y modelos
curl -s http://localhost:8000/v1/health
curl -s http://localhost:8000/v1/models

# Analizar un texto
curl -s -X POST http://localhost:8000/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "text": "La ola de inseguridad en la frontera preocupa a los habitantes de Cúcuta.",
    "title": "Crece la preocupación por seguridad",
    "sourceUrl": "https://www.eltiempo.com/colombia/seguridad-frontera",
    "mediaName": "El Tiempo"
  }'

# Varios textos (máx. 50)
curl -s -X POST http://localhost:8000/v1/analyze/batch \
  -H "Content-Type: application/json" \
  -d '{"items":[{"text":"La inseguridad preocupa."},{"text":"El empleo crece."}]}'

# Historial y detalle
curl -s "http://localhost:8000/v1/analyses?limit=5&sentiment=Negativo"
curl -s http://localhost:8000/v1/analyses/analisis-10620d2d1eb94ae7

# Ingesta de noticias: presets → scan (202) → polling
curl -s http://localhost:8000/v1/sources/presets
curl -s -X POST http://localhost:8000/v1/sources/scan \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.eltiempo.com","maxArticles":4}'
curl -s http://localhost:8000/v1/sources/jobs/job-3f2b9c1a77de
curl -s "http://localhost:8000/v1/sources/jobs?limit=10"

# Extraer y analizar una noticia concreta
curl -s -X POST http://localhost:8000/v1/sources/analyze-url \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.eltiempo.com/colombia/seguridad-frontera"}'

# Dashboard
curl -s http://localhost:8000/v1/dashboard/overview
curl -s "http://localhost:8000/v1/dashboard/timeseries?days=30"
curl -s http://localhost:8000/v1/dashboard/corpus
curl -s http://localhost:8000/v1/dashboard/models
curl -s "http://localhost:8000/v1/dashboard/recent?limit=10"

# Monitoreo
curl -s http://localhost:8000/v1/monitoring/stats
curl -s http://localhost:8000/metrics

# Con NLP_API_KEY activa, añade a todo:
#   -H "X-API-Key: $NLP_API_KEY"
```

### Polling de un job de ingesta

`POST /v1/sources/scan` responde `202` con `jobId`, `statusUrl` y
`pollAfterSeconds` (1,5 s). Consulta `GET /v1/sources/jobs/{jobId}` hasta que
`status` sea `completed` (incluye `summary`) o `error` (incluye `error`):

```text
queued → connecting → crawling → cleaning → analyzing → completed | error
```

---

## Endpoints

Si `NLP_API_KEY` está definida, se exige `X-API-Key` en todas las rutas salvo
`/`, `/v1/health`, `/metrics`, `/docs`, `/redoc` y `/openapi.json`.

| Método | Ruta | Descripción |
| --- | --- | --- |
| `GET` | `/` | Información del servicio. |
| `GET` | `/v1/health` | Salud, motor, modelos y SQLite (sin API key). |
| `GET` | `/v1/models` | Catálogo de modelos, etiquetas y umbrales. |
| `POST` | `/v1/analyze` | Sentimiento + 7 encuadres + sesgo cultural. |
| `POST` | `/v1/analyze/batch` | Hasta 50 textos. |
| `GET` | `/v1/analyses` | Historial paginado y filtrable. |
| `GET` | `/v1/analyses/{analysis_id}` | Análisis guardado completo. |
| `GET` | `/v1/sources/presets` | Medios preconfigurados (8). |
| `POST` | `/v1/sources/scan` | Lanza rastreo + análisis (202). |
| `GET` | `/v1/sources/jobs` | Lista resumida de jobs. |
| `GET` | `/v1/sources/jobs/{job_id}` | Progreso detallado del job. |
| `POST` | `/v1/sources/analyze-url` | Extrae y analiza una noticia. |
| `GET` | `/v1/dashboard/overview` | Agregados del dashboard. |
| `GET` | `/v1/dashboard/timeseries?days=` | Serie diaria por sentimiento. |
| `GET` | `/v1/dashboard/corpus` | Estadísticas del CSV etiquetado. |
| `GET` | `/v1/dashboard/models` | Métricas reales de evaluación. |
| `GET` | `/v1/dashboard/recent?limit=` | Últimos análisis. |
| `GET` | `/v1/monitoring/stats` | Estadísticas internas. |
| `GET` | `/metrics` | Prometheus (texto plano). |

Contrato completo, shapes y ejemplos: [`docs/API.md`](../docs/API.md).

---

## Códigos de error

Formato uniforme:

```json
{ "error": { "code": "invalid_text", "message": "…", "detail": null } }
```

| Código | HTTP | Cuándo |
| --- | --- | --- |
| `validation_error` | 422 | Body/query fuera de contrato (detalle con errores Pydantic). |
| `invalid_text` | 422 | Texto vacío o sin contenido analizable. |
| `batch_too_large` | 422 | Lote mayor que `NLP_MAX_BATCH_ITEMS`. |
| `unauthorized` | 401 | API key ausente o inválida. |
| `rate_limited` | 429 | Rate limit (incluye `Retry-After`). |
| `not_found` | 404 | Análisis/job/página remota inexistente. |
| `invalid_url` / `url_blocked` / `unresolvable_host` | 422 | URL inválida, SSRF bloqueado, DNS. |
| `extraction_failed` / `invalid_content` | 422 | Página sin texto útil / no HTML. |
| `invalid_max_articles` | 422 | `maxArticles` fuera de rango en `/scan`. |
| `robots_denied` | 403 | robots.txt prohíbe el rastreo. |
| `scraper_disabled` | 503 | `NLP_SCRAPER_ENABLED=false`. |
| `upstream_*` / `scraper_error` / `fetch_error` | 503 | Fallo del sitio remoto (timeout, caído, demasiado grande…) o del scraper. |
| `engine_error` | 503 | Fallo del motor de análisis. |
| `corpus_unavailable` | 503 | Falta el CSV del corpus o le falta `sentimiento`. |
| `internal_error` | 500 | Error inesperado (revisa logs del servidor). |

---

## Artefactos y corpus

- `api/app/resources/lexicon.json` — léxico de respaldo (sentimiento, encuadres y
  términos de sesgo). Regenerable con `api/scripts/build_lexicon.py`.
- `api/artifacts/thresholds.json` — umbral óptimo por encuadre (requiere reinicio).
- `api/artifacts/evaluation.json` — métricas reales para `/v1/dashboard/models`
  (se lee por petición). Regenerable con `api/scripts/evaluate_models.py`.
- Corpus etiquetado real: **156 artículos**
  (`Data/dataset_migracion_venezolana_labeled.csv`). La evaluación puede
  solaparse con entrenamiento (no se conservó el split): trátala como indicador
  interno, no como benchmark independiente.

Comandos de regeneración y backups: [`docs/OPERACIONES.md`](../docs/OPERACIONES.md).

---

## Docker y CI

```powershell
# Desde api/
docker build -t migra-nlp-api .                                   # sin torch
docker build --build-arg INSTALL_MODELS=1 -t migra-nlp-api:models # con BETO
docker compose up --build
```

- `api/Dockerfile` — multi-stage `python:3.12-slim`, usuario no root,
  `HEALTHCHECK` a `/v1/health`, `ARG INSTALL_MODELS` para torch/transformers.
- `api/docker-compose.yml` — `env_file: .env`, volúmenes `./models`,
  `./artifacts` y `./data`, puerto `8000`, restart y healthcheck.
- `.github/workflows/api-tests.yml` — CI Ubuntu + Python 3.12 que ejecuta
  `pytest -m "not real_models and not network"`.

Detalles de operación (Prometheus, backups SQLite, GPU, troubleshooting):
[`docs/OPERACIONES.md`](../docs/OPERACIONES.md).

---

## Estructura del código

```text
api/
├── app/
│   ├── main.py          # create_app, middlewares, routers, lifespan
│   ├── config.py        # Settings (NLP_*) y resolución de rutas
│   ├── schemas.py       # contrato Pydantic en camelCase
│   ├── deps.py / errors.py / middleware.py
│   ├── routers/         # health, analyze, sources, dashboard, monitoring
│   ├── engine/          # base, bert_pair, multitask, lexicon, labels, text, registry
│   └── services/        # analysis, cultural, scraper, fetching, jobs, corpus,
│                        # evaluation, store, monitoring, site_catalog
├── scripts/             # build_lexicon.py, evaluate_models.py, run_dev.ps1
├── tests/               # pytest (conftest con motor falso, sin red)
├── requirements.txt / requirements-models.txt / requirements-dev.txt
├── pyproject.toml       # config de pytest y ruff
├── Dockerfile / docker-compose.yml / .dockerignore
└── .env.example
```
