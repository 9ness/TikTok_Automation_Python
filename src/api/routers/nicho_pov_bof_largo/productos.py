"""Endpoints del Nicho POV BOF Largo (Programa 4 — Tiktok Shop AI Pro).

- GET  /api/v1/nicho-pov-bof-largo/voces       → banco de voces por sexo
- GET  /api/v1/nicho-pov-bof-largo/sources     → las 2 fuentes de Drive
- GET  /api/v1/nicho-pov-bof-largo/folders     → carpetas de productos
- GET  /api/v1/nicho-pov-bof-largo/productos   → productos + guion + estado
- POST /api/v1/nicho-pov-bof-largo/guion       → escribe (o reescribe) el guion
- POST /api/v1/nicho-pov-bof-largo/clip/upload → sube 1 de los 2 clips
- GET  /api/v1/nicho-pov-bof-largo/video       → sirve el vídeo montado

Las fotos y los TEXTOS del producto salen del Nicho POV BOF: aquí no se extrae
nada, solo se consulta. Lo que se guarda de propio es el guion, los clips y el
vídeo montado, y va por usuario.
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
from src.api.schemas.nicho_pov_bof_largo import (
    ClipLargoUploadResponse,
    GuionLargoRequest,
    GuionLargoResponse,
    ProductoLargo,
    ProductosLargoResponse,
    VocesLargoResponse,
    VozLargo,
)
from src.nicho_pov_bof_largo import config
from src.nicho_pov_bof_largo.repos import product_repo
from src.queue.manager import JobQueue
from src.queue.models import JobMode, JobStatus

router = APIRouter(
    prefix="/api/v1/nicho-pov-bof-largo",
    tags=["nicho-pov-bof-largo"],
    dependencies=[Depends(get_current_user)],
)

_EXTS_VIDEO = {".mp4", ".mov", ".mkv", ".webm"}


def _bad(msg: str) -> APIError:
    return APIError(msg, status_code=400)


@router.get("/voces", response_model=VocesLargoResponse)
def list_voces() -> VocesLargoResponse:
    return VocesLargoResponse(
        hombre=[VozLargo(**v) for v in config.VOCES["hombre"]],
        mujer=[VozLargo(**v) for v in config.VOCES["mujer"]],
    )


@router.get("/sources")
def list_sources() -> dict:
    return {"items": [
        {"slug": slug, "label": meta.get("label", slug)}
        for slug, meta in config.SOURCES.items()
    ]}


@router.get("/folders")
def list_folders(
    source: Annotated[str, Query()],
    refresh: Annotated[bool, Query()] = False,
) -> dict:
    from src.nicho_pov_bof.services import drive_client

    try:
        carpetas = drive_client.list_product_folders(source, refresh=refresh)
    except ValueError as e:
        raise _bad(str(e)) from e
    except RuntimeError as e:
        raise APIError(f"No se pudo leer el Drive: {e}", status_code=502) from e
    return {"items": [{"name": c.get("name")} for c in carpetas]}


def _montandose(queue: JobQueue | None, source: str, folder: str) -> set[str]:
    if queue is None:
        return set()
    activos: set[str] = set()
    try:
        for job in queue.get_all() or []:
            if job.mode != JobMode.NICHO_POV_BOF_LARGO_VIDEO:
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
) -> ProductosLargoResponse:
    from src.nicho_pov_bof.pipeline.video_editor import caption_arriesgado, textos_fijos
    from src.nicho_pov_bof.services import audience, drive_client, photo_pairing
    from src.nicho_pov_bof.services import emojis as emojis_svc

    try:
        fotos = [
            drive_client.probe_dimensions(f)
            for f in drive_client.list_photos(source, folder)
        ]
    except ValueError as e:
        raise _bad(str(e)) from e
    except RuntimeError as e:
        raise APIError(f"No se pudo leer el Drive: {e}", status_code=502) from e

    pares = photo_pairing.pair_folder(fotos)
    propio = (product_repo.load_folder(source, folder, usuario).get("productos") or {})
    activos = _montandose(queue, source, folder)

    items: list[ProductoLargo] = []
    for par in pares:
        pid = str(par["producto"])
        # Los textos del producto son del POV BOF; lo de este nicho es `mio`.
        textos = product_repo.textos_producto(source, folder, pid, usuario)
        mio = propio.get(pid) or {}
        fijos = textos_fijos(f"{pid} {folder}")
        guion = str(mio.get("guion") or "")
        items.append(ProductoLargo(
            producto=pid,
            clean_photo_id=(par.get("clean") or {}).get("id"),
            titled_photo_id=(par.get("titled") or {}).get("id"),
            titulo=textos.get("titulo", ""),
            tienda=textos.get("tienda", ""),
            caption=textos.get("caption", ""),
            emojis=textos.get("emojis") or emojis_svc.emojis_para(
                pid, textos.get("titulo", ""), textos.get("caption", ""),
            ),
            gancho=fijos["gancho"],
            cta=fijos["cta"],
            caption_riesgo=caption_arriesgado(textos.get("caption", "")) or "",
            sexo_sugerido=audience.sexo_sugerido(
                textos.get("titulo", ""), textos.get("titulo_tiktok_completo", ""),
            ),
            guion=guion,
            subliminal=str(mio.get("subliminal") or ""),
            guion_caracteres=len(guion),
            clip1=bool(mio.get("clip1_path")),
            clip2=bool(mio.get("clip2_path")),
            voz_label=str(mio.get("voz_label") or ""),
            voz_sexo=str(mio.get("voz_sexo") or ""),
            uploaded=bool(mio.get("uploaded")),
            video_path=mio.get("video_path"),
            video_listo_at=int(mio.get("video_listo_at") or 0),
            montando=pid in activos,
        ))
    return ProductosLargoResponse(
        source=source, folder=folder, items=items, montando=bool(activos),
    )


@router.get("/productos", response_model=ProductosLargoResponse)
def list_productos(
    source: Annotated[str, Query()],
    folder: Annotated[str, Query()],
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> ProductosLargoResponse:
    return _listar(source, folder, queue, usuario)


@router.post("/guion", response_model=GuionLargoResponse)
def escribir_guion(
    body: GuionLargoRequest,
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> GuionLargoResponse:
    """Escribe el guion locutado de UN producto con el prompt del curso.

    Se guarda: remontar el mismo producto reutiliza el guion en vez de gastar
    otra llamada y salir distinto. Con `rehacer=True` se fuerza uno nuevo.
    """
    from src.nicho_pov_bof_largo.services import guionista

    guardado = product_repo.get_product(
        body.source, body.folder, body.producto, usuario
    )
    if guardado.get("guion") and not body.rehacer:
        return _uno(body, queue, usuario)

    textos = product_repo.textos_producto(
        body.source, body.folder, body.producto, usuario
    )
    if not textos.get("titulo"):
        raise _bad(
            "Este producto no tiene textos extraídos todavía. Pásale "
            "'Obtener textos' en el Nicho POV BOF y vuelve."
        )

    foto = None
    try:
        from src.nicho_pov_bof.services import drive_client, photo_pairing

        fotos = [
            drive_client.probe_dimensions(f)
            for f in drive_client.list_photos(body.source, body.folder)
        ]
        par = next(
            (x for x in photo_pairing.pair_folder(fotos)
             if str(x.get("producto")) == body.producto), None,
        )
        limpia = (par or {}).get("clean") or {}
        if limpia.get("id"):
            foto = drive_client.fetch_photo(limpia["id"], suffix=".jpg")
    except Exception:
        foto = None

    try:
        escrito = guionista.escribir(
            titulo=textos.get("titulo", ""),
            tienda=textos.get("tienda", ""),
            caption=textos.get("caption", ""),
            foto=foto,
        )
    except ValueError as e:
        raise APIError(str(e), status_code=422) from e
    except Exception as e:
        raise APIError(f"Gemini no pudo escribir el guion: {e}", status_code=502) from e

    try:
        product_repo.update_product(
            body.source, body.folder, body.producto, usuario=usuario,
            guion=escrito["guion"], subliminal=escrito["subliminal"],
            nombre_guion=escrito["nombre"],
        )
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return _uno(body, queue, usuario)


def _uno(body: GuionLargoRequest, queue, usuario: str) -> GuionLargoResponse:
    listado = _listar(body.source, body.folder, queue, usuario)
    for item in listado.items:
        if item.producto == body.producto:
            return GuionLargoResponse(producto=item)
    raise APIError(f"No existe el producto {body.producto}.", status_code=404)


@router.post("/clip/upload", response_model=ClipLargoUploadResponse)
async def upload_clip(
    queue: Annotated[JobQueue, Depends(get_queue)],
    file: Annotated[UploadFile, File()],
    source: Annotated[str, Form()],
    folder: Annotated[str, Form()],
    producto: Annotated[str, Form()],
    slot: Annotated[int, Form()],
    sexo: Annotated[str, Form()],
    con_gancho: Annotated[bool, Form()] = True,
    con_titulo: Annotated[bool, Form()] = True,
    con_cta: Annotated[bool, Form()] = True,
    con_flecha: Annotated[bool, Form()] = True,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> ClipLargoUploadResponse:
    """Sube UNO de los dos clips. Solo encola cuando están los dos.

    Con un solo clip no hay nada que montar: el guion dura ~20s y un clip son
    10s, así que faltaría medio vídeo.
    """
    from src.api.temp_storage import upload_subdir

    if slot not in (1, 2):
        raise _bad(f"slot debe ser 1 o 2, recibido: {slot}")
    sexo_norm = (sexo or "").strip().lower()
    if sexo_norm not in config.SEXOS:
        raise _bad(f"sexo debe ser {' o '.join(config.SEXOS)}, recibido: {sexo!r}")

    guardado = product_repo.get_product(source, folder, producto, usuario)
    if not guardado.get("guion"):
        raise _bad(
            "Primero escribe el guion de este producto: la voz sale de ahí y "
            "es la que decide cuánto dura el vídeo."
        )

    nombre = (file.filename or "").lower()
    ext = next((e for e in _EXTS_VIDEO if nombre.endswith(e)), "")
    if not ext:
        raise _bad(
            f"Formato de vídeo no soportado: {file.filename!r}. "
            f"Acepta: {', '.join(sorted(_EXTS_VIDEO))}."
        )

    stub = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{source}_{folder}_{producto}")
    destino = upload_subdir("nicho_pov_bof_largo") / (
        f"{stub}_clip{slot}_{int(time.time())}{ext}"
    )
    try:
        with destino.open("wb") as out:
            shutil.copyfileobj(file.file, out)
    except Exception as e:
        raise APIError(f"No se pudo guardar el clip: {e}", status_code=500) from e
    finally:
        await file.close()

    try:
        prod = product_repo.update_product(
            source, folder, producto, usuario=usuario,
            **{f"clip{slot}_path": str(destino)},
        )
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e

    if not (prod.get("clip1_path") and prod.get("clip2_path")):
        falta = 2 if slot == 1 else 1
        return ClipLargoUploadResponse(
            encolado=False, message=f"Clip {slot} guardado. Falta el clip {falta}.",
        )

    job = queue.enqueue(
        JobMode.NICHO_POV_BOF_LARGO_VIDEO,
        title=f"🎙️ POV BOF Largo: producto {producto} · {folder}",
        params={
            "source": source, "folder": folder, "producto": producto,
            "clip1_path": prod["clip1_path"], "clip2_path": prod["clip2_path"],
            "sexo": sexo_norm, "operator": usuario,
            "con_gancho": bool(con_gancho), "con_titulo": bool(con_titulo),
            "con_cta": bool(con_cta), "con_flecha": bool(con_flecha),
        },
        enqueued_by=usuario or None,
    )
    return ClipLargoUploadResponse(
        job_id=job.id, encolado=True,
        message="Los dos clips están: locutando y montando.",
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
        raise APIError(
            f"El producto {producto} no tiene vídeo montado.", status_code=404,
        )
    return FileResponse(
        ruta, media_type="video/mp4",
        filename=f"povlargo_{producto}_{folder}.mp4" if descargar else None,
    )
