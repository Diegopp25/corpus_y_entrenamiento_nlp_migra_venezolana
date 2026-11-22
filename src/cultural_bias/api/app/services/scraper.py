"""Descubrimiento y extracción de noticias para la ingesta automática.

El flujo implementado es:

1. **robots.txt**: se consulta con ``urllib.robotparser`` y se cachea por
   dominio. Si el acceso está prohibido se lanza :class:`RobotsDeniedError`
   con un mensaje claro (nunca una excepción genérica).
2. **Descubrimiento**: si la URL parece un artículo se analiza directamente;
   si no, se buscan feeds RSS/Atom (``<link rel="alternate">`` y rutas
   habituales), sitemaps de noticias y, como último recurso, enlaces ``<a>``
   de la portada. Los candidatos se filtran por palabras clave de migración,
   se deduplican y se recortan a ``max_articles``.
3. **Extracción**: trafilatura si está instalado, si no BeautifulSoup y si no
   el ``html.parser`` de la biblioteca estándar. Se descartan cuerpos con
   menos de 80 palabras.
4. **Resumen agregado**: sentimiento promedio, encuadres dominantes,
   tendencia de sesgo y contraste con la hipótesis del proyecto.

Ninguna función de este módulo usa la red directamente: todo pasa por el
descargador inyectable (:class:`~app.services.fetching.SupportsGet`).
"""

from __future__ import annotations

import json
import logging
import re
import threading
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Iterable, Sequence
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

try:  # pragma: no cover - depende del entorno
    from bs4 import BeautifulSoup
    _HAS_BS4 = True
except ImportError:  # pragma: no cover
    BeautifulSoup = None  # type: ignore[assignment,misc]
    _HAS_BS4 = False

try:  # pragma: no cover - depende del entorno
    import trafilatura
    _HAS_TRAFILATURA = True
except ImportError:  # pragma: no cover
    trafilatura = None  # type: ignore[assignment]
    _HAS_TRAFILATURA = False

from ..config import Settings
from ..engine.text import clean_text, count_words, normalize_for_match
from ..schemas import (
    FrameTally,
    NewsArticle,
    ScrapedSiteSummary,
    SentimentScores,
    TextAnalysisResult,
)
from .analysis import AnalysisService
from .fetching import (
    HTML_ACCEPT,
    XML_ACCEPT,
    FetchError,
    FetchResponse,
    SupportsGet,
)
from .site_catalog import (
    domain_from_url,
    infer_country,
    infer_media_name,
    known_site_for,
)

logger = logging.getLogger(__name__)

#: Mínimo de palabras para aceptar el cuerpo de una noticia.
MIN_BODY_WORDS = 80
_MAX_SNIPPET_CHARS = 280
_MAX_TITLE_CHARS = 300

_FEED_PATHS = (
    "/feed",
    "/feed.xml",
    "/rss",
    "/rss.xml",
    "/atom.xml",
    "/arc/outboundfeeds/rss/",
)
_SITEMAP_PATHS = (
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/news-sitemap.xml",
    "/sitemap-news.xml",
    "/sitemap_news.xml",
)
_NON_ARTICLE_SEGMENTS = {
    "tag",
    "tags",
    "autor",
    "author",
    "autores",
    "categoria",
    "category",
    "categorias",
    "seccion",
    "section",
    "tema",
    "temas",
    "buscar",
    "search",
    "login",
    "suscripcion",
    "newsletter",
    "rss",
    "feed",
    "sitemap",
    "privacidad",
    "terminos",
    "contacto",
}
_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "output",
    "ref",
}
_ARTICLE_DATE_PATH_RE = re.compile(
    r"/(?:19|20)\d{2}/(?:0?[1-9]|1[0-2])(?:/(?:0?[1-9]|[12]\d|3[01]))?/"
)
_SLUG_RE = re.compile(r"[a-záéíóúñ0-9]+(?:-[a-záéíóúñ0-9]+){2,}", re.IGNORECASE)

_ARTICLE_JSON_LD_TYPES = {
    "article",
    "newsarticle",
    "reportagenewsarticle",
    "analysisnewsarticle",
    "opinionnewsarticle",
    "blogposting",
}

#: Encuadres esperados por país según la hipótesis del proyecto.
_EXPECTED_FRAMES = {
    "Colombia": {"seguridad", "politica_migratoria"},
    "México": {"empleo_economia", "transito_migratorio"},
}
_EXPECTED_BIAS_TEXT = {
    "Colombia": "Enfoque Punitivo / Seguridad y Alerta Ciudadana",
    "México": "Enfoque de Integración Laboral y Tránsito Migratorio",
}
_FRAME_BIAS_TEXT = {
    "seguridad": "Enfoque Punitivo / Seguridad y Alerta Ciudadana",
    "politica_migratoria": "Enfoque Institucional / Política Migratoria",
    "empleo_economia": "Enfoque de Integración Laboral y Tránsito Migratorio",
    "transito_migratorio": "Enfoque de Integración Laboral y Tránsito Migratorio",
    "integracion_social": "Enfoque de Integración Social y Convivencia",
    "acceso_servicios": "Enfoque de Acceso a Servicios y Derechos",
    "otros": "Enfoque de Derechos Humanos y Cooperación",
}


