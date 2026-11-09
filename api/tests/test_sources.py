"""Pruebas de la ingesta de noticias sin acceso real a la red.

Se usa un ``FakeFetcher`` (inyectado como ``app.state.fetcher`` o pasado al
``NewsScraper``) y ``httpx.MockTransport`` para la capa HTTP, de modo que
robots.txt, RSS, sitemaps, artículos, SSRF, jobs y endpoints se prueban de
forma determinista y offline.
"""

from __future__ import annotations

import socket
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.engine.text import count_words
from app.main import create_app
from app.services.fetching import FetchError, FetchResponse, Fetcher
from app.services.scraper import (
    MIN_BODY_WORDS,
    ExtractionError,
    NewsScraper,
    RobotsDeniedError,
    ScraperError,
    parse_feed,
)
from app.services.site_catalog import KNOWN_SITES
from tests.conftest import FakeEngine, build_settings

FIXTURES = Path(__file__).resolve().parent / "fixtures"

SITE = "https://eltiempo.com"
ARTICLE_URL = f"{SITE}/2026/11/08/venezolanos-en-la-frontera-afrontan-nuevos-controles"
ARTICLE_URL_2 = f"{SITE}/2026/11/07/migracion-venezolana-cifras-del-exodo"
SHORT_URL = f"{SITE}/2026/11/06/nota-corta"
MEXICO_SITE = "https://milenio.com"
MEXICO_URL = f"{MEXICO_SITE}/2026/11/07/venezolanos-empleo-norte-mexico"
SITEMAP_ARTICLE = f"{SITE}/2026/11/08/venezolanos-llegan-a-bogota-tras-cruce"


NO_DATE_URL = f"{SITE}/2026/11/05/noticia-sin-fecha-en-la-pagina"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeFetcher:
    """Descargador falso: sirve páginas por URL y simula errores."""

    def __init__(
        self,
        pages: dict[str, str] | None = None,
        errors: dict[str, FetchError] | None = None,
        content_types: dict[str, str] | None = None,
    ) -> None:
        self.pages = pages or {}
        self.errors = errors or {}
        self.content_types = content_types or {}
        self.requested: list[str] = []
        self.closed = False

    def get(self, url: str, *, headers=None, accept=None) -> FetchResponse:  # noqa: ANN001
        self.requested.append(url)
        if url in self.errors:
            raise self.errors[url]
        page = self.pages.get(url)
        if page is None:
            raise FetchError(
                "not_found",
                f"404 simulado para {url}",
                url=url,
                status_code=404,
            )
        return FetchResponse(
            url=url,
            status_code=200,
            content=page.encode("utf-8"),
            headers={
                "content-type": self.content_types.get(
                    url, "text/html; charset=utf-8"
                )
            },
        )

    def close(self) -> None:
        self.closed = True


def site_pages(*, robots: str = "robots_allow.txt", home: str = "home.html") -> dict[str, str]:
    """Páginas de un sitio colombiano con feed y dos noticias."""
    return {
        f"{SITE}/robots.txt": fixture_text(robots),
        SITE: fixture_text(home),
        f"{SITE}/feed.xml": fixture_text("feed.xml"),
        ARTICLE_URL: fixture_text("article_colombia.html"),
        ARTICLE_URL_2: fixture_text("article_colombia_2.html"),
    }


def build_sources_app(tmp_path: Path, fetcher: FakeFetcher, **overrides):
    overrides.setdefault("scraper_enabled", True)
    settings = build_settings(tmp_path, **overrides)
    app = create_app(settings=settings, engine=FakeEngine())
    app.state.fetcher = fetcher
    return app


def close_app_resources(app) -> None:  # noqa: ANN001
    manager = getattr(app.state, "jobs", None)
    if manager is not None:
        manager.shutdown()


