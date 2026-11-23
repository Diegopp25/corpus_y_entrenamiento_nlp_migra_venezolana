# Operaciones y despliegue del API

Runbook para instalar, desplegar y operar el API de cobertura mediática de la
migración venezolana. Complementa:

- [`docs/API.md`](./API.md) — contrato de endpoints.
- [`docs/FRONTEND.md`](./FRONTEND.md) — integración del frontend.
- [`api/README.md`](../api/README.md) — instalación local paso a paso.
- [`api/.env.example`](../api/.env.example) — todas las variables.

---

## 1. Arquitectura de despliegue

```text
navegador (Vite/React)  ──HTTP/JSON──▶  API FastAPI (:8000)
                                          ├── Motor NLP (BETO par / multitarea / léxico)
                                          ├── SQLite (data/api.db, WAL): análisis, jobs, eventos
                                          ├── Artefactos (artifacts/): thresholds.json, evaluation.json
                                          ├── Pesos BETO (models/, montados; fuera del repo)
                                          └── Scraper HTTP (httpx + BeautifulSoup/trafilatura)
Prometheus  ──scrape /metrics──▶  API
```

- Un solo proceso uvicorn es el modo recomendado (ver §9.3).
- El estado (análisis, jobs, eventos) vive en SQLite; los pesos y artefactos se
  montan como volúmenes en Docker.
- No hay dependencias externas en runtime más allá de los sitios que se rastrean.

---

## 2. Variables de entorno

Todas con prefijo `NLP_`; se leen de `api/.env` o del entorno real (el entorno
tiene prioridad). Referencia completa y comentada:
[`api/.env.example`](../api/.env.example).

| Grupo | Variables | Notas |
| --- | --- | --- |
| Aplicación | `NLP_ENVIRONMENT`, `NLP_LOG_LEVEL`, `NLP_DOCS_ENABLED` | `prod` para despliegue; en prod considera `NLP_DOCS_ENABLED=false`. |
| Seguridad | `NLP_API_KEY`, `NLP_CORS_ORIGINS`, `NLP_RATE_LIMIT_REQUESTS`, `NLP_RATE_LIMIT_WINDOW_SECONDS` | Sin `NLP_API_KEY` la API es abierta. CORS por defecto `["*"]`. |
| Límites | `NLP_MAX_TEXT_CHARS` (20000), `NLP_MAX_BATCH_ITEMS` (50), `NLP_STORE_EVENTS` | |
| Motor | `NLP_ENGINE` (`auto`\|`bert_pair`\|`multitask`\|`lexicon`), `NLP_DEVICE` (`auto`\|`cpu`\|`cuda`), `NLP_MAX_LENGTH` (512), `NLP_FRAME_THRESHOLD` (0.5), `NLP_PREPROCESS_WITH_SPACY` | `auto` cae a léxico si faltan pesos. |
| Pesos | `NLP_SENTIMENT_MODEL_DIR`, `NLP_FRAMES_MODEL_DIR`, `NLP_MULTITASK_MODEL_DIR` | Rutas absolutas a carpetas `save_pretrained`. |
| Artefactos | `NLP_THRESHOLDS_PATH`, `NLP_EVALUATION_PATH`, `NLP_LEXICON_PATH`, `NLP_ARTIFACTS_DIR` | Por defecto en `api/artifacts/`. |
| Persistencia | `NLP_DATABASE_PATH`, `NLP_CORPUS_CSV_PATH` | SQLite WAL; CSV del corpus para `/v1/dashboard/corpus`. |
| Scraper | `NLP_SCRAPER_ENABLED`, `NLP_SCRAPER_RESPECT_ROBOTS`, `NLP_SCRAPER_TIMEOUT_SECONDS`, `NLP_SCRAPER_MAX_ARTICLES`, `NLP_SCRAPER_MAX_RESPONSE_BYTES`, `NLP_SCRAPER_ALLOW_PRIVATE_NETWORKS`, `NLP_SCRAPER_KEYWORDS`, `NLP_SCRAPER_MAX_JOBS_IN_PARALLEL`, `NLP_SCRAPER_JOB_TTL_HOURS`, `NLP_SCRAPER_USER_AGENT` | Valores por defecto prudentes (robots sí, SSRF bloqueado). |

