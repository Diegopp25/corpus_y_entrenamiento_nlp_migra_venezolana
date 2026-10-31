# Benchmark de modelos de sentimiento: tono hacia los migrantes venezolanos

Compara 8 configuraciones de modelos de sentimiento sobre `Data/dataset_migracion_venezolana.csv`
(Semana + Milenio, 160 notas) y mide cuál se parece más a etiquetas humanas del **tono hacia los
migrantes venezolanos**, como base para detectar sesgo cultural.

## Estado (léelo antes de correr)

- **La parte de Hugging Face (`backends.py`) no se pudo ejecutar** cuando se escribió: el entorno
  donde se desarrolló no tenía acceso a Hugging Face ni a PyPI. El resto (troceo, agregación,
  acuerdo entre modelos, evaluación, gráficos) sí se probó de punta a punta con tres modelos de
  juguete (`--backend dummy`) y con pruebas unitarias. Es probable que haya que ajustar algún detalle
  al primer intento real (ver "Problemas probables").
- Los IDs, etiquetas y límites de longitud de cada modelo se leyeron de sus fichas en Hugging Face
  el 9 de octubre de 2026. Pueden cambiar.
- **Hay un desajuste de fondo:** los modelos de sentimiento puntúan el tono *del texto*, no el tono
  *hacia un grupo*. Una nota que cuenta con compasión la muerte de un migrante sale "negativa" para
  ellos. Para acercarse a lo que se etiqueta a mano, el pipeline hace dos cosas: (1) agrega solo los
  fragmentos que mencionan migrantes (`results/<run>/target/`) y (2) incluye `mdeberta_nli_target`,
  un modelo NLI con hipótesis sobre cómo se presenta a los migrantes. Si estas aproximaciones bastan es
  una pregunta empírica: la responde la evaluación contra etiquetas manuales.
- **Acuerdo entre modelos no es exactitud:** para saber cuál acierta hay que evaluar contra las etiquetas humanas (`evaluate_gold`).
- **Sentimiento no es sesgo cultural.** Aun midiendo bien el tono, el sesgo también está en el encuadre
  (víctima, amenaza, carga...); por eso la guía incluye una columna `encuadre`.
- Ninguno de los modelos se entrenó con prensa. Cinco vienen de tuits o reseñas de productos y cine.

## Modelos

| Clave | Modelo | Qué es | Salida |
| --- | --- | --- | --- |
| `robertuito` | `pysentimiento/robertuito-sentiment-analysis` | RoBERTuito afinado en TASS 2020 (tuits en español) | NEG/NEU/POS |
| `beto` | `finiteautomata/beto-sentiment-analysis` | BETO afinado en TASS 2020. Su ficha dice que será retirado | NEG/NEU/POS |
| `xlmr_twitter` | `cardiffnlp/twitter-xlm-roberta-base-sentiment` | XLM-R con ~198M tuits, 8 idiomas | neg/neu/pos |
| `distil_multi` | `lxyuan/distilbert-base-multilingual-cased-sentiments-student` | DistilBERT multilingüe destilado de un mDeBERTa-NLI | pos/neu/neg |
| `nlptown_stars` | `nlptown/bert-base-multilingual-uncased-sentiment` | BERT multilingüe, reseñas de producto | 1-5 estrellas (1-2 neg, 3 neu, 4-5 pos) |
| `roberta_bne_imdb` | `edumunozsala/roberta_bne_sentiment_analysis_es` | RoBERTa-BNE con reseñas de cine (binario) | Negativo/Positivo (nunca neutro) |
| `mdeberta_nli` | `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` | NLI como zero-shot sobre el tono general | softmax de "entailment" |
| `mdeberta_nli_target` | el mismo modelo | NLI con hipótesis sobre los migrantes venezolanos | softmax de "entailment" |

Las hipótesis NLI y el registro de modelos están en `config.py`. Los dos últimos comparten pesos
(se cargan dos veces; solo cambia la hipótesis).

## Cómo funciona

1. Cada nota se parte en oraciones y se agrupa en fragmentos que caben en la ventana **de cada modelo**
   (RoBERTuito admite ~128 tokens; el resto, hasta un tope de 256).
2. Cada modelo puntúa cada fragmento y se normaliza a `negativo | neutro | positivo`.
3. Las probabilidades se promedian por nota, ponderando por tokens, de dos maneras:
   - `results/<run>/`: todos los fragmentos (tono general de la nota).
   - `results/<run>/target/`: solo fragmentos que mencionan migrantes/venezolanos (regex en
     `text_utils.py`, aproximada: también coincide con "venezolano" referido al país). Si una nota no tiene
     ninguno se usa toda y se marca `fallback_all`. En una corrida de prueba ~79% de los fragmentos
     coincidieron, así que el filtro es suave.

## Uso (desde la raíz del repo)