# ---------------------------------------------------------------------------
# Capa HTTP: SSRF, límites y redirecciones
# ---------------------------------------------------------------------------
def test_fetch_blocks_private_and_metadata_urls(settings):
    blocked = (
        "http://127.0.0.1/admin",
        "http://localhost:8080/noticia",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/internal",
        "http://[::1]/loopback",
    )
    with Fetcher(settings) as fetcher:
        for url in blocked:
            with pytest.raises(FetchError) as excinfo:
                fetcher.get(url)
            assert excinfo.value.code == "blocked_url", url
            assert "SSRF" in excinfo.value.message or "privada" in excinfo.value.message


def test_fetch_rejects_non_http_schemes(settings):
    with Fetcher(settings) as fetcher:
        with pytest.raises(FetchError) as excinfo:
            fetcher.get("file:///etc/passwd")
    assert excinfo.value.code == "invalid_scheme"
    assert "http" in excinfo.value.message


def test_fetch_allows_private_networks_when_configured(tmp_path: Path):
    settings = build_settings(tmp_path, scraper_allow_private_networks=True)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, text="<html>ok</html>", headers={"content-type": "text/html"}
        )

    with Fetcher(settings, transport=httpx.MockTransport(handler)) as fetcher:
        response = fetcher.get("http://127.0.0.1:8080/portada")
    assert response.status_code == 200
    assert "ok" in response.text


def test_fetch_limits_response_size(tmp_path: Path):
    settings = build_settings(
        tmp_path, scraper_allow_private_networks=True, scraper_max_response_bytes=256
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"x" * 4096, headers={"content-type": "text/html"}
        )

    with Fetcher(settings, transport=httpx.MockTransport(handler)) as fetcher:
        with pytest.raises(FetchError) as excinfo:
            fetcher.get("http://127.0.0.1/big")
    assert excinfo.value.code == "response_too_large"


