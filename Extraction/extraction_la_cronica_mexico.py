# ======================================================
# LIBRERÍAS
# ======================================================

import re
import time
import json
import pandas as pd
import requests

from bs4 import BeautifulSoup

from playwright.sync_api import (
    sync_playwright
)

# ======================================================
# CONFIG
# ======================================================

SEARCH_TERM = "migración venezolana en México"

PAIS = "México"
MEDIO = "La Crónica de Hoy"

MAX_PAGES = 5000

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0 Safari/537.36"
    )
}

session = requests.Session()
session.headers.update(HEADERS)

# ======================================================
# HELPERS
# ======================================================

def clean_text(text):

    if not text:
        return ""

    return re.sub(
        r"\s+",
        " ",
        text
    ).strip()


def fix_author(author):

    if pd.isna(author):
        return ""

    author = str(author).strip()

    if author.startswith("="):
        author = "'" + author

    return author


# ======================================================
# AUTOR
# ======================================================

def get_article_author(soup):

    # Selector específico de La Crónica
    node = soup.select_one(
        ".b-byline__names"
    )

    if node:

        autor = clean_text(
            node.get_text(
                " ",
                strip=True
            )
        )

        autor = re.sub(
            r"<\s*br\s*/?\s*>",
            "",
            autor,
            flags=re.IGNORECASE
        )

        return clean_text(autor)

    # Fallbacks genéricos
    selectors = [

        ".author-post",
        ".post-author",
        ".author",

        '[itemprop="author"]',

        '[rel="author"]'

    ]

    for selector in selectors:

        node = soup.select_one(
            selector
        )

        if node:

            autor = clean_text(
                node.get_text(
                    " ",
                    strip=True
                )
            )

            autor = re.sub(
                r"<\s*br\s*/?\s*>",
                "",
                autor,
                flags=re.IGNORECASE
            )

            return clean_text(autor)

    return ""

    # Selector específico de La Crónica

    node = soup.select_one(
        ".b-byline__names"
    )

    if node:

        autor = clean_text(
            node.get_text(
                " ",
                strip=True
            )
        )

        return autor

    # Fallbacks genéricos

    selectors = [

        ".author-post",
        ".post-author",
        ".author",

        '[itemprop="author"]',

        '[rel="author"]'

    ]

    for selector in selectors:

        node = soup.select_one(
            selector
        )

        if node:

            autor = re.sub(
            r"<\s*br\s*/?\s*>",
            "",
            autor,
            flags=re.IGNORECASE
        )

        autor = clean_text(autor)

    return ""
    
# ======================================================
# FECHA
# ======================================================

def get_article_date(soup):

    node = soup.select_one(
        "time.c-date.b-date"
    )

    if not node:
        return ""

    fecha = node.get(
        "datetime"
    )

    if fecha:

        return fecha[:10]

    return ""


# ======================================================
# CUERPO
# ======================================================

def get_article_body(soup):

    selectors = [

        ".container-post",

        ".detail-post",

        ".body-post",

        ".content-post",

        '[itemprop="articleBody"]'

    ]

    for selector in selectors:

        body = soup.select_one(
            selector
        )

        if not body:
            continue

        paragraphs = body.find_all(
            "p"
        )

        textos = []

        for p in paragraphs:

            texto = clean_text(
                p.get_text(
                    " ",
                    strip=True
                )
            )

            if len(texto) > 20:

                textos.append(
                    texto
                )

        cuerpo = " ".join(
            textos
        )

        if len(cuerpo) > 200:

            return cuerpo

    textos = []

    for p in soup.find_all("p"):

        texto = clean_text(
            p.get_text(
                " ",
                strip=True
            )
        )

        if len(texto) > 50:

            textos.append(
                texto
            )

    return " ".join(textos)


# ======================================================
# EXTRAER ARTÍCULO
# ======================================================

