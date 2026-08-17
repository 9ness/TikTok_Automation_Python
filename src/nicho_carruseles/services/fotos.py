"""Las fotos del carrusel en el Drive del operador: guardarlas, encontrarlas y
repartir la tanda de chicas entre los productos.

Cuatro tipos por producto (`config.SUBCARPETAS`): la chica y el producto, y sus
dos versiones con el texto ya quemado. Todas se llaman igual —
`<fuente>__<carpeta>__<producto>.<ext>` — así que el nombre del fichero ES el
vínculo con el producto: no hace falta un índice en Redis que se pueda
desincronizar del Drive, y si alguien mira la carpeta desde Drive entiende qué
es cada foto.

**El reparto de la tanda de chicas.** La foto 1 no depende del producto: el
operador genera 78 chicas de golpe en Flow y las sube todas juntas, sin saber
—ni tener por qué saber— cuál va con cuál. Se asignan por orden a los productos
aptos que aún no tienen: es lo único que hace que subir 78 ficheros sea un solo
gesto en vez de 78.
"""

from __future__ import annotations

import re
import time
import unicodedata
from pathlib import Path

from src.nicho_carruseles import config

_EXTS = (".jpg", ".jpeg", ".png", ".webp")

# ---------------------------------------------------------------------------
# Índice por carpeta
# ---------------------------------------------------------------------------
# Estas carpetas viven en el Drive MONTADO, donde cada `stat()` en frío se paga
# contra Google. Preguntar foto a foto era inviable: pintar una carpeta son 10
# productos × 4 tipos × 4 extensiones = 160 comprobaciones, y saber cuántas
# chicas faltan en una fuente entera pasaba de mil.
#
# Se lista cada carpeta UNA vez (`iterdir`) y se resuelve todo contra ese
# diccionario. Escribir NO tira el índice: se corrige la entrada que cambia
# (`_apuntar` / `_olvidar`), porque volver a listar las cuatro carpetas del
# Drive montado son decenas de segundos y se pagaban después de CADA foto
# subida o quemada. El TTL solo cubre el caso de tocar el Drive a mano.
# Mismo patrón que `nicho_pov_bof.services.mis_productos`.
_TTL_S = 600.0
_INDICES: dict[tuple[str, str], tuple[float, dict[str, Path]]] = {}


def _listar(tipo: str, usuario: str) -> dict[str, Path]:
    """Lee la carpeta del Drive. Es LA operación cara de este módulo."""
    base = config.carpeta_de(tipo, usuario)
    return {
        f.stem: f
        for f in base.iterdir()
        if f.is_file() and f.suffix.lower() in _EXTS
    }


def _indice(tipo: str, usuario: str) -> dict[str, Path]:
    """`{nombre_sin_extension: ruta}` de todas las fotos de ese tipo."""
    clave = (tipo, usuario or "ness")
    hit = _INDICES.get(clave)
    if hit and time.monotonic() < hit[0]:
        return hit[1]
    mapa = _listar(tipo, usuario)
    _INDICES[clave] = (time.monotonic() + _TTL_S, mapa)
    return mapa


def invalidar(tipo: str = "", usuario: str = "") -> None:
    """Tira el índice a mano. Lo usa el reparto de tandas antes de decidir a
    quién le toca cada foto: la lista tiene que salir del disco, no de hace un
    minuto."""
    _invalidar(tipo, usuario)


def _invalidar(tipo: str = "", usuario: str = "") -> None:
    """Tras escribir. Sin argumentos tira el índice entero."""
    if not tipo:
        _INDICES.clear()
        return
    _INDICES.pop((tipo, usuario or "ness"), None)


def _apuntar(tipo: str, usuario: str, nombre: str, ruta: Path) -> None:
    """Mete una foto recién guardada en el índice que ya está en memoria."""
    hit = _INDICES.get((tipo, usuario or "ness"))
    if hit:
        hit[1][nombre] = ruta


def _olvidar(tipo: str, usuario: str, nombre: str) -> None:
    """Quita del índice una foto recién borrada."""
    hit = _INDICES.get((tipo, usuario or "ness"))
    if hit:
        hit[1].pop(nombre, None)


# Cada cuánto se repasa el Drive para tener el índice listo antes de que lo
# pidan. Menos que `_TTL_S` a propósito: así nunca se encuentra vencido.
_REFRESCO_S = 300.0


def precalentar(usuario: str = "ness") -> int:
    """Rehace los cuatro índices de ese usuario. Devuelve cuántas fotos hay.

    Listar las carpetas del Drive montado en frío cuesta un minuto largo, y
    hasta ahora lo pagaba quien abriera la pantalla justo después de un
    despliegue. Se llama al arrancar y cada pocos minutos.
    """
    total = 0
    for tipo in config.SUBCARPETAS:
        # Se lista ANTES de tocar el índice vivo: si se tirara primero, quien
        # entrase durante el minuto que tarda se pondría a listar también.
        mapa = _listar(tipo, usuario)
        _INDICES[(tipo, usuario or "ness")] = (time.monotonic() + _TTL_S, mapa)
        total += len(mapa)

    # Las referencias viven en la carpeta de al lado y las pide la misma
    # pantalla: en frío son otros cuarenta segundos.
    from src.nicho_carruseles.services import referencia

    try:
        referencia.estado(usuario, refrescar=True)
    except Exception:  # noqa: BLE001 — es un adelanto, no un requisito
        pass
    return total


