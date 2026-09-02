"""Estado por producto: textos extraídos + Subido / Vendió.

Un documento por CARPETA de productos (no uno por producto): una carpeta son
10 productos y siempre se consultan juntos, así que agruparlos evita 10
lecturas a Upstash cada vez que se abre la pantalla. Mismo criterio que
`month_plan_repo` del calendario, que agrupa por mes.

Key: `nicho_pov_bof:folder:<source>:<carpeta>`
"""

from __future__ import annotations

from datetime import datetime, timezone

import os
import random
import re
import time
import unicodedata
from contextlib import contextmanager

from src.nicho_pov_bof import config
from src.nicho_pov_bof.repos.redis_base import get_nicho_pov_bof_redis


# Lo que es de CADA UNO y no se comparte. Todo lo demás (título, tienda,
# caption, emojis, enlace de la ficha) es un dato objetivo del producto: sale
# de la foto de Drive, cuesta llamadas de Gemini y de EchoTik conseguirlo, y
# no cambia según quién lo mire. Compartirlo evita gastar la cuota tres veces
# en el mismo producto.
CAMPOS_PRIVADOS = frozenset({
    "en_escaparate", "uploaded", "sold", "video_path", "video_listo_at",
    # Cuándo se marcó como subido. Es del usuario, como el propio `uploaded`.
    "uploaded_at",
    # Vídeo de plazos: los dos clips brutos y la voz que le tocó. Cada operador
    # sube SUS clips del mismo producto, así que si esto viviera en el documento
    # compartido el clip de uno dispararía el montaje del otro.
    "clip1_path", "clip2_path", "guion_plazos", "voz_label", "voz_sexo",
    # Qué mano detectó la IA en el vídeo de ESTE usuario y con cuántos votos.
    "mano_detectada", "mano_votos",
})


def _key(source: str, folder: str) -> str:
    """Documento COMPARTIDO de la carpeta (textos y enlaces).

    La fuente se canoniza: leer una carpeta desde la copia de seguridad es leer
    LA MISMA carpeta del curso, así que textos y progreso son los mismos.
    """
    return f"folder:{config.fuente_canonica(source)}:{folder}"


def _key_privado(source: str, folder: str, usuario: str) -> str:
    """Documento PRIVADO de un usuario para esa carpeta.

    `ness` se queda en el documento compartido: es donde está su histórico y
    moverlo sería reescribir meses de trabajo sin ganar nada.
    """
    return f"folder:{config.fuente_canonica(source)}:{folder}:u:{usuario}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _require_redis():
    r = get_nicho_pov_bof_redis()
    if not r.is_available():
        raise RuntimeError(
            "Redis (Upstash) no está configurado — no se puede guardar el "
            "estado del Nicho POV BOF."
        )
    return r


def _es_compartido(usuario: str) -> bool:
    """`ness` escribe en el documento de siempre; el resto en el suyo."""
    return not usuario or usuario == "ness"


def load_folder_para(source: str, folder: str, usuario: str = "") -> dict:
    """Carpeta vista por `usuario`: lo compartido + lo suyo por encima."""
    base = load_folder(source, folder)
    if _es_compartido(usuario):
        return base
    privado = get_nicho_pov_bof_redis().get_json(
        _key_privado(source, folder, usuario)
    ) or {}
    productos = base.setdefault("productos", {})
    # Lo privado de OTRO no debe verse: se quitan esos campos de la base y se
    # ponen los del usuario que mira.
    for pid, prod in productos.items():
        for campo in CAMPOS_PRIVADOS:
            prod.pop(campo, None)
        prod.update((privado.get("productos") or {}).get(pid, {}))
    return base


def load_folder(source: str, folder: str) -> dict:
    """Estado de una carpeta. `{}` si aún no se ha guardado nada."""
    r = get_nicho_pov_bof_redis()
    if not r.is_available():
        return {}
    return r.get_json(_key(source, folder)) or {}


def load_folders(entradas: list[tuple[str, str]]) -> list[dict]:
    """Varias carpetas de una tacada, en el mismo orden que `entradas`.

    Con Upstash REST, N lecturas sueltas son N latencias seguidas: barrer las
    35 carpetas de una fuente para cruzar sus textos costaba segundos. Esto lo
    deja en una llamada (mismo criterio que `buscar_productos`).
    """
    if not entradas:
        return []
    r = get_nicho_pov_bof_redis()
    if not r.is_available():
        return [{} for _ in entradas]
    docs = r.mget_json([_key(s, f) for s, f in entradas])
    return [doc if isinstance(doc, dict) else {} for doc in docs]


def save_folder(source: str, folder: str, data: dict) -> None:
    data["updated_at"] = _now()
    _require_redis().set_json(_key(source, folder), data)


def get_product(
    source: str, folder: str, producto: str, usuario: str = ""
) -> dict:
    return (
        load_folder_para(source, folder, usuario).get("productos") or {}
    ).get(producto, {})


@contextmanager
def _cerrojo_carpeta(source: str, folder: str, espera_s: float = 12.0):
    """Cerrojo por carpeta mientras se lee-modifica-escribe su documento.

    Hace falta de verdad: la cola corre hasta CUATRO trabajos a la vez y cada
    uno guarda el documento ENTERO de la carpeta. Cuando varios vídeos del
    mismo lote terminaban a la vez se pisaban y ganaba el último — de nueve
    vídeos montados solo se guardaron seis, y el "Subido" se quedaba sin
    marcar por lo mismo.

    Si no se consigue el cerrojo se sigue igualmente: es mejor arriesgarse a
    perder una escritura que dejar el vídeo sin registrar.
    """
    r = get_nicho_pov_bof_redis()
    clave = f"lock:folder:{source}:{folder}"
    mio = False
    if r.is_available():
        limite = time.monotonic() + espera_s
        while time.monotonic() < limite:
            if r.set_nx(clave, str(os.getpid()), ttl_s=30):
                mio = True
                break
            time.sleep(0.15 + random.random() * 0.2)
    try:
        yield mio
    finally:
        if mio:
            r.delete(clave)


def update_product(
    source: str, folder: str, producto: str, usuario: str = "", **fields
) -> dict:
    """Parche parcial sobre un producto. Devuelve el producto ya actualizado.

    Reparte los campos: lo privado (`CAMPOS_PRIVADOS`) va al documento del
    usuario, el resto al compartido. Todo dentro del cerrojo de carpeta, que
    es lo que evita que dos trabajos simultáneos se pisen.
    """
    # La hora de subida se sella aquí y no la manda el caller: es lo que deja
    # comprobar de un vistazo si un producto repetido se marcó bien (si la hora
    # cambia, el toque llegó).
    if fields.get("uploaded") is True:
        fields.setdefault("uploaded_at", time.time())
    elif fields.get("uploaded") is False:
        fields["uploaded_at"] = 0

    privados = {k: v for k, v in fields.items() if k in CAMPOS_PRIVADOS}
    comunes = {k: v for k, v in fields.items() if k not in CAMPOS_PRIVADOS}

    with _cerrojo_carpeta(source, folder):
        prod = {}
        if comunes:
            prod = _update_product_sin_cerrojo(source, folder, producto, **comunes)
        if not privados:
            return prod or get_product(source, folder, producto, usuario)
        if _es_compartido(usuario):
            return _update_product_sin_cerrojo(
                source, folder, producto, **privados
            )
        clave = _key_privado(source, folder, usuario)
        r = _require_redis()
        doc = r.get_json(clave) or {}
        productos = doc.setdefault("productos", {})
        mio = productos.setdefault(producto, {})
        mio.update({k: v for k, v in privados.items() if v is not None})
        if mio.get("sold"):
            mio["uploaded"] = True
        mio["updated_at"] = _now()
        r.set_json(clave, doc)
        return {**prod, **mio}


