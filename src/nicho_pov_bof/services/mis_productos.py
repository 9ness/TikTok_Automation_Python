"""Productos que sube el OPERADOR, como una fuente más del Nicho POV BOF.

Las otras dos fuentes ("1 Prod Aleatorios", "2 Prod Aleatorios 2") son carpetas
del Drive del curso, de solo lectura. Esta es la suya: sube la foto limpia y la
captura de la ficha, y a partir de ahí el producto se comporta EXACTAMENTE
igual que uno del curso.

**El truco está en el nombre de los ficheros.** Las fotos se guardan con el
mismo convenio que el Drive compartido —`3.png` la limpia y `3(1).png` la
ficha—, así que `photo_pairing` las empareja sin saber de dónde salieron y todo
lo de después (textos con Gemini, caption, gancho/CTA, escaparate, vendidos,
montaje del vídeo) funciona sin una línea de código extra. Cualquier tentación
de inventar aquí otro convenio se paga en los seis sitios que leen fotos.

Las carpetas se llenan de DIEZ en diez, como las del curso: pasado ese tope se
abre "Mis Productos 2", "Mis Productos 3"… Una carpeta de 200 productos no hay
quien la mire.
"""

from __future__ import annotations

import re
import shutil
import time
from pathlib import Path
from typing import Any, Callable

from src.nicho_pov_bof import config

_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
_PREFIJO = "Mis Productos"

# ---------------------------------------------------------------------------
# Caché de listados
# ---------------------------------------------------------------------------
# Estas carpetas viven en el Drive MONTADO, y tocar por primera vez una ruta
# honda del mount cuesta CARO: medido, 37s para un simple `is_dir()` sobre una
# ruta que rclone no tenía cacheada. Da igual la llamada —`mkdir`, `stat`,
# `iterdir`—, lo que se paga es que rclone resuelva la ruta contra Google.
#
# Las fuentes del curso ya esquivan esto con su caché de dos capas
# (`drive_client`), pero la rama de "Mis productos" se la saltaba entera y por
# eso la pantalla tardaba ~36s en salir frente a los 0,45s de las otras.
#
# Aquí basta con una caché en memoria, PERO con una diferencia que las del
# curso no necesitan: esta carpeta se ESCRIBE. Si el operador sube un producto
# y el listado sigue cacheado, sube y no lo ve. Por eso cualquier escritura la
# invalida entera (`_invalidar`), en vez de esperar al TTL.
#
# El TTL es largo A PROPÓSITO. Con uno corto, quien entrara pasados dos minutos
# volvía a pagar los 20-37s, que es justo la queja original; y como el único
# que escribe aquí es la propia app —y avisa—, lo que protege el TTL es solo el
# caso raro de tocar la carpeta a mano en Drive. Encima va `bucle_precalentado`
# refrescándolo antes de que venza, así que en la práctica nunca se enfría.
_TTL_S = 900.0
_LISTADOS: dict[str, tuple[float, Any]] = {}


def _memo(clave: str, calcular: Callable[[], Any]) -> Any:
    hit = _LISTADOS.get(clave)
    if hit and time.monotonic() < hit[0]:
        return hit[1]
    valor = calcular()
    _LISTADOS[clave] = (time.monotonic() + _TTL_S, valor)
    return valor


def _invalidar() -> None:
    """Tras escribir. Se tira todo: son cuatro entradas, no compensa hilar."""
    _LISTADOS.clear()


def _num_carpeta(nombre: str) -> int:
    m = re.search(r"(\d+)\s*$", nombre or "")
    return int(m.group(1)) if m else 0


def carpetas() -> list[str]:
    """Carpetas existentes, en orden natural. Vacío si aún no hay ninguna."""

    def leer() -> list[str]:
        raiz = config.mis_productos_dir()
        if not raiz.is_dir():
            return []
        return sorted(
            (d.name for d in raiz.iterdir() if d.is_dir() and not d.name.startswith(".")),
            key=_num_carpeta,
        )

    return _memo("carpetas", leer)


