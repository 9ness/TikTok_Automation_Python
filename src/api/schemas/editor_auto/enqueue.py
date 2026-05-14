"""Schema de respuesta de POST /enqueue del programa Editor Auto."""

from __future__ import annotations

from pydantic import BaseModel


class EditorAutoEnqueueResponse(BaseModel):
    job_id: str
    title: str
    position_in_queue: int
    input_path_relative: str
    user_name: str
    tool_count: int
