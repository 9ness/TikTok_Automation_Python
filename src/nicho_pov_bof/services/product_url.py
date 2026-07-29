"""Averigua la URL de TikTok Shop de un producto a partir de su nombre.

El operador no tiene el enlace de los productos que le llegan por Drive: solo
la captura con el título y el nombre de la tienda. Se probaron nueve caminos
para sacar el ID (URL canónica, Gemini con búsqueda web, Apify, DuckDuckGo,
fastmoss, kalodata, capturas, la web y la API de TikTok) y ninguno funcionó;
el único que da el ID es EchoTik, buscando por keyword.

Formato de la ficha, verificado por el operador (2026-07-29):
    https://www.tiktok.com/view/product/<product_id>

**Cada búsqueda gasta una llamada del plan de EchoTik** (trial de 100), así
que:
  - el resultado se guarda en Redis y NO se vuelve a pedir (`url_at`);
  - solo se acepta un resultado si se parece de verdad al producto — atar una
    URL equivocada a un vídeo es peor que no tener URL;
  - `find_product_url` nunca reintenta ni pagina.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Callable

OnLog = Callable[[str], None]

# Por debajo de esto no se acepta el resultado: es otro producto.
MIN_SCORE = 0.34

# Ruido de los títulos de TikTok Shop: no distingue un producto de otro y
# ensucia tanto la keyword de búsqueda como la comparación.
_RELLENO = {
    "de", "del", "la", "el", "los", "las", "para", "con", "sin", "y", "o",
    "un", "una", "unos", "unas", "en", "por", "al", "a", "que", "su", "sus",
    "ideal", "perfecto", "regalo", "nuevo", "nueva", "gran", "alta", "set",
    "pack", "kit", "unidades", "uds", "cm", "mm", "ml", "kg", "incluye",
}


def _normaliza(texto: str) -> str:
    """Minúsculas, sin acentos y sin puntuación — para comparar y trocear."""
    plano = unicodedata.normalize("NFKD", texto)
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9ñ ]+", " ", plano.lower())


def _tokens(texto: str) -> set[str]:
    return {
        t for t in _normaliza(texto).split()
        if len(t) > 2 and t not in _RELLENO
    }


def build_keyword(titulo_completo: str, tienda: str = "", max_palabras: int = 7) -> str:
    """Keyword de búsqueda a partir del título largo de TikTok Shop.

    Los títulos vienen con toda la ficha técnica dentro ("MK Conjunto de
    Maletas de Viaje Elegantes: Carcasa Ligera de ABS, Cerradura Numérica,
    4 Ruedas…"). Mandar eso entero no encuentra nada, así que se trocea por
    los separadores fuertes y se cogen los primeros trozos con contenido.

    Quedarse con el PRIMER trozo a secas no vale: media catálogo empieza por
    la marca ("Freshly - Protector Solar…", "Freshly Cosmetics - Hyaluronic
    Energy Body Serum…") y la keyword salía "freshly", que devuelve el
    catálogo entero de la tienda. Los trozos que son solo marca se saltan.
    """
    marca = _tokens(tienda) | {t for t in _normaliza(tienda).split() if t}
    trozos = re.split(r"[:|,–—]|\s-\s", titulo_completo.strip())

    palabras: list[str] = []
    for trozo in trozos:
        utiles = [
            p for p in _normaliza(trozo).split()
            if len(p) > 2 and p not in _RELLENO
        ]
        if not utiles:
            continue
        # Trozo que es solo la marca: no distingue nada, al siguiente.
        if not palabras and all(p in marca for p in utiles):
            continue
        palabras.extend(utiles)
        if len(palabras) >= 4:
            break

    if not palabras:
        palabras = [p for p in _normaliza(titulo_completo).split() if len(p) > 2]
    keyword = " ".join(palabras[:max_palabras])

    # La marca solo se añade si la keyword se quedó pobre ("sillón gaming"):
    # con 3+ palabras propias, meterla estrecha la búsqueda sin necesidad.
    primera_marca = next(iter(_normaliza(tienda).split()), "")
    if primera_marca and primera_marca not in keyword and len(palabras) < 3:
        keyword = f"{primera_marca} {keyword}"
    return keyword.strip()


def match_score(candidato: str, titulo_completo: str, tienda: str = "") -> float:
    """Cuánto se parece el nombre encontrado al producto que buscamos (0-1).

    Es la proporción de palabras con contenido del producto que aparecen en
    el candidato. Encontrar la marca suma aparte: dos productos distintos de
    la misma tienda se parecen menos que el mismo producto escrito de otra
    forma, pero la marca es una señal fuerte de que no es un producto al azar.
    """
    buscados = _tokens(titulo_completo)
    if not buscados:
        return 0.0
    hallados = _tokens(candidato)
    solape = len(buscados & hallados) / len(buscados)

    marca = _tokens(tienda)
    if marca and marca & hallados:
        solape = min(1.0, solape + 0.15)
    return solape


def find_product_url(
    titulo_completo: str,
    tienda: str = "",
    *,
    region: str = "ES",
    on_log: OnLog | None = None,
) -> dict[str, Any] | None:
    """Busca el producto en EchoTik y devuelve su ID + URL, o None.

    GASTA UNA LLAMADA del plan. Devuelve None (sin reintentar) si no hay
    credenciales, si la cuota está agotada, si no hay resultados o si el
    mejor resultado no se parece lo bastante.
    """
    from src.tiktok_shop.api import echotik_cloud

    def log(msg: str) -> None:
        if on_log:
            on_log(msg)

    if not titulo_completo.strip():
        return None
    if not echotik_cloud.echotik_is_configured():
        log("⚠️ EchoTik no configurado (ECHOTIK_API_USER / ECHOTIK_API_PASSWORD).")
        return None
    if echotik_cloud.quota_exhausted():
        log(f"🚫 EchoTik sin cuota: {echotik_cloud.last_quota_error_msg()}")
        return None

    keyword = build_keyword(titulo_completo, tienda)
    log(f"🔎 EchoTik '{keyword}' (1 llamada)")
    # limit=10 = UNA página = UNA llamada. Subirlo pagina y multiplica el gasto.
    resultados = echotik_cloud.search_products(keyword, region=region, limit=10)
    if not resultados:
        log("  · sin resultados")
        return None

    mejor = max(
        resultados,
        key=lambda p: match_score(p.get("name", ""), titulo_completo, tienda),
    )
    score = match_score(mejor.get("name", ""), titulo_completo, tienda)
    if score < MIN_SCORE or not mejor.get("product_id"):
        log(f"  · descartado (parecido {score:.0%}): {mejor.get('name', '')[:60]}")
        return None

    log(f"  ✓ {score:.0%} · {mejor['name'][:60]}")
    return {
        "product_id": mejor["product_id"],
        "product_url": mejor["tiktok_url"],
        "url_match_name": mejor.get("name", ""),
        "url_match_score": round(score, 3),
        "keyword": keyword,
    }
