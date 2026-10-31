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
PAQUETE = "com.zhiliaoapp.musically"
REINICIAR_CADA = 15  # TikTok se atasca con muchas fichas seguidas


def _adb(*args: str, timeout: int = 30) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, *args], capture_output=True, text=True, timeout=timeout)
    return r.stdout


def _textos() -> list[str]:
    _adb("shell", "uiautomator", "dump", "/sdcard/u.xml")
    xml = _adb("shell", "cat", "/sdcard/u.xml")
    return [t.strip() for t in re.findall(r'text="([^"]+)"', xml) if t.strip()]


def _colgado(textos: list[str]) -> bool:
    foco = _adb("shell", "dumpsys", "window")
    return "Not Responding" in foco or any("no responde" in t.lower() for t in textos)


def reiniciar_tiktok() -> None:
    """Forzar detención: quita la ventana de «TikTok no responde» y la memoria acumulada."""
    _adb("shell", "am", "force-stop", PAQUETE)
    time.sleep(2)
    _adb("shell", "monkey", "-p", PAQUETE, "-c", "android.intent.category.LAUNCHER", "1")
    time.sleep(10)


def _despertar() -> None:
    """En AOD (Dozing) WAKEUP solo no basta y la ficha se lee tras la pantalla de
    bloqueo → todo «desconocido». Se insiste con POWER y se quita el bloqueo."""
    _adb("shell", "svc", "power", "stayon", "true")
    for _ in range(3):
        for tecla in ("KEYCODE_WAKEUP", "KEYCODE_POWER"):
            _adb("shell", "input", "keyevent", tecla)
            time.sleep(1.5)
            if "mWakefulness=Awake" in _adb("shell", "dumpsys power | grep mWakefulness="):
                break
        else:
            continue
        break
    _adb("shell", "wm", "dismiss-keyguard")
    time.sleep(1)
    if "isStatusBarKeyguard=true" in _adb("shell", "dumpsys window | grep isStatusBarKeyguard"):
        _adb("shell", "input", "swipe", "540", "1900", "540", "600", "300")
        time.sleep(2)
    # Guía «no cubrir la zona del auricular»: tapa la ficha y el volcado sale vacío.
    # Se quita con VOLUME_UP y EN SEGUIDA VOLUME_DOWN (autorizado; nunca UP suelto).
    for _ in range(3):
        if "ScreenOnProximitySensorGuide" not in _adb("shell", "dumpsys window | grep mCurrentFocus"):
            break
        _adb("shell", "input keyevent KEYCODE_VOLUME_UP && input keyevent KEYCODE_VOLUME_DOWN")
        time.sleep(2)


def _leer(product_id: str) -> str:
    _despertar()
    _adb("shell", "am", "start", "-a", "android.intent.action.VIEW",
         "-d", f"'snssdk1233://ec/pdp?product_id={product_id}'")
    textos: list[str] = []
    for _ in range(3):
        time.sleep(ESPERA_S)
        textos = _textos()
        if _colgado(textos):
            reiniciar_tiktok()
            return "colgado"
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
    return estado


def comprobar(product_id: str) -> dict:
    """Lo que no sea agotado/en_stock se repite tras forzar la detención: con
    TikTok atascado salen «no disponible» falsos."""
    estado = _leer(product_id)
    if estado not in ("agotado", "en_stock"):
        reiniciar_tiktok()
        estado = _leer(product_id)
    return {"product_id": product_id, "estado": estado}


def cerrar() -> None:
    """Al acabar no se deja TikTok abierto: cerrarlo, ir al inicio y apagar la pantalla."""
    _adb("shell", "am", "force-stop", PAQUETE)
    _adb("shell", "input", "keyevent", "KEYCODE_HOME")
    _adb("shell", "svc", "power", "stayon", "false")
    _adb("shell", "input", "keyevent", "KEYCODE_SLEEP")


def main() -> None:
    try:
        for i, pid in enumerate(sys.argv[1:]):
            if i and i % REINICIAR_CADA == 0:
                reiniciar_tiktok()
            print(json.dumps(comprobar(pid), ensure_ascii=False), flush=True)
    finally:
        cerrar()


if __name__ == "__main__":
    main()
