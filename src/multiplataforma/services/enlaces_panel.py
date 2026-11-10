"""Enlaces de la página de la bio (`/links/<cuenta>`) por el redirector del panel.

El panel (`panel.nebulabsmedia.com/r/<cuenta>/<enlace>?d=links`) cuenta cada clic
(bots aparte) y manda al destino con un 302; los clics salen en Cuentas › Tráfico.
Cada producto se registra en el panel la primera vez que sale en la página
(`POST /api/redirecciones`, idempotente) y se recuerda en memoria. Si el panel
no está configurado o falla, el producto lleva su enlace directo (nunca un
enlace roto). Amazon va directo salvo `MULTIPLATAFORMA_ENLACE_CORTO_AMAZON=1`:
sus normas piden que el enlace muestre que va a Amazon.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import urllib.request

from src.multiplataforma import config

log = logging.getLogger(__name__)

BASE_PUBLICA = "https://panel.nebulabsmedia.com/r/"
ORIGEN = "links"
_TROZO = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}")
_registrados: dict[tuple[str, str], str] = {}
_cerrojo = threading.Lock()


def _registrar(cuenta: str, enlace: str, url: str, titulo: str) -> None:
    req = urllib.request.Request(
        os.getenv("PANEL_URL", "").rstrip("/") + "/api/redirecciones", method="POST",
        data=json.dumps({"cuenta": cuenta, "enlace": enlace, "url": url, "titulo": titulo[:100]}).encode(),
        headers={"Authorization": f"Bearer {os.getenv('PANEL_TOKEN', '')}", "X-Agente": "Links bio",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        r.read()


def contado(cuenta: str, enlace: str, url: str, titulo: str = "", amazon: bool = False) -> str:
    """La URL que cuenta clics para ese producto, o `url` tal cual si no se puede."""
    if not (os.getenv("PANEL_URL") and os.getenv("PANEL_TOKEN")):
        return url
    if amazon and not config.enlace_corto_amazon():
        return url
    cuenta, enlace = (cuenta or "").lower(), (enlace or "").lower()
    if not (_TROZO.fullmatch(cuenta) and _TROZO.fullmatch(enlace)) or not re.fullmatch(r"https?://\S+", url or ""):
        return url
    clave = (cuenta, enlace)
    with _cerrojo:
        hecho = _registrados.get(clave) == url
    if not hecho:
        try:
            _registrar(cuenta, enlace, url, titulo)
        except Exception as e:  # noqa: BLE001 — sin panel, enlace directo
            log.warning("links: no se pudo registrar %s/%s en el panel: %s", cuenta, enlace, e)
            return url
        with _cerrojo:
            _registrados[clave] = url
    return f"{BASE_PUBLICA}{cuenta}/{enlace}?d={ORIGEN}"