# ---------------------------------------------------------------------------
# Errores tipados
# ---------------------------------------------------------------------------
class ScraperError(Exception):
    """Error de descubrimiento o extracción con código estable."""

    def __init__(
        self, message: str, *, code: str = "scraper_error", url: str = ""
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.url = url

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


class RobotsDeniedError(ScraperError):
    """``robots.txt`` prohíbe acceder a la URL solicitada."""

    def __init__(self, message: str, *, url: str = "") -> None:
        super().__init__(message, code="robots_denied", url=url)


class ExtractionError(ScraperError):
    """La página no contiene un cuerpo de noticia aprovechable."""

    def __init__(self, message: str, *, url: str = "") -> None:
        super().__init__(message, code="extraction_failed", url=url)


# ---------------------------------------------------------------------------
# Modelos internos
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class FeedEntry:
    """Noticia candidata descubierta antes de descargar su contenido."""

    url: str
    title: str = ""
    published: datetime | None = None


@dataclass(slots=True)
class DiscoveryResult:
    """Resultado del descubrimiento de un sitio."""

    source: str
    homepage_url: str
    site_name: str = ""
    domain: str = ""
    country: str = "Desconocido"
    entries: list[FeedEntry] = field(default_factory=list)


@dataclass(slots=True)
class ExtractedArticle:
    """Noticia ya extraída (texto y metadatos)."""

    url: str
    canonical_url: str
    title: str
    text: str
    author: str = ""
    date: str = ""
    media: str = ""
    country: str = "Desconocido"
    category: str = ""
    snippet: str = ""


@dataclass(slots=True)
class PageInfo:
    """Metadatos básicos de una página HTML."""

    title: str = ""
    site_name: str = ""
    description: str = ""
    author: str = ""
    date: str = ""
    canonical: str = ""
    category: str = ""


# ---------------------------------------------------------------------------
# Utilidades de URLs y fechas
# ---------------------------------------------------------------------------
def canonical_url(url: str) -> str:
    """Normaliza una URL para deduplicar candidatos (sin fragmentos ni tracking)."""
    candidate = (url or "").strip()
    if not candidate:
        return ""
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return candidate
    if not parsed.scheme:
        return candidate
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_PARAMS and not key.lower().startswith("utm_")
    ]
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse(
        (parsed.scheme.lower(), (parsed.netloc or "").lower(), path, "", urlencode(query), "")
    )


def _parse_datetime(value: str | None) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_date(value: object) -> str:
    """Devuelve la fecha en formato ``YYYY-MM-DD`` (o ``""`` si no se pudo)."""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if not value:
        return ""
    parsed = _parse_datetime(str(value))
    if parsed is not None:
        return parsed.strftime("%Y-%m-%d")
    raw = str(value).strip()
    match = re.search(r"(19|20)\d{2}-\d{2}-\d{2}", raw)
    return match.group(0) if match else ""


def _title_from_url(url: str) -> str:
    path = urlparse(url).path
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return ""
    slug = segments[-1]
    slug = re.sub(r"\.(html?|shtml|amp)$", "", slug, flags=re.IGNORECASE)
    words = re.sub(r"[-_]+", " ", slug).strip()
    return words[:1].upper() + words[1:] if words else ""


def looks_like_article_url(url: str) -> bool:
    """Heurística: ¿la ruta parece la de una noticia y no la de un índice?"""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    path = parsed.path or ""
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False
    if segments[0].lower() in _NON_ARTICLE_SEGMENTS:
        return False
    if _ARTICLE_DATE_PATH_RE.search(path):
        return True
    last = segments[-1]
    if last.lower().endswith((".html", ".htm", ".shtml", ".amp")) and len(last) >= 15:
        return True
    if len(segments) >= 2 and len(last) >= 25 and _SLUG_RE.search(last):
        return True
    return False


# ---------------------------------------------------------------------------
# Parseo de HTML (BeautifulSoup con respaldo de la stdlib)
# ---------------------------------------------------------------------------
def _make_soup(html: str):
    if not _HAS_BS4 or BeautifulSoup is None:  # pragma: no cover - defensivo
        raise RuntimeError("BeautifulSoup no está disponible")
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:  # pragma: no cover - lxml ausente o HTML raro
        return BeautifulSoup(html, "html.parser")


def _find_canonical(soup) -> str:
    for link in soup.find_all("link", href=True):
        rel = " ".join(link.get("rel") or []).lower()
        if "canonical" in rel:
            return str(link.get("href") or "").strip()
    return ""


def _collect_meta(soup) -> dict[str, str]:
    meta: dict[str, str] = {}
    for tag in soup.find_all("meta"):
        key = (
            tag.get("property") or tag.get("name") or tag.get("itemprop") or ""
        ).strip().lower()
        content = str(tag.get("content") or "").strip()
        if key and content and key not in meta:
            meta[key] = content
    return meta


def _iter_json_nodes(data: object) -> Iterable[dict]:
    """Recorre cualquier estructura JSON-LD y devuelve sus nodos dict."""
    stack: list[object] = [data]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            yield item
            graph = item.get("@graph")
            if isinstance(graph, list):
                stack.extend(graph)
            for value in item.values():
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(item, list):
            stack.extend(item)


def _json_author(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("name") or "").strip()
    if isinstance(value, list):
        names = [_json_author(item) for item in value]
        return ", ".join(name for name in names if name)
    return ""


