"""Polar.sh (merchant of record) para el Editor rápido.

Checkout: POST /v1/checkouts/ (products=[id], customer_email, metadata, success_url).
Webhook `order.paid` firmado con Standard Webhooks (webhook-id / webhook-timestamp / webhook-signature).
Env: POLAR_ACCESS_TOKEN, POLAR_WEBHOOK_SECRET, POLAR_SERVER (sandbox|production),
POLAR_PRODUCT_25 / _60 / _150, EDITOR_PAGOS_VUELTA (success_url, opcional).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Mapping

import requests

from .base import EventoPago, FirmaInvalida, NoConfigurado, PagoError

PACKS = ("25", "60", "150")
TOLERANCIA_S = 300


def _api() -> str:
    return ("https://sandbox-api.polar.sh" if os.getenv("POLAR_SERVER", "production").strip().lower() == "sandbox"
            else "https://api.polar.sh")


def _producto(pack: str) -> str:
    return os.getenv(f"POLAR_PRODUCT_{pack}", "").strip()


def _pack_de_producto(product_id: str) -> str:
    for p in PACKS:
        if _producto(p) and _producto(p) == product_id:
            return p
    return ""


def _claves(secreto: str) -> list[bytes]:
    """Claves HMAC candidatas. Estándar (secretos nuevos): base64-decode del `whsec_…` sin prefijo.
    Legado de Polar: los bytes UTF-8 del secreto entero (el SDK lo codificaba en base64 antes)."""
    out: list[bytes] = []
    s = secreto.removeprefix("whsec_")
    try:
        out.append(base64.b64decode(s, validate=True))
    except Exception:  # noqa: BLE001
        pass
    out.append(secreto.encode())
    return out


class Polar:
    nombre = "polar"

    def crear_checkout(self, pack: str, email: str) -> str:
        token = os.getenv("POLAR_ACCESS_TOKEN", "").strip()
        if not token:
            raise PagoError("Falta POLAR_ACCESS_TOKEN")
        prod = _producto(str(pack))
        if str(pack) not in PACKS or not prod:
            raise PagoError(f"No hay producto de Polar para el pack {pack}")
        cuerpo: dict = {"products": [prod], "customer_email": email,
                        "metadata": {"email": email, "pack": str(pack)}}
        vuelta = os.getenv("EDITOR_PAGOS_VUELTA", "https://editor.nebulabsmedia.com/editor")
        if vuelta:
            cuerpo["success_url"] = vuelta
        r = requests.post(f"{_api()}/v1/checkouts/", json=cuerpo, timeout=15,
                          headers={"Authorization": f"Bearer {token}"})
        if r.status_code >= 400:
            raise PagoError(f"Polar checkout → {r.status_code}: {r.text[:300]}")
        url = (r.json() or {}).get("url")
        if not url:
            raise PagoError("Polar no devolvió la URL del checkout")
        return url

    def verificar_y_parsear_webhook(self, headers: Mapping[str, str], body: bytes) -> EventoPago | None:
        secreto = os.getenv("POLAR_WEBHOOK_SECRET", "").strip()
        if not secreto:
            raise NoConfigurado("Falta POLAR_WEBHOOK_SECRET")
        h = {k.lower(): v for k, v in headers.items()}
        wid, ts, sigs = h.get("webhook-id", ""), h.get("webhook-timestamp", ""), h.get("webhook-signature", "")
        if not (wid and ts and sigs):
            raise FirmaInvalida("Faltan cabeceras de firma")
        try:
            if abs(time.time() - int(ts)) > TOLERANCIA_S:
                raise FirmaInvalida("Timestamp fuera de margen")
        except ValueError:
            raise FirmaInvalida("Timestamp no válido")
        firmado = f"{wid}.{ts}.".encode() + body
        validas = {base64.b64encode(hmac.new(k, firmado, hashlib.sha256).digest()).decode() for k in _claves(secreto)}
        recibidas = [p.split(",", 1)[1] for p in sigs.split() if p.startswith("v1,")]
        if not any(hmac.compare_digest(a, b) for a in recibidas for b in validas):
            raise FirmaInvalida("Firma no válida")
        try:
            d = json.loads(body)
        except ValueError:
            return None
        if d.get("type") != "order.paid":
            return None
        o = d.get("data") or {}
        meta = o.get("metadata") or {}
        email = str(meta.get("email") or (o.get("customer") or {}).get("email") or "").strip().lower()
        # El pack sale del producto pagado; metadata.pack solo si no hay productos configurados.
        configurados = any(_producto(p) for p in PACKS)
        pack = _pack_de_producto(str(o.get("product_id") or "")) or ("" if configurados else str(meta.get("pack") or ""))
        if pack not in PACKS:
            pack = ""
        pagado = bool(o.get("paid")) or o.get("status") == "paid"
        return EventoPago(id_pedido=str(o.get("id") or ""), email=email, pack=pack,
                          creditos=int(pack) if pack else 0, pagado=pagado)
