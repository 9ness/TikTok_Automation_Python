"""Schemas del Nicho POV BOF Largo (Programa 4 — Tiktok Shop AI Pro)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class VozLargo(BaseModel):
    id: str
    label: str


class VocesLargoResponse(BaseModel):
    """Banco de voces de Fish, por sexo. El operador solo elige sexo; cuál
    suena se sortea. Se listan para que sepa qué hay detrás."""

    hombre: list[VozLargo] = Field(default_factory=list)
    mujer: list[VozLargo] = Field(default_factory=list)


class ProductoLargo(BaseModel):
    producto: str
    clean_photo_id: str | None = None
    titled_photo_id: str | None = None
    # Textos del producto — vienen del Nicho POV BOF, no se extraen aquí.
    titulo: str = ""
    tienda: str = ""
    caption: str = ""
    emojis: str = ""
    gancho: str = ""
    cta: str = ""
    caption_riesgo: str = ""
    sexo_sugerido: str = ""
    # Lo propio de este nicho.
    guion: str = ""
    subliminal: str = ""
    guion_caracteres: int = 0
    clip1: bool = False
    clip2: bool = False
    voz_label: str = ""
    voz_sexo: str = ""
    uploaded: bool = False
    video_path: str | None = None
    video_listo_at: int = 0
    montando: bool = False


class ProductosLargoResponse(BaseModel):
    source: str
    folder: str
    items: list[ProductoLargo] = Field(default_factory=list)
    montando: bool = False


class GuionLargoRequest(BaseModel):
    source: str
    folder: str
    producto: str
    # Reescribir aunque ya haya uno guardado (el operador no lo ve claro).
    rehacer: bool = False


class GuionLargoResponse(BaseModel):
    producto: ProductoLargo


class ClipLargoUploadResponse(BaseModel):
    job_id: str = ""
    encolado: bool = False
    message: str = ""
