"""Schemas de la Cuenta Piloto (Programa 4 — Tiktok Shop AI Pro)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class VideoPiloto(BaseModel):
    """Un montaje del producto. Hay VARIOS por producto, a propósito."""

    n: int = Field(..., description="Posición en la lista, 1 = el primero montado")
    sexo: str = ""
    job_id: str = ""
    at: int = 0


class ProductoPiloto(BaseModel):
    id: str
    titulo: str = ""
    titulo_tiktok_completo: str = ""
    tienda: str = ""
    caption: str = ""
    emojis: str = ""
    gancho: str = ""
    cta: str = ""
    caption_riesgo: str = ""
    tiene_ficha: bool = False
    videos: list[VideoPiloto] = Field(default_factory=list)
    creado_at: float = 0
    textos_at: str = ""
    montando: bool = False


class ProductosPilotoResponse(BaseModel):
    items: list[ProductoPiloto] = Field(default_factory=list)


class ProductoPilotoResponse(BaseModel):
    producto: ProductoPiloto


class TextosPilotoRequest(BaseModel):
    """Corrección a mano de lo que leyó Gemini."""

    producto: str
    titulo: str | None = None
    tienda: str | None = None
    caption: str | None = None
    emojis: str | None = None


class VideoPilotoUploadResponse(BaseModel):
    job_id: str
    message: str
