"""Lector del Drive compartido "Productos España" (SOLO LECTURA).

Por qué CLI y no el mount FUSE: el mount `gdrive-mount.service` expone "Mi
unidad", y esta carpeta está en "Compartido conmigo" — ahí no aparece. La
única vía es `rclone ... --drive-shared-with-me`, que convierte el shared
en la raíz del remote.

Por qué file ID y no nombre: dentro de una misma carpeta hay nombres
DUPLICADOS reales (`2.PNG` dos veces, `10.PNG` vs `10.png`). Descargar por
path sería ambiguo, así que se usa `rclone backend copyid`.

Este módulo NUNCA escribe en el Drive de origen.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from src.nicho_pov_bof import config

_noop: Callable[[str], None] = lambda _: None

# Caché en memoria del proceso: key -> (expira_en_monotonic, payload)
_CACHE: dict[str, tuple[float, Any]] = {}

# Un file ID de Drive es alfanumérico + '-' + '_'. Validamos antes de meterlo
# en un argv de subprocess.
_FILE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,128}$")


def _cache_get(key: str) -> Any | None:
    hit = _CACHE.get(key)
    if not hit:
        return None
    expires_at, payload = hit
    if time.monotonic() >= expires_at:
        _CACHE.pop(key, None)
        return None
    return payload


def _cache_put(key: str, payload: Any) -> None:
    _CACHE[key] = (time.monotonic() + config.LISTING_TTL_S, payload)


def _run_rclone(args: list[str], *, on_log: Callable[[str], None] = _noop) -> str:
    """Ejecuta rclone y devuelve stdout. Lanza RuntimeError si falla."""
    cmd = ["rclone", *args, config.SHARED_WITH_ME_FLAG]
    conf = config.rclone_config_path()
    if conf:
        cmd += ["--config", conf]
    on_log("+ " + " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=config.RCLONE_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"rclone tardó más de {config.RCLONE_TIMEOUT_S:.0f}s: {' '.join(args[:2])}"
        ) from None
    except FileNotFoundError:
        # El container de la API no traía rclone (ver Dockerfile.api). Sin él
        # no hay forma de leer un Drive "compartido conmigo": no está en el
        # mount FUSE. Mensaje explícito en vez de un 500 pelado.
        raise RuntimeError(
            "rclone no está instalado en este entorno. El Drive compartido "
            "solo se puede leer por CLI (--drive-shared-with-me)."
        ) from None
    if proc.returncode != 0:
        raise RuntimeError(
            f"rclone falló ({' '.join(args[:2])}): {proc.stderr[-500:]}"
        )
    return proc.stdout


def _lsjson(path: str, *, dirs_only: bool = False, files_only: bool = False) -> list[dict]:
    args = ["lsjson", path]
    if dirs_only:
        args.append("--dirs-only")
    if files_only:
        args.append("--files-only")
    out = _run_rclone(args)
    return json.loads(out or "[]")


def list_product_folders(source: str, *, refresh: bool = False) -> list[dict]:
    """Carpetas de producto de una fuente, en orden natural (1, 2, 10...).

    Devuelve [{"name": "1 Pront Flow", "id": "..."}].
    """
    base = config.source_path(source)  # valida el slug
    key = f"folders:{source}"
    if not refresh:
        cached = _cache_get(key)
        if cached is not None:
            return cached

    items = _lsjson(base, dirs_only=True)
    folders = [
        {"name": it["Name"], "id": it.get("ID", "")}
        for it in items
        if it.get("Name")
    ]
    folders.sort(key=lambda f: config.natural_sort_key(f["name"]))
    _cache_put(key, folders)
    return folders


def _assert_known_folder(source: str, folder: str) -> None:
    """El nombre de carpeta viene del cliente → whitelist contra Drive.

    Evita que un `../` o cualquier cosa rara acabe en un path de rclone.
    """
    known = {f["name"] for f in list_product_folders(source)}
    if folder not in known:
        raise ValueError(f"Carpeta desconocida en {source!r}: {folder!r}")


def list_photos(source: str, folder: str, *, refresh: bool = False) -> list[dict]:
    """Fotos de una carpeta de producto, en orden natural.

    Devuelve [{"id","name","size","mime"}]. El `id` es el identificador
    canónico (hay nombres duplicados).
    """
    base = config.source_path(source)
    _assert_known_folder(source, folder)

    key = f"photos:{source}:{folder}"
    if not refresh:
        cached = _cache_get(key)
        if cached is not None:
            return cached

    items = _lsjson(f"{base}/{folder}", files_only=True)
    photos = [
        {
            "id": it.get("ID", ""),
            "name": it["Name"],
            "size": int(it.get("Size") or 0),
            "mime": it.get("MimeType", ""),
        }
        for it in items
        if it.get("Name") and config.is_image(it["Name"]) and it.get("ID")
    ]
    photos.sort(key=lambda p: config.natural_sort_key(p["name"]))
    _cache_put(key, photos)
    return photos


def probe_dimensions(photo: dict) -> dict:
    """Añade `width`/`height` a una foto, descargándola si hace falta.

    Las dimensiones son la señal que distingue la foto de producto (cuadrada)
    de la captura con título (pantallazo alto o tira ancha), y `rclone lsjson`
    no las trae. La descarga se cachea, así que solo se paga una vez.
    """
    import os

    from PIL import Image

    if photo.get("width") and photo.get("height"):
        return photo
    try:
        suffix = os.path.splitext(photo.get("name", ""))[1].lower() or ".jpg"
        path = fetch_photo(photo["id"], suffix=suffix)
        with Image.open(path) as im:
            photo["width"], photo["height"] = im.size
    except Exception as e:  # una foto ilegible no puede tumbar la carpeta
        photo["width"] = photo["height"] = 0
        photo["probe_error"] = str(e)
    return photo


def fetch_photo(file_id: str, *, suffix: str = ".jpg") -> Path:
    """Descarga una foto por file ID y devuelve la ruta local cacheada.

    Se cachea en disco bajo `API_TEMP_ROOT` — la misma foto no se re-descarga
    en cada scroll de la UI.
    """
    if not _FILE_ID_RE.match(file_id or ""):
        raise ValueError(f"file_id inválido: {file_id!r}")

    cache_dir = Path(config.photo_cache_dir())
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / f"{file_id}{suffix}"
    if dest.is_file() and dest.stat().st_size > 0:
        return dest

    # `copyid` es la única forma de resolver la ambigüedad de nombres
    # duplicados: baja el fichero por su ID, no por su path.
    tmp = dest.with_suffix(dest.suffix + ".part")
    _run_rclone(["backend", "copyid", config.DRIVE_REMOTE, file_id, str(tmp)])
    if not tmp.is_file() or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"rclone no devolvió contenido para el ID {file_id}")
    tmp.replace(dest)
    return dest