def _productos_en(carpeta: str) -> set[str]:
    """Números de producto que ya hay en la carpeta (por nombre de fichero)."""
    d = config.mis_productos_dir() / carpeta
    if not d.is_dir():
        return set()
    numeros: set[str] = set()
    for f in d.iterdir():
        if f.is_file() and f.suffix.lower() in _EXTS:
            m = re.match(r"^(\d+)", f.stem)
            if m:
                numeros.add(m.group(1))
    return numeros


def carpeta_actual() -> str:
    """La carpeta donde toca guardar: la última con hueco, o una nueva.

    Se mira cuántos PRODUCTOS hay (no cuántos ficheros): cada producto son dos
    fotos, y contando ficheros la carpeta se daría por llena a la mitad.
    """
    existentes = carpetas()
    if existentes:
        ultima = existentes[-1]
        if len(_productos_en(ultima)) < config.MIS_PRODUCTOS_POR_CARPETA:
            return ultima
        return f"{_PREFIJO} {_num_carpeta(ultima) + 1}"
    return f"{_PREFIJO} 1"


def siguiente_producto(carpeta: str) -> str:
    """Número del próximo producto DENTRO de esa carpeta (1..10)."""
    usados = {int(n) for n in _productos_en(carpeta) if n.isdigit()}
    return str(1 + max(usados, default=0))


def _extension(filename: str) -> str:
    ext = Path(filename or "").suffix.lower()
    return ext if ext in _EXTS else ".jpg"


def guardar_producto(
    limpia: bytes, ficha: bytes | None, *,
    nombre_limpia: str = "", nombre_ficha: str = "",
) -> dict:
    """Guarda las dos fotos y devuelve `{carpeta, producto}`.

    La ficha es opcional: sin ella el producto existe igual y el título se
    escribe a mano (o se reintenta luego con otra captura).
    """
    carpeta = carpeta_actual()
    destino = config.mis_productos_dir() / carpeta
    destino.mkdir(parents=True, exist_ok=True)
    producto = siguiente_producto(carpeta)

    # `3.png` y `3(1).png`: EL MISMO convenio del Drive del curso. De aquí
    # depende que el emparejado y todo lo de después funcionen sin tocarse.
    (destino / f"{producto}{_extension(nombre_limpia)}").write_bytes(limpia)
    if ficha:
        (destino / f"{producto}(1){_extension(nombre_ficha)}").write_bytes(ficha)

    # Sin esto el operador sube el producto y no lo ve hasta que vence el TTL.
    _invalidar()
    return {"carpeta": carpeta, "producto": producto}


def borrar_producto(carpeta: str, producto: str, *, renumerar: bool = True) -> bool:
    """Quita las fotos de un producto y CIERRA EL HUECO que deja.

    Sin renumerar, borrar el 6 dejaba la carpeta en 5, 7, 8… y el operador se
    encuentra con una numeración con agujeros que no cuadra con nada. Al cerrar
    el hueco hay que arrastrar lo que cada nicho guarda de esos productos
    (textos, guion, clips, vídeo, subidos, ventas): el número ES la identidad
    del producto, así que renombrar solo los ficheros le pondría a uno los
    textos del siguiente. Ver `_renumerar`.
    """
    d = config.mis_productos_dir() / carpeta
    if not d.is_dir():
        return False
    borradas = 0
    for f in list(d.iterdir()):
        if f.is_file() and re.match(rf"^{re.escape(producto)}(\(\d+\))?$", f.stem):
            f.unlink(missing_ok=True)
            borradas += 1
    if not borradas:
        return False
    if renumerar:
        renumerar_carpeta(carpeta)
    _invalidar()
    return True


def _numeros(carpeta: str) -> list[int]:
    """Los números de producto que hay HOY en la carpeta, ordenados."""
    d = config.mis_productos_dir() / carpeta
    if not d.is_dir():
        return []
    vistos = set()
    for f in d.iterdir():
        if not f.is_file() or not config.is_image(f.name):
            continue
        m = re.match(r"^(\d+)", f.stem)
        if m:
            vistos.add(int(m.group(1)))
    return sorted(vistos)


