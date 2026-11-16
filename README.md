# cultural_bias

Cultural Bias tiene como finalidad el entrenamiento y evaluación de modelos de procesamiento de lenguaje natural destinados a detectar patrones de sesgo cultural en la cobertura mediática de la migración venezolana.


Para ello, el proyecto consiste en la recopilación, procesamiento y análisis de noticias relacionadas con este fenómeno en Colombia y México, con el propósito de construir un corpus lingüístico especializado.

## Estructura del repositorio

```text
CulturalBias
├── Extraction
│   ├── Scrapers para fuentes colombianas
│   ├── Scrapers para fuentes mexicanas
│   └── full_extraction.py
│       └── Ejecuta todos los procesos de extracción y almacena los datos en CSV
│
├── Transformation
│   ├── LandindStage
│   │   └── Archivos CSV con datos brutos y procesados
│   └── Preparación de datos para entrenamiento
│
├── check_robots.py
│   └── Verifica si los sitios web permiten extracción automatizada de contenido
│
├── .gitignore
├── LICENSE.txt
└── README.md
```

## Instalación 

```powershell
python -m pip install -r requirements.txt
python -m spacy download es_core_news_lg
python -m playwright install chromium
```

El proyecto carga `es_core_news_lg` en el preprocesamiento. Si se usa PyTorch
con GPU, instala la compilación compatible con la versión de CUDA y el equipo
desde el selector oficial de PyTorch; la instalación de `torch` puede variar
según el hardware.

## API (FastAPI)

El repositorio incluye una API HTTP en [`api/`](api/) que expone todo el
pipeline de análisis y lo deja listo para que un frontend lo consuma:

- **Análisis**: sentimiento (BETO), 7 encuadres noticiosos y sesgo cultural
  (hipótesis Colombia–México) — `POST /v1/analyze` y `POST /v1/analyze/batch`.
- **Ingesta de noticias**: rastreo de medios, extracción de contenido y análisis
  asíncrono con jobs y progreso — `/v1/sources/*`.
- **Dashboard**: agregados por sentimiento, encuadres, país, medio y latencias,
  además del corpus etiquetado y las métricas reales de evaluación —
  `/v1/dashboard/*`.
- **Monitoreo**: métricas Prometheus en `/metrics` y estadísticas en
  `/v1/monitoring/stats`.
- **Persistencia**: SQLite (WAL) para análisis, jobs y eventos; pesos BETO fuera
  del repositorio y artefactos regenerables (`thresholds.json`,
  `evaluation.json`).

Arranque rápido (desde `api/`):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\scripts\run_dev.ps1 -Reload
```

Documentación:

- [`api/README.md`](api/README.md) — instalación, configuración, modelos BETO,
  ejemplos `curl` y tabla de endpoints.
- [`docs/API.md`](docs/API.md) — contrato completo de cada endpoint y
  compatibilidad con los tipos del frontend.
- [`docs/FRONTEND.md`](docs/FRONTEND.md) — cómo migrar el frontend de los datos
  simulados (`nlpAnalyzer.ts`, `newsScraperService.ts`, `modelMetrics.ts`) al API.
- [`docs/OPERACIONES.md`](docs/OPERACIONES.md) — Docker, monitoreo Prometheus,
  backups SQLite, seguridad y troubleshooting.
- [`integrations/frontend-api-client.ts`](integrations/frontend-api-client.ts) —
  cliente TypeScript tipado (sin dependencias).
- CI: [`.github/workflows/api-tests.yml`](.github/workflows/api-tests.yml)
  ejecuta la suite de `api/tests` en Ubuntu con Python 3.12 (sin modelos reales).

> Nota: el corpus etiquetado real tiene **156 artículos**; las cifras de la
> maqueta del frontend (1.420 artículos, ~89 % de accuracy) son ficticias. La
> evaluación real de los modelos está en `api/artifacts/evaluation.json` y se
> sirve en `GET /v1/dashboard/models`.
