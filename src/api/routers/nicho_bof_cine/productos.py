"""Nicho BOF Cinematográfico — módulo 10.

- GET  /api/v1/nicho-bof-cine/prompts         → imagen + vídeo (los del curso)
- GET  /api/v1/nicho-bof-cine/sources         → las mismas fuentes del POV BOF
- GET  /api/v1/nicho-bof-cine/folders         → carpetas + progreso PROPIO
- POST /api/v1/nicho-bof-cine/complete        → marcar carpeta hecha
- GET  /api/v1/nicho-bof-cine/productos       → productos + textos + estado
- POST /api/v1/nicho-bof-cine/extraer-textos  → lee las capturas con Gemini
- GET  /api/v1/nicho-bof-cine/foto-limpia     → descarga la foto del producto
- POST /api/v1/nicho-bof-cine/video/upload    → sube el clip 1 o el 2
- GET  /api/v1/nicho-bof-cine/video           → sirve el vídeo montado

El Drive, las fotos y los textos son los MISMOS que en el Nicho POV BOF (se
reutilizan sus servicios). Lo que es propio: el progreso, el estado por
producto y el montaje.

La subida va por partes: son DOS clips de ~5s por producto y hasta que no están
los dos NO se encola nada. Encolar con uno solo daría un vídeo a medias que
habría que rehacer entero.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse

from src.api.dependencies import get_current_user, get_queue, get_web_user
from src.api.exceptions import APIError
from src.api.schemas.nicho_bof_cine import (
    CineEstadoRequest,
    CineFoldersResponse,
    CineMarkCompletedRequest,
    CineMarkCompletedResponse,
    CinePromptsResponse,
    CineProductoInfo,
    CineProductosListResponse,
    CineSourcesResponse,
    CineSourceInfo,
    CineProductFolder,
    CineVideoUploadResponse,
)
from src.nicho_bof_cine import config
from src.nicho_bof_cine.repos import product_repo, progress_repo
from src.queue.manager import JobQueue
from src.queue.models import JobMode, JobStatus

router = APIRouter(
    prefix="/api/v1/nicho-bof-cine",
    tags=["nicho-bof-cine"],
    dependencies=[Depends(get_current_user)],
)

_ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm"}
_SEXOS = ("hombre", "mujer")


@router.get("/prompts", response_model=CinePromptsResponse)
def get_prompts() -> CinePromptsResponse:
    """Los dos prompts del curso. El de imagen se usa DOS veces (dos imágenes),
    y el de vídeo una por imagen."""
    try:
        return CinePromptsResponse(
            imagen=config.prompt_imagen(), video=config.prompt_video(),
        )
    except OSError as e:
        raise APIError(f"No se pudieron leer los prompts: {e}", status_code=500) from e


@router.get("/sources", response_model=CineSourcesResponse)
def list_sources() -> CineSourcesResponse:
    return CineSourcesResponse(items=[
        CineSourceInfo(slug=slug, label=meta["label"])
        for slug, meta in config.SOURCES.items()
    ])


@router.get("/folders", response_model=CineFoldersResponse)
def list_folders(
    source: Annotated[str, Query()],
    refresh: Annotated[bool, Query()] = False,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> CineFoldersResponse:
    """Carpetas con el progreso de ESTE nicho.

    Las carpetas son las del POV BOF, pero completarlas allí no las completa
    aquí: son vídeos distintos del mismo producto.
    """
    from src.nicho_pov_bof.services import drive_client

    try:
        folders = drive_client.list_product_folders(source, refresh=refresh)
    except ValueError as e:
        raise APIError(str(e), status_code=400) from e
    except RuntimeError as e:
        raise APIError(f"No se pudo leer el Drive compartido: {e}", status_code=502) from e

    completed = progress_repo.get_completed(source, usuario)
    items = [
        CineProductFolder(name=f["name"], id=f["id"], completed=f["name"] in completed)
        for f in folders
    ]
    return CineFoldersResponse(
        source=source,
        items=items,
        total=len(items),
        completed_count=sum(1 for i in items if i.completed),
        current=next((i.name for i in items if not i.completed), None),
    )


@router.post("/complete", response_model=CineMarkCompletedResponse)
def mark_completed(
    body: CineMarkCompletedRequest,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> CineMarkCompletedResponse:
    from src.nicho_pov_bof.services import drive_client

    try:
        nombres = [f["name"] for f in drive_client.list_product_folders(body.source)]
    except (ValueError, RuntimeError) as e:
        raise APIError(str(e), status_code=502) from e
    if body.folder not in nombres:
        raise APIError(
            f"Carpeta desconocida en {body.source!r}: {body.folder!r}", status_code=400,
        )
    try:
        if body.completed:
            progress_repo.mark_completed(body.source, body.folder, usuario)
        else:
            progress_repo.unmark_completed(body.source, body.folder, usuario)
        completed = progress_repo.get_completed(body.source, usuario)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return CineMarkCompletedResponse(
        source=body.source,
        folder=body.folder,
        completed=body.completed,
        completed_count=len(completed),
        total=len(nombres),
        next_folder=next((n for n in nombres if n not in completed), None),
    )


def _montandose(queue: JobQueue | None, source: str, folder: str) -> set[str]:
    if queue is None:
        return set()
    activos: set[str] = set()
    try:
        for job in queue.get_all() or []:
            if job.mode != JobMode.NICHO_BOF_CINE_VIDEO:
                continue
            p = job.params or {}
            if str(p.get("source")) != source or str(p.get("folder")) != folder:
                continue
            if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
                activos.add(str(p.get("producto")))
    except Exception:
        pass
    return activos


def _listar(
    source: str, folder: str, queue: JobQueue | None, usuario: str,
) -> CineProductosListResponse:
    from src.nicho_pov_bof.pipeline.video_editor import caption_arriesgado, textos_fijos
    from src.nicho_pov_bof.services import audience, drive_client, photo_pairing
    from src.nicho_pov_bof.services import emojis as emojis_svc

    try:
        fotos = [
            drive_client.probe_dimensions(f)
            for f in drive_client.list_photos(source, folder)
        ]
    except ValueError as e:
        raise APIError(str(e), status_code=400) from e
    except RuntimeError as e:
        raise APIError(f"No se pudo leer el Drive compartido: {e}", status_code=502) from e

    pares = photo_pairing.pair_folder(fotos)
    estado = product_repo.load_folder_para(source, folder, usuario)
    guardados = estado.get("productos") or {}
    activos = _montandose(queue, source, folder)
    # Una sola lectura del índice de escaparate para toda la carpeta.
    from src.nicho_pov_bof.repos import product_repo as pov_repo

    escaparate = pov_repo.escaparate_index(usuario)

    items: list[CineProductoInfo] = []
    for par in pares:
        pid = par["producto"]
        g = guardados.get(pid) or {}
        fijos = textos_fijos(f"{pid} {folder}")
        items.append(CineProductoInfo(
            producto=pid,
            clean_photo_id=(par.get("clean") or {}).get("id"),
            titled_photo_id=(par.get("titled") or {}).get("id"),
            titulo=g.get("titulo", ""),
            titulo_tiktok_completo=g.get("titulo_tiktok_completo", ""),
            tienda=g.get("tienda", ""),
            caption=g.get("caption", ""),
            emojis=g.get("emojis") or emojis_svc.emojis_para(
                pid, g.get("titulo", ""), g.get("caption", ""),
            ),
            caption_riesgo=caption_arriesgado(g.get("caption", "")) or "",
            gancho=fijos["gancho"],
            cta=fijos["cta"],
            sexo_sugerido=audience.sexo_sugerido(
                g.get("titulo", ""), g.get("titulo_tiktok_completo", ""),
            ),
            # Cuáles de los dos clips están ya subidos: es lo que dice si se
            # puede montar o falta material.
            clip1=bool(g.get("clip1_path")),
            clip2=bool(g.get("clip2_path")),
            en_escaparate=(
                pov_repo.clave_escaparate(g.get("tienda", ""), g.get("titulo", ""))
                in escaparate
            ),
            uploaded=bool(g.get("uploaded")),
            video_path=g.get("video_path"),
            video_listo_at=int(g.get("video_listo_at") or 0),
            montando=pid in activos,
        ))
    return CineProductosListResponse(
        source=source,
        folder=folder,
        items=items,
        textos_extraidos=bool(estado.get("textos_extraidos")),
        montando=bool(activos),
    )


@router.post("/producto/estado", response_model=CineProductoInfo)
def set_producto_estado(
    body: CineEstadoRequest,
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> CineProductoInfo:
    """Mete o saca el producto del escaparate.

    No se guarda en el producto sino en el índice ÚNICO por (tienda|nombre):
    el mismo producto sale en varias carpetas y se graba con varios nichos,
    pero al Marketplace se sube UNA vez. Marcado aquí, sale marcado en el POV
    BOF y en el resto.
    """
    from src.nicho_pov_bof.repos import product_repo as pov_repo

    guardado = product_repo.get_product(body.source, body.folder, body.producto, usuario)
    if not guardado.get("titulo"):
        raise APIError(
            "Este producto no tiene textos todavía: sin el nombre y la tienda no "
            "se puede saber si ya está en el escaparate.",
            status_code=400,
        )
    pov_repo.set_escaparate(
        guardado.get("tienda", ""), guardado.get("titulo", ""),
        body.en_escaparate, usuario,
    )

    listado = _listar(body.source, body.folder, queue, usuario)
    for item in listado.items:
        if item.producto == body.producto:
            return item
    raise APIError(f"No existe el producto {body.producto}.", status_code=404)


@router.get("/productos", response_model=CineProductosListResponse)
def list_productos(
    source: Annotated[str, Query()],
    folder: Annotated[str, Query()],
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> CineProductosListResponse:
    return _listar(source, folder, queue, usuario)


@router.post("/extraer-textos", response_model=CineProductosListResponse)
def extraer_textos(
    source: Annotated[str, Query()],
    folder: Annotated[str, Query()],
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> CineProductosListResponse:
    """Mismo extractor que el POV BOF —son las mismas capturas—, pero lo
    guardado es de este nicho."""
    from src.nicho_pov_bof.services import text_extractor

    logs: list[str] = []
    try:
        textos = text_extractor.extract_folder_texts(source, folder, on_log=logs.append)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    if not textos:
        raise APIError(
            "No se pudo extraer ningún texto. " + (logs[-1] if logs else ""),
            status_code=502,
        )
    try:
        product_repo.save_extracted_texts(source, folder, textos)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return _listar(source, folder, queue, usuario)


@router.get("/foto-limpia")
def foto_limpia(
    source: Annotated[str, Query()],
    folder: Annotated[str, Query()],
    producto: Annotated[str, Query()],
) -> FileResponse:
    """La foto del producto — la que se le da a Flow con el prompt de imagen."""
    from src.nicho_pov_bof.services import drive_client, photo_pairing

    fotos = [
        drive_client.probe_dimensions(f)
        for f in drive_client.list_photos(source, folder)
    ]
    for par in photo_pairing.pair_folder(fotos):
        if par["producto"] == producto:
            foto = par.get("clean") or par.get("titled")
            if not foto:
                raise APIError(f"El producto {producto} no tiene fotos.", status_code=404)
            path = drive_client.fetch_photo(foto["id"])
            return FileResponse(
                str(path), media_type="image/jpeg",
                filename=f"cine_{producto}.jpg",
            )
    raise APIError(f"No existe el producto {producto}.", status_code=404)


@router.post("/video/upload", response_model=CineVideoUploadResponse)
async def upload_video(
    queue: Annotated[JobQueue, Depends(get_queue)],
    operator: Annotated[str, Depends(get_web_user)],
    file: Annotated[UploadFile, File()],
    source: Annotated[str, Form()],
    folder: Annotated[str, Form()],
    producto: Annotated[str, Form()],
    slot: Annotated[int, Form()],
    sexo: Annotated[str, Form()] = "hombre",
) -> CineVideoUploadResponse:
    """Guarda uno de los dos clips. Solo encola cuando están LOS DOS.

    Encolar con un clip daría un vídeo a la mitad de largo que la voz y habría
    que rehacerlo entero, así que se espera. La respuesta dice qué falta.
    """
    from src.api.temp_storage import upload_subdir

    if slot not in (1, 2):
        raise APIError("slot debe ser 1 o 2.", status_code=400)
    nombre = (file.filename or "").lower()
    ext = next((e for e in _ALLOWED_VIDEO_EXTS if nombre.endswith(e)), "")
    if not ext:
        raise APIError(
            f"Formato de vídeo no soportado: {file.filename!r}. "
            f"Acepta: {', '.join(sorted(_ALLOWED_VIDEO_EXTS))}.",
            status_code=400,
        )
    sexo_norm = (sexo or "hombre").strip().lower()
    if sexo_norm not in _SEXOS:
        raise APIError("sexo debe ser 'hombre' o 'mujer'.", status_code=400)

    destino = Path(upload_subdir("nicho_bof_cine")) / (
        f"{producto}_clip{slot}_{int(time.time())}{ext}"
    )
    with destino.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    prod = product_repo.update_product(
        source, folder, producto, usuario=operator,
        **{f"clip{slot}_path": str(destino)},
    )

    clip1, clip2 = prod.get("clip1_path"), prod.get("clip2_path")
    if not (clip1 and clip2):
        falta = 2 if slot == 1 else 1
        return CineVideoUploadResponse(
            job_id="", encolado=False,
            message=f"Clip {slot} guardado. Falta el clip {falta} para montar.",
        )

    job = queue.enqueue(
        JobMode.NICHO_BOF_CINE_VIDEO,
        title=f"🎬 Vídeo Cine · {folder} · producto {producto}",
        params={
            "source": source, "folder": folder, "producto": producto,
            "clip1_path": clip1, "clip2_path": clip2,
            "sexo": sexo_norm, "operator": operator,
        },
    )
    return CineVideoUploadResponse(
        job_id=job.id, encolado=True,
        message="Los dos clips están: montando el vídeo.",
    )


@router.get("/video")
def get_video(
    source: Annotated[str, Query()],
    folder: Annotated[str, Query()],
    producto: Annotated[str, Query()],
    descargar: Annotated[bool, Query()] = False,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> FileResponse:
    prod = product_repo.get_product(source, folder, producto, usuario)
    ruta = prod.get("video_path")
    if not ruta or not Path(ruta).is_file():
        raise APIError(f"El producto {producto} no tiene vídeo montado.", status_code=404)
    return FileResponse(
        ruta, media_type="video/mp4",
        filename=f"cine_{producto}.mp4" if descargar else None,
    )