# Lo que GENERA la app para un producto, frente a lo que se LEE de sus fotos.
# Al limpiar se va esto y se queda lo otro: los textos son del producto (y
# costaron una llamada a Gemini), pero el guion, la voz y el vídeo son de la
# tanda que se hizo — y cuando un número se reutiliza, son de otro producto.
CAMPOS_GENERADOS = frozenset({
    "guion_producto", "subliminal_producto",
    "guion_producto_plazos", "guion_producto_envio",
    "guion_plazos", "modo_plazos",
    "video_path", "video_listo_at",
    "clip1_path", "clip2_path",
    "voz_label", "voz_sexo", "mano_detectada", "mano_votos",
    "uploaded", "uploaded_at", "sold",
})


def limpiar_generado(
    source: str, folder: str, producto: str, usuario: str = "",
) -> list[str]:
    """Deja el producto como recién subido: fuera el guion, la voz, los clips,
    el vídeo y las marcas de subido/vendido. Los textos NO se tocan.

    Existe porque el número es la identidad dentro de la carpeta y se
    reutiliza: un producto podía nacer con el guion y el vídeo del que ocupaba
    antes ese número. Borrar y volver a subir las fotos también lo arregla,
    pero esto no obliga a tenerlas a mano.

    Devuelve los campos que había que borrar.
    """
    borrados: list[str] = []
    with _cerrojo_carpeta(source, folder):
        data = load_folder(source, folder)
        prod = (data.get("productos") or {}).get(producto)
        if prod:
            for campo in list(prod):
                if campo in CAMPOS_GENERADOS:
                    prod.pop(campo, None)
                    borrados.append(campo)
            prod["updated_at"] = _now()
            save_folder(source, folder, data)

        if not _es_compartido(usuario):
            r = _require_redis()
            clave = _key_privado(source, folder, usuario)
            doc = r.get_json(clave) or {}
            mio = (doc.get("productos") or {}).get(producto)
            if mio:
                for campo in list(mio):
                    if campo in CAMPOS_GENERADOS:
                        mio.pop(campo, None)
                        borrados.append(campo)
                r.set_json(clave, doc)

    # La venta vive en su propio documento: sin esto el producto seguiría en
    # el ranking de vendidos aunque la tarjeta ya no lo marque.
    try:
        mover_venta(source, folder, producto, "", usuario)
    except Exception:  # noqa: BLE001 — Redis caído no debe tumbar la limpieza
        pass
    return sorted(set(borrados))


def _update_product_sin_cerrojo(
    source: str, folder: str, producto: str, **fields
) -> dict:
    data = load_folder(source, folder)
    productos = data.setdefault("productos", {})
    prod = productos.setdefault(producto, {})
    prod.update({k: v for k, v in fields.items() if v is not None})

    # Marcar "vendió" implica que se subió: el estado contrario es imposible
    # y confundiría los recuentos.
    if prod.get("sold"):
        prod["uploaded"] = True

    prod["updated_at"] = _now()
    save_folder(source, folder, data)
    return prod


def save_extracted_texts(source: str, folder: str, textos: dict[str, dict]) -> None:
    """Guarda de golpe los textos de toda la carpeta (título, tienda, caption…).

    No pisa `uploaded`/`sold`: el operador puede re-extraer textos sin perder
    el progreso de subida.

    Y ARRASTRA la marca del escaparate. La clave del índice es `tienda|titulo`,
    así que al releer la ficha con otras palabras la marca se quedaba huérfana
    y el producto volvía a salir sin marcar: se perdieron cientos de una tacada
    al repasar el catálogo. Aquí se mueve la marca del título viejo al nuevo.
    """
    data = load_folder(source, folder)
    productos = data.setdefault("productos", {})
    mudanzas: list[tuple[str, str, str, str]] = []
    for prod_id, campos in textos.items():
        prod = productos.setdefault(prod_id, {})
        antes = (prod.get("tienda", ""), prod.get("titulo", ""))
        prod.update(campos)
        prod["textos_at"] = _now()
        despues = (prod.get("tienda", ""), prod.get("titulo", ""))
        if antes != despues and clave_escaparate(*antes):
            mudanzas.append((*antes, *despues))
    data["textos_extraidos"] = True
    save_folder(source, folder, data)
    mudar_escaparate(mudanzas)
    if source in FUENTES_DRIVE:
        _sumar_titulos_drive({
            c for prod in productos.values() for c in claves_escaparate(prod)
        })


def mudar_escaparate(
    mudanzas: list[tuple[str, str, str, str]], *, usuario: str | None = None,
) -> None:
    """Pasa la marca del escaparate del título viejo al nuevo.

    Sin `usuario` se repasa el de cada uno (el índice es de cada persona: Ana y
    Mauro tienen su propia cuenta de TikTok).

    No borra la vieja: si dos productos distintos acaban compartiendo título no
    se pierde nada, y una clave huérfana en el índice no molesta a nadie.
    """
    if not mudanzas:
        return
    quienes = (usuario,) if usuario is not None else ("", "ana", "mauro")
    for usuario in quienes:
        try:
            indice = escaparate_index(usuario)
        except Exception:  # noqa: BLE001 — Redis caído: se sigue sin tocar nada
            continue
        for tienda_v, titulo_v, tienda_n, titulo_n in mudanzas:
            if clave_escaparate(tienda_v, titulo_v) not in indice:
                continue
            if not clave_escaparate(tienda_n, titulo_n):
                continue
            try:
                set_escaparate(tienda_n, titulo_n, True, usuario)
            except Exception:  # noqa: BLE001
                pass


def folder_summary(source: str, folder: str) -> dict:
    """Recuento para pintar la cabecera de la carpeta."""
    productos = (load_folder(source, folder).get("productos") or {})
    return {
        "total": len(productos),
        "uploaded": sum(1 for p in productos.values() if p.get("uploaded")),
        "sold": sum(1 for p in productos.values() if p.get("sold")),
        "con_textos": sum(1 for p in productos.values() if p.get("titulo")),
    }


def _normaliza(texto: str) -> str:
    """Minúsculas y sin acentos, para que 'bikini' encuentre 'Bikiní'."""
    plano = unicodedata.normalize("NFKD", str(texto or "").lower())
    return "".join(c for c in plano if not unicodedata.combining(c))


