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

# Palabras de razón social que NO identifican la marca: las lleva media
# industria. Sin quitarlas, "Freshly Cosmetics" casaba con "DONNA COSMETICS
# SERUM FACIAL DE FRUTAS" y se ataba la URL de otra marca.
_MARCA_GENERICA = {
    "cosmetics", "cosmetica", "beauty", "store", "shop", "official", "oficial",
    "espana", "spain", "group", "brand", "company", "sociedad", "limited",
    "iberia", "europe", "global", "team", "studio", "labs", "lab",
}

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


def keyword_sin_marca(titulo_completo: str, tienda: str = "", max_palabras: int = 3) -> str:
    """Frase del nombre SIN la marca, para el segundo intento.

    EchoTik busca por SUBCADENA, no por palabras: `wotsta` devuelve el producto
    exacto pero `wotsta silla para juegos asiento` devuelve 0, porque la ficha
    real dice "WOTSTA-silla para juegos, asiento" y con el guion y la coma la
    keyword deja de ser subcadena.

    Unas fichas pegan la marca al nombre ("BELLA AURORA Crema de Manos") y ahí
    gana `build_keyword`; otras la separan ("Freshly - …", "WOTSTA-silla") y
    entonces hay que buscar solo la frase. No se puede saber de antemano cuál
    de las dos usa el listado real, así que se prueban en ese orden.
    """
    marca = {p for p in _normaliza(tienda).split() if len(p) > 2}
    palabras = [
        w for w in build_keyword(titulo_completo, tienda, max_palabras=8).split()
        if w not in marca
    ]
    return " ".join(palabras[:max_palabras]).strip()


def _marca_distintiva(tienda: str) -> set[str]:
    """Palabras de la tienda que de verdad identifican la marca."""
    return {
        p for p in _normaliza(tienda).split()
        if len(p) > 3 and p not in _MARCA_GENERICA
    }


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
    marca = _marca_distintiva(tienda)
    if marca and not (marca & hallados):
        return 0.0

    return len(nucleo & hallados) / len(nucleo)


def score_ponderado(
    candidato: str, titulo_completo: str, tienda: str, catalogo: list[dict],
) -> float:
    """Parecido pesando las palabras por lo RARAS que son en el catálogo.

    Con todas las palabras valiendo igual, una "crema de manos" casaba con
    "Crema Anti-manchas de día" al 67%: comparten "crema" y "antimanchas", que
    son palabras que lleva medio catálogo de la marca, y se perdía la única
    que de verdad identifica el producto ("manos").

    Teniendo la lista de candidatos delante se puede medir: la palabra que
    aparece en 20 de 30 fichas no distingue nada; la que aparece en 2, sí.
    """
    nucleo = _nucleo(titulo_completo, tienda)
    if not nucleo:
        return 0.0
    hallados = _tokens(candidato)
    marca = _marca_distintiva(tienda)
    if marca and not (marca & hallados):
        return 0.0

    total = max(1, len(catalogo))
    pesos = {}
    for t in nucleo:
        veces = sum(1 for c in catalogo if t in _tokens(c.get("name", "")))
        pesos[t] = 1.0 / (1 + veces / total * 4)      # 1.0 rara → 0.2 ubicua
    suma = sum(pesos.values())
    acertado = sum(w for t, w in pesos.items() if t in hallados)
    return acertado / suma if suma else 0.0


def elegir_de_candidatos(
    candidatos: list[dict], titulo_completo: str, tienda: str,
) -> dict[str, Any] | None:
    """Elige de una lista YA descargada, sin gastar llamadas."""
    if not candidatos:
        return None

    def puntos(p):
        return score_ponderado(
            p.get("name", ""), titulo_completo, tienda, candidatos)

    mejor = max(candidatos, key=lambda p: (round(puntos(p), 3), -len(p.get("name") or "")))
    score = puntos(mejor)
    if score < MIN_SCORE or not mejor.get("product_id"):
        return None
    return {
        "product_id": mejor["product_id"],
        "product_url": mejor["tiktok_url"],
        "url_match_name": mejor.get("name", ""),
        "url_match_score": round(score, 3),
    }


