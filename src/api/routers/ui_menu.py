"""Cómo quiere cada persona SU menú lateral: qué esconde y en qué orden.

No es un ajuste de un programa: la sidebar los cruza todos, así que vive
aquí y no dentro de `src/<programa>/`. Guarda lo MÍNIMO — lo oculto y el
orden—, nunca el menú entero: los items los define el frontend y una copia
guardada aquí se quedaría vieja en cuanto se añada un nicho.

Va en Redis y no en `localStorage` porque la app se usa desde el móvil, el
PC y la APK con la misma cuenta: configurarlo tres veces es justo lo que se
quería evitar.

Endpoints:
  GET /api/v1/ui/menu   → preferencias del usuario del cookie
  PUT /api/v1/ui/menu   → las guarda (reemplaza, no fusiona)
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.api.dependencies import get_current_user, get_web_user
from src.viralizacion.repos.redis_base import get_viralizacion_redis


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/ui/menu",
    tags=["ui · menú"],
    dependencies=[Depends(get_current_user)],
)

# Sin sesión (modo dev sin cookie) todo el mundo es el mismo: es una
# preferencia cosmética, no un permiso.
_ANONIMO = "ness"


class MenuPrefs(BaseModel):
    """Claves de menú, tal y como las manda el frontend.

    La clave de un item es su `href` y la de un grupo su `basePath`. Se
    guardan como strings sueltas a propósito: si mañana desaparece una
    pantalla, su clave sobra en la lista y no rompe nada.
    """

    # Escondidos: items y/o grupos enteros.
    ocultos: list[str] = Field(default_factory=list)
    # Orden del primer nivel (grupos y enlaces sueltos). Lo que no esté
    # nombrado se queda detrás, en el orden de siempre.
    orden_grupos: list[str] = Field(default_factory=list)
    # Orden dentro de cada grupo: `basePath` → hrefs.
    orden_items: dict[str, list[str]] = Field(default_factory=dict)


def _key(usuario: str) -> str:
    return f"ui:menu:{usuario or _ANONIMO}"


@router.get("", response_model=MenuPrefs)
def get_menu(usuario: Annotated[str, Depends(get_web_user)]) -> MenuPrefs:
    r = get_viralizacion_redis()
    if not r.is_available():
        return MenuPrefs()
    try:
        datos = r.get_json(_key(usuario))
        return MenuPrefs(**(datos or {}))
    except Exception as e:  # noqa: BLE001
        # Ni un fallo de Redis ni un documento corrupto pueden dejar sin menú:
        # se cae al de siempre, que es el completo.
        logger.warning("[ui_menu] no se pudieron leer las de %s: %s", usuario, e)
        return MenuPrefs()


@router.put("", response_model=MenuPrefs)
def put_menu(
    body: MenuPrefs,
    usuario: Annotated[str, Depends(get_web_user)],
) -> MenuPrefs:
    r = get_viralizacion_redis()
    if r.is_available():
        r.set_json(_key(usuario), body.model_dump())
    return body
