"""Catálogo de medios permitidos para la ingesta (compartido por análisis y scraper)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from urllib.parse import urlparse

COLOMBIA = "Colombia"
MEXICO = "México"


@dataclass(frozen=True)
class KnownSite:
    id: str
    name: str
    domain: str
    country: str
    category: str
    description: str
    flag: str = ""
    logo_text: str = ""
    accent_color: str = ""

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


# Únicos medios autorizados para scraping/análisis vía API.
KNOWN_SITES: list[KnownSite] = [
    KnownSite(
        id="semana",
        name="Revista Semana",
        domain="semana.com",
        country=COLOMBIA,
        category="Medio Digital",
        description=(
            "Medio colombiano de análisis político y actualidad. En este proyecto "
            "se utiliza como fuente autorizada para la extracción y el análisis de "
            "noticias sobre migración venezolana."
        ),
        flag="🇨🇴",
        logo_text="SEMANA",
        accent_color="#dc2626",
    ),
    KnownSite(
        id="milenio",
        name="Milenio",
        domain="milenio.com",
        country=MEXICO,
        category="Medio Digital",
        description=(
            "Medio mexicano con cobertura nacional y regional. En este proyecto se "
            "utiliza como fuente autorizada para la extracción y el análisis de "
            "noticias sobre migración venezolana."
        ),
        flag="🇲🇽",
        logo_text="MILENIO",
        accent_color="#1d4ed8",
    ),
    KnownSite(
        id="la-cronica",
        name="La Crónica",
        domain="cronica.com.mx",
        country=MEXICO,
        category="Medio Digital",
        description=(
            "Medio mexicano (La Crónica de Hoy) con cobertura informativa. En este "
            "proyecto se utiliza como fuente autorizada para la extracción y el "
            "análisis de noticias sobre migración venezolana."
        ),
        flag="🇲🇽",
        logo_text="LA CRÓNICA",
        accent_color="#0f766e",
    ),
]

_BY_DOMAIN: dict[str, KnownSite] = {}
for _site in KNOWN_SITES:
    _BY_DOMAIN[_site.domain] = _site
    _BY_DOMAIN[_site.domain.removeprefix("www.")] = _site

_MX_HINTS = (".mx",)
_CO_HINTS = (".co",)


def domain_from_url(url: str | None) -> str:
    if not url:
        return ""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return (parsed.netloc or "").lower().removeprefix("www.")


def known_site_for(url_or_domain: str | None) -> KnownSite | None:
    if not url_or_domain:
        return None
    domain = domain_from_url(url_or_domain).split(":")[0]
    if domain in _BY_DOMAIN:
        return _BY_DOMAIN[domain]
    for known_domain, site in _BY_DOMAIN.items():
        if domain.endswith(f".{known_domain}") or known_domain.endswith(f".{domain}"):
            return site
    return None


def is_allowed_source(url_or_domain: str | None) -> bool:
    """Indica si la URL/dominio pertenece a un medio autorizado para ingesta."""
    return known_site_for(url_or_domain) is not None


def allowed_source_message() -> str:
    names = ", ".join(f"{site.name} ({site.country})" for site in KNOWN_SITES)
    return f"Solo se permiten los medios autorizados: {names}."


def infer_country(*, url: str | None = None, media_name: str | None = None) -> str:
    site = known_site_for(url or media_name)
    if site:
        return site.country
    domain = domain_from_url(url)
    if domain.endswith(_MX_HINTS):
        return MEXICO
    if domain.endswith(_CO_HINTS):
        return COLOMBIA
    if media_name:
        normalized = media_name.lower()
        if any(
            hint in normalized
            for hint in ("milenio", "reforma", "universal", "jornada", "mexico", "méxico")
        ):
            return MEXICO
        if any(
            hint in normalized
            for hint in ("tiempo", "semana", "espectador", "heraldo", "colombia")
        ):
            return COLOMBIA
    return "Desconocido"


def infer_media_name(*, url: str | None = None, fallback: str | None = None) -> str | None:
    site = known_site_for(url)
    if site:
        return site.name
    domain = domain_from_url(url)
    if domain:
        return domain
    return fallback
