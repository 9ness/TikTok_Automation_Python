"""El navegador remoto del VPS (Chrome con pantalla virtual) — solo administrador.

Sirve para generar en Flow / Magnific sin tener el PC encendido: se entra desde
una pestaña (móvil o PC) en `/navegador/`, con el MISMO login de la app.

Ruta:
    Ajustes › «Navegador remoto» (botones Encender / Apagar / Abrir)
        ↓ /api/v1/navegador/*  (cookie de admin)
    API (container) ↓ http://host.docker.internal:9000/admin/navegador/*
    webhook_listener (host) → `sudo navegador on|off|json`

    Abrir → Caddy `/navegador/*` → `forward_auth` a `/api/v1/navegador/auth`
    (200 solo si quien mira es admin) → noVNC en el bridge docker (172.18.0.1:6080).
    Nada de esto está abierto a internet sin login.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from src.api.config import APISettings, get_settings
from src.api.dependencies import exigir_admin
from src.api.routers.deploy import _api_key_or_raise, _call

router = APIRouter(prefix="/api/v1/navegador", tags=["navegador"])


@router.get("/auth")
def auth(_: Annotated[str, Depends(exigir_admin)]) -> dict[str, bool]:
    """Puerta de Caddy (`forward_auth`): 200 si es admin, 401 si no."""
    return {"ok": True}


def _accion(settings: APISettings, metodo: str, ruta: str) -> dict[str, Any]:
    key = _api_key_or_raise(settings)
    code, body = _call(metodo, ruta, api_key=key, timeout=90.0)
    if code != 200:
        raise HTTPException(status_code=code, detail=body)
    return body


@router.get("/estado")
def estado(
    _: Annotated[str, Depends(exigir_admin)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> dict[str, Any]:
    return _accion(settings, "GET", "/admin/navegador/estado")


@router.get("/clave")
def clave(
    _: Annotated[str, Depends(exigir_admin)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> dict[str, Any]:
    """La contraseña de la pantalla (noVNC): la segunda puerta tras el login."""
    return _accion(settings, "GET", "/admin/navegador/clave")


@router.post("/encender")
def encender(
    _: Annotated[str, Depends(exigir_admin)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> dict[str, Any]:
    return _accion(settings, "POST", "/admin/navegador/on")


@router.post("/apagar")
def apagar(
    _: Annotated[str, Depends(exigir_admin)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> dict[str, Any]:
    return _accion(settings, "POST", "/admin/navegador/off")