def parse_article(
    url,
    fallback_title="",
    fallback_date=""
):

    try:

        r = session.get(
            url,
            timeout=30
        )

        if r.status_code != 200:

            return None

        soup = BeautifulSoup(
            r.text,
            "html.parser"
        )

        title = fallback_title

        if not title:

            h1 = soup.find(
                "h1"
            )

            if h1:

                title = clean_text(
                    h1.get_text()
                )

        author = get_article_author(
            soup
        )

        fecha = (
            fallback_date
            if fallback_date
            else get_article_date(
                soup
            )
        )

        body = get_article_body(
            soup
        )

        return {

            "Titulo": title,

            "URL": url,

            "Cuerpo": body,

            "Fecha": fecha,

            "Autor": author,

            "Pais": PAIS,

            "Medio": MEDIO

        }

    except Exception as e:

        print(
            "ERROR artículo:",
            url,
            e
        )

        return None


# ======================================================
# GOOGLE CSE
# ======================================================

def get_search_results():

    resultados = []

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page()

        query = SEARCH_TERM.replace(
            " ",
            "%20"
        )

        url = (
            "https://www.cronica.com.mx/busqueda/"
            f"#gsc.tab=0&gsc.q={query}"
        )

        print(
            "Abriendo buscador..."
        )

        page.goto(
            url,
            wait_until="networkidle",
            timeout=60000
        )

        page.wait_for_selector(
            "a.gs-title",
            timeout=30000
        )

        time.sleep(5)

        seen_urls = set()

        pagina_actual = 1

        while pagina_actual <= MAX_PAGES:

            print(
                f"Página {pagina_actual}"
            )

            links = page.locator(
                "a.gs-title"
            )

            total = links.count()

            print(
                "Resultados:",
                total
            )

            for i in range(total):

                try:

                    item = links.nth(i)

                    titulo = clean_text(
                        item.inner_text()
                    )

                    href = item.get_attribute(
                        "data-ctorig"
                    )

                    if not href:

                        href = item.get_attribute(
                            "href"
                        )

                    if (
                        not href
                        or "cronica.com.mx"
                        not in href
                    ):
                        continue

                    if href in seen_urls:
                        continue

                    seen_urls.add(
                        href
                    )

                    resultados.append(
                        {
                            "titulo": titulo,
                            "url": href
                        }
                    )

                except Exception:

                    continue

            next_button = page.locator(
                ".gsc-cursor-page"
            )

            if next_button.count() <= pagina_actual:

                break

            try:

                next_button.nth(
                    pagina_actual
                ).click()

                page.wait_for_load_state(
                    "networkidle"
                )

                time.sleep(3)

                pagina_actual += 1

            except Exception:

                break

        browser.close()

    return resultados


# ======================================================
# PRINCIPAL
# ======================================================

def extraer_cronica_mexico(
    limite=5
):

    resultados = (
        get_search_results()
    )

    print(
        f"\nURLs encontradas: {len(resultados)}"
    )

    all_records = []

    for idx, item in enumerate(
        resultados,
        start=1
    ):

        print(
            f"[{idx}/{len(resultados)}]",
            item["titulo"][:80]
        )

        row = parse_article(
            item["url"],
            fallback_title=item["titulo"]
        )

        if row:

            all_records.append(
                row
            )

        if (
            limite is not None
            and len(all_records)
            >= limite
        ):
            break

        time.sleep(1)

    df = pd.DataFrame(
        all_records,
        columns=[
            "Titulo",
            "URL",
            "Cuerpo",
            "Fecha",
            "Autor",
            "Pais",
            "Medio"
        ]
    )

    if not df.empty:

        df = df.drop_duplicates(
            subset=["URL"]
        )

        df = df.reset_index(
            drop=True
        )

        df["Autor"] = (
            df["Autor"]
            .apply(fix_author)
        )

    print(
        "\nArtículos extraídos:",
        len(df)
    )

    return df


# ======================================================
# EJECUCIÓN
# ======================================================

if __name__ == "__main__":

    df = extraer_cronica_mexico()

    print(
        df.head()
    )

    df.to_csv(
        "cronica_mexico.csv",
        index=False,
        encoding="utf-8-sig"
    )

    print(
        "\nArchivo guardado: cronica_mexico.csv"
    )