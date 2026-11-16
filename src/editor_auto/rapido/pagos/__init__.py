"""Pasarelas de pago del Editor rápido. `proveedor()` devuelve la elegida con EDITOR_PAGOS_PROVEEDOR (polar|lemon)."""
from __future__ import annotations

import os

from .base import EventoPago, FirmaInvalida, NoConfigurado, PagoError, ProveedorPago


def proveedor() -> ProveedorPago:
    nombre = (os.getenv("EDITOR_PAGOS_PROVEEDOR", "") or "polar").strip().lower()
    if nombre == "lemon":
        from .lemon import Lemon
        return Lemon()
    if nombre == "polar":
        from .polar import Polar
        return Polar()
    raise PagoError(f"Proveedor de pagos desconocido: {nombre}")


__all__ = ["proveedor", "EventoPago", "FirmaInvalida", "NoConfigurado", "PagoError", "ProveedorPago"]
