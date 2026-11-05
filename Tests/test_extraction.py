import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pytest

from extraction.extraction_semana import extraer_semana
from extraction.extraction_el_milenio_mexico import extraer_milenio_mexico
from extraction.extraction_la_cronica_mexico import extraer_cronica_mexico


@pytest.mark.parametrize(
    "func,kwargs",
    [
        (extraer_semana, {"query": "migrantes venezolanos"}),
        (extraer_milenio_mexico, {"limite": 5}),
        (extraer_cronica_mexico, {"limite": 5}),
    ],
)
def test_extractores(func, kwargs):
    df = func(**kwargs)

    assert not df.empty
    assert len(df) > 0