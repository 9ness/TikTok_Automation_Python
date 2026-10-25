"""Comprueba en la APP de TikTok (móvil por ADB) si un producto de TikTok Shop está agotado.

La ficha web de TikTok Shop ES no enseña el stock (pide captcha y, resuelto, solo
remite a la app). Esto abre la ficha en el Xiaomi Mi 8 conectado por ADB sobre
Tailscale y lee el texto de la pantalla:

    python scripts/stock_tiktok_movil.py 1729883030578436385 1729869057806408431

Requisitos: `adb connect <IP Tailscale>:5555` hecho, TikTok con una cuenta de
región España (con región/SIM de EE. UU. sale «no disponible en este país»).
Enlace que funciona: `snssdk1233://ec/pdp?product_id=<id>`; el https de
/view/product saca el selector de apps o se queda en el perfil.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

SERIAL = os.environ.get("MOVIL_ADB", "100.115.12.26:5555")
ESPERA_S = 12


def _adb(*args: str, timeout: int = 30) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, *args], capture_output=True, text=True, timeout=timeout)
    return r.stdout


def _textos() -> list[str]:
    _adb("shell", "uiautomator", "dump", "/sdcard/u.xml")
    xml = _adb("shell", "cat", "/sdcard/u.xml")
    return [t.strip() for t in re.findall(r'text="([^"]+)"', xml) if t.strip()]


def comprobar(product_id: str) -> dict:
    _adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
    _adb("shell", "am", "start", "-a", "android.intent.action.VIEW",
         "-d", f"'snssdk1233://ec/pdp?product_id={product_id}'")
    textos: list[str] = []
    for _ in range(3):
        time.sleep(ESPERA_S)
        textos = _textos()
        if any("Comprar" in t or "agotado" in t.lower() or "disponible" in t.lower() for t in textos):
            break
    unido = " | ".join(textos).lower()
    if "agotado" in unido:
        estado = "agotado"
    elif "no está disponible" in unido:
        estado = "no_disponible"
    elif "comprar" in unido:
        estado = "en_stock"
    else:
        estado = "desconocido"
    _adb("shell", "input", "keyevent", "KEYCODE_BACK")
    return {"product_id": product_id, "estado": estado}


def main() -> None:
    for pid in sys.argv[1:]:
        print(json.dumps(comprobar(pid), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
