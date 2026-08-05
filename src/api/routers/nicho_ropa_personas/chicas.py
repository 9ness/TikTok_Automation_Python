"""Modelos (chicas) del Nicho Ropa Con Personas — módulo 7.

- GET    /api/v1/nicho-ropa-personas/prompts   → movimiento + aislar prenda
- GET    /api/v1/nicho-ropa-personas/chicas    → las del usuario
- POST   /api/v1/nicho-ropa-personas/chicas    → foto + nombre → ficha con Gemini
- PATCH  /api/v1/nicho-ropa-personas/chicas    → renombrar
- DELETE /api/v1/nicho-ropa-personas/chicas    → borrar

Las chicas son POR USUARIO a propósito: la cara es la identidad de la cuenta,
así que la de uno no le aparece a los demás.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from src.api.dependencies import get_current_user, get_web_user
from src.api.exceptions import APIError
from src.api.schemas.nicho_ropa_personas import (
    ChicaInfo,
    ChicasListResponse,
    RenombrarChicaRequest,
    RopaPersonasPromptsResponse,
)

router = APIRouter(
    prefix="/api/v1/nicho-ropa-personas",
    tags=["nicho-ropa-personas"],
    dependencies=[Depends(get_current_user)],
)

# Una foto de referencia de internet no pasa de esto ni de lejos; el tope evita
# que un vídeo colado por error se suba entero a Gemini.
MAX_FOTO_BYTES = 12 * 1024 * 1024


def _a_schema(c: dict) -> ChicaInfo:
    return ChicaInfo(
        id=c.get("id", ""),
        nombre=c.get("nombre", ""),
        ficha_texto=c.get("ficha_texto", ""),
        creada_at=float(c.get("creada_at") or 0),
    )


@router.get("/prompts", response_model=RopaPersonasPromptsResponse)
def get_prompts() -> RopaPersonasPromptsResponse:
    from src.nicho_ropa_personas import config

    return RopaPersonasPromptsResponse(
        movimiento=config.prompt_movimiento(),
        extraer_prenda=config.prompt_extraer_prenda(),
    )


@router.get("/chicas", response_model=ChicasListResponse)
def list_chicas(
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> ChicasListResponse:
    from src.nicho_ropa_personas.repos import chica_repo

    return ChicasListResponse(items=[_a_schema(c) for c in chica_repo.listar(usuario)])


@router.post("/chicas", response_model=ChicasListResponse)
async def crear_chica(
    nombre: Annotated[str, Form()],
    foto: Annotated[UploadFile, File()],
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> ChicasListResponse:
    """Foto de una chica → ficha JSON del curso con ella dentro.

    Gasta UNA llamada a Gemini. La ficha se guarda ya formateada para poder
    copiarla y pegarla tal cual en la IA de imagen.
    """
    from src.nicho_ropa_personas.repos import chica_repo
    from src.nicho_ropa_personas.services import chica_generator

    datos = await foto.read()
    if not datos:
        raise APIError("La foto llegó vacía.", status_code=400)
    if len(datos) > MAX_FOTO_BYTES:
        raise APIError(
            f"La foto pesa {len(datos) / 1e6:.0f} MB; el tope son "
            f"{MAX_FOTO_BYTES // 1024 // 1024} MB.",
            status_code=400,
        )

    try:
        ficha = chica_generator.crear_desde_foto(datos)
    except ValueError as e:
        raise APIError(str(e), status_code=422) from e
    except Exception as e:
        raise APIError(f"Gemini no pudo crear la ficha: {e}", status_code=502) from e

    try:
        chica_repo.guardar(usuario, nombre, ficha)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return ChicasListResponse(items=[_a_schema(c) for c in chica_repo.listar(usuario)])


@router.patch("/chicas", response_model=ChicasListResponse)
def renombrar_chica(
    body: RenombrarChicaRequest,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> ChicasListResponse:
    from src.nicho_ropa_personas.repos import chica_repo

    try:
        if chica_repo.renombrar(usuario, body.id, body.nombre) is None:
            raise APIError("Esa modelo ya no existe.", status_code=404)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return ChicasListResponse(items=[_a_schema(c) for c in chica_repo.listar(usuario)])


@router.delete("/chicas", response_model=ChicasListResponse)
def borrar_chica(
    id: Annotated[str, Query(min_length=1)],
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> ChicasListResponse:
    from src.nicho_ropa_personas.repos import chica_repo

    try:
        if not chica_repo.borrar(usuario, id):
            raise APIError("Esa modelo ya no existe.", status_code=404)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return ChicasListResponse(items=[_a_schema(c) for c in chica_repo.listar(usuario)])
