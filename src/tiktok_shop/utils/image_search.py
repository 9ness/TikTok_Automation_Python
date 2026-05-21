"""Búsqueda de imágenes externas para auto-rellenar la textarea de
"Importar fotos por URL".

Dos proveedores soportados, en orden de preferencia:

1. **DuckDuckGo Images** (default) — sin API key, sin setup. Usa la lib
   `ddgs` que llama al backend de DDG. Suficiente para producto
   genérico ("marca + nombre"). Calidad razonable, sin coste.

2. **Google Custom Search Engine (CSE)** — opcional, requiere env vars
   `GOOGLE_CSE_API_KEY` + `GOOGLE_CSE_ID`. 100 q/día gratis. Mejor
   precisión para marcas / SKUs ambiguos. Si está configurado y el
   user pide `provider="google"` o `prefer_google=True`, se usa.

`search_product_images()` decide el provider automáticamente y
devuelve siempre la misma forma: `list[{link, title}]`. Nunca lanza —
si todo falla devuelve `[]`.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger("tiktok_shop.image_search")

_CSE_ENDPOINT = "https://www.googleapis.com/customsearch/v1"
_TIMEOUT_S = 15


# ---------------------------------------------------------------------------
# Public — entry point unificado
# ---------------------------------------------------------------------------
def search_product_images(
    query: str,
    *,
    num: int = 10,
    prefer_google: bool = False,
) -> tuple[str, list[dict[str, str]]]:
    """Busca imágenes para `query`. Devuelve `(provider_used, results)`.

    `provider_used`: "google_cse" | "ddg" | "none"
    `results`: list de `{link, title}`.

    Orden:
      - Si `prefer_google=True` y CSE está configurado → Google CSE.
      - Si no → DuckDuckGo (siempre disponible, sin API key).
      - Si DDG falla y CSE está configurado → fallback CSE.
    """
    query = (query or "").strip()
    if not query:
        return ("none", [])

    if prefer_google and google_cse_is_configured():
        results = google_image_search(query, num=num)
        if results:
            return ("google_cse", results)
        # CSE rate-limit o vacío → caer a DDG
        results = ddg_image_search(query, max_results=num)
        return ("ddg" if results else "none", results)

    # Default: DDG primero
    results = ddg_image_search(query, max_results=num)
    if results:
        return ("ddg", results)

    # DDG cayó → fallback a CSE si está configurado
    if google_cse_is_configured():
        results = google_image_search(query, num=num)
        return ("google_cse" if results else "none", results)
    return ("none", [])


# ---------------------------------------------------------------------------
# DuckDuckGo (default)
# ---------------------------------------------------------------------------
def ddg_image_search(query: str, *, max_results: int = 10) -> list[dict[str, str]]:
    """Busca en DuckDuckGo Images. Sin API key, sin setup.

    Devuelve `list[{link, title}]`. Nunca lanza — si la lib falla o no
    hay red, devuelve [].
    """
    if not query.strip():
        return []
    try:
        from ddgs import DDGS  # type: ignore
    except ImportError:
        logger.warning("[image_search] ddgs no instalado — pip install ddgs")
        return []

    try:
        with DDGS() as client:
            raw = client.images(
                query=query,
                max_results=max_results,
                region="wt-wt",   # mundial — TikTok Shop puede ser ES/UK/US
                safesearch="moderate",
                size="Large",       # filtramos fotos pequeñas / miniatura
            )
    except Exception as e:
        logger.warning("[image_search] DDG falló: %s", e)
        return []

    out: list[dict[str, str]] = []
    for item in raw or []:
        link = item.get("image") or item.get("thumbnail") or ""
        if not link:
            continue
        out.append({
            "link": link,
            "title": str(item.get("title", "")),
        })
        if len(out) >= max_results:
            break
    return out


# ---------------------------------------------------------------------------
# Google CSE (opcional, mejor precisión)
# ---------------------------------------------------------------------------
def google_cse_is_configured() -> bool:
    return bool(
        (os.getenv("GOOGLE_CSE_API_KEY", "").strip())
        and (os.getenv("GOOGLE_CSE_ID", "").strip())
    )


# Compat con código viejo
def is_configured() -> bool:
    """Devuelve True si CUALQUIER provider está disponible.

    DDG no necesita config, así que mientras la lib `ddgs` esté
    instalada (está en requirements.txt), siempre devolvemos True.
    """
    try:
        import ddgs  # noqa: F401
        return True
    except ImportError:
        return google_cse_is_configured()


def google_image_search(
    query: str,
    *,
    num: int = 10,
    safe: str = "off",
    image_size: str = "large",
) -> list[dict[str, Any]]:
    """Busca imágenes en Google CSE. Devuelve `list[{link, title, image}]`.

    Devuelve `[]` si CSE no está configurado o si la query falla.
    """
    api_key = os.getenv("GOOGLE_CSE_API_KEY", "").strip()
    cse_id = os.getenv("GOOGLE_CSE_ID", "").strip()
    if not api_key or not cse_id:
        return []
    if not query.strip():
        return []

    params = {
        "key": api_key,
        "cx": cse_id,
        "q": query,
        "searchType": "image",
        "num": max(1, min(10, num)),
        "safe": safe,
        "imgSize": image_size,
    }

    try:
        resp = requests.get(_CSE_ENDPOINT, params=params, timeout=_TIMEOUT_S)
    except requests.exceptions.RequestException as e:
        logger.warning("[image_search] CSE request falló: %s", e)
        return []

    if resp.status_code >= 400:
        logger.warning(
            "[image_search] CSE HTTP %s body=%s",
            resp.status_code, resp.text[:200],
        )
        return []

    try:
        data = resp.json()
    except ValueError:
        return []

    items = data.get("items") or []
    out: list[dict[str, Any]] = []
    for item in items:
        link = item.get("link")
        if not link:
            continue
        out.append({
            "link": link,
            "title": item.get("title", ""),
        })
    return out