async def bucle_precalentado(stop) -> None:
    """Mantiene calientes los índices mientras la API viva.

    El `to_thread` no es decorativo: `iterdir()` sobre el mount bloquea
    decenas de segundos y en el loop de asyncio se llevaría por delante a
    todas las peticiones en curso (mismo motivo que en "Mis productos").
    """
    import asyncio
    import logging

    log = logging.getLogger("api")
    while not stop.is_set():
        try:
            n = await asyncio.to_thread(precalentar)
            log.debug("carruseles precalentado: %d fotos", n)
        except Exception as e:  # Drive caído, permisos… no es motivo de caída
            log.warning("precalentado de carruseles falló: %s", e)
        try:
            await asyncio.wait_for(stop.wait(), timeout=_REFRESCO_S)
        except asyncio.TimeoutError:
            pass


def _slug(texto: str) -> str:
    """Minúsculas, sin acentos y sin nada que moleste en un nombre de fichero.

    Mismo criterio que los slugs de stock del proyecto: las carpetas del curso
    se llaman "1 Pront Flow" o "Camisetas／Conjuntos" y esos nombres no pueden
    viajar tal cual a un fichero.
    """
    plano = unicodedata.normalize("NFKD", str(texto or "").lower())
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", plano).strip("_")


def ref(source: str, folder: str, producto: str) -> str:
    """El nombre (sin extensión) con el que vive la foto de ese producto."""
    return f"{_slug(source)}__{_slug(folder)}__{_slug(producto)}"


def buscar(tipo: str, usuario: str, source: str, folder: str, producto: str) -> Path | None:
    """La foto de ese producto, sea cual sea su extensión. `None` si no está."""
    return _indice(tipo, usuario).get(ref(source, folder, producto))


def _extension(filename: str) -> str:
    ext = Path(filename or "").suffix.lower()
    return ext if ext in _EXTS else ".jpg"


def guardar(
    tipo: str, usuario: str, source: str, folder: str, producto: str,
    datos: bytes, *, filename: str = "",
) -> Path:
    """Guarda (o sustituye) la foto de un producto.

    Sustituir borra primero las de OTRA extensión: si no, subir un .png encima
    de un .jpg dejaba las dos y `buscar` seguía devolviendo la vieja.
    """
    base = config.carpeta_de(tipo, usuario)
    nombre = ref(source, folder, producto)
    for ext in _EXTS:
        (base / f"{nombre}{ext}").unlink(missing_ok=True)
    destino = base / f"{nombre}{_extension(filename)}"
    destino.write_bytes(datos)
    _apuntar(tipo, usuario, nombre, destino)
    return destino


def borrar(tipo: str, usuario: str, source: str, folder: str, producto: str) -> bool:
    """Quita la foto de ese tipo. Devuelve si había algo que borrar."""
    p = buscar(tipo, usuario, source, folder, producto)
    if not p:
        return False
    p.unlink(missing_ok=True)
    _olvidar(tipo, usuario, ref(source, folder, producto))
    return True


def estado(usuario: str, source: str, folder: str, producto: str) -> dict:
    """Qué fotos tiene ya este producto, para pintar la tarjeta.

    Cada una lleva su `mtime` pegado: es lo que deja cachear la foto en el móvil
    y aun así ver la nueva al sustituirla (mismo truco que "Mis productos").
    """
    nombre = ref(source, folder, producto)
    out: dict[str, str] = {}
    for tipo in config.SUBCARPETAS:
        p = _indice(tipo, usuario).get(nombre)
        out[tipo] = f"{int(p.stat().st_mtime)}" if p else ""
    return out


def tiene(tipo: str, usuario: str, source: str, folder: str, producto: str) -> bool:
    """Como `buscar` pero sin tocar el disco más allá del índice.

    Existe para el recuento de chicas pendientes, que pregunta por cientos de
    productos seguidos.
    """
    return ref(source, folder, producto) in _indice(tipo, usuario)


