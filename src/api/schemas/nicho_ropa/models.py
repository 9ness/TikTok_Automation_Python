"""Schemas del Nicho Ropa Sin Personas (Programa 4 — módulo 8).

Espejo TS en `frontend/lib/types/nichoRopa.ts`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PromptsRopaResponse(BaseModel):
    """Los prompts que el operador copia fuera de la app.

    El de vídeo va en DOS versiones: la diferencia es una única frase (la mano
    acariciando la ropa), así que se derivan de un mismo texto.
    """

    imagen: str
    video_con_manos: str
    video_sin_manos: str


class PrendaInfo(BaseModel):
    producto: str
    clean_photo_id: str | None = None
    titled_photo_id: str | None = None
    # Aviso cuando no se puede distinguir cuál es la foto de la prenda.
    foto_aviso: str = ""
    titulo: str = ""
    titulo_tiktok_completo: str = ""
    tienda: str = ""
    caption: str = ""
    emojis: str = ""
    # Promesa detectada en el caption; vacío si es seguro publicarlo.
    caption_riesgo: str = ""
    uploaded: bool = False
    video_path: str | None = None
    video_listo_at: int = 0
    # Hay un montaje de esta prenda en cola o en curso.
    montando: bool = False


class PrendasListResponse(BaseModel):
    items: list[PrendaInfo] = Field(default_factory=list)
    textos_extraidos: bool = False
    montando: bool = False


class VideoRopaUploadResponse(BaseModel):
    ok: bool = True
    job_id: str | None = None
    message: str = ""
