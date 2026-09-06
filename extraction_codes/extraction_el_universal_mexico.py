import re
import json
import html
import requests
import pandas as pd
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0 Safari/537.36"
    )
}


PALABRAS_CLAVE = [
    "venezol",
    "venezuela",
    "migrante",
    "migrantes",
    "migración",
    "migraciones",
    "migratorio",
    "migratorios",
    "refugiado",
    "refugiados",
    "desplazado",
    "desplazados"
]


def limpiar_html_texto(texto):

    if not texto:
        return ""

    texto = html.unescape(texto)

    soup = BeautifulSoup(
        texto,
        "html.parser"
    )

    return soup.get_text(
        " ",
        strip=True
    )


def es_relevante(texto):

    texto = texto.lower()

    return any(
        palabra in texto
        for palabra in PALABRAS_CLAVE
    )


def obtener_urls_el_universal():

    secciones = [
        "/mundo",
        "/nacion",
        "/estados"
    ]

    urls = set()

    for seccion in secciones:

        feed_url = (
            "https://www.eluniversal.com.mx/"
            "pf/api/v3/content/fetch/"
            "story-feed-by-section"
        )

        params = {
            "query": json.dumps({
                "section": seccion,
                "size": 100
            }),
            "_website": "eluniversal"
        }

        try:

            response = requests.get(
                feed_url,
                headers=HEADERS,
                params=params,
                timeout=30
            )

            response.raise_for_status()

            data = response.json()

            for item in data.get(
                "content_elements",
                []
            ):

                canonical_url = item.get(
                    "canonical_url"
                )

                if canonical_url:

                    urls.add(
                        "https://www.eluniversal.com.mx"
                        + canonical_url
                    )

        except Exception as e:

            print(
                f"Error sección "
                f"{seccion}: {e}"
            )

    urls = sorted(urls)

    print(
        f"URLs encontradas: "
        f"{len(urls)}"
    )

    return urls


def extraer_datos_articulo(url):

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        response.raise_for_status()

        html_text = response.text

        patron = re.search(
            r"Fusion\.globalContent=(.*?);Fusion\.globalContentConfig",
            html_text,
            re.DOTALL
        )

        if not patron:

            print(
                f"No se encontró "
                f"Fusion.globalContent: {url}"
            )

            return None

        json_text = patron.group(1)

        data = json.loads(
            json_text
        )

        titulo = (
            data.get(
                "headlines",
                {}
            ).get(
                "basic",
                ""
            )
        )

        subtitulo = (
            data.get(
                "subheadlines",
                {}
            ).get(
                "basic",
                ""
            )
        )

        fecha = data.get(
            "publish_date",
            ""
        )

        autor = ""

        autores = (
            data.get(
                "credits",
                {}
            ).get(
                "by",
                []
            )
        )

        if autores:

            autor = autores[0].get(
                "name",
                ""
            )

        seccion = (
            data.get(
                "taxonomy",
                {}
            )
            .get(
                "primary_section",
                {}
            )
            .get(
                "name",
                ""
            )
        )

        keywords = (
            data.get(
                "taxonomy",
                {}
            ).get(
                "seo_keywords",
                []
            )
        )

        tags = (
            data.get(
                "taxonomy",
                {}
            ).get(
                "tags",
                []
            )
        )

        keywords_texto = ", ".join(
            keywords
        )

        tags_texto = ", ".join(
            tag.get(
                "text",
                ""
            )
            for tag in tags
        )

        contenido = []

        for elemento in data.get(
            "content_elements",
            []
        ):

            if (
                elemento.get(
                    "type"
                )
                == "text"
            ):

                texto = limpiar_html_texto(
                    elemento.get(
                        "content",
                        ""
                    )
                )

                if texto:

                    contenido.append(
                        texto
                    )

        cuerpo = "\n\n".join(
            contenido
        )

        return {
            "titulo": titulo,
            "subtitulo": subtitulo,
            "autor": autor,
            "fecha": fecha,
            "seccion": seccion,
            "keywords": keywords_texto,
            "tags": tags_texto,
            "texto": cuerpo,
            "url": url
        }

    except Exception as e:

        print(
            f"Error en {url}: {e}"
        )

        return None


def extraer_el_universal(limite=None):

    urls = obtener_urls_el_universal()

    noticias = []

    for i, url in enumerate(
        urls,
        start=1
    ):

        print(
            f"[{i}/{len(urls)}] {url}"
        )

        resultado = extraer_datos_articulo(
            url
        )

        if not resultado:
            continue

        texto_validacion = " ".join([
            resultado["titulo"],
            resultado["subtitulo"],
            resultado["texto"],
            resultado["keywords"],
            resultado["tags"]
        ])

        if es_relevante(
            texto_validacion
        ):

            print(
                "✓ Noticia relevante"
            )

            noticias.append(
                resultado
            )

            if (
                limite
                and len(noticias)
                >= limite
            ):
                break

    df = pd.DataFrame(
        noticias
    )

    if not df.empty:

        df.drop_duplicates(
            subset=["url"],
            inplace=True
        )

    return df


if __name__ == "__main__":

    df = extraer_el_universal(
        limite=5
    )

    print(
        "\nRESULTADOS:"
    )

    print(
        df[[
            "titulo",
            "fecha",
            "url"
        ]]
    )

    print(
        f"\nNoticias obtenidas: "
        f"{len(df)}"
    )

extraer_el_universal(limite=5)