> Las rutas relativas en `.env` se resuelven contra la carpeta `api/`, no contra
> el directorio desde el que se lanza uvicorn.
>
> **Variables de tipo lista** (`NLP_CORS_ORIGINS`, `NLP_SCRAPER_KEYWORDS`): por
> cómo parsea pydantic-settings los `.env`, deben escribirse como **array JSON**
> (`NLP_CORS_ORIGINS=["http://localhost:5173"]`). Un valor como `*` o una lista
> separada por comas hace fallar el arranque con `SettingsError`.

---

## 3. Instalación local (CPU / GPU)

### 3.1 CPU (solo API o motor léxico)

```powershell
cd api
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\scripts\run_dev.ps1 -Reload
```

Sin pesos BETO el motor `auto` selecciona el **léxico** (baseline entrenado con
el corpus, `api/app/resources/lexicon.json`). Sirve para desarrollar el frontend,
CI y demos, pero no es el modelo final.

### 3.2 GPU + modelos BETO reales

1. Instala el build de PyTorch para tu CUDA desde el selector oficial
   (p. ej. `pip install torch --index-url https://download.pytorch.org/whl/cu121`).
2. Instala el resto:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements-models.txt
   ```

3. Configura los pesos en `api/.env`:

   ```text
   NLP_ENGINE=bert_pair
   NLP_DEVICE=cuda
   NLP_SENTIMENT_MODEL_DIR=C:/ruta/a/modelo_sentimiento
   NLP_FRAMES_MODEL_DIR=C:/ruta/a/modelo_encuadre
   ```

4. Arranca y verifica: `GET /v1/health` → `engine.selected="bert_pair"`,
   `engine.degraded=false`, y `models[]` con `beto-sentimiento` y
   `beto-encuadres` en `loaded=true`.

---

## 4. Pesos de los modelos (fuera del repo)

Los pesos **no se versionan** (cientos de MB). El `.gitignore` excluye
`api/models/`, `*.pt`, `*.pth`, `*.ckpt`.

### 4.1 Estructura esperada

```text
api/models/bert-sentiment/      # NLP_SENTIMENT_MODEL_DIR
├── config.json
├── model.safetensors | pytorch_model.bin | model.pt
├── tokenizer.json               # o vocab.txt
└── tokenizer_config.json / special_tokens_map.json
api/models/bert-frames/         # NLP_FRAMES_MODEL_DIR (7 salidas sigmoide)
└── (misma estructura)
api/models/multitask_beto/      # NLP_MULTITASK_MODEL_DIR (alternativa)
├── model.pt
└── sentiment_classes.json
```

Requisitos que comprueba `app/engine/bert_pair.py`:

- `model_dir_ready()`: hay pesos (`model.safetensors`/`pytorch_model.bin`/
  `model.pt`) **y** tokenizador (`tokenizer.json` o `vocab.txt`).
- Nº de salidas del modelo = 3 (sentimiento) y 7 (encuadres); si no, el motor
  falla con un mensaje claro.
- Orden de etiquetas esperado: sentimiento `[Negativo, Neutro, Positivo]`;
  encuadres `[Acceso_a_servicios, Empleo_y_economía, Integración_social, Otros,
  Politica_migratoria, Seguridad, Transito_migratorio]`.

### 4.2 Alternativas de configuración

| Situación | `NLP_ENGINE` | Efecto |
| --- | --- | --- |
| Solo hay pesos del par BETO | `auto` o `bert_pair` | Usa BETO par. |
| Solo hay checkpoint multitarea | `auto` o `multitask` | Usa BETO multitarea. |
| No hay pesos (CI, equipo nuevo) | `auto` | Cae a léxico y marca `degraded=true` solo si la petición era forzada; `/v1/health.status` puede ser `degraded` si no hay modelos. |
| Quiero forzar léxico | `lexicon` | Sin torch; útil para tests. |

Si se **fuerza** `bert_pair`/`multitask` sin pesos, el arranque falla con
`EngineUnavailable` y un mensaje que indica qué variable configurar.

---

## 5. Docker

Archivos: [`api/Dockerfile`](../api/Dockerfile),
[`api/.dockerignore`](../api/.dockerignore),
[`api/docker-compose.yml`](../api/docker-compose.yml).

### 5.1 Imagen sin modelos (API + léxico, ~200 MB)

```powershell
cd api
docker build -t migra-nlp-api .
docker run --rm -p 8000:8000 migra-nlp-api
# http://localhost:8000/v1/health
```

### 5.2 Imagen con soporte de modelos (torch + transformers)

```powershell
docker build --build-arg INSTALL_MODELS=1 -t migra-nlp-api:models .
```

`INSTALL_MODELS=1` instala `requirements-models.txt` (incluye
`-r requirements.txt` + `torch` + `transformers`). La imagen crece a varios GB.
En CPU la inferencia BETO es lenta (≈1 s/noticia); para producción usa GPU.

### 5.3 docker-compose

```powershell
cd api
Copy-Item .env.example .env      # ajustar; en Docker las rutas del .env se sobrescriben
# Estructura de volúmenes:
#   api/models/bert-sentiment/, api/models/bert-frames/
#   api/artifacts/   (thresholds.json, evaluation.json)
#   api/data/        (api.db persistente)
docker compose up --build        # CPU
$env:INSTALL_MODELS=1; docker compose build; docker compose up   # con torch
```

Detalles del compose:

- `env_file: .env` + `environment:` que **sobrescribe** las rutas de modelos a
  `/app/models/...` (las rutas Windows del `.env` no existen en el contenedor).
- Volúmenes: `./models:/app/models:ro`, `./artifacts:/app/artifacts`,
  `./data:/app/data`.
- `restart: unless-stopped`, healthcheck cada 30 s contra `/v1/health`,
  puerto `${API_PORT:-8000}:8000`.
- La imagen corre como usuario **no root** (`app`), con `NLP_ENVIRONMENT=prod`
  por defecto y `/app/data` para SQLite.
- Al apagar el contenedor (`SIGTERM`/`Ctrl+C`), el `lifespan` cierra el pool de
  jobs y el cliente HTTP del scraper; los jobs en curso quedan con su estado
  persistido en SQLite y el TTL (24 h) los limpia.
- **Linux + bind mounts:** `./data` y `./artifacts` deben ser escribibles por el
  usuario no root de la imagen. Si ves `unable to open database file` o errores
  de permisos, ajusta el dueño del directorio del host (`chown`) o usa volúmenes
  nombrados de Docker.

### 5.4 GPU en Docker (opcional)

Requiere NVIDIA Container Toolkit. En `api/docker-compose.yml`, descomenta el
bloque `deploy.resources.reservations.devices` y pon `NLP_DEVICE=cuda` en `.env`
(o `environment`). Verifica con
`docker compose exec api python -c "import torch; print(torch.cuda.is_available())"`.

---

## 6. Monitoreo con Prometheus

### 6.1 Endpoint

`GET /metrics` devuelve texto `text/plain; version=0.0.4; charset=utf-8`.
Está **exento de API key** (y de rate limit) a propósito, para que Prometheus
pueda hacer scraping sin configurar credenciales; solo expone agregados, no
datos de negocio.

Métricas expuestas (detalle en [`docs/API.md` §6.3](./API.md#63-get-metrics)):

- `nlp_api_requests_total{method,path,status}` (counter)
- `nlp_api_request_duration_seconds{path,le}` (histogram)
- `nlp_api_analyses_total{engine,sentiment}` (counter)
- `nlp_api_scrape_jobs_total{status}` (counter)
- `nlp_api_engine_errors_total{engine}` (counter)
- `nlp_api_uptime_seconds` (gauge)
- `nlp_api_analyses_stored`, `nlp_api_scrape_jobs_stored`,
  `nlp_api_engine_degraded` (gauges del store)

Las rutas con id se normalizan (`/v1/analyses/{id}`, `/v1/sources/jobs/{id}`)
para no crear series por cada análisis.

### 6.2 `prometheus.yml` de ejemplo

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: migra-nlp-api
    metrics_path: /metrics
    static_configs:
      - targets: ["api:8000"]
```

