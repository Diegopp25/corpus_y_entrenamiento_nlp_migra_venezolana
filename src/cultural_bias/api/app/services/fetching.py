"""Capa HTTP endurecida para la ingesta de noticias.

Todo el tráfico saliente del scraper pasa por :class:`Fetcher`, que aplica:

* ``User-Agent`` configurable (``settings.scraper_user_agent``) y ``Accept``.
* Timeout de conexión/lectura (``settings.scraper_timeout_seconds``).
* Límite de tamaño de respuesta (``settings.scraper_max_response_bytes``).
* Seguimiento **manual** de redirecciones para revalidar cada destino con el
  guard SSRF antes de seguirlo.
* Guard SSRF: solo ``http(s)``, sin credenciales embebidas y sin IPs privadas,
  de loopback, link-local (incluida la metadata de nube ``169.254.169.254``),
  multicast, reservadas o sin especificar. La resolución DNS se valida con
  :func:`socket.getaddrinfo` para evitar *DNS rebinding* trivial.

La capa es inyectable para pruebas: se puede pasar un ``transport`` de
``httpx`` (:class:`httpx.MockTransport`) o cualquier objeto que cumpla el
protocolo :class:`SupportsGet` (por ejemplo un ``fetch`` falso). Así los tests
corren sin red real.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from dataclasses import dataclass, field
from typing import Mapping, Protocol
from urllib.parse import urljoin, urlparse

import httpx

from ..config import Settings

logger = logging.getLogger(__name__)

#: Máximo de redirecciones que se siguen antes de abortar.
MAX_REDIRECTS = 5

_ALLOWED_SCHEMES = {"http", "https"}
_REDIRECT_CODES = {301, 302, 303, 307, 308}
_DEFAULT_PORTS = {"http": 80, "https": 443}

#: Hosts de metadata de nube que nunca deben ser visitados.
_BLOCKED_HOSTNAMES = {
    "metadata",
    "metadata.google.internal",
    "instance-data",
    "169.254.169.254",
}

#: Rangos extra que ``ipaddress`` no marca como privados en todas las versiones
#: (espacio compartido de operadores y documentación reservada).
_EXTRA_BLOCKED_NETWORKS = (
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("198.18.0.0/15"),
)

HTML_ACCEPT = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
)
XML_ACCEPT = "application/xml,text/xml,application/rss+xml,application/atom+xml,*/*;q=0.8"


class FetchError(Exception):
    """Error tipado de la capa de descarga.

    ``code`` identifica la causa de forma estable para que los routers puedan
    traducirlo a un :class:`~app.errors.APIError` con un mensaje claro.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        url: str = "",
        status_code: int | None = None,
        detail: object | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.url = url
        self.status_code = status_code
        self.detail = detail

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


@dataclass(slots=True)
class FetchResponse:
    """Respuesta HTTP ya validada y acotada en tamaño."""

    url: str
    status_code: int
    content: bytes
    headers: Mapping[str, str] = field(default_factory=dict)

    @property
    def content_type(self) -> str:
        return (self.headers.get("content-type") or "").split(";")[0].strip().lower()

    @property
    def charset(self) -> str | None:
        raw = self.headers.get("content-type") or ""
        for part in raw.split(";")[1:]:
            name, _, value = part.strip().partition("=")
            if name.strip().lower() == "charset" and value:
                return value.strip().strip('"').lower()
        return None

    @property
    def text(self) -> str:
        charset = self.charset or "utf-8"
        try:
            return self.content.decode(charset, errors="replace")
        except LookupError:
            return self.content.decode("utf-8", errors="replace")


class SupportsGet(Protocol):
    """Contrato mínimo de un descargador inyectable (real o falso)."""

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        accept: str | None = None,
    ) -> FetchResponse: ...


