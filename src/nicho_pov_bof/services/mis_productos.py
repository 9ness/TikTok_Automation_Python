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
# Aquí basta con una caché en memoria y corta, PERO con una diferencia que las
# del curso no necesitan: esta carpeta se ESCRIBE. Si el operador sube un
# producto y el listado sigue cacheado, sube y no lo ve. Por eso cualquier
# escritura la invalida entera (`_invalidar`), en vez de esperar al TTL.
_TTL_S = 120.0
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


def borrar_producto(carpeta: str, producto: str) -> bool:
    """Quita las fotos de un producto. La carpeta se queda (con sus huecos)."""
    d = config.mis_productos_dir() / carpeta
    if not d.is_dir():
        return False
    borradas = 0
    for f in list(d.iterdir()):
        if f.is_file() and re.match(rf"^{re.escape(producto)}(\(\d+\))?$", f.stem):
            f.unlink(missing_ok=True)
            borradas += 1
    if borradas:
        _invalidar()
    return borradas > 0


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
                "id": str(f),
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


def copiar_a(destino: Path, foto_id: str) -> Path:
    """`fetch_photo` para fotos propias: ya están en disco, solo se copian."""
    origen = Path(foto_id)
    if not origen.is_file():
        raise ValueError(f"no está la foto: {foto_id}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(origen, destino)
    return destino
