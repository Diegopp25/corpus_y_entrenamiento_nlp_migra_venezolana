# Desplegar el API en Railway (y el frontend aparte)

Estado actual: el código ya está en GitHub en la rama **`integrado`**, que
contiene `api/` (FastAPI), `frontend/` (React) y `training/`. El despliegue del
API se hace desde la carpeta `api/` con su `Dockerfile`.

> Importante: los pesos BETO (~440 MB cada uno) **no están en GitHub** por su
> tamaño. Hay dos modos de despliegue:
>
> - **Modo rápido (plan Free, sin BETO real):** el API arranca con el motor
>   léxico de respaldo. Sirve para tener la app activa y probar endpoints,
>   dashboard e ingesta; el análisis es orientativo y `/v1/health` marca
>   `"degraded": true`.
> - **Modo modelos reales (plan Hobby, ~2 GB RAM):** se descarga un ZIP con los
>   dos modelos al arrancar y el análisis usa BETO real. Requiere subir el ZIP a
>   un GitHub Release o a Hugging Face.

## 0. Requisitos

- Cuenta en [Railway](https://railway.com) conectada a GitHub.
- Repo del proyecto con la rama `integrado` (ya está).
- Para BETO real: plan **Hobby ($5/mes)** o superior, porque el plan Free solo
  da **0.5 GB de RAM** y dos BERT en fp32 necesitan ~2 GB.

## 1. Crear el servicio en Railway (modo rápido)

1. Railway → **New Project → Deploy from GitHub repo** → elige el repo del
   proyecto.
2. En el servicio → **Settings → Source**:
   - **Branch:** `integrado`
   - **Root Directory:** `api`  ← esto es clave, el Dockerfile está ahí.
3. Railway detecta el `Dockerfile` y el `api/railway.json` (healthcheck
   `/v1/health`).
4. **Variables** (Settings → Variables) mínimas:

   | Variable | Valor |
   |---|---|
   | `NLP_ENVIRONMENT` | `prod` |
   | `NLP_ENGINE` | `lexicon` (modo rápido) / `bert_pair` (modo real) |
   | `NLP_CORS_ORIGINS` | `["*"]` mientras pruebas; luego la URL del front (abajo) |
   | `NLP_LOG_LEVEL` | `INFO` |
   | `NLP_DATABASE_PATH` | `/app/data/api.db` |
   | `NLP_SCRAPER_RESPECT_ROBOTS` | `true` |

   Nota: `NLP_CORS_ORIGINS` se parsea como lista; usa JSON válido entre
   corchetes y comillas dobles. Para el front en Vercel/Netlify:
   `["https://tu-front.vercel.app"]`.

5. **Settings → Networking → Generate Domain**. Te queda una URL tipo
   `https://migra-venezuela-api-production.up.railway.app`.
6. Abre `https://TU-URL.up.railway.app/v1/health` → debe responder
   `"status": "ok"` (modo BETO) o `"degraded": true` (modo léxico).
   Documentación interactiva: `https://TU-URL.up.railway.app/docs`.

## 2. Modo modelos reales (BETO)

### 2.1 Crear el ZIP de los modelos

En tu PC, con los modelos de `C:\Users\diego\Desktop\proyecto`:

```powershell
Compress-Archive `
  -Path "C:\Users\diego\Desktop\proyecto\modelo_sentimiento", "C:\Users\diego\Desktop\proyecto\modelo_encuadre" `
  -DestinationPath "$env:USERPROFILE\Desktop\modelos_beto.zip" -Force

Get-Item "$env:USERPROFILE\Desktop\modelos_beto.zip" | Select-Object Length
```

Debe pesar ~880 MB. Sube ese ZIP a:

- **GitHub Release** (recomendado, límite 2 GB por archivo): repo → Releases →
  Draft a new release → tag `modelos-v1` → adjunta el ZIP → publica. Copia la
  URL del asset (termina en `modelos_beto.zip`).
- **Hugging Face** (alternativa): crea un repo de modelos y sube el ZIP; usa la
  URL `https://huggingface.co/<usuario>/<repo>/resolve/main/modelos_beto.zip`.

### 2.2 Variables del modo real

En Railway → servicio → **Variables**, añade/actualiza:

| Variable | Valor |
|---|---|
| `RAILWAY_DOCKERFILE_PATH` | `Dockerfile.models` |
| `NLP_ENGINE` | `bert_pair` |
| `NLP_MODELS_ARCHIVE_URL` | URL del ZIP subido |
| `NLP_MODELS_DIR` | `/app/models` (o `/data/models` con volumen) |
| `NLP_REQUIRE_MODELS` | `true` |
| `NLP_DEVICE` | `cpu` |
| `NLP_MAX_LENGTH` | `512` |

El `start.py` del contenedor descarga el ZIP, lo descomprime como
`bert-sentiment/` y `bert-frames/`, y arranca uvicorn. El primer arranque tarda
más por la descarga y la carga de los dos modelos (~1–2 min en total).

**Memoria:** si Railway mata el proceso por OOM (logs con “out of memory” o
exit 137), sube el plan a Hobby y/o asegúrate de que el servicio tiene al menos
2 GB. Para una demo sin costo, usa el modo rápido léxico.

**Persistencia (opcional):** monta un volumen en `/app/models` para no volver a
descargar los pesos en cada deploy, y otro (o el mismo) en `/app/data` para
conservar `api.db`. Si ves errores de permisos en el volumen con el usuario no
root de la imagen, elimina el volumen (los datos son solo de demo) o monta el
volumen y ajusta el UID del servicio. El histórico del dashboard no es crítico
para la demo.

## 3. Desplegar el frontend (Vercel o Netlify)

El front es estático (Vite). En Vercel:

1. **Add New Project → Import Git Repository** → elige el repo.
2. **Root Directory:** `frontend`.
3. Build command: `pnpm install && pnpm build` (o `npm install && npm run build`).
4. Output directory: `dist`.
5. **Environment Variable:** `VITE_API_URL=https://TU-URL.up.railway.app`.
6. Deploy. Copia la URL final del front.

Luego vuelve a Railway y ajusta CORS:

```
NLP_CORS_ORIGINS=["https://tu-front.vercel.app"]
```

Si usas Netlify: build command `pnpm build`, publish directory `frontend/dist`,
y la misma variable `VITE_API_URL`.

## 4. Probar la app desplegada

- Salud: `GET https://TU-URL/v1/health`
- Modelos: `GET https://TU-URL/v1/models` (muestra motor, umbrales y si está
  degradado)
- Documentación: `https://TU-URL/docs` → puedes probar `POST /v1/analyze`
  directamente desde Swagger (evita problemas de codificación de PowerShell).
- Ingesta real: `POST /v1/sources/scan` con
  `{"url": "https://www.eltiempo.com", "maxArticles": 2}` y consulta
  `GET /v1/sources/jobs/{id}`.
- Dashboard: `GET /v1/dashboard/overview`, `/v1/dashboard/corpus`,
  `/v1/dashboard/models`.
- Front: abre la URL de Vercel y prueba las 4 pestañas.

Ejemplo de análisis con PowerShell (bytes UTF-8, evita el error de parsing):

```powershell
$json = @{ text = "La ola de inseguridad en la frontera preocupa a los habitantes de Cúcuta." } | ConvertTo-Json
$body = [System.Text.Encoding]::UTF8.GetBytes($json)
Invoke-RestMethod -Method Post -Uri "https://TU-URL/v1/analyze" `
  -ContentType "application/json; charset=utf-8" -Body $body | ConvertTo-Json -Depth 4
```

## 5. Alternativa gratis con BETO real: Hugging Face Spaces

HF Spaces (Docker, CPU básico) da ~16 GB de RAM gratis para Spaces públicos, y
sirve para una demo. Pasos resumidos:

1. Crea un Space → SDK **Docker** → plantilla en blanco.
2. Copia el contenido de `api/` al repo del Space (o conecta el repo con el
   `Dockerfile.models`).
3. Sube el ZIP de modelos al propio Space (o usa `NLP_MODELS_ARCHIVE_URL`).
4. En el `README.md` del Space añade:
   ```
   ---
   title: Migra Venezuela API
   sdk: docker
   app_port: 8000
   ---
   ```
5. Variables del Space: `NLP_ENGINE=bert_pair`,
   `NLP_MODELS_ARCHIVE_URL=...`, `NLP_REQUIRE_MODELS=true`,
   `NLP_CORS_ORIGINS=["*"]`.
6. La URL será `https://<usuario>-<space>.hf.space` (API en `/docs`).

## 6. Troubleshooting

| Síntoma | Causa / solución |
|---|---|
| Build falla en Railway | Revisa que **Root Directory** sea `api` y la rama `integrado`; logs de build en Railway. |
| Deploy “crashed” al arrancar | Suele ser OOM con `Dockerfile.models`; usa plan Hobby/2 GB o el modo léxico. |
| `/v1/health` tarda en responder | Primer arranque descargando/cargando BETO; el healthcheck espera hasta 300 s. |
| `/v1/dashboard/corpus` da 503 | La imagen incluye `app/resources/corpus_labeled.csv`; si lo borras, vuelve a copiarlo desde `Data/` y redeploy. |
| CORS bloquea el front | `NLP_CORS_ORIGINS` debe incluir la URL exacta del front (JSON). |
| API key activa y el front falla 401 | Define `VITE_API_KEY` en el front o quita `NLP_API_KEY`. |
| PowerShell “error parsing the body” | Usa Swagger `/docs` o bytes UTF-8 (ver arriba). |
