"""Endpoints del Nicho Creativos Pro (Programa 4 — módulo 13).

Deliberadamente PEQUEÑO. Este nicho comparte con el Nicho POV BOF el catálogo
entero —fuentes, carpetas, fotos, textos, hashtags, escaparate y vendidos— así
que la pantalla usa los endpoints de aquél y aquí solo vive lo que es propio:

- GET  /prompt   → el prompt del creativo + el formato (3:4)
- GET  /folders  → las carpetas con el progreso DE ESTE NICHO
- POST /complete → marcar/desmarcar carpeta hecha
- GET  /subidos  → qué creativos de la carpeta ya se publicaron
- POST /subido   → marcar/desmarcar uno como publicado

Duplicar productos/textos/estado habría significado extraer los textos dos
veces con Gemini y que las dos copias se separaran en cuanto alguien corrigiera
un título.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.api.dependencies import get_current_user, get_web_user
from src.api.exceptions import APIError
from src.nicho_creativos import config

router = APIRouter(
    prefix="/api/v1/nicho-creativos",
    tags=["nicho-creativos"],
    dependencies=[Depends(get_current_user)],
)


class PromptCreativosResponse(BaseModel):
    imagen: str
    formato: str


class CompletarRequest(BaseModel):
    source: str
    folder: str
    completed: bool = True


class SubidoRequest(BaseModel):
    """Marcar a mano que el creativo de ese producto ya está publicado."""

    source: str
    folder: str
    producto: str
    uploaded: bool


@router.get("/prompt", response_model=PromptCreativosResponse)
def get_prompt() -> PromptCreativosResponse:
    """El prompt del creativo y el formato en el que hay que generarlo.

    El formato viaja con el prompt a propósito: el generador no lo deduce del
    texto y copiar el prompt olvidándose del 3:4 es el error fácil aquí.
    """
    try:
        return PromptCreativosResponse(
            imagen=config.prompt_imagen(), formato=config.FORMATO,
        )
    except OSError as e:
        raise APIError(f"No se pudo leer el prompt: {e}", status_code=500) from e


@router.get("/folders")
def list_folders(
    source: Annotated[str, Query()],
    refresh: Annotated[bool, Query()] = False,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Carpetas de la fuente con el progreso de ESTE nicho.

    Las carpetas son las mismas del POV BOF (mismo Drive); lo que cambia es
    cuáles están hechas: un creativo no es un vídeo.
    """
    from src.nicho_creativos.repos import progress_repo
    from src.nicho_pov_bof.services import drive_client

    try:
        carpetas = drive_client.list_product_folders(source, refresh=refresh)
    except ValueError as e:
        raise APIError(str(e), status_code=400) from e
    except RuntimeError as e:
        raise APIError(f"No se pudo leer el Drive: {e}", status_code=502) from e

    try:
        hechas = progress_repo.get_completed(source, usuario)
    except RuntimeError:
        hechas = set()
    nombres = [c.get("name", "") for c in carpetas]
    return {
        "source": source,
        "items": [{"name": n, "completed": n in hechas} for n in nombres],
        "current": next((n for n in nombres if n not in hechas), None),
        "done": len(hechas),
        "total": len(nombres),
    }


@router.post("/complete")
def marcar_completada(
    body: CompletarRequest,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    from src.nicho_creativos.repos import progress_repo

    try:
        if body.completed:
            progress_repo.mark_completed(body.source, body.folder, usuario)
        else:
            progress_repo.unmark_completed(body.source, body.folder, usuario)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return {"ok": True}


@router.get("/subidos")
def list_subidos(
    source: Annotated[str, Query()],
    folder: Annotated[str, Query()],
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Números de producto cuyo creativo ya se publicó.

    Va aparte de la lista de productos (que es la del POV BOF) para no duplicar
    allí un campo que solo entiende este nicho: la pantalla junta las dos cosas.
    """
    from src.nicho_creativos.repos import subidos_repo

    # `items` = números de producto; `horas` = cuándo se marcó cada uno.
    marcados = subidos_repo.subidos(source, folder, usuario)
    return {"items": sorted(marcados), "horas": marcados}


@router.post("/subido")
def marcar_subido(
    body: SubidoRequest,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Lo marca el operador a mano: aquí no hay montaje que termine, el creativo
    se genera fuera. Es PROPIO de este nicho — "subido" en el POV BOF es el
    vídeo, y esto es el creativo."""
    from src.nicho_creativos.repos import subidos_repo

    try:
        subidos_repo.marcar(body.source, body.folder, body.producto, body.uploaded, usuario)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e

    # Un creativo publicado es un CARRUSEL para el tope diario de la cuenta.
    try:
        from src.cuotas.repos import cuota_repo

        cuota_repo.marcar(
            "carruseles",
            f"creativos|{body.source}|{body.folder}|{body.producto}",
            usuario, body.uploaded,
        )
    except Exception:
        pass
    marcados = subidos_repo.subidos(body.source, body.folder, usuario)
    return {"items": sorted(marcados), "horas": marcados}
