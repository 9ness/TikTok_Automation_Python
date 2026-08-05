"""Nicho Gorras — módulo 11.

- GET  /api/v1/nicho-gorras/prompts        → los 6 del curso (1 imagen + 5 escenas)
- GET  /api/v1/nicho-gorras/carpetas       → las 8 de la tienda
- GET  /api/v1/nicho-gorras/gorras         → gorras emparejadas + textos
- POST /api/v1/nicho-gorras/extraer-textos → lee las fichas con Gemini
- GET  /api/v1/nicho-gorras/foto           → foto por file ID
- GET  /api/v1/nicho-gorras/foto-limpia    → descarga la foto de la gorra

No hay subida ni montaje: el vídeo sale del generador y se publica tal cual.
De la app solo hacen falta el producto y sus textos.
"""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from src.api.dependencies import get_current_user
from src.api.exceptions import APIError
from src.api.schemas.nicho_gorras import (
    GorraInfo,
    GorrasCarpeta,
    GorrasCarpetasResponse,
    GorrasListResponse,
    GorrasPrompt,
    GorrasPromptsResponse,
)
from src.nicho_gorras import config
from src.nicho_gorras.repos import product_repo

router = APIRouter(
    prefix="/api/v1/nicho-gorras",
    tags=["nicho-gorras"],
    dependencies=[Depends(get_current_user)],
)

_FILE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,}$")


@router.get("/prompts", response_model=GorrasPromptsResponse)
def get_prompts() -> GorrasPromptsResponse:
    try:
        return GorrasPromptsResponse(items=[
            GorrasPrompt(slug=slug, label=label, texto=config.prompt(slug))
            for slug, label in config.PROMPTS
        ])
    except OSError as e:
        raise APIError(f"No se pudieron leer los prompts: {e}", status_code=500) from e


@router.get("/carpetas", response_model=GorrasCarpetasResponse)
def list_carpetas() -> GorrasCarpetasResponse:
    return GorrasCarpetasResponse(items=[
        GorrasCarpeta(slug=slug, label=meta["label"])
        for slug, meta in config.CARPETAS.items()
    ])


def _listar(carpeta: str) -> GorrasListResponse:
    from src.nicho_gorras.services import text_extractor
    from src.nicho_pov_bof.pipeline.video_editor import caption_arriesgado
    from src.nicho_pov_bof.services import emojis as emojis_svc

    try:
        pares = text_extractor.pares(carpeta)
    except (RuntimeError, ValueError) as e:
        raise APIError(str(e), status_code=502) from e

    doc = product_repo.load(carpeta)
    guardados = doc.get("productos") or {}
    items = []
    for par in pares:
        pid = par["producto"]
        g = guardados.get(pid) or {}
        items.append(GorraInfo(
            producto=pid,
            clean_photo_id=(par.get("clean") or {}).get("id"),
            titled_photo_id=(par.get("titled") or {}).get("id"),
            foto_aviso="" if par.get("confident") else (
                f"Emparejado dudoso ({par.get('reason', '')}) — compruébalo"
            ),
            titulo=g.get("titulo", ""),
            titulo_tiktok_completo=g.get("titulo_tiktok_completo", ""),
            tienda=g.get("tienda", ""),
            caption=g.get("caption", ""),
            emojis=g.get("emojis") or emojis_svc.emojis_para(
                pid, g.get("titulo", ""), g.get("caption", ""),
            ),
            caption_riesgo=caption_arriesgado(g.get("caption", "")) or "",
        ))
    return GorrasListResponse(
        carpeta=carpeta, items=items,
        textos_extraidos=bool(doc.get("textos_extraidos")),
    )


@router.get("/gorras", response_model=GorrasListResponse)
def list_gorras(carpeta: Annotated[str, Query()] = "") -> GorrasListResponse:
    carpeta = carpeta or config.CARPETA_DEFECTO
    if not config.es_carpeta_conocida(carpeta):
        raise APIError(f"Carpeta desconocida: {carpeta!r}", status_code=400)
    return _listar(carpeta)


@router.post("/extraer-textos", response_model=GorrasListResponse)
def extraer_textos(carpeta: Annotated[str, Query()] = "") -> GorrasListResponse:
    from src.nicho_gorras.services import text_extractor

    carpeta = carpeta or config.CARPETA_DEFECTO
    if not config.es_carpeta_conocida(carpeta):
        raise APIError(f"Carpeta desconocida: {carpeta!r}", status_code=400)
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
    return _listar(carpeta)


def _servir(file_id: str, descargar: bool, nombre: str) -> FileResponse:
    from src.nicho_gorras.services import drive_client

    if not _FILE_ID_RE.match(file_id or ""):
        raise APIError(f"file_id no válido: {file_id!r}", status_code=400)
    try:
        path = drive_client.fetch_photo(file_id)
    except (RuntimeError, ValueError) as e:
        raise APIError(str(e), status_code=502) from e
    return FileResponse(
        str(path), media_type="image/jpeg",
        filename=nombre if descargar else None,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/foto")
def get_foto(file_id: Annotated[str, Query()]) -> FileResponse:
    return _servir(file_id, descargar=False, nombre="")


@router.get("/foto-limpia")
def get_foto_limpia(
    producto: Annotated[str, Query()],
    carpeta: Annotated[str, Query()] = "",
) -> FileResponse:
    from src.nicho_gorras.services import text_extractor

    for par in text_extractor.pares(carpeta or config.CARPETA_DEFECTO):
        if par["producto"] == producto:
            foto = par.get("clean") or par.get("titled")
            if not foto:
                raise APIError(f"La gorra {producto} no tiene fotos.", status_code=404)
            return _servir(foto["id"], descargar=True, nombre=f"gorra_{producto}.jpg")
    raise APIError(f"No existe la gorra {producto}.", status_code=404)
