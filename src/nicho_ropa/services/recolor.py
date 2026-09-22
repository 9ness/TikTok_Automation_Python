"""Recolorear una foto con Gemini (modelo de imagen).

Lo usa el formato "Tienda Colores": el primer fotograma del clip 1 se manda
una vez por cada color que la chica nombra y no lleva puesto, y lo que vuelve
es la MISMA foto con el pantalón de ese color. Al montar se intercalan al
ritmo de las palabras, que es el corte de edición que hace viral el formato.

Va por REST y no por el SDK: `google-generativeai` no expone
`responseModalities` en todas las versiones, y la llamada es una sola
petición con la imagen inline. Las keys son las mismas de todo el proyecto
(`_get_gemini_keys`: free → paid → legacy), y como el free tier no suele
tener cuota para imagen se salta al siguiente en cuanto una da 429/403.

Cada imagen se apunta en el coste del trabajo (`record_gemini` con los
tokens reales del `usageMetadata`): unos 4 céntimos por color.
"""

from __future__ import annotations

import base64
import os
from typing import Callable

OnLog = Callable[[str], None]
_noop: OnLog = lambda _m: None

# Nano Banana. Se puede cambiar sin tocar código si Google lo renombra.
MODELO = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
_URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
_TIMEOUT_S = 120
# Códigos con los que se prueba la siguiente key en vez de rendirse.
_CAMBIAR_KEY = {403, 429}
# Cuántas veces se le pide la MISMA imagen: en la primera prueba real, de
# tres colores uno volvió sin imagen (`finishReason: IMAGE_OTHER`) y a la
# segunda salió. Es un tropiezo del modelo, no del prompt.
_INTENTOS = 2

# Del nombre en español del guion a cómo se le pide al modelo. En inglés y
# con matiz: "beige" a secas fallaba y "a light sand / cream beige colour"
# salió a la primera. Lo que no esté aquí va tal cual, marcado como color
# en español.
_COLORES_EN: dict[str, str] = {
    "rosa": "light pink",
    "rosa palo": "dusty pink",
    "fucsia": "fuchsia pink",
    "beige": "a light sand / cream beige colour",
    "beis": "a light sand / cream beige colour",
    "crema": "cream",
    "blanco": "white",
    "blanco roto": "off-white",
    "negro": "black",
    "gris": "grey",
    "gris claro": "light grey",
    "gris oscuro": "dark grey",
    "verde": "green",
    "verde militar": "olive / army green",
    "verde oliva": "olive green",
    "caqui": "khaki",
    "kaki": "khaki",
    "camel": "camel (light tan brown)",
    "marron": "brown",
    "marrón": "brown",
    "marron oscuro": "dark chocolate brown",
    "marrón oscuro": "dark chocolate brown",
    "chocolate": "chocolate brown",
    "azul": "blue",
    "azul claro": "light blue",
    "azul marino": "navy blue",
    "azul cielo": "sky blue",
    "celeste": "sky blue",
    "burdeos": "burgundy / wine red",
    "granate": "burgundy / wine red",
    "rojo": "red",
    "naranja": "orange",
    "amarillo": "yellow",
    "mostaza": "mustard yellow",
    "lila": "lilac",
    "morado": "purple",
    "violeta": "violet purple",
    "turquesa": "turquoise",
    "dorado": "gold",
    "plateado": "silver",
    # Nombres que usan las tiendas de TikTok Shop en el selector de color.
    "taupe": "taupe (warm grey-brown)",
    "arena": "sand beige",
    "tostado": "toasted tan brown",
    "nude": "nude (light skin-tone beige)",
    "hueso": "bone white (warm off-white)",
    "marfil": "ivory",
    "vino": "wine red",
    "teja": "terracotta",
    "terracota": "terracotta",
    "coral": "coral",
    "salmon": "salmon pink",
    "salmón": "salmon pink",
    "menta": "mint green",
    "lavanda": "lavender",
    "esmeralda": "emerald green",
    "petroleo": "petrol / teal blue",
    "petróleo": "petrol / teal blue",
    "antracita": "anthracite dark grey",
    "tabaco": "tobacco brown",
    "cobre": "copper",
    "bronce": "bronze",
    "verde botella": "bottle green",
    "verde caqui": "khaki green",
    "azul klein": "Klein blue (vivid cobalt)",
    "azul eléctrico": "electric blue",
    "azul electrico": "electric blue",
    "azul bebe": "baby blue",
    "azul bebé": "baby blue",
    "rosa bebe": "baby pink",
    "rosa bebé": "baby pink",
    "rosa empolvado": "powder pink",
    "cereza": "cherry red",
}


