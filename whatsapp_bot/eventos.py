"""Traduce el JSON de un webhook de WhatsApp Cloud API a eventos sencillos.

Un POST de Meta puede traer varias ``entry`` y varios ``changes``; cada cambio
lleva un ``field``:

- ``messages``            → mensajes del cliente (``value.messages``) y acuses
                            de entrega de lo que mandamos (``value.statuses``).
- ``smb_message_echoes``  → SOLO con coexistencia: lo que Néstor escribe desde
                            la app de WhatsApp Business del móvil
                            (``value.message_echoes``). Es la señal para que
                            el bot se calle en ese chat.
- el resto (``history``, ``smb_app_state_sync``, plantillas…) se ignora.

Aquí no se decide nada: solo se normaliza. Lo que no se entiende se descarta
sin lanzar excepción, porque a Meta hay que contestarle 200 siempre.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator

CAMPO_MENSAJES = "messages"
CAMPO_ECOS = "smb_message_echoes"


@dataclass
class MensajeEntrante:
    """Mensaje que escribe el cliente."""

    wa_id: str  # teléfono del cliente (solo dígitos); si Meta lo omite, su BSUID
    wamid: str
    tipo: str  # text, interactive, button, image, audio, video, document…
    user_id: str = ""  # BSUID de Meta (identificador que no revela el teléfono)
    texto: str = ""  # cuerpo, título del botón o pie de la foto
    boton_id: str = ""  # id del botón o fila de lista pulsada
    nombre: str = ""  # nombre de perfil de WhatsApp
    ts: int = 0
    phone_number_id: str = ""
    crudo: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class EcoNegocio:
    """Mensaje que el negocio manda desde la app del móvil (coexistencia)."""

    wa_id: str  # cliente al que escribe Néstor (teléfono o, si falta, BSUID)
    wamid: str
    tipo: str
    texto: str = ""
    ts: int = 0
    phone_number_id: str = ""
    user_id: str = ""


@dataclass
class EstadoEnvio:
    """Acuse de un mensaje nuestro: sent, delivered, read o failed."""

    wa_id: str
    wamid: str
    estado: str
    ts: int = 0
    error: str = ""


Evento = MensajeEntrante | EcoNegocio | EstadoEnvio


def _entero(valor: Any) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return 0


def _texto_y_boton(msg: dict[str, Any]) -> tuple[str, str]:
    """Saca el texto visible y, si lo hay, el id del botón pulsado."""
    tipo = msg.get("type", "")
    if tipo == "text":
        return str((msg.get("text") or {}).get("body", "")), ""
    if tipo == "interactive":
        inter = msg.get("interactive") or {}
        sub = inter.get(inter.get("type", ""), {}) or {}
        return str(sub.get("title", "")), str(sub.get("id", ""))
    if tipo == "button":  # respuesta rápida de una plantilla
        boton = msg.get("button") or {}
        return str(boton.get("text", "")), str(boton.get("payload", ""))
    if tipo in ("image", "video", "document"):
        return str((msg.get(tipo) or {}).get("caption", "")), ""
    return "", ""


def extraer_eventos(payload: dict[str, Any]) -> Iterator[Evento]:
    """Recorre el webhook y va dando eventos normalizados."""
    if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
        return
    for entry in payload.get("entry") or []:
        for cambio in (entry or {}).get("changes") or []:
            campo = (cambio or {}).get("field", "")
            valor = (cambio or {}).get("value") or {}
            if not isinstance(valor, dict):
                continue
            pnid = str((valor.get("metadata") or {}).get("phone_number_id", ""))

            if campo == CAMPO_MENSAJES:
                nombres: dict[str, str] = {}
                for c in valor.get("contacts") or []:
                    if isinstance(c, dict):
                        nombre = str((c.get("profile") or {}).get("name", ""))
                        for clave in (c.get("wa_id"), c.get("user_id")):
                            if clave:
                                nombres[str(clave)] = nombre
                for msg in valor.get("messages") or []:
                    if not isinstance(msg, dict) or not msg.get("id"):
                        continue
                    # Desde 2026 Meta puede omitir el teléfono y dar solo el BSUID.
                    user_id = str(msg.get("from_user_id") or "")
                    wa_id = str(msg.get("from") or user_id)
                    if not wa_id:
                        continue
                    texto, boton = _texto_y_boton(msg)
                    yield MensajeEntrante(
                        wa_id=wa_id,
                        wamid=str(msg["id"]),
                        user_id=user_id,
                        tipo=str(msg.get("type", "")),
                        texto=texto.strip(),
                        boton_id=boton,
                        nombre=nombres.get(wa_id, ""),
                        ts=_entero(msg.get("timestamp")),
                        phone_number_id=pnid,
                        crudo=msg,
                    )
                for st in valor.get("statuses") or []:
                    if not isinstance(st, dict) or not st.get("id"):
                        continue
                    errores = st.get("errors") or []
                    detalle = ""
                    if errores and isinstance(errores[0], dict):
                        detalle = str(errores[0].get("title") or errores[0].get("message") or "")
                    yield EstadoEnvio(
                        wa_id=str(st.get("recipient_id", "")),
                        wamid=str(st["id"]),
                        estado=str(st.get("status", "")),
                        ts=_entero(st.get("timestamp")),
                        error=detalle,
                    )

            elif campo == CAMPO_ECOS:
                for eco in valor.get("message_echoes") or []:
                    if not isinstance(eco, dict) or not eco.get("id"):
                        continue
                    user_id = str(eco.get("to_user_id") or "")
                    wa_id = str(eco.get("to") or user_id)
                    if not wa_id:
                        continue
                    texto, _ = _texto_y_boton(eco)
                    yield EcoNegocio(
                        wa_id=wa_id,
                        user_id=user_id,
                        wamid=str(eco["id"]),
                        tipo=str(eco.get("type", "")),
                        texto=texto.strip(),
                        ts=_entero(eco.get("timestamp")),
                        phone_number_id=pnid,
                    )
