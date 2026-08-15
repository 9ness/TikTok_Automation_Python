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


def _cacheado_sin_esperar(key: str, cargar: Callable[[], Any], sino: Any) -> Any:
    """Como `_listar_cacheado` pero NUNCA bloquea: si no hay nada guardado,
    devuelve `sino` y lo calcula en segundo plano.

    Para datos que solo ENRIQUECEN una respuesta y no pueden retrasarla. El
    caso real: saber qué carpetas ha borrado el curso cuesta ~17s de rclone
    (hay que recorrer todas las copias) y se necesita en cada listado de
    carpetas; pagarlo dejaba la pantalla y el buscador colgados. Aparecerán en
    cuanto termine el cálculo de fondo, unos segundos después.
    """
    en_memoria = _cache_get(key)
    if en_memoria is not None:
        return en_memoria
    en_redis = _redis_cache_get(key)
    if en_redis is not None:
        payload, edad = en_redis
        _cache_put(key, payload)
        if edad > _TTL_COPIA_S:
            _refrescar_en_segundo_plano(key, cargar)
        return payload
    _refrescar_en_segundo_plano(key, cargar)
    return sino


# Las carpetas que el curso ha borrado cambian de mes en mes, no de minuto en
# minuto: no merece la pena recalcularlo con el ritmo de los listados normales.
_TTL_COPIA_S = 6 * 3600


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


def _run_rclone(
    args: list[str], *, on_log: Callable[[str], None] = _noop, shared: bool = True,
) -> str:
    """Ejecuta rclone y devuelve stdout. Lanza RuntimeError si falla.

    `shared=False` quita `--drive-shared-with-me`: hace falta para la copia de
    seguridad, que vive en NUESTRO Drive ("Mi unidad"). Con el flag puesto, esa
    carpeta sencillamente no existe para rclone.
    """
    cmd = ["rclone", *args] + ([config.SHARED_WITH_ME_FLAG] if shared else [])
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


def _lsjson(
    path: str, *, dirs_only: bool = False, files_only: bool = False,
    shared: bool = True,
) -> list[dict]:
    args = ["lsjson", path]
    if dirs_only:
        args.append("--dirs-only")
    if files_only:
        args.append("--files-only")
    out = _run_rclone(args, shared=shared)
    return json.loads(out or "[]")


def _servicio_propio(source: str):
    """Qué módulo lleva las carpetas de una fuente que vive en NUESTRO Drive.

    Hay dos y las dos hablan el mismo idioma que este cliente
    (`listar_carpetas_como_drive` / `listar_fotos_como_drive`): los productos
    que sube el operador y los que ya vendieron.
    """
    from src.nicho_pov_bof.services import mis_productos, top_vendidos

    return top_vendidos if source == top_vendidos.SOURCE else mis_productos


def list_product_folders(source: str, *, refresh: bool = False) -> list[dict]:
    """Carpetas de producto de una fuente, en orden natural (1, 2, 10...).

    Devuelve [{"name": "1 Pront Flow", "id": "..."}].
    """
    # Fuente propia: las carpetas son del Drive MONTADO, no del compartido, y
    # se leen del disco. Sin caché: son cuatro entradas y cambian al subir.
    if config.es_fuente_propia(source):
        return _servicio_propio(source).listar_carpetas_como_drive()

    # La COPIA de seguridad: no es una carpeta del Drive del curso sino la
    # unión de todas las copias guardadas (ver `backup_sync.carpetas_de`), así
    # que la resuelve ese módulo y no un `lsjson` a secas.
    if config.es_fuente_backup(source):
        from src.nicho_pov_bof.services import backup_sync

        fuente = config.SOURCES[source]["folder"]
        # Misma clave que usa el listado normal para saber qué se borró: así se
        # calcula UNA vez y sirve a los dos.
        nombres = _listar_cacheado(
            f"backup-folders:{source}",
            lambda: backup_sync.carpetas_de(fuente),
            refresh=refresh,
        )
        return [{"name": c, "id": c} for c in nombres]

    base = config.source_path(source)  # valida el slug

    # La copia de seguridad está en "Mi unidad", no en "Compartido conmigo".
    compartido = not config.es_fuente_backup(source)

    def cargar() -> list[dict]:
        items = _lsjson(base, dirs_only=True, shared=compartido)
        folders = [
            {"name": it["Name"], "id": it.get("ID", "")}
            for it in items
            if it.get("Name")
        ]
        # Carpetas que el curso BORRÓ ENTERAS y nosotros sí tenemos. Sin esto
        # desaparecían del navegador y con ellas el trabajo a medias: el
        # progreso sigue en Redis, pero sin carpeta que abrir no hay forma de
        # llegar a él. Se marcan para que se vea de dónde salen.
        vistas = {f["name"] for f in folders}
        for nombre in _carpetas_solo_en_copia(source, vistas):
            folders.append({"name": nombre, "id": nombre, "desde_copia": True})
        folders.sort(key=lambda f: config.natural_sort_key(f["name"]))
        return folders

    return _listar_cacheado(f"folders:{source}", cargar, refresh=refresh)