```bash
pip install -r sentiment_benchmark/requirements.txt

# 0) Prueba rápida del pipeline sin descargar modelos
python -m sentiment_benchmark.run_models --backend dummy
python -m sentiment_benchmark.analyze --run dummy/target

# 1) Modelos reales (la primera vez descarga varios cientos de MB por modelo)
python -m sentiment_benchmark.run_models --limit 20          # prueba con 20 notas
python -m sentiment_benchmark.run_models                     # corpus completo
python -m sentiment_benchmark.run_models --models robertuito,xlmr_twitter --device cuda

# 2) Comparar los modelos entre sí (por defecto, la variante enfocada en migrantes)
python -m sentiment_benchmark.analyze                        # results/full/target
python -m sentiment_benchmark.analyze --run full             # tono general

# 3) Evaluar contra las etiquetas del proyecto (ver "Etiquetas del proyecto")
python -m sentiment_benchmark.check_labels ruta/dataset_migracion_venezolana_labeled.csv
python -m sentiment_benchmark.evaluate_gold --gold ruta/dataset_migracion_venezolana_labeled.csv
python -m sentiment_benchmark.evaluate_gold --gold ruta/... --run full   # comparar con tono general
```

Si un modelo falla (por ejemplo, retirado del Hub), se registra en `run_summary.json` y se continúa
con los demás. Los resultados ya calculados se reutilizan; usa `--force` para recalcular.

## Etiquetas del proyecto (`dataset_migracion_venezolana_labeled.csv`)

El CSV etiquetado (columna `sentimiento` = tono de la noticia hacia los migrantes venezolanos, más
siete columnas temáticas 0/1) se usa directamente:

```bash
# 1) ANTES de evaluar: ¿las etiquetas están unidas al texto correcto?
python -m sentiment_benchmark.check_labels ruta/dataset_migracion_venezolana_labeled.csv
# 2) Evaluar (la unión es por URL; los IDs de este módulo empiezan en articulo_0 y los del CSV en articulo_1)
python -m sentiment_benchmark.evaluate_gold --gold ruta/dataset_migracion_venezolana_labeled.csv --medios Milenio
```

**Aviso (28 oct 2026):** `check_labels` da un AUC medio de 0.81 para Milenio (coherente) y 0.40 para
Semana (sin relación con el texto), y al leer los títulos de Semana junto a sus etiquetas hay
desajustes claros (p. ej. una nota sobre Uber y motos etiquetada "Positivo, Integración social").
Hasta aclararlo, evalúa solo con `--medios Milenio`. Causa probable, sin confirmar: las etiquetas se
hicieron sobre una versión anterior del scrape de Semana (la API devuelve resultados que cambian) y se
unieron por ID a la versión actual. Solución: re-exportar de Labelbox incluyendo el texto de cada nota
y unir por texto o URL, no por número.

## Qué hace `evaluate_gold`

Compara cada modelo con las etiquetas humanas (`negativo`, `neutro`, `positivo`; las `no_aplica`, si
las hubiera, se excluyen) y ordena por macro-F1 con intervalo de confianza. También escribe
`gold_tone_by_medio.csv`: la distribución del tono según las personas por medio (Semana = Colombia,
Milenio = México). Con ~80 notas por medio y solo 6 positivas en Milenio, trátalo como exploración.
`annotator_agreement.py` calcula el kappa entre dos anotadores si algún día se tienen sus archivos por separado.

## Salidas (`results/<full|limit_N|dummy>[/target]/`, ignoradas por git)

| Archivo | Contenido |
| --- | --- |
| `articles_<modelo>.csv`, `chunks_<modelo>.csv` | Probabilidades y etiqueta por nota / fragmento |
| `label_distribution_pct.csv`, `label_distribution.png` | % de notas por etiqueta, modelo y medio |
| `pairwise_kappa.csv`, `kappa_heatmap.png` | Acuerdo entre pares de modelos |
| `labels_and_consensus.csv`, `agreement_with_consensus.csv` | Voto por mayoría y cercanía de cada modelo |
| `polarity_spearman.csv` | Correlación de la polaridad (p_pos − p_neg) entre modelos |
| `gold_evaluation.csv`, `gold_macro_f1.png`, `confusion_<modelo>.csv` | Evaluación contra etiquetas manuales |
| `gold_tone_by_medio.csv`, `gold_encuadre_by_medio.csv` | Tono y encuadre según las personas, por medio |

## Problemas probables al primer intento

- **Tokenizador de RoBERTuito:** puede pedir el paquete `emoji` (está en `requirements.txt`).
- **`beto`:** si su repositorio ya no existe, fallará y se omitirá.
- **`xlmr_twitter` y el tokenizador:** su repo solo trae un archivo SentencePiece y `transformers` puede fallar al convertirlo (error "Converting from SentencePiece and Tiktoken failed"). El código ya usa como respaldo el tokenizador de `FacebookAI/xlm-roberta-base`, que comparte vocabulario. Si aun así falla, instala `sentencepiece` y `protobuf`.
- **Python 3.14:** es muy reciente y varias librerías de ML aún no lo soportan bien (PyTorch avisa de ello). Si aparecen errores raros, usa un entorno virtual con Python 3.11 o 3.12.
- **`--limit N`:** guarda en `results/limit_N/`, así que para analizar esa prueba usa `python -m sentiment_benchmark.analyze --run limit_20/target`.
- **Etiquetas `LABEL_0`:** si algún modelo cambiara a etiquetas genéricas, `labels.py` lanza un error claro
  y hay que añadir un `label_map` en su `ModelSpec`.
- **Memoria/tiempo:** los modelos NLI hacen tres pasadas por fragmento. Baja `--batch-size` si falta memoria.

## Pruebas

```bash
python -m pytest sentiment_benchmark/tests        # o: python sentiment_benchmark/tests/test_core.py
```
