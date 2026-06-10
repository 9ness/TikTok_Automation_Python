"""CRUD de las 4 carpetas del usuario Editor Auto (entrada / cola /
recuperacion / salida). Permite al admin gestionar el ciclo de vida de
los vídeos sin tocar Drive manualmente.

Endpoints:
    GET  /users/{id}/folders                 — todo en un payload
    GET  /users/{id}/folders/counts          — solo los 4 conteos (badges)
    GET  /folders/counts                     — agregado de todos los users
    POST /users/{id}/folders/move            — mover entre carpetas
    DELETE /users/{id}/folders/file          — borrar (irreversible)
    POST /users/{id}/folders/enqueue         — encolar desde `entrada/`
                                               (mueve a `cola/` + crea job)
    GET  /users/{id}/folders/file/preview    — servir el MP4 para preview
                                               (auth dual header/query)

Auth: header `X-API-Key` (dependencia del router). El endpoint
`/preview` permite también `?api_key=` query porque `<video src=>` no
admite headers custom (mismo patrón que fonts/stickers).
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse

from src.api.config import APISettings, get_settings
from src.api.dependencies import get_current_user, get_queue
from src.api.exceptions import UnauthorizedError, ValidationError
from src.editor_auto.config import USER_FOLDERS, user_subfolder
from src.editor_auto.repos import UserRepo
from src.editor_auto.services import folder_manager
from src.queue.manager import JobQueue
from src.queue.models import JobMode

logger = logging.getLogger("editor_auto.folders")


router = APIRouter(
    prefix="/api/v1/editor-auto",
    tags=["editor-auto · folders"],
)


_VIDEO_MIME = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".avi": "video/x-msvideo",
    ".m4v": "video/x-m4v",
}


def _user_or_raise(user_id: str):
    repo = UserRepo()
    u = repo.get(user_id)
    if u is None or u.deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Usuario no encontrado o eliminado: {user_id}",
        )
    return u


# Claves Redis del flujo web (mismas que web_upload). Un vídeo de `entrada/`
# que ya tiene job o está en sentfiles YA fue mandado a edición → no es un
# "pendiente" aunque su archivo siga en Drive (el flujo web lo lee in-place).
_WEB_SENT_KEY = "webday_sentfiles:"
_WEB_JOBS_KEY = "webday_jobs:"


def _processed_entrada_names(user_id: str, days: set[str]) -> dict[str, set[str]]:
    """Por día, los filenames de `entrada/` YA enviados a edición."""
    from src.editor_auto.repos.redis_base import get_editor_redis
    r = get_editor_redis()
    out: dict[str, set[str]] = {}
    for d in days:
        names: set[str] = set()
        try:
            names |= set(r.smembers(f"{_WEB_SENT_KEY}{user_id}:{d}") or [])
        except Exception:
            pass
        try:
            meta = r.get_json(f"{_WEB_JOBS_KEY}{user_id}:{d}")
            if isinstance(meta, list):
                names |= {
                    m.get("filename") for m in meta
                    if isinstance(m, dict) and m.get("filename")
                }
        except Exception:
            pass
        out[d] = names
    return out


def _pending_entrada(items: list[dict[str, Any]], user_id: str) -> list[dict[str, Any]]:
    """Filtra de `entrada/` los vídeos de día YA mandados a edición → solo
    quedan los PENDIENTES (subidos pero sin enviar). Los items sin `day`
    (flujo manual: subida plana) se mantienen tal cual."""
    day_items = [it for it in items if it.get("day")]
    if not day_items:
        return items  # flujo manual o sin días → nada que filtrar
    processed = _processed_entrada_names(user_id, {it["day"] for it in day_items})
    out: list[dict[str, Any]] = []
    for it in items:
        d = it.get("day")
        if d:
            fn = str(it.get("filename", ""))
            base = fn.split("/", 1)[1] if "/" in fn else fn
            if base in processed.get(d, set()):
                continue  # ya editado → no es pendiente
        out.append(it)
    return out


def _user_counts(u) -> dict[str, int]:
    """Conteos por carpeta con `entrada` ya filtrada a solo-pendientes."""
    counts = folder_manager.count_files(u.name)
    try:
        items = folder_manager.list_files(u.name, "entrada")
        counts["entrada"] = len(_pending_entrada(items, u.id))
    except Exception:
        pass
    return counts


# ---------------------------------------------------------------------------
# Listados (auth normal — header)
# ---------------------------------------------------------------------------
@router.get(
    "/users/{user_id}/folders",
    dependencies=[Depends(get_current_user)],
)
def list_user_folders(user_id: str) -> dict[str, Any]:
    """Listado completo de las 4 carpetas del usuario con metadatos por
    archivo. La UI lo consume para pintar los 4 tabs de una vez."""
    u = _user_or_raise(user_id)
    by_folder: dict[str, list[dict[str, Any]]] = {}
    counts: dict[str, int] = {}
    for folder in USER_FOLDERS:
        items = folder_manager.list_files(u.name, folder)
        # `entrada/` muestra SOLO pendientes (sin enviar) — lo ya editado no
        # es accionable aquí y solo estorba al admin.
        if folder == "entrada":
            items = _pending_entrada(items, u.id)
        by_folder[folder] = items
        counts[folder] = len(items)
    return {
        "user_id": u.id,
        "user_name": u.name,
        "folders": by_folder,
        "counts": counts,
    }


@router.get(
    "/users/{user_id}/folders/counts",
    dependencies=[Depends(get_current_user)],
)
def user_folder_counts(user_id: str) -> dict[str, Any]:
    """Solo los 4 conteos, sin metadatos por archivo. Diseñado para el
    badge de la lista de usuarios (refresca cada 20–30s)."""
    u = _user_or_raise(user_id)
    return {
        "user_id": u.id,
        "user_name": u.name,
        "counts": _user_counts(u),
    }


# Cache módulo para `/folders/counts`. El badge global de la sidebar
# llama a este endpoint cada 30s desde cada cliente — y cada call hace
# `listdir` + `stat` sobre las 4 carpetas de Drive de CADA usuario, lo
# que en Drive Desktop / rclone puede tardar varios segundos. Cachear
# 15s evita golpear el FS en cada navegación SPA sin perder reactividad
# (al subir un vídeo, el badge tarda como mucho 15s en actualizarse).
_GLOBAL_COUNTS_TTL = 15.0
_global_counts_cache: dict[str, tuple[float, dict[str, Any]]] = {}


@router.get(
    "/folders/counts",
    dependencies=[Depends(get_current_user)],
)
def global_folder_counts() -> dict[str, Any]:
    """Conteos agregados de TODOS los usuarios activos. Lo consume el
    badge global de la sidebar (un número total de pendientes en
    `entrada/` para que el admin vea cuántos hay sin entrar a cada user).

    Returns:
        {
            "totals": {"entrada": N, "cola": N, "recuperacion": N, "salida": N},
            "by_user": [{"user_id", "user_name", "counts": {...}}, ...]
        }
    """
    now = time.time()
    cached = _global_counts_cache.get("data")
    if cached and now - cached[0] < _GLOBAL_COUNTS_TTL:
        return cached[1]

    repo = UserRepo()
    users = repo.list_all(include_deleted=False)

    # Paralelizar el conteo por usuario: cada `count_files` hace 4 listdir
    # + stat sobre Drive Desktop (que en Windows es lento por sync). Para
    # N usuarios secuencial sería N × ~0.5-1s; en paralelo ≈ max() ~1s.
    def _count_one(u) -> tuple[Any, dict[str, int]]:
        try:
            return u, _user_counts(u)
        except Exception:
            return u, {f: 0 for f in USER_FOLDERS}

    totals = {f: 0 for f in USER_FOLDERS}
    by_user: list[dict[str, Any]] = []
    if users:
        with ThreadPoolExecutor(max_workers=min(8, len(users))) as ex:
            for u, counts in ex.map(_count_one, users):
                for k, v in counts.items():
                    totals[k] = totals.get(k, 0) + v
                by_user.append({
                    "user_id": u.id,
                    "user_name": u.name,
                    "counts": counts,
                })
    result = {"totals": totals, "by_user": by_user}
    _global_counts_cache["data"] = (now, result)
    return result


# ---------------------------------------------------------------------------
# Acciones (auth normal — header)
# ---------------------------------------------------------------------------
@router.post(
    "/users/{user_id}/folders/move",
    dependencies=[Depends(get_current_user)],
)
def move_user_file(
    user_id: str,
    payload: Annotated[dict, Body(...)],
) -> dict[str, Any]:
    """Mueve un archivo entre carpetas del usuario. Body:
    `{src_folder, dst_folder, filename}`. Si el destino ya tiene un
    archivo con ese nombre, se renombra con sufijo `_2`/`_3`/…"""
    u = _user_or_raise(user_id)
    src = (payload.get("src_folder") or "").strip()
    dst = (payload.get("dst_folder") or "").strip()
    filename = (payload.get("filename") or "").strip()
    try:
        result = folder_manager.move_file(u.name, src, dst, filename)
    except (folder_manager.FolderError, ValueError) as e:
        raise ValidationError(str(e))
    return result


@router.delete(
    "/users/{user_id}/folders/file",
    dependencies=[Depends(get_current_user)],
)
def delete_user_file(
    user_id: str,
    folder: Annotated[str, Query(...)],
    filename: Annotated[str, Query(...)],
) -> dict[str, Any]:
    """Borra un archivo del filesystem. IRREVERSIBLE."""
    u = _user_or_raise(user_id)
    try:
        folder_manager.delete_file(u.name, folder, filename)
    except (folder_manager.FolderError, ValueError) as e:
        raise ValidationError(str(e))
    return {"ok": True, "user_id": u.id, "folder": folder, "filename": filename}


@router.post(
    "/users/{user_id}/folders/enqueue",
    dependencies=[Depends(get_current_user)],
)
def enqueue_from_entrada(
    user_id: str,
    payload: Annotated[dict, Body(...)],
    background: BackgroundTasks,
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> dict[str, Any]:
    """Encola un vídeo que ya está en `entrada/` del usuario.

    Pasos:
        1. Valida que existe en `entrada/`.
        2. MUEVE entrada/<file> → cola/<file> (lock visual: el cliente
           no debe tocar archivos en procesamiento).
        3. Crea el job con `input_path` apuntando a cola/<file>.
        4. Job ejecuta. Tras éxito el pipeline mueve cola → recuperacion.
           Tras fallo el runner mueve cola → entrada (auto-retry manual).

    Body: `{filename, script?}` (script obligatorio si flow tiene
    silence_cutter_scripted).
    """
    u = _user_or_raise(user_id)
    filename = (payload.get("filename") or "").strip()
    script_from_body = (payload.get("script") or "").strip()

    enabled = [s for s in u.tool_flow if s.enabled]
    if not enabled:
        raise ValidationError(
            f"El usuario '{u.name}' no tiene herramientas habilitadas."
        )
    needs_script = any(s.tool_id == "silence_cutter_scripted" for s in enabled)

    # Resolución del guion (prioridad: body > companion .txt en entrada/).
    # Para flows scripted, si el cliente subió `<stem>.txt` junto al
    # vídeo en entrada/, lo leemos automáticamente — el operador no tiene
    # que copiar/pegar nada. Si NO hay companion ni body, el job se
    # encola igualmente con `script=""`: el runtime de
    # `silence_cutter_scripted` detecta el guion vacío y hace fallback
    # automático a `silence_cutter` (modo sin guion), loguenado la
    # decisión en la cola del job. No bloqueamos el encolado.
    script: str = ""
    if script_from_body:
        script = script_from_body
    elif needs_script:
        try:
            companion = folder_manager.read_script_companion(
                u.name, "entrada", filename,
            )
        except (folder_manager.FolderError, ValueError) as e:
            raise ValidationError(str(e))
        if companion:
            script = companion

    # Validación rápida: el archivo debe existir en entrada/ (así no
    # devolvemos 202 para un fichero inexistente).
    entrada_path = os.path.join(user_subfolder(u.name, "entrada"), filename)
    if not os.path.exists(entrada_path):
        raise ValidationError(
            f"El archivo '{filename}' no está en entrada/ de '{u.name}'."
        )

    try:
        from src.utils import load_config
        cfg = load_config()
        temp_folder = cfg["paths"]["temp_folder"]
    except Exception:
        temp_folder = "./temp_work"

    tools_used = [s.tool_id for s in enabled]
    enabled_count = len(enabled)
    script_final = script if needs_script else None

    # El MOVE entrada→cola de un vídeo pesado por rclone puede tardar
    # MINUTOS (copia sobre el FUSE mount). Hacerlo síncrono bloqueaba el
    # request y recargar la página perdía el encolado. Lo hacemos en
    # BackgroundTask: el server completa el move + crea el job pase lo que
    # pase con la conexión del cliente. Devolvemos 202 al instante.
    def _move_and_enqueue() -> None:
        try:
            move_result = folder_manager.move_file(
                u.name, "entrada", "cola", filename,
            )
        except Exception as e:
            logger.warning(
                "[enqueue-bg] move entrada→cola falló para %s/%s: %s — "
                "el archivo se queda en entrada/ para reintentar.",
                u.name, filename, e,
            )
            return
        final_filename = move_result["filename_new"]
        input_path = os.path.join(user_subfolder(u.name, "cola"), final_filename)
        params: dict[str, Any] = {
            "user_id": u.id,
            "user_name": u.name,
            "input_path": input_path,
            "temp_folder": temp_folder,
            "tool_count": enabled_count,
            "tools_used": tools_used,
            "script": script_final,
            "source": "entrada",
            "source_filename": final_filename,
        }
        try:
            job = queue.enqueue(
                JobMode.EDITOR_AUTO,
                title=f"{u.name} · {final_filename} · {enabled_count} tool(s)",
                params=params,
            )
            logger.info(
                "[enqueue-bg] %s/%s → job %s encolado", u.name, final_filename, job.id,
            )
        except Exception as e:
            logger.warning(
                "[enqueue-bg] crear job falló para %s/%s: %s — devuelvo a entrada/.",
                u.name, final_filename, e,
            )
            try:
                folder_manager.move_file(u.name, "cola", "entrada", final_filename)
            except Exception:
                pass

    background.add_task(_move_and_enqueue)
    return {
        "status": "encolando",
        "filename": filename,
        "message": (
            "Encolando en segundo plano (puede tardar en vídeos pesados). "
            "Aparecerá en la cola en breve — puedes recargar la página."
        ),
    }


# ---------------------------------------------------------------------------
# Preview de archivo — auth dual header + query (necesario para <video src>)
# ---------------------------------------------------------------------------
def _auth_or_raise(
    settings: APISettings, header: str | None, query: str | None
) -> None:
    if not settings.api_key:
        return
    provided = header or query
    if not provided or provided != settings.api_key:
        raise UnauthorizedError("API key inválida o ausente.")


@router.get("/users/{user_id}/folders/file/preview")
def preview_user_file(
    user_id: str,
    folder: Annotated[str, Query(...)],
    filename: Annotated[str, Query(...)],
    settings: Annotated[APISettings, Depends(get_settings)],
    api_key: Annotated[str | None, Query()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> FileResponse:
    """Sirve el MP4 para preview en `<video>`. Auth dual."""
    _auth_or_raise(settings, x_api_key, api_key)
    u = _user_or_raise(user_id)
    try:
        path = folder_manager.resolve_file(u.name, folder, filename)
    except (folder_manager.FolderError, ValueError) as e:
        raise ValidationError(str(e))
    ext = os.path.splitext(filename)[1].lower()
    return FileResponse(
        path,
        media_type=_VIDEO_MIME.get(ext, "application/octet-stream"),
        filename=os.path.basename(filename),
    )


# ---------------------------------------------------------------------------
# Editor de RETOQUE manual — proyecto editable + re-render que reemplaza salida
# ---------------------------------------------------------------------------
def _strip_editado(output_filename: str) -> str:
    """`IMG_9750_editado.mp4` / `..._editado_2.mp4` → `IMG_9750` (stem original)."""
    stem = os.path.splitext(output_filename)[0]
    return re.sub(r"_editado(_\d+)?$", "", stem)


def _find_original_in_recovery(user_name: str, output_filename: str) -> str | None:
    """Localiza el vídeo ORIGINAL en `recuperacion/` que dio lugar a este
    output (por stem). El editor manual re-renderiza desde el original."""
    rec = user_subfolder(user_name, "recuperacion")
    base = _strip_editado(output_filename)
    try:
        for f in os.listdir(rec):
            if f.startswith("."):
                continue
            if os.path.splitext(f)[0] == base:
                return f
    except OSError:
        return None
    return None


@router.get(
    "/users/{user_id}/output/editproject",
    dependencies=[Depends(get_current_user)],
)
def get_output_editproject(
    user_id: str,
    filename: Annotated[str, Query(...)],
) -> dict[str, Any]:
    """Devuelve el 'proyecto editable' de un vídeo de salida: palabras
    (transcripción), tramos conservados y duración, + el nombre del original
    en recuperacion (para que el editor lo reproduzca y re-renderice)."""
    u = _user_or_raise(user_id)
    salida = user_subfolder(u.name, "salida")
    if not os.path.exists(os.path.join(salida, filename)):
        raise ValidationError(f"'{filename}' no está en salida/ de '{u.name}'.")
    original = _find_original_in_recovery(u.name, filename)
    data: dict[str, Any] = {
        "output_filename": filename,
        "original_filename": original,
        "has_project": False,
        "words": [],
        "keep_intervals": [],
        "video_duration_s": 0.0,
    }
    # `.editproj` a nivel de usuario (hermano de salida). Fallback al sitio
    # antiguo (dentro de salida) para proyectos generados antes del cambio.
    proj_path = os.path.join(os.path.dirname(salida), ".editproj", f"{filename}.json")
    if not os.path.exists(proj_path):
        proj_path = os.path.join(salida, ".editproj", f"{filename}.json")
    if os.path.exists(proj_path):
        try:
            with open(proj_path, encoding="utf-8") as f:
                proj = json.load(f)
            data["has_project"] = True
            data["words"] = proj.get("words", [])
            data["keep_intervals"] = proj.get("keep_intervals", [])
            data["video_duration_s"] = proj.get("video_duration_s", 0.0)
        except Exception:  # noqa: BLE001
            pass
    return data


@router.post(
    "/users/{user_id}/output/manual-render",
    dependencies=[Depends(get_current_user)],
)
def manual_render_output(
    user_id: str,
    payload: Annotated[dict, Body(...)],
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> dict[str, Any]:
    """Re-renderiza un vídeo de salida con los tramos a CONSERVAR dados por el
    operador (retoque manual) y REEMPLAZA el de salida (mismo nombre).

    Body: `{filename, keep_intervals: [[start,end], ...]}`.
    Encola un job EDITOR_AUTO con `manual_keep_intervals` (el cutter salta la
    detección) + `output_override` (pisa el output). El original se queda en
    recuperacion (no se toca). Async → devuelve job_id para hacer polling.
    """
    u = _user_or_raise(user_id)
    filename = (payload.get("filename") or "").strip()
    raw = payload.get("keep_intervals") or []
    if not filename:
        raise ValidationError("Falta 'filename'.")
    intervals: list[list[float]] = []
    for it in raw:
        try:
            a, b = float(it[0]), float(it[1])
        except (TypeError, ValueError, IndexError):
            continue
        if b - a > 0.02:
            intervals.append([round(a, 3), round(b, 3)])
    if not intervals:
        raise ValidationError("'keep_intervals' vacío o inválido.")

    salida = user_subfolder(u.name, "salida")
    out_path = os.path.join(salida, filename)
    if not os.path.exists(out_path):
        raise ValidationError(f"'{filename}' no está en salida/ de '{u.name}'.")
    original = _find_original_in_recovery(u.name, filename)
    if not original:
        raise ValidationError(
            f"No encuentro el vídeo original en recuperacion/ para '{filename}'. "
            f"Es necesario para re-renderizar (no se borre de recuperacion)."
        )
    input_path = os.path.join(user_subfolder(u.name, "recuperacion"), original)

    try:
        from src.utils import load_config
        temp_folder = load_config()["paths"]["temp_folder"]
    except Exception:  # noqa: BLE001
        temp_folder = "./temp_work"

    enabled = [s for s in u.tool_flow if s.enabled]
    params: dict[str, Any] = {
        "user_id": u.id,
        "user_name": u.name,
        "input_path": input_path,
        "temp_folder": temp_folder,
        "manual_keep_intervals": intervals,
        "output_override": out_path,
        "tool_count": len(enabled),
        "tools_used": [s.tool_id for s in enabled],
        # sin `source` → el runner NO toca recuperacion (el original se queda).
    }
    job = queue.enqueue(
        JobMode.EDITOR_AUTO,
        title=f"{u.name} · {filename} · ✂️ retoque manual",
        params=params,
    )
    # Actualiza el proyecto editable con los nuevos tramos (la próxima vez que
    # se abra el editor parte de aquí).
    try:
        proj_dir = os.path.join(os.path.dirname(salida), ".editproj")
        os.makedirs(proj_dir, exist_ok=True)
        pp = os.path.join(proj_dir, f"{filename}.json")
        proj = {}
        if os.path.exists(pp):
            with open(pp, encoding="utf-8") as f:
                proj = json.load(f)
        proj["keep_intervals"] = intervals
        with open(pp, "w", encoding="utf-8") as f:
            json.dump(proj, f, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        pass

    logger.info("[manual-render] %s/%s → job %s", u.name, filename, job.id)
    return {"status": "renderizando", "job_id": job.id, "filename": filename}
