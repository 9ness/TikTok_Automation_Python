"""Renovar la sesión de Claude Code del VPS desde la web — solo administrador.

La sesión de claude.ai del servidor caduca (≈ cada mes) y entonces Remote Control y el
chat de la app dan «failed to fetch». Desde Accesos › «Sesión de Claude en el VPS»:
«Iniciar sesión» → enlace de claude.com → el operador entra con SU cuenta en SU
navegador → pega el código → el servidor lo teclea en `claude auth login` y reinicia las
sesiones remotas. Nadie más toca la cuenta.

API (container) → webhook_listener (host, `/admin/claude-login/*`) → `claude-login`.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException

from src.api.config import APISettings, get_settings
from src.api.dependencies import exigir_admin
from src.api.routers.deploy import _api_key_or_raise, _call

router = APIRouter(prefix="/api/v1/claude-vps", tags=["claude-vps"])


def _accion(settings: APISettings, metodo: str, ruta: str, cuerpo: dict | None = None) -> dict[str, Any]:
    key = _api_key_or_raise(settings)
    code, body = _call(metodo, ruta, api_key=key, json_body=cuerpo, timeout=120.0)
    if code != 200:
        raise HTTPException(status_code=code, detail=body)
    return body


@router.get("/estado")
def estado(
    _: Annotated[str, Depends(exigir_admin)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> dict[str, Any]:
    return _accion(settings, "GET", "/admin/claude-login/estado")


@router.post("/iniciar")
def iniciar(
    _: Annotated[str, Depends(exigir_admin)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> dict[str, Any]:
    """Lanza `claude auth login` en el VPS y devuelve el enlace para entrar."""
    return _accion(settings, "POST", "/admin/claude-login/iniciar", {})


@router.post("/codigo")
def codigo(
    _: Annotated[str, Depends(exigir_admin)],
    settings: Annotated[APISettings, Depends(get_settings)],
    codigo: Annotated[str, Body(embed=True, max_length=400)],
) -> dict[str, Any]:
    """El código que da claude.com tras iniciar sesión. No se guarda ni se registra."""
    return _accion(settings, "POST", "/admin/claude-login/codigo", {"codigo": codigo})


@router.post("/cancelar")
def cancelar(
    _: Annotated[str, Depends(exigir_admin)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> dict[str, Any]:
    return _accion(settings, "POST", "/admin/claude-login/cancelar", {})
