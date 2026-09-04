from extraction_codes.extraction_el_espectador import extraer_el_espectador
from extraction_codes.extraction_el_heraldo import extraer_el_heraldo
from extraction_codes.extraction_el_heraldo_mexico import extraer_el_heraldo_mexico

import pandas as pd

df_elespectador= extraer_el_espectador()
df_elheraldo = extraer_el_heraldo()
df_elheraldo_mexico = extraer_el_heraldo_mexico()

df_elespectador.head()
df_elheraldo.head()
df_elheraldo_mexico.head()