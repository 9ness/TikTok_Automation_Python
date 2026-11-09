"""Cliente de la API del Editor Auto (vps-trabajo, por Tailscale).

El bot no guarda datos de clientes: pregunta al editor quién es ese teléfono,
cuántos vídeos le quedan hoy y cómo van los que ha mandado.
"""
from __future__ import annotations

from typing import Any

import httpx

from .config import Ajustes

PREFIJO = "/api/v1/editor-auto/whatsapp"


class ErrorEditor(Exception):
    """La API del editor no contesta o contesta con error."""


class ClienteEditor:
    def __init__(self, ajustes: Ajustes, cliente: httpx.Client | None = None) -> None:
        self._aj = ajustes
        self._http = cliente or httpx.Client(timeout=12.0)

    @property
    def configurado(self) -> bool:
        return bool(self._aj.editor_api_url and self._aj.editor_api_key)

    def _pedir(self, metodo: str, ruta: str, **kwargs: Any) -> dict[str, Any]:
        if not self.configurado:
            raise ErrorEditor("falta EDITOR_API_URL o EDITOR_API_KEY")
        try:
            resp = self._http.request(
                metodo,
                f"{self._aj.editor_api_url}{PREFIJO}{ruta}",
                headers={"X-API-Key": self._aj.editor_api_key},
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise ErrorEditor(f"sin conexión con el editor ({type(exc).__name__})") from None
        if resp.status_code >= 400:
            raise ErrorEditor(f"el editor contestó HTTP {resp.status_code}")
        try:
            datos = resp.json()
        except ValueError:
            raise ErrorEditor("el editor no devolvió JSON") from None
        return datos if isinstance(datos, dict) else {}

    def cliente(self, telefono: str) -> dict[str, Any]:
        """Ficha del cliente de ese teléfono: ``{"vinculado": False}`` si no lo conoce."""
        return self._pedir("GET", "/cliente", params={"telefono": telefono})

    def pedir_codigo(self, telefono: str, email: str) -> dict[str, Any]:
        return self._pedir("POST", "/vincular/pedir", json={"telefono": telefono, "email": email})

    def confirmar_codigo(self, telefono: str, codigo: str) -> dict[str, Any]:
        return self._pedir("POST", "/vincular/confirmar", json={"telefono": telefono, "codigo": codigo})

    def desvincular(self, telefono: str) -> dict[str, Any]:
        return self._pedir("POST", "/desvincular", json={"telefono": telefono})

    def apuntar_coste(self, modelo: str, entrada: int, salida: int,
                      cache_lectura: int = 0, cache_escritura: int = 0) -> dict[str, Any]:
        """Deja el gasto de IA en el panel de costes de la fábrica."""
        return self._pedir(
            "POST",
            "/coste",
            json={
                "modelo": modelo,
                "input_tokens": entrada,
                "output_tokens": salida,
                "cache_read_tokens": cache_lectura,
                "cache_write_tokens": cache_escritura,
            },
        )

    def alcanzable(self) -> tuple[bool, str]:
        """Para el diagnóstico: ¿contesta la API del editor?"""
        try:
            self.cliente("0")
        except ErrorEditor as exc:
            return False, str(exc)
        return True, "contesta"
