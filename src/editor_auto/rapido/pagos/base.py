"""Interfaz de pasarela de pago del Editor rápido (el proveedor se elige con EDITOR_PAGOS_PROVEEDOR)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol


class PagoError(RuntimeError):
    """Fallo de configuración o de la API del proveedor (la ruta lo traduce a 503)."""


class FirmaInvalida(PagoError):
    """Firma o timestamp del webhook no válidos (401)."""


class NoConfigurado(PagoError):
    """Falta el secreto/clave del proveedor (503)."""


@dataclass(frozen=True)
class EventoPago:
    id_pedido: str
    email: str
    pack: str          # "25" | "60" | "150" ("" si no se pudo identificar)
    creditos: int      # 0 si pack desconocido
    pagado: bool
    tipo: str = "pago"  # "pago" | "reembolso" (total) | "reembolso_parcial"


class ProveedorPago(Protocol):
    nombre: str

    def crear_checkout(self, pack: str, email: str) -> str: ...

    def verificar_y_parsear_webhook(self, headers: Mapping[str, str], body: bytes) -> EventoPago | None:
        """Verifica la firma (lanza FirmaInvalida/NoConfigurado) y devuelve el evento normalizado,
        o None si el evento no es de compra (se ignora con 200)."""
        ...
