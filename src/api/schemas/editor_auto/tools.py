"""Schema Pydantic para descriptores de herramientas (GET /tools)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ToolDescriptorResponse(BaseModel):
    tool_id: str
    display_name: str
    description: str
    position_weight: int
    default_config: dict[str, Any]
    config_schema: list[dict[str, Any]]
