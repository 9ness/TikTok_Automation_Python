"""Los productos de la web del curso, importados por ZIP.

Jonny publica el catálogo en su web y deja descargar cada carpeta en un ZIP.
Esto los mete en la fábrica como una fuente más, para que tengan textos,
guion, escaparate, vendidos, ficha enlazada y montaje igual que el resto.

Dos cosas que NO son obvias y de las que depende todo:

1. **La convención de nombres viene AL REVÉS.** En su ZIP `3.png` es la
   captura de la ficha (con precio y título) y `3.1.jpeg` la foto limpia del
   producto. En el Drive del curso —y por tanto en toda nuestra fábrica— es al
   contrario: `3.png` es la limpia y `3(1).png` la ficha. Si no se invierte al
   importar, entran las diez parejas cambiadas y los textos se extraen de la
   foto que no es.

2. **Los ZIP se vuelven a subir.** El catálogo se actualiza a menudo, así que
   importar tiene que ser repetible: la carpeta se llama como el ZIP y cada
   producto se compara con lo que ya había. Lo igual no se toca, lo nuevo entra
   y lo que cambió se sustituye — y se dice cuál es cuál, que es lo que
   permite saber a qué productos hay que ponerles la URL.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from pathlib import Path
from typing import Any, Callable

from src.nicho_pov_bof import config

_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# Igual que en "Mis productos": listar el mount en frío cuesta segundos.
_TTL_S = 900.0
_LISTADOS: dict[str, tuple[float, Any]] = {}


def _memo(clave: str, calcular: Callable[[], Any]) -> Any:
    import time

    guardado = _LISTADOS.get(clave)
    if guardado and time.monotonic() < guardado[0]:
        return guardado[1]
    valor = calcular()
    _LISTADOS[clave] = (time.monotonic() + _TTL_S, valor)
    return valor


def _invalidar() -> None:
    _LISTADOS.clear()


def _num_carpeta(nombre: str) -> int:
    """Para ordenar `Carpeta 2` antes que `Carpeta 10`."""
    m = re.search(r"(\d+)", nombre)
    return int(m.group(1)) if m else 0


def carpetas() -> list[str]:
    def leer() -> list[str]:
        raiz = config.productos_web_dir()
        if not raiz.is_dir():
            return []
        return sorted(
            (d.name for d in raiz.iterdir() if d.is_dir() and not d.name.startswith(".")),
            key=_num_carpeta,
        )

    return _memo("carpetas", leer)


def listar_carpetas_como_drive() -> list[dict]:
    """Mismo shape que `drive_client.list_product_folders`."""
    return [{"name": c, "id": c} for c in carpetas()]


def listar_fotos_como_drive(carpeta: str) -> list[dict]:
    """Mismo shape que `drive_client.list_photos`.

    El `id` es la RUTA con el mtime pegado, igual que en "Mis productos": es
    lo que deja cachear la foto un día en el móvil y que al sustituirla cambie
    la URL y se vuelva a pedir.
    """

    def leer() -> list[dict]:
        d = config.productos_web_dir() / carpeta
        if not d.is_dir():
            return []
        fotos = [
            {
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
# Importar un ZIP
# ---------------------------------------------------------------------------
def nombre_carpeta(nombre_zip: str) -> str:
    """`Carpeta 26.zip` → `Carpeta 26`. Sin extensión y sin rutas."""
    limpio = Path(nombre_zip or "").name
    limpio = re.sub(r"\.zip$", "", limpio, flags=re.IGNORECASE).strip()
    # Los navegadores y los descargadores meten sufijos al bajar dos veces.
    limpio = re.sub(r"\s*\(\d+\)$", "", limpio).strip()
    return limpio or "Carpeta"


def _parejas(zf: zipfile.ZipFile) -> dict[str, dict[str, str]]:
    """`{"1": {"ficha": "1.png", "limpia": "1.1.jpeg"}}` a partir del ZIP.

    En su ZIP el número suelto es la FICHA y el `.1` la limpia. Se acepta
    cualquier profundidad de carpetas dentro: algunos descargadores meten todo
    bajo un directorio con el nombre de la carpeta.
    """
    salida: dict[str, dict[str, str]] = {}
    for nombre in zf.namelist():
        if nombre.endswith("/"):
            continue
        base = Path(nombre).name
        if Path(base).suffix.lower() not in _EXTS:
            continue
        m = re.match(r"^(\d+)(\.1)?\.[A-Za-z0-9]+$", base)
        if not m:
            continue
        producto, es_limpia = m.group(1), bool(m.group(2))
        salida.setdefault(producto, {})["limpia" if es_limpia else "ficha"] = nombre
    return salida


def _huella(datos: bytes) -> str:
    return hashlib.sha1(datos).hexdigest()


def _huella_fichero(ruta: Path) -> str:
    try:
        return _huella(ruta.read_bytes())
    except OSError:
        return ""


def importar_zip(datos: bytes, nombre_zip: str) -> dict:
    """Mete un ZIP de la web en su carpeta. Repetible: se puede resubir.

    Devuelve `{carpeta, nuevos, actualizados, iguales, incompletos}` con los
    números de producto de cada grupo — que es lo que dice a qué productos hay
    que ponerles la URL.
    """
    carpeta = nombre_carpeta(nombre_zip)
    destino = config.productos_web_dir() / carpeta
    destino.mkdir(parents=True, exist_ok=True)

    try:
        zf = zipfile.ZipFile(io.BytesIO(datos))
    except zipfile.BadZipFile as e:
        raise ValueError(f"Eso no es un ZIP válido: {e}") from e

    nuevos: list[str] = []
    actualizados: list[str] = []
    iguales: list[str] = []
    incompletos: list[str] = []

    for producto in sorted(_parejas(zf), key=lambda x: int(x)):
        par = _parejas(zf)[producto]
        # Sin las dos fotos no entra: la ficha es de donde salen los textos y
        # la limpia es la que se anima. A medias daría un producto inservible
        # que además ocuparía número.
        if "limpia" not in par or "ficha" not in par:
            incompletos.append(producto)
            continue

        limpia = zf.read(par["limpia"])
        ficha = zf.read(par["ficha"])
        # AQUÍ se invierte: lo que en su ZIP es `N.1` (limpia) pasa a ser
        # nuestro `N`, y su `N` (ficha) pasa a ser nuestro `N(1)`.
        ruta_limpia = destino / f"{producto}{_ext(par['limpia'])}"
        ruta_ficha = destino / f"{producto}(1){_ext(par['ficha'])}"

        antes = {
            _huella_fichero(p) for p in destino.glob(f"{producto}*") if p.is_file()
        }
        ya_estaba = bool(antes)
        if ya_estaba and _huella(limpia) in antes and _huella(ficha) in antes:
            iguales.append(producto)
            continue

        # Se limpian las versiones anteriores de ESE producto: puede venir con
        # otra extensión y si no quedarían las dos y el emparejado vería tres
        # fotos para un producto.
        for viejo in destino.glob(f"{producto}[!0-9]*"):
            if viejo.is_file():
                viejo.unlink(missing_ok=True)
        for viejo in destino.glob(f"{producto}.*"):
            if viejo.is_file():
                viejo.unlink(missing_ok=True)

        ruta_limpia.write_bytes(limpia)
        ruta_ficha.write_bytes(ficha)
        (actualizados if ya_estaba else nuevos).append(producto)

    _invalidar()
    return {
        "carpeta": carpeta,
        "nuevos": nuevos,
        "actualizados": actualizados,
        "iguales": iguales,
        "incompletos": incompletos,
    }


def _ext(nombre: str) -> str:
    ext = Path(nombre).suffix.lower()
    return ext if ext in _EXTS else ".jpg"
