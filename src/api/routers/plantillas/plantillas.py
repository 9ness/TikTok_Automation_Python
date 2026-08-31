"""Plantillas de mensajes para vendedores (Programa 4 — Tiktok Shop AI Pro).

- GET    /api/v1/plantillas            → las del operador (o las de fábrica)
- POST   /api/v1/plantillas            → guarda la lista entera
- DELETE /api/v1/plantillas            → vuelve a las de fábrica

No hay cola ni coste: son textos. La pantalla los copia al portapapeles.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.dependencies import get_current_user, get_web_user
from src.api.exceptions import APIError
from src.api.schemas.plantillas import PlantillasRequest, PlantillasResponse

router = APIRouter(
    prefix="/api/v1/plantillas",
    tags=["plantillas"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=PlantillasResponse)
def listar(usuario: Annotated[str, Depends(get_web_user)] = "") -> PlantillasResponse:
    """Las plantillas de quien está usando la app."""
    from src.plantillas.repos import plantilla_repo

    doc = plantilla_repo.leer(usuario)
    return PlantillasResponse(ok=True, items=doc["plantillas"], valores=doc["valores"])


@router.post("", response_model=PlantillasResponse)
def guardar(
    body: PlantillasRequest,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> PlantillasResponse:
    """Guarda la lista completa (crear, editar, reordenar y borrar, todo aquí)."""
    from src.plantillas.repos import plantilla_repo

    try:
        doc = plantilla_repo.guardar(
            [p.model_dump() for p in body.items], usuario, body.valores,
        )
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return PlantillasResponse(ok=True, items=doc["plantillas"], valores=doc["valores"])


@router.delete("", response_model=PlantillasResponse)
def restaurar(usuario: Annotated[str, Depends(get_web_user)] = "") -> PlantillasResponse:
    """Descarta los cambios del operador y vuelve a las de fábrica."""
    from src.plantillas.repos import plantilla_repo

    doc = plantilla_repo.restaurar(usuario)
    return PlantillasResponse(ok=True, items=doc["plantillas"], valores=doc["valores"])
