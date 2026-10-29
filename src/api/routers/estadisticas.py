"""Estadísticas de ventas de TikTok Shop (de `ness` y de `nes_bugallo`, cada uno las suyas).

- GET  /api/v1/estadisticas → el documento guardado (meses, días, productos)
- POST /api/v1/estadisticas → guarda/fusiona lo leído del panel «Datos»

Sin cola ni coste: los datos los lee un agente del móvil y los sube aquí.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends

from src.api.dependencies import get_current_user, get_web_user
from src.api.exceptions import APIError

router = APIRouter(
    prefix="/api/v1/estadisticas",
    tags=["estadisticas"],
    dependencies=[Depends(get_current_user)],
)

# Quién tiene estadísticas: cada uno ve y guarda las de SU cuenta (Néstor y la
# cuenta árabe de Bugallo, docs/CUENTA_ARABE.md §6).
USUARIOS = {"ness", "nes_bugallo"}


def _permitido(usuario: str) -> str:
    if usuario not in USUARIOS:
        raise APIError("Tu usuario no tiene estadísticas de ventas.", status_code=403)
    return usuario


@router.get("")
def leer(usuario: Annotated[str, Depends(get_web_user)] = "") -> dict:
    from src.estadisticas import repo

    return {"ok": True, **repo.leer(_permitido(usuario))}


@router.post("")
def guardar(
    doc: Annotated[dict[str, Any], Body()],
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    from src.estadisticas import repo

    fusionar = bool(doc.pop("fusionar", True))
    try:
        out = repo.guardar(_permitido(usuario), doc, fusionar=fusionar)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return {"ok": True, **out}
