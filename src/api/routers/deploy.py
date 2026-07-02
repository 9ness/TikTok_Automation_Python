"""Proxy del panel "Deploy" del frontend → `webhook_listener.py` del host.

El backend de la app corre dentro de un container Docker; pero `systemctl`,
`docker compose` y los logs viven en el HOST. Para no exponer Docker socket
al container (riesgo de privilege escalation), redirigimos las acciones
admin a `webhook_listener.py` que ya corre en el host como `nebulabsai`
con permisos sudo NOPASSWD para los servicios concretos.

Ruta de la llamada:
    Frontend (Settings → Deploy)
        ↓ HTTPS /api/v1/deploy/*  (X-API-Key)
    Caddy → api container
        ↓ HTTP http://host.docker.internal:9000/admin/*  (X-API-Key)
    webhook_listener.py (host)
        ↓ subprocess
    systemctl / docker compose

Endpoints (todos requieren auth `X-API-Key` igual que el resto):
  POST /api/v1/deploy/run               — git pull + deploy_safe.sh
  POST /api/v1/deploy/rebuild           — docker compose up -d --build {svc}
  POST /api/v1/deploy/restart           — docker compose restart {svc}
  GET  /api/v1/deploy/containers        — docker compose ps
  GET  /api/v1/deploy/log?n=200         — tail logs/deploy.log
  GET  /api/v1/deploy/system            — uptime/disk/memory
  GET  /api/v1/deploy/health            — ¿webhook_listener responde?
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from src.api.config import APISettings, get_settings
from src.api.dependencies import get_current_user
from src.api.exceptions import APIError


router = APIRouter(
    prefix="/api/v1/deploy",
    tags=["deploy"],
    dependencies=[Depends(get_current_user)],
)


# `host.docker.internal` resuelve al gateway del host gracias a la entrada
# `extra_hosts: host-gateway` en `docker-compose.yml`. En dev local sin
# Docker, fallback a `127.0.0.1` para que el panel funcione contra un
# webhook_listener corriendo en la misma máquina.
DEFAULT_WEBHOOK_HOSTS = ("host.docker.internal", "127.0.0.1")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "9000"))


def _webhook_base() -> str:
    """Permite override por env (`DEPLOY_WEBHOOK_URL`); si no, usa el
    primer host alcanzable. NO hace probe — confiamos en que el container
    está bien configurado y dejamos que la llamada real falle con un
    mensaje claro si no."""
    override = os.getenv("DEPLOY_WEBHOOK_URL")
    if override:
        return override.rstrip("/")
    return f"http://{DEFAULT_WEBHOOK_HOSTS[0]}:{WEBHOOK_PORT}"


def _call(
    method: str,
    path: str,
    *,
    api_key: str,
    json_body: dict | None = None,
    timeout: float = 30.0,
) -> tuple[int, dict]:
    """Llama al webhook_listener inyectando `X-API-Key`. Devuelve
    `(status_code, parsed_json)`. Si el JSON falla, `parsed_json` es
    `{"raw": <text>}`."""
    url = f"{_webhook_base()}{path}"
    headers = {"X-API-Key": api_key, "Accept": "application/json"}
    data: bytes | None = None
    if json_body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(json_body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            code = resp.getcode() or 200
    except urllib.error.HTTPError as e:
        raw = e.read() or b""
        code = e.code
    except urllib.error.URLError as e:
        raise APIError(
            f"No pude contactar con el webhook_listener del host: {e.reason}. "
            f"¿Está `systemctl status tiktok-webhook` activo en :9000?",
            details={"url": url},
        )
    try:
        body = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        body = {"raw": raw.decode("utf-8", errors="replace")[:500]}
    return code, body


def _api_key_or_raise(settings: APISettings) -> str:
    """Recupera la API_KEY de la app — la usamos también para autenticar
    contra el webhook_listener (comparten secreto). Si la app NO tiene
    api_key set, no podemos llamar al admin del listener."""
    if not settings.api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "El panel Deploy requiere que `API_KEY` esté definida en el "
                "`.env` del server. Sin ella el webhook_listener rechaza las "
                "acciones admin."
            ),
        )
    return settings.api_key


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/status")
def deploy_status(
    settings: Annotated[APISettings, Depends(get_settings)],
) -> dict[str, Any]:
    """Estado inteligente: commits pendientes, qué se rebuildearía, si hay
    deploy en curso. La UI lo consume para decidir habilitar/deshabilitar
    el botón Smart Deploy."""
    key = _api_key_or_raise(settings)
    code, body = _call("GET", "/admin/status", api_key=key, timeout=20)
    if code != 200:
        raise HTTPException(status_code=code, detail=body)
    return body


@router.get("/health")
def deploy_health(
    settings: Annotated[APISettings, Depends(get_settings)],
) -> dict[str, Any]:
    """¿El webhook_listener responde? Útil para que el panel muestre un
    indicador rojo/verde antes de que el usuario haga click en nada."""
    try:
        code, body = _call("GET", "/health", api_key=settings.api_key or "", timeout=4)
    except APIError as e:
        return {"reachable": False, "error": str(e.message)}
    return {"reachable": code == 200, "code": code, "body": body}


@router.get("/system")
def deploy_system(
    settings: Annotated[APISettings, Depends(get_settings)],
) -> dict[str, Any]:
    """Snapshot del host: uptime, disco, memoria, carga."""
    key = _api_key_or_raise(settings)
    code, body = _call("GET", "/admin/system", api_key=key)
    if code != 200:
        raise HTTPException(status_code=code, detail=body)
    return body


@router.get("/containers")
def deploy_containers(
    settings: Annotated[APISettings, Depends(get_settings)],
) -> dict[str, Any]:
    """Estado de los containers vía `docker compose ps`."""
    key = _api_key_or_raise(settings)
    code, body = _call("GET", "/admin/docker/ps", api_key=key)
    if code != 200:
        raise HTTPException(status_code=code, detail=body)
    return body


@router.get("/log")
def deploy_log(
    settings: Annotated[APISettings, Depends(get_settings)],
    n: Annotated[int, Query(ge=1, le=2000)] = 200,
) -> dict[str, Any]:
    """Últimas `n` líneas de `logs/deploy.log`."""
    key = _api_key_or_raise(settings)
    code, body = _call("GET", f"/admin/deploy/log?n={n}", api_key=key)
    if code != 200:
        raise HTTPException(status_code=code, detail=body)
    return body


@router.post("/run")
def deploy_run(
    settings: Annotated[APISettings, Depends(get_settings)],
) -> dict[str, Any]:
    """🚀 Botón "Deploy ahora": ejecuta `git pull + deploy_safe.sh` en el
    host. Responde 202 inmediato; el progreso se ve vía `GET /log`."""
    key = _api_key_or_raise(settings)
    code, body = _call("POST", "/admin/deploy", api_key=key)
    if code >= 400:
        raise HTTPException(status_code=code, detail=body)
    return body


@router.post("/rebuild")
def deploy_rebuild(
    settings: Annotated[APISettings, Depends(get_settings)],
    payload: Annotated[dict, Body()] = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """🐳 Rebuild forzado de containers (sin git pull). Body opcional:
    `{"services": ["api", "web"]}`. Por defecto rebuildea api+web."""
    key = _api_key_or_raise(settings)
    body_payload = payload or {}
    code, body = _call(
        "POST", "/admin/docker/rebuild", api_key=key, json_body=body_payload,
    )
    if code >= 400:
        raise HTTPException(status_code=code, detail=body)
    return body


@router.post("/restart")
def deploy_restart(
    settings: Annotated[APISettings, Depends(get_settings)],
    payload: Annotated[dict, Body(...)],
) -> dict[str, Any]:
    """🔄 Restart de un container concreto sin rebuild. Body:
    `{"service": "api"}`. Permitido: api / web / caddy."""
    key = _api_key_or_raise(settings)
    code, body = _call(
        "POST", "/admin/docker/restart", api_key=key, json_body=payload,
    )
    if code >= 400:
        raise HTTPException(status_code=code, detail=body)
    return body


# ---------------------------------------------------------------------------
# Claude Remote Control (chat web "A la app") — backend Agent SDK fuera de
# Docker (proceso host en :8765). No es un container, así que los endpoints
# docker de arriba no lo tocan: usa estos, que corren `deploy/fix_remote.sh`
# vía el webhook_listener (mismo user que el SDK → sin sudo).
# ---------------------------------------------------------------------------
@router.get("/claude-sdk/status")
def claude_sdk_status(
    settings: Annotated[APISettings, Depends(get_settings)],
) -> dict[str, Any]:
    """Estado del backend Remote Control + sesiones remotas activas."""
    key = _api_key_or_raise(settings)
    code, body = _call("GET", "/admin/claude-sdk/status", api_key=key, timeout=60)
    if code >= 400:
        raise HTTPException(status_code=code, detail=body)
    return body


@router.post("/claude-sdk/free")
def claude_sdk_free(
    settings: Annotated[APISettings, Depends(get_settings)],
) -> dict[str, Any]:
    """🔓 Libera (graceful) los slots remotos colgados sin reiniciar nada.
    Prueba esto primero: suele desbloquear "A la app" al instante."""
    key = _api_key_or_raise(settings)
    code, body = _call("POST", "/admin/claude-sdk/free", api_key=key, timeout=60)
    if code >= 400:
        raise HTTPException(status_code=code, detail=body)
    return body


@router.post("/claude-sdk/restart")
def claude_sdk_restart(
    settings: Annotated[APISettings, Depends(get_settings)],
) -> dict[str, Any]:
    """🔄 Reinicio duro del backend Remote Control (kill + relaunch, o
    systemd si lo gestiona). Úsalo si `free` no basta."""
    key = _api_key_or_raise(settings)
    code, body = _call("POST", "/admin/claude-sdk/restart", api_key=key, timeout=130)
    if code >= 400:
        raise HTTPException(status_code=code, detail=body)
    return body