No hace falta autenticación: `/metrics` está exento de API key. Si en el futuro
se protegiera, se podría usar `authorization: {type: Bearer, credentials_file: …}`
o `http_headers.X-API-Key`, que el middleware también acepta en el resto de rutas.

### 6.3 Consultas y alertas útiles

```text
# p95 de latencia por ruta
histogram_quantile(0.95, sum(rate(nlp_api_request_duration_seconds_bucket[5m])) by (le, path))

# tasa de errores 5xx
sum(rate(nlp_api_requests_total{status=~"5.."}[5m])) /
sum(rate(nlp_api_requests_total[5m]))

# motor degradado
max(nlp_api_engine_degraded) == 1

# API caída
up{job="migra-nlp-api"} == 0
```

Alertas mínimas sugeridas: `up == 0` (crítica), `nlp_api_engine_degraded == 1`
(warning), tasa 5xx > 5 % durante 10 min (warning), p95 > 2 s durante 10 min
(warning).

### 6.4 `GET /v1/monitoring/stats`

Alternativa JSON sin Prometheus: uptime, peticiones por estado, errores,
análisis por motor, jobs, latencias p50/p95/p99 y estado de SQLite. Si
`NLP_STORE_EVENTS=true` (por defecto) las cifras se calculan sobre la tabla
`api_events` y sobreviven reinicios; si está en `false`, solo cuentan el
proceso actual.