def _patch_public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    real_getaddrinfo = socket.getaddrinfo

    def fake_getaddrinfo(host, port, *args, **kwargs):  # noqa: ANN001
        if host == "noticias.test":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]
        return real_getaddrinfo(host, port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


def test_fetch_revalidates_redirect_destinations(settings, monkeypatch):
    _patch_public_dns(monkeypatch)
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1:8080/admin"})

    with Fetcher(settings, transport=httpx.MockTransport(handler)) as fetcher:
        with pytest.raises(FetchError) as excinfo:
            fetcher.get("https://noticias.test/portada")
    assert excinfo.value.code == "blocked_url"
    assert seen == ["https://noticias.test/portada"]


def test_fetch_follows_allowed_redirects(settings, monkeypatch):
    _patch_public_dns(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/portada":
            return httpx.Response(
                302, headers={"location": "https://noticias.test/nota"}
            )
        return httpx.Response(
            200, text="<html>nota</html>", headers={"content-type": "text/html"}
        )

    with Fetcher(settings, transport=httpx.MockTransport(handler)) as fetcher:
        response = fetcher.get("https://noticias.test/portada")
    assert response.status_code == 200
    assert response.url == "https://noticias.test/nota"
    assert "nota" in response.text


def test_fetch_maps_connection_errors(tmp_path: Path):
    settings = build_settings(tmp_path, scraper_allow_private_networks=True)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("fallo de conexión", request=request)

    with Fetcher(settings, transport=httpx.MockTransport(handler)) as fetcher:
        with pytest.raises(FetchError) as excinfo:
            fetcher.get("http://127.0.0.1/sin-servidor")
    assert excinfo.value.code == "connection_error"


# ---------------------------------------------------------------------------
# Robots.txt
# ---------------------------------------------------------------------------
def test_robots_allows_discovery(settings):
    scraper = NewsScraper(settings, fetcher=FakeFetcher(site_pages()))
    discovery = scraper.discover(SITE, max_articles=2)
    assert discovery.source == "rss"
    assert discovery.site_name == "El Tiempo"
    assert discovery.domain == "eltiempo.com"
    assert discovery.country == "Colombia"
    urls = [entry.url for entry in discovery.entries]
    assert ARTICLE_URL in urls
    assert ARTICLE_URL_2 in urls
    assert len(discovery.entries) == 2


def test_robots_denied_raises_clear_error(settings):
    scraper = NewsScraper(
        settings, fetcher=FakeFetcher(site_pages(robots="robots_deny.txt"))
    )
    with pytest.raises(RobotsDeniedError) as excinfo:
        scraper.discover(SITE)
    assert excinfo.value.code == "robots_denied"
    message = str(excinfo.value)
    assert "robots.txt" in message
    assert "eltiempo.com" in message


def test_robots_can_be_ignored_per_request(settings):
    scraper = NewsScraper(
        settings, fetcher=FakeFetcher(site_pages(robots="robots_deny.txt"))
    )
    discovery = scraper.discover(SITE, max_articles=1, respect_robots=False)
    assert len(discovery.entries) == 1


# ---------------------------------------------------------------------------
# Descubrimiento y extracción
# ---------------------------------------------------------------------------
def test_discovery_from_homepage_links(settings):
    pages = {
        f"{SITE}/robots.txt": fixture_text("robots_allow.txt"),
        SITE: fixture_text("home_links.html"),
        ARTICLE_URL: fixture_text("article_colombia.html"),
        ARTICLE_URL_2: fixture_text("article_colombia_2.html"),
    }
    scraper = NewsScraper(settings, fetcher=FakeFetcher(pages))
    discovery = scraper.discover(SITE, max_articles=2)
    assert discovery.source == "links"
    assert [entry.url for entry in discovery.entries] == [ARTICLE_URL, ARTICLE_URL_2]


def test_discovery_from_sitemap(settings):
    pages = {
        f"{SITE}/robots.txt": fixture_text("robots_allow.txt"),
        SITE: fixture_text("home_links.html"),
        f"{SITE}/sitemap.xml": fixture_text("sitemap.xml"),
    }
    scraper = NewsScraper(settings, fetcher=FakeFetcher(pages))
    discovery = scraper.discover(SITE, max_articles=2)
    assert discovery.source == "sitemap"
    urls = [entry.url for entry in discovery.entries]
    assert SITEMAP_ARTICLE in urls
    assert discovery.entries[0].published is not None


def test_article_url_is_analyzed_directly(settings):
    pages = {
        f"{SITE}/robots.txt": fixture_text("robots_allow.txt"),
        ARTICLE_URL: fixture_text("article_colombia.html"),
    }
    scraper = NewsScraper(settings, fetcher=FakeFetcher(pages))
    discovery = scraper.discover(ARTICLE_URL, max_articles=3)
    assert discovery.source == "article"
    assert [entry.url for entry in discovery.entries] == [ARTICLE_URL]


def test_article_extraction(settings):
    pages = {
        f"{SITE}/robots.txt": fixture_text("robots_allow.txt"),
        ARTICLE_URL: fixture_text("article_colombia.html"),
    }
    scraper = NewsScraper(settings, fetcher=FakeFetcher(pages))
    article = scraper.extract(ARTICLE_URL)
    assert article.title == "Venezolanos en la frontera afrontan nuevos controles"
    assert article.author == "María Fernanda Rojas"
    assert article.date == "2026-11-08"
    assert article.media == "El Tiempo"
    assert article.country == "Colombia"
    assert article.category == "Migración"
    assert article.canonical_url == ARTICLE_URL
    assert count_words(article.text) >= MIN_BODY_WORDS
    assert "inseguridad" in article.text.lower()
    assert article.snippet


def test_article_date_falls_back_to_feed_hint(settings):
    pages = {
        f"{SITE}/robots.txt": fixture_text("robots_allow.txt"),
        NO_DATE_URL: fixture_text("article_sin_fecha.html"),
    }
    scraper = NewsScraper(settings, fetcher=FakeFetcher(pages))
    with_hint = scraper.extract(NO_DATE_URL, date_hint="2026-11-05")
    assert with_hint.date == "2026-11-05"
    without_hint = scraper.extract(NO_DATE_URL)
    assert without_hint.date == ""


def test_mexico_article_infers_country(settings):
    pages = {
        f"{MEXICO_SITE}/robots.txt": fixture_text("robots_allow.txt"),
        MEXICO_URL: fixture_text("article_mexico.html"),
    }
    scraper = NewsScraper(settings, fetcher=FakeFetcher(pages))
    article = scraper.extract(MEXICO_URL)
    assert article.country == "México"
    assert article.media == "Milenio"


def test_short_article_is_discarded(settings):
    pages = {
        f"{SITE}/robots.txt": fixture_text("robots_allow.txt"),
        SHORT_URL: fixture_text("article_short.html"),
    }
    scraper = NewsScraper(settings, fetcher=FakeFetcher(pages))
    with pytest.raises(ExtractionError) as excinfo:
        scraper.extract(SHORT_URL)
    assert str(MIN_BODY_WORDS) in str(excinfo.value)


def test_non_html_response_is_rejected(settings):
    binary_url = f"{SITE}/2026/11/08/documento.pdf"
    pages = {
        f"{SITE}/robots.txt": fixture_text("robots_allow.txt"),
        binary_url: "%PDF-1.4 documento binario",
    }
    scraper = NewsScraper(
        settings,
        fetcher=FakeFetcher(pages, content_types={binary_url: "application/pdf"}),
    )
    with pytest.raises(ScraperError) as excinfo:
        scraper.extract(binary_url)
    assert excinfo.value.code == "invalid_content"


def test_parse_atom_feed():
    atom = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        "<entry>"
        "<title>Venezolanos en tránsito por la frontera</title>"
        '<link rel="alternate" href="https://ejemplo.com/2026/11/08/nota-1"/>'
        "<updated>2026-11-08T10:00:00Z</updated>"
        "</entry>"
        "</feed>"
    )
    entries = parse_feed(atom, base_url="https://ejemplo.com/feed.xml")
    assert len(entries) == 1
    assert entries[0].url == "https://ejemplo.com/2026/11/08/nota-1"
    assert entries[0].title == "Venezolanos en tránsito por la frontera"
    assert entries[0].published is not None


# ---------------------------------------------------------------------------
# Endpoints: presets, jobs y analyze-url
# ---------------------------------------------------------------------------
def test_presets(client):
    response = client.get("/v1/sources/presets")
    assert response.status_code == 200
    presets = response.json()
    assert len(presets) == len(KNOWN_SITES)
    assert {
        "id",
        "name",
        "domain",
        "country",
        "category",
        "description",
        "flag",
        "logoText",
        "accentColor",
    } <= set(presets[0])
    assert {preset["country"] for preset in presets} <= {"Colombia", "México"}
    assert {"el-tiempo", "milenio", "reforma"} <= {preset["id"] for preset in presets}
    assert presets[0]["flag"] in {"🇨🇴", "🇲🇽"}


def test_scan_disabled_returns_503(client):
    response = client.post("/v1/sources/scan", json={"url": SITE})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "scraper_disabled"
    response = client.post("/v1/sources/analyze-url", json={"url": ARTICLE_URL})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "scraper_disabled"


def test_unknown_job_returns_404(client):
    response = client.get("/v1/sources/jobs/job-inexistente")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_scan_job_completes_with_summary(tmp_path: Path):
    app = build_sources_app(tmp_path, FakeFetcher(site_pages()))
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/sources/scan", json={"url": SITE, "maxArticles": 2}
            )
            assert response.status_code == 202
            accepted = response.json()
            assert accepted["status"] == "queued"
            assert accepted["statusUrl"] == f"/v1/sources/jobs/{accepted['jobId']}"
            assert accepted["pollAfterSeconds"] == 1.5

            assert app.state.jobs.wait(accepted["jobId"], timeout=20)
            job_response = client.get(accepted["statusUrl"])
            assert job_response.status_code == 200
            job = job_response.json()
    finally:
        close_app_resources(app)

    assert job["status"] == "completed", job
    assert job["currentStep"] == 5
    assert job["totalSteps"] == 5
    assert job["articlesFoundCount"] == 2
    assert job["articlesAnalyzedCount"] == 2
    assert job["error"] is None
    assert [step["step"] for step in job["steps"]] == [1, 2, 3, 4, 5]
    assert job["steps"][0]["totalSteps"] == 5

    summary = job["summary"]
    assert summary["siteName"] == "El Tiempo"
    assert summary["domain"] == "eltiempo.com"
    assert summary["country"] == "Colombia"
    assert summary["totalAnalyzed"] == 2
    assert set(summary["averageSentiment"]) == {"negativo", "neutro", "positivo"}
    assert summary["averageSentiment"]["negativo"] > 50
    frames = summary["topFrames"]
    assert frames and frames[0]["frame"] == "Seguridad"
    percentages = [frame["percentage"] for frame in frames]
    assert percentages == sorted(percentages, reverse=True)
    assert summary["biasTendency"] == "Enfoque Punitivo / Seguridad y Alerta Ciudadana"
    assert summary["hypothesisMatch"] == "Confirmada (Sesgo esperado)"
    assert summary["generatedAt"]

    articles = summary["articles"]
    assert len(articles) == 2
    assert {article["url"] for article in articles} == {ARTICLE_URL, ARTICLE_URL_2}
    for article in articles:
        assert article["country"] == "Colombia"
        assert article["preAnalyzedResult"]["meta"]["source"] == "scraper"
        assert article["preAnalyzedResult"]["country"] == "Colombia"
        assert article["preAnalyzedResult"]["sentiment"]["prediction"] == "Negativo"
        assert count_words(article["fullText"]) >= MIN_BODY_WORDS


