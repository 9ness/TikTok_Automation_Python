"""Schemas de las plantillas de mensajes (Programa 4 — Tiktok Shop AI Pro)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Plantilla(BaseModel):
    """Un mensaje listo para copiar y pegar en el chat del vendedor."""

    id: str
    titulo: str = ""
    # Para qué sirve y qué hay que rellenar antes de mandarla. Se ve encima del
    # texto: la plantilla no se explica sola cuando llevas cuatro.
    nota: str = ""
    texto: str = ""


class PlantillasResponse(BaseModel):
    ok: bool = True
    items: list[Plantilla] = Field(default_factory=list)


class PlantillasRequest(BaseModel):
    """La lista ENTERA. La pantalla manda siempre el conjunto, como los
    hashtags: son cuatro textos y así el orden y los borrados van gratis."""

    items: list[Plantilla] = Field(default_factory=list)