def renumerar_carpeta(carpeta: str) -> dict[str, str]:
    """Cierra los huecos: 5, 7, 8 → 5, 6, 7. Devuelve el mapa viejo→nuevo.

    Se llama al borrar, y también a mano desde la pantalla para arreglar los
    huecos que dejaron los borrados de antes de que esto existiera.

    Renombra las fotos y mueve TODO lo que está guardado con ese número. Se va
    de menor a mayor y el nuevo número siempre es menor que el viejo, así que
    ningún renombrado pisa a otro.
    """
    numeros = _numeros(carpeta)
    mapa = {
        str(viejo): str(nuevo)
        for nuevo, viejo in enumerate(numeros, start=1)
        if str(nuevo) != str(viejo)
    }
    if not mapa:
        return {}
    # Los que HOY tienen fotos. Lo guardado de cualquier otro número es de un
    # producto que ya no está: se tira. Si no, al cerrar el hueco del 6 el
    # texto viejo del 6 chocaría con el 7 que pasa a ser 6.
    validos = {str(n) for n in numeros}

    d = config.mis_productos_dir() / carpeta
    for viejo, nuevo in mapa.items():
        for f in sorted(d.iterdir()):
            if not f.is_file():
                continue
            m = re.match(rf"^{re.escape(viejo)}(\(\d+\))?$", f.stem)
            if m:
                f.rename(d / f"{nuevo}{m.group(1) or ''}{f.suffix}")
    _mover_datos(carpeta, mapa, validos)
    return mapa


def _mover_datos(carpeta: str, mapa: dict[str, str], validos: set[str]) -> None:
    """Arrastra a su número nuevo lo que cada nicho guarda de esos productos.

    Todo lo de aquí es "si falla, que no impida borrar": las fotos ya están
    renombradas y dejar un texto viejo es menos grave que reventar la pantalla.
    """
    from src.api import users as _users

    fuente = "mis_productos"
    usuarios = list(_users.USUARIOS) + [""]

    def _rehacer(productos: dict) -> dict:
        """Aplica el mapa a un `{producto: datos}` y tira lo que ya no existe."""
        salida = {}
        for pid, valor in productos.items():
            if str(pid) not in validos:
                continue
            salida[mapa.get(str(pid), str(pid))] = valor
        return salida

    # 1) Documentos con `productos` dentro: textos del POV BOF (compartido y
    #    privado) y lo del POV BOF Largo (guion, clips, vídeo).
    from src.nicho_pov_bof.repos.redis_base import get_nicho_pov_bof_redis
    from src.nicho_pov_bof_largo.repos.redis_base import get_nicho_pov_bof_largo_redis

    # OJO con los repetidos: aplicar el mapa dos veces al mismo documento
    # volvería a correr los números (el 7 pasa a 6 y luego el 6 a 5). Por eso
    # se juntan por (nicho, clave) antes de tocar nada.
    docs: dict[tuple[str, str], Any] = {}
    docs[("pov", f"folder:{fuente}:{carpeta}")] = get_nicho_pov_bof_redis()
    for u in usuarios:
        if u:
            docs[("pov", f"folder:{fuente}:{carpeta}:u:{u}")] = get_nicho_pov_bof_redis()
        docs[("largo", f"folder:{fuente}:{carpeta}:u:{u or 'ness'}")] = (
            get_nicho_pov_bof_largo_redis()
        )
    for (_nicho, clave), r in docs.items():
        try:
            if not r.is_available():
                continue
            doc = r.get_json(clave)
            if not doc or not doc.get("productos"):
                continue
            doc["productos"] = _rehacer(doc["productos"])
            r.set_json(clave, doc)
        except Exception:  # noqa: BLE001
            continue

    # 2) Creativos Pro: `{producto: hora}` de los ya publicados.
    try:
        from src.nicho_creativos.repos.redis_base import get_nicho_creativos_redis

        rc = get_nicho_creativos_redis()
        if rc.is_available():
            claves = {
                f"subidos:{fuente}:{carpeta}" + (f":{u}" if u and u != "ness" else "")
                for u in usuarios
            }
            for clave in claves:
                doc = rc.get_json(clave)
                if doc:
                    rc.set_json(clave, _rehacer(doc))
    except Exception:  # noqa: BLE001
        pass

    # 3) Ventas: viven en un documento por referencia `fuente|carpeta|numero`,
    #    así que se mueven de número para no dejar el ranking colgando.
    try:
        from src.nicho_pov_bof.repos import product_repo as pov

        for viejo, nuevo in mapa.items():
            pov.mover_venta(fuente, carpeta, viejo, nuevo)
    except Exception:  # noqa: BLE001
        pass


