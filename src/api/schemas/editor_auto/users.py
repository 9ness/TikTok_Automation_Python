"""Schemas Pydantic para users del programa Editor Auto."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolStepIn(BaseModel):
    """ToolStep tal y como llega del frontend."""

    tool_id: str
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class EditorUserCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    display_name: str = ""
    description: str = ""
    tool_flow: list[ToolStepIn] = Field(default_factory=list)


class EditorUserUpdateRequest(BaseModel):
    display_name: str | None = None
    description: str | None = None
    tool_flow: list[ToolStepIn] | None = None
    auto_enqueue: bool | None = None


class EditorUserResponse(BaseModel):
    id: str
    name: str
    display_name: str
    description: str
    tool_flow: list[ToolStepIn]
    drive_folder: str | None
    output_folder: str | None
    auto_enqueue: bool = False
    deleted: bool
    created_at: str
    updated_at: str
