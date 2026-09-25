"""Llamar a la propia API desde el MCP, como si fuera la web.

El MCP no reimplementa nada: cada herramienta llama a los mismos endpoints que
usa la pantalla, en proceso (`httpx.ASGITransport`, sin red), con la API key y
la cookie firmada del usuario del token. Así los permisos por rol, la cola, el
coste y el progreso POR USUARIO funcionan exactamente igual que en la web, y
si mañana cambia un endpoint el MCP no se queda atrás con una copia vieja.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

try:  # el mensaje de un ToolError sí le llega al modelo; el de otra excepción no
    from mcp.server.mcpserver.exceptions import ToolError as _Base
except ImportError:  # pragma: no cover — sin el paquete mcp
    _Base = Exception


# La app FastAPI a la que llamar. La pone el middleware del MCP con la que
# recibe la petición (`scope["app"]`): en producción es siempre la misma, pero
# los tests crean la suya con dependencias falsas y hay que llamar a ESA.
APP_ACTUAL = None


class ErrorApp(_Base):
    """La API ha contestado con error, o el agente ha pedido algo que no
    existe. El mensaje es el que se le enseña al agente."""


def _cookies(usuario: str) -> dict[str, str]:
    from src.api import session

    key, name, _ = session._cookie_config()
    if not key:
        # Modo dev: no hay con qué firmar, la suplantación va en claro.
        return {session._nombre_cookie_suplantacion(name): usuario}
    return {name: session._sign({"u": usuario, "exp": int(time.time()) + 3600}, key)}


def _headers() -> dict[str, str]:
    from src.api.config import get_settings

    key = get_settings().api_key
    return {"X-API-Key": key} if key else {}


def _mensaje(r: httpx.Response) -> str:
    try:
        datos = r.json()
    except ValueError:
        return f"HTTP {r.status_code}: {r.text[:300]}"
    if isinstance(datos, dict):
        msg = datos.get("error") or datos.get("detail") or datos.get("message")
        if msg:
            return f"HTTP {r.status_code}: {msg}"
    return f"HTTP {r.status_code}: {str(datos)[:300]}"


class Interno:
    def __init__(self, usuario: str) -> None:
        self.usuario = usuario

    def _cliente(self) -> httpx.AsyncClient:
        app = APP_ACTUAL
        if app is None:
            from src.api.main import app

        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://interno",
            headers=_headers(),
            cookies=_cookies(self.usuario),
            timeout=httpx.Timeout(900.0),
        )

    async def _pedir(self, metodo: str, ruta: str, **kw: Any) -> httpx.Response:
        params = kw.pop("params", None)
        if params:
            kw["params"] = {k: v for k, v in params.items() if v not in (None, "")}
        async with self._cliente() as c:
            r = await c.request(metodo, ruta, **kw)
        if r.status_code >= 400:
            raise ErrorApp(_mensaje(r))
        return r

    async def get(self, ruta: str, **params: Any) -> Any:
        return (await self._pedir("GET", ruta, params=params)).json()

    async def get_bytes(self, ruta: str, **params: Any) -> tuple[bytes, str, str]:
        """(contenido, content-type, nombre de fichero sugerido)."""
        r = await self._pedir("GET", ruta, params=params)
        nombre = ""
        disp = r.headers.get("content-disposition", "")
        if "filename=" in disp:
            nombre = disp.split("filename=", 1)[1].strip().strip('"')
        return r.content, r.headers.get("content-type", ""), nombre

    async def post(self, ruta: str, body: dict | None = None, **params: Any) -> Any:
        r = await self._pedir("POST", ruta, json=body or {}, params=params)
        return r.json() if r.content else {}

    async def post_form(
        self, ruta: str, datos: dict[str, Any], fichero: tuple[str, bytes, str],
    ) -> Any:
        form = {k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in datos.items()}
        r = await self._pedir("POST", ruta, data=form, files={"file": fichero})
        return r.json() if r.content else {}
