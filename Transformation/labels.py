import json
import pandas as pd

NDJSON_PATH = "Transformation/LandingStage/labels.ndjson"
CSV_PATH = "Transformation/LandingStage/labels.csv"

# =====================================================
# PASO 1: Descubrir automáticamente todos los encuadres
# =====================================================

encuadres = set()

with open(NDJSON_PATH, "r", encoding="utf-8") as f:

    for line in f:

        item = json.loads(line)

        project = next(iter(item["projects"].values()))
        label = project["labels"][0]

        for classification in label["annotations"]["classifications"]:

            if classification["name"] == "Dimensiones de encuadre":

                for ans in classification.get("checklist_answers", []):
                    encuadres.add(ans["name"])

encuadres = sorted(encuadres)

print("Encuadres encontrados:")
print(encuadres)

# =====================================================
# PASO 2: Construir el dataframe
# =====================================================

rows = []

with open(NDJSON_PATH, "r", encoding="utf-8") as f:

    for line in f:

        item = json.loads(line)

        fila = {
            "ID": item["data_row"]["global_key"],
            "sentimiento": None
        }

        # Inicializar todas las columnas de encuadre en 0
        for encuadre in encuadres:
            fila[encuadre] = 0

        project = next(iter(item["projects"].values()))
        label = project["labels"][0]

        for classification in label["annotations"]["classifications"]:

            # Encuadres
            if classification["name"] == "Dimensiones de encuadre":

                for ans in classification.get("checklist_answers", []):

                    encuadre = ans["name"]

                    if encuadre in fila:
                        fila[encuadre] = 1

            # Sentimiento
            elif classification["name"] == "Sentimiento":

                fila["sentimiento"] = (
                    classification["radio_answer"]["name"]
                )

        rows.append(fila)

# =====================================================
# PASO 3: Crear dataframe y exportar
# =====================================================

df_labels = pd.DataFrame(rows)

# Ordenar columnas:
columnas = (
    ["ID", "sentimiento"]
    + encuadres
)

df_labels = df_labels[columnas]

print(df_labels.head())

df_labels.to_csv(
    CSV_PATH,
    index=False,
    encoding="utf-8-sig"
)

print(f"\nArchivo exportado: {CSV_PATH}")
print(f"Registros: {len(df_labels)}")
print(f"Encuadres detectados: {len(encuadres)}")