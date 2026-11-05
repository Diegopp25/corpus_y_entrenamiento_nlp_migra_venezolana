import pandas as pd
ROOT_DIR = path(__file__).resolve().parent
# Cargar archivos
df1 = pd.read_csv(f"{ROOT_DIR}/data/dataset_migracion_venezolana.csv")
df2 = pd.read_csv(f"{ROOT_DIR}/data/cronica_mexico.csv")

# Unir datasets
df_merged = pd.concat([df1, df2], ignore_index=True)

# Guardar resultado
df_merged.to_csv(f"{ROOT_DIR}/data/dataset_merged.csv", index=False)

print(f"Filas totales: {len(df_merged)}")