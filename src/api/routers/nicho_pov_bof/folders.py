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
    CompartirPaqueteRequest,
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
def list_sources(
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> SourcesListResponse:
    from src.nicho_pov_bof import config
    from src.nicho_pov_bof.services import top_vendidos

    # Cuántos vendidos quedan por traer. Es una resta de dos lecturas de Redis
    # (no toca Drive), así que se puede pedir en cada carga de la pantalla; si
    # falla, se enseña 0 antes que tumbar el selector de fuentes.
    try:
        faltan = top_vendidos.pendientes(usuario)
    except Exception:
        faltan = 0

    return SourcesListResponse(
        items=[
            SourceInfo(
                slug=slug,
                label=meta["label"],
                pendientes=faltan if slug == top_vendidos.SOURCE else 0,
            )
            for slug, meta in config.SOURCES.items()
        ]
    )


@router.get("/folders", response_model=FoldersListResponse)
def list_folders(
    source: Annotated[str, Query()],
    refresh: Annotated[bool, Query()] = False,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> FoldersListResponse:
    from src.nicho_pov_bof.repos import product_repo, progress_repo
    from src.nicho_pov_bof.services import drive_client

    try:
        folders = drive_client.list_product_folders(source, refresh=refresh)
    except ValueError as e:
        raise _bad_request(str(e)) from e
    except RuntimeError as e:
        raise APIError(f"No se pudo leer el Drive compartido: {e}", status_code=502) from e

    completed = progress_repo.get_completed(source, usuario)
    # Cuántos productos de cada carpeta tienen ya la ficha enlazada: es lo que
    # dice desde el listado dónde hay trabajo, sin entrar a mirar.
    try:
        con_url = product_repo.con_url_por_carpeta(
            source, [f["name"] for f in folders],
        )
    except Exception:  # noqa: BLE001
        # Un fallo contando no puede dejar sin listado de carpetas.
        con_url = {}
    items = [
        ProductFolder(
            name=f["name"], id=f["id"], completed=f["name"] in completed,
            desde_copia=bool(f.get("desde_copia")),
            con_url=int(con_url.get(f["name"], 0)),
        )
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

    # Un día entero de caché para todas. Los ids del curso son de Google y no
    # cambian nunca; los de las carpetas propias son la RUTA + la fecha del
    # fichero (`/…/1.jpg#1786…`), así que al sustituir una foto cambia la URL y
    # el navegador se la pide otra vez.
    #
    # Antes las propias iban con `no-cache` justo por eso —la ruta se reutiliza
    # al borrar un producto y subir otro—, y el precio era que el móvil se las
    # volvía a bajar en cada scroll: cargaban lentas y a veces ni salían.
    return FileResponse(
        path,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/backup/paquete")
def backup_paquete_estado() -> dict:
    """El último paquete montado (la carpeta única con TODO el material).

    Nuestro archivo son una copia completa + un delta por día: vale para
    trabajar, pero para DEVOLVERLE el material a quien comparte el Drive hace
    falta una sola carpeta con el árbol original.
    """
    from src.nicho_pov_bof.services import backup_sync

    return backup_sync.paquete_actual()


@router.post(
    "/backup/paquete",
    response_model=BackupSyncResponse,
    status_code=status.HTTP_201_CREATED,
)
def backup_paquete_enqueue(
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> BackupSyncResponse:
    """Encola el montaje del paquete (vuelca todas las copias en una)."""
    title = "📦 Paquete completo Productos España"
    job = queue.enqueue(
        JobMode.NICHO_POV_BOF_BACKUP, title=title, params={"paquete": True},
    )
    pending = [
        j for j in queue.get_all()
        if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
    ]
    position = next((i for i, j in enumerate(pending) if j.id == job.id), 0)
    return BackupSyncResponse(job_id=job.id, title=title, position_in_queue=position)


@router.post("/backup/paquete/compartir")
def backup_paquete_compartir(body: CompartirPaqueteRequest) -> dict:
    """Da acceso al paquete a un correo (le llega el aviso de Google)."""
    from src.nicho_pov_bof.services import backup_sync

    actual = backup_sync.paquete_actual()
    if not actual.get("carpeta"):
        raise _bad_request("Todavía no hay paquete montado: púlsalo antes.")
    try:
        return backup_sync.compartir(actual["carpeta"], body.correo, rol=body.rol)
    except RuntimeError as e:
        raise APIError(str(e), status_code=502) from e


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


@router.get("/backup/ultima")
def backup_ultima() -> dict:
    """Qué hizo la última copia (y cuántos ficheros borró el curso).

    Es una lectura de Redis, no toca Drive: se pide al abrir la pantalla para
    poder avisar de los borrados el mismo día en que pasan.
    """
    from src.nicho_pov_bof.services import backup_sync

    return backup_sync.ultima()


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


@router.post("/textos/lote", status_code=status.HTTP_201_CREATED)
def textos_lote_enqueue(
    queue: Annotated[JobQueue, Depends(get_queue)],
    source: Annotated[str, Query()],
    rehacer: Annotated[bool, Query()] = False,
    uno_a_uno: Annotated[bool, Query()] = False,
    carpetas: Annotated[list[str] | None, Query()] = None,
) -> dict:
    """Encola la extracción de textos de TODAS las carpetas de un catálogo.

    Es del POV BOF porque los textos son del catálogo COMPARTIDO: valen igual
    para POV BOF Largo, Creativos Pro y Carruseles, que leen el mismo
    documento. Por la cola porque son ~1 min de Gemini por carpeta.

    Por defecto solo las que no tienen textos; con `rehacer` se repasan todas
    (cuesta una llamada de Gemini por carpeta, así que no es el caso normal).
    """
    from src.nicho_pov_bof import config as pov_config

    if source not in pov_config.SOURCES:
        raise _bad_request(f"Catálogo desconocido: {source!r}")

    etiqueta = (pov_config.SOURCES[source].get("label") or source)
    solo = [c for c in (carpetas or []) if c.strip()]
    title = (
        f"🔤 Textos · {etiqueta}"
        + (f" · {len(solo)} carpeta(s)" if solo else "")
        + (" (rehacer)" if rehacer else "")
        + (" · una a una" if uno_a_uno else "")
    )
    job = queue.enqueue(
        JobMode.NICHO_POV_BOF_TEXTOS,
        title=title,
        params={
            "source": source,
            "rehacer": bool(rehacer),
            "uno_a_uno": bool(uno_a_uno),
            "carpetas": solo,
        },
    )
    pending = [
        j for j in queue.get_all()
        if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
    ]
    position = next((i for i, j in enumerate(pending) if j.id == job.id), 0)
    return {"job_id": job.id, "title": title, "position_in_queue": position}


@router.post("/textos/revisar", status_code=status.HTTP_201_CREATED)
def revisar_textos_enqueue(
    queue: Annotated[JobQueue, Depends(get_queue)],
    source: Annotated[str, Query()],
    arreglar: Annotated[bool, Query()] = False,
    carpetas: Annotated[list[str] | None, Query()] = None,
) -> dict:
    """Encola la revisión de que cada texto es el de SU producto.

    Le enseña a Gemini la captura de la ficha y el título guardado y pregunta
    si son el mismo producto. Es una llamada por producto (céntimos) y sirve
    para cazar los cruces que dejó la extracción por lotes — un producto con el
    nombre de otro se publica con el texto equivocado y no se nota hasta que
    alguien mira la foto.
    """
    from src.nicho_pov_bof import config as pov_config

    if source not in pov_config.SOURCES:
        raise _bad_request(f"Catálogo desconocido: {source!r}")

    etiqueta = pov_config.SOURCES[source].get("label") or source
    solo = [c for c in (carpetas or []) if c.strip()]
    title = (
        f"🔍 Revisar textos · {etiqueta}"
        + (f" · {len(solo)} carpeta(s)" if solo else "")
        + (" (y arreglar)" if arreglar else "")
    )
    job = queue.enqueue(
        JobMode.NICHO_POV_BOF_REVISAR,
        title=title,
        params={"source": source, "arreglar": bool(arreglar), "carpetas": solo},
    )
    return {"job_id": job.id, "title": title}


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
