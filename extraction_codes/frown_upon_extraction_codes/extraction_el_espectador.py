# ======================================================
# Librerías
# ======================================================

import json
import re
import html
import requests
import pandas as pd
import time

# ======================================================
# CONFIG
# ======================================================

HEADERS = {

    "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/138.0 Safari/537.36"

}

API_URL = (
    "https://www.elespectador.com/"
    "pf/api/v3/content/fetch/searcherTag"
)

KEYWORD = "migración-venezolana"


#La api del espectador extrae del cuerpo los <div>, <b>, \r, \n, etc. del html. Esta función limpia lo anterior.

# ======================================================
# LIMPIEZA CUERPO
# ======================================================

def limpiar_texto(texto):
    """
    Limpieza básica de texto extraído de páginas web.
    """

    if not texto:
        return ""

    # Convertir entidades HTML
    texto = html.unescape(str(texto))

    # Eliminar etiquetas HTML
    texto = re.sub(r"<[^>]+>", " ", texto)

    # Eliminar URLs
    texto = re.sub(
        r"https?://\S+|www\.\S+",
        " ",
        texto,
        flags=re.IGNORECASE
    )

    # Eliminar atributos HTML que puedan quedar sueltos
    texto = re.sub(
        r"\b(href|src|style|class|target|rel|id|alt|title)\s*=\s*['\"]?[^'\"\s>]+['\"]?",
        " ",
        texto,
        flags=re.IGNORECASE
    )

    # Eliminar espacios repetidos, saltos de línea y tabs
    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip()

#Algunos autores empizan con el signo ""=". Por tanto, se debe quitar ese signo para que no aparezcan como error en csv/xlsx

# ======================================================
# LIMPIEZA AUTOR
# ======================================================


def limpiar_autor(autor):

    if not autor:
        return ""

    autor = autor.strip()

    while (
        autor.startswith("=")
        or autor.startswith("+")
        or autor.startswith("-")
        or autor.startswith("@")
    ):
        autor = autor[1:].strip()

    return autor



# ======================================================
# EXTRAER CUERPO
# ======================================================

def extraer_cuerpo(url):

    try:

        resp = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        if resp.status_code != 200:
            return ""

        pagina = resp.text

        inicio = pagina.find(
            '"content_elements":['
        )

        if inicio == -1:
            return ""

        fragmento = pagina[
            inicio:inicio + 400000
        ]

        bloques = re.findall(
            r'"content":"(.*?)".*?"type":"text"',
            fragmento,
            re.DOTALL
        )

        textos = []

        for bloque in bloques:

            bloque = limpiar_texto(
                bloque
            )

            if len(bloque) > 20:

                textos.append(
                    bloque
                )

        cuerpo = " ".join(textos)

        cortes = [

            "👀🌎📄",

            "¿Ya se enteró de las últimas noticias",

            "Le puede interesar nuestro plan",

            "The New York Times",

            "Si le interesa recibir un resumen semanal",

            "Si desea contactar al equipo",

            "Invitamos a verlas en El Espectador"

        ]

        for corte in cortes:

            pos = cuerpo.find(corte)

            if pos > 0:

                cuerpo = cuerpo[:pos]

        return cuerpo.strip()

    except Exception as e:

        print(
            f"❌ Error cuerpo: {e}"
        )

        return ""

# ======================================================
# EXTRAER FECHA
# ======================================================

def obtener_fecha(noticia):

    fecha = noticia.get(
        "display_date",
        ""
    )

    if not fecha:

        fecha = noticia.get(
            "publish_date",
            ""
        )

    return fecha

# ======================================================
# EXTRAER AUTOR
# ======================================================

def obtener_autor(noticia):

    autores = noticia.get(
        "credits",
        {}
    ).get(
        "by",
        []
    )

    if not autores:
        return ""

    nombres = []

    for autor in autores:

        nombre = autor.get(
            "name",
            ""
        ).strip()

        if nombre:
            nombres.append(
                nombre
            )

    return ", ".join(
        nombres
    )

# ======================================================
# BUSQUEDA API
# ======================================================

def obtener_articulos():

    resultados = []

    for offset in range(
        0,
        500,
        10
    ):
        time.sleep(1)
        print(
            f"📄 Descargando bloque {offset}"
        )

        query = {

            "author": None,

            "date": None,

            "from": offset,

            "keyword": KEYWORD,

            "section": None,

            "size": 10,

            "subtype": None
        }

        params = {

            "query": json.dumps(
                query,
                ensure_ascii=False
            ),

            "d": "1198",

            "mxId": "00000000",

            "_website": "el-espectador"
        }

        data = None

        for intento in range(3):

            try:

                r = requests.get(
                    API_URL,
                    params=params,
                    headers=HEADERS,
                    timeout=60
                )

                if r.status_code == 200:

                    data = r.json()

                    break

                print(
                    f"⚠️ Offset {offset} | "
                    f"Intento {intento + 1}/3 | "
                    f"Status: {r.status_code}"
                )

                time.sleep(5)

            except Exception as e:

                print(
                    f"⚠️ Offset {offset} | "
                    f"Intento {intento + 1}/3 | "
                    f"Error: {e}"
                )

                time.sleep(5)

        if data is None:

            print(
                f"❌ Se omite offset {offset}"
            )

            continue

        noticias = data.get(
            "content_elements",
            []
        )


        if not noticias:

            break

        for noticia in noticias:

            titulo = noticia.get(
                "headlines",
                {}
            ).get(
                "basic",
                ""
            )

            canonical = noticia.get(
                "canonical_url",
                ""
            )

            url = (
                "https://www.elespectador.com"
                + canonical
            )

            fecha = obtener_fecha(
                noticia
            )

            autor = obtener_autor(
                noticia
            )

            autor = limpiar_autor(
                autor
            )

            resultados.append({

                "Titulo": titulo,

                "URL": url,

                "Fecha": fecha,

                "Autor": autor,

                "Medio": "El Espectador",

                "Pais": "Colombia"
            })

    return resultados

# ======================================================
# MAIN
# ======================================================

def extraer_el_espectador(limite=None):

    articulos = obtener_articulos()

    if limite is not None:
        articulos = articulos[:limite]

    print(
        f"\n✅ Artículos encontrados: "
        f"{len(articulos)}"
    )

    filas = []

    for i, articulo in enumerate(
        articulos,
        start=1
    ):

        print(
            f"\n[{i}/{len(articulos)}]"
        )

        print(
            articulo["Titulo"]
        )

        cuerpo = extraer_cuerpo(
            articulo["URL"]
        )

        print(
            f"Autor: {articulo['Autor']}"
        )

        print(
            f"Fecha: {articulo['Fecha']}"
        )

        print(
            f"Caracteres: {len(cuerpo)}"
        )

        filas.append({

            "Titulo":
            articulo["Titulo"],

            "URL":
            articulo["URL"],

            "Cuerpo":
            cuerpo,

            "Fecha":
            articulo["Fecha"],

            "Autor":
            articulo["Autor"],

            "Medio":
            articulo["Medio"],

            "Pais":
            articulo["Pais"]
        })

    df = pd.DataFrame(
        filas
    )

    df.to_csv(
        "Data/el_espectador_colombia_migracion_venezolana.csv",
        index=False,
        encoding="utf-8-sig"
    )

    return df

