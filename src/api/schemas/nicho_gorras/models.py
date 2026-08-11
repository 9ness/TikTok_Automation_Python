"""Schemas del Nicho Gorras (módulo 11).

Espejo TS en `frontend/lib/types/nichoGorras.ts`. No hay nada de vídeo: este
nicho no edita, solo sirve para encontrar la gorra y copiar sus textos.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GorrasPrompt(BaseModel):
    slug: str
    label: str
    texto: str


class GorrasPromptsResponse(BaseModel):
    items: list[GorrasPrompt] = Field(default_factory=list)


class GorrasCarpeta(BaseModel):
    slug: str
    label: str


class GorrasCarpetasResponse(BaseModel):
    items: list[GorrasCarpeta] = Field(default_factory=list)


class GorraInfo(BaseModel):
    producto: str
    clean_photo_id: str | None = None
    titled_photo_id: str | None = None
    foto_aviso: str = ""
    titulo: str = ""
    titulo_tiktok_completo: str = ""
    tienda: str = ""
    caption: str = ""
    emojis: str = ""
    caption_riesgo: str = ""
    # Escaparate: sale del índice ÚNICO por (tienda|nombre), compartido con
    # los demás nichos — al Marketplace el producto se sube una sola vez.
    en_escaparate: bool = False


class GorrasListResponse(BaseModel):
    carpeta: str
    items: list[GorraInfo] = Field(default_factory=list)
    textos_extraidos: bool = False


class GorraEstadoRequest(BaseModel):
    """Marcar/desmarcar la gorra en el escaparate.

    El escaparate es único por producto (tienda|nombre) y compartido con los
    demás nichos: al Marketplace se sube una sola vez.
    """

    carpeta: str
    producto: str
    en_escaparate: bool
