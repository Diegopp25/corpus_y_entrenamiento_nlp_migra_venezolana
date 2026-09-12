# ===========================================================
# LIBRERÍAS
# ===========================================================

import requests
import pandas as pd
import json
import re
import time

from bs4 import BeautifulSoup


# ============================================================
# CONFIGURACIÓN
# ============================================================

QUERYLY_KEY = "06e63be824464567"

BUSQUEDA = "migrantes venezolanos"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    )
}

BASE_URL = "https://www.semana.com"


# ============================================================
# LIMPIEZA
# ============================================================

def limpiar_texto(texto):
    if not texto:
        return ""

    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


# ============================================================
# OBTENER RESULTADOS DESDE QUERYLY
# ============================================================

def obtener_resultados_queryly(
    query,
    queryly_key=QUERYLY_KEY,
    batchsize=80,
):
    """
    Devuelve una lista con todos los resultados encontrados.
    """

    resultados = []

    endindex = 0
    total = None

    while True:

        params = {
            "queryly_key": queryly_key,
            "query": query,
            "endindex": endindex,
            "batchsize": batchsize,
            "callback": "searchPage.resultcallback",
            "showfaceted": "true",
            "extendeddatafields": "creator,imageresizer,promo_image",
            "timezoneoffset": "300",
        }

        url = "https://api.queryly.com/json.aspx"

        response = requests.get(
            url,
            params=params,
            headers=HEADERS,
            timeout=30
        )

        response.raise_for_status()

        texto = response.text

        match = re.search(
            r"searchPage\.resultcallback\((.*?)\)\s*;",
            texto,
            re.DOTALL
        )

        if not match:
            raise ValueError("No se encontró el JSON de Queryly")

        json_text = match.group(1)

        data = json.loads(json_text)

        if total is None:
            total = data["metadata"]["total"]
            print(f"Total resultados encontrados: {total}")

        items = data.get("items", [])

        if not items:
            break

        resultados.extend(items)

        print(
            f"Resultados acumulados: "
            f"{len(resultados)} / {total}"
        )

        endindex += batchsize

        if len(resultados) >= 10:
            break

        time.sleep(1)

    return resultados


# ============================================================
# EXTRAER CUERPO DE UNA NOTICIA
# ============================================================

def extraer_cuerpo_articulo(url):
    """
    Busca articleBody dentro del JSON-LD.
    """

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        scripts = soup.find_all(
            "script",
            type="application/ld+json"
        )

        for script in scripts:

            try:
                contenido = script.string

                if not contenido:
                    continue

                data = json.loads(contenido)

                if isinstance(data, dict):

                    cuerpo = data.get("articleBody")

                    if cuerpo:
                        return limpiar_texto(cuerpo)

            except Exception:
                continue

    except Exception as e:
        print(f"Error en artículo: {url}")
        print(e)

    return ""


# ============================================================
# EXTRAER SEMANA
# ============================================================

def extraer_semana(query="migrantes venezolanos"):

    resultados = obtener_resultados_queryly(query)

    noticias = []

    for i, item in enumerate(resultados, start=1):

        try:

            titulo = item.get("title", "")

            url_relativa = item.get("link", "")

            if not url_relativa:
                continue

            url = BASE_URL + url_relativa

            autor = item.get("creator", "")

            fecha = item.get("pubdate", "")

            print(
                f"[{i}/{len(resultados)}] "
                f"Extrayendo: {titulo[:80]}"
            )

            cuerpo = extraer_cuerpo_articulo(url)

            noticias.append(
                {
                    "Titulo": limpiar_texto(titulo),
                    "URL": url,
                    "Cuerpo": cuerpo,
                    "Autor": limpiar_texto(autor),
                    "Medio": "Semana",
                    "Pais": "Colombia",
                    "Fecha": fecha
                }
            )

            time.sleep(0.5)

        except Exception as e:
            print(f"Error procesando noticia {i}: {e}")

    df = pd.DataFrame(noticias)

    df.to_csv(

        "Data/semana_colombia_migracion_venezolana.csv",
        index = False,
        encoding="utf-8-sig"

    )

    return df


