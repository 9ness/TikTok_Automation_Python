"""Lemon Squeezy adaptado a la interfaz de pagos (se conserva; la lógica vive en rapido/lemon.py)."""
from __future__ import annotations

from typing import Mapping

from src.editor_auto.rapido import lemon as _ls
from .base import EventoPago, PagoError


class Lemon:
    nombre = "lemon"

    def crear_checkout(self, pack: str, email: str) -> str:
        try:
            return _ls.crear_checkout(int(pack), email)
        except _ls.LemonError as e:
            raise PagoError(str(e)) from e

    def verificar_y_parsear_webhook(self, headers: Mapping[str, str], body: bytes) -> EventoPago | None:
        # El webhook de Lemon sigue en POST /pagos/lemon (reembolsos incluidos); no pasa por aquí.
        raise NotImplementedError("Lemon usa su endpoint propio /pagos/lemon")