---

## 7. Logs

- Formato: `fecha | NIVEL | logger | mensaje` a **stdout**
  (`app/main.py:configure_logging`), pensado para `docker logs`/journald.
- Nivel: `NLP_LOG_LEVEL` (`INFO` por defecto; `DEBUG` para diagnóstico).
- `httpx`/`httpcore` se fuerzan a `WARNING` para no inundar con cada descarga.
- Cada respuesta lleva `X-Request-ID`: úsalo para correlacionar la petición del
  frontend con la línea de log del servidor.
- Los errores no controlados se registran con traza (`logger.exception`) y el
  cliente recibe `500 internal_error` sin detalles internos.

```powershell
docker logs -f migra-nlp-api
docker logs migra-nlp-api 2>&1 | Select-String "ERROR"
```

---

## 8. Backups y rotación de SQLite

SQLite guarda **análisis, jobs de scraping y eventos** en
`NLP_DATABASE_PATH` (`api/data/api.db`), en modo WAL
(`api.db`, `api.db-wal`, `api.db-shm`).

### 8.1 Backup consistente

Con la API parada basta copiar el `.db`. En caliente, usa el backup online de
SQLite (no copies solo el `.db` con WAL activo):

```powershell
# Windows/PowerShell, API corriendo
$db = "C:\ruta\migra-nlp\api\data\api.db"
$dest = "D:\backups\api-$(Get-Date -Format yyyyMMdd-HHmmss).db"
& api\.venv\Scripts\python.exe -c "import sqlite3,sys; src=sqlite3.connect(sys.argv[1]); dst=sqlite3.connect(sys.argv[2]); src.backup(dst); dst.close(); src.close()" $db $dest
```

o con la CLI de SQLite:

