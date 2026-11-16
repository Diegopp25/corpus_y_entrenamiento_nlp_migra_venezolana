import pytest

from extraction import extraction_la_cronica_mexico as scraper


def test_extraer_cronica_respects_article_limit(monkeypatch):
    seen_limits = []
    search_results = [
        {"titulo": f"Noticia {index}", "url": f"https://cronica.com.mx/{index}"}
        for index in range(5)
    ]

    def fake_search(limit):
        seen_limits.append(limit)
        return search_results

    monkeypatch.setattr(scraper, "get_search_results", fake_search)
    monkeypatch.setattr(
        scraper,
        "parse_article",
        lambda url, fallback_title: {
            "Titulo": fallback_title,
            "URL": url,
            "Cuerpo": f"Texto de noticia suficientemente completo para analizar {url}.",
            "Fecha": "",
            "Autor": "",
            "Pais": scraper.PAIS,
            "Medio": scraper.MEDIO,
        },
    )
    monkeypatch.setattr(scraper.time, "sleep", lambda _: None)

    articles = scraper.extraer_cronica_mexico(limite=2)

    assert seen_limits == [2]
    assert len(articles) == 2


@pytest.mark.parametrize("limit", [0, -1, 1.5, True])
def test_extraer_cronica_rejects_invalid_limit(limit):
    with pytest.raises(ValueError, match="entero positivo"):
        scraper.extraer_cronica_mexico(limite=limit)
