"""Sistema de herramientas componibles del Editor Auto.

Cada herramienta implementa `BaseTool` y se registra en `REGISTRY`. El
orchestrator reordena las herramientas activas de un usuario por
`position_weight` (regla fija definida en config) y las ejecuta
secuencialmente sobre el vídeo input.

Para añadir una herramienta nueva:
  1. Crea `tools/<slug>.py` con una clase que herede de BaseTool.
  2. Asigna su `tool_id` (slug canónico).
  3. Registra el peso en `config.TOOL_POSITION_WEIGHTS`.
  4. Añade `REGISTRY[<slug>] = <Class>()` aquí.
"""

from __future__ import annotations

from .base import BaseTool, ToolContext, ToolDescriptor
from .silence_cutter import SilenceCutterTool
from .silence_cutter_scripted import SilenceCutterScriptedTool
from .sticker_arrow import StickerArrowTool
from .subs_auto import SubsAutoTool


REGISTRY: dict[str, BaseTool] = {
    SubsAutoTool.tool_id: SubsAutoTool(),
    SilenceCutterTool.tool_id: SilenceCutterTool(),
    SilenceCutterScriptedTool.tool_id: SilenceCutterScriptedTool(),
    StickerArrowTool.tool_id: StickerArrowTool(),
}


def get_tool(tool_id: str) -> BaseTool | None:
    return REGISTRY.get(tool_id)


def list_descriptors() -> list[ToolDescriptor]:
    """Lista completa de descriptores — usado por la API para exponer las
    herramientas disponibles al frontend."""
    return [t.descriptor() for t in REGISTRY.values()]


__all__ = [
    "BaseTool",
    "ToolContext",
    "ToolDescriptor",
    "REGISTRY",
    "get_tool",
    "list_descriptors",
]
