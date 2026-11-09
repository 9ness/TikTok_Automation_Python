"""Avisos del box al bot de WhatsApp (otro servidor). Nunca lanza.

Apagado salvo `EDITOR_WHATSAPP_AVISOS=1` y con `EDITOR_WHATSAPP_BOT_URL` +
`EDITOR_WHATSAPP_BOT_TOKEN` definidas.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("editor_auto.whatsapp_notify")


def _config() -> tuple[str, str]:
    return (
        (os.getenv("EDITOR_WHATSAPP_BOT_URL") or "").strip().rstrip("/"),
        (os.getenv("EDITOR_WHATSAPP_BOT_TOKEN") or "").strip(),
    )


def avisar_bot(evento: str, datos: dict) -> bool:
    """POST {BOT_URL}/interno/aviso con {"evento": ..., **datos}. True si el bot
    respondio 2xx."""
    try:
        if os.getenv("EDITOR_WHATSAPP_AVISOS") != "1":
            return False
        url, token = _config()
        if not url or not token:
            return False
        import httpx
        r = httpx.post(
            f"{url}/interno/aviso",
            headers={"Authorization": f"Bearer {token}"},
            json={"evento": evento, **(datos or {})},
            timeout=5.0,
        )
        return 200 <= r.status_code < 300
    except Exception as e:
        logger.warning("[wa] aviso al bot fallido: %s", type(e).__name__)
        return False


def avisar_videos_listos(
    *, email: str, nombre: str, dia: str, listos: int, caduca: str | None = None,
) -> bool:
    """Avisa de 'videos listos' si la cuenta tiene telefono vinculado."""
    try:
        if os.getenv("EDITOR_WHATSAPP_AVISOS") != "1":
            return False
        url, token = _config()
        if not url or not token:
            return False
        from src.editor_auto.services.whatsapp_vinculo import telefono_de
        tel = telefono_de(email)
        if not tel:
            return False
        return avisar_bot("videos_listos", {
            "telefono": tel, "nombre": nombre, "dia": dia,
            "listos": int(listos), "caduca": caduca,
        })
    except Exception:
        return False