def buscar_productos(
    consulta: str, *, usuario: str = "", source: str | None = None,
    limite: int = 20,
) -> tuple[list[dict], int]:
    """Busca en TODAS las carpetas por título, tienda o carpeta.

    Existe para lo de siempre: llega el aviso de una venta con el nombre del
    producto y hay que dar con él para marcarlo, sin acordarse de en cuál de
    las 35 carpetas estaba.

    Barre las carpetas con DOS `mget` (uno de lo compartido y otro de lo
    privado del usuario) en vez de leerlas una a una: 35 lecturas sueltas eran
    lo que hacía que el ranking de vendidos tardase ocho segundos.

    Devuelve `(resultados, total)`. El total va aparte porque los resultados
    vienen recortados a `limite` y quien llama tiene que poder decir "hay más".
    """
    from src.nicho_pov_bof import config
    from src.nicho_pov_bof.services import drive_client

    palabras = [p for p in _normaliza(consulta).split() if p]
    if not palabras:
        return [], 0
    r = get_nicho_pov_bof_redis()
    if not r.is_available():
        return [], 0

    entradas: list[tuple[str, str]] = []
    for src in ([source] if source else config.fuentes_a_barrer()):
        try:
            entradas += [(src, c["name"]) for c in drive_client.list_product_folders(src)]
        except Exception:
            # Una fuente ilegible no debe dejar sin buscar a la otra.
            continue
    if not entradas:
        return [], 0

    compartidos = r.mget_json([_key(s, f) for s, f in entradas])
    privados = (
        [] if _es_compartido(usuario)
        else r.mget_json([_key_privado(s, f, usuario) for s, f in entradas])
    )

    encontrados: list[dict] = []
    for i, (src, folder) in enumerate(entradas):
        doc = compartidos[i] if i < len(compartidos) else None
        productos = ((doc or {}).get("productos") or {})
        mios = ((privados[i] if i < len(privados) else None) or {}).get("productos") or {}
        for pid, prod in productos.items():
            if _es_compartido(usuario):
                estado = dict(prod)
            else:
                estado = {k: v for k, v in prod.items() if k not in CAMPOS_PRIVADOS}
                estado.update(mios.get(pid, {}))

            # La carpeta y el número entran en la búsqueda a propósito: a
            # veces lo que se recuerda es "el 4 de la carpeta 11".
            texto = _normaliza(" ".join([
                str(estado.get("titulo") or ""),
                str(estado.get("titulo_tiktok_completo") or ""),
                str(estado.get("tienda") or ""),
                folder, pid,
            ]))
            if not all(p in texto for p in palabras):
                continue

            # Lo que encaja por NOMBRE va antes de lo que solo encaja por
            # carpeta: buscando "11" interesa más el producto que se llama así
            # que los diez de la carpeta 11.
            por_nombre = _normaliza(" ".join([
                str(estado.get("titulo") or ""),
                str(estado.get("titulo_tiktok_completo") or ""),
                str(estado.get("tienda") or ""),
            ]))
            encontrados.append({
                "source": src, "folder": folder, "producto": pid,
                "_score": 1 if all(p in por_nombre for p in palabras) else 0,
                **estado,
            })

    # Orden NATURAL, no alfabético: ordenando como texto, "10 Pront Flow" va
    # antes que "4 Pront Flow" y buscar "pront flow 4" sacaba primero la 10.
    def _natural(texto: str) -> list:
        return [
            int(t) if t.isdigit() else t
            for t in re.split(r"(\d+)", _normaliza(texto))
        ]

    encontrados.sort(
        key=lambda d: (-d["_score"], _natural(d["folder"]), _natural(d["producto"]))
    )
    total = len(encontrados)
    recortados = encontrados[:limite]

    # Unidades vendidas, solo de los que se van a devolver.
    refs = [_ref_vendido(d["source"], d["folder"], d["producto"]) for d in recortados]
    if refs:
        docs = r.mget_json([_key_vendido(ref) for ref in refs])
        for d, vendido in zip(recortados, docs):
            d["unidades"] = int((vendido or {}).get("unidades") or 0)

    for d in recortados:
        d.pop("_score", None)
    return recortados, total


def productos_recuperados(usuario: str = "") -> list[dict]:
    """Productos que aparecieron DESPUÉS de haber trabajado ya su carpeta.

    Temporal, para una sola cosa: hasta ahora se perdían productos por dos
    fallos —fotos sin extensión que no se listaban y dos productos fundidos
    bajo el mismo número—, así que en carpetas ya terminadas hay fichas que
    nadie ha visto. Sin esto habría que repasar las 35 carpetas a mano.

    Un producto entra en la lista si su carpeta YA se trabajó pero él no tiene
    textos. Los de carpetas sin empezar no cuentan: esos no se han perdido, es
    que todavía no les toca.

    **Una vez dentro, se queda.** La lista se guarda en un índice de Redis y no
    se recalcula desde cero: si saliera solo mientras le faltan textos,
    desaparecería justo al extraerlos — que es cuando el operador todavía tiene
    que hacerle el vídeo, y se quedaría sin forma de encontrarlo entre 350.
    """
    from src.nicho_pov_bof import config
    from src.nicho_pov_bof.services import drive_client, photo_pairing

    out: list[dict] = []
    for src in config.fuentes_a_barrer():
        try:
            carpetas = drive_client.list_product_folders(src)
        except Exception:
            continue
        for carpeta in carpetas:
            folder = carpeta["name"]
            doc = load_folder_para(src, folder, usuario)
            guardados = doc.get("productos") or {}
            try:
                fotos = [
                    drive_client.probe_dimensions(f)
                    for f in drive_client.list_photos(src, folder)
                ]
                pares = photo_pairing.pair_folder(fotos)
            except Exception:
                continue
            procesada = bool(doc.get("textos_extraidos")) or any(
                (guardados.get(p["producto"]) or {}).get("titulo") for p in pares
            )
            if not procesada:
                continue
            for par in pares:
                pid = par["producto"]
                if (guardados.get(pid) or {}).get("titulo"):
                    continue
                _marcar_recuperado(src, folder, pid)

    return _leer_recuperados()


_RECUPERADOS_INDEX = "recuperados:index"


def _marcar_recuperado(source: str, folder: str, producto: str) -> None:
    r = get_nicho_pov_bof_redis()
    if r.is_available():
        r.sadd(_RECUPERADOS_INDEX, f"{source}|{folder}|{producto}")


def _leer_recuperados() -> list[dict]:
    """Los del índice, con su foto. Vale aunque ya tengan textos o vídeo."""
    from src.nicho_pov_bof.services import drive_client, photo_pairing

    r = get_nicho_pov_bof_redis()
    if not r.is_available():
        return []
    refs = sorted(str(x) for x in r.smembers(_RECUPERADOS_INDEX) if x)

    # Las fotos se resuelven por CARPETA, no por producto: cinco productos de
    # cuatro carpetas son cuatro emparejados, no cinco.
    cache: dict[tuple[str, str], dict[str, str]] = {}
    salida: list[dict] = []
    for ref in refs:
        partes = ref.split("|")
        if len(partes) != 3:
            continue
        src, folder, pid = partes
        clave = (src, folder)
        if clave not in cache:
            try:
                fotos = [
                    drive_client.probe_dimensions(f)
                    for f in drive_client.list_photos(src, folder)
                ]
                cache[clave] = {
                    p["producto"]: (p.get("clean") or {}).get("id") or ""
                    for p in photo_pairing.pair_folder(fotos)
                }
            except Exception:
                cache[clave] = {}
        salida.append({
            "source": src, "folder": folder, "producto": pid,
            "clean_photo_id": cache[clave].get(pid, ""),
        })
    return salida


def olvidar_recuperado(source: str, folder: str, producto: str) -> None:
    """Saca un producto de la lista de recuperados (ya está hecho)."""
    r = get_nicho_pov_bof_redis()
    if r.is_available():
        r.srem(_RECUPERADOS_INDEX, f"{source}|{folder}|{producto}")


def sold_products(source: str | None = None) -> list[dict]:
    """Productos marcados como vendidos, para el apartado de referencia.

    Recorre las carpetas que tengan estado guardado. Es una vista de consulta,
    no de uso intensivo, así que leer carpeta a carpeta es aceptable.
    """
    from src.nicho_pov_bof import config
    from src.nicho_pov_bof.services import drive_client

    out: list[dict] = []
    fuentes = [source] if source else config.fuentes_a_barrer()
    for src in fuentes:
        try:
            carpetas = drive_client.list_product_folders(src)
        except Exception:
            continue
        for carpeta in carpetas:
            data = load_folder(src, carpeta["name"])
            for prod_id, prod in (data.get("productos") or {}).items():
                if prod.get("sold"):
                    out.append({
                        "source": src,
                        "folder": carpeta["name"],
                        "producto": prod_id,
                        **prod,
                    })
    return out


# ---------------------------------------------------------------------------
# Hashtags del caption
# ---------------------------------------------------------------------------
# Van aparte del producto porque son los MISMOS para toda la cuenta: el
# operador los cambia según la campaña del momento (#rebajasdeverano…) y se
# pegan al final de cada caption. Guardarlos por producto obligaría a
# editarlos diez veces.
_HASHTAGS_KEY = "hashtags"
# Los de la cuenta de referencia del mentor, como punto de partida.
HASHTAGS_DEFECTO = ["#rebajasdeverano", "#tiktokshop", "#ofertas"]


def get_hashtags() -> list[str]:
    """Hashtags configurados. Si nunca se han tocado, los de partida."""
    r = get_nicho_pov_bof_redis()
    if not r.is_available():
        return list(HASHTAGS_DEFECTO)
    doc = r.get_json(_HASHTAGS_KEY)
    if not isinstance(doc, dict) or "tags" not in doc:
        return list(HASHTAGS_DEFECTO)
    return [str(t) for t in (doc.get("tags") or []) if str(t).strip()]