def test_jobs_listing_is_summarized(tmp_path: Path):
    app = build_sources_app(tmp_path, FakeFetcher(site_pages()))
    try:
        with TestClient(app) as client:
            accepted = client.post(
                "/v1/sources/scan", json={"url": SITE, "maxArticles": 1}
            ).json()
            assert app.state.jobs.wait(accepted["jobId"], timeout=20)
            response = client.get("/v1/sources/jobs", params={"limit": 5})
    finally:
        close_app_resources(app)
    assert response.status_code == 200
    rows = response.json()
    assert isinstance(rows, list) and rows
    assert set(rows[0]) == {
        "id",
        "url",
        "domain",
        "status",
        "currentStep",
        "totalSteps",
        "message",
        "articlesFound",
        "articlesAnalyzed",
        "error",
        "createdAt",
        "updatedAt",
    }
    assert rows[0]["id"] == accepted["jobId"]
    assert rows[0]["domain"] == "eltiempo.com"
    assert rows[0]["status"] == "completed"


def test_scan_article_url_infers_mexico_bias(tmp_path: Path):
    pages = {
        f"{MEXICO_SITE}/robots.txt": fixture_text("robots_allow.txt"),
        MEXICO_URL: fixture_text("article_mexico.html"),
    }
    app = build_sources_app(tmp_path, FakeFetcher(pages))
    try:
        with TestClient(app) as client:
            accepted = client.post(
                "/v1/sources/scan", json={"url": MEXICO_URL, "maxArticles": 1}
            ).json()
            assert app.state.jobs.wait(accepted["jobId"], timeout=20)
            job = client.get(accepted["statusUrl"]).json()
    finally:
        close_app_resources(app)
    assert job["status"] == "completed", job
    summary = job["summary"]
    assert summary["country"] == "México"
    assert summary["totalAnalyzed"] == 1
    assert summary["averageSentiment"]["positivo"] > 50
    assert summary["biasTendency"] == (
        "Enfoque de Integración Laboral y Tránsito Migratorio"
    )
    assert summary["hypothesisMatch"] == "Confirmada (Sesgo esperado)"