def _extract_json_ld(soup) -> dict[str, str]:
    result: dict[str, str] = {}
    for script in soup.find_all("script"):
        if "ld+json" not in str(script.get("type") or "").lower():
            continue
        raw = (script.string or script.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            continue
        for node in _iter_json_nodes(data):
            node_type = node.get("@type")
            types = {
                str(value).lower()
                for value in (node_type if isinstance(node_type, list) else [node_type])
                if value
            }
            if not (types & _ARTICLE_JSON_LD_TYPES):
                continue
            headline = str(node.get("headline") or node.get("name") or "").strip()
            result.setdefault("headline", headline)
            result.setdefault(
                "date_published",
                str(node.get("datePublished") or node.get("dateCreated") or "").strip(),
            )
            result.setdefault("author", _json_author(node.get("author")))
            result.setdefault(
                "description", str(node.get("description") or "").strip()
            )
            result.setdefault(
                "article_section", str(node.get("articleSection") or "").strip()
            )
    return {key: value for key, value in result.items() if value}


class _StdlibHtmlParser(HTMLParser):
    """Respaldo mínimo de ``html.parser`` para metadatos y párrafos."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.h1_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.canonical = ""
        self.time_datetime = ""
        self.paragraphs: list[str] = []
        self._buffer: list[str] | None = None
        self._skip = 0
        self._in_title = False
        self._in_h1 = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        values = {key.lower(): (value or "") for key, value in attrs}
        if name in ("script", "style", "noscript", "template"):
            self._skip += 1
        elif name == "meta":
            key = (
                values.get("property") or values.get("name") or values.get("itemprop") or ""
            ).strip().lower()
            content = values.get("content", "").strip()
            if key and content:
                self.meta.setdefault(key, content)
        elif name == "link":
            if "canonical" in values.get("rel", "").lower() and values.get("href"):
                self.canonical = values["href"].strip()
        elif name == "title":
            self._in_title = True
        elif name == "h1":
            self._in_h1 = True
        elif name == "time":
            if values.get("datetime") and not self.time_datetime:
                self.time_datetime = values["datetime"].strip()
        elif name in ("p", "h2", "h3"):
            self._buffer = []

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name in ("script", "style", "noscript", "template"):
            self._skip = max(0, self._skip - 1)
        elif name == "title":
            self._in_title = False
        elif name == "h1":
            self._in_h1 = False
        elif name in ("p", "h2", "h3") and self._buffer is not None:
            text = clean_text(" ".join(self._buffer))
            if text:
                self.paragraphs.append(text)
            self._buffer = None

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._in_title:
            self.title_parts.append(data)
        if self._in_h1:
            self.h1_parts.append(data)
        if self._buffer is not None:
            self._buffer.append(data)


def _clean_title(value: str) -> str:
    title = clean_text(value or "").strip()
    if not title:
        return ""
    for separator in (" | ", " · ", " — ", " - "):
        if separator in title:
            head, _, tail = title.rpartition(separator)
            if head and len(head) >= 20 and len(tail) <= 40:
                title = head.strip()
    return title[:_MAX_TITLE_CHARS]


def _clean_author(value: str) -> str:
    author = clean_text(value or "").strip()
    author = re.sub(r"^(por|by)\s+", "", author, flags=re.IGNORECASE)
    return author[:200]


# ---------------------------------------------------------------------------
# Robots.txt con cache por dominio
# ---------------------------------------------------------------------------
class RobotsCache:
    """Cache thread-safe de ``robots.txt`` por dominio."""

    def __init__(self, fetcher: SupportsGet, settings: Settings) -> None:
        self.fetcher = fetcher
        self.settings = settings
        self._lock = threading.Lock()
        # ``None`` significa "sin reglas: permitido" (404, error o vacío).
        self._cache: dict[str, object | None] = {}

    def allowed(self, url: str, *, user_agent: str | None = None) -> bool:
        try:
            parsed = urlparse(url)
        except ValueError:
            return True
        if (parsed.scheme or "").lower() not in ("http", "https"):
            return True
        domain = (parsed.netloc or "").lower()
        if not domain:
            return True
        parser = self._parser_for(domain, parsed.scheme)
        if parser is None:
            return True
        return bool(
            parser.can_fetch(  # type: ignore[attr-defined]
                user_agent or self.settings.scraper_user_agent, url
            )
        )

    def _parser_for(self, domain: str, scheme: str):
        from urllib.robotparser import RobotFileParser

        with self._lock:
            if domain in self._cache:
                return self._cache[domain]
        robots_url = f"{scheme}://{domain}/robots.txt"
        parser: object | None = None
        try:
            response = self.fetcher.get(robots_url, accept="text/plain,*/*")
            candidate = RobotFileParser()
            candidate.parse(response.text.splitlines())
            parser = candidate
        except FetchError as exc:
            level = logging.WARNING if (exc.status_code or 0) >= 500 else logging.DEBUG
            logger.log(
                level,
                "robots.txt no disponible en %s (%s); se asume permitido",
                domain,
                exc.code,
            )
        except Exception:  # pragma: no cover - defensivo
            logger.warning(
                "Error inesperado leyendo robots.txt de %s; se asume permitido",
                domain,
                exc_info=True,
            )
        with self._lock:
            self._cache[domain] = parser
        return parser


# ---------------------------------------------------------------------------
# Parseo de feeds y sitemaps
# ---------------------------------------------------------------------------
def _local_name(tag: object) -> str:
    return str(tag or "").rsplit("}", 1)[-1].lower()


def _parse_xml(text: str) -> ET.Element:
    cleaned = re.sub(r"^\s*<\?xml[^>]*\?>", "", text or "").strip()
    if not cleaned:
        raise ValueError("documento XML vacío")
    try:
        return ET.fromstring(cleaned)
    except ET.ParseError as exc:
        raise ValueError(f"XML inválido: {exc}") from exc


def _node_text(node: ET.Element) -> str:
    """Texto plano de un nodo XML, sin quitar URLs (clean_text las elimina)."""
    return " ".join("".join(node.itertext()).split())


def _child_text(node: ET.Element, *names: str) -> str:
    wanted = {name.lower() for name in names}
    for child in node:
        if _local_name(child.tag) in wanted:
            value = _node_text(child)
            if value:
                return value
    return ""


def _descendant_text(node: ET.Element, *names: str) -> str:
    wanted = {name.lower() for name in names}
    for child in node.iter():
        if child is node:
            continue
        if _local_name(child.tag) in wanted:
            value = _node_text(child)
            if value:
                return value
    return ""


def _feed_entry_from_node(node: ET.Element, base_url: str) -> FeedEntry | None:
    link = ""
    for child in node:
        if _local_name(child.tag) != "link":
            continue
        href = str(child.get("href") or "").strip()
        rel = str(child.get("rel") or "alternate").lower()
        if href and (not link or rel == "alternate"):
            link = href
        elif not href and not link:
            text = _node_text(child)
            if text.startswith(("http://", "https://")):
                link = text
    if not link:
        link = _child_text(node, "guid", "id")
    if not link.startswith(("http://", "https://")):
        return None
    title = _child_text(node, "title")
    raw_date = _child_text(node, "pubdate", "published", "updated", "date")
    return FeedEntry(
        url=canonical_url(urljoin(base_url, link)),
        title=title,
        published=_parse_datetime(raw_date),
    )


def parse_feed(text: str, *, base_url: str = "") -> list[FeedEntry]:
    """Extrae los ítems de un feed RSS 2.0 o Atom."""
    root = _parse_xml(text)
    entries: list[FeedEntry] = []
    for node in root.iter():
        if _local_name(node.tag) not in ("item", "entry"):
            continue
        entry = _feed_entry_from_node(node, base_url)
        if entry is not None:
            entries.append(entry)
    return entries


def parse_sitemap(text: str, *, base_url: str = "") -> tuple[list[FeedEntry], list[str]]:
    """Devuelve ``(entradas, hijos)`` de un sitemap o de un índice de sitemaps."""
    root = _parse_xml(text)
    if _local_name(root.tag) == "sitemapindex":
        children: list[str] = []
        for node in root.iter():
            if _local_name(node.tag) != "loc":
                continue
            value = _node_text(node)
            if value:
                children.append(urljoin(base_url, value))
        return [], children
    entries: list[FeedEntry] = []
    for node in root.iter():
        if _local_name(node.tag) != "url":
            continue
        loc = _child_text(node, "loc")
        if not loc:
            continue
        title = _descendant_text(node, "title")
        published = _descendant_text(node, "publication_date", "pubdate", "lastmod")
        entries.append(
            FeedEntry(
                url=canonical_url(urljoin(base_url, loc)),
                title=title,
                published=_parse_datetime(published),
            )
        )
    return entries, []


# ---------------------------------------------------------------------------
# Agregados del resumen
# ---------------------------------------------------------------------------
def _average_sentiment(analyses: Sequence[TextAnalysisResult]) -> SentimentScores:
    if not analyses:
        return SentimentScores()
    totals = {"negativo": 0.0, "neutro": 0.0, "positivo": 0.0}
    for result in analyses:
        scores = result.sentiment.scores
        totals["negativo"] += float(scores.negativo)
        totals["neutro"] += float(scores.neutro)
        totals["positivo"] += float(scores.positivo)
    total = float(len(analyses))
    return SentimentScores(
        negativo=round(totals["negativo"] / total, 1),
        neutro=round(totals["neutro"] / total, 1),
        positivo=round(totals["positivo"] / total, 1),
    )


def _aggregate_frames(
    analyses: Sequence[TextAnalysisResult],
) -> tuple[list[FrameTally], list[str]]:
    totals: dict[str, dict[str, object]] = {}
    for result in analyses:
        for frame in result.frames:
            entry = totals.setdefault(
                frame.id, {"label": frame.label, "sum": 0.0, "count": 0}
            )
            entry["sum"] = float(entry["sum"]) + float(frame.score)  # type: ignore[arg-type]
            entry["count"] = int(entry["count"]) + 1  # type: ignore[arg-type]
    ordered = sorted(
        totals.items(),
        key=lambda item: float(item[1]["sum"]) / max(1, int(item[1]["count"])),  # type: ignore[arg-type]
        reverse=True,
    )
    tallies = [
        FrameTally(
            frame=str(entry["label"]),
            percentage=round(float(entry["sum"]) / max(1, int(entry["count"])), 1),  # type: ignore[arg-type]
        )
        for _, entry in ordered
    ]
    return tallies, [frame_id for frame_id, _ in ordered]


def bias_tendency_for(dominant_frame: str | None, country: str) -> str:
    """Texto de tendencia de sesgo según el encuadre dominante y el país."""
    if dominant_frame and dominant_frame in _FRAME_BIAS_TEXT:
        return _FRAME_BIAS_TEXT[dominant_frame]
    return _EXPECTED_BIAS_TEXT.get(country, "Enfoque Neutro / Informativo Institucional")


def hypothesis_match_for(
    dominant_frame: str | None, country: str, top_frames: Sequence[str]
) -> str:
    """Contrasta el encuadre dominante con la hipótesis del proyecto."""
    expected = _EXPECTED_FRAMES.get(country)
    if not expected or not dominant_frame:
        return "No concluyente"
    if dominant_frame in expected:
        return "Confirmada (Sesgo esperado)"
    if any(frame_id in expected for frame_id in top_frames[:3]):
        return "Parcial"
    return "No concluyente"


def build_news_article(
    article: ExtractedArticle, analysis: TextAnalysisResult | None = None
) -> NewsArticle:
    """Convierte una noticia extraída al contrato ``NewsArticle`` del frontend."""
    import hashlib

    signature = (article.canonical_url or article.url).encode("utf-8")
    return NewsArticle(
        id=f"noticia-{hashlib.sha1(signature).hexdigest()[:12]}",
        title=article.title,
        snippet=article.snippet,
        full_text=article.text,
        author=article.author,
        date=article.date,
        media=article.media,
        country=article.country,
        url=article.canonical_url or article.url,
        category=article.category,
        pre_analyzed_result=analysis,
    )


def build_summary(
    *,
    site_name: str,
    domain: str,
    country: str,
    articles: Sequence[NewsArticle],
    analyses: Sequence[TextAnalysisResult] | None = None,
) -> ScrapedSiteSummary:
    """Construye el resumen agregado del sitio escaneado."""
    analyzed = list(analyses or [])
    tallies, frame_ids = _aggregate_frames(analyzed)
    dominant = frame_ids[0] if frame_ids else None
    return ScrapedSiteSummary(
        site_name=site_name or domain or "Sitio desconocido",
        domain=domain,
        country=country or "Desconocido",
        total_analyzed=len(analyzed),
        average_sentiment=_average_sentiment(analyzed),
        top_frames=tallies,
        bias_tendency=bias_tendency_for(dominant, country),
        hypothesis_match=hypothesis_match_for(dominant, country, frame_ids),  # type: ignore[arg-type]
        articles=list(articles),
        generated_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------
class NewsScraper:
    """Descubrimiento, extracción y resumen de sitios de noticias."""

    def __init__(
        self, settings: Settings, *, fetcher: SupportsGet | None = None
    ) -> None:
        self.settings = settings
        self._owns_fetcher = fetcher is None
        if fetcher is None:
            from .fetching import Fetcher

            fetcher = Fetcher(settings)
        self.fetcher: SupportsGet = fetcher
        self.robots = RobotsCache(self.fetcher, settings)
        self.user_agent = settings.scraper_user_agent
        self.keywords = [keyword.strip() for keyword in settings.scraper_keywords if keyword.strip()]

    def close(self) -> None:
        if self._owns_fetcher:
            close = getattr(self.fetcher, "close", None)
            if callable(close):
                close()

    # -------------------------------------------------------- robots/acceso
    def effective_respect_robots(self, respect_robots: bool | None) -> bool:
        if respect_robots is None:
            return self.settings.scraper_respect_robots
        return respect_robots

    def check_robots(self, url: str, *, respect_robots: bool | None = None) -> None:
        if not self.effective_respect_robots(respect_robots):
            return
        if self.robots.allowed(url, user_agent=self.user_agent):
            return
        domain = domain_from_url(url)
        raise RobotsDeniedError(
            (
                f"robots.txt del dominio {domain} prohíbe descargar {url}. "
                "Envía respectRobots=false para forzar la descarga."
            ),
            url=url,
        )

    def fetch_html(
        self, url: str, *, respect_robots: bool | None = None
    ) -> FetchResponse:
        self.check_robots(url, respect_robots=respect_robots)
        response = self.fetcher.get(url, accept=HTML_ACCEPT)
        content_type = response.content_type
        if content_type and not any(
            token in content_type for token in ("html", "xml", "text/plain")
        ):
            raise ScraperError(
                (
                    f"La URL {url} no devolvió HTML sino '{content_type}'; "
                    "no se puede extraer una noticia de un documento binario."
                ),
                code="invalid_content",
                url=url,
            )
        return response

    # ---------------------------------------------------------- descubrir
    def discover(
        self,
        url: str,
        *,
        max_articles: int | None = None,
        keywords: Sequence[str] | None = None,
        respect_robots: bool | None = None,
    ) -> DiscoveryResult:
        """Descubre noticias candidatas a partir de una URL de sitio o noticia."""
        limit = self._article_limit(max_articles)
        response = self.fetch_html(url, respect_robots=respect_robots)
        html = response.text
        page_url = response.url or url
        info = self._parse_page_info(html, page_url)
        domain = domain_from_url(page_url) or domain_from_url(url)
        site = known_site_for(page_url) or known_site_for(url)
        site_name = info.site_name or (site.name if site else "") or domain

        source = "article"
        entries: list[FeedEntry] = []
        if looks_like_article_url(page_url) or self._is_probable_article_page(html, page_url):
            entries = [
                FeedEntry(
                    url=canonical_url(page_url), title=info.title or _title_from_url(page_url)
                )
            ]
        else:
            source = "rss"
            entries = self._discover_from_feeds(html, page_url, respect_robots)
            if not entries:
                source = "sitemap"
                entries = self._discover_from_sitemaps(page_url, respect_robots)
            if not entries:
                source = "links"
                entries = self._discover_from_links(html, page_url, domain)

        selected = self._select_entries(
            entries, keywords=keywords or None, limit=limit
        )
        return DiscoveryResult(
            source=source,
            homepage_url=page_url,
            site_name=site_name,
            domain=domain,
            country=infer_country(url=page_url, media_name=site_name),
            entries=selected,
        )

    def _article_limit(self, max_articles: int | None) -> int:
        configured = max(1, int(self.settings.scraper_max_articles))
        requested = int(max_articles) if max_articles else configured
        return max(1, min(requested, configured, 10))

    def _select_entries(
        self,
        entries: Sequence[FeedEntry],
        *,
        keywords: Sequence[str] | None,
        limit: int,
    ) -> list[FeedEntry]:
        active_keywords = [
            normalize_for_match(keyword.strip())
            for keyword in (keywords if keywords is not None else self.keywords)
            if keyword and keyword.strip()
        ]
        ordered = sorted(
            entries,
            key=lambda entry: entry.published
            or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        unique: list[FeedEntry] = []
        seen: set[str] = set()
        for entry in ordered:
            key = canonical_url(entry.url)
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(entry)
        matched = [
            entry for entry in unique if self._matches_keywords(entry, active_keywords)
        ]
        chosen = list(matched[:limit])
        for entry in unique:
            if len(chosen) >= limit:
                break
            if entry not in chosen:
                chosen.append(entry)
        return chosen[:limit]

    @staticmethod
    def _matches_keywords(entry: FeedEntry, keywords: Sequence[str]) -> bool:
        if not keywords:
            return True
        haystack = normalize_for_match(f"{entry.title} {entry.url}")
        return any(keyword in haystack for keyword in keywords)

    # --------------------------------------------------------------- feeds
    def _discover_from_feeds(
        self, html: str, base_url: str, respect_robots: bool | None
    ) -> list[FeedEntry]:
        seen: set[str] = set()
        for feed_url in self._feed_urls(html, base_url):
            if feed_url in seen:
                continue
            seen.add(feed_url)
            if (
                self.effective_respect_robots(respect_robots)
                and not self.robots.allowed(feed_url, user_agent=self.user_agent)
            ):
                logger.debug("robots.txt prohíbe el feed %s; se omite", feed_url)
                continue
            try:
                response = self.fetcher.get(feed_url, accept=XML_ACCEPT)
            except FetchError as exc:
                logger.debug("Feed no disponible %s: %s", feed_url, exc)
                continue
            try:
                entries = parse_feed(response.text, base_url=response.url or feed_url)
            except ValueError as exc:
                logger.debug("Feed inválido %s: %s", feed_url, exc)
                continue
            if entries:
                logger.debug("Feed %s aportó %s noticias", feed_url, len(entries))
                return entries
        return []

    def _feed_urls(self, html: str, base_url: str) -> list[str]:
        declared: list[str] = []
        if _HAS_BS4 and BeautifulSoup is not None:
            soup = _make_soup(html)
            for link in soup.find_all("link", href=True):
                rel = " ".join(link.get("rel") or []).lower()
                content_type = str(link.get("type") or "").lower()
                if (
                    "rss" in content_type
                    or "atom" in content_type
                    or "rss" in rel
                    or "atom" in rel
                ):
                    declared.append(urljoin(base_url, str(link.get("href") or "")))
        else:  # pragma: no cover - solo sin BeautifulSoup
            pattern = re.compile(
                r"<link[^>]+(?:rss|atom)[^>]*>", re.IGNORECASE
            )
            href_pattern = re.compile(r'href=["\']([^"\']+)', re.IGNORECASE)
            for match in pattern.finditer(html):
                href = href_pattern.search(match.group(0))
                if href:
                    declared.append(urljoin(base_url, href.group(1)))
        candidates = list(declared)
        for path in _FEED_PATHS:
            candidates.append(urljoin(base_url, path))
        unique: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if candidate and candidate not in seen:
                seen.add(candidate)
                unique.append(candidate)
        return unique

    # ------------------------------------------------------------- sitemaps
    def _discover_from_sitemaps(
        self, base_url: str, respect_robots: bool | None
    ) -> list[FeedEntry]:
        for path in _SITEMAP_PATHS:
            entries = self._read_sitemap(
                urljoin(base_url, path), respect_robots=respect_robots, depth=0
            )
            if entries:
                logger.debug("Sitemap %s aportó %s noticias", path, len(entries))
                return entries
        return []

    def _read_sitemap(
        self,
        sitemap_url: str,
        *,
        respect_robots: bool | None,
        depth: int,
    ) -> list[FeedEntry]:
        if (
            self.effective_respect_robots(respect_robots)
            and not self.robots.allowed(sitemap_url, user_agent=self.user_agent)
        ):
            return []
        try:
            response = self.fetcher.get(sitemap_url, accept=XML_ACCEPT)
        except FetchError as exc:
            logger.debug("Sitemap no disponible %s: %s", sitemap_url, exc)
            return []
        try:
            entries, children = parse_sitemap(
                response.text, base_url=response.url or sitemap_url
            )
        except ValueError as exc:
            logger.debug("Sitemap inválido %s: %s", sitemap_url, exc)
            return []
        if entries:
            return entries
        if children and depth == 0:
            for child in children[:4]:
                lowered = child.lower()
                if any(token in lowered for token in ("image", "video", "tag", "categoria")):
                    continue
                child_entries = self._read_sitemap(
                    child, respect_robots=respect_robots, depth=depth + 1
                )
                if child_entries:
                    return child_entries
        return []

    # -------------------------------------------------------------- enlaces
    def _discover_from_links(
        self, html: str, base_url: str, domain: str
    ) -> list[FeedEntry]:
        entries: list[FeedEntry] = []
        seen: set[str] = set()
        for href, text in self._iter_links(html, base_url):
            try:
                parsed = urlparse(href)
            except ValueError:
                continue
            if (parsed.scheme or "").lower() not in ("http", "https"):
                continue
            link_domain = domain_from_url(href)
            if domain and link_domain != domain:
                continue
            if not looks_like_article_url(href):
                continue
            key = canonical_url(href)
            if not key or key in seen:
                continue
            seen.add(key)
            entries.append(
                FeedEntry(url=key, title=clean_text(text) or _title_from_url(key))
            )
        return entries

    @staticmethod
    def _iter_links(html: str, base_url: str) -> Iterable[tuple[str, str]]:
        if _HAS_BS4 and BeautifulSoup is not None:
            soup = _make_soup(html)
            for anchor in soup.find_all("a", href=True):
                href = str(anchor.get("href") or "").strip()
                if href and not href.startswith(("#", "javascript:", "mailto:", "tel:")):
                    yield urljoin(base_url, href), anchor.get_text(" ", strip=True)
        else:  # pragma: no cover - solo sin BeautifulSoup
            pattern = re.compile(
                r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                re.IGNORECASE | re.DOTALL,
            )
            for match in pattern.finditer(html):
                yield urljoin(base_url, match.group(1)), clean_text(
                    re.sub(r"<[^>]+>", " ", match.group(2))
                )

    def _is_probable_article_page(self, html: str, url: str) -> bool:
        """¿Es una página de noticia aunque la URL no lo delate?

        Señales: ``og:type=article`` o un ``<article>`` con muy pocos enlaces de
        navegación (portadas y secciones tienen decenas).
        """
        if _HAS_BS4 and BeautifulSoup is not None:
            soup = _make_soup(html)
            meta = _collect_meta(soup)
            if str(meta.get("og:type") or "").lower() == "article":
                return True
            links = len(soup.find_all("a", href=True))
            return links <= 3 and soup.find("article") is not None
        parser = _StdlibHtmlParser()
        parser.feed(html)
        if str(parser.meta.get("og:type") or "").lower() == "article":
            return True
        return False

    # ------------------------------------------------------------ extraer
    def extract(
        self,
        url: str,
        *,
        respect_robots: bool | None = None,
        country: str | None = None,
        category: str = "",
        date_hint: str | None = None,
    ) -> ExtractedArticle:
        """Descarga y extrae una noticia.

        ``date_hint`` permite usar la fecha del feed/sitemap como respaldo
        cuando la página del artículo no declara una fecha parseable.
        """
        response = self.fetch_html(url, respect_robots=respect_robots)
        return self.extract_from_html(
            response.text,
            url=response.url or url,
            country=country,
            category=category,
            date_hint=date_hint,
        )

    def extract_from_html(
        self,
        html: str,
        *,
        url: str,
        country: str | None = None,
        category: str = "",
        date_hint: str | None = None,
    ) -> ExtractedArticle:
        info = self._parse_page_info(html, url)
        body = self._extract_body(html, url)
        words = count_words(body)
        if words < MIN_BODY_WORDS:
            raise ExtractionError(
                (
                    f"La noticia {url} solo tiene {words} palabras útiles "
                    f"(mínimo {MIN_BODY_WORDS}); se descarta."
                ),
                url=url,
            )
        text = body[: self.settings.max_text_chars]
        canonical = info.canonical or url
        site = known_site_for(canonical) or known_site_for(url)
        media = info.site_name or (site.name if site else "") or infer_media_name(
            url=canonical, fallback=domain_from_url(canonical)
        ) or ""
        resolved_country = country or infer_country(url=canonical, media_name=media)
        snippet = self._snippet(info.description, text)
        return ExtractedArticle(
            url=url,
            canonical_url=canonical,
            title=info.title or _title_from_url(canonical),
            text=text,
            author=info.author,
            date=info.date or normalize_date(date_hint),
            media=media,
            country=resolved_country,
            category=category or info.category,
            snippet=snippet,
        )

    def _parse_page_info(self, html: str, url: str) -> PageInfo:
        if _HAS_BS4 and BeautifulSoup is not None:
            soup = _make_soup(html)
            meta = _collect_meta(soup)
            json_ld = _extract_json_ld(soup)
            heading = soup.find("h1")
            raw_title = (
                meta.get("og:title")
                or meta.get("twitter:title")
                or (heading.get_text(" ", strip=True) if heading is not None else "")
                or (soup.title.get_text(" ", strip=True) if soup.title is not None else "")
            )
            canonical = _find_canonical(soup)
            time_node = soup.find("time")
            time_value = ""
            if time_node is not None:
                time_value = str(
                    time_node.get("datetime") or time_node.get_text(" ", strip=True) or ""
                ).strip()
        else:  # pragma: no cover - solo sin BeautifulSoup
            parser = _StdlibHtmlParser()
            parser.feed(html)
            meta = parser.meta
            json_ld = {}
            raw_title = (
                meta.get("og:title")
                or meta.get("twitter:title")
                or "".join(parser.title_parts)
                or "".join(parser.h1_parts)
            )
            canonical = parser.canonical
            time_value = parser.time_datetime

        title = (
            _clean_title(raw_title)
            or _clean_title(json_ld.get("headline", ""))
            or _title_from_url(url)
        )
        site_name = (
            meta.get("og:site_name") or meta.get("application-name") or ""
        ).strip()
        if not site_name:
            site = known_site_for(url)
            if site is not None:
                site_name = site.name
        if not site_name:
            site_name = domain_from_url(url)
        raw_date = (
            meta.get("article:published_time")
            or meta.get("datepublished")
            or meta.get("date")
            or meta.get("pubdate")
            or json_ld.get("date_published", "")
            or time_value
        )
        author = _clean_author(
            meta.get("author") or meta.get("article:author") or json_ld.get("author", "")
        )
        description = (
            meta.get("og:description") or meta.get("description") or json_ld.get("description", "")
        ).strip()
        section = (
            meta.get("article:section") or json_ld.get("article_section", "")
        ).strip()
        return PageInfo(
            title=title,
            site_name=site_name,
            description=description,
            author=author,
            date=normalize_date(raw_date),
            canonical=urljoin(url, canonical) if canonical else url,
            category=section,
        )

    def _extract_body(self, html: str, url: str) -> str:
        if _HAS_TRAFILATURA and trafilatura is not None:
            try:
                extracted = trafilatura.extract(
                    html,
                    url=url,
                    include_comments=False,
                    include_tables=False,
                    favor_recall=True,
                    deduplicate=True,
                )
            except Exception:  # pragma: no cover - trafilatura es defensivo
                logger.debug("trafilatura falló en %s", url, exc_info=True)
                extracted = None
            candidate = clean_text(extracted or "")
            if count_words(candidate) >= MIN_BODY_WORDS:
                return candidate
        if _HAS_BS4 and BeautifulSoup is not None:
            candidate = clean_text(self._body_with_soup(html))
            if count_words(candidate) >= MIN_BODY_WORDS:
                return candidate
        parser = _StdlibHtmlParser()
        parser.feed(html)
        return clean_text("\n\n".join(parser.paragraphs))

    @staticmethod
    def _body_with_soup(html: str) -> str:
        soup = _make_soup(html)
        for tag in soup(
            [
                "script",
                "style",
                "noscript",
                "template",
                "nav",
                "header",
                "footer",
                "aside",
                "form",
                "iframe",
                "svg",
                "button",
            ]
        ):
            tag.decompose()
        container = (
            soup.find("article")
            or soup.find("main")
            or soup.find(attrs={"role": "main"})
            or soup.body
            or soup
        )
        blocks = [
            node.get_text(" ", strip=True) for node in container.find_all(["p", "h2", "h3"])
        ]
        text = "\n\n".join(block for block in blocks if len(block) >= 40)
        if count_words(text) < MIN_BODY_WORDS:
            fallback = container.get_text("\n", strip=True)
            if count_words(fallback) > count_words(text):
                text = fallback
        return text

    @staticmethod
    def _snippet(description: str, text: str) -> str:
        if len(description) >= 40:
            return description[:_MAX_SNIPPET_CHARS].strip()
        snippet = text[:_MAX_SNIPPET_CHARS].strip()
        if len(text) > _MAX_SNIPPET_CHARS and " " in snippet:
            snippet = snippet.rsplit(" ", 1)[0] + "…"
        return snippet

    # ------------------------------------------------------------ análisis
    def analyze_extracted(
        self,
        article: ExtractedArticle,
        analysis: AnalysisService,
        *,
        job_id: str | None = None,
    ) -> TextAnalysisResult:
        """Analiza el texto de una noticia ya extraída."""
        country = article.country if article.country in ("Colombia", "México") else None
        return analysis.analyze_text(
            text=article.text,
            title=article.title or None,
            source_url=article.canonical_url or article.url,
            media_name=article.media or None,
            country=country,
            source="scraper",
            job_id=job_id,
        )

    def analyze_url(
        self,
        analysis: AnalysisService,
        url: str,
        *,
        respect_robots: bool | None = None,
        country: str | None = None,
    ) -> NewsArticle:
        """Extrae UNA noticia y la analiza en línea (endpoint ``analyze-url``)."""
        extracted = self.extract(
            url, respect_robots=respect_robots, country=country
        )
        result = self.analyze_extracted(extracted, analysis)
        return build_news_article(extracted, result)
