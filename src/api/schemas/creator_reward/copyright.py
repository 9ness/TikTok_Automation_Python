"""Schemas Pydantic del nicho 🛡️ Quitar Copy.

Solo response — el endpoint usa multipart/form-data, no body JSON.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


CleanModeValue = Literal[
    "Subtítulos Virales",
    "Camuflaje Geométrico (Sin Subtítulos)",
    "Solo Limpiar (Sin Subtítulos)",
    "Limpiar Metadata (Sin Tocar Subtítulos)",
]
HookYPctValue = Literal[0.20, 0.45, 0.75]


class CopyrightEnqueueResponse(BaseModel):
    job_id: str
    title: str
    position_in_queue: int
    input_path_relative: str  # path relativo a temp_root (ej. "api_uploads/copyright/clean_in_1234.mp4")
