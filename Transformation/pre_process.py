"""
Pipeline de preprocesamiento del dataset de migración venezolana.

Replica la sección "Preprocesamiento" de brute_dataset.ipynb:

    1. Asignar ID a cada artículo
    2. Eliminar filas con nulos
    3. Eliminar cuerpos textuales duplicados
    4. Corregir texto "roto" (entidades HTML como &aacute;)
    5. Eliminar el artículo más corto (solo ofrece suscripción / sin contenido)
    6. Estandarizar fechas (YYYY-MM-DD)
    7. Anonimizar autores
    8. (Opcional) Unir las etiquetas exportadas de Labelbox y reordenar columnas

Uso:
    python preprocessing.py                       # solo limpieza, sin etiquetas
    python preprocessing.py --labels Data/labels.csv   # limpieza + etiquetas

Uso como módulo:
    from preprocessing import run_pipeline
    df = run_pipeline(labels_path="Data/labels.csv")
"""

from __future__ import annotations

import argparse
import html
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------- #
# Configuración
# --------------------------------------------------------------------------- #
RAW_PATH = ["Data/dataset_migracion_venezolana.csv"]
LABELS_PATH = ["Data/labels.csv"]
OUTPUT_LABELED_PATH = "Data/dataset_migracion_venezolana_labeled_test.csv"
OUTPUT_CLEAN_PATH = "Data/dataset_migracion_venezolana_clean.csv"
AUTHORS_PATHS = "Data/Anon/dataset_autores_anonimizados.csv"


HTML_ENTITY_PATTERN = r"&[a-zA-Z]+;"


# --------------------------------------------------------------------------- #
# Pasos
# --------------------------------------------------------------------------- #
def add_id(df: pd.DataFrame) -> pd.DataFrame:
    """Elimina la columna índice sin título (si existe) y crea la columna ID.

    Debe ejecutarse ANTES de eliminar filas: los IDs (articulo_1, articulo_2...)
    son los que se usan para cruzar con las etiquetas de Labelbox, así que
    quedan con "huecos" cuando se descartan filas después.
    """
    df = df.copy()
    if str(df.columns[0]).startswith("Unnamed"):
        df = df.iloc[:, 1:]
    df.insert(0, "ID", [f"articulo_{i}" for i in range(1, len(df) + 1)])
    return df


def drop_nulls(df: pd.DataFrame) -> pd.DataFrame:
    """Elimina filas con cualquier valor nulo."""
    return df.dropna(how="any")


def drop_duplicate_bodies(df: pd.DataFrame) -> pd.DataFrame:
    """Elimina noticias con cuerpo textual repetido."""
    return df.drop_duplicates(subset=["Cuerpo"]).reset_index(drop=True)


def fix_html_entities(df: pd.DataFrame) -> pd.DataFrame:
    """Decodifica entidades HTML (&aacute; -> á) en los cuerpos afectados."""
    df = df.copy()
    mask = df["Cuerpo"].fillna("").str.contains(HTML_ENTITY_PATTERN, regex=True)
    df.loc[mask, "Cuerpo"] = df.loc[mask, "Cuerpo"].apply(html.unescape)
    return df


def drop_shortest_body(df: pd.DataFrame) -> pd.DataFrame:
    """Elimina el artículo con menos palabras (cuerpo que solo ofrece suscripción)."""
    n_words = df["Cuerpo"].fillna("").str.split().str.len()
    return df.drop(n_words.idxmin()).reset_index(drop=True)


def standardize_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Convierte formatos de fecha mixtos a YYYY-MM-DD (requiere pandas >= 2.0)."""
    df = df.copy()
    fechas = pd.to_datetime(df["Fecha"], format="mixed", errors="coerce")
    df["Fecha"] = fechas.dt.strftime("%Y-%m-%d")
    return df


def anonymize_authors(
    df: pd.DataFrame,
    output_paths: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reemplaza el nombre de cada autor por AutorID_n.

    Devuelve (df anonimizado, tabla de equivalencias Autor <-> ID_Autor).
    La tabla se guarda en cada ruta de `output_paths`.
    """
    df = df.copy()
    autores_unicos = df["Autor"].unique()
    df_autores = pd.DataFrame(
        {
            "ID_Autor": [f"AutorID_{i}" for i in range(1, len(autores_unicos) + 1)],
            "Autor": autores_unicos,
        }
    )

    for path in output_paths or []:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        df_autores.to_csv(path, index=False, encoding="utf-8-sig")

    mapa_autores = dict(zip(df_autores["Autor"], df_autores["ID_Autor"]))
    df["Autor"] = df["Autor"].map(mapa_autores)
    return df, df_autores


def merge_labels(df: pd.DataFrame, labels_path: str) -> pd.DataFrame:
    """Une las etiquetas exportadas de Labelbox por ID (left join)."""
    df_labels = pd.read_csv(labels_path)
    return df.merge(df_labels, on="ID", how="left")


def move_body_before_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Reubica 'Cuerpo' justo antes de la columna 'sentimiento'."""
    cols = list(df.columns)
    cols.remove("Cuerpo")
    cols.insert(cols.index("sentimiento"), "Cuerpo")
    return df[cols]


# --------------------------------------------------------------------------- #
# Pipeline completo
# --------------------------------------------------------------------------- #
def run_pipeline(
    input_path: str = RAW_PATH,
    labels_path: str | None = None,
    output_path: str | None = None,
    authors_paths: list[str] | None = None,
) -> pd.DataFrame:
    """Ejecuta el preprocesamiento y guarda el CSV resultante."""
    if authors_paths is None:
        authors_paths = AUTHORS_PATHS
    if output_path is None:
        output_path = OUTPUT_LABELED_PATH if labels_path else OUTPUT_CLEAN_PATH

    df = pd.read_csv(input_path)

    df = add_id(df)
    df = drop_nulls(df)
    df = drop_duplicate_bodies(df)
    df = fix_html_entities(df)
    df = drop_shortest_body(df)
    df = standardize_dates(df)
    df, _ = anonymize_authors(df, authors_paths)

    if labels_path:
        df = merge_labels(df, labels_path)
        df = move_body_before_labels(df)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Pipeline terminado: {len(df)} registros -> {output_path}")
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--input", default=RAW_PATH, help="CSV crudo de entrada")
    parser.add_argument(
        "--labels",
        default=None,
        help=f"CSV de etiquetas de Labelbox (ej. {LABELS_PATH}). Si se omite, no se unen etiquetas.",
    )
    parser.add_argument("--output", default=None, help="CSV de salida")
    args = parser.parse_args()

    run_pipeline(args.input, args.labels, args.output)


if __name__ == "__main__":
    main()