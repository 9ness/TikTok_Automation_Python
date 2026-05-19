"""Schemas Pydantic del nicho 🏗️ Construcción POV."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ConstruccionPovEnqueueResponse(BaseModel):
    job_id: str
    title: str
    position_in_queue: int
    input_path_relative: str


class ConstruccionPovGenerateScriptResponse(BaseModel):
    """Output del paso 1 del flujo semi-automático.

    El cliente sube el vídeo, recibe el guion candidato + el `input_path_relative`
    (donde ya está guardado el upload) y la duración real. Luego, si el usuario
    aprueba, llama a `/enqueue` reusando ese `input_path_relative` (sin volver
    a subir el archivo) y pasando el guion aprobado como `manual_script`.
    """

    script: str
    target_chars: int
    duration_seconds: float
    input_path_relative: str
    gemini_model: str


# ---------------------------------------------------------------------------
# Presets — favoritos persistentes en Redis (namespace "pov")
# ---------------------------------------------------------------------------
class ConstruccionPovPresetResponse(BaseModel):
    name: str
    config: dict[str, Any]


class ConstruccionPovPresetListResponse(BaseModel):
    items: list[str]
    total: int
