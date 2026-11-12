# BETO multitarea (sentimiento + temas)

Encoder `dccuchile/bert-base-spanish-wwm-cased` con dos cabezas: sentimiento (3 clases)
y temas (multilabel). Usa pesos de clase en sentimiento y `pos_weight` en labels multilabel,
sin sobremuestreo; threshold óptimo por etiqueta (sobre OOF),
early stopping por Macro-F1 de temas y selección del mejor fold/epoch como modelo final.

## Archivos

| Archivo | Qué hace |
|---|---|
| `preprocess.py` | Limpieza (`prepare_text` elimina stopwords, palabras menores de 3 caracteres y términos identificados como inglés), carga, pesos, folds y DataLoaders |
| `train.py` | Modelo, CV + OOF + thresholds, modelo final |
| `infer.py` | Predicción con `models_beto/beto_multitask.pt` (un texto o un CSV) |
| `metrics.json` | Resultados OOF guardados automáticamente por `train.py` |

## Uso

```bash
python preprocess.py                 # revisar columnas y distribución
python train.py --stage cv           # CV -> thresholds y checkpoint del mejor fold
python train.py --stage final        # mejor checkpoint -> models_beto/beto_multitask.pt
# (python train.py hace ambos pasos seguidos)

python infer.py --text "Texto de una noticia..."
python infer.py --csv noticias.csv --text_col Cuerpo --out predicciones.csv
```

Por defecto lee `../data/dataset_migracion_venezolana_labeled.csv` (relativo a esta carpeta);
cambia con `--data`. Cualquier hiperparámetro se puede sobrescribir por CLI
(`--lr`, `--epochs`, `--model_name`, ...).

Para comparar el resultado con RoBERTa y DistilBERT, ejecuta también sus
entrenamientos con los mismos valores de `--data`, `--seed`, `--n_folds` y
`--max_len`. Luego genera la tabla común:

```bash
python ../compare_models.py
```

La comparación usa F1 macro de temas como criterio principal e incluye F1 de
sentimiento, F1 micro y duración de la validación cruzada. Estos son resultados
OOF con umbrales ajustados sobre las mismas predicciones OOF, por lo que sirven
para una comparación inicial, no como estimación independiente de prueba.