# ---------------------------------------------------------------------------
# Guard SSRF
# ---------------------------------------------------------------------------
def _is_blocked_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Indica si una dirección IP no debe visitarse desde el scraper."""
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    if (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        return True
    if address.version == 4:
        return any(address in network for network in _EXTRA_BLOCKED_NETWORKS)
    return False


def _resolve_addresses(
    host: str,
    parsed,
    *,
    original_url: str,
) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    try:
        port = parsed.port or _DEFAULT_PORTS.get((parsed.scheme or "").lower(), 80)
    except ValueError as exc:
        raise FetchError(
            "invalid_url",
            f"La URL {original_url} tiene un puerto inválido.",
            url=original_url,
        ) from exc
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchError(
            "dns_error",
            f"No se pudo resolver el host '{host}' ({exc}). Revisa la URL del sitio.",
            url=original_url,
        ) from exc
    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        raw = info[4][0]
        try:
            address = ipaddress.ip_address(raw)
        except ValueError:  # pragma: no cover - defensivo
            continue
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise FetchError(
            "dns_error",
            f"El host '{host}' no resolvió a ninguna dirección IP.",
            url=original_url,
        )
    return addresses


def validate_url(url: str, *, allow_private_networks: bool = False) -> str:
    """Valida esquema, host y destino de una URL (guard SSRF).

    Devuelve la misma URL si es segura; lanza :class:`FetchError` con un
    mensaje en español si no lo es.
    """
    candidate = (url or "").strip()
    if not candidate:
        raise FetchError("invalid_url", "La URL está vacía.", url=url)
    try:
        parsed = urlparse(candidate)
    except ValueError as exc:
        raise FetchError(
            "invalid_url", f"La URL no es válida: {candidate}", url=url
        ) from exc
    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise FetchError(
            "invalid_scheme",
            f"Solo se permiten URLs http o https; se recibió '{scheme or 'sin esquema'}'.",
            url=candidate,
        )
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise FetchError(
            "invalid_url", f"La URL no incluye un host válido: {candidate}", url=candidate
        )
    if parsed.username or parsed.password:
        raise FetchError(
            "invalid_url",
            "No se permiten URLs con credenciales embebidas.",
            url=candidate,
        )
    if host in _BLOCKED_HOSTNAMES:
        raise FetchError(
            "blocked_url",
            f"El host '{host}' está bloqueado por seguridad (SSRF).",
            url=candidate,
        )
    addresses = _resolve_addresses(host, parsed, original_url=candidate)
    if allow_private_networks:
        return candidate
    for address in addresses:
        if _is_blocked_address(address):
            raise FetchError(
                "blocked_url",
                (
                    f"La URL {candidate} apunta a una dirección privada o interna "
                    f"({address}); se bloquea para evitar SSRF."
                ),
                url=candidate,
            )
    return candidate


# ---------------------------------------------------------------------------
# Cliente HTTP
# ---------------------------------------------------------------------------
class Fetcher:
    """Cliente HTTP síncrono y reutilizable con redirecciones controladas."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
        client: httpx.Client | None = None,
        max_redirects: int = MAX_REDIRECTS,
    ) -> None:
        self.settings = settings
        self.max_redirects = max(1, int(max_redirects))
        self._owns_client = client is None
        if client is not None:
            self._client = client
        else:
            self._client = httpx.Client(
                timeout=httpx.Timeout(settings.scraper_timeout_seconds),
                transport=transport,
                follow_redirects=False,
                headers={"User-Agent": settings.scraper_user_agent},
            )

    # ------------------------------------------------------------ ciclo vida
    @property
    def user_agent(self) -> str:
        return self.settings.scraper_user_agent

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Fetcher:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ----------------------------------------------------------------- API
    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        accept: str | None = None,
    ) -> FetchResponse:
        """Descarga ``url`` siguiendo redirecciones de forma segura."""
        request_headers = {"User-Agent": self.settings.scraper_user_agent}
        if accept:
            request_headers["Accept"] = accept
        if headers:
            request_headers.update(headers)
        return self._request(url.strip(), request_headers)

    # -------------------------------------------------------------- interno
    def _request(self, url: str, headers: Mapping[str, str]) -> FetchResponse:
        current = url
        allow_private = self.settings.scraper_allow_private_networks
        for _hop in range(self.max_redirects + 1):
            validate_url(current, allow_private_networks=allow_private)
            location: str | None = None
            status_code: int
            response_headers: dict[str, str]
            content: bytes
            try:
                with self._client.stream(
                    "GET", current, headers=dict(headers), follow_redirects=False
                ) as response:
                    status_code = response.status_code
                    response_headers = {
                        key.lower(): value for key, value in response.headers.items()
                    }
                    if status_code in _REDIRECT_CODES:
                        location = response.headers.get("location")
                        if not location:
                            raise FetchError(
                                "invalid_redirect",
                                f"La URL {current} respondió {status_code} sin cabecera Location.",
                                url=current,
                                status_code=status_code,
                            )
                    else:
                        content = self._read_limited(response, current)
            except httpx.TimeoutException as exc:
                raise FetchError(
                    "timeout",
                    (
                        f"El sitio {current} tardó más de "
                        f"{self.settings.scraper_timeout_seconds:.0f}s en responder."
                    ),
                    url=current,
                ) from exc
            except httpx.HTTPError as exc:
                raise FetchError(
                    "connection_error",
                    f"No se pudo conectar con {current}: {exc}",
                    url=current,
                ) from exc
            if location is not None:
                try:
                    current = urljoin(current, location)
                except ValueError as exc:  # pragma: no cover - defensivo
                    raise FetchError(
                        "invalid_redirect",
                        f"La redirección de {current} no es válida: {location}",
                        url=current,
                    ) from exc
                continue
            if status_code >= 400:
                code = "not_found" if status_code == 404 else "http_error"
                raise FetchError(
                    code,
                    f"El sitio respondió HTTP {status_code} para {current}.",
                    url=current,
                    status_code=status_code,
                )
            if not content:
                raise FetchError(
                    "empty_response",
                    f"La respuesta de {current} está vacía.",
                    url=current,
                    status_code=status_code,
                )
            return FetchResponse(
                url=current,
                status_code=status_code,
                content=content,
                headers=response_headers,
            )
        raise FetchError(
            "too_many_redirects",
            (
                f"La URL {url} supera el máximo de {self.max_redirects} "
                "redirecciones permitidas."
            ),
            url=url,
        )

    def _read_limited(self, response: httpx.Response, url: str) -> bytes:
        max_bytes = max(1, int(self.settings.scraper_max_response_bytes))
        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            raise FetchError(
                "response_too_large",
                (
                    f"La respuesta de {url} declara {declared} bytes y supera el "
                    f"máximo de {max_bytes} bytes."
                ),
                url=url,
                status_code=response.status_code,
            )
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes():
            total += len(chunk)
            if total > max_bytes:
                raise FetchError(
                    "response_too_large",
                    f"La respuesta de {url} supera el máximo de {max_bytes} bytes.",
                    url=url,
                    status_code=response.status_code,
                )
            chunks.append(chunk)
        return b"".join(chunks)


def fetch(
    url: str,
    settings: Settings,
    *,
    transport: httpx.BaseTransport | None = None,
    accept: str | None = None,
) -> FetchResponse:
    """Atajo de conveniencia para descargar una URL con un ``Fetcher`` efímero."""
    with Fetcher(settings, transport=transport) as fetcher:
        return fetcher.get(url, accept=accept)
