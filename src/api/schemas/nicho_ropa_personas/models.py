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