def save_hashtags(tags: list[str]) -> list[str]:
    """Guarda la lista (ya normalizada) y la devuelve.

    Una lista VACÍA es un estado válido: significa "no quiero hashtags", y
    hay que poder distinguirlo de "nunca los he configurado".
    """
    limpios: list[str] = []
    for t in tags:
        t = str(t).strip().lstrip("#").strip()
        if not t:
            continue
        tag = f"#{t}"
        if tag.lower() not in {x.lower() for x in limpios}:
            limpios.append(tag)
    r = _require_redis()
    r.set_json(_HASHTAGS_KEY, {"tags": limpios, "updated_at": _now()})
    return limpios


# ---------------------------------------------------------------------------
# Escaparate: índice ÚNICO por producto (tienda + nombre), por usuario
# ---------------------------------------------------------------------------
# Meter un producto en el escaparate del Marketplace se hace UNA vez por
# producto: da igual en qué carpeta salga y con qué nicho se grabe, la cuenta de
# TikTok es la misma. Marcarlo carpeta a carpeta y nicho a nicho obligaba a
# recordar cuáles ya estaban — y el mismo producto aparece repetido en varias
# carpetas del Drive del curso.
#
# Por eso el estado NO vive en el producto, sino en un índice con clave
# `tienda|nombre`: marcado desde cualquier sitio, se ve marcado en todos.
#
# Es POR USUARIO y no se comparte: Ana y Mauro son otras personas con su propia
# cuenta de TikTok, así que su escaparate no es el de `ness`.
_ESCAPARATE_INDEX = "escaparate:index"


# Longitud mínima del trozo común para dar por bueno un título cortado. Con
# menos no se distingue un producto de su hermano ("DEWINNER cama..." hay
# cinco), así que se prefiere no emparejar.
_MIN_TROZO = 40


def _sin_puntos(clave: str) -> str:
    """El trozo útil de una clave cortada, o vacío si no está cortada."""
    limpia = clave.rstrip()
    if not limpia.endswith("..."):
        return ""
    trozo = limpia[:-3].rstrip()
    return trozo if len(trozo) >= _MIN_TROZO else ""


def casa_clave(clave: str, candidatas) -> str:
    """La clave equivalente dentro de `candidatas`, aunque una venga CORTADA.

    El título literal se lee de la CAPTURA de la ficha y TikTok corta los
    largos con puntos suspensivos: la misma cama es "…reposabrazos" en una
    captura y "…reposabra..." en otra. Sin esto, la URL pegada con la captura
    corta se quedaba huérfana en cuanto se releían los textos y salía el
    título entero — 61 de las 169 fichas guardadas estaban así.

    Solo empareja si NO hay duda: si el trozo cuadra con dos productos
    distintos devuelve vacío, que es mejor que enseñar la ficha equivocada.
    """
    if not clave:
        return ""
    candidatas = list(candidatas)
    if clave in candidatas:
        return clave
    trozo = _sin_puntos(clave)
    casan = set()
    for otra in candidatas:
        if trozo and otra.startswith(trozo):
            casan.add(otra)
            continue
        trozo_otra = _sin_puntos(otra)
        if trozo_otra and clave.startswith(trozo_otra):
            casan.add(otra)
    return casan.pop() if len(casan) == 1 else ""


def marcado_en_escaparate(prod: dict, indice: set[str]) -> bool:
    """¿Este producto está en el escaparate? ÚNICO criterio para todos los nichos.

    Manda el índice compartido, pero se acepta también la marca antigua que
    vive dentro del producto (`en_escaparate`), de cuando el escaparate era de
    cada carpeta. Hacía falta unificarlo: el POV BOF miraba las dos cosas y el
    Largo solo el índice, así que la misma carpeta salía llena en uno y a cero
    en el otro.

    Se miran las DOS claves posibles (ver `claves_escaparate`): la nueva, con
    el título literal de la ficha, y la vieja, con el título reescrito. Así las
    marcas de antes de la migración siguen valiendo.
    """
    if bool(prod.get("en_escaparate")):
        return True
    claves = claves_escaparate(prod)
    if any(c in indice for c in claves):
        return True
    # Y las cortadas: el título literal depende de cuánto se vea en la captura
    # de la ficha (ver `casa_clave`).
    return any(casa_clave(c, indice) for c in claves)


def claves_escaparate(prod: dict) -> list[str]:
    """Las claves con las que este producto puede estar en el índice.

    La primera es la BUENA: el título LITERAL de la ficha
    (`titulo_tiktok_completo`), que se copia letra a letra y no cambia aunque
    se vuelvan a leer los textos. La segunda es la vieja, con el `titulo`
    reescrito por la IA — se resumía y se traducía, así que cada relectura lo
    dejaba distinto y la marca se quedaba huérfana. Se sigue mirando para no
    perder lo marcado antes de la migración.
    """
    tienda = prod.get("tienda", "") or ""
    claves = []
    for nombre in (prod.get("titulo_tiktok_completo"), prod.get("titulo")):
        clave = clave_escaparate(tienda, str(nombre or ""))
        if clave and clave not in claves:
            claves.append(clave)
    return claves


def marcar_escaparate_producto(prod: dict, on: bool, usuario: str = "") -> None:
    """Mete o saca del escaparate un producto entero (con sus dos claves).

    Al marcar se escribe SOLO la clave buena (la del título literal). Al
    desmarcar se quitan las dos, porque si no la vieja seguiría diciendo que
    está dentro.
    """
    claves = claves_escaparate(prod)
    if not claves:
        return
    r = get_nicho_pov_bof_redis()
    if not r.is_available():
        return
    # Cualquier escritura tira la memoria: si no, marcar algo tardaría en
    # verse y parecería que no se ha guardado.
    _olvidar(f"esc:{usuario}")
    if on:
        r.sadd(_key_escaparate(usuario), claves[0])
        return
    for clave in claves:
        r.srem(_key_escaparate(usuario), clave)


def clave_escaparate(tienda: str, titulo: str) -> str:
    """`tienda|nombre` normalizados. Vacía si no hay nombre — sin textos
    extraídos todavía no se puede saber si dos productos son el mismo."""
    nombre = " ".join(_normaliza(titulo).split())
    if not nombre:
        return ""
    return f"{' '.join(_normaliza(tienda).split())}|{nombre}"


# ---------------------------------------------------------------------------
# La ficha del producto en TikTok Shop (su URL)
# ---------------------------------------------------------------------------
# La URL es del PRODUCTO, no de la carpeta: el mismo producto sale en varias
# carpetas y catálogos, y pegarla una vez tiene que valer para todas. Por eso
# va en un índice con la misma clave que el escaparate (tienda + título
# literal) y NO por usuario: la ficha de TikTok es la misma para ness, Mauro y
# Ana — lo que cambia es la cuenta desde la que cada uno la añade al suyo.
_URLS_INDEX = "urls:index"


def urls_index() -> dict[str, str]:
    """`{clave: url}` de todos los productos con ficha guardada."""
    def _leer() -> dict[str, str]:
        r = get_nicho_pov_bof_redis()
        if not r.is_available():
            return {}
        return r.get_json(_URLS_INDEX) or {}

    return _recordado("urls", _leer)


