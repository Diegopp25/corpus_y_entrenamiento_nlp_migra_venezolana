# Reentrenamiento y balanceo del corpus (estado actual)

Este documento resume el primer ciclo de **balanceo + reentrenamiento** de los
modelos BETO y la decisión tomada. El pipeline reproducible y el detalle
completo viven en la rama `retraining`, carpeta `training/` (ver
`training/README.md`).

## 1. Hallazgo sobre los datos

- `Data/dataset_balanced.csv` **no está balanceado**: tiene 237 filas pero solo
  **116 artículos únicos** (121 filas duplicadas, 51 %). Es un *sobremuestreo*
  del corpus, no un corpus nuevo.
- Su unión con `dataset_migracion_venezolana_labeled.csv` (156 artículos)
  deduplicada por texto da **156 artículos únicos en total**.
- Cualquier validación cruzada debe deduplicar antes de partir folds; de lo
  contrario se filtra información entre train y test.

Distribución real (156 únicos): Negativo 44, Neutro 79, Positivo 33;
Colombia 77, México 79. Etiquetas raras: `otros` 12 positivos,
`empleo_economia` 29, `integracion_social` 27.

## 2. Método

Validación cruzada 5-fold estratificada, con test intacto por fold:

- Dos modelos single-task (`BertForSequenceClassification`) inicializados desde
  los checkpoints actuales (continuar fine-tuning, no desde cero).
- Class weights en sentimiento y `pos_weight` topado en encuadres.
- Umbrales elegidos **solo con validación** (grid 0.2–0.8 con piso de
  precisión); baseline evaluado en los mismos folds.
- CPU: 5 folds × 1 época × `max_len=256` (los defaults del script son 5/3/384).

## 3. Resultados reales (media ± desviación entre folds)

| Tarea | Baseline | Reentrenado | Delta | Veredicto |
|---|---|---|---|---|
| Sentimiento (accuracy) | 0.635 ± 0.043 | 0.551 ± 0.108 | −0.084 | **no reemplazar** |
| Sentimiento (macro-F1) | 0.590 ± 0.051 | 0.531 ± 0.092 | −0.059 | **no reemplazar** |
| Encuadres (macro-F1@0.5) | 0.366 ± 0.048 | 0.463 ± 0.050 | **+0.097** (5/5 folds) | candidato, falta validación externa |

- El balanceo de sentimiento sube el recall de Positivo (0.73 vs 0.33) pero
  hunde su precisión (0.38 vs 0.75): pierde F1 global.
- En encuadres la mejora se concentra en etiquetas raras: integración +0.31,
  otros +0.25, empleo +0.21; tránsito, acceso y seguridad empeoran levemente.
- El tuning de umbrales es inestable con 25 validaciones/fold. Recomendación:
  **umbral 0.5 en los 7 encuadres**; las variantes estrictas/F1-óptimas quedan
  guardadas solo como referencia.

## 4. Decisión

- **Producción se queda como está** (modelos actuales en
  `NLP_SENTIMENT_MODEL_DIR` / `NLP_FRAMES_MODEL_DIR`).
- Los modelos reentrenados (`training/models/`, ~440 MB cada uno, gitignored) no
  se reemplazan hasta validarlos con **noticias nuevas no usadas en
  entrenamiento** (~150).
- Limitaciones del ciclo: 156 artículos, 2 medios, pesos iniciales ya expuestos
  al corpus (el delta sigue siendo comparable porque el baseline también),
  truncación 256 vs 512 de producción, una semilla y una época por CPU.

## 5. Siguiente paso recomendado

1. **Etiquetar +300–500 noticias nuevas con Labelbox**, estratificadas por
   país × sentimiento × encuadre. Prioridades: Positivo México (solo 6 hoy),
   Negativo Colombia (16), y los encuadres `otros`, `integración` y `empleo`.
2. Balancear el corpus por país (hoy 82 % de los positivos son colombianos y
   64 % de los negativos mexicanos).
3. Reentrenar en GPU (los defaults 5 folds × 3 épocas × 384 tokens) y validar
   el candidato en el set externo de ~150 noticias.
4. Si supera al modelo actual, reemplazar solo la cabeza de encuadres:
   copiar `training/models/bert-frames-retrained/` al servidor, apuntar
   `NLP_FRAMES_MODEL_DIR` a esa carpeta, copiar `training/artifacts/thresholds.json`
   a `api/artifacts/thresholds.json` y regenerar
   `api/artifacts/evaluation.json` con `api/scripts/evaluate_models.py`.
5. Repetir la evaluación de la API y actualizar el dashboard.

> Comando del ciclo actual (rama `retraining`):
> `$env:PYTHONPATH="api"; python training/train_models.py --folds 5 --epochs 1 --max-len 256 --batch-size 8 --lr 2e-5 --seed 42`
