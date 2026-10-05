"""«Mis tandas»: los vídeos montados del usuario, de todos sus nichos, en
tandas de diez para publicar.

Solo LEE lo de cada nicho y sus botones escriben en el documento original
(ver `src/mis_tandas/`). Para los agentes: aquí no se sube nada; lo que montan
en su nicho aparece solo.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.api.dependencies import get_current_user, get_web_user
from src.api.exceptions import APIError
from src.mis_tandas import servicio

router = APIRouter(
    prefix="/api/v1/mis-tandas",
    tags=["tiktok-shop-ai-pro · mis tandas"],
    dependencies=[Depends(get_current_user)],
)


class EstadoRequest(BaseModel):
    """Un cambio de una fila. Solo se aplica lo que venga."""

    id: str
    uploaded: bool | None = None
    sin_stock: bool | None = None
    rehacer: bool | None = None
    rehacer_nota: str | None = None


def _error(e: Exception) -> APIError:
    if isinstance(e, servicio.ErrorTanda):
        return APIError(str(e), status_code=e.status)
    if isinstance(e, RuntimeError):
        return APIError(str(e), status_code=503)
    return APIError(f"{type(e).__name__}: {e}", status_code=500)


@router.get("")
def get_tandas(
    todas: Annotated[bool, Query()] = False,
    fresco: Annotated[bool, Query()] = False,
    ver_ocultos: Annotated[bool, Query()] = False,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Tandas abiertas con sus vídeos (con `todas`, también las cerradas).
    `fresco` vuelve a leer los nichos en vez de usar lo leído hace segundos.
    `ver_ocultos` añade la lista de lo quitado (para devolverlo)."""
    try:
        return servicio.tandas(usuario, todas=todas, fresco=fresco, ver_ocultos=ver_ocultos)
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e


@router.post("/estado")
def set_estado(
    body: EstadoRequest,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Subido / sin stock / rehacer, escrito en el nicho del vídeo."""
    try:
        return servicio.marcar(
            usuario, body.id, uploaded=body.uploaded, sin_stock=body.sin_stock,
            rehacer=body.rehacer, rehacer_nota=body.rehacer_nota,
        )
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e


class SemaforoRequest(BaseModel):
    """verde / ambar / rojo, o "" para quitarlo."""

    id: str
    color: str = ""
    motivo: str = ""
    por: str = ""


@router.post("/semaforo")
def set_semaforo(
    body: SemaforoRequest,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Semáforo de revisión antes de subir. Rojo marca también «rehacer»."""
    try:
        return servicio.poner_semaforo(usuario, body.id, body.color, body.motivo, body.por)
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e


class CompletarRequest(BaseModel):
    """Los vídeos de la tanda que se da por terminada (todos)."""

    ids: list[str]


@router.post("/completar")
def completar(
    body: CompletarRequest,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """«Tanda completada»: cierra la tanda de esos vídeos (todos los de la
    tanda) y pasa a la siguiente. NO marca nada como subido."""
    try:
        return servicio.completar(usuario, body.ids[:50])
    except servicio.ErrorTanda as e:
        raise _error(e) from e


class OcultarRequest(BaseModel):
    id: str
    oculto: bool = True


@router.post("/ocultar")
def set_oculto(
    body: OcultarRequest,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Quita un vídeo de la lista (ya no se va a subir) o lo devuelve. No toca
    nada del nicho: solo deja de salir aquí y su hueco lo ocupa el siguiente."""
    try:
        return servicio.ocultar(usuario, body.id, body.oculto)
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e


@router.get("/video")
def get_video(
    id: Annotated[str, Query()],
    descargar: Annotated[bool, Query()] = False,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> FileResponse:
    """El vídeo de POV BOF o Largo (los del multimodo, por su nicho)."""
    try:
        path, nombre = servicio.video(usuario, id)
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e
    return FileResponse(str(path), media_type="video/mp4", filename=nombre if descargar else None)


@router.get("/foto")
def get_foto(
    id: Annotated[str, Query()],
    w: Annotated[int, Query(ge=32, le=800)] = 96,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> FileResponse:
    """Miniatura de la foto limpia del producto."""
    try:
        path = servicio.foto(usuario, id, w)
    except Exception as e:  # noqa: BLE001
        raise _error(e) from e
    return FileResponse(
        str(path),
        media_type="image/png" if path.suffix.lower() == ".png" else "image/jpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )
