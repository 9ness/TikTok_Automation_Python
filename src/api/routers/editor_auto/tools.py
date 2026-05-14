"""GET /api/v1/editor-auto/tools — descriptores de herramientas disponibles."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.dependencies import get_current_user
from src.api.schemas.editor_auto import ToolDescriptorResponse
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
