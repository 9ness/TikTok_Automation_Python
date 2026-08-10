"""Endpoints del Nicho POV BOF (Programa 4 — Tiktok Shop AI Pro).

FASE 1 — navegación del Drive compartido "Productos España" (solo lectura)
y tracking de qué carpetas de producto ya están hechas.

- GET  /api/v1/nicho-pov-bof/sources    → fuentes disponibles (A y B)
- GET  /api/v1/nicho-pov-bof/folders    → carpetas de producto + completadas
- GET  /api/v1/nicho-pov-bof/photos     → fotos de una carpeta
- GET  /api/v1/nicho-pov-bof/photo      → bytes de una foto (por file ID)
- POST /api/v1/nicho-pov-bof/complete   → marca/desmarca completada

Todavía NO genera vídeos (eso es fase 2).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse

from src.api.dependencies import get_current_user, get_web_user, get_queue
from src.api.exceptions import APIError, PhotoNotFoundError
from src.api.schemas.nicho_pov_bof import (
    BackupCheckResponse,
    BackupSyncRequest,
    BackupSyncResponse,
    FoldersListResponse,
    MarkCompletedRequest,
    MarkCompletedResponse,
    PhotoInfo,
    PhotosListResponse,
    ProductFolder,
    SourceInfo,
    SourcesListResponse,
)
from src.queue.manager import JobQueue
from src.queue.models import JobMode, JobStatus

router = APIRouter(
    prefix="/api/v1/nicho-pov-bof",
    tags=["nicho-pov-bof"],
    dependencies=[Depends(get_current_user)],
)


def _bad_request(msg: str) -> APIError:
    return APIError(msg, status_code=400)


@router.get("/sources", response_model=SourcesListResponse)
def list_sources() -> SourcesListResponse:
    from src.nicho_pov_bof import config

    return SourcesListResponse(
        items=[
            SourceInfo(slug=slug, label=meta["label"])
            for slug, meta in config.SOURCES.items()
        ]
    )


@router.get("/folders", response_model=FoldersListResponse)
def list_folders(
    source: Annotated[str, Query()],
    refresh: Annotated[bool, Query()] = False,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> FoldersListResponse:
    from src.nicho_pov_bof.repos import progress_repo
    from src.nicho_pov_bof.services import drive_client

    try:
        folders = drive_client.list_product_folders(source, refresh=refresh)
    except ValueError as e:
        raise _bad_request(str(e)) from e
    except RuntimeError as e:
        raise APIError(f"No se pudo leer el Drive compartido: {e}", status_code=502) from e

    completed = progress_repo.get_completed(source, usuario)
    items = [
        ProductFolder(name=f["name"], id=f["id"], completed=f["name"] in completed)
        for f in folders
    ]
    current = next((i.name for i in items if not i.completed), None)

    return FoldersListResponse(
        source=source,
        items=items,
        total=len(items),
        completed_count=sum(1 for i in items if i.completed),
        current=current,
    )


@router.get("/photos", response_model=PhotosListResponse)
def list_photos(
    source: Annotated[str, Query()],
    folder: Annotated[str, Query()],
    refresh: Annotated[bool, Query()] = False,
) -> PhotosListResponse:
    from src.nicho_pov_bof.services import drive_client

    try:
        photos = drive_client.list_photos(source, folder, refresh=refresh)
    except ValueError as e:
        raise _bad_request(str(e)) from e
    except RuntimeError as e:
        raise APIError(f"No se pudo leer el Drive compartido: {e}", status_code=502) from e

    return PhotosListResponse(
        source=source,
        folder=folder,
        items=[PhotoInfo(**p) for p in photos],
    )


@router.get("/photo")
def get_photo(
    source: Annotated[str, Query()],
    folder: Annotated[str, Query()],
    file_id: Annotated[str, Query()],
    w: Annotated[int | None, Query(ge=64, le=4000)] = None,
) -> FileResponse:
    """Sirve los bytes de una foto. Auth por `?api_key=` (va en un <img src>).

    El `file_id` se valida contra el listado real de la carpeta — no se
    descarga un ID arbitrario que mande el cliente.

    Con `w` se sirve encogida a ese ancho. No es un lujo de red: el móvil
    guarda cada foto descodificada (ancho × alto × 4 bytes), y con las fichas a
    tamaño original una carpeta se comía ~300 MB y Chrome mataba la pestaña —
    en la APK eso es la app cerrándose sola. Ver `services/thumbs.py`.
    """
    import os

    from src.nicho_pov_bof.services import drive_client

    try:
        photos = drive_client.list_photos(source, folder)
    except ValueError as e:
        raise _bad_request(str(e)) from e
    except RuntimeError as e:
        raise APIError(f"No se pudo leer el Drive compartido: {e}", status_code=502) from e

    match = next((p for p in photos if p["id"] == file_id), None)
    if not match:
        raise PhotoNotFoundError(
            f"La foto {file_id!r} no está en {folder!r}.",
            details={"source": source, "folder": folder},
        )

    suffix = os.path.splitext(match["name"])[1].lower() or ".jpg"
    try:
        path = drive_client.fetch_photo(file_id, suffix=suffix)
    except (ValueError, RuntimeError) as e:
        raise APIError(f"No se pudo descargar la foto: {e}", status_code=502) from e

    media_type = match.get("mime") or "image/jpeg"
    if w:
        from src.nicho_pov_bof.services import thumbs

        encogida = thumbs.miniatura(path, w)
        if encogida != path:
            path, media_type = encogida, "image/jpeg"

    from src.nicho_pov_bof import config as pov_config

    # Un file ID de Drive es inmutable → se puede cachear un día entero. Pero
    # en "Mis productos" el identificador es la RUTA, y esa se REUTILIZA: al
    # borrar un producto y subir otro, `Mis Productos 1/1.jpg` pasa a ser una
    # foto distinta con la misma URL. Cacheando agresivo, el navegador seguía
    # enseñando la anterior durante 24h — que es exactamente lo que pasó.
    propia = pov_config.es_fuente_propia(source)
    return FileResponse(
        path,
        media_type=media_type,
        headers={
            "Cache-Control": "no-cache" if propia else "public, max-age=86400",
        },
    )


@router.get("/backup/check", response_model=BackupCheckResponse)
def backup_check() -> BackupCheckResponse:
    """¿Ha cambiado algo en el Drive de origen desde la última copia?

    Solo lee y compara — no copia nada. Tarda lo que tarde el listado
    recursivo del Drive (~1 min con 2.2k objetos).
    """
    from src.nicho_pov_bof.services import backup_sync

    try:
        return BackupCheckResponse(**backup_sync.check_only())
    except RuntimeError as e:
        raise APIError(f"No se pudo comparar con el origen: {e}", status_code=502) from e


@router.post(
    "/backup/sync",
    response_model=BackupSyncResponse,
    status_code=status.HTTP_201_CREATED,
)
def backup_sync_enqueue(
    queue: Annotated[JobQueue, Depends(get_queue)],
    body: BackupSyncRequest,
) -> BackupSyncResponse:
    """Encola la copia. Va por la cola porque puede tardar mucho."""
    title = "💾 Backup Productos España" + (" (completa)" if body.force_full else "")
    job = queue.enqueue(
        JobMode.NICHO_POV_BOF_BACKUP,
        title=title,
        params={"force_full": bool(body.force_full)},
    )
    pending = [
        j for j in queue.get_all()
        if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
    ]
    position = next((i for i, j in enumerate(pending) if j.id == job.id), 0)
    return BackupSyncResponse(job_id=job.id, title=title, position_in_queue=position)


@router.post("/complete", response_model=MarkCompletedResponse)
def mark_completed(
    body: MarkCompletedRequest,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> MarkCompletedResponse:
    from src.nicho_pov_bof.repos import progress_repo
    from src.nicho_pov_bof.services import drive_client

    try:
        folders = drive_client.list_product_folders(body.source)
    except ValueError as e:
        raise _bad_request(str(e)) from e
    except RuntimeError as e:
        raise APIError(f"No se pudo leer el Drive compartido: {e}", status_code=502) from e

    names = [f["name"] for f in folders]
    if body.folder not in names:
        raise _bad_request(f"Carpeta desconocida en {body.source!r}: {body.folder!r}")

    try:
        if body.completed:
            progress_repo.mark_completed(body.source, body.folder, usuario)
        else:
            progress_repo.unmark_completed(body.source, body.folder, usuario)
        completed = progress_repo.get_completed(body.source, usuario)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e

    next_folder = next((n for n in names if n not in completed), None)

    return MarkCompletedResponse(
        source=body.source,
        folder=body.folder,
        completed=body.completed,
        completed_count=sum(1 for n in names if n in completed),
        total=len(names),
        next_folder=next_folder,
    )