def test_scan_clamps_max_articles(tmp_path: Path):
    app = build_sources_app(
        tmp_path, FakeFetcher(site_pages()), scraper_max_articles=3
    )
    try:
        with TestClient(app) as client:
            accepted = client.post(
                "/v1/sources/scan", json={"url": SITE, "maxArticles": 10}
            ).json()
            assert app.state.jobs.wait(accepted["jobId"], timeout=20)
            stored = app.state.store.get_job(accepted["jobId"])
    finally:
        close_app_resources(app)
    assert stored["request"]["maxArticles"] == 3


def test_scan_job_reports_error(tmp_path: Path):
    fetcher = FakeFetcher(
        errors={SITE: FetchError("connection_error", "fallo simulado de conexión", url=SITE)}
    )
    app = build_sources_app(tmp_path, fetcher)
    try:
        with TestClient(app) as client:
            accepted = client.post("/v1/sources/scan", json={"url": SITE}).json()
            assert app.state.jobs.wait(accepted["jobId"], timeout=20)
            job = client.get(accepted["statusUrl"]).json()
    finally:
        close_app_resources(app)
    assert job["status"] == "error"
    assert "fallo simulado" in job["error"]
    assert job["summary"] is None


def test_analyze_url_returns_article_with_analysis(tmp_path: Path):
    app = build_sources_app(tmp_path, FakeFetcher(site_pages()))
    try:
        with TestClient(app) as client:
            response = client.post("/v1/sources/analyze-url", json={"url": ARTICLE_URL})
    finally:
        close_app_resources(app)
    assert response.status_code == 200, response.text
    article = response.json()
    assert article["title"] == "Venezolanos en la frontera afrontan nuevos controles"
    assert article["url"] == ARTICLE_URL
    assert article["country"] == "Colombia"
    assert article["media"] == "El Tiempo"
    assert article["date"] == "2026-11-08"
    assert article["author"] == "María Fernanda Rojas"
    assert count_words(article["fullText"]) >= MIN_BODY_WORDS
    result = article["preAnalyzedResult"]
    assert set(result) == {
        "id",
        "text",
        "title",
        "sourceUrl",
        "mediaName",
        "country",
        "dateAnalyzed",
        "sentiment",
        "frames",
        "culturalBias",
        "tokensCount",
        "readingTimeSeconds",
        "modelUsed",
        "meta",
    }
    assert result["meta"]["source"] == "scraper"
    assert result["sourceUrl"] == ARTICLE_URL
    assert result["country"] == "Colombia"
    assert result["sentiment"]["prediction"] == "Negativo"


