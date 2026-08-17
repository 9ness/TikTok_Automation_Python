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
# diccionario. El TTL es corto porque aquí escribe la propia app: cualquier
# escritura invalida (`_invalidar`) y el TTL solo cubre el caso de tocar el
# Drive a mano. Mismo patrón que `nicho_pov_bof.services.mis_productos`.
_TTL_S = 120.0
_INDICES: dict[tuple[str, str], tuple[float, dict[str, Path]]] = {}


def _indice(tipo: str, usuario: str) -> dict[str, Path]:
    """`{nombre_sin_extension: ruta}` de todas las fotos de ese tipo."""
    clave = (tipo, usuario or "ness")
    hit = _INDICES.get(clave)
    if hit and time.monotonic() < hit[0]:
        return hit[1]
    base = config.carpeta_de(tipo, usuario)
    mapa = {
        f.stem: f
        for f in base.iterdir()
        if f.is_file() and f.suffix.lower() in _EXTS
    }
    _INDICES[clave] = (time.monotonic() + _TTL_S, mapa)
    return mapa


def _invalidar(tipo: str = "", usuario: str = "") -> None:
    """Tras escribir. Sin argumentos tira el índice entero."""
    if not tipo:
        _INDICES.clear()
        return
    _INDICES.pop((tipo, usuario or "ness"), None)


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
    _invalidar(tipo, usuario)
    return destino


def borrar(tipo: str, usuario: str, source: str, folder: str, producto: str) -> bool:
    """Quita la foto de ese tipo. Devuelve si había algo que borrar."""
    p = buscar(tipo, usuario, source, folder, producto)
    if not p:
        return False
    p.unlink(missing_ok=True)
    _invalidar(tipo, usuario)
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
    for destino, (filename, datos) in zip(pendientes, archivos):
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
    _invalidar(f"{tipo}_txt", usuario)
    return salida


def limpiar_texto(usuario: str, source: str, folder: str, producto: str) -> None:
    """Tira las versiones quemadas (el mensaje cambió y hay que rehacerlas)."""
    for tipo in ("chica_txt", "producto_txt"):
        borrar(tipo, usuario, source, folder, producto)


def nombre_descarga(source: str, folder: str, producto: str, pos: int) -> str:
    """Cómo se llama la foto al bajarla: `<carpeta>_<producto>_1.jpg`.

    Con el número delante para que al subirlas a TikTok desde la galería salgan
    en orden — la 1 es la chica y la 2 el producto, y al revés el carrusel no
    tiene sentido.
    """
    base = f"{_slug(folder)}_{_slug(producto)}_{pos}"
    return f"{base}.jpg"
