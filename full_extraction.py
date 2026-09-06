from extraction_codes.extraction_el_espectador import extraer_el_espectador
from extraction_codes.extraction_el_heraldo import extraer_el_heraldo
from extraction_codes.extraction_el_heraldo_mexico import extraer_el_heraldo_mexico
from extraction_codes.extraction_el_milenio_mexico import extraer_milenio_mexico

import pandas as pd

def extraer_data_completa():

    # Extracción: para hacer extracción completa quitar el "limite=5"

    df_elespectador = extraer_el_espectador(limite=5)
    df_elheraldo = extraer_el_heraldo(limite=5)
    df_elheraldo_mexico = extraer_el_heraldo_mexico(limite=5)
    df_elmilenio_mexico = extraer_milenio_mexico(limite=5)
    # Inspección rápida

    print(df_elespectador.head())
    print(df_elheraldo.head())
    print(df_elheraldo_mexico.head())

    # Unión

    df_total = pd.concat(
        [
            df_elespectador,
            df_elheraldo,
            df_elheraldo_mexico,
            df_elmilenio_mexico
        ],
        ignore_index=True 
    )

    print("El Espectador:", len(df_elespectador))
    print("El Heraldo:", len(df_elheraldo))
    print("El Heraldo México:", len(df_elheraldo_mexico))
    print("Milenio:", len(df_elmilenio_mexico))

    print(df_elespectador.columns.tolist())
    print(df_elheraldo.columns.tolist())
    print(df_elheraldo_mexico.columns.tolist())
    print(df_elmilenio_mexico.columns.tolist())
    
    # CSV final único

    df_total.to_csv(
        "Data/dataset_migracion_venezolana.csv",
        index=True,
        encoding="utf-8-sig"
    )

    print(f"\n✅ Registros totales: {len(df_total)}")
    print("✅ Archivo: Data/dataset_migracion_venezolana.csv")


extraer_data_completa()