def barrer_marca(
    tienda: str, *, region: str = "ES", paginas: int = 3,
    on_log: OnLog | None = None,
) -> list[dict]:
    """Baja el catálogo de una marca de una vez: `paginas` llamadas para todos
    sus productos de la carpeta, en vez de 1-2 por producto.

    Buscar el nombre exacto falla mucho (EchoTik busca por subcadena y las
    fichas del operador no coinciden literalmente con el listado), pero
    buscando la MARCA salen 30 productos y ahí sí está el que falta: el
    "SPLENDOR serum" no aparecía por nombre y sí en la barrida.
    """
    from src.tiktok_shop.api import echotik_cloud

    # En ORDEN, no alfabético: EchoTik busca por subcadena y "aurora bella"
    # devuelve 6 productos donde "bella aurora" devuelve 30.
    distintivas = _marca_distintiva(tienda)
    marca = " ".join(
        [w for w in _normaliza(tienda).split() if w in distintivas][:2]
    ) or tienda.strip()
    if not marca:
        return []
    if on_log:
        on_log(f"🔎 EchoTik marca {marca!r} ({paginas} llamadas para toda la marca)")
    res = echotik_cloud.search_products(marca, region=region, limit=paginas * 10)
    # Fichas repetidas: la API devuelve el mismo producto en varias páginas.
    unicos: dict[str, dict] = {}
    for p in res:
        unicos.setdefault(p.get("product_id") or p.get("name", ""), p)
    if on_log:
        on_log(f"  · {len(unicos)} productos distintos de la marca")
    return list(unicos.values())


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
        sin_marca = keyword_sin_marca(titulo_completo, tienda)
        if sin_marca and sin_marca != keyword:
            log(f"  · sin resultados → reintento sin marca: {sin_marca!r} (1 llamada más)")
            keyword = sin_marca
            resultados = echotik_cloud.search_products(sin_marca, region=region, limit=10)
    if not resultados:
        log("  · sin resultados")
        return None

    # Las ventas que devuelve EchoTik NO son fiables (el operador comprobó
    # productos con ventas reales que la API da a 0), así que no se usan ni
    # para desempatar ni para avisar. Manda el parecido y, a igualdad, el
    # nombre más corto: los títulos con menos relleno SEO suelen ser la ficha
    # principal del producto.
    def orden(p):
        return (
            round(match_score(p.get("name", ""), titulo_completo, tienda), 2),
            -len(p.get("name") or ""),
        )

    mejor = max(resultados, key=orden)
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


# ---------------------------------------------------------------------------
# El ID del producto, sacado del enlace corto
# ---------------------------------------------------------------------------
# Las fichas de la web del curso llegan como `vm.tiktok.com/ZN9k…`, que no dice
# nada del producto. Pero ese enlace redirige a
# `tiktok.com/view/product/<id>`, y ESE id es el que TikTok Studio acepta en el
# buscador de "Añade enlaces de productos" — sin él hay que bucear 139 páginas
# para encontrar el producto al publicar.
#
# Es una petición HTTP normal siguiendo el redirect: ni API, ni cuota, ni
# EchoTik. Se hace una vez y se guarda.
_ID_EN_URL = re.compile(r"/view/product/(\d{10,})")


def id_desde_url(url: str, *, timeout: float = 15.0) -> str:
    """El id de producto al que apunta ese enlace. Vacío si no se puede.

    Nunca lanza: sin id el producto sigue valiendo, solo que al publicar hay
    que buscarlo a mano.
    """
    limpia = (url or "").strip()
    if not limpia:
        return ""
    # Si ya viene la ficha larga, no hace falta pedir nada.
    directo = _ID_EN_URL.search(limpia)
    if directo:
        return directo.group(1)

    try:
        import requests

        r = requests.get(
            limpia, timeout=timeout, allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        final = str(r.url or "")
    except Exception:  # noqa: BLE001
        return ""
    m = _ID_EN_URL.search(final)
    return m.group(1) if m else ""


def ids_de_carpeta(
    productos: dict[str, dict], urls: dict[str, str], *, hilos: int = 8,
) -> dict[str, str]:
    """`{producto: id}` resolviendo en paralelo los que no lo tengan.

    En paralelo porque son diez enlaces y cada redirect tarda medio segundo: de
    uno en uno son cinco segundos de espera con el operador delante.
    """
    from concurrent.futures import ThreadPoolExecutor

    pendientes = {
        pid: u for pid, u in urls.items()
        if u and not (productos.get(pid) or {}).get("product_id")
    }
    if not pendientes:
        return {}
    with ThreadPoolExecutor(max_workers=max(1, hilos)) as pool:
        hallados = list(pool.map(id_desde_url, pendientes.values()))
    return {pid: i for pid, i in zip(pendientes, hallados) if i}
