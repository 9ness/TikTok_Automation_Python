"""Endpoints de FASE 2 del Nicho POV BOF (Programa 4 — Tiktok Shop AI Pro):
automatización de los vídeos por producto.

- GET  /api/v1/nicho-pov-bof/prompts         → los 2 prompts fijos (imagen/vídeo)
- GET  /api/v1/nicho-pov-bof/productos       → productos emparejados + estado
- POST /api/v1/nicho-pov-bof/extraer-textos  → extrae título/tienda/caption con Gemini
- GET  /api/v1/nicho-pov-bof/foto-limpia     → descarga la foto limpia de un producto
- POST /api/v1/nicho-pov-bof/video/upload    → sube el bruto (Veo3/Kling) y encola el montaje
- POST /api/v1/nicho-pov-bof/producto/estado → marca Subido/Vendió
- GET  /api/v1/nicho-pov-bof/vendidos        → productos vendidos (referencia)

Fase 1 (navegación de carpetas/fotos) vive en `folders.py`, sobre el mismo
router prefix — este módulo se registra aparte para no mezclar los dos
momentos del flujo en un único archivo largo.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse

from src.api.dependencies import get_current_user, get_queue
from src.api.exceptions import APIError, PhotoNotFoundError
from src.api.schemas.nicho_pov_bof import (
    ExtraerTextosRequest,
    ProductoEstadoRequest,
    ProductoInfo,
    ProductosListResponse,
    PromptsResponse,
    SoldProductsResponse,
    VideoUploadResponse,
)
from src.queue.manager import JobQueue
from src.queue.models import JobMode

router = APIRouter(
    prefix="/api/v1/nicho-pov-bof",
    tags=["nicho-pov-bof"],
    dependencies=[Depends(get_current_user)],
)

_ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm"}
_ALLOWED_SEXOS = ("hombre", "mujer")
_ALLOWED_ORIGENES = ("veo3", "kling")


def _bad_request(msg: str) -> APIError:
    return APIError(msg, status_code=400)


def _prompts_dir() -> Path:
    import src.nicho_pov_bof as _pkg

    return Path(_pkg.__file__).resolve().parent / "prompts"


@router.get("/prompts", response_model=PromptsResponse)
def get_prompts() -> PromptsResponse:
    """Los DOS prompts fijos que el operador copia fuera de la app (imagen y
    vídeo, para Veo3/Kling/generador de imágenes). Viven en `.md` — nunca
    hardcoded en el código (convención del proyecto)."""
    d = _prompts_dir()
    try:
        imagen = (d / "prompt_imagen.md").read_text(encoding="utf-8").strip()
        video = (d / "prompt_video.md").read_text(encoding="utf-8").strip()
    except OSError as e:
        raise APIError(f"No se pudieron leer los prompts: {e}", status_code=500) from e
    return PromptsResponse(imagen=imagen, video=video)


def _list_productos(source: str, folder: str) -> ProductosListResponse:
    """Compone el emparejado de fotos (`photo_pairing`) con el estado
    guardado en Redis (`product_repo`). Reusada por `/productos` y
    `/extraer-textos` (que devuelve la lista ya actualizada)."""
    from src.nicho_pov_bof.repos import product_repo
    from src.nicho_pov_bof.services import drive_client, photo_pairing

    try:
        photos = drive_client.list_photos(source, folder)
    except ValueError as e:
        raise _bad_request(str(e)) from e
    except RuntimeError as e:
        raise APIError(f"No se pudo leer el Drive compartido: {e}", status_code=502) from e

    # Las dimensiones son la señal principal para distinguir foto limpia de
    # captura con título; `probe_dimensions` descarga (cacheado) si hace falta.
    photos = [drive_client.probe_dimensions(p) for p in photos]
    pairs = photo_pairing.pair_folder(photos)

    folder_state = product_repo.load_folder(source, folder)
    guardados = folder_state.get("productos") or {}

    items: list[ProductoInfo] = []
    for pair in pairs:
        producto = pair["producto"]
        guardado = guardados.get(producto, {})
        clean = pair.get("clean") or {}
        titled = pair.get("titled") or {}
        items.append(
            ProductoInfo(
                producto=producto,
                clean_photo_id=clean.get("id"),
                titled_photo_id=titled.get("id"),
                titulo=guardado.get("titulo", ""),
                titulo_tiktok_completo=guardado.get("titulo_tiktok_completo", ""),
                tienda=guardado.get("tienda", ""),
                caption=guardado.get("caption", ""),
                gancho=guardado.get("gancho", ""),
                cta=guardado.get("cta", ""),
                uploaded=bool(guardado.get("uploaded")),
                sold=bool(guardado.get("sold")),
                video_path=guardado.get("video_path"),
            )
        )

    return ProductosListResponse(
        source=source,
        folder=folder,
        items=items,
        textos_extraidos=bool(folder_state.get("textos_extraidos")),
    )


@router.get("/productos", response_model=ProductosListResponse)
def list_productos(
    source: Annotated[str, Query()],
    folder: Annotated[str, Query()],
) -> ProductosListResponse:
    return _list_productos(source, folder)


@router.post("/extraer-textos", response_model=ProductosListResponse)
def extraer_textos(body: ExtraerTextosRequest) -> ProductosListResponse:
    """Ejecuta la extracción de textos (Gemini, UNA llamada para toda la
    carpeta) y guarda el resultado. Síncrono a propósito — tarda ~1 min pero
    el operador lo pulsa una sola vez por carpeta."""
    from src.nicho_pov_bof.repos import product_repo
    from src.nicho_pov_bof.services import text_extractor

    try:
        textos = text_extractor.extract_folder_texts(body.source, body.folder)
    except ValueError as e:
        raise _bad_request(str(e)) from e

    if textos:
        try:
            product_repo.save_extracted_texts(body.source, body.folder, textos)
        except RuntimeError as e:
            raise APIError(str(e), status_code=503) from e

    return _list_productos(body.source, body.folder)


@router.get("/foto-limpia")
def download_clean_photo(
    source: Annotated[str, Query()],
    folder: Annotated[str, Query()],
    producto: Annotated[str, Query()],
) -> FileResponse:
    """Descarga la FOTO LIMPIA (sin título) de un producto, con un nombre que
    agrupa por carpeta al ordenar en la galería del móvil.

    Auth por `?api_key=`: `get_current_user` (dependencia del router) ya
    acepta el api_key por query además de por header — necesario porque este
    endpoint va en un `<a download>` que no manda headers.
    """
    from src.nicho_pov_bof.services import drive_client, photo_pairing

    try:
        photos = drive_client.list_photos(source, folder)
    except ValueError as e:
        raise _bad_request(str(e)) from e
    except RuntimeError as e:
        raise APIError(f"No se pudo leer el Drive compartido: {e}", status_code=502) from e

    photos = [drive_client.probe_dimensions(p) for p in photos]
    pairs = photo_pairing.pair_folder(photos)
    pair = next((pr for pr in pairs if pr["producto"] == producto), None)
    clean = (pair or {}).get("clean")
    if not clean:
        raise PhotoNotFoundError(
            f"No hay foto limpia para el producto {producto!r} en {folder!r}.",
            details={"source": source, "folder": folder, "producto": producto},
        )

    suffix = os.path.splitext(clean.get("name", ""))[1].lower() or ".jpg"
    try:
        path = drive_client.fetch_photo(clean["id"], suffix=suffix)
    except (ValueError, RuntimeError) as e:
        raise APIError(f"No se pudo descargar la foto: {e}", status_code=502) from e

    # Nombre de descarga: "<carpeta sin espacios>_<NN>.<ext>" — así, al bajar
    # varias fotos al móvil, quedan agrupadas y ordenadas por carpeta+número
    # en vez de mezcladas con el nombre suelto "3.png" que trae Drive.
    folder_slug = re.sub(r"\s+", "_", folder.strip())
    filename = f"{folder_slug}_{producto.zfill(2)}{suffix}"

    return FileResponse(
        path,
        media_type=clean.get("mime") or "image/jpeg",
        filename=filename,  # Starlette pone Content-Disposition: attachment
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.post("/video/upload")
async def upload_video(
    queue: Annotated[JobQueue, Depends(get_queue)],
    operator: Annotated[str, Depends(get_current_user)],
    file: Annotated[UploadFile, File()],
    source: Annotated[str, Form()],
    folder: Annotated[str, Form()],
    producto: Annotated[str, Form()],
    sexo: Annotated[str, Form()],
    origen: Annotated[str, Form()],
    # Marcado por defecto. Sin marcar, el vídeo sale limpio: sin gancho,
    # título, CTA ni flecha; solo la voz (y sin marca de agua si es Veo3).
    con_textos: Annotated[bool, Form()] = True,
) -> VideoUploadResponse:
    """Sube el vídeo bruto generado fuera (Veo3/Kling) y ENCOLA el montaje
    completo (quita marca de agua + normaliza + cuadra duración + textos +
    flecha + audio). El resultado se ve en la Cola; al terminar el producto
    queda marcado `uploaded=True` en Redis."""
    import shutil

    from src.api.temp_storage import upload_subdir

    sexo_norm = (sexo or "").strip().lower()
    if sexo_norm not in _ALLOWED_SEXOS:
        raise _bad_request(f"sexo debe ser 'hombre' o 'mujer', recibido: {sexo!r}")
    origen_norm = (origen or "").strip().lower()
    if origen_norm not in _ALLOWED_ORIGENES:
        raise _bad_request(f"origen debe ser 'veo3' o 'kling', recibido: {origen!r}")

    filename = (file.filename or "").lower()
    ext = next((e for e in _ALLOWED_VIDEO_EXTS if filename.endswith(e)), "")
    if not ext:
        raise _bad_request(
            f"Formato de vídeo no soportado: '{file.filename}'. "
            f"Acepta: {', '.join(sorted(_ALLOWED_VIDEO_EXTS))}."
        )

    dest_dir = upload_subdir("nicho_pov_bof")
    # Nombre único por producto+timestamp: el operador puede resubir el mismo
    # producto (p. ej. tras un fallo) sin pisar el bruto anterior.
    safe_stub = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{source}_{folder}_{producto}")
    raw_path = dest_dir / f"{safe_stub}_{int(time.time())}{ext}"
    try:
        with open(raw_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise APIError(f"No se pudo guardar el vídeo: {e}", status_code=500) from e
    finally:
        await file.close()

    job = queue.enqueue(
        JobMode.NICHO_POV_BOF_VIDEO,
        title=f"🎬 Nicho POV BOF: producto {producto} · {folder}",
        params={
            "source": source,
            "folder": folder,
            "producto": producto,
            "raw_path": str(raw_path),
            "sexo": sexo_norm,
            "origen": origen_norm,
            "con_textos": bool(con_textos),
        },
        enqueued_by=operator or None,
    )
    return VideoUploadResponse(ok=True, job_id=job.id, message="En la cola, procesando…")


@router.post("/producto/estado", response_model=ProductoInfo)
def set_producto_estado(body: ProductoEstadoRequest) -> ProductoInfo:
    """Parche parcial de Subido/Vendió. `update_product` ya ignora los
    campos que vengan `None`, así que el caller puede mandar solo el que
    cambia."""
    from src.nicho_pov_bof.repos import product_repo

    try:
        prod = product_repo.update_product(
            body.source, body.folder, body.producto,
            uploaded=body.uploaded, sold=body.sold,
        )
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e

    return ProductoInfo(
        producto=body.producto,
        titulo=prod.get("titulo", ""),
        titulo_tiktok_completo=prod.get("titulo_tiktok_completo", ""),
        tienda=prod.get("tienda", ""),
        caption=prod.get("caption", ""),
        gancho=prod.get("gancho", ""),
        cta=prod.get("cta", ""),
        uploaded=bool(prod.get("uploaded")),
        sold=bool(prod.get("sold")),
        video_path=prod.get("video_path"),
    )


@router.get("/vendidos", response_model=SoldProductsResponse)
def list_sold(source: Annotated[str | None, Query()] = None) -> SoldProductsResponse:
    """Productos marcados como vendidos, con foto y título — apartado de
    referencia para inspirarse en lo que ya ha funcionado."""
    from src.nicho_pov_bof.repos import product_repo

    return SoldProductsResponse(items=product_repo.sold_products(source))
