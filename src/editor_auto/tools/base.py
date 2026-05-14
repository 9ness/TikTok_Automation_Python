"""Contrato base de las herramientas del Editor Auto.

Cada herramienta recibe:
- `input_path`: vídeo de entrada (MP4 normalmente).
- `output_path`: dónde escribir el vídeo procesado.
- `config`: dict con la config del usuario para esta herramienta.
- `ctx`: contexto compartido (callbacks, paths temp, sub-progreso).

Y devuelve la ruta del vídeo procesado (== output_path en condiciones
normales, pero la firma admite que la herramienta devuelva otra ruta si
necesita componer en sitio).

Las herramientas DEBEN:
- Llamar a `ctx.on_log` para mensajes visibles en la UI.
- Llamar a `ctx.on_progress(frac)` con frac ∈ [0..1] dentro de su slot
  (el orchestrator se encarga de mapear al rango global del job).
- Nunca abortar el pipeline por config opcional — log warning y seguir.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol


SubProgress = Callable[[float, str], None]
LogFn = Callable[[str], None]


@dataclass
class ToolContext:
    """Contexto compartido entre todas las herramientas del flujo de un job."""

    user_id: str
    user_name: str
    job_id: str
    temp_folder: str
    on_log: LogFn
    # Sub-progreso de la herramienta actual [0..1]. El orchestrator inyecta
    # un wrapper que reescala al rango global del job antes de propagar.
    on_progress: SubProgress


@dataclass
class ToolDescriptor:
    """Metadatos públicos de una herramienta (UI los consume)."""

    tool_id: str
    display_name: str
    description: str
    position_weight: int
    default_config: dict[str, Any]
    # Esquema de la config (label, type, options) para que la UI genere
    # un formulario sin tener hardcoded las claves.
    config_schema: list[dict[str, Any]]


class BaseTool(Protocol):
    """Contrato. Implementaciones viven en `tools/<slug>.py`."""

    tool_id: str
    display_name: str
    description: str
    position_weight: int

    def default_config(self) -> dict[str, Any]:
        """Config inicial al añadir la herramienta al flujo de un usuario."""
        ...

    def config_schema(self) -> list[dict[str, Any]]:
        """Esquema declarativo para la UI:
        [{key, label, type, options?, default?, min?, max?}, ...].
        """
        ...

    def descriptor(self) -> ToolDescriptor:
        return ToolDescriptor(
            tool_id=self.tool_id,
            display_name=self.display_name,
            description=self.description,
            position_weight=self.position_weight,
            default_config=self.default_config(),
            config_schema=self.config_schema(),
        )

    def run(
        self,
        *,
        input_path: str,
        output_path: str,
        config: dict[str, Any],
        ctx: ToolContext,
    ) -> str:
        """Ejecuta la herramienta. Devuelve la ruta final (típicamente
        `output_path`)."""
        ...
