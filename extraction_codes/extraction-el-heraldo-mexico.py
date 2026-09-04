# ============================================================
# EL HERALDO DE MÉXICO
# Búsqueda: migración venezolana
#
# Salida:
# fecha
# autor
# pais
# medio
# titulo
# cuerpo
# url
#
# CSV final: heraldo_mexico_migracion_venezolana.csv
# ============================================================

import re
import html
import time
import requests
import pandas as pd

from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin


BUSQUEDA = "migración venezolana"

BASE_URL = "https://heraldodemexico.com.mx"

SEARCH_URL = (
    "https://heraldodemexico.com.mx/noticias/buscar/"
    f"?buscar={quote_plus(BUSQUEDA)}"
)

AJAX_URL = (
    "https://heraldodemexico.com.mx/"
    "a/aps/noticias/paginas/ajax/ultimoinf-fecha-en-grupos.asp"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    )
}


# ============================================================
# LIMPIEZA
# ============================================================

def limpiar_texto(texto):
    if not texto:
        return ""

    texto = html.unescape(texto)

    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = re.sub(r"(href|src)\s*=\s*['\"].*?['\"]", " ", texto, flags=re.I)

    texto = re.sub(r"\s+", " ", texto)

    return texto.strip()


# ============================================================
# EXTRAER URLS DESDE HTML DE RESULTADOS
# ============================================================

def extraer_urls_resultado(html_text):

    soup = BeautifulSoup(html_text, "html.parser")

    urls = set()

    for a in soup.select("h5.titulo a"):
        href = a.get("href")

        if not href:
            continue

        if href.endswith(".html"):
            urls.add(urljoin(BASE_URL, href))

    for a in soup.select("article a"):
        href = a.get("href")

        if not href:
            continue

        if href.endswith(".html"):
            urls.add(urljoin(BASE_URL, href))

    return list(urls)


# ============================================================
# PAGINA INICIAL
# ============================================================

def obtener_urls_primera_pagina():

    r = requests.get(
        SEARCH_URL,
        headers=HEADERS,
        timeout=60
    )

    r.raise_for_status()

    return extraer_urls_resultado(r.text)


# ============================================================
# PAGINACIÓN AJAX
# ============================================================

def obtener_urls_ajax():

    todas = set()

    page = 1

    while True:

        payload = {
            "busqueda": BUSQUEDA,
            "page": page
        }

        r = requests.post(
            AJAX_URL,
            headers=HEADERS,
            data=payload,
            timeout=60
        )

        r.raise_for_status()

        html_text = r.text

        urls = extraer_urls_resultado(html_text)

        if not urls:
            print(f"Fin de paginación en page={page}")
            break

        nuevas = set(urls) - todas

        if not nuevas:
            print(f"Sin URLs nuevas en page={page}")
            break

        todas.update(nuevas)

        print(
            f"Page {page}: "
            f"{len(nuevas)} nuevas "
            f"({len(todas)} acumuladas)"
        )

        page += 1

        time.sleep(0.5)

    return list(todas)


# ============================================================
# EXTRAER ARTÍCULO
# ============================================================

def extraer_articulo(url):

    try:

        r = requests.get(
            url,
            headers=HEADERS,
            timeout=60
        )

        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")

        # -------------------------
        # TITULO
        # -------------------------

        titulo = ""

        nodo = soup.select_one("h1.titulo-noticia")

        if nodo:
            titulo = limpiar_texto(nodo.get_text(" ", strip=True))

        if not titulo:
            meta = soup.find("meta", {"property": "og:title"})
            if meta:
                titulo = limpiar_texto(meta.get("content", ""))

        # -------------------------
        # AUTOR
        # -------------------------

        autor = ""

        nodo = soup.select_one("span.autor")

        if nodo:
            autor = limpiar_texto(
                nodo.get_text(" ", strip=True)
            )

        if not autor:

            m = re.search(
                r'"creador":"([^"]+)"',
                r.text
            )

            if m:
                autor = limpiar_texto(m.group(1))

        # -------------------------
        # FECHA
        # -------------------------

        fecha = ""

        nodo = soup.select_one(
            "span.fecha-de-publicacion"
        )

        if nodo:
            fecha = limpiar_texto(
                nodo.get_text(" ", strip=True)
            )

        if not fecha:

            m = re.search(
                r'"fecha":"([^"]+)"',
                r.text
            )

            if m:
                fecha = m.group(1)

        # -------------------------
        # CUERPO
        # -------------------------

        cuerpo = ""

        body = soup.select_one(
            "div.texto-noticia"
        )

        if body:

            parrafos = []

            for p in body.find_all("p"):

                txt = limpiar_texto(
                    p.get_text(" ", strip=True)
                )

                if txt:
                    parrafos.append(txt)

            cuerpo = "\n".join(parrafos)

        # -------------------------
        # REGISTRO
        # -------------------------

        return {
            "fecha": fecha,
            "autor": autor,
            "pais": "México",
            "medio": "El Heraldo de México",
            "titulo": titulo,
            "cuerpo": cuerpo,
            "url": url
        }

    except Exception as e:

        print("ERROR:", url)
        print(e)

        return None


# ============================================================
# MAIN
# ============================================================

print("Extrayendo URLs...")

urls = set()

urls.update(obtener_urls_primera_pagina())

urls.update(obtener_urls_ajax())

urls = sorted(urls)

print(f"\nTotal URLs únicas: {len(urls)}")

# ============================================================
# EXTRAER ARTÍCULOS
# ============================================================

registros = []

for i, url in enumerate(urls, start=1):

    print(f"[{i}/{len(urls)}]")

    articulo = extraer_articulo(url)

    if articulo:
        registros.append(articulo)

    time.sleep(0.3)

# ============================================================
# DATAFRAME
# ============================================================

df = pd.DataFrame(registros)

df = df.drop_duplicates(
    subset=["url"]
)

# ============================================================
# CSV
# ============================================================

archivo_salida = (
    "Data/heraldo_mexico_migracion_venezolana.csv"
)

df.to_csv(
    archivo_salida,
    index=False,
    encoding="utf-8-sig"
)

print("\nListo.")
print("Artículos:", len(df))
print("Archivo:", archivo_salida)