```text
sqlite3 api/data/api.db ".backup 'D:/backups/api-2026-11-09.db'"
sqlite3 api/data/api.db "VACUUM INTO 'D:/backups/api-compacto.db'"   # además compacta
```

En Docker:

```powershell
docker compose exec api python -c "import sqlite3; src=sqlite3.connect('/app/data/api.db'); dst=sqlite3.connect('/app/data/backup.db'); src.backup(dst); dst.close(); src.close()"
docker cp migra-nlp-api:/app/data/backup.db .\backup-$(Get-Date -Format yyyyMMdd).db
```

### 8.2 Rotación y limpieza

- Al arrancar, `lifespan` ejecuta `prune_events(days=30)` y
  `prune_jobs(ttl_hours=NLP_SCRAPER_JOB_TTL_HOURS)` (24 h por defecto).
- Los análisis **no** se borran automáticamente; define una retención manual si
  el volumen crece (p. ej. `DELETE FROM analyses WHERE created_at < ...` seguido
  de `VACUUM`).
- Programa el backup diario con el Programador de tareas (Windows) o cron
  (Linux), conservando 7–30 copias. Los `.db-wal`/`.db-shm` no hace falta
  copiarlos con el backup online.
- Los **artefactos** (`thresholds.json`, `evaluation.json`) se regeneran con
  scripts (§10): respáldalos junto al CSV del corpus si son costosos de
  recalcular.

### 8.3 Restauración

1. Detén la API.
2. Reemplaza `api/data/api.db` por la copia (elimina `.db-wal` y `.db-shm`
   viejos).
3. Arranca y verifica `GET /v1/health` (`database.status="ok"`, `analyses > 0`).

---

## 9. Healthchecks y despliegue

### 9.1 Healthcheck

- `GET /v1/health` (sin API key). `status` es `"ok"` o `"degraded"`.
- `degraded` = motor degradado (cayó a léxico), SQLite con error o sin modelos.
- **No** uses solo el código HTTP: siempre 200 si el proceso responde. Para
  probes de Kubernetes/LB que deban reiniciar el pod, valida el contenido:

```yaml
# Kubernetes (ejemplo)
livenessProbe:
  httpGet: { path: /v1/health, port: 8000 }
  initialDelaySeconds: 40
  periodSeconds: 30
readinessProbe:
  httpGet: { path: /v1/health, port: 8000 }
  periodSeconds: 15
```

Docker: el `HEALTHCHECK` del Dockerfile y el `healthcheck` del compose consultan
`/v1/health` con la stdlib de Python (la imagen `slim` no trae `curl`).

### 9.2 Despliegue con reverse proxy (ejemplo nginx)

```nginx
server {
    listen 80;
    server_name api.midominio.com;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 120s;   # jobs de scraping largos
    }
}
```

Si el proxy termina TLS, el API sigue escuchando HTTP en localhost (no lo
expongas directo a Internet sin TLS, sobre todo si envías la API key).

### 9.3 Workers y estado en memoria

`uvicorn app.main:app --host 0.0.0.0 --port 8000` (1 worker) es lo recomendado.
Con `--workers N`:

- los **contadores de monitoreo** (`/v1/monitoring/stats`, `/metrics`) y el
  rate limit se separan por proceso;
- los análisis/jobs se comparten vía SQLite (funciona, pero con más contención);
- el `JobManager` de cada worker atiende sus propios jobs (el polling cruza
  workers sin problema porque lee de SQLite).

Si necesitas escalar, primero mueve la tasa de ingesta y el dashboard a un
worker dedicado o usa un balanceo con sesiones pegajosas para los jobs.

### 9.4 Checklist de pase a producción

- [ ] `NLP_ENVIRONMENT=prod`, `NLP_LOG_LEVEL=WARNING` o `INFO`.
- [ ] `NLP_API_KEY` definida y repartida por gestor de secretos (no en `.env`
      commiteado; `.env` está en `.gitignore`).
