"""Prueba de integración con los pesos BETO reales (marcador ``real_models``).

NO se ejecuta en CI: requiere ~900 MB de pesos en disco, torch/transformers y
varios segundos de carga. Se ejecuta aparte con::

    .\\api\\.venv\\Scripts\\python.exe -m pytest tests -q -m real_models

La prueba se omite limpiamente (``pytest.skip``) si faltan torch/transformers o
los directorios de pesos. Las rutas se resuelven con las variables de entorno
``NLP_SENTIMENT_MODEL_DIR`` / ``NLP_FRAMES_MODEL_DIR`` y, si no están definidas,
con los defaults del proyecto (``api/models/bert-*`` y Desktop).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SENTIMENT_DIR = Path.home() / "Desktop" / "proyecto" / "modelo_sentimiento"
DEFAULT_FRAMES_DIR = Path.home() / "Desktop" / "proyecto" / "modelo_encuadre"

#: Noticia real del corpus etiquetado: ``articulo_63`` con
#: ``sentimiento=Negativo`` y ``Seguridad=1``
#: (``Data/dataset_migracion_venezolana_labeled.csv``). Se pega el ``Cuerpo``
#: crudo exacto: el modelo BETO debe predecir Negativo y colocar ``seguridad``
#: en el top-3 de encuadres (en la evaluación real: Negativo=0.67,
#: seguridad=0.60, ranking #1).
KNOWN_NEGATIVE_TEXT = (
    "Un venezolano, que sobrevivió al fatal incendio en Ciudad Juárez del pasado 27 de marzo, habló con el medio mexicano Univisión Noticias y entregó detalles desconocidos sobre el origen del incendio y los sucesos que sucedieron ese día, en el fatal hecho, que dejó 40 migrantes muertos y decenas de heridos, en un centro en donde estaban encerrados.¿Qué pasó?El incendio ocurrió en un centro de migrantes en donde estaban recluidos ciudadanos de distintas nacionalidades. Inicialmente, de acuerdo con las declaraciones del presidente de México Andrés Manuel López Obrador, el fuego lo habrían iniciado los mismos migrantes, cuando se enteraron de que iban a ser deportados.La Fiscalía General de México informó el pasado 30 de marzo, que tras haber identificado a 8 personas señalados por el incendio, se logró la captura de 5 presuntos responsables. “Ya se ejecutaron cinco” órdenes de aprehensión, dijo la fiscal especializada en Derechos Humanos, Sara Irene Herrerías, en una conferencia de prensa en la que se detalló que los fallecidos fueron 18 guatemaltecos, siete salvadoreños, siete venezolanos, seis hondureños y un colombiano.La falta de agua, inició el fuegoEn entrevista exclusiva con Univision Noticias, el venezolano Eduard de Jesús Caraballo López, quien sobrevivió al incendio, cuenta que Jeison Catari Rivas, uno de los migrantes acusados por la Fiscalía de México de causar el incendio, no tenía en la mano el encendedor con el que se prendió una colchoneta en la celda y asegura que tampoco fue él, quien dio inicio al fatal hecho.Caraballo López recordó ante Univisión Noticias, que durante la tarde de ese día, un grupo de migrantes guatemaltecos exigió a los guardias la entrega de agua potable. Dado que la petición no fue atendida, la tensión aumentaba en las celdas cada vez más, de acuerdo con el testimonio, el ánimo se tornó aún más tenso ante la amenaza de que posiblemente los migrantes serían enviados a Ciudad de México.El grupo de guatemaltecos, cuenta Caraballo, decidió emprender acciones para llamar la atención de los guardias “Vamos a prender una colchoneta y vamos a lanzarla para afuera”, amenazaban y añade que “Tenían entre 18 y 20 días encerrados. Me estaban contando el día que entré (…) Me decían que les pasaban agua de vez en cuando”.Según cuenta el sobreviviente, él intentó disuadir a la gente que pensaba encender fuego, como estrategia de protesta: “Como a las 9:00 pm arranca el incendio. Ellos tenían rato conversando de eso. Yo les decía: ‘Hermano, yo voy a salir ahorita, no se pongan con esa locura’. Pero no me hicieron caso. Traté de quitarles el yesquero (encendedor) y se me revelaron”.El encendedorDe acuerdo con la declaración del sobreviviente venezolano, fue un guardia del centro de detención quien le vendió a uno de los guatemaltecos el encendedor con el que se generó el fuego. Caraballo asegura que los guardias vendían también cigarrillos e incluso marihuana.“Yo empecé a gritarle a mi familia, llamaba a los guardias, no me importa que quedara delante de todos como el chismoso. Les decía (a los guardias): ‘Hermano, van a prender esto, van a prender esto’. No me hicieron caso”, dice, confirmando una de las acusaciones que se han hecho a los vigilantes del lugar, de que no hicieron nada para evitar el avance del fuego. La redadaAlgunos migrantes como Caraballo, habían sido detenidos esa misma tarde del 27 de marzo. Él iba en la misma patrulla que a Jeison Catari Rivas, un venezolano imputado por presuntamente iniciar el incendio a quien Caraballo dice que no le cabe responsabilidad alguna en los hechos “Lo metieron preso y él no estaba en eso”, asegura.La esposa de Caraballo se encontraba esperándolo afuera, con los papeles que demostrarían que él y su familia tenían permiso de estar en México."
)

pytestmark = pytest.mark.real_models


def _first_ready(candidates: list[Path | str | None]) -> Path | None:
    from app.engine.bert_pair import model_dir_ready

    for candidate in candidates:
        if not candidate:
            continue
        if model_dir_ready(candidate):
            return Path(candidate)
    return None


@pytest.fixture(scope="module")
def engine():
    pytest.importorskip(
        "torch", reason="torch no está instalado; instala api/requirements-models.txt"
    )
    pytest.importorskip(
        "transformers",
        reason="transformers no está instalado; instala api/requirements-models.txt",
    )
    from app.engine.bert_pair import BertPairEngine

    sentiment_dir = _first_ready(
        [
            os.environ.get("NLP_SENTIMENT_MODEL_DIR"),
            API_DIR / "models" / "bert-sentiment",
            DEFAULT_SENTIMENT_DIR,
        ]
    )
    frames_dir = _first_ready(
        [
            os.environ.get("NLP_FRAMES_MODEL_DIR"),
            API_DIR / "models" / "bert-frames",
            DEFAULT_FRAMES_DIR,
        ]
    )
    if sentiment_dir is None or frames_dir is None:
        pytest.skip(
            "No se encontraron los pesos BETO. Configura NLP_SENTIMENT_MODEL_DIR y "
            "NLP_FRAMES_MODEL_DIR (o colócalos en api/models/bert-sentiment y "
            "api/models/bert-frames). Esperados por defecto: "
            f"{DEFAULT_SENTIMENT_DIR} y {DEFAULT_FRAMES_DIR}"
        )

    real_engine = BertPairEngine(
        sentiment_model_dir=sentiment_dir,
        frames_model_dir=frames_dir,
        device="cpu",
        max_length=512,
    )
    yield real_engine
    real_engine.unload()


def test_engine_real_carga_las_dos_cabezas(engine) -> None:
    from app.engine.labels import FRAME_IDS, SENTIMENT_LABELS, MODEL_DISPLAY_NAME

    descriptors = engine.models
    assert len(descriptors) == 2
    assert {descriptor.role for descriptor in descriptors} == {"sentiment", "frames"}
    assert engine.display_name == MODEL_DISPLAY_NAME
    for descriptor in descriptors:
        assert descriptor.available is True
        assert descriptor.loaded is True
        assert descriptor.path

    sentiment_descriptor = next(d for d in descriptors if d.role == "sentiment")
    frames_descriptor = next(d for d in descriptors if d.role == "frames")
    assert sentiment_descriptor.labels == list(SENTIMENT_LABELS)
    assert len(frames_descriptor.labels) == len(FRAME_IDS)


def test_noticia_negativa_conocida_predice_negativo_y_seguridad(engine) -> None:
    from app.engine.labels import FRAME_IDS, SENTIMENT_LABELS

    prediction = engine.predict(KNOWN_NEGATIVE_TEXT)

    assert set(prediction.sentiment) == set(SENTIMENT_LABELS)
    assert prediction.preprocessing == "bert-tokenizer"
    assert sum(prediction.sentiment.values()) == pytest.approx(1.0, abs=1e-4)

    predicted_sentiment = max(prediction.sentiment, key=prediction.sentiment.get)
    assert predicted_sentiment == "Negativo", (
        "La noticia negativa conocida debe predecirse como Negativo; "
        f"scores={prediction.sentiment}"
    )

    assert set(prediction.frames) == set(FRAME_IDS)
    top3 = sorted(prediction.frames, key=prediction.frames.get, reverse=True)[:3]
    assert "seguridad" in top3, (
        "El encuadre Seguridad debe estar entre los 3 primeros; "
        f"top3={top3} scores={prediction.frames}"
    )
    assert all(0.0 <= score <= 1.0 for score in prediction.frames.values())
