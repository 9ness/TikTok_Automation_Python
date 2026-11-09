"""Detector del puzle («Verifica para continuar») de TikTok sobre un volcado `uiautomator dump` (XML).

Aviso medido el 7/11: en el Mi 8 uiautomator a menudo NO ve el puzle (WebView/capa sin nodos), asi que
`detectar_puzle` es True si hay texto/desc/id de captcha, y `dump_sospechoso` avisa de un volcado casi vacio
(en ese caso confirmar por OCR, como `hay_puzle` de ~/work/oppo/movil.py). Solo detecta: la X se pulsa UNA vez
y nunca se resuelve el puzle (regla de Nestor).
"""
import re
import xml.etree.ElementTree as ET

_TEXTOS = re.compile(
    r"verifica para continuar|verify to continue|arrastra el (control|deslizador)|drag the slider|"
    r"desliza para completar|slide to complete|encaja la pieza|rota(r)? .*imagen|rotate the (image|puzzle)",
    re.I)
_IDS = re.compile(r"captcha|secsdk|verify_?(bar|container|dialog)|puzzle", re.I)
_CERRAR = re.compile(r"^(cerrar|close|x|×|✕)$|close_?(btn|button|icon)|btn_close|iv_close", re.I)
_BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def _nodos(xml):
    try:
        raiz = ET.fromstring(xml)
    except (ET.ParseError, TypeError, ValueError):
        return []
    return list(raiz.iter("node"))


def _centro(bounds):
    m = _BOUNDS.fullmatch((bounds or "").strip())
    if not m:
        return None
    x1, y1, x2, y2 = map(int, m.groups())
    if x2 <= x1 or y2 <= y1:
        return None
    return ((x1 + x2) // 2, (y1 + y2) // 2)


def detectar_puzle(xml: str) -> bool:
    for n in _nodos(xml):
        if _TEXTOS.search(n.get("text", "") or "") or _TEXTOS.search(n.get("content-desc", "") or ""):
            return True
        if _IDS.search(n.get("resource-id", "") or ""):
            return True
    return False


def boton_cerrar(xml: str):
    """(x, y) del centro del boton cerrar del puzle, o None si no hay puzle o no se ve el boton."""
    if not detectar_puzle(xml):
        return None
    for n in _nodos(xml):
        pistas = [n.get("text", ""), n.get("content-desc", ""), n.get("resource-id", "")]
        if any(_CERRAR.search((p or "").split("/")[-1].strip()) for p in pistas) and n.get("clickable") != "false":
            c = _centro(n.get("bounds"))
            if c:
                return c
    return None


def dump_sospechoso(xml: str, minimo: int = 6) -> bool:
    """Volcado casi vacio o sin parsear: el puzle (o una capa de carga) puede estar tapando la app."""
    return len(_nodos(xml)) < minimo
