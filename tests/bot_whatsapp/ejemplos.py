"""Webhooks de ejemplo con la forma que documenta Meta (Cloud API).

Los teléfonos y los ids son inventados. Se usan para simular el webhook en
los tests sin tocar la red.
"""
from __future__ import annotations

from typing import Any

WABA_ID = "102290129340398"
PHONE_NUMBER_ID = "106540352242922"
NUMERO_NEGOCIO = "34600111222"
CLIENTE = "34611222333"


def _sobre(campo: str, valor: dict[str, Any]) -> dict[str, Any]:
    valor = {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": NUMERO_NEGOCIO, "phone_number_id": PHONE_NUMBER_ID},
        **valor,
    }
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": WABA_ID, "changes": [{"value": valor, "field": campo}]}],
    }


def texto(cuerpo: str, wa_id: str = CLIENTE, wamid: str = "wamid.TEXTO1", ts: int = 1794262300,
          nombre: str = "Lucía") -> dict[str, Any]:
    """Mensaje de texto entrante."""
    return _sobre(
        "messages",
        {
            "contacts": [{"profile": {"name": nombre}, "wa_id": wa_id}],
            "messages": [
                {"from": wa_id, "id": wamid, "timestamp": str(ts), "type": "text",
                 "text": {"body": cuerpo}}
            ],
        },
    )


def boton(boton_id: str, titulo: str, wa_id: str = CLIENTE, wamid: str = "wamid.BOTON1",
          ts: int = 1794262310) -> dict[str, Any]:
    """El cliente pulsa un botón de respuesta de un mensaje interactivo."""
    return _sobre(
        "messages",
        {
            "contacts": [{"profile": {"name": "Lucía"}, "wa_id": wa_id}],
            "messages": [
                {
                    "context": {"from": NUMERO_NEGOCIO, "id": "wamid.MENU"},
                    "from": wa_id,
                    "id": wamid,
                    "timestamp": str(ts),
                    "type": "interactive",
                    "interactive": {"type": "button_reply",
                                    "button_reply": {"id": boton_id, "title": titulo}},
                }
            ],
        },
    )


def audio(wa_id: str = CLIENTE, wamid: str = "wamid.AUDIO1", ts: int = 1794262320) -> dict[str, Any]:
    """Nota de voz: el bot no la entiende."""
    return _sobre(
        "messages",
        {
            "contacts": [{"profile": {"name": "Lucía"}, "wa_id": wa_id}],
            "messages": [
                {"from": wa_id, "id": wamid, "timestamp": str(ts), "type": "audio",
                 "audio": {"mime_type": "audio/ogg; codecs=opus", "sha256": "x", "id": "999",
                           "voice": True}}
            ],
        },
    )


def estado(wamid: str, valor: str = "delivered", wa_id: str = CLIENTE,
           ts: int = 1794262330) -> dict[str, Any]:
    """Acuse de entrega de un mensaje nuestro."""
    return _sobre(
        "messages",
        {"statuses": [{"id": wamid, "status": valor, "timestamp": str(ts), "recipient_id": wa_id}]},
    )


def eco(cuerpo: str, wa_id: str = CLIENTE, wamid: str = "wamid.ECO1", ts: int = 1794262340) -> dict[str, Any]:
    """Coexistencia: Néstor contesta desde la app de WhatsApp Business."""
    return _sobre(
        "smb_message_echoes",
        {
            "message_echoes": [
                {"from": NUMERO_NEGOCIO, "to": wa_id, "id": wamid, "timestamp": str(ts),
                 "type": "text", "text": {"body": cuerpo}}
            ]
        },
    )
