"""Lemon Squeezy para el Editor rápido: packs de la tienda, enlaces de pago y webhooks.

Los packs se reconocen por el NOMBRE del producto o variante («25 vídeos» → 25 créditos),
no por el id: al copiar los productos a modo live cambian los ids y no hay que tocar nada.
Clave: `EDITOR_LS_API_KEY` (la de prueba da checkouts y pedidos de prueba; la live, reales).
Detalle: nebulabs-media/docs/LEMON_SQUEEZY_EDITOR.md · variables en docs/contexto/env-vars.md.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time

import requests

logger = logging.getLogger("editor_auto.rapido.lemon")

API = "https://api.lemonsqueezy.com/v1"
_CABECERAS = {"Accept": "application/vnd.api+json", "Content-Type": "application/vnd.api+json"}
_CACHE: dict = {"t": 0.0, "packs": {}}
_LOCK = threading.Lock()
_TTL_S = 600


class LemonError(RuntimeError):
    pass


def clave() -> str:
    return os.getenv("EDITOR_LS_API_KEY", "").strip()


def tienda() -> str:
    return os.getenv("EDITOR_LS_TIENDA_ID", "").strip()


def packs_validos() -> set[int]:
    """Créditos que puede tener un pack (`EDITOR_LS_PACKS`, por defecto 25,60,150)."""
    out = set()
    for x in (os.getenv("EDITOR_LS_PACKS", "") or "25,60,150").split(","):
        if x.strip().isdigit():
            out.add(int(x.strip()))
    return out


def creditos_de_nombre(*textos: str | None) -> int | None:
    """Primer número de los nombres que sea un pack válido («Pack 60 vídeos» → 60)."""
    validos = packs_validos()
    for t in textos:
        for n in re.findall(r"\d+", str(t or "")):
            if int(n) in validos:
                return int(n)
    return None


def _pedir(metodo: str, ruta: str, *, params: dict | None = None, cuerpo: dict | None = None) -> dict:
    k = clave()
    if not k:
        raise LemonError("Falta EDITOR_LS_API_KEY")
    r = requests.request(metodo, f"{API}{ruta}", params=params, json=cuerpo, timeout=15,
                         headers={**_CABECERAS, "Authorization": f"Bearer {k}"})
    if r.status_code >= 400:
        raise LemonError(f"Lemon {metodo} {ruta} → {r.status_code}: {r.text[:300]}")
    return r.json()


def _todos(ruta: str, params: dict) -> list[dict]:
    out, pag = [], 1
    while pag <= 10:
        d = _pedir("GET", ruta, params={**params, "page[size]": 100, "page[number]": pag})
        out += d.get("data") or []
        if pag >= int(((d.get("meta") or {}).get("page") or {}).get("lastPage") or 1):
            break
        pag += 1
    return out


def packs(forzar: bool = False) -> dict[int, dict]:
    """{créditos: {"variante": id, "producto": nombre, "precio": céntimos, "test": bool}} de la tienda."""
    with _LOCK:
        if not forzar and _CACHE["packs"] and time.time() - _CACHE["t"] < _TTL_S:
            return _CACHE["packs"]
    params = {"filter[store_id]": tienda()} if tienda() else {}
    nombres = {p["id"]: (p.get("attributes") or {}).get("name") for p in _todos("/products", params)}
    out: dict[int, dict] = {}
    for pid, nombre in nombres.items():
        for v in _todos("/variants", {"filter[product_id]": pid}):
            a = v.get("attributes") or {}
            if a.get("status") == "draft":
                continue
            n = creditos_de_nombre(nombre, a.get("name"))
            if n and n not in out:
                out[n] = {"variante": str(v["id"]), "producto": nombre, "precio": a.get("price"),
                          "test": bool(a.get("test_mode"))}
    with _LOCK:
        _CACHE.update(t=time.time(), packs=out)
    return out


def crear_checkout(creditos: int, email: str, vuelta: str | None = None) -> str:
    """Enlace de pago de un solo uso con el email puesto (y en custom_data para el webhook)."""
    if not tienda():
        raise LemonError("Falta EDITOR_LS_TIENDA_ID")
    p = packs().get(int(creditos))
    if not p:
        raise LemonError(f"No hay pack de {creditos} créditos en la tienda")
    attrs: dict = {"checkout_data": {"email": email, "custom": {"email": email}}}
    vuelta = vuelta or os.getenv("EDITOR_LS_VUELTA", "https://editor.nebulabsmedia.com/editor")
    if vuelta:
        attrs["product_options"] = {"redirect_url": vuelta}
    d = _pedir("POST", "/checkouts", cuerpo={"data": {
        "type": "checkouts", "attributes": attrs,
        "relationships": {"store": {"data": {"type": "stores", "id": tienda()}},
                          "variant": {"data": {"type": "variants", "id": p["variante"]}}}}})
    url = ((d.get("data") or {}).get("attributes") or {}).get("url")
    if not url:
        raise LemonError("Lemon no devolvió la URL del checkout")
    return url
