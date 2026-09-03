"""Estado de cada prenda en Redis (prefijo `nicho_ropa:`).

Mucho más simple que el del Nicho POV BOF: aquí hay UNA sola carpeta, así que
no hay progreso por carpeta ni documentos por usuario. Un único documento con
todos los productos dentro.
"""

from __future__ import annotations

import os
import random
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from src.nicho_ropa.repos.redis_base import get_nicho_ropa_redis

def _key(carpeta: str) -> str:
    return f"productos:{carpeta}"


def _lock(carpeta: str) -> str:
    return f"lock:productos:{carpeta}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _require_redis():
    r = get_nicho_ropa_redis()
    if not r.is_available():
        raise RuntimeError(
            "Redis (Upstash) no está configurado — no se pueden guardar los "
            "textos de las prendas."
        )
    return r


@contextmanager
def _cerrojo(carpeta: str, espera_s: float = 10.0):
    """Mismo cerrojo que en los otros repos: se guarda el documento ENTERO y
    la API corre con varios workers, así que sin él se pierden escrituras."""
    r = get_nicho_ropa_redis()
    mio = False
    if r.is_available():
        limite = time.monotonic() + espera_s
        while time.monotonic() < limite:
            if r.set_nx(_lock(carpeta), str(os.getpid()), ttl_s=30):
                mio = True
                break
            time.sleep(0.15 + random.random() * 0.2)
    try:
        yield mio
    finally:
        if mio:
            r.delete(_lock(carpeta))


def load(carpeta: str) -> dict:
    r = get_nicho_ropa_redis()
    if not r.is_available():
        return {}
    return r.get_json(_key(carpeta)) or {}


def get_product(carpeta: str, producto: str) -> dict:
    return (load(carpeta).get("productos") or {}).get(str(producto)) or {}


def save_extracted_texts(carpeta: str, textos: dict[str, dict]) -> dict:
    """Guarda lo que devolvió Gemini, sin pisar el estado de los vídeos."""
    with _cerrojo(carpeta):
        r = _require_redis()
        doc = r.get_json(_key(carpeta)) or {}
        productos = doc.setdefault("productos", {})
        # La marca del escaparate se guarda por `tienda|titulo`: si el título
        # cambia al releer la ficha, hay que mudarla o el producto vuelve a
        # salir sin marcar (pasó con cientos a la vez).
        mudanzas: list[tuple[str, str, str, str]] = []
        for pid, campos in textos.items():
            prod = productos.setdefault(str(pid), {})
            antes = (prod.get("tienda", "") or "", prod.get("titulo", "") or "")
            prod.update(campos)
            prod["textos_at"] = _now()
            despues = (prod.get("tienda", "") or "", prod.get("titulo", "") or "")
            if antes != despues and antes[1]:
                mudanzas.append((*antes, *despues))
        doc["textos_extraidos"] = True
        doc["updated_at"] = _now()
        r.set_json(_key(carpeta), doc)
    from src.nicho_pov_bof.repos import product_repo as pov_repo

    pov_repo.mudar_escaparate(mudanzas)
    return doc


def update_product(carpeta: str, producto: str, **campos) -> dict:
    """Parche parcial. Ignora los campos que vengan `None`."""
    with _cerrojo(carpeta):
        r = _require_redis()
        doc = r.get_json(_key(carpeta)) or {}
        productos = doc.setdefault("productos", {})
        prod = productos.setdefault(str(producto), {})
        prod.update({k: v for k, v in campos.items() if v is not None})
        prod["updated_at"] = _now()
        r.set_json(_key(carpeta), doc)
        return prod


def quitar_campos(carpeta: str, producto: str, *campos: str) -> dict:
    """Borra campos del producto. `update_product` no sirve: ignora los `None`.

    Hace falta para volver a "lo que diga la ficha" tras haber corregido algo
    a mano — guardar `False` no es lo mismo que no haber opinado.
    """
    with _cerrojo(carpeta):
        r = _require_redis()
        doc = r.get_json(_key(carpeta)) or {}
        prod = (doc.get("productos") or {}).get(str(producto))
        if not prod:
            return {}
        for campo in campos:
            prod.pop(campo, None)
        prod["updated_at"] = _now()
        r.set_json(_key(carpeta), doc)
        return prod