def test_analyze_url_normalizes_country_alias(tmp_path: Path):
    pages = {
        f"{MEXICO_SITE}/robots.txt": fixture_text("robots_allow.txt"),
        MEXICO_URL: fixture_text("article_mexico.html"),
    }
    app = build_sources_app(tmp_path, FakeFetcher(pages))
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/sources/analyze-url",
                json={"url": MEXICO_URL, "country": "Mexico"},
            )
    finally:
        close_app_resources(app)
    assert response.status_code == 200, response.text
    article = response.json()
    assert article["country"] == "México"
    assert article["preAnalyzedResult"]["country"] == "México"
    assert article["preAnalyzedResult"]["sentiment"]["prediction"] == "Positivo"


def test_analyze_url_respects_robots_and_can_be_forced(tmp_path: Path):
    app = build_sources_app(
        tmp_path, FakeFetcher(site_pages(robots="robots_deny.txt"))
    )
    try:
        with TestClient(app) as client:
            denied = client.post("/v1/sources/analyze-url", json={"url": ARTICLE_URL})
            forced = client.post(
                "/v1/sources/analyze-url",
                json={"url": ARTICLE_URL, "respectRobots": False},
            )
    finally:
        close_app_resources(app)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "robots_denied"
    assert "robots.txt" in denied.json()["error"]["message"]
    assert forced.status_code == 200, forced.text


def test_analyze_url_blocks_private_networks(tmp_path: Path):
    settings = build_settings(tmp_path, scraper_enabled=True)
    app = create_app(settings=settings, engine=FakeEngine())
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/sources/analyze-url",
                json={"url": "http://127.0.0.1:8080/noticia"},
            )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "url_blocked"
    finally:
        fetcher = getattr(app.state, "fetcher", None)
        if fetcher is not None:
            fetcher.close()
