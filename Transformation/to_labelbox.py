import pandas as pd
import labelbox as lb
import os
from dotenv import load_dotenv

load_dotenv()

def enviar_a_labelbox(df):

    # =====================================
    # CONFIGURACIÓN
    # =====================================

    API_KEY = os.getenv("LABELBOX_API_KEY")
    CSV_PATH = "Data/dataset_migracion_venezolana_limpio_estandarizado.csv"

    df = pd.read_csv(CSV_PATH)

    enviar_a_labelbox(
        df=df,
        api_key=API_KEY,
        csv_path=CSV_PATH
    )
    # =====================================
    # CONECTAR A LABELBOX
    # =====================================

    client = lb.Client(API_KEY)

    # Crear dataset
    dataset = client.create_dataset(
        name="Noticias_Migracion"
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