def guardar_ids_vigentes(source: str, folder: str, ids: list[str]) -> None:
    """Apunta qué productos tiene HOY la carpeta.

    Hace falta porque el documento acumula huérfanos: cuando el curso cambia
    las fotos de una carpeta, lo guardado del producto viejo se reengancha por
    file ID (`reanclaje`) y lo que no encuentra dueño se queda ahí para siempre.
    Una carpeta de diez llegó a tener veinticuatro entradas, y contarlas todas
    decía "19 productos con ficha" en una carpeta de 10.

    Se escribe al listar la carpeta, que es cuando se sabe de verdad — sacarlo
    en el listado de carpetas costaría un listado de Drive por carpeta (medido:
    ~0,2s cada una, 6,5s por pantalla).
    """
    r = get_nicho_pov_bof_redis()
    if not r.is_available():
        return
    clave = _key(source, folder)
    doc = r.get_json(clave) or {}
    nuevos = [str(x) for x in ids if str(x)]
    if doc.get("ids_vigentes") == nuevos:
        return
    doc["ids_vigentes"] = nuevos
    r.set_json(clave, doc)


def con_url_por_carpeta(source: str, folders: list[str]) -> dict[str, int]:
    """`{carpeta: cuántos de sus productos tienen ficha enlazada}`.

    Sirve para saber desde el listado en qué carpetas hay trabajo de verdad sin
    entrar en cada una. Los textos (título y tienda) son del producto y viven en
    el documento COMPARTIDO, así que vale con leer ese: la ficha enlazada
    tampoco es de nadie en particular.

    Se leen TODAS las carpetas de un tirón (`mget`) y el índice de fichas UNA
    vez. Carpeta a carpeta serían 30 idas y vueltas a Upstash cada vez que se
    abre la pantalla, que es justo lo que hizo lenta la de Carruseles.
    """
    r = get_nicho_pov_bof_redis()
    if not r.is_available() or not folders:
        return {}
    indice = urls_index()
    if not indice:
        return {n: 0 for n in folders}
    docs = r.mget_json([_key(source, n) for n in folders])
    salida: dict[str, int] = {}
    for nombre, doc in zip(folders, docs):
        todos = ((doc or {}).get("productos") or {})
        # Solo los que la carpeta tiene HOY. Sin esa lista (carpeta que nadie
        # ha abierto todavía) se cuentan todos: es lo que había, y se corrige
        # sola en cuanto se abra.
        vigentes = (doc or {}).get("ids_vigentes")
        if isinstance(vigentes, list):
            productos = [todos[str(i)] for i in vigentes if str(i) in todos]
        else:
            productos = list(todos.values())
        salida[nombre] = sum(1 for prod in productos if url_de(prod, indice))
    return salida


def resumen_por_carpeta(source: str, folders: list[str]) -> dict[str, dict]:
    """`{carpeta: {total, con_url, sin_stock}}` con UNA sola lectura.

    Las tres cifras salen del mismo documento, así que contarlas por separado
    eran tres `mget` a Upstash para pintar la misma pantalla.

    Es lo que hace falta para saber desde el listado qué carpeta merece abrirse:
    `con_url` sola engaña —un "9" no dice si la carpeta tiene nueve productos o
    diez con uno sin enlazar— y un producto retirado se sigue contando como
    trabajo pendiente hasta que se marca.
    """
    r = get_nicho_pov_bof_redis()
    if not r.is_available() or not folders:
        return {}
    indice = urls_index()
    docs = r.mget_json([_key(source, n) for n in folders])
    salida: dict[str, dict] = {}
    for nombre, doc in zip(folders, docs):
        todos = ((doc or {}).get("productos") or {})
        # `ids_vigentes` es lo que la carpeta tiene HOY; sin ella el documento
        # arrastra huérfanos y contaría de más. Si no está (carpeta que nadie ha
        # abierto), se cuenta todo: es lo que había, y se corrige al abrirla.
        vigentes = (doc or {}).get("ids_vigentes")
        productos = (
            [todos[str(i)] for i in vigentes if str(i) in todos]
            if isinstance(vigentes, list) else list(todos.values())
        )
        salida[nombre] = {
            "total": len(productos),
            "con_url": sum(1 for prod in productos if indice and url_de(prod, indice)),
            "sin_stock": sum(1 for prod in productos if prod.get("sin_stock")),
        }
    return salida


def esperando_stock(
    source: str, folders: list[str], usuario: str = "",
) -> dict[str, list[str]]:
    """`{carpeta: [números]}` de los productos con el vídeo hecho, marcados sin
    stock y aún sin subir.

    Es trabajo TERMINADO que no se puede publicar: la ficha de TikTok no está
    disponible. No se tira —el producto puede volver— pero mezclado con el
    resto se pierde de vista, y el vídeo estaba hecho. Al marcarlos subidos
    salen solos de la lista, porque el filtro es este.

    `video_path` y `uploaded` son campos privados: para `ness` viven en el
    documento compartido y para los demás en el suyo, así que hay que mirar
    los dos y quedarse con el privado, igual que hace `get_product`.
    """
    r = get_nicho_pov_bof_redis()
    if not r.is_available() or not folders:
        return {}
    docs = r.mget_json([_key(source, n) for n in folders])
    privados: dict[str, dict] = {}
    if not _es_compartido(usuario):
        for nombre in folders:
            doc = r.get_json(_key_privado(source, nombre, usuario)) or {}
            privados[nombre] = doc.get("productos") or {}

    salida: dict[str, list[str]] = {}
    for nombre, doc in zip(folders, docs):
        todos = ((doc or {}).get("productos") or {})
        mios = privados.get(nombre) or {}
        vigentes = (doc or {}).get("ids_vigentes")
        numeros = (
            [str(i) for i in vigentes if str(i) in todos]
            if isinstance(vigentes, list) else list(todos)
        )
        aqui = []
        for n in numeros:
            prod = {**todos.get(n, {}), **mios.get(n, {})}
            if prod.get("sin_stock") and prod.get("video_path") and not prod.get("uploaded"):
                aqui.append(str(n))
        if aqui:
            salida[nombre] = sorted(aqui, key=lambda x: int(x) if x.isdigit() else 0)
    return salida


def productos_por_carpeta(source: str, folders: list[str]) -> dict[str, int]:
    """`{carpeta: cuántos productos tiene HOY}`. Una sola lectura para todas.

    Se usa para avisar de que una carpeta YA COMPLETADA ha crecido: el
    catálogo de la web se actualiza y, sin esto, los productos nuevos de una
    carpeta terminada no se ven nunca.
    """
    r = get_nicho_pov_bof_redis()
    if not r.is_available() or not folders:
        return {}
    docs = r.mget_json([_key(source, n) for n in folders])
    salida: dict[str, int] = {}
    for nombre, doc in zip(folders, docs):
        todos = ((doc or {}).get("productos") or {})
        vigentes = (doc or {}).get("ids_vigentes")
        # `ids_vigentes` es la lista de lo que la carpeta tiene HOY; sin ella
        # el documento arrastra huérfanos y contaría de más.
        salida[nombre] = (
            len([i for i in vigentes if str(i) in todos])
            if isinstance(vigentes, list) else len(todos)
        )
    return salida


def _casa_solo_titulo(clave: str, indice) -> str:
    """La clave del índice con el MISMO título aunque la tienda sea otra.

    `casa_clave` cubre el título cortado por TikTok, pero no el otro modo de
    quedarse huérfana una ficha: que cambie la TIENDA. Pasa de verdad — la
    tienda se lee de la captura igual que el título, y al releer los textos un
    producto puede pasar de "DEWINNER" a "TEENO" (la marca del producto y la
    del vendedor no siempre son la misma). La URL seguía guardada con la
    tienda vieja y el botón salía apagado.

    Misma regla que el resto: solo si NO hay duda. Si el título cuadra con dos
    tiendas distintas se devuelve vacío, que es mejor que abrir la ficha
    equivocada.
    """
    if "|" not in clave:
        return ""
    titulo = clave.split("|", 1)[1]
    if not titulo:
        return ""
    casan = {
        otra for otra in indice
        if "|" in otra and otra.split("|", 1)[1] == titulo
    }
    return casan.pop() if len(casan) == 1 else ""


