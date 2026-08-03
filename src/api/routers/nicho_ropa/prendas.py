"""Endpoints del Nicho Ropa Sin Personas (Programa 4 — módulo 8).

- GET  /api/v1/nicho-ropa/prompts        → imagen + vídeo (con y sin manos)
- GET  /api/v1/nicho-ropa/prendas        → prendas emparejadas + textos
- POST /api/v1/nicho-ropa/extraer-textos → lee las capturas con Gemini
- GET  /api/v1/nicho-ropa/foto           → sirve una foto por file ID
- GET  /api/v1/nicho-ropa/foto-limpia    → descarga la foto de la prenda
- POST /api/v1/nicho-ropa/video/upload   → sube el bruto y encola el montaje
- GET  /api/v1/nicho-ropa/video          → sirve el vídeo ya montado

Es UNA sola carpeta de Drive, compartida por enlace, así que ningún endpoint
lleva `source`/`folder` — a diferencia del Nicho POV BOF.
"""

from __future__ import annotations

import re
import shutil
import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse

from src.api.dependencies import get_current_user, get_queue, get_web_user
from src.api.exceptions import APIError
from src.api.schemas.nicho_ropa import (
    CarpetaRopa,
    CarpetasRopaResponse,
    PrendaInfo,
    PrendasListResponse,
    PromptsRopaResponse,
    VideoRopaUploadResponse,
)
from src.nicho_ropa import config
from src.nicho_ropa.repos import product_repo
from src.nicho_ropa.services import drive_client, text_extractor
from src.queue.manager import JobQueue
from src.queue.models import JobMode, JobStatus

router = APIRouter(
    prefix="/api/v1/nicho-ropa",
    tags=["nicho-ropa"],
    dependencies=[Depends(get_current_user)],
)

_ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm"}
_FILE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,}$")


@router.get("/prompts", response_model=PromptsRopaResponse)
def get_prompts() -> PromptsRopaResponse:
    """Los prompts del curso. El de vídeo, en sus dos versiones."""
    try:
        return PromptsRopaResponse(
            imagen=config.prompt_imagen(),
            video_con_manos=config.prompt_video(True),
            video_sin_manos=config.prompt_video(False),
            video_percha=config.prompt_video_percha(),
        )
    except OSError as e:
        raise APIError(f"No se pudieron leer los prompts: {e}", status_code=500) from e


@router.get("/carpetas", response_model=CarpetasRopaResponse)
def list_carpetas() -> CarpetasRopaResponse:
    """Carpetas de producto disponibles.

    Las de mujer (mono, pantalón corto, bikinis) son las del nicho CON
    personas, pero la misma prenda vale aquí colgada en percha: lo que cambia
    es el prompt, no la foto.
    """
    return CarpetasRopaResponse(items=[
        CarpetaRopa(slug=slug, label=meta["label"])
        for slug, meta in config.CARPETAS.items()
    ])


def _montando(queue: JobQueue | None, carpeta: str) -> set[str]:
    """Prendas con un montaje en cola o en curso.

    Sale de la COLA y no del estado guardado, por lo mismo que en el otro
    nicho: el runner escribe `uploaded` y `video_path` a la vez al terminar,
    así que lo guardado no distingue "montándose" de "sin empezar".
    """
    if queue is None:
        return set()
    activos = set()
    try:
        for job in queue.list_jobs():
            if job.mode != JobMode.NICHO_ROPA_VIDEO:
                continue
            if str(job.params.get("carpeta") or config.CARPETA_DEFECTO) != carpeta:
                continue
            if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
                activos.add(str(job.params.get("producto")))
    except Exception:
        pass
    return activos


@router.get("/prendas", response_model=PrendasListResponse)
def list_prendas(
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    carpeta: Annotated[str, Query()] = "",
    refresh: Annotated[bool, Query()] = False,
) -> PrendasListResponse:
    """Prendas de la carpeta, con su foto limpia, su captura y sus textos."""
    from src.nicho_pov_bof.pipeline.video_editor import caption_arriesgado
    from src.nicho_pov_bof.services import emojis as emojis_svc

    carpeta = carpeta or config.CARPETA_DEFECTO
    if not config.es_carpeta_conocida(carpeta):
        raise APIError(f"Carpeta desconocida: {carpeta!r}", status_code=400)
    try:
        pares = text_extractor.pares(carpeta, refresh=refresh)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e

    doc = product_repo.load(carpeta)
    guardados = doc.get("productos") or {}
    activos = _montando(queue, carpeta)

    items = []
    for par in pares:
        pid = par["producto"]
        prod = guardados.get(pid) or {}
        items.append(PrendaInfo(
            producto=pid,
            clean_photo_id=(par.get("clean") or {}).get("id"),
            titled_photo_id=(par.get("titled") or {}).get("id"),
            foto_aviso="" if par.get("confident") else (
                "No se distingue cuál es la foto de la prenda — compruébala"
            ),
            titulo=prod.get("titulo", ""),
            titulo_tiktok_completo=prod.get("titulo_tiktok_completo", ""),
            tienda=prod.get("tienda", ""),
            caption=prod.get("caption", ""),
            emojis=prod.get("emojis") or emojis_svc.emojis_para(
                pid, prod.get("titulo", ""), prod.get("caption", ""),
            ),
            caption_riesgo=caption_arriesgado(prod.get("caption", "")) or "",
            uploaded=bool(prod.get("uploaded")),
            video_path=prod.get("video_path"),
            video_listo_at=int(prod.get("video_listo_at") or 0),
            montando=pid in activos,
        ))
    return PrendasListResponse(
        carpeta=carpeta,
        items=items,
        textos_extraidos=bool(doc.get("textos_extraidos")),
        montando=bool(activos),
    )


