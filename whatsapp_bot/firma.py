"""Firma de los webhooks de Meta (cabecera ``X-Hub-Signature-256``).

Meta firma el CUERPO CRUDO de cada POST con HMAC-SHA256 y el App Secret de la
app. Se compara en tiempo constante y siempre sobre los bytes recibidos: si se
vuelve a serializar el JSON la firma deja de cuadrar.
"""
from __future__ import annotations

import hashlib
import hmac

PREFIJO = "sha256="


def calcular_firma(cuerpo: bytes, app_secret: str) -> str:
    """Devuelve la cabecera que mandaría Meta para ese cuerpo."""
    digest = hmac.new(app_secret.encode("utf-8"), cuerpo, hashlib.sha256).hexdigest()
    return PREFIJO + digest


def firma_valida(cuerpo: bytes, cabecera: str | None, app_secret: str) -> bool:
    """True solo si la cabecera existe, lleva el prefijo y coincide.

    Sin App Secret configurado NUNCA se da por buena: un webhook sin firma
    dejaría a cualquiera hacer hablar al bot.
    """
    if not app_secret or not cabecera or not cabecera.startswith(PREFIJO):
        return False
    esperada = calcular_firma(cuerpo, app_secret)
    return hmac.compare_digest(esperada, cabecera.strip())