def url_de(prod: dict, indice: dict[str, str] | None = None) -> str:
    """La ficha de ese producto: la del índice o la que guardó EchoTik."""
    if indice is None:
        indice = urls_index()
    claves = claves_escaparate(prod)
    for clave in claves:
        if indice.get(clave):
            return str(indice[clave])
    for clave in claves:
        equivalente = casa_clave(clave, indice)
        if equivalente and indice.get(equivalente):
            return str(indice[equivalente])
    # Último intento: mismo título, otra tienda.
    for clave in claves:
        equivalente = _casa_solo_titulo(clave, indice)
        if equivalente and indice.get(equivalente):
            return str(indice[equivalente])
    return str(prod.get("product_url") or "")


def guardar_url(prod: dict, url: str) -> str:
    """Guarda (o borra, con url vacía) la ficha de un producto. Devuelve la url."""
    claves = claves_escaparate(prod)
    if not claves:
        raise RuntimeError(
            "Sin título no se puede guardar la ficha: extrae antes los textos."
        )
    r = _require_redis()
    indice = r.get_json(_URLS_INDEX) or {}
    # Las equivalentes cortadas salen del índice: si no, el mismo producto
    # acabaría con dos entradas y la vieja seguiría contestando.
    viejas = {c for clave in claves if (c := casa_clave(clave, indice))}
    limpia = url.strip()
    for clave in viejas | set(claves):
        indice.pop(clave, None)
    if limpia:
        indice[claves[0]] = limpia
    r.set_json(_URLS_INDEX, indice)
    _olvidar("urls")
    return limpia


# ---------------------------------------------------------------------------
# Qué productos son EXCLUSIVOS de la web
# ---------------------------------------------------------------------------
# El catálogo de la web repite muchos productos del Drive del curso, y saber
# cuáles son nuevos de verdad es lo que decide a cuál merece la pena dedicarle
# un vídeo. Se compara por la misma clave que el escaparate (tienda|título),
# que es la que ya trata dos fichas del mismo producto como una.
#
# Va en un índice aparte y no se recalcula al vuelo: leer los documentos de las
# 61 carpetas del Drive en cada pantalla sería justo lo que se quitó de en
# medio al optimizar Upstash. Se escribe al extraer textos, que es cuando de
# verdad cambia.
_TITULOS_DRIVE = "titulos:drive"

# Las fuentes que SON el Drive del curso. Las demás ("Mis productos", la web,
# top vendidos) son nuestras: un producto que solo esté ahí no cuenta como
# "también en el Drive".
FUENTES_DRIVE = ("aleatorios_1", "aleatorios_2")


def titulos_drive() -> set[str]:
    """Claves de todos los productos del Drive del curso con texto leído."""
    def _leer() -> set[str]:
        r = get_nicho_pov_bof_redis()
        if not r.is_available():
            return set()
        return set(r.get_json(_TITULOS_DRIVE) or [])

    return _recordado("titulos_drive", _leer)


def _sumar_titulos_drive(claves: set[str]) -> None:
    """Añade claves al índice. Solo escribe si hay alguna nueva."""
    if not claves:
        return
    r = get_nicho_pov_bof_redis()
    if not r.is_available():
        return
    actuales = set(r.get_json(_TITULOS_DRIVE) or [])
    if claves <= actuales:
        return
    r.set_json(_TITULOS_DRIVE, sorted(actuales | claves))
    _olvidar("titulos_drive")


def reconstruir_titulos_drive(carpetas_por_fuente: dict[str, list[str]]) -> int:
    """Rehace el índice entero leyendo los documentos de las carpetas.

    Hace falta una vez, para lo ya extraído antes de que esto existiera, y
    cuando se sospeche que se ha quedado corto. Un `mget` por fuente.
    """
    r = _require_redis()
    claves: set[str] = set()
    for fuente, carpetas in carpetas_por_fuente.items():
        if fuente not in FUENTES_DRIVE or not carpetas:
            continue
        for doc in r.mget_json([_key(fuente, n) for n in carpetas]):
            for prod in ((doc or {}).get("productos") or {}).values():
                claves.update(claves_escaparate(prod))
    r.set_json(_TITULOS_DRIVE, sorted(claves))
    _olvidar("titulos_drive")
    return len(claves)


def tambien_en_drive(prod: dict, indice: set[str] | None = None) -> bool:
    """¿Este producto existe también en el Drive del curso?

    `None` de verdad no existe aquí: sin texto leído no se puede comparar, y
    eso lo distingue la UI mirando si hay título — no un tercer valor.
    """
    if indice is None:
        indice = titulos_drive()
    if not indice:
        return False
    claves = claves_escaparate(prod)
    if any(c in indice for c in claves):
        return True
    # Mismo producto con la ficha cortada por otro sitio.
    if any(casa_clave(c, indice) for c in claves):
        return True
    # Y mismo título con la tienda leída de otra forma ("MIKOMIKA" vs
    # "MIKOMIKA Store"): la clave lleva la tienda dentro, así que sin esto un
    # producto idéntico se daba por exclusivo de la web. Es el mismo rescate
    # que ya hace `url_de`, y solo cuela si el título casa ENTERO y no hay
    # más de un candidato.
    return any(_casa_solo_titulo(c, indice) for c in claves)


