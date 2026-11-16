# ======================================================
# Librerías
# ======================================================

import re
import time
import json
import pandas as pd
import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin

# ==========================================
# CONFIG
# ==========================================

SEARCH_TERM = "migrantes venezolanos"
START_PAGE = 1
MAX_PAGES = 100

PAIS = "México"
MEDIO = "Milenio"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0 Safari/537.36"
    )
}

session = requests.Session()
session.headers.update(HEADERS)

# ==========================================
# HELPERS
# ==========================================

def clean_text(text):
    if not text:
        return ""

    return re.sub(r"\s+", " ", text).strip()


def get_article_author(soup):

    selectors = [
        '[itemprop="author"]',
        '.author',
        '.article-author',
        '.nd-author',
        '.nota-autor',
        '.content-author',
        '.author-name',
        '[rel="author"]'
    ]

    for selector in selectors:

        node = soup.select_one(selector)

        if node:

            txt = clean_text(
                node.get_text(" ", strip=True)
            )

            if txt:
                return txt

    for tag in soup.select(
        'script[type="application/ld+json"]'
    ):

        try:

            data = json.loads(tag.string)

            if isinstance(data, dict):

                author = data.get("author")

                if isinstance(author, dict):

                    name = author.get("name")

                    if name:
                        return clean_text(name)

                if isinstance(author, list):

                    names = []

                    for x in author:

                        if isinstance(x, dict):

                            name = x.get("name")

                            if name:
                                names.append(name)

                    if names:
                        return "; ".join(names)

        except:
            pass

    return ""


def get_article_body(soup):

    body_selectors = [
        '[itemprop="articleBody"]',
        '.article-body',
        '.nd-content-body',
        '.content-note-body',
        '.nota__contenido',
        '.story-body',
        '.body-content'
    ]

    for selector in body_selectors:

        body = soup.select_one(selector)

        if body:

            paragraphs = body.find_all("p")

            if paragraphs:

                text = " ".join(
                    clean_text(
                        p.get_text(" ", strip=True)
                    )
                    for p in paragraphs
                )

                if len(text) > 100:
                    return text

    paragraphs = soup.find_all("p")

    textos = []

    for p in paragraphs:

        texto = clean_text(
            p.get_text(" ", strip=True)
        )

        if len(texto) > 40:
            textos.append(texto)

    return " ".join(textos)


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

            h1 = soup.find("h1")

            if h1:
                title = clean_text(
                    h1.get_text()
                )

        author = get_article_author(soup)

        body = get_article_body(soup)

        return {
            "Fecha": fallback_date,
            "Autor": author,
            "Pais": PAIS,
            "Medio": MEDIO,
            "Titulo": title,
            "Cuerpo": body,
            "URL": url
        }

    except Exception as e:

        print(
            "ERROR artículo:",
            url,
            e
        )

        return None


def fix_author(author):

    if pd.isna(author):
        return ""

    author = str(author).strip()

    if author.startswith("="):
        author = "'" + author

    return author


# ==========================================
# FUNCIÓN PRINCIPAL
# ==========================================

def extraer_milenio_mexico(limite=None):

    all_records = []
    seen_urls = set()

    for page in range(
        START_PAGE,
        MAX_PAGES + 1
    ):

        search_url = (
            f"https://www.milenio.com/buscador?"
            f"text={SEARCH_TERM.replace(' ', '+')}"
            f"&page={page}"
        )

        print(f"\nPágina {page}")

        try:

            r = session.get(
                search_url,
                timeout=30
            )

            if r.status_code != 200:

                print("No se pudo cargar")

                break

            soup = BeautifulSoup(
                r.text,
                "html.parser"
            )

            articles = soup.select(
                "li.lr-list-row-row-news"
            )

            if not articles:

                print(
                    "Sin más resultados"
                )

                break

            print(
                "Resultados:",
                len(articles)
            )

            for article in articles:

                fecha = ""

                time_tag = article.find(
                    "time"
                )

                if time_tag:

                    fecha = (
                        time_tag.get(
                            "datetime"
                        )
                        or clean_text(
                            time_tag.get_text()
                        )
                    )

                title_node = article.select_one(
                    ".lr-list-row-row-news__title a"
                )

                if not title_node:
                    continue

                titulo = clean_text(
                    title_node.get_text()
                )

                href = title_node.get(
                    "href"
                )

                if not href:
                    continue

                article_url = urljoin(
                    "https://www.milenio.com",
                    href
                )

                if article_url in seen_urls:
                    continue

                seen_urls.add(
                    article_url
                )

                print(
                    "  ->",
                    titulo[:80]
                )

                row = parse_article(
                    article_url,
                    fallback_title=titulo,
                    fallback_date=fecha
                )

                if row:
                    all_records.append(
                        row
                    )

                if (
                    limite is not None
                    and len(all_records) >= limite
                ):
                    break

                time.sleep(1)

            if (
                limite is not None
                and len(all_records) >= limite
            ):
                break

        except Exception as e:

            print(
                "Error página:",
                page,
                e
            )

            continue

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
        ).reset_index(
            drop=True
        )

        df["Autor"] = df[
            "Autor"
        ].apply(
            fix_author
        )


    print("\nListo.")
    print(
        "Artículos:",
        len(df)
    )

    return df