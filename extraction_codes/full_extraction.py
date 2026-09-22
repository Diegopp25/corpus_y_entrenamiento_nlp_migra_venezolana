from extraction_codes.extraction_semana import extraer_semana
from extraction_codes.extraction_el_milenio_mexico import extraer_milenio_mexico

import pandas as pd

def extraer_data_completa(x):

    # Extracción: para hacer extracción completa quitar el "limite=5"

    df_semana = extraer_semana(query="migrantes venezolanos")
    df_elmilenio_mexico = extraer_milenio_mexico(limite=x)

    # Inspección rápida

    print(df_semana.head())
    print(df_elmilenio_mexico.head())


    # Unión

    df_total = pd.concat(
        [
            df_semana,
            df_elmilenio_mexico
        ],
        ignore_index=True 
    )

    print(f"\n✅ Registros totales: {len(df_total)}")

    return df_total


