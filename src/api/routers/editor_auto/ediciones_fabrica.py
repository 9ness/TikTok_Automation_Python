"""Ediciones del Editor Auto mandadas «para» un usuario de la fábrica.

Las lee el MCP (`ediciones_editor`) para saber qué vídeos se editaron para ese
usuario y registrarlos en Mis tandas. Ver `src/editor_auto/services/ediciones_fabrica.py`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from src.api import users
from src.api.dependencies import get_current_user, get_queue, get_web_user
from src.api.exceptions import APIError, UserNotFoundError
from src.editor_auto.services import ediciones_fabrica as ef
from src.queue.manager import JobQueue

router = APIRouter(
    prefix="/api/v1/editor-auto/ediciones-fabrica",
    tags=["editor-auto · ediciones para la fábrica"],
    dependencies=[Depends(get_current_user)],
)


def _quien(web_user: str, usuario: str) -> str:
    """Tu propio usuario; otro solo si eres admin."""
    if usuario and usuario != web_user:
        if not users.es_admin(web_user):
            raise APIError("Solo un admin puede ver las ediciones de otro usuario.", status_code=403)
        if usuario not in ef.usuarios_validos():
            raise APIError(f"Usuario de fábrica desconocido: {usuario}", status_code=404)
        return usuario
    if not web_user:
        raise APIError("Sin sesión de usuario.", status_code=401)
    return web_user


@router.get("")
def listar(
    queue: Annotated[JobQueue, Depends(get_queue)],
    web_user: Annotated[str, Depends(get_web_user)] = "",
    usuario: Annotated[str, Query()] = "",
    limite: Annotated[int, Query(ge=1, le=500)] = 50,
) -> dict:
    u = _quien(web_user, usuario)
    return {"usuario": u, "ediciones": ef.listar(u, queue, limite=limite)}


@router.get("/{job_id}/mp4")
def mp4(
    job_id: str,
    queue: Annotated[JobQueue, Depends(get_queue)],
    web_user: Annotated[str, Depends(get_web_user)] = "",
    usuario: Annotated[str, Query()] = "",
) -> FileResponse:
    u = _quien(web_user, usuario)
    ruta = ef.ruta_mp4(u, job_id, queue)
    if not ruta:
        raise UserNotFoundError("Esa edición no existe o aún no está lista.", details={"job_id": job_id})
    return FileResponse(ruta, media_type="video/mp4", filename=f"edicion_{job_id}.mp4")
