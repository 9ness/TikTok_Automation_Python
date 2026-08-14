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
    """
    data = load_folder(source, folder)
    productos = data.setdefault("productos", {})
    for prod_id, campos in textos.items():
        prod = productos.setdefault(prod_id, {})
        prod.update(campos)
        prod["textos_at"] = _now()
    data["textos_extraidos"] = True
    save_folder(source, folder, data)


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


def marcado_en_escaparate(prod: dict, indice: set[str]) -> bool:
    """¿Este producto está en el escaparate? ÚNICO criterio para todos los nichos.

    Manda el índice compartido, pero se acepta también la marca antigua que
    vive dentro del producto (`en_escaparate`), de cuando el escaparate era de
    cada carpeta. Hacía falta unificarlo: el POV BOF miraba las dos cosas y el
    Largo solo el índice, así que la misma carpeta salía llena en uno y a cero
    en el otro.

    Los dos datos se separan cuando se re-extraen los textos: la clave del
    índice es `tienda|titulo` y al cambiar el título la marca vieja queda
    huérfana. Por eso no basta con el índice, y por eso existe
    `scripts/migrar_escaparate.py`, que reengancha las huérfanas.
    """
    if bool(prod.get("en_escaparate")):
        return True
    titulo = prod.get("titulo", "")
    if not titulo:
        return False
    return clave_escaparate(prod.get("tienda", ""), titulo) in indice


def clave_escaparate(tienda: str, titulo: str) -> str:
    """`tienda|nombre` normalizados. Vacía si no hay nombre — sin textos
    extraídos todavía no se puede saber si dos productos son el mismo."""
    nombre = " ".join(_normaliza(titulo).split())
    if not nombre:
        return ""
    return f"{' '.join(_normaliza(tienda).split())}|{nombre}"


def _key_escaparate(usuario: str = "") -> str:
    if _es_compartido(usuario):
        return _ESCAPARATE_INDEX
    return f"{_ESCAPARATE_INDEX}:{usuario}"


def escaparate_index(usuario: str = "") -> set[str]:
    """Claves de los productos ya metidos en el escaparate por ese usuario."""
    r = get_nicho_pov_bof_redis()
    if not r.is_available():
        return set()
    return {str(x) for x in r.smembers(_key_escaparate(usuario)) if x}


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


def _key_vendido(ref: str) -> str:
    return f"vendido:{ref}"


def marcar_vendido(
    source: str, folder: str, producto: str,
    *, titulo: str = "", tienda: str = "", clean_photo_id: str = "",
    product_url: str = "", unidades: int = 1, nicho: str = "",
) -> dict:
    """Entra (o actualiza) en el ranking de vendidos.

    `nicho` lo elige el operador: el mismo producto se graba con varios nichos
    y solo él sabe con cuál vendió. Si no llega, se conserva el que ya tuviera
    y si no había ninguno queda vacío (= "sin atribuir"), que en el ranking se
    ve igual pero no cuenta para ningún nicho.
    """
    r = _require_redis()
    ref = _ref_vendido(source, folder, producto)
    doc = r.get_json(_key_vendido(ref)) or {}
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
    r.set_json(_key_vendido(ref), doc)
    r.sadd(_VENDIDOS_INDEX, ref)
    return doc


def desmarcar_vendido(source: str, folder: str, producto: str) -> None:
    r = _require_redis()
    ref = _ref_vendido(source, folder, producto)
    r.delete(_key_vendido(ref))
    r.srem(_VENDIDOS_INDEX, ref)


def sumar_unidades(source: str, folder: str, producto: str, delta: int) -> dict:
    """Suma (o resta) unidades vendidas. Nunca baja de 1.

    Existe porque un producto que repite venta es la señal más valiosa que hay
    aquí, y no había forma de anotarla: el armario vendió una segunda unidad y
    se quedaba como "1 venta" igual que los que solo vendieron una vez.
    """
    r = _require_redis()
    ref = _ref_vendido(source, folder, producto)
    doc = r.get_json(_key_vendido(ref))
    if not doc:
        raise ValueError("Ese producto no está marcado como vendido.")
    doc["unidades"] = max(1, int(doc.get("unidades") or 1) + int(delta))
    doc["updated_at"] = time.time()
    r.set_json(_key_vendido(ref), doc)
    return doc


def ranking_vendidos(nicho: str = "") -> list[dict]:
    """Vendidos de más a menos unidades. Dos llamadas a Redis.

    `nicho` vacío = TODOS mezclados, que es la vista por defecto. Con nicho se
    filtra a las ventas atribuidas a ese.
    """
    r = get_nicho_pov_bof_redis()
    if not r.is_available():
        return []
    refs = [str(x) for x in r.smembers(_VENDIDOS_INDEX) if x]
    if not refs:
        return []
    docs = r.mget_json([_key_vendido(ref) for ref in refs])
    salida = [d for d in docs if isinstance(d, dict)]
    if nicho:
        salida = [d for d in salida if (d.get("nicho") or "") == nicho]
    salida.sort(
        key=lambda d: (int(d.get("unidades") or 1), d.get("vendido_at") or 0),
        reverse=True,
    )
    return salida
