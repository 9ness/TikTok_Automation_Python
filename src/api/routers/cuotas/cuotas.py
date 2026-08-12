"""Topes diarios de publicación (transversal a todos los nichos).

- GET  /api/v1/cuotas/hoy    → lo publicado hoy y sus topes
- POST /api/v1/cuotas/ajuste → fija a mano lo subido fuera de la app

El contador NO es de un nicho: el límite es de la cuenta de TikTok, y da igual
con qué nicho se grabara el vídeo. Se reinicia solo a medianoche (la fecha va
en la clave de Redis), en hora de España.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.dependencies import get_current_user, get_web_user
from src.api.exceptions import APIError
from src.cuotas.repos import cuota_repo

router = APIRouter(
    prefix="/api/v1/cuotas",
    tags=["cuotas"],
    dependencies=[Depends(get_current_user)],
)


class AjusteRequest(BaseModel):
    """Lo subido HOY fuera de la app (o corrección a mano del recuento)."""

    tipo: str
    valor: int


@router.get("/hoy")
def cuota_hoy(usuario: Annotated[str, Depends(get_web_user)] = "") -> dict:
    return cuota_repo.resumen(usuario)


@router.post("/ajuste")
def ajustar(
    body: AjusteRequest,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    try:
        return cuota_repo.ajustar(body.tipo, body.valor, usuario)
    except ValueError as e:
        raise APIError(str(e), status_code=400) from e
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
