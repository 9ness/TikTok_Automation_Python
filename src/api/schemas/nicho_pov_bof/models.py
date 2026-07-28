"""Schemas del Nicho POV BOF (Fase 1 — navegación de productos).

Espejo TS en `frontend/lib/types/nichoPovBof.ts`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SourceInfo(BaseModel):
    slug: str
    label: str


class SourcesListResponse(BaseModel):
    items: list[SourceInfo]


class ProductFolder(BaseModel):
    name: str
    id: str
    completed: bool


class FoldersListResponse(BaseModel):
    source: str
    items: list[ProductFolder]
    total: int
    completed_count: int
    # Primera carpeta no completada — es lo que la UI muestra por defecto.
    # None si ya están todas hechas.
    current: str | None = None


class PhotoInfo(BaseModel):
    id: str
    name: str
    size: int
    mime: str


class PhotosListResponse(BaseModel):
    source: str
    folder: str
    items: list[PhotoInfo]


class MarkCompletedRequest(BaseModel):
    source: str = Field(..., min_length=1)
    folder: str = Field(..., min_length=1)
    completed: bool = True


class BackupCheckResponse(BaseModel):
    """Diff del origen contra la última copia. No copia nada."""

    last_snapshot: str | None = None
    has_changes: bool
    would_be_full: bool
    full_copy_ratio: float
    n_added: int
    n_modified: int
    n_deleted: int
    n_total_source: int
    change_ratio: float


class BackupSyncRequest(BaseModel):
    force_full: bool = False


class BackupSyncResponse(BaseModel):
    job_id: str
    title: str
    position_in_queue: int


class MarkCompletedResponse(BaseModel):
    source: str
    folder: str
    completed: bool
    completed_count: int
    total: int
    next_folder: str | None = None