def importar_urls(
    source: str, filas: list[dict], carpetas_reales: list[str] | None = None,
) -> dict:
    """Guarda de golpe las fichas que vienen pegadas de la web del curso.

    Cada fila es `{carpeta, producto, url}` tal cual sale del DOM de su página
    (`Carpeta 7` / `Producto 3`). Se escribe en dos sitios a la vez y no es
    redundante:

    - `product_url` en el documento de la carpeta, que es lo ÚNICO que funciona
      antes de extraer los textos. La clave del índice es `tienda|título`, así
      que sin título no hay dónde meterlo — y pegar los enlaces antes de leer
      las capturas es justo el orden natural.
    - el índice global, para los que ya tienen texto: así el mismo producto
      enlazado aquí sale enlazado en los demás nichos y catálogos.

    Un producto por escritura serían 310 idas y vueltas a Upstash. Aquí es un
    documento por carpeta (31) más una sola pasada por el índice.
    """
    # Su web dice "Carpeta 1" y en el ZIP la carpeta acabó llamándose
    # "Carpeta_1": el nombre sale del fichero que descarga el navegador. Sin
    # casarlos, cada enlace se guardaba en un documento fantasma y la pantalla
    # seguía sin fichas — mal sin dar ningún error.
    reales = {_llana(n): n for n in (carpetas_reales or [])}

    # `url` vacía y `sin_stock` no son lo mismo que "no venía en el pegote":
    # el producto existe, su web dice que está agotado. Guardarlo es lo que
    # deja saber de un vistazo cuáles no se pueden grabar hoy — y como sacar
    # el pegote es gratis, al repetirlo el estado se actualiza solo.
    por_carpeta: dict[str, dict[str, str]] = {}
    agotados: dict[str, set[str]] = {}
    con_stock: dict[str, set[str]] = {}
    sin_carpeta: set[str] = set()
    descartadas: list[str] = []
    for fila in filas:
        pegada = _carpeta_pegada(str(fila.get("carpeta") or ""))
        producto = _numero_pegado(str(fila.get("producto") or ""))
        url = str(fila.get("url") or "").strip()
        if not pegada or not producto:
            continue
        carpeta = reales.get(_llana(pegada), "" if reales else pegada)
        if not carpeta:
            sin_carpeta.add(pegada)
            continue
        if not url:
            # Sin enlace NO es sin stock: en su web hay productos sin ninguna
            # de las dos cosas —simplemente no le ha puesto la ficha—. Solo se
            # marca agotado cuando el guion ha leído el cartel de verdad, y se
            # DESMARCA cuando el pegote dice que ya no lo lleva.
            if fila.get("sin_stock"):
                agotados.setdefault(carpeta, set()).add(producto)
            elif "sin_stock" in fila:
                con_stock.setdefault(carpeta, set()).add(producto)
            continue
        # Su web tiene enlaces que no son fichas (apareció un script de Google
        # en una). Guardarlos dejaría un botón 🔗 que abre cualquier cosa.
        if not _es_ficha_tiktok(url):
            descartadas.append(f"{pegada} · {producto}: {url[:60]}")
            continue
        por_carpeta.setdefault(carpeta, {})[producto] = url

    if not por_carpeta and not agotados and not con_stock:
        return {
            "carpetas": 0, "guardados": 0, "con_id": 0, "en_indice": 0,
            "agotados": 0,
            "sin_carpeta": sorted(sin_carpeta), "descartadas": descartadas,
        }

    # El ID de producto sale de seguir el redirect del enlace, y es lo que se
    # pega en TikTok Studio para enlazar sin bucear en la lista. Se saca AQUÍ,
    # al guardar, y no en un botón aparte: si no, el operador pega las fichas y
    # luego tiene que acordarse de un segundo paso.
    from src.nicho_pov_bof.services import product_url as _url_svc

    todas = [u for urls in por_carpeta.values() for u in urls.values()]
    ids: dict[str, str] = {}
    if todas:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=16) as pool:
            ids = {
                u: i for u, i in zip(todas, pool.map(_url_svc.id_desde_url, todas)) if i
            }

    r = _require_redis()
    indice = r.get_json(_URLS_INDEX) or {}
    guardados = 0
    en_indice = 0
    con_id = 0

    agotados_escritos = 0
    for carpeta in sorted(set(por_carpeta) | set(agotados) | set(con_stock)):
        urls = por_carpeta.get(carpeta, {})
        with _cerrojo_carpeta(source, carpeta):
            data = load_folder(source, carpeta)
            productos = data.setdefault("productos", {})
            # Primero los agotados: si el mismo producto trae URL en esta
            # misma tanda, la rama de abajo lo desmarca.
            for producto in agotados.get(carpeta, set()):
                prod = productos.setdefault(producto, {})
                if not prod.get("sin_stock"):
                    prod["sin_stock"] = True
                    prod["updated_at"] = _now()
                agotados_escritos += 1
            # Ya no lleva el cartel: se quita, aunque siga sin enlace.
            for producto in con_stock.get(carpeta, set()):
                prod = productos.get(producto)
                if prod and prod.get("sin_stock"):
                    prod["sin_stock"] = False
                    prod["updated_at"] = _now()
            for producto, url in urls.items():
                prod = productos.setdefault(producto, {})
                if prod.get("product_url") != url or prod.get("sin_stock"):
                    prod["product_url"] = url
                    # Vuelve a haber ficha: ya no está agotado.
                    prod["sin_stock"] = False
                    prod["updated_at"] = _now()
                if ids.get(url):
                    prod["product_id"] = ids[url]
                    con_id += 1
                guardados += 1
                # Con textos ya extraídos, también al índice global.
                claves = claves_escaparate(prod)
                if claves:
                    for vieja in {c for cl in claves if (c := casa_clave(cl, indice))}:
                        indice.pop(vieja, None)
                    indice[claves[0]] = url
                    en_indice += 1
            save_folder(source, carpeta, data)

    r.set_json(_URLS_INDEX, indice)
    _olvidar("urls")
    return {
        "carpetas": len(set(por_carpeta) | set(agotados) | set(con_stock)),
        "guardados": guardados,
        "con_id": con_id,
        "en_indice": en_indice,
        "agotados": agotados_escritos,
        # Las que no casan con ninguna carpeta del catálogo. No se guardan en
        # ningún sitio: se dicen, para no dejar enlaces en un limbo.
        "sin_carpeta": sorted(sin_carpeta),
        # Enlaces que no son una ficha de TikTok.
        "descartadas": descartadas,
    }


def _es_ficha_tiktok(url: str) -> bool:
    """Solo enlaces de TikTok: el corto (`vm.tiktok.com`) o la ficha entera."""
    return bool(re.match(r"^https?://([a-z0-9-]+\.)*tiktok\.com/", url.strip(), re.I))


def _llana(texto: str) -> str:
    """`Carpeta_1` y `📁 Carpeta 1` dan lo mismo: `carpeta1`."""
    return re.sub(r"[^a-z0-9]", "", (texto or "").lower())


def _carpeta_pegada(texto: str) -> str:
    """`📁 Carpeta 7` → `Carpeta 7`, que es como se llama la del ZIP."""
    limpio = " ".join(texto.split())
    m = re.search(r"(Carpeta\s*\d+)", limpio, flags=re.IGNORECASE)
    if m:
        return f"Carpeta {m.group(1).split()[-1]}"
    # Sin "Carpeta N" reconocible se devuelve el texto sin el emoji de delante.
    return re.sub(r"^[^\w]+|[^\w]+$", "", limpio).strip()


def _numero_pegado(texto: str) -> str:
    """`Producto 3` → `3`, que es el id con el que se guardan las fotos."""
    m = re.search(r"(\d+)", texto or "")
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# Memoria corta de los índices GLOBALES
# ---------------------------------------------------------------------------
# Estos tres índices —escaparate, fichas y vendidos— son de TODO el catálogo, no
# de una carpeta, y se consultan una y otra vez dentro de la misma petición: hay
# bucles que los piden por cada producto. Con diez productos por carpeta y cinco
# carpetas en "Top vendidos", eran cientos de lecturas idénticas a Upstash por
# pantalla.
#
# Se guardan unos segundos en memoria del proceso. El TTL es corto a propósito:
# lo que de verdad evita servir datos rancios es que CUALQUIER escritura sobre
# un índice lo tira (`_olvidar`), así que marcar algo se ve al instante. El TTL
# solo cubre el caso de que escriba OTRO proceso (Ana desde su móvil), y ahí
# unos segundos de retraso no molestan a nadie.
_MEMO_S = 5.0
_memo: dict[str, tuple[float, object]] = {}


def _recordado(clave: str, leer):
    """Lo que devuelva `leer()`, recordado unos segundos."""
    import time

    guardado = _memo.get(clave)
    if guardado and (time.monotonic() - guardado[0]) < _MEMO_S:
        return guardado[1]
    valor = leer()
    _memo[clave] = (time.monotonic(), valor)
    return valor


def _olvidar(prefijo: str = "") -> None:
    """Tira lo recordado. Se llama en CADA escritura de un índice."""
    if not prefijo:
        _memo.clear()
        return
    for k in [k for k in _memo if k.startswith(prefijo)]:
        _memo.pop(k, None)


def _key_escaparate(usuario: str = "") -> str:
    if _es_compartido(usuario):
        return _ESCAPARATE_INDEX
    return f"{_ESCAPARATE_INDEX}:{usuario}"


def escaparate_index(usuario: str = "") -> set[str]:
    """Claves de los productos ya metidos en el escaparate por ese usuario."""
    def _leer() -> set[str]:
        r = get_nicho_pov_bof_redis()
        if not r.is_available():
            return set()
        return {str(x) for x in r.smembers(_key_escaparate(usuario)) if x}

    return _recordado(f"esc:{usuario}", _leer)


def en_escaparate(tienda: str, titulo: str, usuario: str = "") -> bool:
    clave = clave_escaparate(tienda, titulo)
    return bool(clave) and clave in escaparate_index(usuario)


def set_escaparate(tienda: str, titulo: str, on: bool, usuario: str = "") -> None:
    """Mete o saca el producto del escaparate. Degrada en silencio si aún no
    hay textos (sin nombre no hay clave) o si Redis no está."""
    clave = clave_escaparate(tienda, titulo)
    if not clave:
        return
    r = get_nicho_pov_bof_redis()
    if not r.is_available():
        return
    _olvidar(f"esc:{usuario}")
    if on:
        r.sadd(_key_escaparate(usuario), clave)
    else:
        r.srem(_key_escaparate(usuario), clave)


