# cultural_bias

Cultural Bias tiene como finalidad el entrenamiento y evaluación de modelos de procesamiento de lenguaje natural destinados a detectar patrones de sesgo cultural en la cobertura mediática de la migración venezolana.


Para ello, el proyecto consiste en la recopilación, procesamiento y análisis de noticias relacionadas con este fenómeno en Colombia y México, con el propósito de construir un corpus lingüístico especializado.

## Flujo de datos y ciclo de vida ML



```text
Fuentes de noticias
        ↓
Extracción web (extraction/)
        ↓
Datos recopilados (CSV)
        ↓
Transformación, anonimización y preparación (Transformation/)
        ↓
Revisión y etiquetado humano
        ↓
Corpus etiquetado y preprocesado
        ↓
Entrenamiento y evaluación NLP (modelling/)
        ↓
Modelo y umbrales
        ↓
Aplicación de inferencia (app/)
```

- **Extracción:** recopila artículos de las fuentes configuradas y los guarda
  en archivos CSV.
- **Transformación y etiquetado:** limpia y prepara los datos. Cuando se
  requiere revisión humana, se exportan para etiquetado y luego se integran las
  etiquetas antes de generar los datos de entrenamiento.
- **Aprendizaje automático:** entrena y evalúa los modelos con el corpus
  preparado; esta etapa no forma parte del ETL.
- **Inferencia:** la aplicación recibe el texto de una noticia y presenta las
  predicciones del modelo entrenado.

Los archivos CSV funcionan como almacenamiento entre etapas; no se presupone
una base de datos ni servicios separados. Los datos originales, las versiones
anonimizadas y los conjuntos usados para etiquetado o entrenamiento deben
gestionarse según sus requisitos de acceso y confidencialidad.

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

## Comparación de modelos

BETO, XLM-RoBERTa y DistilBETO comparten el mismo preprocesamiento,
entrenamiento multitarea y evaluación OOF. Ejecuta cada validación cruzada con
los mismos datos, semilla, número de folds y longitud máxima:

```powershell
python modelling\beto\train.py --stage cv
python modelling\roberta_es\train.py --stage cv
python modelling\distilbert_es\train.py --stage cv
python modelling\compare_models.py
```

Los modelos preentrenados se descargan desde Hugging Face la primera vez. Cada
entrenamiento guarda sus resultados en `metrics.json`; la comparación se ordena
por F1 macro de temas y genera `modelling\model_comparison.csv`. Para guardar
también el checkpoint final, ejecuta cada entrenamiento con `--stage all`.

## Dashboard y API de análisis

La aplicación de `app/app.py` usa el checkpoint BETO de
`modelling/beto/models_beto/beto_multitask.pt` y el mismo preprocesamiento de
`modelling/beto/infer.py`. El dashboard permite analizar texto pegado o buscar
y clasificar noticias con el scrapper de La Crónica de Hoy.

Instala los requisitos del proyecto y Playwright/Chromium si aún no están
configurados; luego inicia desde la raíz del repositorio:

```powershell
python -m pip install -r requirements.txt
python -m spacy download es_core_news_lg
python -m playwright install chromium
python app\app.py
```

La interfaz se sirve en `http://127.0.0.1:7860`; el esquema interactivo de la
API está disponible en `http://127.0.0.1:7860/gradio_api/info`. Los endpoints
son `analizar_noticia` (recibe el texto de una noticia) y `recolectar_cronica`
(recibe el máximo de artículos entre 1 y 30). La respuesta de análisis incluye
la clase de sentimiento, sus probabilidades y los cinco encuadres con
probabilidades, umbrales y estado de detección. Se pueden invocar desde un
cliente compatible con Gradio:

```python
from gradio_client import Client

client = Client("http://127.0.0.1:7860")
prediccion = client.predict(
    "Texto completo de la noticia",
    api_name="/analizar_noticia",
)
```

### Crear un Droplet con Terraform

La configuración está en `terraform/main.tf`. Define `DIGITALOCEAN_TOKEN` y
aplica la huella de una clave SSH registrada en tu cuenta:

```bash
export DIGITALOCEAN_TOKEN="tu_token"
cd terraform
terraform init
terraform apply -var='ssh_key_fingerprints=["HUELLA_SSH"]'
```

Terraform muestra la IP pública al finalizar. Este recurso crea infraestructura
facturable; para eliminar el Droplet ejecuta `terraform destroy` desde `terraform/`.