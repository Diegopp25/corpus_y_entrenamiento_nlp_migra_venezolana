# Evidencias de la API desplegada

Fecha de captura: **23 de noviembre de 2026**  
API: **https://20-226-99-99.sslip.io**  
Swagger: **https://20-226-99-99.sslip.io/docs**  
Motor verificado: **`bert_pair`** (BETO sentimiento + BETO encuadres, CPU).

## Capturas

| Archivo | Qué muestra |
|---|---|
| `01_swagger_docs.png` | Swagger/OpenAPI público de la API en Azure, con los endpoints reales. |
| `02_api_demo.png` | Evidencia en vivo: health con motor `bert_pair`, modelos cargados, un `POST /v1/analyze` real y métricas del dashboard. |
| `03_health_json.png` | Respuesta JSON de `/v1/health`: estado, motor, rutas de modelos, labels. |
| `04_dashboard_json.png` | Respuesta JSON de `/v1/dashboard/models`. |

La página `demo_api.html` es la que se usó para la captura `02_api_demo.png`; hace las peticiones reales a la API al abrirse.

## Pruebas ejecutadas

| Evidencia | Resultado |
|---|---|
| `pytest_suite.txt` + `junit_suite.xml` | Suite de la API: **93 pruebas, 0 fallos** (sin las pruebas que requieren pesos BETO). |
| `pytest_real_models.txt` + `junit_real.xml` | Pruebas de integración con los **pesos BETO reales**: **2 pruebas, 0 fallos**. |
| `pytest_live_api.txt` + `junit_live.xml` | Pruebas contra la **API desplegada en Azure**: **4 pruebas, 0 fallos**. |
| `live_api_check.txt` | Smoke test de conectividad: **6/6 PASS** (health, docs, OpenAPI, analyze, dashboard, metrics). |

### Cómo reproducirlas

```powershell
# 1) Suite normal (rápida, sin cargar BETO)
$py = "C:\Users\diego\Documents\deepseek-harness\default-workspace\migra-nlp\api\.venv\Scripts\python.exe"
cd C:\Users\diego\Documents\deepseek-harness\default-workspace\migra-nlp\src\cultural_bias\api
& $py -m pytest -q -m "not real_models"

# 2) Pruebas con los pesos BETO reales
$env:NLP_SENTIMENT_MODEL_DIR="C:\Users\diego\Desktop\proyecto\modelo_sentimiento"
$env:NLP_FRAMES_MODEL_DIR="C:\Users\diego\Desktop\proyecto\modelo_encuadre"
& $py -m pytest tests\test_engine_real.py -q -m real_models

# 3) Pruebas de conectividad contra la API desplegada
$env:LIVE_API_URL="https://20-226-99-99.sslip.io"
& $py -m pytest tests\test_live_api.py -q
& $py scripts\check_live_api.py
```

## Qué valida cada grupo

- `tests/test_health.py`: `/v1/health` responde y reporta el motor correcto.
- `tests/test_analyze.py` y `tests/test_contract.py`: contrato de `/v1/analyze`, `/v1/analyze/batch`, historial y validaciones.
- `tests/test_engine_real.py`: los dos BETO cargan y una noticia negativa conocida se clasifica como `Negativo` con el encuadre `Seguridad` en el top-3.
- `tests/test_live_api.py`: contra la URL pública real comprueba health, OpenAPI, análisis, dashboard y métricas.
- `scripts/check_live_api.py`: smoke test legible de extremo a extremo, pensado para el informe.

## Nota sobre las métricas

El dashboard muestra las métricas del artefacto de evaluación del corpus etiquetado
(156 noticias). La evaluación es **in-sample** (se usó parte del corpus para ajustar
umbrales), así que sirve como referencia del proyecto, no como validación independiente.
