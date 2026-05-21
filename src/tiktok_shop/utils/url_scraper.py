"""Scraper de URLs de TikTok Shop (y similares) para auto-rellenar el form
de un producto sin que el usuario tenga que copiar a mano nombre/precio/etc.

Estrategia (en orden, defensiva — devuelve lo que pueda):

1) HTTP GET con User-Agent realista.
2) Parsea HTML con BeautifulSoup.
3) Extrae en este orden de prioridad:
   - JSON-LD `<script type="application/ld+json">` (Schema.org Product)
   - Open Graph (`og:title`, `og:description`, `og:image`, `og:price:amount`,
     `og:price:currency`, `product:price:amount`, etc.)
   - Twitter Card (`twitter:title`, `twitter:description`, `twitter:image`)
   - `<title>` y `<meta name="description">` como último recurso.
4) Si tiene texto suficiente, opcionalmente pide a Gemini que extraiga
   nombre / marca / categoría / subcategoría / precio EUR.

TikTok Shop renderiza muchas cosas client-side, así que el scraping HTML
solo capturará lo que esté en el primer payload. Es mejor que nada y
sirve como pre-relleno — el usuario revisa y guarda.

NUNCA lanza excepción: si todo falla, devuelve un dict con lo poco que
haya conseguido + un `warnings` con el motivo.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("tiktok_shop.url_scraper")


# User-Agent realista — TikTok responde 403 a UAs por defecto de requests.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_REQUEST_TIMEOUT = 15  # seg — TikTok a veces tarda


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def scrape_product_url(url: str, *, use_gemini: bool = True) -> dict[str, Any]:
    """Descarga `url` e intenta extraer datos de producto.

    Devuelve dict con (cualquier subset, según lo encontrado):
      - name: str
      - brand: str
      - description: str
      - category: str (inferida)
      - subcategory: str
      - price_eur: float
      - currency: str
      - image_url: str
      - warnings: list[str]  (qué falló o qué se asume)
      - raw_text_sample: str (primeros ~2000 chars del HTML, para debug)

    Nunca lanza: si el GET falla → devuelve `{"warnings": [error_msg]}`.
    """
    out: dict[str, Any] = {"warnings": []}

    # ---------- 1. HTTP GET ----------
    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/webp,*/*;q=0.8"
                ),
            },
            timeout=_REQUEST_TIMEOUT,
            allow_redirects=True,
        )
    except requests.exceptions.RequestException as e:
        msg = f"No se pudo descargar la URL: {e}"
        logger.warning("[url_scraper] %s", msg)
        out["warnings"].append(msg)
        return out

    if resp.status_code >= 400:
        msg = f"HTTP {resp.status_code} al pedir la URL."
        logger.warning("[url_scraper] %s url=%s", msg, url)
        out["warnings"].append(msg)
        return out

    # ---------- 2a. Extraer datos de la URL FINAL (tras redirects) ----------
    # TikTok Shop: los share-link `vm.tiktok.com/...` redirigen a una URL
    # `www.tiktok.com/view/product/{id}?og_info={...}&share_region=...` que
    # YA TRAE el título e imagen en `og_info` URL-encoded. Es mucho más
    # fiable que parsear el HTML (que está bot-protegido y JS-rendered).
    final_url = str(resp.url)
    tt_meta = _extract_tiktok_share_params(final_url)
    if tt_meta:
        out.update(tt_meta)

    html = resp.text
    out["raw_text_sample"] = html[:2000]

    # ---------- 2. Parse ----------
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception as e:
        out["warnings"].append(f"Parse HTML falló: {e}")
        return out

    # ---------- 3a. JSON-LD ----------
    jsonld = _extract_jsonld_product(soup)
    if jsonld:
        out.update(jsonld)

    # ---------- 3b. Open Graph ----------
    og = _extract_open_graph(soup)
    for k, v in og.items():
        out.setdefault(k, v)

    # ---------- 3c. Twitter Card ----------
    tw = _extract_twitter(soup)
    for k, v in tw.items():
        out.setdefault(k, v)

    # ---------- 3d. Fallback <title> / <meta description> ----------
    if "name" not in out:
        title_tag = soup.find("title")
        if title_tag and title_tag.text.strip():
            out["name"] = _clean_title(title_tag.text.strip())
    if "description" not in out:
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            out["description"] = meta_desc["content"].strip()

    # ---------- 4. Refinar con Gemini si tenemos descripción ----------
    if use_gemini:
        gemini_result = _refine_with_gemini(out, html=html)
        if gemini_result:
            # Gemini puede AÑADIR campos pero no sobrescribe lo que ya
            # detectamos con scraping (más fiable que la inferencia LLM).
            for k, v in gemini_result.items():
                if v and not out.get(k):
                    out[k] = v

    # ---------- 5. Limpieza final ----------
    if "name" in out:
        out["name"] = out["name"].strip()[:200]
    if "brand" in out:
        out["brand"] = out["brand"].strip()[:120]
    if "description" in out:
        out["description"] = out["description"].strip()[:2000]

    return out


# ---------------------------------------------------------------------------
# TikTok Shop share params — URL final ya trae name+image en query string
# ---------------------------------------------------------------------------
_TT_PRODUCT_PATH_RE = re.compile(r"/view/product/(\d+)")


def _extract_tiktok_share_params(final_url: str) -> dict[str, Any]:
    """Extrae datos del producto desde la URL final tras seguir redirects.

    TikTok pone en los query params al hacer share:
      - `og_info`: JSON URL-encoded con `{"title": "...", "image": "..."}`
      - `share_region`: ES / FR / DE …
      - path `/view/product/{product_id}`

    Esto bypassa por completo el bot-detection del HTML porque los datos
    YA están en la URL que TikTok mismo genera al compartir.
    """
    out: dict[str, Any] = {}
    if not final_url:
        return out

    try:
        parsed = urlparse(final_url)
    except Exception:
        return out

    # 1) product_id del path
    if m := _TT_PRODUCT_PATH_RE.search(parsed.path or ""):
        out["product_id"] = m.group(1)

    # 2) og_info JSON encoded
    qs = parse_qs(parsed.query or "")
    og_info_raw = qs.get("og_info", [None])[0]
    if og_info_raw:
        try:
            og = json.loads(unquote(og_info_raw))
            if isinstance(og, dict):
                if title := og.get("title"):
                    out["name"] = _clean_tiktok_title(str(title))
                if img := og.get("image"):
                    out["image_url"] = str(img)
        except (json.JSONDecodeError, ValueError) as e:
            logger.debug("[url_scraper] og_info parse falló: %s", e)

    # 3) share_region → idioma probable
    if region := qs.get("share_region", [None])[0]:
        out["share_region"] = str(region).upper()

    return out


# Limpia títulos de TikTok Shop que suelen ser muy largos con varias
# separaciones por " - ". Nos quedamos con los primeros 2-3 segmentos
# que normalmente son: marca - nombre - variante.
def _clean_tiktok_title(title: str) -> str:
    title = title.strip()
    # Si tiene muchos " - ", recortamos a los primeros 3 trozos. Suele
    # ser suficiente para name (más se pierde en ruido SEO).
    parts = [p.strip() for p in title.split(" - ") if p.strip()]
    if len(parts) > 3:
        title = " - ".join(parts[:3])
    return title[:200]


# ---------------------------------------------------------------------------
# JSON-LD
# ---------------------------------------------------------------------------
def _extract_jsonld_product(soup: BeautifulSoup) -> dict[str, Any]:
    """Busca `<script type="application/ld+json">` con un Product Schema.org."""
    out: dict[str, Any] = {}
    for script in soup.find_all("script", type="application/ld+json"):
        text = (script.string or "").strip()
        if not text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            t = item.get("@type")
            if isinstance(t, list):
                is_product = any(x in ("Product", "schema:Product") for x in t)
            else:
                is_product = t in ("Product", "schema:Product")
            if not is_product:
                continue

            if name := item.get("name"):
                out["name"] = str(name)
            if brand := item.get("brand"):
                if isinstance(brand, dict):
                    out["brand"] = str(brand.get("name", "")).strip()
                else:
                    out["brand"] = str(brand).strip()
            if desc := item.get("description"):
                out["description"] = str(desc)
            if img := item.get("image"):
                if isinstance(img, list) and img:
                    out["image_url"] = str(img[0])
                elif isinstance(img, str):
                    out["image_url"] = img

            offers = item.get("offers")
            if isinstance(offers, dict):
                offers = [offers]
            if isinstance(offers, list) and offers:
                first = offers[0]
                if isinstance(first, dict):
                    price = first.get("price") or first.get("lowPrice")
                    if price is not None:
                        try:
                            out["price_eur"] = float(str(price).replace(",", "."))
                        except ValueError:
                            pass
                    if cur := first.get("priceCurrency"):
                        out["currency"] = str(cur)

            if cat := item.get("category"):
                out["category"] = str(cat).lower()

            return out  # primer producto encontrado → suficiente
    return out


# ---------------------------------------------------------------------------
# Open Graph
# ---------------------------------------------------------------------------
def _extract_open_graph(soup: BeautifulSoup) -> dict[str, Any]:
    """`<meta property="og:*">` — `name` también soportado por compat."""
    out: dict[str, Any] = {}

    def og(prop: str) -> str | None:
        m = soup.find("meta", attrs={"property": prop}) or soup.find(
            "meta", attrs={"name": prop}
        )
        if m and m.get("content"):
            return m["content"].strip()
        return None

    if v := og("og:title"):
        out["name"] = _clean_title(v)
    if v := og("og:description"):
        out["description"] = v
    if v := og("og:image"):
        out["image_url"] = v
    if v := og("product:brand"):
        out["brand"] = v

    # Precio: muchos sitios usan `product:price:amount` o `og:price:amount`
    for k in ("product:price:amount", "og:price:amount", "product:price"):
        if v := og(k):
            try:
                out["price_eur"] = float(v.replace(",", "."))
                break
            except ValueError:
                continue
    for k in ("product:price:currency", "og:price:currency"):
        if v := og(k):
            out.setdefault("currency", v)
            break

    return out


# ---------------------------------------------------------------------------
# Twitter card
# ---------------------------------------------------------------------------
def _extract_twitter(soup: BeautifulSoup) -> dict[str, Any]:
    out: dict[str, Any] = {}

    def tw(name: str) -> str | None:
        m = soup.find("meta", attrs={"name": name}) or soup.find(
            "meta", attrs={"property": name}
        )
        if m and m.get("content"):
            return m["content"].strip()
        return None

    if v := tw("twitter:title"):
        out["name"] = _clean_title(v)
    if v := tw("twitter:description"):
        out["description"] = v
    if v := tw("twitter:image"):
        out["image_url"] = v
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_TITLE_SUFFIX_RE = re.compile(
    r"\s*[|–-]\s*(TikTok Shop|TikTok|Amazon|.*Shop)\s*$",
    re.IGNORECASE,
)


def _clean_title(title: str) -> str:
    """Quita sufijos típicos como ' | TikTok Shop' del título de la página."""
    return _TITLE_SUFFIX_RE.sub("", title).strip()


# ---------------------------------------------------------------------------
# Extracción desde texto pegado por el usuario
# ---------------------------------------------------------------------------
def extract_from_text(raw_text: str) -> dict[str, Any]:
    """Atajo: el user pega texto libre (título, descripción, share text del
    móvil, copy del dashboard de TikTok Shop, …) y Gemini saca name/brand/
    category/subcategory/price_eur. Usa exactamente el mismo prompt que
    `_refine_with_gemini` para que la salida sea coherente.

    Devuelve dict con campos detectados + `warnings` si Gemini no está
    disponible. Nunca lanza.
    """
    out: dict[str, Any] = {"warnings": []}
    text = (raw_text or "").strip()
    if len(text) < 5:
        out["warnings"].append("Texto demasiado corto para analizar.")
        return out

    try:
        from src.tiktok_shop.api.gemini import generate_json, is_configured
    except Exception as e:
        out["warnings"].append(f"Gemini no disponible: {e}")
        return out
    if not is_configured():
        out["warnings"].append("Gemini sin API key configurada.")
        return out

    system_prompt = (
        "Eres un asistente que extrae datos estructurados de productos a "
        "partir de texto en español. Devuelve SIEMPRE JSON estricto, sin "
        "explicación. Si un campo no se puede inferir, omítelo. "
        "Categorías válidas: skincare, fitness, hogar, tech, moda, otros. "
        "El precio devuélvelo SOLO como número (sin €, sin separadores de "
        "miles, decimal con punto)."
    )
    user_prompt = (
        "Extrae nombre, marca, categoría, subcategoría y precio en EUR del "
        "siguiente texto de un producto. Si el precio está en otra moneda, "
        "asume EUR igualmente.\n\nTexto:\n"
        f"{text[:6000]}\n\n"
        "Schema:\n"
        "{\n"
        '  "name": "string",\n'
        '  "brand": "string",\n'
        '  "category": "skincare|fitness|hogar|tech|moda|otros",\n'
        '  "subcategory": "string",\n'
        '  "price_eur": number\n'
        "}"
    )
    try:
        result = generate_json(system_prompt, user_prompt)
        if isinstance(result, dict):
            for k in (
                "name", "brand", "category", "subcategory", "price_eur",
                "description",
            ):
                if k in result and result[k]:
                    out[k] = result[k]
    except Exception as e:
        logger.warning("[url_scraper.extract_from_text] Gemini falló: %s", e)
        out["warnings"].append(f"Gemini falló al analizar el texto: {e}")
    return out


# ---------------------------------------------------------------------------
# Gemini refinement
# ---------------------------------------------------------------------------
def _refine_with_gemini(
    partial: dict[str, Any], *, html: str
) -> dict[str, Any] | None:
    """Si tenemos texto pero faltan campos clave, pide a Gemini que extraiga
    name / brand / category / subcategory / price_eur de la descripción.

    Devuelve None si Gemini no está configurado o falla."""
    # Necesitamos AL MENOS algo de texto para que Gemini razone.
    text = partial.get("description") or partial.get("name") or ""
    if len(text) < 30:
        # Probamos a sacar texto visible del HTML
        try:
            soup_text = BeautifulSoup(html, "html.parser").get_text(
                separator=" ", strip=True
            )
            text = soup_text[:4000]  # cap
        except Exception:
            return None
    if len(text) < 30:
        return None

    try:
        from src.tiktok_shop.api.gemini import generate_json, is_configured
    except Exception:
        return None
    if not is_configured():
        return None

    system_prompt = (
        "Eres un asistente que extrae datos estructurados de productos a "
        "partir de texto en español. Devuelve SIEMPRE JSON estricto, sin "
        "explicación. Si un campo no se puede inferir, omítelo. "
        "Categorías válidas: skincare, fitness, hogar, tech, moda, otros. "
        "El precio devuélvelo SOLO como número (sin €, sin separadores de "
        "miles, decimal con punto)."
    )
    user_prompt = (
        "Extrae nombre, marca, categoría, subcategoría y precio en EUR del "
        "siguiente texto de un producto de TikTok Shop. Si el precio está "
        "en otra moneda, asume EUR igualmente.\n\nTexto:\n"
        f"{text[:3500]}\n\n"
        "Schema:\n"
        "{\n"
        '  "name": "string",\n'
        '  "brand": "string",\n'
        '  "category": "skincare|fitness|hogar|tech|moda|otros",\n'
        '  "subcategory": "string",\n'
        '  "price_eur": number\n'
        "}"
    )
    try:
        result = generate_json(system_prompt, user_prompt)
        if isinstance(result, dict):
            return result
    except Exception as e:
        logger.warning("[url_scraper] Gemini refinement falló: %s", e)
    return None
