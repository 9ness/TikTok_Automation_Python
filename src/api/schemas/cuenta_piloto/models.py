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
    # Escaparate: sale del índice ÚNICO por (tienda|nombre), compartido con
    # los demás nichos — al Marketplace el producto se sube una sola vez.
    en_escaparate: bool = False
    tiene_ficha: bool = False
    videos: list[VideoPiloto] = Field(default_factory=list)
    # Última tanda enviada a editar: cuántos vídeos eran y cuántos van ya. El
    # operador manda 9 de golpe y lo que quiere ver es "7 de 9", no la lista
    # entera de vídeos que lleva el producto desde siempre.
    lote_total: int = 0
    lote_listos: int = 0
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


class EstadoPilotoRequest(BaseModel):
    """Marcar/desmarcar el producto en el escaparate.

    El escaparate es único por producto (tienda|nombre) y compartido con los
    demás nichos: al Marketplace se sube una sola vez.

    El campo se llama `producto` y no `id` aunque en `ProductoPiloto` el
    identificador sea `id`: es el nombre que ya usan el resto de endpoints de
    este nicho (`TextosPilotoRequest`, los query params) y el que manda el
    modal del escaparate, común a todos los nichos.
    """

    producto: str
    en_escaparate: bool