def describir_color(color: str) -> str:
    """Cómo se le pide ese color al modelo (inglés, con matiz si lo hay)."""
    import unicodedata

    plano = "".join(
        c for c in unicodedata.normalize("NFKD", color or "")
        if not unicodedata.combining(c)
    ).lower().strip()
    plano = " ".join(plano.split())
    if plano in _COLORES_EN:
        return _COLORES_EN[plano]
    # "rosa claro", "verde agua"…: la base traducida y el matiz tal cual.
    base = plano.split(" ")[0]
    if base in _COLORES_EN and len(plano.split(" ")) > 1:
        return f"{_COLORES_EN[base]} ({plano}, a Spanish colour name)"
    return f'the colour "{color.strip()}" (a Spanish colour name)'


def recolorear(
    imagen: bytes, color: str, mime: str = "image/jpeg", on_log: OnLog = _noop,
    tono: str = "",
) -> bytes:
    """La misma foto con la prenda en `color`. Lanza `RuntimeError` si no sale.

    `tono` es el hex de la miniatura de esa variante en la tienda (lo leyó el
    guion de la captura): con él el modelo clava ESE beige y no uno genérico.
    Se manda como texto y no la captura como imagen: adjuntándola, el modelo
    calcaba la barra de "Añadir al carrito" en la foto (probado dos veces).
    """
    ultimo: Exception | None = None
    for intento in range(1, _INTENTOS + 1):
        try:
            return _recolorear(imagen, color, mime, on_log, tono)
        except RuntimeError as e:
            ultimo = e
            if intento < _INTENTOS:
                on_log(f"[recolor] «{color}»: {str(e)[:120]} — se reintenta")
    raise RuntimeError(str(ultimo))


def _recolorear(
    imagen: bytes, color: str, mime: str, on_log: OnLog, tono: str = "",
) -> bytes:
    import requests

    from src.nicho_ropa import config
    from src.tiktok_shop.api.gemini import _get_gemini_keys

    keys = _get_gemini_keys()
    if not keys:
        raise RuntimeError("sin key de Gemini configurada")

    cuerpo = {
        "contents": [{"parts": [
            {"text": config.prompt_recolor(describir_color(color), tono)},
            {"inline_data": {
                "mime_type": mime,
                "data": base64.b64encode(imagen).decode("ascii"),
            }},
        ]}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }
    ultimo = ""
    for etiqueta, key in keys:
        try:
            resp = requests.post(
                _URL.format(modelo=MODELO), params={"key": key}, json=cuerpo,
                timeout=_TIMEOUT_S,
            )
        except requests.RequestException as e:
            ultimo = f"{etiqueta}: {e}"
            on_log(f"[recolor] {ultimo}")
            continue
        if resp.status_code in _CAMBIAR_KEY:
            ultimo = f"{etiqueta}: HTTP {resp.status_code}"
            on_log(f"[recolor] {ultimo} — se prueba la siguiente key")
            continue
        if resp.status_code != 200:
            raise RuntimeError(f"Gemini imagen ({etiqueta}) HTTP {resp.status_code}: {resp.text[:200]}")
        datos = resp.json()
        _apuntar_coste(datos, color)
        salida = _imagen_de(datos)
        if not salida:
            raise RuntimeError(
                f"Gemini imagen ({etiqueta}) no devolvió imagen para «{color}»: "
                + _motivo(datos)
            )
        return salida
    raise RuntimeError(f"ninguna key de Gemini sirvió para la imagen ({ultimo})")


def _imagen_de(datos: dict) -> bytes:
    for cand in datos.get("candidates") or []:
        for parte in ((cand.get("content") or {}).get("parts") or []):
            inline = parte.get("inlineData") or parte.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
    return b""


def _motivo(datos: dict) -> str:
    cand = (datos.get("candidates") or [{}])[0]
    razon = cand.get("finishReason") or ""
    bloqueo = (datos.get("promptFeedback") or {}).get("blockReason") or ""
    texto = " ".join(
        str(p.get("text") or "") for p in ((cand.get("content") or {}).get("parts") or [])
    ).strip()
    return " · ".join(x for x in (razon, bloqueo, texto[:120]) if x) or "sin motivo"


def _apuntar_coste(datos: dict, color: str) -> None:
    """Coste real por tokens: nunca tumba la llamada si el tracker no está."""
    try:
        from src.cost_tracking import record_gemini

        uso = datos.get("usageMetadata") or {}
        record_gemini(
            input_tokens=int(uso.get("promptTokenCount") or 0),
            output_tokens=int(uso.get("candidatesTokenCount") or 0),
            model=MODELO, detail=f"recolor · {color}",
        )
    except Exception:  # noqa: BLE001
        pass
