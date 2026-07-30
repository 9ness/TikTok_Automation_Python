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
# Fracción del núcleo del nombre que debe aparecer en el candidato. Con 0.34
# entraban productos distintos de la misma marca (una crema de manos frente a
# una crema antiedad comparten "crema" y poco más).
MIN_SCORE = 0.6

# Ruido de los títulos de TikTok Shop: no distingue un producto de otro y
# ensucia tanto la keyword de búsqueda como la comparación.
_RELLENO = {
    "de", "del", "la", "el", "los", "las", "para", "con", "sin", "y", "o",
    "un", "una", "unos", "unas", "en", "por", "al", "a", "que", "su", "sus",
    "ideal", "perfecto", "regalo", "nuevo", "nueva", "gran", "alta", "set",
    "pack", "kit", "unidades", "uds", "cm", "mm", "ml", "kg", "incluye",
}


def _normaliza(texto: str) -> str:
    """Minúsculas, sin acentos y sin puntuación — para comparar y trocear.

    """
    plano = unicodedata.normalize("NFKD", texto)
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    plano = plano.lower()
    # Los prefijos unidos por guion se PEGAN ("Anti-Manchas" -> "antimanchas",
    # que es como se llama el producto de verdad); el resto de guiones separan
    # ("WOTSTA-silla" -> "wotsta silla", que sí son dos palabras).
    plano = re.sub(r"\b(anti|multi|super|ultra|pre|post|sub|semi)-", r"\1", plano)
    return re.sub(r"[^a-z0-9ñ ]+", " ", plano)


def _tokens(texto: str) -> set[str]:
    return {
        t for t in _normaliza(texto).split()
        if len(t) > 2 and t not in _RELLENO
    }


def build_keyword(titulo_completo: str, tienda: str = "", max_palabras: int = 5) -> str:
    """Keyword de búsqueda: MARCA + las primeras palabras del nombre.

    La marca es imprescindible. Buscando "crema manos antimanchas" EchoTik
    devuelve 0 resultados; con "bella aurora crema de manos" devuelve los tres
    productos correctos. Antes solo se añadía si la keyword quedaba corta, y
    ahí se perdían casi todos.

    Cortar por el primer separador tampoco vale: media catálogo escribe
    "BELLA AURORA - Crema de Manos…" y el primer trozo es SOLO la marca. Se
    van acumulando trozos hasta juntar palabras que describan el producto.

    Las palabras funcionales ("de", "para") se dejan: el buscador las tolera y
    quitarlas rompe expresiones como "crema DE manos".
    """
    marca = [p for p in _normaliza(tienda).split() if len(p) > 2][:2]
    ruido = {"ml", "gr", "kg", "cm", "mm", "uds", "unidades", "spf"}

    propias: list[str] = []
    for trozo in re.split(r"[:|,]|\s-\s|\s–\s", titulo_completo):
        for w in _normaliza(trozo).split():
            if w.isdigit() or w in ruido or len(w) < 2:
                continue
            # No repetir la marca dentro de las palabras propias.
            if w in marca and not propias:
                continue
            propias.append(w)
        if len(propias) >= max_palabras:
            break

    partes = marca + [w for w in propias if w not in marca]
    return " ".join(partes[:max_palabras]).strip()


def keyword_corta(titulo_completo: str, tienda: str = "") -> str:
    """Segundo intento cuando la primera búsqueda no devuelve NADA: marca + 2
    palabras. Menos específica, más probabilidad de que el buscador acierte."""
    return build_keyword(titulo_completo, tienda, max_palabras=4)


def _nucleo(titulo_completo: str, tienda: str) -> set[str]:
    """Palabras que IDENTIFICAN el producto, sin la marca ni el relleno.

    Se toman del principio del nombre, no de toda la ficha: el resto es SEO
    ("Anti-edad, Despigmentante, Tratamiento Reparador Hidratante…") y lo
    comparten media docena de productos de la misma marca.
    """
    marca = {p for p in _normaliza(tienda).split() if len(p) > 2}
    palabras = [
        w for w in build_keyword(titulo_completo, tienda, max_palabras=6).split()
        if w not in marca and w not in _RELLENO and len(w) > 2
    ]
    return set(palabras)


def match_score(candidato: str, titulo_completo: str, tienda: str = "") -> float:
    """Cuánto se parece el nombre encontrado al producto buscado (0-1).

    Se mide sobre el NÚCLEO del nombre. Compararlo contra la ficha entera no
    distinguía productos de la misma marca: para una crema de manos, el
    "B7 Crema Antimanchas y Antiedad" sacaba 51% y la crema de manos correcta
    60% — nueve puntos, indistinguible. Sobre el núcleo ("crema manos") el
    correcto saca 100% y el otro 50%.
    """
    nucleo = _nucleo(titulo_completo, tienda)
    if not nucleo:
        return 0.0
    hallados = _tokens(candidato)

    # La MARCA es condición, no puntos: "Neutrogena Crema de Manos" comparte el
    # núcleo entero con una crema de manos de Bella Aurora y no es el producto.
    marca = {p for p in _normaliza(tienda).split() if len(p) > 3}
    if marca and not (marca & hallados):
        return 0.0

    return len(nucleo & hallados) / len(nucleo)


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
        # Segundo intento con menos palabras: la mayoría de los fallos eran
        # keywords demasiado específicas, no productos ausentes del catálogo.
        corta = keyword_corta(titulo_completo, tienda)
        if corta and corta != keyword:
            log(f"  · sin resultados → reintento con {corta!r} (1 llamada más)")
            keyword = corta
            resultados = echotik_cloud.search_products(corta, region=region, limit=10)
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
