"""Enlaces de afiliado.

- Amazon: `https://<dominio>/dp/<ASIN>?tag=<tag>` — el enlace largo y limpio
  que pide el programa (sin acortar, sin parámetros de rastreo ajenos).
- SHEIN: el panel de afiliados de SHEIN genera el enlace por producto (su
  formato cambia según campaña), así que se PEGA TAL CUAL lo que dé el panel;
  aquí solo se valida que sea https, de SHEIN y no un acortador.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from src.multiplataforma import config

_ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")


class EnlaceInvalido(ValueError):
    pass


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def es_acortador(url: str) -> bool:
    h = _host(url)
    return any(h == a or h.endswith("." + a) for a in config.ACORTADORES)


def es_amazon(url: str) -> bool:
    h = _host(url)
    return bool(re.search(r"(^|\.)amazon\.[a-z.]+$", h))


def es_shein(url: str) -> bool:
    h = _host(url)
    return h == "shein.com" or h.endswith(".shein.com") or bool(re.search(r"(^|\.)shein\.[a-z.]+$", h))


def validar(url: str) -> str:
    """Devuelve el enlace limpio o lanza `EnlaceInvalido`."""
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith("https://"):
        raise EnlaceInvalido(f"El enlace tiene que ser https://: {url}")
    if es_acortador(url):
        raise EnlaceInvalido(f"No se usan acortadores ({_host(url)}): pega el enlace completo")
    return url


def enlace_amazon(asin: str, tag: str) -> str:
    asin = (asin or "").strip().upper()
    tag = (tag or "").strip()
    if not _ASIN_RE.match(asin):
        raise EnlaceInvalido(f"ASIN no válido: {asin!r} (10 caracteres A-Z/0-9)")
    if not tag:
        raise EnlaceInvalido("Falta el tag de afiliado de Amazon de la cuenta")
    return f"https://{config.AMAZON_DOMINIO}/dp/{asin}?tag={tag}"


def enlace_shein(url: str) -> str:
    """El enlace del panel de afiliados de SHEIN, tal cual."""
    url = validar(url)
    if url and not es_shein(url):
        raise EnlaceInvalido(f"No parece un enlace de SHEIN: {url}")
    return url


def resolver(*, asin: str = "", enlace: str = "", amazon_tag: str = "") -> str:
    """ASIN → enlace Amazon con el tag de la cuenta; si no, el enlace validado."""
    if asin:
        return enlace_amazon(asin, amazon_tag)
    if enlace and es_shein(enlace):
        return enlace_shein(enlace)
    return validar(enlace)
