"""Subidas: vídeos y carruseles publicados cada día, con el total del mes.

- GET  /api/v1/subidas?mes=YYYY-MM[&usuario=] → días del mes + totales
- POST /api/v1/subidas → apunta un día (`modo` sumar | fijar)

Lo rellenan los agentes con el MCP (`registrar_subidas`) al terminar cada
tanda de subida; la pantalla `/subidas` solo lo lee. Cada uno ve y escribe
lo suyo; `ness` (admin) puede pasar `usuario=` para el de otro permitido.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, Field

from src.api.dependencies import get_current_user, get_web_user
from src.api.exceptions import APIError

router = APIRouter(
    prefix="/api/v1/subidas",
    tags=["subidas"],
    dependencies=[Depends(get_current_user)],
)

# Quién tiene contador de subidas: la cuenta árabe de Bugallo y Néstor.
USUARIOS = {"nes_bugallo", "ness"}


def _de_quien(usuario: str, otro: str) -> str:
    """El contador que toca: el propio, o el de `otro` si quien pide es admin."""
    from src.api import users

    if usuario not in USUARIOS:
        raise APIError("Tu usuario no tiene contador de subidas.", status_code=403)
    otro = (otro or "").strip().lower()
    if not otro or otro == usuario:
        return usuario
    if not users.es_admin(usuario):
        raise APIError("Solo puedes ver tus propias subidas.", status_code=403)
    if otro not in USUARIOS:
        raise APIError(f"{otro!r} no tiene contador de subidas.", status_code=400)
    return otro


class RegistroSubidas(BaseModel):
    fecha: str = ""
    videos: int = Field(0, ge=0)
    carruseles: int = Field(0, ge=0)
    nota: str = ""
    modo: str = "sumar"
    usuario: str = ""


@router.get("")
def leer(
    mes: Annotated[str, Query()] = "",
    usuario_param: Annotated[str, Query(alias="usuario")] = "",
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    from src.subidas import repo

    quien = _de_quien(usuario, usuario_param)
    try:
        return {"ok": True, **repo.leer_mes(quien, mes)}
    except ValueError as e:
        raise APIError(str(e), status_code=400) from e


@router.post("")
def registrar(
    body: Annotated[RegistroSubidas, Body()],
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    from src.subidas import repo

    quien = _de_quien(usuario, body.usuario)
    try:
        out = repo.registrar(quien, fecha=body.fecha, videos=body.videos,
                             carruseles=body.carruseles, nota=body.nota, modo=body.modo)
    except ValueError as e:
        raise APIError(str(e), status_code=400) from e
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return {"ok": True, **out}
