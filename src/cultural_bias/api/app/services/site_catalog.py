"""Catálogo de medios conocidos (compartido por análisis y scraper)."""

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


# Medios usados por el dashboard del frontend + algunos de referencia.
KNOWN_SITES: list[KnownSite] = [
    KnownSite(
        id="el-tiempo",
        name="El Tiempo",
        domain="eltiempo.com",
        country=COLOMBIA,
        category="Prensa Escrita",
        description=(
            "Diario de mayor circulación en Colombia. Cobertura nacional con "
            "énfasis en políticas públicas, frontera y convivencia urbana."
        ),
        flag="🇨🇴",
        logo_text="EL TIEMPO",
        accent_color="#1e40af",
    ),
    KnownSite(
        id="semana",
        name="Revista Semana",
        domain="semana.com",
        country=COLOMBIA,
        category="Medio Digital",
        description=(
            "Medio de análisis político y judicial. Tiende a priorizar encuadres "
            "de seguridad ciudadana, crimen organizado y orden público."
        ),
        flag="🇨🇴",
        logo_text="SEMANA",
        accent_color="#dc2626",
    ),
    KnownSite(
        id="el-espectador",
        name="El Espectador",
        domain="elespectador.com",
        country=COLOMBIA,
        category="Prensa Escrita",
        description=(
            "Diario colombiano con cobertura de derechos humanos, migración y "
            "política pública."
        ),
        flag="🇨🇴",
        logo_text="EL ESPECTADOR",
        accent_color="#0f766e",
    ),
    KnownSite(
        id="el-universal-mx",
        name="El Universal",
        domain="eluniversal.com.mx",
        country=MEXICO,
        category="Prensa Escrita",
        description=(
            "Diario mexicano con amplia cobertura de migración en tránsito y "
            "política migratoria de EE. UU."
        ),
        flag="🇲🇽",
        logo_text="EL UNIVERSAL",
        accent_color="#b91c1c",
    ),
    KnownSite(
        id="milenio",
        name="Milenio",
        domain="milenio.com",
        country=MEXICO,
        category="Medio Digital",
        description=(
            "Medio digital mexicano con cobertura de frontera, empleo y "
            "economía regional."
        ),
        flag="🇲🇽",
        logo_text="MILENIO",
        accent_color="#1d4ed8",
    ),
    KnownSite(
        id="reforma",
        name="Reforma",
        domain="reforma.com",
        country=MEXICO,
        category="Prensa Escrita",
        description=(
            "Diario mexicano de referencia nacional; cobertura económica y de "
            "política migratoria."
        ),
        flag="🇲🇽",
        logo_text="REFORMA",
        accent_color="#15803d",
    ),
    KnownSite(
        id="el-heraldo-co",
        name="El Heraldo",
        domain="elheraldo.co",
        country=COLOMBIA,
        category="Prensa Escrita",
        description="Diario del Caribe colombiano con cobertura de frontera y migración.",
        flag="🇨🇴",
        logo_text="EL HERALDO",
        accent_color="#b45309",
    ),
    KnownSite(
        id="la-jornada",
        name="La Jornada",
        domain="jornada.com.mx",
        country=MEXICO,
        category="Prensa Escrita",
        description="Diario mexicano con énfasis en derechos humanos y movilidad.",
        flag="🇲🇽",
        logo_text="LA JORNADA",
        accent_color="#7c3aed",
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
