"""La captura del selector de colores de una prenda ("captura de variantes").

La captura de la ficha que viene del Drive o del ZIP casi nunca llega hasta
el selector "Color" de TikTok Shop, y el formato Tienda Colores necesita los
nombres EXACTOS de las variantes (el vídeo tiene que decir lo mismo que la
ficha, o TikTok lo sanciona como producto inconsistente). Así que el operador
sube UNA captura más —la del selector, con las miniaturas y sus nombres— y
se adjunta al guion junto con la ficha y la limpia.

Vive en el Drive montado, aparte de las fotos de la prenda: en la carpeta de
la prenda rompería el emparejado limpia/ficha (que mira todas las imágenes
del directorio). `_variantes` cuelga de la raíz de prendas importadas, que
no es un género y no sale en ningún selector.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.nicho_ropa import config

_EXTS = (".jpg", ".jpeg", ".png", ".webp")
MAX_BYTES = 12 * 1024 * 1024


def _dir(carpeta: str) -> Path:
    seguro = re.sub(r"[^\w.\- ]+", "_", carpeta or "").strip() or "_"
    return config.prendas_web_dir() / "_variantes" / seguro


def ruta(carpeta: str, producto: str) -> Path | None:
    """La captura guardada de esa prenda, o None (nunca la copia cuadrada)."""
    d = _dir(carpeta)
    if not d.is_dir():
        return None
    for ext in _EXTS:
        f = d / f"{producto}{ext}"
        if f.is_file() and f.stat().st_size > 0:
            return f
    return None


def guardar(carpeta: str, producto: str, datos: bytes, nombre: str) -> Path:
    """Sustituye la que hubiera (con otra extensión también)."""
    ext = Path(nombre or "").suffix.lower()
    if ext not in _EXTS:
        raise ValueError(f"Formato no soportado ({nombre!r}): acepta jpg, jpeg, png o webp.")
    if not datos:
        raise ValueError("La captura llegó vacía.")
    if len(datos) > MAX_BYTES:
        raise ValueError(f"La captura pesa {len(datos) / 1e6:.0f} MB; el tope son 12 MB.")
    d = _dir(carpeta)
    d.mkdir(parents=True, exist_ok=True)
    quitar(carpeta, producto)
    destino = d / f"{producto}{ext}"
    destino.write_bytes(datos)
    return destino


def quitar(carpeta: str, producto: str) -> bool:
    habia = False
    for ext in _EXTS:
        f = _dir(carpeta) / f"{producto}{ext}"
        if f.is_file():
            f.unlink(missing_ok=True)
            habia = True
    return habia


def tienen(carpeta: str) -> set[str]:
    """Productos de la carpeta con captura, en una sola lectura del disco."""
    d = _dir(carpeta)
    if not d.is_dir():
        return set()
    return {
        f.stem for f in d.iterdir()
        if f.is_file() and f.suffix.lower() in _EXTS and "__" not in f.stem
    }


def extraer(captura: Path) -> dict:
    """`{"colores": [...], "hex": {...}}` leídos de la captura con Gemini.

    Una llamada de texto con UNA imagen. No se hace dentro del guion: con la
    ficha, la limpia y esta captura (precios, botones) Gemini bloqueó la
    petición entera y no salió ningún guion. Lanza si Gemini no contesta.
    """
    from src.nicho_ropa.services.guionista import limpiar_colores, limpiar_hex
    from src.tiktok_shop.api.gemini import generate_json

    prompt = config._limpio("variantes_colores.md")
    datos = generate_json(prompt, "Lee el selector de color de esta captura.", images=[str(captura)])
    colores = limpiar_colores((datos or {}).get("colores"))
    return {"colores": colores, "hex": limpiar_hex((datos or {}).get("hex"), colores)}


def detectar_miniaturas(captura: Path) -> list[tuple[int, int, int, int]]:
    """Las tarjetas del selector de color, de izquierda a derecha: `(x, y, w, h)`.

    Con OpenCV y no con Gemini: pedirle las cajas devolvía la Y normalizada
    por el ancho (los recortes caían en los pies de la modelo), y rellenando a
    cuadrado tampoco cuadraba. Las tarjetas son rectángulos con borde fino,
    del mismo tamaño y en fila; se buscan contornos así y se queda la fila
    con más. La tachada que asoma cortada por el borde no cierra contorno y
    se queda fuera sola.
    """
    import cv2
    import numpy as np

    im = cv2.imread(str(captura))
    if im is None:
        return []
    alto, ancho = im.shape[:2]
    gris = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    bordes = cv2.dilate(cv2.Canny(gris, 40, 120), np.ones((3, 3), np.uint8), 1)
    contornos, _ = cv2.findContours(bordes, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cajas = []
    for c in contornos:
        x, y, w, h = cv2.boundingRect(c)
        if 0.10 * ancho < w < 0.30 * ancho and 0.08 * ancho < h < 0.35 * ancho and 0.6 < w / h < 1.6:
            cajas.append((x, y, w, h))
    cajas.sort(key=lambda b: b[1])
    filas: list[list[tuple[int, int, int, int]]] = []
    for b in cajas:
        for f in filas:
            if abs(f[0][1] - b[1]) < 0.05 * alto and abs(f[0][3] - b[3]) < 0.3 * b[3]:
                f.append(b)
                break
        else:
            filas.append([b])
    if not filas:
        return []
    mejor = max(filas, key=len)
    if len(mejor) < 2:
        return []
    return sorted(mejor, key=lambda b: b[0])


def recortar_miniaturas(captura: Path, colores: list[str], carpeta: str, producto: str) -> list[str]:
    """Recorta de la captura la miniatura de cada color (por ORDEN: la lista
    leída y las tarjetas van las dos de izquierda a derecha, sin las
    tachadas) y la guarda como `<producto>__ref__<color>.jpg`: la foto del
    producto en ese color para adjuntar en Flow. Devuelve los que salieron.
    Si el número de tarjetas no cuadra con el de colores, no recorta nada:
    mejor ninguna que una con el nombre cambiado."""
    from PIL import Image

    cajas = detectar_miniaturas(captura)
    if not cajas or len(cajas) != len(colores):
        return []
    d = _dir(carpeta)
    d.mkdir(parents=True, exist_ok=True)
    hechos: list[str] = []
    with Image.open(captura) as im:
        im = im.convert("RGB")
        for color, (x, y, w, h) in zip(colores, cajas):
            # Solo la foto: el nombre va en el cuarto de abajo de la tarjeta.
            im.crop((x + 2, y + 2, x + w - 2, y + int(h * 0.78))).save(
                d / f"{producto}__ref__{_slug_color(color)}.jpg", "JPEG", quality=92,
            )
            hechos.append(color)
    return hechos


def ruta_miniatura(carpeta: str, producto: str, color: str) -> Path | None:
    f = _dir(carpeta) / f"{producto}__ref__{_slug_color(color)}.jpg"
    return f if f.is_file() and f.stat().st_size > 0 else None


def miniaturas_de(carpeta: str, producto: str, colores: list[str]) -> list[str]:
    return [c for c in colores if ruta_miniatura(carpeta, producto, c)]


def guardar_leidos(carpeta: str, producto: str, leido: dict) -> None:
    """Apunta en la ficha del producto (doc compartido: los colores son del
    producto, no de quien lo graba) lo que se leyó de la captura."""
    import time

    from src.nicho_ropa.repos import product_repo

    product_repo.update_product(
        carpeta, producto,
        variantes={
            "colores": list(leido.get("colores") or []),
            "hex": dict(leido.get("hex") or {}),
            "at": int(time.time()),
        },
    )


def leidos(prod: dict) -> dict:
    """`{"colores": [...], "hex": {...}}` guardados en la ficha, o vacíos."""
    v = (prod or {}).get("variantes") or {}
    return {
        "colores": [str(c) for c in (v.get("colores") or []) if str(c).strip()],
        "hex": {str(k): str(x) for k, x in (v.get("hex") or {}).items() if str(x).strip()},
    }


# ---------------------------------------------------------------------------
# Fotos por color: la imagen 1 con el pantalón en cada uno de los otros
# colores, generadas en Flow por el operador (gratis) y subidas aquí. Son las
# que el montaje corta al ritmo de la voz. Van en la misma carpeta que la
# captura, con el color en el nombre: `<producto>__<color>.jpg`.
# ---------------------------------------------------------------------------
def _slug_color(color: str) -> str:
    import unicodedata

    plano = "".join(
        c for c in unicodedata.normalize("NFKD", color or "") if not unicodedata.combining(c)
    ).lower().strip()
    return re.sub(r"[^a-z0-9]+", "_", plano).strip("_")


def _es_ref(nombre: str) -> bool:
    return "__ref__" in nombre


def ruta_color(carpeta: str, producto: str, color: str) -> Path | None:
    d = _dir(carpeta)
    if not d.is_dir():
        return None
    for ext in _EXTS:
        f = d / f"{producto}__{_slug_color(color)}{ext}"
        if f.is_file() and f.stat().st_size > 0:
            return f
    return None


def guardar_color(carpeta: str, producto: str, color: str, datos: bytes, nombre: str) -> Path:
    ext = Path(nombre or "").suffix.lower()
    if ext not in _EXTS:
        raise ValueError(f"Formato no soportado ({nombre!r}): acepta jpg, jpeg, png o webp.")
    if not datos:
        raise ValueError("La foto llegó vacía.")
    if len(datos) > MAX_BYTES:
        raise ValueError(f"La foto pesa {len(datos) / 1e6:.0f} MB; el tope son 12 MB.")
    if not _slug_color(color):
        raise ValueError("Falta el color de la foto.")
    d = _dir(carpeta)
    d.mkdir(parents=True, exist_ok=True)
    quitar_color(carpeta, producto, color)
    destino = d / f"{producto}__{_slug_color(color)}{ext}"
    destino.write_bytes(datos)
    return destino


def quitar_color(carpeta: str, producto: str, color: str) -> bool:
    habia = False
    for ext in _EXTS:
        f = _dir(carpeta) / f"{producto}__{_slug_color(color)}{ext}"
        if f.is_file():
            f.unlink(missing_ok=True)
            habia = True
    return habia


def fotos_de_colores(carpeta: str, producto: str, colores: list[str]) -> dict[str, Path]:
    """`{color: ruta}` de los colores de la lista que tienen foto subida."""
    salida: dict[str, Path] = {}
    for c in colores:
        f = ruta_color(carpeta, producto, c)
        if f:
            salida[c] = f
    return salida


def colores_con_foto(carpeta: str) -> dict[str, set[str]]:
    """`{producto: {slug_color…}}` de toda la carpeta, en una lectura."""
    d = _dir(carpeta)
    salida: dict[str, set[str]] = {}
    if not d.is_dir():
        return salida
    for f in d.iterdir():
        if not f.is_file() or f.suffix.lower() not in _EXTS or "__" not in f.stem:
            continue
        producto, _, color = f.stem.partition("__")
        if color.startswith("ref__"):
            continue  # recorte de la miniatura de la ficha, no una foto de color
        salida.setdefault(producto, set()).add(color)
    return salida
