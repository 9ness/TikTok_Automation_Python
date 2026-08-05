"""Schemas del Nicho Ropa Con Personas (módulo 7).

Espejo TS en `frontend/lib/types/nichoRopaPersonas.ts`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChicaInfo(BaseModel):
    """Una modelo creada por el usuario.

    `ficha_texto` es el JSON ya formateado: es lo que el operador copia y pega
    en la IA de imagen, así que se guarda hecho y no se reformatea en cada
    lectura (dos lectores darían espaciados distintos del mismo JSON).
    """

    id: str
    nombre: str
    ficha_texto: str
    creada_at: float = 0.0


class ChicasListResponse(BaseModel):
    items: list[ChicaInfo] = Field(default_factory=list)


class RenombrarChicaRequest(BaseModel):
    id: str = Field(..., min_length=1)
    nombre: str = Field(..., min_length=1)


class RopaPersonasPromptsResponse(BaseModel):
    """Los prompts que se copian fuera de la app."""

    movimiento: str
    # Para cuando la IA se niega a vestir a la chica (bikinis, lencería): se
    # aísla la prenda sobre fondo blanco y se usa esa imagen como referencia.
    extraer_prenda: str


# ---------------------------------------------------------------------------
# Prendas
# ---------------------------------------------------------------------------
class CarpetaRopaPersonas(BaseModel):
    slug: str
    label: str


class CarpetasRopaPersonasResponse(BaseModel):
    items: list[CarpetaRopaPersonas] = Field(default_factory=list)


class PrendaPersonasInfo(BaseModel):
    """Una prenda con sus dos fotos, sus textos y su vídeo."""

    producto: str
    clean_photo_id: str | None = None
    titled_photo_id: str | None = None
    foto_aviso: str = ""
    titulo: str = ""
    titulo_tiktok_completo: str = ""
    tienda: str = ""
    caption: str = ""
    # El emoji que acompaña al título quemado en el vídeo.
    emojis: str = ""
    caption_riesgo: str = ""
    uploaded: bool = False
    video_path: str | None = None
    video_listo_at: int = 0
    montando: bool = False


class PrendasPersonasListResponse(BaseModel):
    carpeta: str
    items: list[PrendaPersonasInfo] = Field(default_factory=list)
    textos_extraidos: bool = False
    montando: bool = False


class VideoRopaPersonasUploadResponse(BaseModel):
    job_id: str
    message: str
