

import re
import json
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup

# ==========================
# CONFIGURACIÓN
# ==========================

QUERIES = [
    "migración venezolana",
    "migrantes venezolanos",
    "migrantes venezolanas",
    "migrante venezolano",
    "migrante venezolana"
]
QUERYLY_KEY = "5a632fcb9cec48db"
BASE_URL = "https://www.elheraldo.co"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}




# ==========================
# BÚSQUEDA
# ==========================
def obtener_resultados_busqueda():

    resultados = []

    for query in QUERIES:

        print(f"\nBuscando: {query}")

        params = {
            "queryly_key": QUERYLY_KEY,
            "query": query,
            "endindex": 0,
            "batchsize": 200,
            "showfaceted": "true"
        }

        r = requests.get(
            "https://api.queryly.com/json.aspx",
            params=params,
            headers=HEADERS,
            timeout=30
        )

        print("Status búsqueda:", r.status_code)

        texto = r.text

        titulos = re.findall(
            r'"title":"([^"]+)"',
            texto
        )

        links = re.findall(
            r'"link":"([^"]+)"',
            texto
        )

        for titulo, link in zip(titulos, links):

            if not link.startswith("http"):
                link = BASE_URL + link

            resultados.append({
                "titulo_busqueda": titulo,
                "url": link
            })

    # Eliminar duplicados por URL
    urls_vistas = set()
    resultados_unicos = []

    for item in resultados:

        if item["url"] not in urls_vistas:
            urls_vistas.add(item["url"])
            resultados_unicos.append(item)

    print("Resultados encontrados:", len(resultados))
    print("Resultados únicos:", len(resultados_unicos))

    return resultados_unicos

# ==========================
# EXTRACCIÓN ARTÍCULO
# ==========================

def extraer_texto_articulo(url):

    try:

        r = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        if r.status_code != 200:

            print("Error:", r.status_code, url)
            return None

        soup = BeautifulSoup(
            r.text,
            "html.parser"
        )

        # ==========================
        # TÍTULO
        # ==========================

        titulo = ""

        og_title = soup.find(
            "meta",
            property="og:title"
        )

        if og_title:

            titulo = og_title.get(
                "content",
                ""
            ).strip()

        if not titulo:

            h1 = soup.find("h1")

            if h1:

                titulo = h1.get_text(
                    " ",
                    strip=True
                )

        # ==========================
        # FECHA Y AUTOR
        # ==========================

        fecha = ""
        autor = ""

        for script in soup.find_all(
            "script",
            type="application/ld+json"
        ):

            try:

                if not script.string:
                    continue

                data = json.loads(
                    script.string
                )

                if isinstance(data, list):

                    datos = data

                else:

                    datos = [data]

                for item in datos:

                    if not isinstance(item, dict):
                        continue

                    if not fecha:

                        fecha = (
                            item.get("datePublished", "")
                            or item.get("dateCreated", "")
                            or item.get("dateModified", "")
                        )

                    if not autor:

                        a = item.get("author")

                        if isinstance(a, dict):

                            autor = a.get(
                                "name",
                                ""
                            )

                        elif isinstance(a, list):

                            autores = []

                            for x in a:

                                if isinstance(x, dict):

                                    nombre = x.get(
                                        "name",
                                        ""
                                    )

                                    if nombre:
                                        autores.append(
                                            nombre
                                        )

                            autor = ", ".join(
                                autores
                            )

            except Exception:
                pass

        # ==========================
        # RESPALDO FECHA
        # ==========================

        if not fecha:

            meta_fecha = soup.find(
                "meta",
                property="article:published_time"
            )

            if meta_fecha:

                fecha = meta_fecha.get(
                    "content",
                    ""
                ).strip()

        # ==========================
        # RESPALDO AUTOR
        # ==========================

        if not autor:

            meta_autor = soup.find(
                "meta",
                attrs={"name": "author"}
            )

            if meta_autor:

                autor = meta_autor.get(
                    "content",
                    ""
                ).strip()

        if not autor:

            meta_autor = soup.find(
                "meta",
                property="article:author"
            )

            if meta_autor:

                autor = meta_autor.get(
                    "content",
                    ""
                ).strip()

        # ==========================
        # CUERPO DEL ARTÍCULO
        # ==========================

        texto = []

        for p in soup.select("article p"):

            t = p.get_text(
                " ",
                strip=True
            )

            if len(t) > 200:

                texto.append(t)

        # Respaldo

        if len(texto) < 3:

            texto = []

            for p in soup.find_all("p"):

                t = p.get_text(
                    " ",
                    strip=True
                )

                if len(t) > 40:

                    texto.append(t)

        cuerpo = "\n".join(texto)

        return {
            "Titulo": titulo,
            "URL": url,
            "Cuerpo": cuerpo,
            "Fecha": fecha,
            "Autor": autor,
            "Pais": "Colombia",
            "Medio": "El Heraldo"
        }

    except Exception as e:

        print("ERROR:", url)
        print(e)

        return None


# ==========================
# PROCESO PRINCIPAL
# ==========================


def extraer_el_heraldo(limite=None):

    urls = obtener_resultados_busqueda()
    if limite is not None:
        urls = urls[:limite]

    
    print("\nPrimeros enlaces encontrados:\n")

    for item in urls[:5]:
        print(item["url"])

    noticias = []

    for i, item in enumerate(urls, start=1):

        print(
            f"\n[{i}/{len(urls)}] {item['url']}"
        )

        resultado = extraer_texto_articulo(
            item["url"]
        )

        if resultado:

            longitud = len(
                resultado["Cuerpo"]
            )

            print(
                "Título:",
                resultado["Titulo"][:80]
            )

            print(
                "Autor:",
                resultado["Autor"]
            )

            print(
                "Fecha:",
                resultado["Fecha"]
            )

            print(
                "Caracteres:",
                longitud
            )

            noticias.append(
                resultado
            )

        time.sleep(1)


    df = pd.DataFrame(noticias)

    df.to_csv(
                "Data/el_heraldo_colombia_migracion_venezolana.csv",
                index=False,
                encoding="utf-8-sig"
            )


    return df