- [ ] `NLP_CORS_ORIGINS` restringido al dominio del frontend.
- [ ] `NLP_DOCS_ENABLED=false` si no quieres Swagger público.
- [ ] Pesos BETO montados en solo lectura y verificados con `/v1/health`.
- [ ] `artifacts/thresholds.json` y `evaluation.json` presentes (o asumir
      `isActive` con 0.5 y `/v1/dashboard/models` con `available=false`).
- [ ] Volumen `data/` con backup programado y tamaño vigilado.
- [ ] Healthcheck y reinicio automático (`restart: unless-stopped`).
- [ ] `/metrics` scrapeado y alertas de `up`/5xx activas.
- [ ] Límites del proxy ≥ timeout del scraper (120 s).

---

## 10. Regenerar artefactos

Los artefactos son **regenerables** y no se versionan como pesos.

### 10.1 Léxico de respaldo

```powershell
cd <raíz del repo>
api\.venv\Scripts\python.exe api\scripts\build_lexicon.py `
  --csv Data\dataset_migracion_venezolana_labeled.csv `
  --output api\app\resources\lexicon.json
```

Genera `sentiment`, `frames` y `bias_terms` con log-odds (df ≥ 2, sin términos
genéricos). **Requiere reiniciar el API** (el motor léxico se carga al arrancar).

### 10.2 Umbrales y evaluación real

```powershell
cd <raíz del repo>
api\.venv\Scripts\python.exe api\scripts\evaluate_models.py
```

Salida por defecto:

- `api/artifacts/evaluation.json` — métricas de sentimiento y encuadres para
  `/v1/dashboard/models` (se lee **en cada petición**: no hace falta reiniciar).
- `api/artifacts/thresholds.json` — umbral óptimo por encuadre (búsqueda de F1
  en grid 0.2–0.8). **Requiere reiniciar** para que el motor y `/v1/models` los
  apliquen.

Comprueba después:

```bash
curl -s http://localhost:8000/v1/models | jq ".thresholds, .evaluationAvailable"
curl -s http://localhost:8000/v1/dashboard/models | jq ".available, .sampleSize"
```

### 10.3 Corpus del dashboard

`/v1/dashboard/corpus` lee `NLP_CORPUS_CSV_PATH` y cachea por `mtime`+tamaño: si
reemplazas el CSV, la siguiente petición lo recarga sola (no hace falta
reiniciar). Requiere la columna `sentimiento` y acepta las columnas de encuadre
(`Acceso_a_servicios`, `Empleo_y_economía`, …, o sus ids).

### 10.4 Nota de transparencia sobre la evaluación

El corpus etiquetado real tiene **156 artículos**
(`Data/dataset_migracion_venezolana_labeled.csv`: 79 Neutro, 44 Negativo,
33 Positivo; 77 Colombia, 79 México). La evaluación de `evaluate_models.py` se
hace sobre esos 156 artículos: accuracy de sentimiento ≈ 0.789 y macro-F1
≈ 0.777, con F1 de encuadres variable (0.14–0.82).

**No se conservó el split de entrenamiento**, por lo que la muestra de
evaluación puede solaparse con datos usados para afinar los modelos: las
métricas son un indicador interno, no un benchmark independiente. Los números
de la maqueta del front (`modelMetrics.ts`: 1.420 artículos, ~89 %) son
ficticios y deben reemplazarse por `GET /v1/dashboard/models`.

Otros archivos del corpus (no usados por el API):

| Archivo | Filas | Uso |
| --- | --- | --- |
| `Data/dataset_migracion_venezolana_labeled.csv` | 156 | Etiquetado; dashboard y evaluación. |
| `Data/dataset_balanced.csv` | 237 | Balanceado (79 por clase); entrenamiento. |
| `Data/dataset_merged.csv` | 256 | Sin etiquetar. |

---

## 11. Límites y seguridad

### 11.1 API key

- Se activa definiendo `NLP_API_KEY`; se acepta `X-API-Key: <clave>` o
  `Authorization: Bearer <clave>`.
