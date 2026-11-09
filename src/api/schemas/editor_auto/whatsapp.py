"""Schemas del puente con el bot de WhatsApp (Editor Auto)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class VincularPedirRequest(BaseModel):
    telefono: str = Field(..., min_length=1, max_length=40)
    email: str = Field(..., min_length=1, max_length=200)


class VincularConfirmarRequest(BaseModel):
    telefono: str = Field(..., min_length=1, max_length=40)
    codigo: str = Field(..., min_length=1, max_length=20)


class DesvincularRequest(BaseModel):
    telefono: str = Field(..., min_length=1, max_length=40)


class CosteRequest(BaseModel):
    modelo: str = Field(..., min_length=1, max_length=80)
    input_tokens: int = Field(0, ge=0)
    output_tokens: int = Field(0, ge=0)
    cache_read_tokens: int = Field(0, ge=0)
    cache_write_tokens: int = Field(0, ge=0)
