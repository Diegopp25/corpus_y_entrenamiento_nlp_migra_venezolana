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
- **Sin etiquetas humanas solo se mide acuerdo entre modelos, no exactitud.**
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

# 3) Etiquetar y evaluar (leer annotations/GUIA_ETIQUETADO.md)
python -m sentiment_benchmark.make_annotation_sample --n 60  # ya viene una muestra generada
python -m sentiment_benchmark.annotator_agreement a.csv b.csv   # si anotan dos personas
python -m sentiment_benchmark.evaluate_gold                  # contra full/target
python -m sentiment_benchmark.evaluate_gold --run full       # comparar con tono general
```

Si un modelo falla (por ejemplo, retirado del Hub), se registra en `run_summary.json` y se continúa
con los demás. Los resultados ya calculados se reutilizan; usa `--force` para recalcular.

## Etiquetado manual

Etiquetas: `negativo`, `neutro`, `positivo`, `no_aplica` (nota que no trata de migrantes
venezolanos) y, opcional, `encuadre`. La guía con reglas para los casos difíciles es
`annotations/GUIA_ETIQUETADO.md`; es una propuesta que conviene ajustar con una prueba piloto de
~10 notas. La muestra incluye el cuerpo completo de 60 notas (30 por medio). Con ~60 notas los
intervalos de confianza del macro-F1 serán anchos: un par de puntos entre modelos no significa nada.

`evaluate_gold` excluye las `no_aplica` de la evaluación y escribe además `gold_tone_by_medio.csv`:
la distribución del tono según las personas por medio (Semana = Colombia, Milenio = México), que es la
base para comparar sesgo entre países. Con ~30 notas por medio, trátalo como exploración, no como conclusión.

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
- **Etiquetas `LABEL_0`:** si algún modelo cambiara a etiquetas genéricas, `labels.py` lanza un error claro
  y hay que añadir un `label_map` en su `ModelSpec`.
- **Memoria/tiempo:** los modelos NLI hacen tres pasadas por fragmento. Baja `--batch-size` si falta memoria.

## Pruebas

```bash
python -m pytest sentiment_benchmark/tests        # o: python sentiment_benchmark/tests/test_core.py
```
