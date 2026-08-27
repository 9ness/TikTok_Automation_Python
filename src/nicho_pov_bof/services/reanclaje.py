"""Que renombrar las fotos en el Drive del curso NO nos rompa el trabajo.

El identificador de un producto es el NÚMERO de sus fotos (`3.png` + `3(1).png`
→ producto "3"). Es lo que hace que todo encaje sin código especial… hasta que
el admin del Drive reordena una carpeta: lo que era `IMG_0245.jpg` pasa a
llamarse `4.png` y, para nosotros, ese producto desaparece y nace otro vacío.
Con él se quedan colgados sus textos, su categoría, sus mensajes, su guion y
las fotos ya generadas y quemadas.

La pieza que no cambia es el **file ID de Google**: renombrar un fichero no lo
toca. Así que de cada producto se guarda el id de sus dos fotos (`foto_ids`) y,
cuando la carpeta se relee, se comparan: si los ids de un producto guardado
aparecen ahora bajo otro número, se MUEVE todo lo suyo a ese número.

Se ejecuta al listar la carpeta, que es cuando se nota el cambio, y no hace
nada si no hay nada que mover.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Iterable

log = logging.getLogger("api")

# Los nichos que guardan cosas por (fuente, carpeta, producto). El escaparate y
# los vendidos NO están aquí: el escaparate va por `tienda|titulo` y los
# vendidos se mueven aparte (tienen su propio documento por referencia).
_DOCS = (
    ("src.nicho_pov_bof.repos.redis_base", "get_nicho_pov_bof_redis"),
    ("src.nicho_pov_bof_largo.repos.redis_base", "get_nicho_pov_bof_largo_redis"),
    ("src.nicho_bof_cine.repos.redis_base", "get_nicho_bof_cine_redis"),
    ("src.nicho_carruseles.repos.redis_base", "get_nicho_carruseles_redis"),
)
# Los usuarios con documento propio. `ness` va en el compartido.
_USUARIOS = ("", "ana", "mauro")


def ids_de(par: dict) -> set[str]:
    """Los file IDs de las fotos de un producto emparejado."""
    out = set()
    for clave in ("clean", "titled"):
        foto = par.get(clave) or {}
        if foto.get("id"):
            out.add(str(foto["id"]))
    for extra in par.get("extras") or []:
        if extra.get("id"):
            out.add(str(extra["id"]))
    return out


def sincronizar(
    source: str, folder: str, pares: Iterable[dict], usuario: str = "",
) -> dict[str, str]:
    """Reengancha lo guardado si el curso ha renumerado la carpeta.

    Devuelve el mapa viejo→nuevo de lo que se ha movido (vacío si no había
    nada). Nunca lanza: esto va en mitad de un listado y un fallo aquí no puede
    dejar al operador sin pantalla.
    """
    try:
        return _sincronizar(source, folder, list(pares), usuario)
    except Exception as e:  # noqa: BLE001
        log.warning("reanclaje de %s/%s falló: %s", source, folder, e)
        return {}


def _sincronizar(
    source: str, folder: str, pares: list[dict], usuario: str = "",
) -> dict[str, str]:
    from src.nicho_pov_bof.repos import product_repo as pov

    doc = pov.load_folder(source, folder)
    guardados = doc.get("productos") or {}
    if not guardados or not pares:
        return {}

    actuales = {str(p["producto"]): ids_de(p) for p in pares}

    # Quién es quién: para cada producto guardado, en qué número están HOY sus
    # fotos. Basta con que coincida UN id — el otro puede haberse sustituido.
    mapa: dict[str, str] = {}
    for pid, prod in guardados.items():
        ids = {str(x) for x in (prod.get("foto_ids") or []) if x}
        if not ids or str(pid) in actuales and ids & actuales[str(pid)]:
            continue
        destino = next((n for n, suyos in actuales.items() if ids & suyos), "")
        if destino and destino != str(pid):
            mapa[str(pid)] = destino

    if mapa:
        # Si dos productos viejos apuntan al mismo número nuevo no se adivina:
        # se deja como está y que lo mire una persona.
        repes = {v for v in mapa.values() if list(mapa.values()).count(v) > 1}
        for k in [k for k, v in mapa.items() if v in repes]:
            mapa.pop(k, None)
    if mapa:
        log.info("reanclaje %s/%s: %s", source, folder, mapa)
        mover_productos(source, folder, mapa)
        doc = pov.load_folder(source, folder)  # lo movido cambia el documento

    _guardar_ids(source, folder, actuales, doc)
    return mapa


def _guardar_ids(
    source: str, folder: str, actuales: dict[str, set[str]], doc: dict | None = None,
) -> None:
    """Apunta en cada producto los ids de sus fotos (solo si han cambiado).

    Se reutiliza el documento que ya tiene quien llama: esto corre en CADA
    listado de carpeta y volver a leerlo era otra ida y vuelta a Redis.
    """
    from src.nicho_pov_bof.repos import product_repo as pov

    doc = doc if doc is not None else pov.load_folder(source, folder)
    productos = doc.get("productos") or {}
    if not productos:
        return
    cambio = False
    for pid, ids in actuales.items():
        prod = productos.get(pid)
        if prod is None:
            continue
        nuevos = sorted(ids)
        if sorted(str(x) for x in (prod.get("foto_ids") or [])) != nuevos:
            prod["foto_ids"] = nuevos
            cambio = True
    if cambio:
        doc["productos"] = productos
        pov.save_folder(source, folder, doc)


def mover_productos(
    source: str, folder: str, mapa: dict[str, str], *, validos: set[str] | None = None,
) -> None:
    """Mueve TODO lo que guardan los nichos de esos productos a su número nuevo.

    `validos` (opcional) son los productos que siguen existiendo: lo de
    cualquier otro se tira. Se usa al renumerar "Mis productos", donde el hueco
    lo deja un borrado.

    Cada paso va en su try: haber movido la mitad es mejor que no mover nada, y
    lo que falle se puede repetir (es idempotente).
    """
    if not mapa:
        return

    def _rehacer(productos: dict) -> dict:
        salida = {}
        for pid, valor in productos.items():
            if validos is not None and str(pid) not in validos:
                continue
            salida[mapa.get(str(pid), str(pid))] = valor
        return salida

    import importlib

    claves = {f"folder:{source}:{folder}"}
    for u in _USUARIOS:
        if u:
            claves.add(f"folder:{source}:{folder}:u:{u}")
        claves.add(f"folder:{source}:{folder}:u:{u or 'ness'}")
    for modulo, getter in _DOCS:
        try:
            r = getattr(importlib.import_module(modulo), getter)()
            if not r.is_available():
                continue
            for clave in claves:
                doc = r.get_json(clave)
                if not doc or not doc.get("productos"):
                    continue
                doc["productos"] = _rehacer(doc["productos"])
                r.set_json(clave, doc)
        except Exception as e:  # noqa: BLE001
            log.warning("reanclaje: %s no se pudo mover (%s)", modulo, e)

    # Creativos Pro guarda `{producto: hora}` de lo ya publicado.
    try:
        from src.nicho_creativos.repos.redis_base import get_nicho_creativos_redis

        rc = get_nicho_creativos_redis()
        if rc.is_available():
            for u in _USUARIOS:
                clave = f"subidos:{source}:{folder}" + (f":{u}" if u and u != "ness" else "")
                doc = rc.get_json(clave)
                if doc:
                    rc.set_json(clave, _rehacer(doc))
    except Exception as e:  # noqa: BLE001
        log.warning("reanclaje: creativos no se pudo mover (%s)", e)

    # Carruseles: lo mismo con lo que marca como subido.
    try:
        from src.nicho_carruseles.repos import subidos_repo as carr_subidos

        carr_subidos.mover(source, folder, mapa)
    except Exception:  # noqa: BLE001
        pass

    # Las ventas viven en un documento por referencia `fuente|carpeta|numero`.
    try:
        from src.nicho_pov_bof.repos import product_repo as pov

        for viejo, nuevo in mapa.items():
            pov.mover_venta(source, folder, viejo, nuevo, usuario)
    except Exception as e:  # noqa: BLE001
        log.warning("reanclaje: ventas no se pudieron mover (%s)", e)

    mover_fotos(source, folder, mapa)


def _slug(texto: str) -> str:
    plano = unicodedata.normalize("NFKD", str(texto or "").lower())
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", plano).strip("_")


def mover_fotos(source: str, folder: str, mapa: dict[str, str]) -> None:
    """Renombra las fotos de Carruseles: el número va en el nombre del fichero.

    Son las generadas en Flow y las que ya llevan el texto quemado — lo que más
    cuesta rehacer de todo esto.
    """
    try:
        from src.nicho_carruseles import config as carr_config
        from src.nicho_carruseles.services import fotos as carr_fotos
    except Exception:  # noqa: BLE001
        return
    for usuario in ("ness", "ana", "mauro"):
        for tipo in carr_config.SUBCARPETAS:
            try:
                base = carr_config.carpeta_de(tipo, usuario)
            except Exception:  # noqa: BLE001
                continue
            for viejo, nuevo in mapa.items():
                origen_pref = f"{_slug(source)}__{_slug(folder)}__{_slug(viejo)}"
                destino_pref = f"{_slug(source)}__{_slug(folder)}__{_slug(nuevo)}"
                for f in list(base.glob(f"{origen_pref}.*")):
                    try:
                        f.rename(base / f"{destino_pref}{f.suffix}")
                    except OSError:
                        continue
        try:
            carr_fotos.invalidar()
        except Exception:  # noqa: BLE001
            pass


def mover_entre_carpetas(
    source: str, movimientos: list[tuple[str, str, str, str]],
) -> int:
    """Mueve productos de una carpeta a OTRA, con todo lo que guardan.

    `movimientos` son `(carpeta_origen, producto_origen, carpeta_destino,
    producto_destino)`, YA en un orden en el que ningún destino esté ocupado
    (al compactar, el destino de cada producto siempre va por delante del
    origen, así que basta recorrerlos en orden).

    El hermano de `mover_productos`, que solo sabe renumerar dentro de una
    misma carpeta. Aquí hay que sacar la entrada de un documento y meterla en
    otro, y eso por cada nicho y cada usuario: un producto lleva sus textos en
    el compartido, su guion en el del Largo y su "subido" en el de quien lo
    subió.

    Devuelve cuántas entradas se movieron. Idempotente: repetirlo no duplica
    nada, porque lo movido ya no está en el origen.
    """
    if not movimientos:
        return 0

    import importlib

    movidas = 0
    for modulo, getter in _DOCS:
        try:
            r = getattr(importlib.import_module(modulo), getter)()
            if not r.is_available():
                continue
        except Exception:  # noqa: BLE001 — un nicho caído no para a los demás
            continue

        for sufijo in {"", *(f":u:{u or 'ness'}" for u in _USUARIOS)}:
            # Todo el trasiego de un documento se hace en memoria y se escribe
            # UNA vez: entrada a entrada serían cientos de idas a Upstash.
            cache: dict[str, dict] = {}
            tocados: set[str] = set()

            def _doc(carpeta: str) -> dict:
                clave = f"folder:{source}:{carpeta}{sufijo}"
                if clave not in cache:
                    cache[clave] = r.get_json(clave) or {}
                return cache[clave]

            for c_ori, p_ori, c_des, p_des in movimientos:
                origen = _doc(c_ori)
                prods = origen.get("productos") or {}
                entrada = prods.pop(str(p_ori), None)
                if entrada is None:
                    continue
                destino = _doc(c_des)
                destino.setdefault("productos", {})[str(p_des)] = entrada
                tocados.add(c_ori)
                tocados.add(c_des)
                movidas += 1

            for carpeta in tocados:
                clave = f"folder:{source}:{carpeta}{sufijo}"
                doc = cache.get(clave)
                if doc is not None:
                    # `ids_vigentes` era de la composición vieja: se tira para
                    # que se vuelva a escribir al listar la carpeta.
                    doc.pop("ids_vigentes", None)
                    try:
                        r.set_json(clave, doc)
                    except Exception:  # noqa: BLE001
                        continue
    return movidas
