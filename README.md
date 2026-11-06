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