def listar_carpetas_como_drive() -> list[dict]:
    """Mismo shape que `drive_client.list_product_folders`."""
    return [{"name": c, "id": c} for c in carpetas()]


def listar_fotos_como_drive(carpeta: str) -> list[dict]:
    """Mismo shape que `drive_client.list_photos`.

    El `id` es la RUTA del fichero: en el Drive compartido el id lo pone
    Google, aquí no hay tal cosa y la ruta es igual de única. `fetch_photo` lo
    detecta y sirve el fichero directamente.
    """

    def leer() -> list[dict]:
        d = config.mis_productos_dir() / carpeta
        if not d.is_dir():
            return []
        fotos = [
            {
                # El id lleva pegada la fecha del fichero: es lo que permite
                # cachear la foto un día entero en el móvil sin arriesgarse a
                # ver una vieja. Al sustituirla cambia el mtime, con él la URL,
                # y el navegador la vuelve a pedir. Sin esto había que servirlas
                # con `no-cache` y se rebajaban en cada scroll.
                "id": f"{f}#{int(f.stat().st_mtime)}",
                "name": f.name,
                "size": f.stat().st_size,
                "mime": "image/png" if f.suffix.lower() == ".png" else "image/jpeg",
                "mtime": "",
            }
            for f in d.iterdir()
            if f.is_file() and f.suffix.lower() in _EXTS
        ]
        fotos.sort(key=lambda p: config.natural_sort_key(p["name"]))
        return fotos

    return _memo(f"fotos:{carpeta}", leer)


# ---------------------------------------------------------------------------
# Precalentado
# ---------------------------------------------------------------------------
# La caché de arriba deja la pantalla en <1s… mientras esté caliente. En frío
# sigue costando 20-37s, y en frío está siempre justo después de un deploy o
# tras un rato sin entrar, que es EXACTAMENTE cuando el operador abre la app.
#
# Por eso se refresca desde fuera: al arrancar la API y luego cada pocos
# minutos, antes de que venza el TTL. Es una llamada a rclone cada 10 min —
# nada al lado de lo que ya hace el mount (`--poll-interval 15s`).
_REFRESCO_S = 600.0


def precalentar() -> int:
    """Recalcula el listado y renueva la caché, esté fresca o no.

    Devuelve cuántas carpetas hay (para el log). Llamar a `carpetas()` a secas
    NO valdría: si la caché aún vive, devuelve lo cacheado sin renovar la
    fecha de caducidad, y el TTL vencería igual con el operador delante.
    """
    _LISTADOS.pop("carpetas", None)
    nombres = carpetas()
    if nombres:
        # También las fotos de la última carpeta, que es la que se abre: son
        # un nivel más hondo del mount y se pagan aparte.
        ultima = nombres[-1]
        _LISTADOS.pop(f"fotos:{ultima}", None)
        listar_fotos_como_drive(ultima)
    return len(nombres)


async def bucle_precalentado(stop) -> None:
    """Mantiene caliente el listado mientras la API viva.

    El `to_thread` no es decorativo: `iterdir()` sobre el mount bloquea
    decenas de segundos y en el loop de asyncio se llevaría por delante a
    todas las peticiones en curso.
    """
    import asyncio
    import logging

    log = logging.getLogger("api")
    while not stop.is_set():
        try:
            n = await asyncio.to_thread(precalentar)
            log.debug("mis_productos precalentado: %d carpetas", n)
        except Exception as e:  # Drive caído, permisos… no es motivo de caída
            log.warning("precalentado de mis_productos falló: %s", e)
        try:
            await asyncio.wait_for(stop.wait(), timeout=_REFRESCO_S)
        except asyncio.TimeoutError:
            pass


def copiar_a(destino: Path, foto_id: str) -> Path:
    """`fetch_photo` para fotos propias: ya están en disco, solo se copian."""
    origen = Path(foto_id)
    if not origen.is_file():
        raise ValueError(f"no está la foto: {foto_id}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(origen, destino)
    return destino
