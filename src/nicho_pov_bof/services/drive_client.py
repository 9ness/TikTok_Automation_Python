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
import threading
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from src.nicho_pov_bof import config
from src.nicho_pov_bof.repos.redis_base import get_nicho_pov_bof_redis

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


# ------------------------------------------------------------------
# Caché persistente en Redis (segunda capa, detrás de la de memoria)
# ------------------------------------------------------------------
# Listar un Drive "compartido conmigo" es LENTO de verdad: rclone no puede
# resolver la ruta de un tirón, va segmento a segmento, y listar las 31
# carpetas de producto tarda ~41s. Con solo la caché de memoria eso se paga
# entero cada vez que se reinicia la API y cada vez que vence el TTL, y es lo
# que hacía que entrar a la página tardase una eternidad.
#
# `Productos España` es SOLO LECTURA y su contenido apenas cambia, así que se
# guarda también en Redis con dos edades:
#   - hasta `LISTING_TTL_S` se sirve tal cual;
#   - a partir de ahí se sirve IGUAL DE RÁPIDO (stale) y se dispara un
#     refresco en segundo plano, así el operador nunca espera a rclone.
# Solo se descarta del todo pasado `_REDIS_MAX_AGE_S`.
_REDIS_MAX_AGE_S = 7 * 24 * 3600.0
_REFRESCANDO: set[str] = set()
_REFRESCANDO_LOCK = threading.Lock()


def _redis_cache_get(key: str) -> tuple[Any, float] | None:
    """(payload, antigüedad en segundos) o None si no hay nada usable."""
    try:
        r = get_nicho_pov_bof_redis()
        if not r.is_available():
            return None
        doc = r.get_json(f"cache:{key}")
    except Exception:
        # La caché nunca debe tumbar una petición: si Redis falla, se lista.
        return None
    if not isinstance(doc, dict) or "payload" not in doc:
        return None
    edad = time.time() - float(doc.get("at") or 0)
    if edad > _REDIS_MAX_AGE_S:
        return None
    return doc["payload"], edad


def _redis_cache_put(key: str, payload: Any) -> None:
    try:
        r = get_nicho_pov_bof_redis()
        if r.is_available():
            r.set_json(f"cache:{key}", {"at": time.time(), "payload": payload})
    except Exception:
        pass


def _refrescar_en_segundo_plano(key: str, cargar: Callable[[], Any]) -> None:
    """Relista en un hilo aparte. Como mucho un refresco por clave a la vez."""
    with _REFRESCANDO_LOCK:
        if key in _REFRESCANDO:
            return
        _REFRESCANDO.add(key)

    def _tarea() -> None:
        try:
            payload = cargar()
            _cache_put(key, payload)
            _redis_cache_put(key, payload)
        except Exception:
            # Si falla se conserva lo que hubiera: es preferible una lista
            # de hace un rato a un error en pantalla.
            pass
        finally:
            with _REFRESCANDO_LOCK:
                _REFRESCANDO.discard(key)

    threading.Thread(target=_tarea, daemon=True, name=f"drive-refresh-{key}").start()


def _listar_cacheado(key: str, cargar: Callable[[], Any], *, refresh: bool) -> Any:
    """Memoria → Redis (sirviendo stale) → rclone."""
    if refresh:
        payload = cargar()
        _cache_put(key, payload)
        _redis_cache_put(key, payload)
        return payload

    en_memoria = _cache_get(key)
    if en_memoria is not None:
        return en_memoria

    en_redis = _redis_cache_get(key)
    if en_redis is not None:
        payload, edad = en_redis
        _cache_put(key, payload)
        if edad > config.LISTING_TTL_S:
            _refrescar_en_segundo_plano(key, cargar)
        return payload

    payload = cargar()
    _cache_put(key, payload)
    _redis_cache_put(key, payload)
    return payload


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

    def cargar() -> list[dict]:
        items = _lsjson(base, dirs_only=True)
        folders = [
            {"name": it["Name"], "id": it.get("ID", "")}
            for it in items
            if it.get("Name")
        ]
        folders.sort(key=lambda f: config.natural_sort_key(f["name"]))
        return folders

    return _listar_cacheado(f"folders:{source}", cargar, refresh=refresh)


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

    def cargar() -> list[dict]:
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
        return photos

    return _listar_cacheado(f"photos:{source}:{folder}", cargar, refresh=refresh)


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
