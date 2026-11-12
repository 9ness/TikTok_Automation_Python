"""Estadísticas de ventas de TikTok Shop (de `ness` y de `nes_bugallo`, cada uno las suyas).

- GET  /api/v1/estadisticas[?usuario=] → el documento guardado (meses, días, productos)
- POST /api/v1/estadisticas[?usuario=] → guarda/fusiona lo leído del panel «Datos»

`ness` (admin) puede pasar `usuario=` para ver o guardar las de las otras
cuentas que lleva él (Ama Shop = `ana`, Casca Chollos = `nestor2`): el
selector de cuenta de su pantalla. Esos usuarios NO entran a la pantalla.

Sin cola ni coste: los datos los lee un agente del móvil y los sube aquí.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Query

from src.api.dependencies import get_current_user, get_web_user
from src.api.exceptions import APIError

router = APIRouter(
    prefix="/api/v1/estadisticas",
    tags=["estadisticas"],
    dependencies=[Depends(get_current_user)],
)

# Quién tiene estadísticas: cada uno ve y guarda las de SU cuenta (Néstor y la
# cuenta árabe de Bugallo, docs/CUENTA_ARABE.md §6).
USUARIOS = {"ness", "nes_bugallo", "nestor2"}
# Cuentas que solo ve un admin con `usuario=` (selector de la pantalla de ness).
OTRAS_CUENTAS = {"ana"}


def _permitido(usuario: str, otro: str = "") -> str:
    from src.api import users

    if usuario not in USUARIOS:
        raise APIError("Tu usuario no tiene estadísticas de ventas.", status_code=403)
    otro = (otro or "").strip().lower()
    if not otro or otro == usuario:
        return usuario
    if not users.es_admin(usuario):
        raise APIError("Solo puedes ver tus propias estadísticas.", status_code=403)
    if otro not in USUARIOS | OTRAS_CUENTAS:
        raise APIError(f"{otro!r} no tiene estadísticas de ventas.", status_code=400)
    return otro


@router.get("")
def leer(
    usuario_param: Annotated[str, Query(alias="usuario")] = "",
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    from src.estadisticas import repo

    return {"ok": True, **repo.leer(_permitido(usuario, usuario_param))}


@router.post("")
def guardar(
    doc: Annotated[dict[str, Any], Body()],
    usuario_param: Annotated[str, Query(alias="usuario")] = "",
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    from src.estadisticas import repo

    fusionar = bool(doc.pop("fusionar", True))
    quien = _permitido(usuario, usuario_param or str(doc.pop("usuario", "") or ""))
    try:
        out = repo.guardar(quien, doc, fusionar=fusionar)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return {"ok": True, **out}