def repartir_chicas(
    usuario: str, pendientes: list[dict], archivos: list[tuple[str, bytes]],
) -> list[dict]:
    """Reparte una tanda de fotos de chica entre los productos que no tienen.

    `pendientes` son `{source, folder, producto}` YA ordenados por quien llama
    (carpeta y número), que es el orden en el que se van a trabajar. Sobran
    fotos o sobran productos sin que pase nada: se asigna lo que da de sí la
    lista más corta y el resto se informa.
    """
    asignados: list[dict] = []
    fotos = list(archivos)
    for destino in pendientes:
        if not fotos:
            break
        # Cierre de seguridad: si el que llama trae una lista de pendientes
        # vieja —pasó con la tanda en trozos, donde el trozo 2 recibía los
        # mismos productos que el 1—, la foto se pondría ENCIMA de otra y de 20
        # fotos entrarían 8. Aquí se comprueba contra el disco.
        if tiene("chica", usuario, destino["source"], destino["folder"], destino["producto"]):
            continue
        filename, datos = fotos.pop(0)
        ruta = guardar(
            "chica", usuario, destino["source"], destino["folder"],
            destino["producto"], datos, filename=filename,
        )
        asignados.append({**destino, "archivo": ruta.name, "mtime": int(ruta.stat().st_mtime)})
    return asignados


def quemar_texto(
    tipo: str, usuario: str, source: str, folder: str, producto: str, texto: str,
) -> Path:
    """Escribe el mensaje sobre la foto original y guarda la versión con texto.

    `tipo` es la foto de partida ("chica" o "producto"); la salida va siempre a
    su carpeta `_txt`, para no perder el original (ver `texto_foto.quemar`).
    """
    from src.nicho_carruseles.services import texto_foto

    origen = buscar(tipo, usuario, source, folder, producto)
    if not origen:
        raise ValueError("todavía no has subido esa foto")
    destino = (
        config.carpeta_de(f"{tipo}_txt", usuario)
        / f"{ref(source, folder, producto)}.jpg"
    )
    # Se borra antes: si la anterior era .png y la nueva .jpg, quedarían dos y
    # `buscar` podría devolver la vieja.
    for ext in _EXTS:
        (destino.parent / f"{ref(source, folder, producto)}{ext}").unlink(missing_ok=True)
    salida = texto_foto.quemar(origen, texto, destino)
    _apuntar(f"{tipo}_txt", usuario, ref(source, folder, producto), salida)
    return salida


def limpiar_texto(usuario: str, source: str, folder: str, producto: str) -> None:
    """Tira las versiones quemadas (el mensaje cambió y hay que rehacerlas)."""
    for tipo in ("chica_txt", "producto_txt"):
        borrar(tipo, usuario, source, folder, producto)


# ---------------------------------------------------------------------------
# Fotos de producto que la IA no supo colocar
# ---------------------------------------------------------------------------
# No se tiran: son generaciones de Flow que han costado su rato. Se guardan
# aparte y la pantalla las enseña para asignarlas a mano.
def guardar_sin_asignar(usuario: str, datos: bytes, *, filename: str = "") -> Path:
    base = config.carpeta_sin_asignar(usuario)
    limpio = _slug(Path(filename or "foto").stem) or "foto"
    ext = _extension(filename)
    destino = base / f"{limpio}{ext}"
    # Dos tandas seguidas de Flow traen ficheros con el mismo nombre
    # (`imagen_1.png`): sin esto la segunda pisaría a la primera.
    n = 2
    while destino.is_file():
        destino = base / f"{limpio}_{n}{ext}"
        n += 1
    destino.write_bytes(datos)
    return destino


def listar_sin_asignar(usuario: str) -> list[dict]:
    base = config.carpeta_sin_asignar(usuario)
    fotos = [
        {"archivo": f.name, "version": str(int(f.stat().st_mtime))}
        for f in base.iterdir()
        if f.is_file() and f.suffix.lower() in _EXTS
    ]
    fotos.sort(key=lambda d: d["archivo"])
    return fotos


def ruta_sin_asignar(usuario: str, archivo: str) -> Path | None:
    """La foto por su nombre. `None` si no está o si el nombre es una trampa
    (`../`): lo manda el cliente y nunca se concatena a ciegas."""
    nombre = Path(str(archivo or "")).name
    if not nombre:
        return None
    p = config.carpeta_sin_asignar(usuario) / nombre
    return p if p.is_file() else None


def asignar_sin_asignar(
    usuario: str, archivo: str, source: str, folder: str, producto: str,
) -> Path:
    """Coloca una foto suelta en su producto."""
    origen = ruta_sin_asignar(usuario, archivo)
    if not origen:
        raise ValueError("esa foto ya no está")
    destino = guardar(
        "producto", usuario, source, folder, producto, origen.read_bytes(),
        filename=origen.name,
    )
    origen.unlink(missing_ok=True)
    # La versión con texto era de la foto que hubiera antes.
    borrar("producto_txt", usuario, source, folder, producto)
    return destino


def nombre_descarga(source: str, folder: str, producto: str, pos: int) -> str:
    """Cómo se llama la foto al bajarla: `<carpeta>_<producto>_1.jpg`.

    Con el número delante para que al subirlas a TikTok desde la galería salgan
    en orden — la 1 es la chica y la 2 el producto, y al revés el carrusel no
    tiene sentido.
    """
    base = f"{_slug(folder)}_{_slug(producto)}_{pos}"
    return f"{base}.jpg"