def _carpetas_solo_en_copia(source: str, ya_estan: set[str]) -> list[str]:
    """Las carpetas que están en el backup y ya no en el Drive del curso.

    Va por la fuente "🗄️ Copia" y NO por `backup_sync` directamente para
    aprovechar su caché: reconstruir el archivo son varias llamadas a rclone
    (mira todas las copias) y esto se ejecuta en cada listado de carpetas —
    pagarlo cada vez dejaba el buscador sin responder.
    """
    copia = config.fuente_copia_de(source)
    if not copia:
        return []

    def cargar() -> list[str]:
        from src.nicho_pov_bof.services import backup_sync

        fuente = config.SOURCES.get(source, {}).get("folder") or ""
        return backup_sync.carpetas_de(fuente) if fuente else []

    todas = _cacheado_sin_esperar(f"backup-folders:{copia}", cargar, [])
    return [c for c in todas if c not in ya_estan]


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
    if config.es_fuente_propia(source):
        return _servicio_propio(source).listar_fotos_como_drive(folder)

    if config.es_fuente_backup(source):
        from src.nicho_pov_bof.services import backup_sync

        fuente = config.SOURCES[source]["folder"]
        _assert_known_folder(source, folder)
        return _listar_cacheado(
            f"backup-photos:{source}:{folder}",
            lambda: backup_sync.fotos_de(fuente, folder),
            refresh=refresh,
        )

    base = config.source_path(source)
    _assert_known_folder(source, folder)

    compartido = not config.es_fuente_backup(source)

    def limpiar(nombre: str) -> str:
        """En la copia, los nombres duplicados llevan pegado el file ID.

        El backup no puede guardar dos `2.PNG` en la misma carpeta, así que al
        copiarlos les añade `__<8 primeros del ID>` (ver `backup_sync`). Ese
        sufijo rompería el emparejado, que va por el número del nombre — se
        quita al listar; el identificador real sigue siendo el file ID.
        """
        return re.sub(r"__[0-9A-Za-z_-]{8}(\.[^.]+)$", r"\1", nombre) if not compartido else nombre

    def cargar() -> list[dict]:
        items = _lsjson(f"{base}/{folder}", files_only=True, shared=compartido)
        photos = [
            {
                "id": it.get("ID", ""),
                "name": limpiar(it["Name"]),
                "size": int(it.get("Size") or 0),
                "mime": it.get("MimeType", ""),
                # Cuándo se subió. Es lo único que separa dos productos cuyas
                # cuatro fotos se llaman EXACTAMENTE igual (`8.PNG` x4): cada
                # pareja se subió con segundos de diferencia y con días entre
                # una y otra. Ver `photo_pairing.group_by_product`.
                "mtime": it.get("ModTime", ""),
            }
            for it in items
            if it.get("Name") and it.get("ID")
            and config.is_image(it["Name"], it.get("MimeType", ""))
        ]
        photos.sort(key=lambda p: config.natural_sort_key(p["name"]))
        if photos:
            return photos
        # Carpeta VACÍA en el Drive del curso. El admin de aquel Drive borra
        # cada cierto tiempo, y entonces desaparecían productos con los que ya
        # se estaba trabajando ("10 Agosto 2026" perdió ocho de golpe). Si la
        # copia los tiene, se sirven de ahí: misma fuente y misma carpeta, así
        # que el progreso guardado (subido, clips, escaparate) sigue valiendo.
        return _de_la_copia(source, folder)

    return _listar_cacheado(f"photos:{source}:{folder}", cargar, refresh=refresh)


def _de_la_copia(source: str, folder: str) -> list[dict]:
    """Las fotos de esa carpeta en el backup, marcadas como tales. `[]` si no hay.

    Cada foto lleva `desde_copia`, que es lo que la pantalla usa para avisar de
    que eso ya no está en el Drive del curso.
    """
    try:
        from src.nicho_pov_bof.services import backup_sync

        fuente = config.SOURCES.get(source, {}).get("folder") or ""
        if not fuente:
            return []
        fotos = backup_sync.fotos_de(fuente, folder)
    except Exception:  # noqa: BLE001
        return []
    for f in fotos:
        f["desde_copia"] = True
    return fotos


def desde_la_copia(fotos: list[dict]) -> bool:
    """¿Lo que se está enseñando sale del backup y no del Drive del curso?"""
    return any(f.get("desde_copia") for f in fotos)


