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
    # Los huecos ya rellenados (`{"CUENTA": "@micuenta"}`). Se guardan con las
    # plantillas: el `@` es del operador y no cambia, y volver a escribirlo en
    # cada visita era el error más tonto de la pantalla.
    valores: dict[str, str] = Field(default_factory=dict)


class PlantillasRequest(BaseModel):
    """La lista ENTERA. La pantalla manda siempre el conjunto, como los
    hashtags: son cuatro textos y así el orden y los borrados van gratis."""

    items: list[Plantilla] = Field(default_factory=list)
    # `None` = no se tocan los que ya había. Así, guardar una edición del texto
    # no borra la cuenta escrita antes (ni al revés).
    valores: dict[str, str] | None = None