def importar_urls(filas: list[dict], carpetas_reales: list[str]) -> dict:
    """Guarda de golpe las fichas copiadas del DOM de la web del curso.

    Es el gemelo de `nicho_pov_bof.product_repo.importar_urls` y reusa sus
    normalizadores: el pegote sale de la MISMA página y trae los mismos
    `Carpeta 7` / `Producto 3`. Lo único distinto es que aquí la carpeta lleva
    el sexo delante (`mujer_web__Carpeta 7`), así que el emparejado se hace
    contra las carpetas que existen de ese sexo.

    La ficha va al producto y, cuando ya tiene textos, también al índice global
    de fichas —que es de TODOS los nichos, no del POV BOF—, para que el mismo
    producto salga enlazado donde sea que aparezca.
    """
    from src.nicho_pov_bof.repos import product_repo as pov_repo

    # El pegote dice "Carpeta 7" y aquí la carpeta se llama
    # "mujer_web__Carpeta 7": se casa por la PARTE de la carpeta, no por el
    # slug entero, o no coincidiría ninguna.
    from src.nicho_ropa import config as ropa_config

    reales = {}
    for slug in carpetas_reales:
        _, nombre = ropa_config.partes_web(slug)
        reales[pov_repo._llana(nombre or slug)] = slug

    por_carpeta: dict[str, dict[str, str]] = {}
    agotados: dict[str, set[str]] = {}
    con_stock: dict[str, set[str]] = {}
    sin_carpeta: set[str] = set()
    descartadas: list[str] = []

    for fila in filas:
        pegada = pov_repo._carpeta_pegada(str(fila.get("carpeta") or ""))
        producto = pov_repo._numero_pegado(str(fila.get("producto") or ""))
        url = str(fila.get("url") or "").strip()
        if not pegada or not producto:
            continue
        carpeta = reales.get(pov_repo._llana(pegada), "")
        if not carpeta:
            sin_carpeta.add(pegada)
            continue
        if not url:
            if fila.get("sin_stock"):
                agotados.setdefault(carpeta, set()).add(producto)
            elif "sin_stock" in fila:
                con_stock.setdefault(carpeta, set()).add(producto)
            continue
        if not pov_repo._es_ficha_tiktok(url):
            descartadas.append(f"{pegada} · {producto}: {url[:60]}")
            continue
        por_carpeta.setdefault(carpeta, {})[producto] = url

    # El ID de TikTok, al guardar (ver el gemelo del POV BOF): es lo que se
    # pega en TikTok Studio para enlazar el producto sin buscarlo a mano.
    from src.nicho_pov_bof.services import product_url as _url_svc

    todas = [u for urls in por_carpeta.values() for u in urls.values()]
    ids: dict[str, str] = {}
    if todas:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=16) as pool:
            ids = {
                u: i for u, i in zip(todas, pool.map(_url_svc.id_desde_url, todas)) if i
            }

    guardados = agotados_escritos = en_indice = con_id = 0
    tocadas = set(por_carpeta) | set(agotados) | set(con_stock)
    indice = {}
    if tocadas:
        r = _require_redis()
        indice = r.get_json(pov_repo._URLS_INDEX) or {}

    for carpeta in sorted(tocadas):
        with _cerrojo(carpeta):
            r = _require_redis()
            doc = r.get_json(_key(carpeta)) or {}
            productos = doc.setdefault("productos", {})
            for producto in agotados.get(carpeta, set()):
                prod = productos.setdefault(producto, {})
                if not prod.get("sin_stock"):
                    prod["sin_stock"] = True
                    prod["updated_at"] = _now()
                agotados_escritos += 1
            for producto in con_stock.get(carpeta, set()):
                prod = productos.get(producto)
                if prod and prod.get("sin_stock"):
                    prod["sin_stock"] = False
                    prod["updated_at"] = _now()
            for producto, url in por_carpeta.get(carpeta, {}).items():
                prod = productos.setdefault(producto, {})
                if prod.get("product_url") != url or prod.get("sin_stock"):
                    prod["product_url"] = url
                    prod["sin_stock"] = False
                    prod["updated_at"] = _now()
                if ids.get(url):
                    prod["product_id"] = ids[url]
                    con_id += 1
                guardados += 1
                claves = pov_repo.claves_escaparate(prod)
                if claves:
                    for vieja in {
                        c for cl in claves if (c := pov_repo.casa_clave(cl, indice))
                    }:
                        indice.pop(vieja, None)
                    indice[claves[0]] = url
                    en_indice += 1
            r.set_json(_key(carpeta), doc)

    if tocadas:
        _require_redis().set_json(pov_repo._URLS_INDEX, indice)
        pov_repo._olvidar("urls")

    return {
        "carpetas": len(tocadas),
        "guardados": guardados,
        "con_id": con_id,
        "agotados": agotados_escritos,
        "en_indice": en_indice,
        "sin_carpeta": sorted(sin_carpeta),
        "descartadas": descartadas,
    }
