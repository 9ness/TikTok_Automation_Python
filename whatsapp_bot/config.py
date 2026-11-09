"""Ajustes del bot: todo llega por variables de entorno (`.env` + `clave`).

Ninguna clave va en el código. ``Ajustes.desde_entorno()`` se llama al
arrancar; los tests construyen ``Ajustes(...)`` a mano.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Modelo de IA para lo que no cubren los menús. UNA constante: al salir otro
# modelo se cambia aquí y en ningún sitio más.
MODELO_IA = "claude-haiku-5-5"

GRAPH_BASE = "https://graph.facebook.com"
GRAPH_VERSION = "v27.0"  # la de los ejemplos de la doc de Meta (nov 2026)

# Variables que hacen falta para hablar con Meta. La página «Conectar
# WhatsApp» enseña cuáles faltan (solo el nombre, nunca el valor).
CLAVES_META = (
    "WHATSAPP_VERIFY_TOKEN",
    "WHATSAPP_APP_SECRET",
    "WHATSAPP_ACCESS_TOKEN",
    "WHATSAPP_PHONE_NUMBER_ID",
    "WHATSAPP_WABA_ID",
)

# Con 360dialog (proveedor oficial; única vía sencilla para seguir usando la
# app del móvil) solo hace falta la clave del canal. El secreto del webhook lo
# genera el despliegue: 360dialog no firma, así que nos lo reenvía en una
# cabecera que le decimos nosotros.
D360_BASE = "https://waba-v2.360dialog.io"
CABECERA_SECRETO = "X-Webhook-Secreto"
CLAVES_360 = ("D360_API_KEY", "WHATSAPP_WEBHOOK_SECRETO")
PROVEEDORES = ("meta", "360dialog")


def _entero(nombre: str, defecto: int) -> int:
    try:
        return int(os.environ.get(nombre, "").strip() or defecto)
    except ValueError:
        return defecto


@dataclass
class Ajustes:
    proveedor: str = "meta"  # meta | 360dialog

    # 360dialog
    d360_api_key: str = ""
    d360_base: str = D360_BASE
    webhook_secreto: str = ""

    # Meta / WhatsApp Cloud API
    verify_token: str = ""
    app_secret: str = ""
    access_token: str = ""
    phone_number_id: str = ""
    waba_id: str = ""
    graph_version: str = GRAPH_VERSION
    graph_base: str = GRAPH_BASE

    # API del Editor Auto (vps-trabajo, por Tailscale)
    editor_api_url: str = ""
    editor_api_key: str = ""
    web_publica: str = "https://nebulabsmedia.com"

    # IA (Haiku) para preguntas libres
    anthropic_api_key: str = ""
    ia_max_dia_por_chat: int = 15

    # Panel de mando (avisos a Néstor)
    panel_url: str = ""
    panel_token: str = ""

    # Comportamiento
    horario: str = "1234567=09:00-22:00"
    silencio_tras_nestor_min: int = 120  # Néstor contesta desde el móvil → el bot calla
    pausa_humano_min: int = 720  # el cliente pide hablar con Néstor
    nombre_negocio: str = "Nebulabs Media"
    tope_mes: int = 950  # Meta regala 1.000 mensajes de servicio al mes: frenar antes
    enlace_pago: str = ""  # p. ej. un enlace de PayPal; vacío = lo pasa Néstor
    datos_pago: str = ""  # texto libre (Bizum, IBAN…); vacío = lo pasa Néstor
    plantillas_de_pago: bool = False  # avisar con plantilla (cuesta) fuera de las 24 h

    # Servicio
    url_publica: str = ""  # https://… donde Caddy publica este servicio
    admin_token: str = ""  # lo usa el panel del Editor para /admin/*
    interno_token: str = ""  # lo usa la API del editor para /interno/aviso
    db_path: str = "datos/whatsapp.db"
    faltan: list[str] = field(default_factory=list)

    @classmethod
    def desde_entorno(cls) -> "Ajustes":
        e = os.environ.get
        base = Path(__file__).resolve().parent
        proveedor = e("WHATSAPP_PROVEEDOR", "").strip().lower() or "meta"
        if proveedor not in PROVEEDORES:
            proveedor = "meta"
        ajustes = cls(
            proveedor=proveedor,
            d360_api_key=e("D360_API_KEY", "").strip(),
            d360_base=(e("D360_BASE", "").strip() or D360_BASE).rstrip("/"),
            webhook_secreto=e("WHATSAPP_WEBHOOK_SECRETO", "").strip(),
            verify_token=e("WHATSAPP_VERIFY_TOKEN", "").strip(),
            app_secret=e("WHATSAPP_APP_SECRET", "").strip(),
            access_token=e("WHATSAPP_ACCESS_TOKEN", "").strip(),
            phone_number_id=e("WHATSAPP_PHONE_NUMBER_ID", "").strip(),
            waba_id=e("WHATSAPP_WABA_ID", "").strip(),
            graph_version=e("WHATSAPP_GRAPH_VERSION", "").strip() or GRAPH_VERSION,
            editor_api_url=e("EDITOR_API_URL", "").strip().rstrip("/"),
            editor_api_key=e("EDITOR_API_KEY", "").strip(),
            web_publica=(e("WHATSAPP_WEB_PUBLICA", "").strip() or "https://nebulabsmedia.com").rstrip("/"),
            anthropic_api_key=e("ANTHROPIC_API_KEY", "").strip(),
            ia_max_dia_por_chat=_entero("WHATSAPP_IA_MAX_DIA", 15),
            panel_url=e("PANEL_URL", "").strip().rstrip("/"),
            panel_token=e("PANEL_TOKEN", "").strip(),
            horario=e("WHATSAPP_HORARIO", "").strip() or "1234567=09:00-22:00",
            silencio_tras_nestor_min=_entero("WHATSAPP_SILENCIO_MIN", 120),
            pausa_humano_min=_entero("WHATSAPP_PAUSA_HUMANO_MIN", 720),
            nombre_negocio=e("WHATSAPP_NOMBRE_NEGOCIO", "").strip() or "Nebulabs Media",
            tope_mes=_entero("WHATSAPP_TOPE_MES", 950),
            enlace_pago=e("WHATSAPP_ENLACE_PAGO", "").strip(),
            datos_pago=e("WHATSAPP_DATOS_PAGO", "").strip(),
            plantillas_de_pago=e("WHATSAPP_PLANTILLAS_DE_PAGO", "").strip() == "1",
            url_publica=e("WHATSAPP_URL_PUBLICA", "").strip().rstrip("/"),
            admin_token=e("WHATSAPP_ADMIN_TOKEN", "").strip(),
            interno_token=e("WHATSAPP_INTERNO_TOKEN", "").strip(),
            db_path=e("WHATSAPP_DB", "").strip() or str(base / "datos" / "whatsapp.db"),
        )
        claves = CLAVES_360 if proveedor == "360dialog" else CLAVES_META
        ajustes.faltan = [k for k in claves if not e(k, "").strip()]
        return ajustes

    @property
    def es_360(self) -> bool:
        return self.proveedor == "360dialog"

    @property
    def listo(self) -> bool:
        """True si están las claves para hablar con WhatsApp por el proveedor elegido."""
        if self.es_360:
            return bool(self.d360_api_key and self.webhook_secreto)
        return all(
            (self.verify_token, self.app_secret, self.access_token, self.phone_number_id, self.waba_id)
        )

    @property
    def meta_listo(self) -> bool:  # nombre antiguo
        return self.listo
