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
from pathlib import Path

from src.nicho_pov_bof import config

_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
_PREFIJO = "Mis Productos"


def _num_carpeta(nombre: str) -> int:
    m = re.search(r"(\d+)\s*$", nombre or "")
    return int(m.group(1)) if m else 0


def carpetas() -> list[str]:
    """Carpetas existentes, en orden natural. Vacío si aún no hay ninguna."""
    raiz = config.mis_productos_dir()
    if not raiz.is_dir():
        return []
    return sorted(
        (d.name for d in raiz.iterdir() if d.is_dir() and not d.name.startswith(".")),
        key=_num_carpeta,
    )


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


def copiar_a(destino: Path, foto_id: str) -> Path:
    """`fetch_photo` para fotos propias: ya están en disco, solo se copian."""
    origen = Path(foto_id)
    if not origen.is_file():
        raise ValueError(f"no está la foto: {foto_id}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(origen, destino)
    return destino