# ---------------------------------------------------------------------------
# Vendidos: índice propio + unidades
# ---------------------------------------------------------------------------
# Recorrer las 31 carpetas de cada fuente para encontrar dos productos vendidos
# costaba 8 SEGUNDOS de Redis. Y el resultado no traía foto, porque
# `clean_photo_id` se calcula al listar y nunca se guardaba.
#
# Así que los vendidos llevan su propio índice, con una copia de lo poco que
# hace falta para pintarlos. Se escribe al marcar "vendió", que pasa dos veces
# al día; leerlo son dos llamadas a Redis en vez de sesenta.
# El índice es UNO SOLO para todos los nichos, a propósito: el operador quiere
# poder verlo todo junto Y filtrar por nicho, y eso con índices separados
# obligaría a leer N índices y mezclarlos. Cada venta lleva apuntado de qué
# nicho salió (`nicho`), y ese dato lo pone él al marcarla — no se adivina,
# porque el mismo producto se graba con varios nichos y solo él sabe cuál
# vendió.
_VENDIDOS_INDEX = "vendidos:index"


def _key_vendidos_index(usuario: str = "") -> str:
    """Índice del ranking. Es POR USUARIO, igual que el escaparate: haber
    vendido un producto es el resultado de la cuenta de UNA persona, no un dato
    del catálogo. Ana no vende porque venda yo.

    `ness` se queda en la clave sin sufijo (su histórico), que es el criterio
    que ya usan el progreso de carpetas y el escaparate.
    """
    if _es_compartido(usuario):
        return _VENDIDOS_INDEX
    return f"{_VENDIDOS_INDEX}:{usuario}"

# Nichos que pueden atribuirse una venta. La clave es lo que se guarda; la
# etiqueta, lo que se enseña.
NICHOS_VENTA: dict[str, str] = {
    "pov_bof": "POV BOF",
    "pov_bof_largo": "POV BOF Largo",
    "bof_cine": "BOF Cinematográfico",
    "creativos": "Creativos Pro",
    "ropa": "Ropa",
    "ropa_personas": "Ropa Con Personas",
    "gorras": "Gorras",
    "otro": "Otro",
}


def _ref_vendido(source: str, folder: str, producto: str) -> str:
    """La referencia con la que vive un producto en el ranking.

    En "Top vendidos" el producto es una COPIA de uno del curso, así que la
    venta se le apunta al ORIGINAL: es quien está en el ranking y con quien se
    cruzan las ventas al listar. Apuntarla aquí dejaba dos entradas del mismo
    producto y, peor, el listado de Top vendidos no veía esas ventas —seguía
    diciendo 0 y el orden por ventas no cambiaba— porque solo cruza por la
    referencia de origen.

    La traducción se hace AQUÍ y no en cada endpoint: el POV BOF la hacía y el
    Largo no, así que marcar la venta desde una pantalla u otra daba resultados
    distintos.
    """
    if source == "top_vendidos":
        try:
            from src.nicho_pov_bof.services import top_vendidos

            origen = top_vendidos.origen_de(folder, producto)
            if origen:
                return (
                    f"{origen['source']}|{origen['folder']}|{origen['producto']}"
                )
        except Exception:  # noqa: BLE001
            # Sin manifiesto (Redis caído) se apunta donde estaba: perder la
            # venta sería peor que apuntarla en el sitio raro.
            pass
    return f"{source}|{folder}|{producto}"


def _key_vendido(ref: str, usuario: str = "") -> str:
    if _es_compartido(usuario):
        return f"vendido:{ref}"
    return f"vendido:u:{usuario}:{ref}"


def marcar_vendido(
    source: str, folder: str, producto: str,
    *, titulo: str = "", tienda: str = "", clean_photo_id: str = "",
    product_url: str = "", unidades: int = 1, nicho: str = "",
    usuario: str = "",
) -> dict:
    """Entra (o actualiza) en el ranking de vendidos.

    `nicho` lo elige el operador: el mismo producto se graba con varios nichos
    y solo él sabe con cuál vendió. Si no llega, se conserva el que ya tuviera
    y si no había ninguno queda vacío (= "sin atribuir"), que en el ranking se
    ve igual pero no cuenta para ningún nicho.
    """
    r = _require_redis()
    ref = _ref_vendido(source, folder, producto)
    doc = r.get_json(_key_vendido(ref, usuario)) or {}
    doc.update({
        "source": source, "folder": folder, "producto": producto,
        "titulo": titulo or doc.get("titulo", ""),
        "tienda": tienda or doc.get("tienda", ""),
        "clean_photo_id": clean_photo_id or doc.get("clean_photo_id", ""),
        "product_url": product_url or doc.get("product_url", ""),
        "nicho": (nicho or doc.get("nicho") or "").strip(),
        "unidades": max(1, int(doc.get("unidades") or 0) or unidades),
        "vendido_at": doc.get("vendido_at") or time.time(),
        "updated_at": time.time(),
    })
    r.set_json(_key_vendido(ref, usuario), doc)
    r.sadd(_key_vendidos_index(usuario), ref)
    return doc


def mover_venta(
    source: str, folder: str, viejo: str, nuevo: str, usuario: str = "",
) -> None:
    """Cambia de número la venta de un producto (o la borra si no hay nuevo).

    Hace falta al renumerar "Mis productos": la venta vive en un documento por
    referencia `fuente|carpeta|producto`, así que cerrar un hueco sin mover
    esto dejaría el ranking apuntando a un producto que ya no existe.
    """
    r = get_nicho_pov_bof_redis()
    if not r.is_available():
        return
    ref_v = _ref_vendido(source, folder, viejo)
    doc = r.get_json(_key_vendido(ref_v, usuario))
    r.delete(_key_vendido(ref_v, usuario))
    r.srem(_key_vendidos_index(usuario), ref_v)
    if not doc or not nuevo:
        return
    doc["producto"] = nuevo
    ref_n = _ref_vendido(source, folder, nuevo)
    r.set_json(_key_vendido(ref_n, usuario), doc)
    r.sadd(_key_vendidos_index(usuario), ref_n)


def desmarcar_vendido(
    source: str, folder: str, producto: str, usuario: str = "",
) -> None:
    r = _require_redis()
    ref = _ref_vendido(source, folder, producto)
    r.delete(_key_vendido(ref, usuario))
    r.srem(_key_vendidos_index(usuario), ref)


def sumar_unidades(
    source: str, folder: str, producto: str, delta: int, usuario: str = "",
) -> dict:
    """Suma (o resta) unidades vendidas. Nunca baja de 1.

    Existe porque un producto que repite venta es la señal más valiosa que hay
    aquí, y no había forma de anotarla: el armario vendió una segunda unidad y
    se quedaba como "1 venta" igual que los que solo vendieron una vez.
    """
    r = _require_redis()
    ref = _ref_vendido(source, folder, producto)
    doc = r.get_json(_key_vendido(ref, usuario))
    if not doc:
        raise ValueError("Ese producto no está marcado como vendido.")
    doc["unidades"] = max(1, int(doc.get("unidades") or 1) + int(delta))
    doc["updated_at"] = time.time()
    r.set_json(_key_vendido(ref, usuario), doc)
    return doc


def ranking_vendidos(nicho: str = "", usuario: str = "") -> list[dict]:
    """Vendidos de más a menos unidades. Dos llamadas a Redis.

    `nicho` vacío = TODOS mezclados, que es la vista por defecto. Con nicho se
    filtra a las ventas atribuidas a ese.
    """
    r = get_nicho_pov_bof_redis()
    if not r.is_available():
        return []
    refs = [str(x) for x in r.smembers(_key_vendidos_index(usuario)) if x]
    if not refs:
        return []
    docs = r.mget_json([_key_vendido(ref, usuario) for ref in refs])
    salida = [d for d in docs if isinstance(d, dict)]
    if nicho:
        salida = [d for d in salida if (d.get("nicho") or "") == nicho]
    salida.sort(
        key=lambda d: (int(d.get("unidades") or 1), d.get("vendido_at") or 0),
        reverse=True,
    )
    return salida
