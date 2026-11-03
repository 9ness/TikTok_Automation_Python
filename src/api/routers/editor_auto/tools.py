"""GET /api/v1/editor-auto/tools — descriptores de herramientas disponibles."""

from __future__ import annotations

import os
import shutil
import tempfile
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from src.api.dependencies import get_current_user
from src.api.schemas.editor_auto import ToolDescriptorResponse
from src.api.temp_storage import upload_subdir
from src.editor_auto.tools import list_descriptors


router = APIRouter(
    prefix="/api/v1/editor-auto/tools",
    tags=["editor-auto · tools"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=list[ToolDescriptorResponse])
def list_editor_auto_tools(
    _user: Annotated[str, Depends(get_current_user)],
) -> list[ToolDescriptorResponse]:
    """Lista las herramientas registradas en el registry con su esquema de
    config y peso de ordenación. La UI consume este endpoint para pintar
    el panel de "añadir herramienta" y los formularios de config por
    usuario sin tener nada hardcoded."""
    return [
        ToolDescriptorResponse(
            tool_id=d.tool_id,
            display_name=d.display_name,
            description=d.description,
            position_weight=d.position_weight,
            default_config=d.default_config,
            config_schema=d.config_schema,
        )
        for d in list_descriptors()
    ]


@router.post("/vip-overlays/estilo")
async def estilo_vip_desde_video(
    _user: Annotated[str, Depends(get_current_user)],
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Saca el estilo de edición de un vídeo de referencia del cliente (hoja
    de fotogramas → Claude visión, ~0,002 $) y devuelve la config parcial de
    `vip_overlays`. NO guarda nada: la UI la mezcla en el paso del flujo y el
    operador guarda el flujo como siempre."""
    from src.editor_auto.services.estilo_vip import estilo_desde_video

    suf = os.path.splitext(file.filename or "")[1].lower() or ".mp4"
    fd, path = tempfile.mkstemp(suffix=suf, dir=str(upload_subdir("vip_estilo")))
    try:
        with os.fdopen(fd, "wb") as out:
            shutil.copyfileobj(file.file, out)
        try:
            cfg = await run_in_threadpool(estilo_desde_video, path)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=f"No pude sacar el estilo: {e}") from e
        # La fuente va como ruta del servidor; la UI la muestra por nombre.
        return cfg
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
