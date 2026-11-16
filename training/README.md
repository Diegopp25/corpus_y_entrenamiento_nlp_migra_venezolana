# Balanceo y reentrenamiento de los BETO

Pipeline reproducible para **balancear** el corpus etiquetado y **reentrenar** las
dos cabezas BETO del proyecto (*sentimiento* de 3 clases y *encuadres* de 7
salidas multi-etiqueta), con una evaluación **honesta fuera de muestra**
(validación cruzada) y comparación contra los modelos que hoy están en
producción.

Pregunta que responde este directorio: *¿el balanceo + reentrenamiento mejora de
verdad a los modelos actuales lo suficiente como para reemplazarlos?*

> **Veredicto corto (resultados reales, sin maquillar):**
>
> * **Sentimiento: NO mejora, empeora.** macro-F1 0.531 ± 0.092 frente a
>   0.590 ± 0.051 de los modelos actuales en los mismos folds
>   (Δ **−0.059**, solo 2 de 5 folds mejoran).
> * **Encuadres: SÍ mejora, pero solo en las etiquetas raras.** macro-F1 a
>   umbral 0.5: **0.463 ± 0.050 vs 0.366 ± 0.048** (Δ **+0.097**; **5 de 5
>   folds** mejoran). La ganancia viene de `integración social` (+0.31),
>   `otros` (+0.25) y `empleo y economía` (+0.21); `tránsito`, `acceso` y
>   `seguridad` quedan levemente peores.
> * **El "balanceo" no arregla el sesgo cultural por sí solo.** El
>   reentrenamiento con `class_weight` sobre-predice `Positivo` (recall 0.73 vs
>   0.33) pero hunde su precisión (0.38 vs 0.75) y pierde macro-F1 global.
> * **No reemplazar el modelo de sentimiento.** El de encuadres es un candidato
>   serio, pero **solo tras validarlo en noticias nuevas fuera del corpus**
>   (ver [Recomendación](#10-recomendación)).
> * La elección de umbrales en validaciones de 25 noticias es inestable: el
>   piso de precisión estricto baja el macro-F1 de 0.465 a 0.378, así que el
>   `thresholds.json` recomendado conserva **0.5** en todas las etiquetas.

---

## 1. Qué hay y qué se hizo

| Pieza | Archivo | Descripción |
|---|---|---|
| Pipeline | [`training/train_models.py`](train_models.py) | CLI `argparse`: carga y deduplica CSVs, CV estratificada, balanceo por pesos, early stopping, umbrales solo con validación, baseline comparable, modelos finales, artefactos. |
| Umbrales | [`training/recompute_thresholds.py`](recompute_thresholds.py) | Recalcula/audita los umbrales finales desde `artifacts/cv_folds/fold_*.json` sin reentrenar (~5 s). |
| Verificación | [`training/verify_retrained.py`](verify_retrained.py) | Carga los modelos retrenados con el `BertPairEngine` real de la API y predice una noticia del corpus. |
| Dependencias | [`training/requirements-train.txt`](requirements-train.txt) | `torch`, `transformers`, `scikit-learn`, `pandas`, `numpy` (CPU). |
| Modelos | `training/models/bert-sentiment-retrained/` y `training/models/bert-frames-retrained/` | `save_pretrained` (gitignored, ~440 MB cada uno). |
| Artefactos | `training/artifacts/` | `retraining_evaluation.json`, `thresholds.json`, `baseline_predictions.json`, `cv_folds/fold_*.json`, `retraining.log`. |

Los pesos actuales de `C:\Users\diego\Desktop\proyecto\modelo_sentimiento` y
`...\modelo_encuadre` **no se modifican**: solo se leen como punto de partida.

---

## 2. Análisis de balance del corpus

### 2.1 `dataset_balanced.csv` no está balanceado: está *sobremuestreado*

| Archivo | Filas | Artículos únicos | Filas duplicadas |
|---|---:|---:|---:|
| `Data/dataset_balanced.csv` | 237 | **116** | 121 (51.1 %) |
| `Data/dataset_migracion_venezolana_labeled.csv` | 156 | **156** | 0 |

`dataset_balanced.csv` se generó duplicando filas con reemplazo hasta dejar
79/79/79 en sentimiento (ver `modelling/balance.py`). El "balance" es artificial:
sus 116 artículos únicos **son un subconjunto** de los 156 del CSV etiquetado, y
el 100 % de las etiquetas coincide. Por tanto:

* la *unión deduplicada* de ambos CSV son **156 artículos únicos**, no 393;
* usar el CSV de 237 filas tal cual en una validación cruzada **filtra
  información**: el mismo artículo cae a la vez en train y en test y las
  métricas se inflan. `train_models.py` deduplica por texto antes de partir los
  folds.

Distribución real del corpus único (156):

| Sentimiento | Artículos | % |
|---|---:|---:|
| Neutro | 79 | 50.6 % |
| Negativo | 44 | 28.2 % |
| Positivo | 33 | 21.2 % |

### 2.2 Sentimiento por país (el desbalance que importa)

| País | Neutro | Negativo | Positivo | Total |
|---|---:|---:|---:|---:|
| Colombia | 34 | 16 | 27 | 77 |
| México | 45 | 28 | 6 | 79 |
| **Total** | **79** | **44** | **33** | **156** |

Dos patrones claros de sesgo cultural en el etiquetado:

* **Positivo es casi colombiano**: 27 de 33 artículos positivos (82 %) son de
  Colombia; en México solo hay 6.
* **Negativo es mayoritariamente mexicano**: 28 de 44 (64 %) son de México.

`Medio` está alineado con el país (Semana = Colombia, Milenio = México), así que
"balancear por país" y "balancear por medio" son casi la misma intervención.

### 2.3 Encuadres: soporte y porcentaje de artículos con cada frame (n=156)

| frame_id canónico | Columna del CSV | Artículos | % del corpus |
|---|---|---:|---:|
| `politica_migratoria` | `Politica_migratoria` | 98 | 62.8 % |
| `transito_migratorio` | `Transito_migratorio` | 53 | 34.0 % |
| `acceso_servicios` | `Acceso_a_servicios` | 45 | 28.8 % |
| `seguridad` | `Seguridad` | 40 | 25.6 % |
| `empleo_economia` | `Empleo_y_economía` | 29 | 18.6 % |
| `integracion_social` | `Integración_social` | 27 | 17.3 % |
| `otros` | `Otros` | 12 | 7.7 % |

Es un problema **multi-etiqueta desbalanceado**: `politica_migratoria` aparece
en 2 de cada 3 noticias, mientras `otros` solo en 12 artículos (el 7.7 %), y
`empleo_economia`/`integracion_social` en menos de una de cada cinco.

Número de frames activos por artículo (n=156): 1 frame = 55 (35.3 %), 2 = 63
(40.4 %), 3 = 30 (19.2 %), 4 = 7 (4.5 %), 5 = 1 (0.6 %); ningún artículo sin
frame. Es decir, **la mayoría de los artículos activa 2–3 frames**, lo que
justifica `pos_weight` por etiqueta y no un simple `0.5` para todo.

Frecuencia de cada frame por país (esto es el sesgo cultural del corpus):

| Encuadre | Colombia (n=77) | México (n=79) |
|---|---:|---:|
| `empleo_economia` | **32.5 %** | **5.1 %** |
| `integracion_social` | **29.9 %** | **5.1 %** |
| `transito_migratorio` | **16.9 %** | **50.6 %** |
| `seguridad` | **18.2 %** | **32.9 %** |
| `politica_migratoria` | 70.1 % | 55.7 % |
| `acceso_servicios` | 29.9 % | 27.8 % |
| `otros` | 9.1 % | 6.3 % |

La cobertura colombiana habla de empleo, integración y política; la mexicana de
tránsito y seguridad. Cualquier modelo entrenado con estas proporciones
aprenderá que "empleo" es un tema colombiano y "tránsito" un tema mexicano.

### 2.4 Tamaño de los textos

`Cuerpo` (texto crudo, lo que usa el motor de producción): 460 ± 255 palabras,
2.888 caracteres de media (mín. 594, máx. 9.629). Con `max_len=256` tokens se
trunca una parte importante de los artículos largos (ver Limitaciones).

---

## 3. Pipeline: decisiones de evaluación honesta

### 3.1 Validación cruzada con test intacto

* `StratifiedKFold` (5 folds por defecto) **estratificado por sentimiento**
  sobre los 156 artículos únicos. El mismo split de filas se usa para sentimiento
  y para encuadres (así ambos modelos se comparan sobre exactamente las mismas
  noticias).
* De cada fold se aparta un **test intacto**; el resto se divide en
  **train/validación** (80/20, estratificado). Resultado típico por fold:
  train ≈ 99, validación ≈ 25, test ≈ 32.
* **Early stopping por macro-F1 de validación** con restauración del mejor
  estado.
* Los umbrales de encuadres se eligen **solo con la validación del fold** y se
  evalúan en el test. Las métricas que se reportan salen del test.

### 3.2 Balanceo aplicado (sin duplicar filas de test)

* **Sentimiento**: `CrossEntropyLoss` con `class_weight="balanced"` calculado
  *solo con el train de cada fold* (en la práctica ≈ `[1.18, 0.66, 1.57]`).
* **Encuadres**: `BCEWithLogitsLoss` con `pos_weight = negativos/positivos` por
  etiqueta, también calculado solo con el train del fold y **topado en 20**
  (evita pesos explosivos con etiquetas de 3–5 positivos). En la corrida real:
  `otros` es la etiqueta con el `pos_weight` más alto y `politica_migratoria` la
  más baja (es la más frecuente).
* No se duplican artículos: el "balanceo" es a nivel de función de pérdida, que
  es lo correcto cuando hay tan pocos datos (evita empeorar el sobreajuste y no
  contamina la validación).

### 3.3 Umbrales de encuadres

* Grid **0.20–0.80** (paso 0.05) y **piso de precisión 0.50**.
* Criterio: entre los umbrales que alcanzan precisión ≥ 0.50 en validación, se
  elige el de mayor F1 (desempate por mayor precisión y luego mayor umbral). Si
  ningún umbral alcanza el piso (habitual con etiquetas de 12 positivos en todo
  el corpus), queda 0.50 por defecto y se marca `fallback`.
* Los **umbrales finales** se eligen con las predicciones de validación de los 5
  folds (nunca con test) y se guardan en `training/artifacts/thresholds.json`
  con **ids canónicos** (`acceso_servicios`, `transito_migratorio`, ...), que es
  lo que espera `load_thresholds` de la API.
* **Salvaguarda anti-sobreajuste** (implementada en
  `train_models.guard_thresholds`): si el umbral elegido con el piso de
  precisión tiene **peor F1 que el umbral por defecto 0.5 en la misma
  validación**, se conserva 0.5. Con 25 ejemplos de validación por fold, el piso
  de precisión puede empujar el umbral a 0.65 y subir la precisión a costa de
  hundir el recall (y el F1). Los umbrales estrictos con piso quedan guardados
  para trazabilidad en `artifacts/thresholds_precision_floor_estricto.json` y
  los F1-óptimos sin piso en `artifacts/thresholds_alt_max_f1.json`. Ver
  [Resultados](#5-resultados-cv-fuera-de-muestra).

### 3.4 Baseline manzana-con-manzana

Los modelos actuales de Desktop se evalúan **una vez** sobre los 156 artículos y
luego se recortan con los mismos folds de test y el mismo `max_len` que los
reentrenados. Sus umbrales también se eligen con la validación de cada fold. La
comparación reporta la diferencia *paired* por fold
(`retrenado − baseline`) para no depender de la media global.

---

## 4. Comandos exactos

### 4.1 Entorno

```powershell
$py = "C:\Users\diego\Documents\deepseek-harness\default-workspace\migra-nlp\api\.venv\Scripts\python.exe"
```

No hacen falta dependencias nuevas: `torch 2.14.1+cpu`, `transformers 5.20.2`,
`scikit-learn 1.9.1`, `pandas 3.0.5`, `numpy 2.5.2`.

### 4.2 Corrida usada para este informe (config reducida por CPU)

Los defaults del script son `--folds 5 --epochs 3 --max-len 384`, pero en esta
máquina (CPU sin AVX-512, compartida) un paso de entrenamiento de batch 8 con
256 tokens tardó ~7 s y con 384 ~11 s. Para respetar el presupuesto se usó la
siguiente configuración, **documentada y reproducible**:

```powershell
$env:PYTHONPATH = "api"
& $py training/train_models.py `
    --folds 5 --epochs 1 --max-len 256 `
    --batch-size 8 --lr 2e-5 --seed 42 --num-threads 8 `
    --sent-model-dir "C:\Users\diego\Desktop\proyecto\modelo_sentimiento" `
    --frames-model-dir "C:\Users\diego\Desktop\proyecto\modelo_encuadre"
```

Tiempo total de la corrida: **28,2 min** en CPU (5 folds × 2 modelos + modelos
finales + inferencia del baseline; 1.691 s). La corrida se hizo con 1 época
porque cada paso de entrenamiento de batch 8 × 256 tokens tarda ~7 s en esta
máquina; **los defaults del script siguen siendo `--folds 5 --epochs 3
--max-len 384`** y conviene repetir con ellos en GPU antes de tomar una decisión
definitiva (los resultados de sentimiento son sensibles a épocas y truncación).

### 4.3 Corrida con los valores por defecto (más CPU/GPU)

```powershell
$env:PYTHONPATH = "api"
& $py training/train_models.py
```

Todas las salidas van a `training/models/` y `training/artifacts/`; se puede
cambiar con `--out-dir` y `--artifacts-dir`. `--skip-final` entrena solo la CV.

### 4.4 Verificación con el motor real de producción

```powershell
$env:PYTHONPATH = "api"
& $py training/verify_retrained.py --index 0 --device cpu
```

---

## 5. Resultados CV (fuera de muestra)

5 folds estratificados por sentimiento sobre 156 artículos únicos; test de cada
fold intacto (≈ 31 noticias), validación ≈ 25, entrenamiento ≈ 99. Todas las
métricas de esta sección salen del **test** de cada fold (media ± desviación
típica entre folds).

### 5.1 Sentimiento

| Métrica (test) | Reentrenado | Modelos actuales (baseline) | Δ (retr. − base) |
|---|---:|---:|---:|
| Accuracy | 0.551 ± 0.108 | 0.635 ± 0.043 | **−0.084** (mejora en 2/5 folds) |
| **Macro-F1** | **0.531 ± 0.092** | **0.590 ± 0.051** | **−0.059** (2/5 folds) |
| Macro-precisión | 0.595 ± 0.081 | 0.684 ± 0.099 | −0.089 |
| Macro-recall | 0.575 ± 0.084 | 0.611 ± 0.043 | −0.036 |

Por clase:

| Clase | F1 reentrenado | F1 baseline | Δ | P / R reentrenado | P / R baseline |
|---|---:|---:|---:|---:|---:|
| Negativo | 0.500 ± 0.150 | 0.627 ± 0.026 | −0.127 | 0.567 / 0.475 | 0.494 / 0.867 |
| Neutro | 0.604 ± 0.150 | 0.711 ± 0.070 | −0.107 | 0.837 / 0.517 | 0.809 / 0.634 |
| Positivo | 0.488 ± 0.092 | 0.433 ± 0.127 | **+0.055** | 0.380 / **0.733** | 0.750 / 0.333 |

Matriz de confusión sumada de los 5 folds (filas = real, columnas = predicho,
orden Negativo/Neutro/Positivo):

```text
reentrenado : [[21,  7, 16],      baseline : [[38,  5,  1],
               [12, 41, 26],                 [24, 50,  5],
               [ 5,  4, 24]]                 [15,  7, 11]]
```

**Lectura:** el `class_weight` hace lo que promete (recall de `Positivo` sube de
0.33 a 0.73) pero a costa de la precisión (0.75 → 0.38) y de la clase
mayoritaria; el macro-F1 global cae **−0.059**. El modelo actual ya era razonable
en `Negativo`/`Neutro` y el balanceo lo degrada. **No hay mejora en
sentimiento.**

### 5.2 Encuadres

Macro-promedio de las 7 etiquetas en test:

| Umbral | Métrica | Reentrenado | Baseline actual | Δ |
|---|---|---:|---:|---:|
| 0.5 | Macro-precisión | 0.409 ± 0.075 | 0.380 ± 0.067 | +0.029 |
| 0.5 | Macro-recall | 0.670 ± 0.049 | 0.411 ± 0.033 | **+0.259** |
| 0.5 | **Macro-F1** | **0.463 ± 0.050** | **0.366 ± 0.048** | **+0.097** (5/5 folds) |
| elegido en validación | Macro-F1 | 0.431 ± 0.099 | 0.385 ± 0.071 | +0.046 (4/5 folds) |

Por etiqueta a umbral 0.5 (soporte medio de test entre paréntesis):

| Encuadre | Soporte | F1 reentrenado | F1 baseline | Δ | Recall retr. / base |
|---|---:|---:|---:|---:|---:|
| `integracion_social` | 5.4 | 0.442 ± 0.137 | 0.136 ± 0.218 | **+0.306** | 0.655 / 0.105 |
| `otros` | 2.4 | 0.246 ± 0.243 | 0.000 ± 0.000 | **+0.246** | 0.533 / 0.000 |
| `empleo_economia` | 5.8 | 0.385 ± 0.096 | 0.173 ± 0.248 | **+0.212** | 0.790 / 0.120 |
| `politica_migratoria` | 19.6 | 0.783 ± 0.061 | 0.768 ± 0.034 | +0.015 | 0.973 / 0.839 |
| `transito_migratorio` | 10.6 | 0.542 ± 0.178 | 0.557 ± 0.054 | −0.015 | 0.733 / 0.716 |
| `acceso_servicios` | 9.0 | 0.443 ± 0.163 | 0.483 ± 0.106 | −0.040 | 0.457 / 0.439 |
| `seguridad` | 8.0 | 0.402 ± 0.238 | 0.446 ± 0.155 | −0.044 | 0.549 / 0.658 |

**Lectura:** la mejora es real y consistente en los 5 folds, pero **se
concentra en las etiquetas con menos positivos** (`otros`, `integración`,
`empleo`), justo donde el `pos_weight` actúa. `política` y `tránsito` (las
frecuentes) quedan iguales; `acceso` y `seguridad` empeoran levemente porque
pierden precisión/recall al repartir capacidad hacia las raras.

### 5.3 Umbrales: el tuning no aporta con este tamaño de datos

| Variante de umbrales (elegidos solo con validación agrupada, n=125) | Macro-F1 en validación |
|---|---:|
| 0.5 en todas las etiquetas | **0.4646** |
| Piso de precisión estricto (sin salvaguarda) | 0.3782 |
| F1-óptimo sin piso de precisión | 0.4972 |
| **Finales con salvaguarda (`thresholds.json`)** | **0.4646** |

El protocolo con piso de precisión sobre 25 validaciones por fold empuja los
umbrales a 0.65/0.60 en `acceso`, `seguridad` y `empleo`: sube la precisión pero
hunde el recall (p. ej. `acceso`: precisión 1.00, recall 0.05, F1 0.10), y el
macro-F1 cae de 0.465 a 0.378. La salvaguarda conserva 0.5 cuando el umbral con
piso empeora el F1 en la misma validación. **Con 156 artículos, no hay evidencia
para mover los umbrales de 0.5**; los umbrales estrictos y los F1-óptimos sin
piso quedan en artefactos aparte para auditoría.

### 5.4 Fold a fold (test)

| Fold | n test | Sent. acc retr./base | Sent. macro-F1 retr./base | Frames macro-F1@0.5 retr./base |
|---|---:|---:|---:|---:|
| 1 | 32 | 0.594 / 0.562 | 0.567 / 0.521 | 0.495 / 0.408 |
| 2 | 31 | 0.452 / 0.677 | 0.454 / 0.641 | 0.446 / 0.394 |
| 3 | 31 | 0.710 / 0.645 | 0.657 / 0.600 | 0.481 / 0.301 |
| 4 | 31 | 0.548 / 0.645 | 0.546 / 0.556 | 0.510 / 0.398 |
| 5 | 31 | 0.452 / 0.645 | 0.428 / 0.633 | 0.385 / 0.330 |

La varianza entre folds es grande (desviación 0.04–0.21 en sentimiento), pero el
patrón de encuadres es estable: **5/5 folds mejoran**.

---

## 6. Modelos finales y artefactos

| Archivo | Contenido |
|---|---|
| `training/models/bert-sentiment-retrained/` | `BertForSequenceClassification` de 3 clases (`save_pretrained`, 440 MB). |
| `training/models/bert-frames-retrained/` | `BertForSequenceClassification` multi-etiqueta de 7 salidas, `problem_type=multi_label_classification`. |
| `training/models/training_config.json` | Config de la corrida, datos y umbrales finales. |
| `training/artifacts/retraining_evaluation.json` | Métricas CV completas (por fold, por clase, por etiqueta), baseline vs reentrenado, delta paired, umbrales, parámetros y tallas. |
| `training/artifacts/thresholds.json` | Umbrales finales recomendados (ids canónicos). |
| `training/artifacts/thresholds_precision_floor_estricto.json` | Variante estricta con piso de precisión (para auditoría; **no recomendada**). |
| `training/artifacts/thresholds_alt_max_f1.json` | Variante F1-óptima sin piso (para auditoría). |
| `training/artifacts/cv_folds/fold_*.json` | Predicciones de validación y test por fold, umbrales elegidos y matrices. |
| `training/artifacts/baseline_predictions.json` | Predicciones de los modelos actuales sobre los 156 artículos (mismo `max_len`). |

La corrida completa (5 folds × 2 modelos + modelos finales + inferencia del
baseline + validación in-sample) tardó **28,2 minutos** en CPU. La comprobación
in-sample del modelo final (accuracy 0.699 y macro-F1 0.697 en sentimiento;
macro-F1 0.578 en encuadres a 0.5) es **solo un sanity check**: está medida
sobre los mismos datos de entrenamiento y no sirve para decidir si el modelo
mejora.

---

## 7. Verificación con `BertPairEngine`

El 2026-11-09 se cargaron los modelos retrenados con el motor real de la API
(`api/app/engine/bert_pair.py`, importado desde el `api/` de este worktree) y
`load_thresholds`, y se infirió la primera noticia del CSV etiquetado. Resultado:

```text
load_thresholds() -> {"acceso_servicios": 0.5, "transito_migratorio": 0.5,
  "seguridad": 0.5, "integracion_social": 0.5, "politica_migratoria": 0.5,
  "empleo_economia": 0.5, "otros": 0.5}
BertPairEngine cargado en cpu · max_length=256

=== noticia analizada ===
ID: articulo_1 | país: Colombia | medio: Semana
título: Vuelven los vuelos de deportación a Venezuela: 147 migrantes llegaron desde Estados Unidos
etiqueta real sentimiento: Neutro

sentimiento (probabilidades): Positivo 0.3803 | Neutro 0.3321 | Negativo 0.2877
encuadres: politica_migratoria 0.6820 (activo), acceso_servicios 0.5344 (activo),
  integracion_social 0.5166 (activo), transito_migratorio 0.5104 (activo),
  otros 0.4940, seguridad 0.4753, empleo_economia 0.3901
encuadres activos: {"acceso_servicios": 0.5344, "transito_migratorio": 0.5104,
  "integracion_social": 0.5166, "politica_migratoria": 0.682}
advertencias: ['El texto supera los 256 tokens y fue truncado...',
  'Baja confianza del clasificador de sentimiento.']

OK: los modelos retrenados cargan y predicen con el motor de producción.
```

Snippet mínimo usado (equivale a `training/verify_retrained.py`):

```python
import sys
sys.path.insert(0, "api")  # api/ del worktree; el motor real de producción

import pandas as pd
from app.engine.bert_pair import BertPairEngine, load_thresholds

thresholds = load_thresholds("training/artifacts/thresholds.json")
engine = BertPairEngine(
    sentiment_model_dir="training/models/bert-sentiment-retrained",
    frames_model_dir="training/models/bert-frames-retrained",
    device="cpu",
    max_length=256,
    thresholds=thresholds,
)
df = pd.read_csv("Data/dataset_migracion_venezolana_labeled.csv", encoding="utf-8-sig")
noticia = df.iloc[0]
pred = engine.predict(noticia["Cuerpo"])
print(pred.sentiment)   # {"Negativo": p, "Neutro": p, "Positivo": p}
print(pred.frames)      # {frame_id canónico: probabilidad sigmoide}
activos = {k: v for k, v in pred.frames.items() if v >= thresholds[k]}
```

Comando exacto:

```powershell
$env:PYTHONPATH = "api"
& $py training/verify_retrained.py --index 0 --device cpu
```

La noticia es `Neutro` y el modelo retrenado le da `Positivo 0.38` como primera
opción: es la evidencia práctica de la sobre-predicción de `Positivo` que
introdujo el balanceo (y de por qué no recomendamos reemplazar sentimiento aún).

---

## 8. Interpretación honesta: ¿mejora?

**Encuadres: sí, de forma modesta pero consistente, y por la vía esperada.** El
`pos_weight` sube el recall de las etiquetas con pocos positivos (`otros` de 0.00
a 0.53, `empleo` de 0.12 a 0.79, `integración` de 0.11 a 0.66) manteniendo la
precisión macro casi igual (0.38 → 0.41). El macro-F1 a 0.5 pasa de 0.366 a
0.463: **+0.097, más del doble que la desviación del delta (0.053), con 5/5
folds a favor**. Es la señal más sólida de todo el trabajo. Aun así, el valor
absoluto (0.46 de macro-F1, con etiquetas de 2–10 positivos por test) sigue
siendo bajo, y tres etiquetas empeoran levemente.

**Sentimiento: no.** El balanceo por `class_weight` cambia el punto de operación
hacia `Positivo` (recall 0.73) pero sacrifica precisión (0.38) y las clases
mayoritarias; el macro-F1 baja 0.059. Es un caso claro de que balancear una
métrica intermedia (recall de la clase minoritaria) no equivale a mejorar la
métrica objetivo. Con 1 época de continuación y 156 ejemplos, el ajuste fino no
aporta y sí desestabiliza. **Recomendación directa: no reemplazar el modelo de
sentimiento con el retrenado.**

**¿Es fiable con 156–237 ejemplos?** La dirección del efecto de encuadres es
fiable (consistente en 5 folds, magnitud > varianza); los valores absolutos no.
Las métricas de ambos modelos están además **contaminadas por el entrenamiento
previo con este mismo corpus** (ver Limitaciones), por lo que los números
absolutos son optimistas para ambos; el *delta* sigue siendo comparable porque
la contaminación es simétrica.

---

## 9. Limitaciones (importantes)

1. **Pocos datos.** 156 artículos únicos y 7 etiquetas multi-etiqueta (la menos
   frecuente, `otros`, tiene 12 positivos). Con estos tamaños, un fold de test
   tiene ~32 noticias y **cambios de 1–2 aciertos mueven el macro-F1 varios
   puntos**: la desviación entre folds es parte del resultado, no ruido evitable.
2. **Contaminación de los pesos iniciales.** Los checkpoints de Desktop se
   entrenaron con este mismo corpus (el `evaluation.json` actual reconoce que
   sus métricas están influidas por solapamiento). Al inicializar desde ellos, la
   CV mide *cuánto mejora reajustar y balancear*, **no** el rendimiento de un
   modelo entrenado desde cero. El baseline tiene exactamente la misma
   contaminación, por lo que el *delta* sigue siendo comparable, pero las cifras
   absolutas son optimistas.
3. **Truncación.** `max_len=256` (frente a los 512 con los que se entrenaron los
   modelos originales) deja fuera el final de muchas noticias. Se aplicó igual a
   baseline y reentrenados para que la comparación sea justa; los valores
   absolutos no son directamente comparables con `api/artifacts/evaluation.json`.
4. **Una sola semilla y una sola partición.** La CV de 5 folds da una estimación
   razonable, pero no un intervalo de confianza formal. Repetir con varias
   semillas (`--seed`) acotaría la incertidumbre.
5. **Umbrales inestables por etiqueta.** Con 12–27 positivos por etiqueta, el
   umbral que maximiza F1 en validación puede no ser el óptimo en test. Por eso
   se reportan también las métricas a 0.50 y el número de folds que mejoran.
6. **El corpus es pequeño y de dos medios.** Semana y Milenio (Colombia y
   México) no representan todo el ecosistema mediático; el sesgo cultural del
   corpus puede reforzarse en el modelo.

---

## 10. Recomendación

Con los números de arriba, la decisión es distinta para cada modelo:

1. **Sentimiento: NO reemplazar.** El retrenado pierde 0.059 de macro-F1 y baja
   la accuracy de 0.635 a 0.551. Seguir con `modelo_sentimiento` actual.
2. **Encuadres: candidato a reemplazo, pero no directo a producción.** La mejora
   de +0.097 de macro-F1 (5/5 folds) es real y viene de las etiquetas raras, pero
   (a) las métricas absolutas son bajas, (b) ambos modelos están contaminados por
   el corpus de entrenamiento, y (c) el cambio sube el recall y baja la
   precisión, lo que cambia el significado del dashboard (más frames por
   noticia). Antes de reemplazar: validar en un set externo de noticias nuevas.
3. **Más etiquetado con Labelbox, estratificado por país × sentimiento ×
   encuadre.** Este es el cuello de botella real: 156 artículos son insuficientes
   para 7 etiquetas (la menor tiene 12 positivos). Prioridades concretas:
   `Positivo` de México (hoy 6), `Negativo` de Colombia (hoy 16), y las
   etiquetas `otros` (12), `integración social` (27) y `empleo y economía` (29).
   Objetivo razonable para la siguiente iteración: **+300–500 noticias nuevas**,
   con cuotas por país para romper la correlación "empleo/integración =
   Colombia" y "tránsito/seguridad = México".
4. **Balanceo por país en el próximo corpus.** El desbalance de sentimiento por
   país es el hallazgo más fuerte del análisis (82 % de los positivos son
   colombianos; 64 % de los negativos, mexicanos). Construir el corpus con cuotas
   parecidas por país y sentimiento; entrenar y reportar F1 **desagregado por
   país** para detectar si el modelo reproduce el sesgo.
5. **No usar los umbrales "tuneados" todavía** salvo que un set externo muestre
   que aportan; el mejor punto de operación con estos datos es 0.5, como
   demuestra la comparación de validación (0.465 vs 0.378 con piso estricto).
6. **Cuándo reemplazar los modelos** (checklist concreta):
   * set externo etiquetado (noticias que no estén en el corpus de entrenamiento)
     de al menos ~150 artículos, con cuotas por país y sentimiento;
   * sentimiento: Δ macro-F1 ≥ +0.03 en el set externo y sin caída > 0.03 en
     ninguna clase;
   * encuadres: Δ macro-F1 ≥ +0.05 en el set externo, sin que `seguridad` ni
     `acceso a servicios` caigan > 0.03, y decisión de producto sobre el
     trade-off recall/precisión;
   * si se cumple: apuntar `NLP_SENTIMENT_MODEL_DIR` / `NLP_FRAMES_MODEL_DIR` a
     los modelos nuevos, copiar `training/artifacts/thresholds.json` a
     `api/artifacts/thresholds.json`, regenerar `api/artifacts/evaluation.json`
     con `python api/scripts/evaluate_models.py` (usa esos modelos) y reiniciar
     la API. **No** hacer el reemplazo solo porque los modelos se reentrenaron.

---

## 11. Estructura de archivos

```text
training/
├── train_models.py            # pipeline completo (CV + modelos finales + artefactos)
├── recompute_thresholds.py    # recalcula/audita umbrales desde las predicciones de validación
├── verify_retrained.py        # carga con BertPairEngine y predice una noticia real
├── requirements-train.txt
├── README.md
├── .gitignore                 # models/, logs, __pycache__
├── models/                    # GITIGNORED: modelos save_pretrained
│   ├── bert-sentiment-retrained/
│   ├── bert-frames-retrained/
│   └── training_config.json
└── artifacts/
    ├── retraining_evaluation.json            # métricas CV, baseline vs retrenado, umbrales
    ├── thresholds.json                       # umbrales recomendados {frame_id canónico: umbral}
    ├── thresholds_precision_floor_estricto.json
    ├── thresholds_alt_max_f1.json
    ├── baseline_predictions.json             # predicciones de los modelos actuales
    ├── cv_progress.json                      # progreso de la corrida
    ├── retraining.log
    └── cv_folds/fold_*.json                  # predicciones y umbrales por fold
```
