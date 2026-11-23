# Desplegar gratis en Render (modo léxico)

Hugging Face dejó de permitir Docker Spaces gratis (ahora pide PRO), así que la
opción gratis inmediata es **Render Free**: 512 MB de RAM, 0.1 CPU, duerme tras
15 minutos sin tráfico. Alcanza para el API con el **motor léxico** (sin torch).
Para BETO real hace falta más RAM: Oracle Cloud Always Free (24 GB, ver
`DEPLOY_HF_SPACES.md`) o un plan pagado.

## Pasos

1. Entra a <https://dashboard.render.com> e inicia sesión con **GitHub**.
2. **New → Blueprint** → elige el repositorio del proyecto.
3. Render detecta [`render.yaml`](../render.yaml) en la raíz y propone el
   servicio `migra-venezuela-api` (Docker, plan free).
4. Clic en **Apply / Deploy**. La primera build tarda unos minutos.
5. Cuando termine, copia la URL (`https://migra-venezuela-api.onrender.com` o
   similar) y prueba:
   - `https://TU-URL.onrender.com/v1/health`
   - `https://TU-URL.onrender.com/docs`

La primera petición después de dormir tarda ~30–60 s en despertar.

## Variables

Ya están en `render.yaml`:

| Variable | Valor |
|---|---|
| `NLP_ENGINE` | `lexicon` (análisis con el motor de respaldo) |
| `NLP_ENVIRONMENT` | `prod` |
| `NLP_CORS_ORIGINS` | `["*"]` (luego pon la URL del frontend) |
| `NLP_DATABASE_PATH` | `/app/data/api.db` (efímero en el plan free) |

El corpus para `/v1/dashboard/corpus` va incluido en la imagen
(`app/resources/corpus_labeled.csv`), así que el dashboard funciona.

## Frontend gratis

Vercel → importa el repo → **Root Directory** `src/cultural_bias/frontend` →
build `pnpm build` → output `dist` → variable
`VITE_API_URL=https://TU-URL.onrender.com` → Deploy. Después actualiza
`NLP_CORS_ORIGINS` en Render con la URL del front.

## Si quieres BETO real gratis

- **Oracle Cloud Always Free**: VM ARM con 4 OCPU / 24 GB RAM; se instala Docker
  y se corre `src/cultural_bias/api/Dockerfile.models`. Requiere cuenta con
  tarjeta de verificación (no cobra) y unos 15–20 minutos de configuración.
- Alternativa pagada pequeña: Hugging Face PRO (~$9/mes) o Railway Hobby
  (~$5/mes) con el Dockerfile de modelos ya preparado.
