"""Claves API de los proyectos del VPS (Accesos › «Claves API») — solo administrador.

La versión web de `~/.local/bin/clave`. El contenedor NO monta `~/proyectos`:
    Accesos › «Claves API»
        ↓ /api/v1/claves  (cookie de admin)
    API (container) ↓ http://host.docker.internal:9000/admin/claves  (X-API-Key)
    webhook_listener (host) → `deploy/claves_proyectos.py`
El valor de la clave solo pasa de ida; ninguna respuesta ni log lo contiene
(el listado da nombre + últimos 4).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from starlette.concurrency import run_in_threadpool

from src.api.config import APISettings, get_settings
from src.api.dependencies import exigir_admin
from src.api.routers.deploy import _api_key_or_raise, _call

router = APIRouter(prefix="/api/v1/claves", tags=["claves"])


def _host(settings: APISettings, metodo: str, cuerpo: dict | None = None) -> dict[str, Any]:
    key = _api_key_or_raise(settings)
    code, body = _call(metodo, "/admin/claves", api_key=key, json_body=cuerpo, timeout=60.0)
    if code != 200:
        raise HTTPException(status_code=code, detail=body.get("error") or "Error del servidor")
    return body


@router.get("")
def listar(
    _: Annotated[str, Depends(exigir_admin)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> dict[str, Any]:
    return _host(settings, "GET")


@router.post("")
async def guardar(
    request: Request,
    _: Annotated[str, Depends(exigir_admin)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> dict[str, Any]:
    # Sin modelo Pydantic a propósito: un 422 de FastAPI devuelve el `input`
    # recibido, y ahí iría la clave. Se valida a mano y el error no la cita.
    try:
        cuerpo = await request.json()
    except ValueError:
        cuerpo = None
    if not isinstance(cuerpo, dict) or not all(
        isinstance(cuerpo.get(k), str) and cuerpo.get(k) for k in ("proyecto", "variable", "valor")
    ):
        raise HTTPException(status_code=400, detail="Faltan proyecto, variable o clave")
    datos = {k: cuerpo[k] for k in ("proyecto", "variable", "valor")}
    return await run_in_threadpool(_host, settings, "POST", datos)
