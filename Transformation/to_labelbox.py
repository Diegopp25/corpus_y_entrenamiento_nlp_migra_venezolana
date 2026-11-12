import pandas as pd
import labelbox as lb
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

def enviar_a_labelbox(df, api_key):
    if not api_key:
        raise ValueError("Configura LABELBOX_API_KEY en el entorno o en el archivo .env.")

    required_columns = {"ID", "Cuerpo"}
    missing_columns = required_columns.difference(df.columns)
    if missing_columns:
        raise ValueError(f"Faltan columnas requeridas en el CSV: {', '.join(sorted(missing_columns))}")

    # =====================================
    # CONECTAR A LABELBOX
    # =====================================

    client = lb.Client(api_key)

    # Crear dataset
    dataset = client.create_dataset(
        name="Noticias_Migracion_more"
    )

    # =====================================
    # CONSTRUIR DATA ROWS
    # =====================================

    data_rows = []

    for _, row in df.iterrows():

        data_rows.append(
            {
                "row_data": row["Cuerpo"],
                "global_key": row["ID"]
            }
        )

    # =====================================
    # SUBIR A LABELBOX
    # =====================================

    task = dataset.create_data_rows(data_rows)

    task.wait_till_done()

    print("Dataset cargado correctamente")
    print(f"Total registros: {len(data_rows)}")


if __name__ == "__main__":
    root_dir = Path(__file__).resolve().parent.parent
    csv_path = root_dir / "data" / "dataset_migracion_venezolana_probando.csv"
    api_key = os.getenv("LABELBOX_API_KEY")
    df = pd.read_csv(csv_path)
    enviar_a_labelbox(df, api_key)

