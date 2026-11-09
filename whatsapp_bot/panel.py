"""Avisos a Néstor por el panel de mando (panel.nebulabsmedia.com)."""
from __future__ import annotations

import logging

import httpx

from .config import Ajustes

log = logging.getLogger("whatsapp_bot.panel")


class Panel:
    def __init__(self, ajustes: Ajustes, cliente: httpx.Client | None = None) -> None:
        self._aj = ajustes
        self._http = cliente or httpx.Client(timeout=10.0)

    @property
    def configurado(self) -> bool:
        return bool(self._aj.panel_url and self._aj.panel_token)

    def avisar(self, texto: str, *, notificar: bool = False, nivel: str = "aviso") -> bool:
        """Deja un aviso; con ``notificar`` suena en el móvil. Nunca lanza."""
        if not self.configurado:
            log.warning("aviso sin enviar (panel sin configurar): %s", texto)
            return False
        try:
            resp = self._http.post(
                f"{self._aj.panel_url}/api/avisos",
                headers={"Authorization": f"Bearer {self._aj.panel_token}"},
                json={
                    "texto": texto,
                    "nivel": nivel,
                    "notificar": notificar,
                    "cuenta": "Editor Auto",
                    "tipo": "whatsapp",
                },
            )
        except httpx.HTTPError as exc:
            log.warning("aviso sin enviar (%s): %s", type(exc).__name__, texto)
            return False
        if resp.status_code >= 400:
            log.warning("el panel contestó HTTP %s al aviso", resp.status_code)
            return False
        return True