- Exentos: `/`, `/v1/health`, `/metrics`, `/docs`, `/redoc`, `/openapi.json`.
- Comparación de igualdad simple (no hash): usa claves largas y aleatorias, rota
  periódicamente y no las expongas en logs (el middleware registra solo prefijo
  de 12 caracteres como identificador de cliente, no la clave).
- En el frontend, `VITE_API_KEY` queda en el bundle: solo para demo local.

### 11.2 Rate limit

- `NLP_RATE_LIMIT_REQUESTS`/`NLP_RATE_LIMIT_WINDOW_SECONDS` (120/60 s por
  defecto), por IP o por prefijo de API key.
- Al superarlo: `429 rate_limited` + `Retry-After`.
- En memoria por proceso: con varios workers el límite efectivo se multiplica.
- Pon límites adicionales en el reverse proxy si el API es público.

### 11.3 Límites de payload

- `text` ≤ 20 000 caracteres; lote ≤ 50 y ≤ `NLP_MAX_BATCH_ITEMS`.
- `maxArticles` por escaneo ≤ 10 (recortado a `NLP_SCRAPER_MAX_ARTICLES`).
- `NLP_SCRAPER_MAX_RESPONSE_BYTES` (5 MB) limita cada descarga.
- `NLP_SCRAPER_TIMEOUT_SECONDS` (20 s) por petición del scraper.

### 11.4 robots.txt y SSRF

- `NLP_SCRAPER_RESPECT_ROBOTS=true` (por defecto) consulta y respeta
  `robots.txt`; un sitio que prohíbe el rastreo devuelve `403 robots_denied`
  (el cliente puede saltarlo con `respectRobots=false` **solo** con autorización).
- `NLP_SCRAPER_ALLOW_PRIVATE_NETWORKS=false` bloquea IPs privadas, loopback,
  link-local y endpoints de metadatos (169.254.169.254) → `422 url_blocked`
  (protección SSRF). No lo actives en producción salvo para un servicio interno
  controlado.
- User-Agent identificable (`NLP_SCRAPER_USER_AGENT`), con URL del proyecto.
- Los jobs tienen TTL (24 h) y se limpian al arrancar.

### 11.5 Contenedor

- Imagen `python:3.12-slim`, usuario no root (`app`), sin `curl` ni herramientas
  extra, solo `app/` + venv.
- `.dockerignore` excluye `.venv`, `data/`, `models/`, `artifacts/`, `tests/`,
  `.env`, cachés y basura de pip.
- Monta `models/` en solo lectura y `data/` con permisos de escritura solo para
  el usuario del contenedor.

---

## 12. Troubleshooting

