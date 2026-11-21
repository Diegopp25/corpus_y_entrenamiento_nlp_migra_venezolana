# Desplegar gratis con BETO real: Hugging Face Spaces (Docker)

Es la opción **gratuita sin tarjeta** que sí aguanta los dos modelos BETO:
CPU Basic = **2 vCPU / 16 GB RAM / 50 GB de disco**, para Spaces públicos.
Railway Free, Render Free y Koyeb Free dan 0.5–0.5 GB de RAM, insuficiente
para torch + dos BERT (~2 GB).

> Limitaciones del plan gratis: el Space es **público** (código y API visibles)
> y **se duerme tras un tiempo de inactividad**; el primer acceso tras dormir
> tarda ~30–90 s en despertar y cargar los modelos.

## 0. Antes de empezar

- Cuenta gratis en [Hugging Face](https://huggingface.co).
- El ZIP con los dos modelos (`modelos_beto.zip`, ~880 MB) creado con:

  ```powershell
  Compress-Archive `
    -Path "C:\Users\diego\Desktop\proyecto\modelo_sentimiento", "C:\Users\diego\Desktop\proyecto\modelo_encuadre" `
    -DestinationPath "$env:USERPROFILE\Desktop\modelos_beto.zip" -Force
  ```

- Sube ese ZIP a un **GitHub Release** del proyecto (o a un repo de modelos de
  Hugging Face) y copia la URL pública del archivo. El Space la descargará al
  arrancar con `NLP_MODELS_ARCHIVE_URL`.

## 1. Preparar la carpeta del Space en tu PC

Desde la raíz del repo:

```powershell
# Crea una carpeta con el contenido de api/ listo para un Space Docker
powershell -ExecutionPolicy Bypass -File deploy\prepare_hf_space.ps1
```

El script deja todo en `$env:USERPROFILE\Desktop\hf-space-migra-api`:

- `Dockerfile` (copia de `api/Dockerfile.models`, con torch/transformers)
- `app/`, `scripts/`, `requirements*.txt`, `artifacts/`,
  `app/resources/corpus_labeled.csv`
- `README.md` con el metadata `sdk: docker` y `app_port: 8000`

Revisa que **no** se haya copiado `.env` ni `models/`. Si quieres, borra
`tests/` y `docker-compose.yml` para aligerar.

## 2. Crear el Space y subir el código

1. Hugging Face → **New → Space**:
   - Nombre: `migra-venezuela-api`
   - SDK: **Docker** → plantilla **Blank**
   - Hardware: **CPU basic (free)**
   - Visibilidad: **Public**
2. Clona el Space recién creado y copia dentro el contenido preparado:

   ```powershell
   git clone https://huggingface.co/spaces/TU_USUARIO/migra-venezuela-api
   Copy-Item "$env:USERPROFILE\Desktop\hf-space-migra-api\*" `
     .\migra-venezuela-api -Recurse -Force
   cd .\migra-venezuela-api
   git add .
   git commit -m "API FastAPI migración venezolana"
   git push
   ```

   La primera vez pide usuario y **token de Hugging Face** como contraseña
   (Settings → Access Tokens → token con permiso *write*).

## 3. Variables del Space

En el Space → **Settings → Variables and secrets**:

| Variable | Valor |
|---|---|
| `NLP_ENGINE` | `bert_pair` |
| `NLP_MODELS_ARCHIVE_URL` | URL del ZIP de modelos |
| `NLP_MODELS_DIR` | `/app/models` |
| `NLP_REQUIRE_MODELS` | `true` |
| `NLP_DEVICE` | `cpu` |
| `NLP_CORS_ORIGINS` | `["*"]` (o la URL de tu front) |
| `NLP_DATABASE_PATH` | `/app/data/api.db` |
| `NLP_LOG_LEVEL` | `INFO` |

El Space reconstruye la imagen al guardar. En los logs verás algo como
`[modelos] descargando pesos...` y luego `[start] arrancando API`.

## 4. Probar

- URL del Space: `https://TU_USUARIO-migra-venezuela-api.hf.space`
- Salud: `https://.../v1/health` → `{"status":"ok","engine":{"selected":"bert_pair"}}`
- Docs: `https://.../docs` (prueba `POST /v1/analyze` desde Swagger)
- Análisis:
  `POST /v1/analyze` con `{"text": "..."}` (mejor con el cuerpo completo de una
  noticia)
- Ingesta: `POST /v1/sources/scan` con `{"url":"https://www.eltiempo.com"}`
- Dashboard: `/v1/dashboard/overview`, `/v1/dashboard/corpus`,
  `/v1/dashboard/models`

## 5. Frontend gratis (Vercel/Netlify)

1. Vercel → **Add New Project** → importa el repo de GitHub.
2. **Root Directory:** `frontend`; build `pnpm build` (o `npm run build`);
   output `dist`.
3. Variable `VITE_API_URL=https://TU_USUARIO-migra-venezuela-api.hf.space`.
4. Deploy y copia la URL del front.
5. En el Space, actualiza `NLP_CORS_ORIGINS` con la URL del front.

## 6. Si algo falla

| Síntoma | Solución |
|---|---|
| El Space se queda en “Building” | Revisa logs; la instalación de torch tarda varios minutos la primera vez. |
| `OOM` / reinicio | CPU Basic da 16 GB; si pasa, revisa que no se estén cargando modelos dos veces. |
| `degraded: true` en `/v1/health` | La descarga del ZIP falló: revisa la URL y los logs `[modelos]`. |
| Primera petición lenta | El Space dormido despierta y carga BETO (~30–90 s). |
| CORS | `NLP_CORS_ORIGINS` debe incluir la URL exacta del front. |

## Alternativa: Oracle Cloud Always Free (24 GB RAM, siempre encendido)

Si no te importa configurar una VM: **4 OCPU / 24 GB RAM ARM gratis para
siempre** (Oracle Cloud Always Free). Instalas Docker, `git clone` del repo,
`docker build -f api/Dockerfile.models` y expones el puerto 8000 detrás de un
proxy con HTTPS (Caddy/Nginx). Es la opción gratuita más potente, pero requiere
tarjeta de verificación y más pasos que un Space.
