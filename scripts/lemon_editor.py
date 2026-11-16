#!/usr/bin/env python3
"""Lemon Squeezy del Editor rápido: ver la tienda y crear el webhook sin pasar secretos por chat.

    python3 scripts/lemon_editor.py ver              # tienda, packs (créditos por nombre) y webhooks
    python3 scripts/lemon_editor.py webhook          # crea el webhook (test) si no existe
    python3 scripts/lemon_editor.py webhook --live   # ídem en modo live (con la API key live)

Lee EDITOR_LS_API_KEY y EDITOR_LS_TIENDA_ID del .env (`--env`, por defecto el del repo
principal). Si falta EDITOR_LS_WEBHOOK_SECRET lo genera y lo escribe en el .env (chmod 600);
nunca lo imprime. Después hay que recrear el contenedor api para que lo lea:
`docker compose --env-file .env up -d api`. Solo stdlib.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.lemonsqueezy.com/v1"
URL_WEBHOOK = "https://factory.nebulabsmedia.com/api/v1/editor-auto/rapido/pagos/lemon"
EVENTOS = ["order_created", "order_refunded"]
ENV_DEF = Path.home() / "proyectos/TikTok_Automation_Python/.env"


def leer_env(p: Path) -> dict[str, str]:
    out = {}
    for linea in p.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*([A-Z0-9_]+)\s*=\s*(.*)$", linea)
        if m:
            out[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return out


def poner_env(p: Path, nombre: str, valor: str) -> None:
    txt = p.read_text(encoding="utf-8")
    if re.search(rf"^\s*{nombre}\s*=", txt, re.M):
        txt = re.sub(rf"^\s*{nombre}\s*=.*$", f"{nombre}={valor}", txt, flags=re.M)
    else:
        txt = txt.rstrip("\n") + f"\n{nombre}={valor}\n"
    p.write_text(txt, encoding="utf-8")
    os.chmod(p, 0o600)


def pedir(clave: str, metodo: str, ruta: str, params: dict | None = None, cuerpo: dict | None = None) -> dict:
    url = API + ruta + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, method=metodo, data=json.dumps(cuerpo).encode() if cuerpo else None, headers={
        "Accept": "application/vnd.api+json", "Content-Type": "application/vnd.api+json",
        "Authorization": f"Bearer {clave}", "User-Agent": "nebulabs-editor"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        sys.exit(f"Lemon {metodo} {ruta} → {e.code}: {e.read()[:400].decode(errors='replace')}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("accion", choices=["ver", "webhook"])
    ap.add_argument("--live", action="store_true", help="webhook en modo live (por defecto, test)")
    ap.add_argument("--env", type=Path, default=ENV_DEF)
    ap.add_argument("--url", default=URL_WEBHOOK)
    a = ap.parse_args()
    env = leer_env(a.env)
    clave, tienda = env.get("EDITOR_LS_API_KEY", ""), env.get("EDITOR_LS_TIENDA_ID", "")
    if not clave:
        sys.exit(f"Falta EDITOR_LS_API_KEY en {a.env} (Néstor: `clave TikTok_Automation_Python EDITOR_LS_API_KEY`).")

    yo = pedir(clave, "GET", "/users/me")["data"]["attributes"]
    tiendas = pedir(clave, "GET", "/stores")["data"]
    print(f"Cuenta: {yo.get('name')} · tiendas: " + ", ".join(f"{t['id']} {t['attributes']['name']}" for t in tiendas))
    if not tienda:
        if len(tiendas) != 1:
            sys.exit("Pon EDITOR_LS_TIENDA_ID en el .env: hay más de una tienda.")
        tienda = str(tiendas[0]["id"])
        poner_env(a.env, "EDITOR_LS_TIENDA_ID", tienda)
        print(f"EDITOR_LS_TIENDA_ID={tienda} escrito en el .env")

    if a.accion == "ver":
        for p in pedir(clave, "GET", "/products", {"filter[store_id]": tienda})["data"]:
            for v in pedir(clave, "GET", "/variants", {"filter[product_id]": p["id"]})["data"]:
                va = v["attributes"]
                print(f"  producto {p['id']} «{p['attributes']['name']}» · variante {v['id']} «{va.get('name')}» "
                      f"· {va.get('price', 0) / 100:.2f} € · {va.get('status')} · test={va.get('test_mode')}")
        for w in pedir(clave, "GET", "/webhooks", {"filter[store_id]": tienda})["data"]:
            wa = w["attributes"]
            print(f"  webhook {w['id']} {wa.get('url')} {wa.get('events')} test={wa.get('test_mode')}")
        return

    test = not a.live
    for w in pedir(clave, "GET", "/webhooks", {"filter[store_id]": tienda})["data"]:
        wa = w["attributes"]
        if wa.get("url") == a.url and bool(wa.get("test_mode")) == test:
            print(f"Ya existe el webhook {w['id']} (test={test}). No se toca.")
            return
    secreto = env.get("EDITOR_LS_WEBHOOK_SECRET", "")
    if len(secreto) > 40:  # Lemon no admite más de 40 caracteres
        secreto = ""
    if not secreto:
        secreto = secrets.token_hex(20)  # 40 caracteres: el máximo de Lemon
        poner_env(a.env, "EDITOR_LS_WEBHOOK_SECRET", secreto)
        print("EDITOR_LS_WEBHOOK_SECRET generado y escrito en el .env (no se muestra).")
    w = pedir(clave, "POST", "/webhooks", cuerpo={"data": {
        "type": "webhooks",
        "attributes": {"url": a.url, "events": EVENTOS, "secret": secreto, "test_mode": test},
        "relationships": {"store": {"data": {"type": "stores", "id": tienda}}}}})["data"]
    print(f"Webhook {w['id']} creado → {a.url} {EVENTOS} test={test}")
    print("Falta: recrear la API para que lea el .env → docker compose --env-file .env up -d api")


if __name__ == "__main__":
    main()
