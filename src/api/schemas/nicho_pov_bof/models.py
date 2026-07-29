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


# ---------------------------------------------------------------------------
# FASE 2 — automatización de vídeos
# ---------------------------------------------------------------------------
class PromptsResponse(BaseModel):
    """Los dos prompts fijos que copia el operador fuera de la app."""

    imagen: str
    video: str


class ProductoInfo(BaseModel):
    """Un producto de una carpeta: emparejado de fotos + textos + estado."""

    producto: str
    clean_photo_id: str | None = None
    titled_photo_id: str | None = None
    titulo: str = ""
    titulo_tiktok_completo: str = ""
    tienda: str = ""
    caption: str = ""
    gancho: str = ""
    cta: str = ""
    uploaded: bool = False
    sold: bool = False
    video_path: str | None = None
    # Marcado = el vídeo lleva gancho, título, CTA y flecha. Sin marcar sale
    # limpio (solo voz, encuadre y quitado de marca si es Veo3).
    con_textos: bool = True


class ProductosListResponse(BaseModel):
    source: str
    folder: str
    items: list[ProductoInfo]
    # True una vez que se pulsó "Obtener textos" con éxito para la carpeta.
    textos_extraidos: bool = False


class ExtraerTextosRequest(BaseModel):
    source: str = Field(..., min_length=1)
    folder: str = Field(..., min_length=1)


class ProductoEstadoRequest(BaseModel):
    """Parche parcial: solo se tocan los campos que vengan poblados."""

    source: str = Field(..., min_length=1)
    folder: str = Field(..., min_length=1)
    producto: str = Field(..., min_length=1)
    uploaded: bool | None = None
    sold: bool | None = None


class ProductoTextosRequest(BaseModel):
    """Marca si el vídeo de ese producto lleva textos y flecha."""

    source: str = Field(..., min_length=1)
    folder: str = Field(..., min_length=1)
    producto: str = Field(..., min_length=1)
    con_textos: bool = True


class VideoUploadResponse(BaseModel):
    ok: bool
    job_id: str | None = None
    message: str


class SoldProductsResponse(BaseModel):
    # Cada item trae source/folder/producto + los campos guardados
    # (titulo, video_path, gancho, cta...) — el schema exacto por producto
    # ya lo valida `ProductoInfo`, aquí basta un dict de paso.
    items: list[dict]