# Dimensiones ya medidas, guardadas en disco. La clave es el id de la foto (que
# en las fuentes propias lleva pegado el mtime) más su tamaño, así que una foto
# sustituida no reutiliza las medidas de la anterior.
_DIMS: dict[str, list[int]] | None = None
_DIMS_SUCIO = False
_DIMS_LOCK = threading.Lock()


def _dims_fichero() -> Path:
    return Path(config.photo_cache_dir()) / "dimensiones.json"


def _dims_cargar() -> dict[str, list[int]]:
    global _DIMS
    if _DIMS is None:
        try:
            _DIMS = json.loads(_dims_fichero().read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            _DIMS = {}
    return _DIMS


def _dims_guardar() -> None:
    """Vuelca a disco. Por fichero temporal: con varios workers escribiendo, un
    guardado a medias dejaría el JSON roto y se perderían TODAS las medidas."""
    global _DIMS_SUCIO
    with _DIMS_LOCK:
        if not _DIMS_SUCIO or _DIMS is None:
            return
        try:
            destino = _dims_fichero()
            destino.parent.mkdir(parents=True, exist_ok=True)
            tmp = destino.with_suffix(".tmp")
            tmp.write_text(json.dumps(_DIMS), encoding="utf-8")
            tmp.replace(destino)
            _DIMS_SUCIO = False
        except Exception:  # noqa: BLE001
            pass


def probe_dimensions(photo: dict) -> dict:
    """Añade `width`/`height` a una foto, descargándola si hace falta.

    Las dimensiones son la señal que distingue la foto de producto (cuadrada)
    de la captura con título (pantallazo alto o tira ancha), y `rclone lsjson`
    no las trae.

    Se guardan en disco porque medirlas es lo que hacía LENTO el listado: abrir
    con Pillow las veinte fotos de una carpeta desde el Drive montado costaba
    ~55s, y el ranking (cuatro carpetas) casi dos minutos — la pantalla se
    quedaba enseñando lo de la vez anterior mientras tanto, que parecía que no
    se había actualizado nada. Medidas ya, el listado va con lo que hay en
    disco.
    """
    import os

    from PIL import Image

    global _DIMS_SUCIO

    if photo.get("width") and photo.get("height"):
        return photo

    clave = f"{photo.get('id', '')}|{photo.get('size', 0)}"
    guardado = _dims_cargar().get(clave)
    if guardado:
        photo["width"], photo["height"] = guardado[0], guardado[1]
        return photo

    try:
        suffix = os.path.splitext(photo.get("name", ""))[1].lower() or ".jpg"
        path = fetch_photo(photo["id"], suffix=suffix)
        with Image.open(path) as im:
            photo["width"], photo["height"] = im.size
        with _DIMS_LOCK:
            _dims_cargar()[clave] = [photo["width"], photo["height"]]
            _DIMS_SUCIO = True
        _dims_guardar()
    except Exception as e:  # una foto ilegible no puede tumbar la carpeta
        photo["width"] = photo["height"] = 0
        photo["probe_error"] = str(e)
    return photo


def fetch_photo(file_id: str, *, suffix: str = ".jpg") -> Path:
    """Descarga una foto por file ID y devuelve la ruta local cacheada.

    Se cachea en disco bajo `API_TEMP_ROOT` — la misma foto no se re-descarga
    en cada scroll de la UI.
    """
    # Las fotos propias llevan la RUTA como id (no hay ID de Google). Se
    # detectan porque empiezan por "/" — un ID de Drive nunca lo hace.
    if str(file_id).startswith("/"):
        # Ya está en disco: se sirve tal cual. Copiarla a la caché no ahorraba
        # nada y añadía una copia que se podía quedar vieja.
        #
        # El id trae `#<mtime>` pegado (ver `mis_productos.listar_fotos_como_drive`):
        # es lo que hace que la URL cambie al cambiar la foto. Aquí se quita.
        ruta = Path(str(file_id).split("#", 1)[0])
        if not ruta.is_file():
            raise ValueError(f"no está la foto: {file_id}")
        return ruta

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
    try:
        _run_rclone(["backend", "copyid", config.DRIVE_REMOTE, file_id, str(tmp)])
    except RuntimeError:
        # Las fotos de la COPIA de seguridad están en nuestro Drive, y ahí el
        # flag `--drive-shared-with-me` estorba. Como aquí solo llega el ID (no
        # de qué fuente venía), se reintenta sin él antes de rendirse.
        _run_rclone(
            ["backend", "copyid", config.DRIVE_REMOTE, file_id, str(tmp)], shared=False,
        )
    if not tmp.is_file() or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"rclone no devolvió contenido para el ID {file_id}")
    tmp.replace(dest)
    return dest
