"""Prendas del Nicho Ropa Con Personas — módulo 7.

- GET  /api/v1/nicho-ropa-personas/carpetas       → carpetas de prenda
- GET  /api/v1/nicho-ropa-personas/prendas        → prendas + textos + vídeo
- POST /api/v1/nicho-ropa-personas/extraer-textos → lee las capturas con Gemini
- POST /api/v1/nicho-ropa-personas/prenda/titulo  → título escrito a mano
- POST /api/v1/nicho-ropa-personas/prenda/estado  → mete/saca del escaparate
- GET  /api/v1/nicho-ropa-personas/foto           → foto por file ID
- GET  /api/v1/nicho-ropa-personas/foto-limpia    → descarga la foto de la prenda
- POST /api/v1/nicho-ropa-personas/video/upload   → sube el bruto y encola
- GET  /api/v1/nicho-ropa-personas/video          → sirve el vídeo montado

Solo ropa de MUJER: las tres carpetas que en Drive cuelgan de "Ropa Mujer".
Las camisetas y conjuntos son del módulo 8, en percha.

Esas tres carpetas NO traen captura de la ficha (solo la foto de la prenda,
`IMG_4482.PNG`…), así que no hay texto que leer: el título se escribe a mano
con `POST /prenda/titulo`. El endpoint de extracción se conserva para carpetas
que sí tengan capturas.
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
from src.api.schemas.nicho_ropa_personas import (
    CarpetaRopaPersonas,
    CarpetasRopaPersonasResponse,
    PrendaPersonasEstadoRequest,
    PrendaPersonasInfo,
    PrendasPersonasListResponse,
    TituloPrendaRequest,
    VideoRopaPersonasUploadResponse,
)
from src.nicho_ropa_personas import config
from src.nicho_ropa_personas.repos import product_repo
from src.queue.manager import JobQueue
from src.queue.models import JobMode, JobStatus

router = APIRouter(
    prefix="/api/v1/nicho-ropa-personas",
    tags=["nicho-ropa-personas"],
    dependencies=[Depends(get_current_user)],
)

_ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm"}
_FILE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,}$")


@router.get("/carpetas", response_model=CarpetasRopaPersonasResponse)
def list_carpetas() -> CarpetasRopaPersonasResponse:
    return CarpetasRopaPersonasResponse(items=[
        CarpetaRopaPersonas(slug=slug, label=meta["label"])
        for slug, meta in config.CARPETAS.items()
    ])


def _montando(queue: JobQueue | None, carpeta: str) -> set[str]:
    """Prendas con un montaje en cola o en curso.

    Sale de la COLA, no del estado guardado: el runner escribe `uploaded` y
    `video_path` a la vez al terminar, así que lo guardado no distingue
    "montándose" de "sin empezar".
    """
    if queue is None:
        return set()
    activos: set[str] = set()
    try:
        for job in queue.get_all() or []:
            if job.mode != JobMode.NICHO_ROPA_PERSONAS_VIDEO:
                continue
            if str((job.params or {}).get("carpeta") or config.CARPETA_DEFECTO) != carpeta:
                continue
            if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
                activos.add(str((job.params or {}).get("producto")))
    except Exception:
        pass
    return activos


@router.get("/prendas", response_model=PrendasPersonasListResponse)
def list_prendas(
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    carpeta: Annotated[str, Query()] = "",
    refresh: Annotated[bool, Query()] = False,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> PrendasPersonasListResponse:
    from src.nicho_pov_bof.pipeline.video_editor import caption_arriesgado
    from src.nicho_pov_bof.repos import product_repo as pov_repo
    from src.nicho_pov_bof.services import emojis as emojis_svc
    from src.nicho_ropa.services import text_extractor

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
    sin_ficha = carpeta in config.SIN_CAPTURA_DE_FICHA
    # Una sola lectura del índice de escaparate para toda la carpeta: son 38
    # prendas y preguntar por cada una serían 38 viajes a Redis.
    escaparate = pov_repo.escaparate_index(usuario)

    items = []
    for par in pares:
        pid = par["producto"]
        prod = guardados.get(pid) or {}
        items.append(PrendaPersonasInfo(
            producto=pid,
            clean_photo_id=(par.get("clean") or {}).get("id"),
            titled_photo_id=(par.get("titled") or {}).get("id"),
            # En las carpetas sin captura de ficha, tener UNA sola foto es lo
            # normal: avisar en las 38 prendas era ruido que escondía los
            # avisos de verdad.
            foto_aviso="" if (par.get("confident") or sin_ficha) else (
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
            en_escaparate=pov_repo.marcado_en_escaparate(prod, escaparate),
            uploaded=bool(prod.get("uploaded")),
            video_path=prod.get("video_path"),
            video_listo_at=int(prod.get("video_listo_at") or 0),
            montando=pid in activos,
        ))
    return PrendasPersonasListResponse(
        carpeta=carpeta,
        items=items,
        textos_extraidos=bool(doc.get("textos_extraidos")),
        montando=bool(activos),
    )


@router.post("/extraer-textos", response_model=PrendasPersonasListResponse)
def extraer_textos(
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    carpeta: Annotated[str, Query()] = "",
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> PrendasPersonasListResponse:
    """Pone el título a cada prenda.

    Dos caminos según lo que tenga la carpeta:

    - **Con captura de la ficha** → se LEE el título del listado, como en el
      módulo 8 (mismo extractor, mismas capturas).
    - **Sin captura** (las tres de ropa de mujer) → no hay texto que leer, así
      que se MIRA la foto y Gemini le pone un nombre corto. El operador lo
      corrige si alguno no encaja, en vez de escribir 38 a mano.
    """
    from src.nicho_ropa.services import drive_client, text_extractor

    carpeta = carpeta or config.CARPETA_DEFECTO
    if not config.es_carpeta_conocida(carpeta):
        raise APIError(f"Carpeta desconocida: {carpeta!r}", status_code=400)
    logs: list[str] = []
    try:
        if carpeta in config.SIN_CAPTURA_DE_FICHA:
            from src.nicho_ropa_personas.services import titulador

            textos = titulador.titular(
                text_extractor.pares(carpeta),
                drive_client.fetch_photo,
                on_log=logs.append,
            )
        else:
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
    return list_prendas(queue=queue, carpeta=carpeta, usuario=usuario)


@router.post("/prenda/titulo", response_model=PrendasPersonasListResponse)
def set_titulo(
    body: TituloPrendaRequest,
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> PrendasPersonasListResponse:
    """Título escrito a mano — es el que se quema en el centro del vídeo.

    Las tres carpetas de ropa de mujer no traen captura de la ficha, así que
    aquí no hay nada que extraer con Gemini: lo escribe el operador. Vaciarlo
    es válido (deja la prenda sin texto).
    """
    carpeta = body.carpeta or config.CARPETA_DEFECTO
    if not config.es_carpeta_conocida(carpeta):
        raise APIError(f"Carpeta desconocida: {carpeta!r}", status_code=400)
    try:
        product_repo.update_product(
            carpeta, body.producto, titulo=body.titulo.strip(),
        )
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return list_prendas(queue=queue, carpeta=carpeta, usuario=usuario)


@router.post("/prenda/estado", response_model=PrendaPersonasInfo)
def set_prenda_estado(
    body: PrendaPersonasEstadoRequest,
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> PrendaPersonasInfo:
    """Mete o saca la prenda del escaparate.

    No se guarda en la prenda sino en el índice ÚNICO por (tienda|nombre): el
    mismo producto sale en varias carpetas y se graba con varios nichos, pero
    al Marketplace se sube UNA vez. Marcado aquí, sale marcado en el POV BOF y
    en el resto.
    """
    from src.nicho_pov_bof.repos import product_repo as pov_repo

    carpeta = body.carpeta or config.CARPETA_DEFECTO
    if not config.es_carpeta_conocida(carpeta):
        raise APIError(f"Carpeta desconocida: {carpeta!r}", status_code=400)

    guardado = product_repo.get_product(carpeta, body.producto)
    if not guardado.get("titulo"):
        raise APIError(
            "Este producto no tiene textos todavía: sin el nombre y la tienda no "
            "se puede saber si ya está en el escaparate.",
            status_code=400,
        )
    pov_repo.marcar_escaparate_producto(guardado, body.en_escaparate, usuario)

    listado = list_prendas(queue=queue, carpeta=carpeta, usuario=usuario)
    for item in listado.items:
        if item.producto == body.producto:
            return item
    raise APIError(f"No existe la prenda {body.producto}.", status_code=404)


def _servir_foto(file_id: str, descargar: bool, nombre: str) -> FileResponse:
    from src.nicho_ropa.services import drive_client

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
    return _servir_foto(file_id, descargar=False, nombre="")


@router.get("/foto-limpia")
def get_foto_limpia(
    producto: Annotated[str, Query()],
    carpeta: Annotated[str, Query()] = "",
) -> FileResponse:
    """La foto de la prenda: es la que se le pasa como referencia al generador
    de imagen junto con la ficha de la chica."""
    from src.nicho_ropa.services import text_extractor

    for par in text_extractor.pares(carpeta or config.CARPETA_DEFECTO):
        if par["producto"] == producto:
            clean = par.get("clean") or par.get("titled")
            if not clean:
                raise APIError(f"La prenda {producto} no tiene fotos.", status_code=404)
            return _servir_foto(
                clean["id"], descargar=True, nombre=f"ropa_{producto}.jpg",
            )
    raise APIError(f"No existe la prenda {producto}.", status_code=404)


@router.post("/video/upload", response_model=VideoRopaPersonasUploadResponse)
async def upload_video(
    queue: Annotated[JobQueue, Depends(get_queue)],
    operator: Annotated[str, Depends(get_web_user)],
    file: Annotated[UploadFile, File()],
    producto: Annotated[str, Form()],
    carpeta: Annotated[str, Form()] = "",
) -> VideoRopaPersonasUploadResponse:
    """Sube el vídeo de 8s generado fuera y encola el montaje.

    No hay opción de mudo ni de sexo de voz, al revés que en el módulo 8: aquí
    SIEMPRE lleva una de las cinco locutoras, sorteada.
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
    carpeta = carpeta or config.CARPETA_DEFECTO
    if not config.es_carpeta_conocida(carpeta):
        raise APIError(f"Carpeta desconocida: {carpeta!r}", status_code=400)

    dest_dir = upload_subdir("nicho_ropa_personas")
    destino = Path(dest_dir) / f"{producto}_{int(time.time())}{ext}"
    with destino.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    label = config.CARPETAS.get(carpeta, {}).get("label", carpeta)
    job = queue.enqueue(
        JobMode.NICHO_ROPA_PERSONAS_VIDEO,
        title=f"👗 Vídeo Ropa Con Personas · {label} · prenda {producto}",
        params={
            "producto": producto,
            "carpeta": carpeta,
            "raw_path": str(destino),
            "operator": operator,
        },
    )
    return VideoRopaPersonasUploadResponse(
        job_id=job.id, message="Encolado con voz de mujer (una de las cinco)",
    )


@router.get("/video")
def get_video(
    producto: Annotated[str, Query()],
    carpeta: Annotated[str, Query()] = "",
    descargar: Annotated[bool, Query()] = False,
) -> FileResponse:
    prod = product_repo.get_product(carpeta or config.CARPETA_DEFECTO, producto)
    ruta = prod.get("video_path")
    if not ruta or not Path(ruta).is_file():
        raise APIError(f"La prenda {producto} no tiene vídeo montado.", status_code=404)
    return FileResponse(
        ruta,
        media_type="video/mp4",
        filename=Path(ruta).name if descargar else None,
    )
