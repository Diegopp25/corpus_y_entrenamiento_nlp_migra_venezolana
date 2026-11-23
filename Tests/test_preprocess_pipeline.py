import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from Transformation.pre_process import PreprocessingPipeline


@pytest.fixture(scope="module")
def pipeline():
    return PreprocessingPipeline()


@pytest.fixture
def df_raw():
    return pd.DataFrame(
        {
            "Unnamed: 0": [0, 1, 2, 3],
            "Cuerpo": [
                "Texto largo del primer artículo con varias palabras",
                "Texto largo del primer artículo con varias palabras",
                "Otro artículo &amp; con entidad &#39;numérica&#39; incluida",
                "corto",
            ],
            "Fecha": [
                "2024-03-05",
                "2024-03-05",
                "2024-03-06",
                "2024-03-07",
            ],
            "Autor": [
                "Ana",
                "Ana",
                "Luis",
                "Ana",
            ],
            "URL": [
                "u1",
                "u1",
                "u2",
                "u3",
            ],
        }
    )


# =====================================================
# add_article_id
# =====================================================

def test_add_article_id_creates_unique_ids(
    pipeline,
    df_raw,
):
    out = pipeline.add_article_id(df_raw.copy())

    assert "ID" in out.columns
    assert out["ID"].is_unique

    expected = [
        f"articulo_{i}"
        for i in range(1, len(out) + 1)
    ]

    assert out["ID"].tolist() == expected


def test_add_article_id_removes_unnamed_column(
    pipeline,
    df_raw,
):
    out = pipeline.add_article_id(df_raw.copy())

    assert "Unnamed: 0" not in out.columns


def test_add_article_id_does_not_mutate_input(
    pipeline,
):
    df = pd.DataFrame(
        {"Cuerpo": ["a", "b"]}
    )

    original = df.copy(deep=True)

    pipeline.add_article_id(df)

    pd.testing.assert_frame_equal(
        df,
        original,
    )


# =====================================================
# fix_html_entities
# =====================================================

@pytest.mark.parametrize(
    "raw,expected",
    [
        (
            "Tom &amp; Jerry",
            "Tom & Jerry",
        ),
        (
            "Prueba &#39;texto&#39;",
            "Prueba 'texto'",
        ),
        (
            "&lt;b&gt;hola&lt;/b&gt;",
            "<b>hola</b>",
        ),
    ],
)
def test_fix_html_entities(
    pipeline,
    raw,
    expected,
):
    df = pd.DataFrame(
        {
            "Cuerpo": [raw]
        }
    )

    out = pipeline.fix_html_entities(df)

    assert (
        out["Cuerpo"].iloc[0]
        == expected
    )


# =====================================================
# remove_shortest_article
# =====================================================

def test_remove_shortest_article_removes_one_row(
    pipeline,
):
    df = pd.DataFrame(
        {
            "Cuerpo": [
                "muy largo texto",
                "medio",
                "x",
            ]
        }
    )

    out = pipeline.remove_shortest_article(df)

    assert len(out) == 2
    assert "x" not in out["Cuerpo"].values


def test_remove_shortest_article_empty_df(
    pipeline,
):
    df = pd.DataFrame(
        {"Cuerpo": []}
    )

    with pytest.raises(ValueError):
        pipeline.remove_shortest_article(df)


# =====================================================
# standardize_dates
# =====================================================

@pytest.mark.parametrize(
    "raw,expected",
    [
        (
            "2024-03-05",
            "2024-03-05",
        ),
        (
            "05/03/2024",
            "2024-03-05",
        ),
        (
            "05-03-2024",
            "2024-03-05",
        ),
    ],
)
def test_standardize_dates(
    pipeline,
    raw,
    expected,
):
    df = pd.DataFrame(
        {
            "Fecha": [raw]
        }
    )

    out = pipeline.standardize_dates(df)

    assert (
        out["Fecha"].iloc[0]
        == expected
    )


# =====================================================
# anonymize_authors
# =====================================================

def test_anonymize_authors_is_consistent(
    pipeline,
    tmp_path,
):
    df = pd.DataFrame(
        {
            "Autor": [
                "Ana",
                "Luis",
                "Ana",
            ]
        }
    )

    output_file = (
        tmp_path
        / "autores.csv"
    )

    out = pipeline.anonymize_authors(
        df,
        output_file,
    )

    assert (
        out["Autor"].iloc[0]
        ==
        out["Autor"].iloc[2]
    )

    assert (
        out["Autor"].iloc[0]
        !=
        out["Autor"].iloc[1]
    )

    assert output_file.exists()


# =====================================================
# E2E
# =====================================================

def test_run_end_to_end_properties(
    pipeline,
    df_raw,
    tmp_path,
):
    authors_file = (
        tmp_path
        / "authors.csv"
    )

    urls_file = (
        tmp_path
        / "urls.csv"
    )

    out = pipeline.run(
        df_raw.copy(),
        authors_file,
        urls_file,
    )

    assert len(out) > 0

    assert out["ID"].is_unique

    assert not out.isna().any().any()

    assert not (
        out["Autor"]
        .isin(["Ana", "Luis"])
        .any()
    )

    assert authors_file.exists()
    assert urls_file.exists()


def test_pipeline_preserves_required_columns(
    pipeline,
    df_raw,
    tmp_path,
):
    out = pipeline.run(
        df_raw.copy(),
        tmp_path / "a.csv",
        tmp_path / "u.csv",
    )

    expected = {
        "ID",
        "Cuerpo",
        "Fecha",
        "Autor",
    }

    assert expected.issubset(out.columns)