from extraction_codes.extraction_el_espectador import extraer_el_espectador
from extraction_codes.extraction_el_heraldo import extraer_el_heraldo
from extraction_codes.extraction_el_heraldo_mexico import extraer_el_heraldo_mexico

import pandas as pd

# Extracción

df_elespectador = extraer_el_espectador()
df_elheraldo = extraer_el_heraldo()
df_elheraldo_mexico = extraer_el_heraldo_mexico()

# Inspección rápida

print(df_elespectador.head())
print(df_elheraldo.head())
print(df_elheraldo_mexico.head())

# Unión

df_total = pd.concat(
    [
        df_elespectador,
        df_elheraldo,
        df_elheraldo_mexico
    ],
    ignore_index=True
)

# CSV final único

df_total.to_csv(
    "Data/dataset_migracion_venezolana.csv",
    index=False,
    encoding="utf-8-sig"
)

print(f"\n✅ Registros totales: {len(df_total)}")
print("✅ Archivo: Data/dataset_migracion_venezolana.csv")