| Síntoma | Causa probable | Solución |
| --- | --- | --- |
| `/v1/health` → `engine.selected="lexicon"`, `degraded=true` | Faltan pesos o `torch`/`transformers`. | Configura `NLP_SENTIMENT_MODEL_DIR`/`NLP_FRAMES_MODEL_DIR`, instala `requirements-models.txt`, revisa los logs del motor. |
| Arranque falla con `EngineUnavailable` | `NLP_ENGINE=bert_pair`/`multitask` forzado sin pesos. | Corrige rutas o usa `NLP_ENGINE=auto`. |
| `503 engine_error` en `/v1/analyze` | Excepción durante la inferencia. | Mira el log con el `X-Request-ID`; revisa memoria/GPU y formato de pesos. |
| `422 validation_error` | Body fuera de contrato (texto vacío, > 20 000 chars, lote > 50…). | Revisa `error.detail`. |
| `401 unauthorized` | `NLP_API_KEY` activa y falta/incorrecta la cabecera. | Envía `X-API-Key`. Recuerda que `/metrics` también la exige. |
| `429 rate_limited` | Superaste la cuota. | Respeta `Retry-After` o sube `NLP_RATE_LIMIT_REQUESTS`. |
| `503 corpus_unavailable` | Falta el CSV o no tiene columna `sentimiento`. | Ajusta `NLP_CORPUS_CSV_PATH`; verifica cabeceras. |
| `/v1/dashboard/models` con `available=false` | No existe `api/artifacts/evaluation.json`. | Ejecuta `api/scripts/evaluate_models.py`. |
| `isActive` raro / valores 0.5 | No hay `thresholds.json`. | Genera artefactos y reinicia. |
| `403 robots_denied` | robots.txt del sitio prohíbe. | Respeta la decisión; no desactives robots por defecto. |
| `422 url_blocked` | SSRF guard: IP privada/loopback/metadata. | Usa una URL pública; no desactives el guard en producción. |
| `503 upstream_timeout` / `upstream_unavailable` | Sitio lento o caído. | Reintenta más tarde; sube `NLP_SCRAPER_TIMEOUT_SECONDS` con criterio. |
| Jobs se quedan en `queued` | Pool de jobs saturado o hilo bloqueado. | Revisa `NLP_SCRAPER_MAX_JOBS_IN_PARALLEL`, logs y timeout del sitio. |
| `database is locked` en logs | Contención SQLite (muchos workers o backup). | Un worker; backups con `.backup`/`VACUUM INTO`; revisa `busy_timeout` (ya 10 s). |
| `unable to open database file` (Docker/Linux) | Permisos del bind mount `./data` para el usuario no root. | Ajusta dueño/permisos del directorio del host o usa volumen nombrado. |
| `/metrics` devuelve 401 | No debería: `/metrics` está exento. Si pasa, un proxy/WAF externo está exigiendo credenciales. | Revisa la capa de proxy por delante del API. |
| Docker: `No module named torch` | Construiste sin `INSTALL_MODELS=1`. | `docker build --build-arg INSTALL_MODELS=1`. |
| Docker: modelo no encontrado en `/app/models/...` | Volumen mal montado o carpeta vacía. | Verifica `api/models/bert-sentiment` y `bert-frames`; `docker compose exec api ls /app/models`. |
| Docker: rutas `C:\...` en el contenedor | El `.env` tiene rutas Windows. | El compose ya las sobrescribe; si usas `docker run`, pasa `-e NLP_SENTIMENT_MODEL_DIR=...`. |
| GPU no usada | `NLP_DEVICE=cpu` o build de torch CPU. | `NLP_DEVICE=cuda`, instala torch CUDA y verifica `torch.cuda.is_available()`. |
| CI falla por tests `real_models`/`network` | Sin pesos/red en el runner. | El workflow excluye `-m "not real_models and not network"`. |
| CORS en el navegador | Origen no permitido o API caída. | Ajusta `NLP_CORS_ORIGINS`; recuerda `credentials: false`. |

---

## 13. Estructura de carpetas relevante

```text
migra-nlp/
├── api/
│   ├── app/            # código FastAPI (routers, engine, services, schemas)
│   ├── scripts/        # build_lexicon.py, evaluate_models.py, run_dev.ps1
│   ├── artifacts/      # thresholds.json, evaluation.json (regenerables)
│   ├── data/           # api.db + WAL (ignorado por git)
│   ├── models/         # pesos BETO montados (ignorado por git)
│   ├── tests/          # suite pytest (sin red ni pesos reales)
│   ├── Dockerfile / docker-compose.yml / .dockerignore / .env.example
│   └── requirements*.txt
├── Data/               # corpus etiquetado (156 artículos) y variantes
├── docs/               # API.md, FRONTEND.md, OPERACIONES.md
├── integrations/       # frontend-api-client.ts
└── .github/workflows/  # api-tests.yml (CI)
```

CI: [`.github/workflows/api-tests.yml`](../.github/workflows/api-tests.yml)
ejecuta `pytest` en Ubuntu con Python 3.12, sin pesos ni red, en cada push/PR
que toque `api/**`.
