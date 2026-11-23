from pathlib import Path
import pandas as pd
import html


class PreprocessingPipeline:
    def __init__(self):
        self.author_map = None

    def add_article_id(self, df):
        # Eliminar columna índice original si existe
        first_col = df.columns[0]

        if first_col.startswith("Unnamed"):
            df = df.iloc[:, 1:].copy()

        df.insert(
            0,
            "ID",
            [f"articulo_{i}" for i in range(1, len(df) + 1)]
        )

        return df

    def remove_null_rows(self, df):
        return df.dropna(how="any").reset_index(drop=True)

    def remove_duplicate_articles(self, df):
        return (
            df.drop_duplicates(subset=["Cuerpo"])
              .reset_index(drop=True)
        )

    def fix_html_entities(self, df):
        mask = (
            df["Cuerpo"]
            .fillna("")
            .str.contains(r"&[a-zA-Z]+;", regex=True)
        )

        df.loc[mask, "Cuerpo"] = (
            df.loc[mask, "Cuerpo"]
            .apply(html.unescape)
        )

        return df

    def remove_shortest_article(self, df):
        lengths = (
            df["Cuerpo"]
            .fillna("")
            .str.split()
            .str.len()
        )

        idx_min = lengths.idxmin()

        return (
            df.drop(idx_min)
              .reset_index(drop=True)
        )

    def standardize_dates(self, df):
        df["Fecha"] = pd.to_datetime(
            df["Fecha"],
            format="mixed",
            errors="coerce"
        )

        df["Fecha"] = df["Fecha"].dt.strftime("%Y-%m-%d")

        return df

    def anonymize_authors(
        self,
        df,
        authors_output_path=None
    ):
        unique_authors = df["Autor"].unique()

        authors_df = pd.DataFrame({
            "ID_Autor": [
                f"AutorID_{i}"
                for i in range(1, len(unique_authors) + 1)
            ],
            "Autor": unique_authors
        })

        self.author_map = dict(
            zip(
                authors_df["Autor"],
                authors_df["ID_Autor"]
            )
        )

        df["Autor"] = df["Autor"].map(self.author_map)

        if authors_output_path:
            authors_df.to_csv(
                authors_output_path,
                index=False,
                encoding="utf-8-sig"
            )

        return df

    def reorder_columns(self, df):
        if "sentimiento" not in df.columns:
            return df

        cols = list(df.columns)

        cols.remove("Cuerpo")

        pos_sentimiento = cols.index("sentimiento")

        cols.insert(pos_sentimiento, "Cuerpo")

        return df[cols]

    def run(
        self,
        df,
        authors_output_path=None
    ):
        print("1. Agregando ID...")
        df = self.add_article_id(df)

        print("2. Eliminando nulos...")
        df = self.remove_null_rows(df)

        print("3. Eliminando duplicados...")
        df = self.remove_duplicate_articles(df)

        print("4. Corrigiendo entidades HTML...")
        df = self.fix_html_entities(df)

        print("5. Eliminando artículo basura...")
        df = self.remove_shortest_article(df)

        print("6. Estandarizando fechas...")
        df = self.standardize_dates(df)

        print("7. Anonimizando autores...")
        df = self.anonymize_authors(
            df,
            authors_output_path
        )

        print("8. Reordenando columnas...")
        df = self.reorder_columns(df)

        print(f"Pipeline finalizado. Registros: {len(df)}")

        return df