@router.post("/extraer-textos", response_model=PrendasListResponse)
def extraer_textos(
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    carpeta: Annotated[str, Query()] = "",
) -> PrendasListResponse:
    """Lee las capturas con Gemini y guarda título, tienda, caption y emojis.

    Va síncrono como en el otro nicho: es UNA llamada con todas las imágenes.
    """
    carpeta = carpeta or config.CARPETA_DEFECTO
    logs: list[str] = []
    try:
        textos = text_extractor.extract_texts(carpeta, on_log=logs.append)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    if not textos:
        raise APIError(
            "No se pudo extraer ningún texto. " + (logs[-1] if logs else ""),
            status_code=502,
        )
    try:
        product_repo.save_extracted_texts(carpeta, textos)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return list_prendas(queue=queue, carpeta=carpeta)


def _servir_foto(file_id: str, descargar: bool, nombre: str) -> FileResponse:
    if not _FILE_ID_RE.match(file_id or ""):
        raise APIError(f"file_id no válido: {file_id!r}", status_code=400)
    try:
        path = drive_client.fetch_photo(file_id)
    except (RuntimeError, ValueError) as e:
        raise APIError(str(e), status_code=502) from e
    return FileResponse(
        str(path),
        media_type="image/jpeg",
        filename=nombre if descargar else None,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/foto")
def get_foto(file_id: Annotated[str, Query()]) -> FileResponse:
    """Miniatura/foto por file ID (el nombre no vale: hay duplicados)."""
    return _servir_foto(file_id, descargar=False, nombre="")


@router.get("/foto-limpia")
def get_foto_limpia(
    producto: Annotated[str, Query()],
    carpeta: Annotated[str, Query()] = "",
) -> FileResponse:
    """Descarga la foto de la prenda — la que se le da al generador."""
    for par in text_extractor.pares(carpeta or config.CARPETA_DEFECTO):
        if par["producto"] == producto:
            clean = par.get("clean") or par.get("titled")
            if not clean:
                raise APIError(f"La prenda {producto} no tiene fotos.", status_code=404)
            return _servir_foto(
                clean["id"], descargar=True, nombre=f"ropa_{producto}.jpg",
            )
    raise APIError(f"No existe la prenda {producto}.", status_code=404)


@router.post("/video/upload", response_model=VideoRopaUploadResponse)
async def upload_video(
    queue: Annotated[JobQueue, Depends(get_queue)],
    operator: Annotated[str, Depends(get_web_user)],
    file: Annotated[UploadFile, File()],
    producto: Annotated[str, Form()],
    carpeta: Annotated[str, Form()] = "",
    # Vacío = mudo, que es el modo por defecto de este nicho.
    sexo: Annotated[str, Form()] = "",
) -> VideoRopaUploadResponse:
    """Sube el vídeo generado fuera y encola el encuadre.

    Sin `sexo` el vídeo sale MUDO a propósito: la música la pone el operador
    al publicar.
    """
    from src.api.temp_storage import upload_subdir

    nombre = (file.filename or "").lower()
    ext = next((e for e in _ALLOWED_VIDEO_EXTS if nombre.endswith(e)), "")
    if not ext:
        raise APIError(
            f"Formato de vídeo no soportado: {file.filename!r}. "
            f"Acepta: {', '.join(sorted(_ALLOWED_VIDEO_EXTS))}.",
            status_code=400,
        )
    sexo_norm = (sexo or "").strip().lower()
    if sexo_norm and sexo_norm not in ("hombre", "mujer"):
        raise APIError("sexo debe ser 'hombre', 'mujer' o vacío.", status_code=400)

    dest_dir = upload_subdir("nicho_ropa")
    destino = Path(dest_dir) / f"{producto}_{int(time.time())}{ext}"
    with destino.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    job = queue.enqueue(
        JobMode.NICHO_ROPA_VIDEO,
        title=(
            f"👕 Vídeo Nicho Ropa · {config.carpeta_label(carpeta or config.CARPETA_DEFECTO)}"
            f" · prenda {producto}"
        ),
        params={
            "producto": producto,
            "carpeta": carpeta or config.CARPETA_DEFECTO,
            "raw_path": str(destino),
            "sexo": sexo_norm,
            "operator": operator,
        },
    )
    return VideoRopaUploadResponse(
        job_id=job.id,
        message=(
            "Encolado. Sale mudo" if not sexo_norm
            else f"Encolado con voz de {sexo_norm}"
        ),
    )


@router.get("/video")
def get_video(
    producto: Annotated[str, Query()],
    carpeta: Annotated[str, Query()] = "",
    descargar: Annotated[bool, Query()] = False,
) -> FileResponse:
    """Sirve el vídeo ya montado."""
    prod = product_repo.get_product(carpeta or config.CARPETA_DEFECTO, producto)
    ruta = prod.get("video_path")
    if not ruta or not Path(ruta).is_file():
        raise APIError(f"La prenda {producto} no tiene vídeo montado.", status_code=404)
    return FileResponse(
        ruta,
        media_type="video/mp4",
        filename=f"ropa_{producto}.mp4" if descargar else None,
    )
