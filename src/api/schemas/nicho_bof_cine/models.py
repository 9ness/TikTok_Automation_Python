"""Schemas del Nicho BOF Cinematográfico (módulo 10).

Espejo TS en `frontend/lib/types/nichoBofCine.ts`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CinePromptsResponse(BaseModel):
    """Los dos prompts del curso. El de imagen se usa DOS veces —hacen falta
    dos imágenes— y el de vídeo una por imagen."""

    imagen: str
    video: str


class CineSourceInfo(BaseModel):
    slug: str
    label: str


class CineSourcesResponse(BaseModel):
    items: list[CineSourceInfo] = Field(default_factory=list)


class CineProductFolder(BaseModel):
    name: str
    id: str
    completed: bool = False
    # Los vídeos ya están hechos pero falta subirlos (se preparan de días
    # futuros). Independiente de `completed`.
    pendiente_subir: bool = False


class CineFoldersResponse(BaseModel):
    source: str
    items: list[CineProductFolder] = Field(default_factory=list)
    total: int = 0
    completed_count: int = 0
    current: str | None = None


class CineMarkCompletedRequest(BaseModel):
    source: str = Field(..., min_length=1)
    folder: str = Field(..., min_length=1)
    completed: bool = True


class CineMarkPendienteRequest(BaseModel):
    """Marca/desmarca "vídeos hechos, falta subirlos"."""

    source: str = Field(..., min_length=1)
    folder: str = Field(..., min_length=1)
    pendiente: bool = True


class CineMarkCompletedResponse(BaseModel):
    source: str
    folder: str
    completed: bool
    completed_count: int
    total: int
    next_folder: str | None = None


class CineProductoInfo(BaseModel):
    producto: str
    clean_photo_id: str | None = None
    titled_photo_id: str | None = None
    titulo: str = ""
    titulo_tiktok_completo: str = ""
    tienda: str = ""
    caption: str = ""
    emojis: str = ""
    caption_riesgo: str = ""
    gancho: str = ""
    cta: str = ""
    sexo_sugerido: str = "hombre"
    # Cuáles de los dos clips están subidos. Hasta que no están los dos no se
    # monta nada: con uno saldría un vídeo a medias.
    clip1: bool = False
    clip2: bool = False
    # Escaparate: sale del índice ÚNICO por (tienda|nombre), compartido con
    # los demás nichos — al Marketplace el producto se sube una sola vez.
    en_escaparate: bool = False
    uploaded: bool = False
    video_path: str | None = None
    video_listo_at: int = 0
    montando: bool = False


class CineProductosListResponse(BaseModel):
    source: str
    folder: str
    items: list[CineProductoInfo] = Field(default_factory=list)
    textos_extraidos: bool = False
    montando: bool = False


class CineVideoUploadResponse(BaseModel):
    # Vacío mientras falte el otro clip: no hay trabajo que seguir todavía.
    job_id: str = ""
    encolado: bool = False
    message: str


class CineEstadoRequest(BaseModel):
    """Marcar/desmarcar el producto en el escaparate.

    El escaparate es único por producto (tienda|nombre) y compartido con los
    demás nichos: al Marketplace se sube una sola vez.
    """

    source: str
    folder: str
    producto: str
    en_escaparate: bool
