"""Marca «GMV Max»: productos o tiendas que inyectan GMV Max (anuncios de TikTok Shop).

Para el Black Friday (13-30/11) se suben primero los vídeos y carruseles de esos productos: su
tráfico pagado empuja también los vídeos de afiliado. Lo marcan los agentes al cruzar con Social1
(`marcar_gmv_max` del MCP) o el operador desde Mis tandas. La marca es GLOBAL (no por usuario):
una tienda que inyecta lo hace para Viva, Ama y Casca a la vez.

Una pieza (vídeo o carrusel) es GMV Max si:
  - su tienda está marcada, o
  - su producto está marcado: por id de producto de TikTok (sacado de la URL) o por tienda+título.
"""

from __future__ import annotations

import re
import time
import unicodedata

from src.mis_tandas import config


def _redis():
    from src.mis_tandas.servicio import _redis as r

    return r()


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


def id_producto(url: str) -> str:
    """El id numérico de TikTok Shop de una URL de producto (…/product/1729…), o ""."""
    m = re.search(r"(?:product|pdp)[/=](\d{10,})", str(url or "")) or re.search(r"\b(\d{15,})\b", str(url or ""))
    return m.group(1) if m else ""


def clave_producto(pieza: dict) -> str:
    return f"{norm(pieza.get('tienda', ''))}|{norm(pieza.get('titulo', ''))}"


def marcas() -> dict:
    r = _redis()
    if not r.is_available():
        return {"tiendas": {}, "productos": {}}
    d = r.get_json(config.GMV_MAX_KEY) or {}
    return {"tiendas": d.get("tiendas") or {}, "productos": d.get("productos") or {}}


def es_gmv_max(pieza: dict, m: dict | None = None) -> bool:
    m = m if m is not None else marcas()
    tienda = norm(pieza.get("tienda", ""))
    if tienda and tienda in m["tiendas"]:
        return True
    pid = id_producto(pieza.get("product_url") or pieza.get("url_producto") or "")
    if pid and pid in m["productos"]:
        return True
    return bool(norm(pieza.get("titulo", ""))) and clave_producto(pieza) in m["productos"]


def poner(*, tienda: str = "", pieza: dict | None = None, si: bool = True, nota: str = "", por: str = "") -> dict:
    """Marca (o desmarca, `si=False`) una tienda entera o el producto de una pieza."""
    from src.mis_tandas.servicio import ErrorTanda

    r = _redis()
    if not r.is_available():
        raise ErrorTanda("Redis no está disponible.", status=503)
    d = r.get_json(config.GMV_MAX_KEY) or {}
    tiendas, productos = d.get("tiendas") or {}, d.get("productos") or {}
    meta = {"at": time.time(), "por": por, "nota": nota[:300]}
    tocadas: list[str] = []
    if tienda:
        k = norm(tienda)
        if not k:
            raise ErrorTanda("Tienda vacía.")
        if si:
            tiendas[k] = {**meta, "nombre": tienda.strip()}
        else:
            tiendas.pop(k, None)
        tocadas.append(f"tienda «{tienda.strip()}»")
    if pieza:
        claves = [c for c in (id_producto(pieza.get("product_url") or ""),
                              clave_producto(pieza) if norm(pieza.get("titulo", "")) else "") if c]
        if not claves:
            raise ErrorTanda("Esa pieza no tiene título ni URL de producto: márcala por tienda.")
        for c in claves:
            if si:
                productos[c] = {**meta, "titulo": pieza.get("titulo", ""), "tienda": pieza.get("tienda", "")}
            else:
                productos.pop(c, None)
        tocadas.append(f"producto «{pieza.get('titulo', '')}»")
    if not tocadas:
        raise ErrorTanda("Di la tienda, el id de un vídeo/carrusel o el título del producto.")
    r.set_json(config.GMV_MAX_KEY, {"tiendas": tiendas, "productos": productos, "updated_at": time.time()})
    return {"ok": True, "gmv_max": si, "marcado": tocadas, "tiendas": len(tiendas), "productos": len(productos)}
