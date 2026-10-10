# Guía de etiquetado: tono hacia los migrantes venezolanos

Propuesta inicial. Pruébenla con ~10 notas entre las dos personas anotadoras, comparen y ajusten
las reglas antes de etiquetar la muestra completa.

## Qué se etiqueta

**Cómo la nota presenta a los migrantes venezolanos como grupo.** No se etiqueta el tono general
del texto ni lo "triste" o "grave" del hecho. Una nota sobre una tragedia o un crimen no es
negativa por eso: lo es solo si la forma de contarla juzga, culpa o estigmatiza al grupo.

Se etiqueta la nota completa. El tono hacia el grupo puede aparecer solo en un párrafo
o al final; lee todo el cuerpo antes de decidir.

## Etiqueta principal (`label_manual`)

| Etiqueta | Cuándo | Señales típicas |
| --- | --- | --- |
| `negativo` | Presenta a los migrantes como problema, amenaza o carga; los asocia con delito, desorden o saturación de servicios; generaliza a todo el grupo | "invasión", "ola", "avalancha"; atribuye al grupo problemas del país; nacionalidad destacada sin necesidad al hablar de un delito; deshumaniza |
| `neutro` | Informa sin valorar a favor ni en contra, o equilibra posturas | cifras, trámites, declaraciones oficiales, hechos puntuales sin generalizar |
| `positivo` | Los presenta de forma favorable: aportes, logros, derechos, solidaridad hacia ellos, denuncia de discriminación en su contra | historias de integración, defensa de sus derechos, voz propia de los migrantes |
| `no_aplica` | La nota no trata de migrantes venezolanos de forma sustantiva (mención de pasada o tema distinto, p. ej. política interna de Venezuela) | solo aparece "venezolanos" en una frase |

Si dudas entre dos etiquetas, elige `neutro` y explica en `notas`. Reserva `no_aplica` para
notas que realmente no tratan del grupo.

## Reglas para los casos difíciles

1. **Hecho vs. grupo.** Un delito cometido por una persona venezolana, contado como hecho policial
   sin generalizar, es `neutro`. Pasa a `negativo` si la nota extiende la culpa al grupo,
   o si la nacionalidad se usa como explicación del delito.
2. **Citas.** Se evalúa la postura de la nota, no la de la persona citada. Una declaración hostil
   presentada sin distancia, o sin contraste, cuenta como `negativo`; si la nota la
   cuestiona o la contrasta, es `neutro` o `positivo`.
3. **Compasión.** Una nota que muestra sufrimiento de migrantes con simpatía es `positivo` o `neutro`,
   no `negativo`. Si los retrata solo como víctimas pasivas, anótalo en `encuadre`; es una
   dimensión de sesgo distinta del tono.
4. **Titular vs. cuerpo.** Si no coinciden, manda el cuerpo; anota la diferencia en `notas`.
5. **Mezcla.** Si hay partes favorables y desfavorables que se compensan, `neutro`.

## Encuadre (`encuadre`, opcional)

Dimensión aparte del tono, útil para analizar sesgo cultural por medio o país. Elige la que más pese
en la nota o déjala vacía:

`victima_humanitario` · `amenaza_delito` · `carga_economica_servicios` · `aporte_oportunidad` ·
`politica_institucional` · `xenofobia_discriminacion` · `otro`

## Flujo

1. `python -m sentiment_benchmark.make_annotation_sample --n 60` (ya hay una muestra generada).
2. Cada anotador trabaja en **su propia copia** del CSV y solo rellena `label_manual`, `encuadre` y `notas`.
3. `python -m sentiment_benchmark.annotator_agreement a.csv b.csv`: revisa el kappa y
   `annotations/desacuerdos.csv`; discutan y ajusten esta guía.
4. Une las etiquetas finales en `annotation_sample.csv` y corre `python -m sentiment_benchmark.evaluate_gold`.
