"""Acabado «regalo» del montaje POV BOF / POV BOF Largo (oct 2026).

Para vídeos de producto vendidos como IDEA DE REGALO de Navidad. Sustituye al
bloque de texto de siempre y a la flecha `.mov`:

  - un RÓTULO arriba (cabecera de regalo + nombre del producto + línea que
    SUGIERE mirar los cupones), y
  - una ANIMACIÓN de cierre abajo a la izquierda que acaba en una flecha
    señalando el carrito naranja de TikTok, con su sonido sintetizado.

El dueño lo pidió así: «que no sea siempre lo mismo ni el mismo formato». Por
eso casi todo rota por producto —forma del rótulo, paleta, letra, frase,
emojis, giro, animación y sonido— y con SHA-256 de la semilla, no con `hash()`
de Python (que cambia entre procesos): el mismo producto remontado sale igual
y dos productos seguidos no se parecen.

Lo que NO rota, a propósito:
  - la cabecera nunca promete nada («regalo perfecto», Black Friday, envío,
    fechas): en campaña es lo que más sanciona TikTok Shop;
  - el cupón se SUGIERE («revisa si tienes…»), nunca se afirma («tu cupón»);
    afirmar un cupón que no se puede ver en la ficha ya costó puntos de CRH;
  - el sitio de la flecha: el carrito naranja está siempre en el mismo sitio.

Todo es PIL + numpy + ffmpeg, sin assets nuevos ni nada con derechos.
"""

from __future__ import annotations

import hashlib
import math
import random
import subprocess
import wave
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from src.font_resolver import _bundled_fonts_dir
from src.nicho_pov_bof import config

OnLog = Callable[[str], None]
_noop: OnLog = lambda _msg: None

W, H, FPS = config.TARGET_W, config.TARGET_H, config.TARGET_FPS

# ---------------------------------------------------------------------------
# Variantes
# ---------------------------------------------------------------------------
FORMAS = ("caja", "texto_borde", "cinta", "etiqueta")
ANIMACIONES = ("caja_flecha", "lluvia", "lazo")
SONIDOS = ("pop_estrella_ding", "campanillas", "whoosh_brillo", "carillon")

# Paletas navideñas. Cada una dice cómo se pinta CADA pieza en vez de dar un
# par de colores y dejar que cada forma los combine: en «blanco/rojo» la caja
# es blanca y la letra roja, y con un esquema genérico salía blanco sobre
# blanco.
#   fondo/texto/texto_borde  la caja, cinta o etiqueta y la letra encima
#   marco                    el metal (oro/plata): bordes, lazo, flecha
#   sombra                   el oscuro de contornos y sombras
#   banda/banda_txt          la cabecera cuando va en pastilla
#   fuerte                   el color del borde gordo en «texto_borde»
PALETAS = (
    {"nombre": "rojo_oro", "fondo": (200, 16, 46), "texto": (255, 255, 255),
     "texto_borde": (110, 8, 22), "marco": (255, 206, 64), "marco_osc": (190, 140, 20),
     "sombra": (110, 8, 22), "banda": (22, 120, 60), "banda_txt": (255, 206, 64),
     "fuerte": (200, 16, 46), "confeti": ((255, 206, 64), (255, 255, 255), (230, 40, 60), (60, 190, 100))},
    {"nombre": "verde_oro", "fondo": (20, 110, 56), "texto": (255, 255, 255),
     "texto_borde": (6, 52, 24), "marco": (255, 206, 64), "marco_osc": (190, 140, 20),
     "sombra": (6, 52, 24), "banda": (200, 16, 46), "banda_txt": (255, 236, 160),
     "fuerte": (20, 110, 56), "confeti": ((255, 206, 64), (255, 255, 255), (230, 40, 60), (60, 190, 100))},
    {"nombre": "blanco_rojo", "fondo": (252, 250, 245), "texto": (200, 16, 46),
     "texto_borde": (252, 250, 245), "marco": (200, 16, 46), "marco_osc": (120, 6, 20),
     "sombra": (120, 6, 20), "banda": (200, 16, 46), "banda_txt": (255, 255, 255),
     "fuerte": (200, 16, 46), "confeti": ((230, 30, 55), (255, 255, 255), (255, 206, 64), (40, 150, 80))},
    {"nombre": "azul_plata", "fondo": (16, 34, 82), "texto": (255, 255, 255),
     "texto_borde": (4, 12, 36), "marco": (214, 224, 238), "marco_osc": (130, 145, 172),
     "sombra": (4, 12, 36), "banda": (214, 224, 238), "banda_txt": (16, 34, 82),
     "fuerte": (24, 52, 120), "confeti": ((214, 224, 238), (255, 255, 255), (120, 170, 240), (255, 220, 120))},
    {"nombre": "burdeos_oro", "fondo": (118, 14, 40), "texto": (255, 240, 205),
     "texto_borde": (60, 4, 18), "marco": (240, 196, 80), "marco_osc": (170, 120, 30),
     "sombra": (60, 4, 18), "banda": (250, 240, 215), "banda_txt": (118, 14, 40),
     "fuerte": (150, 20, 52), "confeti": ((240, 196, 80), (255, 245, 225), (200, 40, 70), (90, 170, 110))},
)

# Letras gruesas que llevan tildes, Ñ, ¿ y ¡ (comprobado con el cmap de cada
# una). Las «de cartel» van con mayúsculas; Playfair da el aire de tarjeta.
FUENTES = (
    "LuckiestGuy-Regular.ttf",
    "Bangers-Regular.ttf",
    "Rubik-Bold.ttf",
    "Fredoka-SemiBold.ttf",
    "PlayfairDisplay-Black.ttf",
    "Montserrat-Black.ttf",
)
_FUENTE_CUPON = "Montserrat-Black.ttf"   # la línea pequeña tiene que leerse sí o sí

# Cabeceras: hablan de la ocasión, no del producto ni del precio. Nada de
# «regalo perfecto» (promesa), ofertas, Black Friday, envío ni fechas.
FRASES = (
    "IDEA DE REGALO",
    "IDEA DE REGALO DE NAVIDAD",
    "¿NO SABES QUÉ REGALAR?",
    "UN DETALLE QUE SIRVE",
    "PARA REGALAR ESTAS NAVIDADES",
    "PARA REGALAR EN NAVIDAD",
)
# Sugerir, nunca afirmar: «tu cupón» da por hecho algo que no se ve en la ficha.
CUPONES = (
    "REVISA SI TIENES CUPÓN DE DESCUENTO",
    "MIRA SI TIENES CUPONES",
)
EMOJIS = ("🎁", "🎄", "✨", "⭐")
# Grados. Poco: es para que no parezca una plantilla, no para que se lea torcido.
GIROS = (-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0)

# La flecha señala el carrito naranja que pinta TikTok abajo a la izquierda
# (centro de la flecha, ya apuntando hacia abajo). Medido sobre capturas.
DIANA = (int(W * 0.18), int(H * 0.775))
# La animación vive en la mitad de abajo: el producto está en el centro y no
# se le pasa nada por encima. El lienzo es más pequeño y el pipe va el doble
# de rápido.
REG_Y0 = int(H * 0.50)
REG_H = H - REG_Y0


def elegir_variante(semilla: str) -> dict:
    """Combinación de este producto. Determinista: SHA-256 y un byte distinto
    para cada eje, así no salen correlacionados (con un único índice la misma
    forma arrastraba siempre la misma paleta)."""
    h = hashlib.sha256(f"regalo|{semilla}".encode("utf-8")).digest()

    def toma(i: int, opciones):
        return opciones[h[i] % len(opciones)]

    forma = toma(0, FORMAS)
    e1 = toma(6, EMOJIS)
    resto = [e for e in EMOJIS if e != e1]
    e2 = resto[h[7] % len(resto)]
    giro = toma(8, GIROS)
    if forma == "etiqueta":
        # La etiqueta cuelga: inclinada se ve más de verdad (siempre 4-6°).
        giro = (4.0 + (h[9] % 3)) * (1 if h[10] % 2 else -1)
    elif forma == "cinta":
        # La cinta va de lado a lado: girada se le cortan las puntas.
        giro = 0.0
    return {
        "forma": forma,
        "paleta": toma(1, PALETAS),
        "fuente": toma(2, FUENTES),
        "frase": toma(3, FRASES),
        "cupon": toma(4, CUPONES),
        "anim": toma(5, ANIMACIONES),
        "sonido": toma(11, SONIDOS),
        "emojis": (e1, e2),
        "giro": giro,
    }


def describir(v: dict) -> str:
    return (
        f"forma={v['forma']} paleta={v['paleta']['nombre']} "
        f"fuente={v['fuente'].rsplit('.', 1)[0]} anim={v['anim']} sonido={v['sonido']}"
    )


# ---------------------------------------------------------------------------
# Utilidades de dibujo
# ---------------------------------------------------------------------------
def _fuente(nombre: str, tam: int) -> ImageFont.FreeTypeFont:
    p = Path(_bundled_fonts_dir()) / nombre
    if not p.exists():
        p = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    return ImageFont.truetype(str(p), int(tam))


_EMOJI_CACHE: dict[tuple[str, int], Image.Image] = {}


def _emoji(ch: str, tam: int) -> Image.Image | None:
    """Emoji en color (Noto solo se carga a 109 px; se pinta y se escala)."""
    k = (ch, tam)
    if k in _EMOJI_CACHE:
        return _EMOJI_CACHE[k]
    try:
        f = _fuente("NotoColorEmoji.ttf", 109)
        im = Image.new("RGBA", (160, 160))
        ImageDraw.Draw(im).text((10, 10), ch, font=f, embedded_color=True)
        bb = im.getbbox()
        if not bb:
            return None
        im = im.crop(bb).resize((tam, tam), Image.LANCZOS)
    except Exception:  # noqa: BLE001 — un emoji es adorno, nunca rompe el rótulo
        return None
    _EMOJI_CACHE[k] = im
    return im


def _ancho(d: ImageDraw.ImageDraw, txt: str, f, borde: int = 0) -> float:
    return d.textlength(txt, font=f) + 2 * borde


def _alto(f) -> int:
    a, b = f.getmetrics()
    return a + b


def _ajustar(txt: str, fuente: str, max_w: int, tam_max: int, tam_min: int,
             borde_frac: float = 0.0, dos_lineas: bool = True):
    """(líneas, fuente) con la letra más grande que cabe en `max_w`.

    Primero en UNA línea sin bajar demasiado; si no entra, en dos repartidas
    por ancho (no por número de palabras: «3 GNOMOS / SUECOS CON LUZ» queda
    cojo). Si ni así, el mínimo — y el rótulo entero se escala al final.
    """
    d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    palabras = txt.split()
    umbral_una = int(tam_max * 0.78)
    for tam in range(tam_max, umbral_una - 1, -2):
        f = _fuente(fuente, tam)
        if _ancho(d, txt, f, int(tam * borde_frac)) <= max_w:
            return [txt], f
    if not dos_lineas or len(palabras) < 2:
        for tam in range(umbral_una, tam_min - 1, -2):
            f = _fuente(fuente, tam)
            if _ancho(d, txt, f, int(tam * borde_frac)) <= max_w:
                return [txt], f
        return [txt], _fuente(fuente, tam_min)
    for tam in range(int(tam_max * 0.92), tam_min - 1, -2):
        f = _fuente(fuente, tam)
        b = int(tam * borde_frac)
        mejor = None
        for i in range(1, len(palabras)):
            l1, l2 = " ".join(palabras[:i]), " ".join(palabras[i:])
            w = max(_ancho(d, l1, f, b), _ancho(d, l2, f, b))
            if mejor is None or w < mejor[0]:
                mejor = (w, [l1, l2])
        if mejor and mejor[0] <= max_w:
            return mejor[1], f
    f = _fuente(fuente, tam_min)
    mejor = min(
        ([" ".join(palabras[:i]), " ".join(palabras[i:])] for i in range(1, len(palabras))),
        key=lambda ls: max(_ancho(d, x, f) for x in ls),
    )
    return mejor, f


def _texto_c(d, cx, cy, txt, f, fill, borde=0, borde_color=(0, 0, 0)):
    """Texto centrado de verdad en (cx, cy) por su caja de tinta, no por la
    línea base: Luckiest Guy y Bangers tienen métricas muy distintas y con
    `anchor="mm"` una quedaba alta y la otra baja dentro de la caja."""
    bb = d.textbbox((0, 0), txt, font=f, stroke_width=borde)
    x = cx - (bb[0] + bb[2]) / 2
    y = cy - (bb[1] + bb[3]) / 2
    d.text((x, y), txt, font=f, fill=fill, stroke_width=borde, stroke_fill=borde_color)


def _alto_tinta(d, txt, f, borde=0) -> int:
    bb = d.textbbox((0, 0), txt, font=f, stroke_width=borde)
    return bb[3] - bb[1]


def _sombra(im: Image.Image, radio: int = 8, alfa: int = 120, off=(6, 9)) -> Image.Image:
    """La silueta del dibujo, difuminada y desplazada, debajo de él."""
    a = im.getchannel("A").point(lambda v: min(alfa, v))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    sh.putalpha(a)
    sh = sh.filter(ImageFilter.GaussianBlur(radio))
    out = Image.new("RGBA", (im.width + off[0] + radio, im.height + off[1] + radio))
    out.alpha_composite(sh, off)
    out.alpha_composite(im, (0, 0))
    return out


def _lazo(ancho: int, pal: dict, colas: bool = True) -> Image.Image:
    """Lazo de regalo visto de frente: dos lazadas, dos colas y el nudo."""
    w = ancho
    h = int(ancho * 0.62)
    im = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(im)
    oro, osc = pal["marco"], pal["marco_osc"]
    cx, cy = w / 2, h * 0.42
    g = max(4, w // 40)
    if colas:
        d.polygon([(cx - 8, cy), (cx - w * 0.30, h - 2), (cx - w * 0.16, h - w * 0.06)], fill=oro, outline=osc)
        d.polygon([(cx + 8, cy), (cx + w * 0.30, h - 2), (cx + w * 0.16, h - w * 0.06)], fill=oro, outline=osc)
    # lazadas
    for x0b, x1b in ((2, cx - 4), (cx + 4, w - 2)):
        d.ellipse((x0b, cy - h * 0.38, x1b, cy + h * 0.30), fill=oro, outline=osc, width=g)
        d.ellipse((x0b + w * 0.09, cy - h * 0.17, x1b - w * 0.09, cy + h * 0.10), fill=osc)
    r = w * 0.10
    d.ellipse((cx - r, cy - r * 0.9, cx + r, cy + r * 0.9), fill=oro, outline=osc, width=g)
    return im


# ---------------------------------------------------------------------------
# Rótulo
# ---------------------------------------------------------------------------
_MAX_W = W - 160          # el rótulo entero, emojis incluidos
_MAX_H = int(H * 0.22)    # de 0.15 a ~0.37: no baja hasta el producto


def nombre_seguro(textos: dict, on_log: OnLog = _noop) -> str:
    """Nombre del producto para el rótulo, pasado por el filtro de términos
    arriesgados del montaje. Si cae alguno («barato», «oferta» metidos en el
    nombre de la ficha), se quitan esas palabras en vez de quitar el nombre:
    el nombre en pantalla es lo que demuestra que el vídeo es de ESE producto.
    """
    from src.nicho_pov_bof.pipeline import video_editor as ve

    nombre = " ".join(ve._titulo_para_video(textos or {}).split())
    riesgo = ve.texto_arriesgado(nombre)
    if not riesgo:
        return nombre
    termino = riesgo.split(" ")[0]
    limpio = " ".join(p for p in nombre.split() if termino not in ve._sin_acentos(p))
    if ve.texto_arriesgado(limpio):
        limpio = ""
    return ve._texto_seguro(nombre, limpio, "nombre (regalo)", on_log)


def render_rotulo(textos: dict, variante: dict, on_log: OnLog = _noop,
                  piezas: "set[str] | None" = None) -> Image.Image | None:
    """Rótulo de regalo (RGBA, ≤ 1080 de ancho). `piezas` como en el bloque de
    siempre: gancho → cabecera, titulo → nombre, cta → línea del cupón."""
    quiere = piezas if piezas is not None else {"gancho", "titulo", "cta"}
    nombre = nombre_seguro(textos, on_log).upper() if "titulo" in quiere else ""
    frase = variante["frase"] if "gancho" in quiere else ""
    cupon = variante["cupon"] if "cta" in quiere else ""
    if not (nombre or frase or cupon):
        return None
    pintor = {
        "caja": _rotulo_caja, "texto_borde": _rotulo_borde,
        "cinta": _rotulo_cinta, "etiqueta": _rotulo_etiqueta,
    }[variante["forma"]]
    im = pintor(nombre, frase, cupon, variante)
    im = im.crop(im.getbbox()) if im.getbbox() else im
    giro = variante.get("giro") or 0.0
    if giro:
        im = im.rotate(giro, expand=True, resample=Image.BICUBIC)
    # La cinta va de lado a lado a propósito: se recorta al ancho del vídeo.
    if variante["forma"] == "cinta" and im.width > W:
        x = (im.width - W) // 2
        im = im.crop((x, 0, x + W, im.height))
    tope_w = W if variante["forma"] == "cinta" else _MAX_W
    k = min(1.0, tope_w / im.width, _MAX_H / im.height)
    if k < 1.0:
        im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
    return im


def _linea_cupon(cupon: str, pal: dict, max_w: int, estilo: str) -> Image.Image | None:
    if not cupon:
        return None
    lineas, f = _ajustar(cupon, _FUENTE_CUPON, max_w - 80, 32, 22, dos_lineas=False)
    d0 = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    tw = _ancho(d0, lineas[0], f)
    th = _alto_tinta(d0, lineas[0], f)
    if estilo == "pastilla":
        im = Image.new("RGBA", (int(tw + 80), th + 30))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, im.width - 1, im.height - 1), im.height // 2,
                            fill=pal["marco"], outline=pal["sombra"], width=3)
        _texto_c(d, im.width / 2, im.height / 2, lineas[0], f, pal["sombra"])
        return im
    # «suelta»: solo letra blanca con borde, para los rótulos sin cajas.
    b = max(3, f.size // 8)
    im = Image.new("RGBA", (int(tw + 2 * b + 10), th + 2 * b + 14))
    d = ImageDraw.Draw(im)
    _texto_c(d, im.width / 2, im.height / 2, lineas[0], f, (255, 255, 255), b, pal["sombra"])
    return im


def _apilar(piezas: list[tuple[Image.Image, int]], ancho: int) -> Image.Image:
    """Pega las piezas una debajo de otra, centradas; el entero es el hueco
    (negativo = se montan, como la pastilla que pisa el borde de la caja)."""
    alto = sum(p.height + g for p, g in piezas)
    im = Image.new("RGBA", (ancho, max(1, alto + 40)))
    y = 0
    for p, g in piezas:
        im.alpha_composite(p, ((ancho - p.width) // 2, max(0, y)))
        y += p.height + g
    return im


def _rotulo_caja(nombre, frase, cupon, v) -> Image.Image:
    """El del prototipo: pastilla de cabecera, caja con el nombre y etiqueta
    de cupón debajo; un emoji a cada lado de la caja."""
    pal, fuente = v["paleta"], v["fuente"]
    piezas: list[tuple[Image.Image, int]] = []
    d0 = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    if frase:
        lin, f = _ajustar(frase, fuente, _MAX_W - 160, 42, 28, dos_lineas=False)
        tw, th = _ancho(d0, lin[0], f), _alto_tinta(d0, lin[0], f)
        p = Image.new("RGBA", (int(tw + 64), th + 28))
        d = ImageDraw.Draw(p)
        d.rounded_rectangle((0, 0, p.width - 1, p.height - 1), p.height // 2,
                            fill=pal["banda"], outline=pal["marco"], width=4)
        _texto_c(d, p.width / 2, p.height / 2, lin[0], f, pal["banda_txt"])
        piezas.append((p, 8))
    if nombre:
        caja_max = _MAX_W - 70          # sitio para que los emojis asomen
        lin, f = _ajustar(nombre, fuente, caja_max - 80, 70, 40, borde_frac=0.05)
        b = max(2, f.size // 20)
        lh = int(_alto(f) * 0.92)
        tw = max(_ancho(d0, l, f, b) for l in lin)
        bw, bh = int(tw + 80), int(lh * len(lin) + 34)
        c = Image.new("RGBA", (bw, bh))
        d = ImageDraw.Draw(c)
        d.rounded_rectangle((0, 0, bw - 1, bh - 1), 30, fill=pal["fondo"],
                            outline=pal["marco"], width=6)
        y = 17 + lh / 2
        for l in lin:
            _texto_c(d, bw / 2, y, l, f, pal["texto"], b, pal["texto_borde"])
            y += lh
        c = _sombra(c)
        # emojis a los lados, medio fuera de la caja
        es = min(84, int(bh * 0.62))
        ancho = bw + es
        cc = Image.new("RGBA", (ancho, c.height))
        cc.alpha_composite(c, (es // 2, 0))
        for i, ch in enumerate(v["emojis"]):
            e = _emoji(ch, es)
            if e is not None:
                x = 0 if i == 0 else ancho - es
                cc.alpha_composite(e, (x, max(0, (bh - es) // 2)))
        piezas.append((cc, 10))
    cup = _linea_cupon(cupon, pal, _MAX_W - 100, "pastilla")
    if cup is not None:
        piezas.append((cup, 0))
    return _apilar(piezas, W)


def _rotulo_borde(nombre, frase, cupon, v) -> Image.Image:
    """Solo letra: el nombre grande con borde doble (color fuerte + oscuro) y
    sombra, sin caja ni fondo. Es el que menos tapa."""
    pal, fuente = v["paleta"], v["fuente"]
    piezas: list[tuple[Image.Image, int]] = []
    d0 = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    if frase:
        es = 52
        lin, f = _ajustar(frase, fuente, _MAX_W - 2 * es - 40, 50, 30, borde_frac=0.12,
                          dos_lineas=False)
        b = max(3, f.size // 9)
        tw, th = _ancho(d0, lin[0], f, b), _alto_tinta(d0, lin[0], f, b)
        p = Image.new("RGBA", (int(tw + 2 * es + 30), max(th, es) + 12))
        d = ImageDraw.Draw(p)
        # Sin caja detrás, un marco oscuro (el rojo del blanco_rojo) no se lee
        # sobre un fondo oscuro: entonces la frase va en blanco.
        r, g, bl = pal["marco"][:3]
        claro = 0.299 * r + 0.587 * g + 0.114 * bl > 150
        _texto_c(d, p.width / 2, p.height / 2, lin[0], f,
                 pal["marco"] if claro else (255, 255, 255), b, pal["sombra"])
        for i, ch in enumerate(v["emojis"]):
            e = _emoji(ch, es)
            if e is not None:
                p.alpha_composite(e, (0 if i == 0 else p.width - es, (p.height - es) // 2))
        piezas.append((_sombra(p, 6, 110, (4, 6)), 0))
    if nombre:
        lin, f = _ajustar(nombre, fuente, _MAX_W - 20, 88, 46, borde_frac=0.22)
        b_ext = max(6, int(f.size * 0.16))
        b_int = max(3, int(f.size * 0.08))
        lh = int(_alto(f) * 0.95)
        tw = max(_ancho(d0, l, f, b_ext) for l in lin)
        p = Image.new("RGBA", (int(tw + 20), int(lh * len(lin) + 2 * b_ext)))
        d = ImageDraw.Draw(p)
        y = b_ext + lh / 2
        for l in lin:
            # Dos pasadas: el borde gordo oscuro debajo y el de color encima.
            _texto_c(d, p.width / 2, y, l, f, pal["sombra"], b_ext, pal["sombra"])
            _texto_c(d, p.width / 2, y, l, f, (255, 255, 255), b_int, pal["fuerte"])
            y += lh
        piezas.append((_sombra(p, 8, 130, (5, 8)), 2))
    cup = _linea_cupon(cupon, pal, _MAX_W, "suelta")
    if cup is not None:
        piezas.append((cup, 0))
    return _apilar(piezas, W)


def _rotulo_cinta(nombre, frase, cupon, v) -> Image.Image:
    """Cinta de regalo de lado a lado con el nombre dentro y un lazo encima,
    la cabecera en letra suelta y el cupón en pastilla debajo."""
    pal, fuente = v["paleta"], v["fuente"]
    d0 = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    piezas: list[tuple[Image.Image, int]] = []
    if frase:
        lin, f = _ajustar(frase, fuente, _MAX_W - 120, 46, 28, borde_frac=0.12,
                          dos_lineas=False)
        b = max(3, f.size // 9)
        th = _alto_tinta(d0, lin[0], f, b)
        es = 46
        tw = _ancho(d0, lin[0], f, b)
        p = Image.new("RGBA", (int(tw + 2 * es + 30), max(th, es) + 10))
        d = ImageDraw.Draw(p)
        _texto_c(d, p.width / 2, p.height / 2, lin[0], f, pal["marco"], b, pal["sombra"])
        e = _emoji(v["emojis"][0], es)
        if e is not None:
            p.alpha_composite(e, (0, (p.height - es) // 2))
            p.alpha_composite(e, (p.width - es, (p.height - es) // 2))
        piezas.append((p, 2))
    # Sin colas y centrado en el borde de arriba: con colas, o a un lado,
    # tapaba la última palabra del nombre.
    lazo_w = 170
    lazo = _lazo(lazo_w, pal, colas=False)
    nudo = int(lazo.height * 0.42)         # alto del centro del nudo en el sprite
    pisa = int(lazo.height * 0.34)         # lo que las lazadas bajan dentro de la cinta
    if nombre:
        lin, f = _ajustar(nombre, fuente, _MAX_W - 40, 70, 40, borde_frac=0.05)
        b = max(2, f.size // 20)
        lh = int(_alto(f) * 0.92)
        cinta_h = int(lh * len(lin) + 44 + pisa)
        top = nudo
        c = Image.new("RGBA", (W + 40, top + cinta_h))
        d = ImageDraw.Draw(c)
        x0, x1, y0, y1 = 0, c.width, top, top + cinta_h
        mid = (y0 + y1) / 2
        muesca = 34                        # cola de golondrina en las puntas
        d.polygon([(x0, y0), (x1, y0), (x1 - muesca, mid), (x1, y1), (x0, y1), (x0 + muesca, mid)],
                  fill=pal["fondo"])
        # ribete metálico arriba y abajo, como las cintas de verdad
        d.rectangle((x0, y0 + 7, x1, y0 + 13), fill=pal["marco"])
        d.rectangle((x0, y1 - 13, x1, y1 - 7), fill=pal["marco"])
        y = y0 + 22 + pisa + lh / 2
        for l in lin:
            _texto_c(d, c.width / 2, y, l, f, pal["texto"], b, pal["texto_borde"])
            y += lh
        c = _sombra(c, 8, 110, (0, 8))
        c.alpha_composite(lazo, (c.width // 2 - lazo_w // 2, 0))
        piezas.append((c, 6))
    else:
        piezas.append((lazo, 6))
    cup = _linea_cupon(cupon, pal, _MAX_W - 100, "pastilla")
    if cup is not None:
        piezas.append((cup, 0))
    return _apilar(piezas, W + 40)


def _rotulo_etiqueta(nombre, frase, cupon, v) -> Image.Image:
    """Etiqueta de regalo colgada de un cordel: punta a la izquierda con su
    agujero, borde metálico y una línea de puntadas por dentro."""
    pal, fuente = v["paleta"], v["fuente"]
    d0 = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    punta = 80
    max_txt = _MAX_W - punta - 90
    filas: list[tuple[str, ImageFont.FreeTypeFont, tuple, int, tuple]] = []
    if frase:
        lin, f = _ajustar(frase, fuente, max_txt, 40, 26, dos_lineas=False)
        filas.append((lin[0], f, pal["marco"] if pal["nombre"] != "blanco_rojo" else pal["sombra"], 0, pal["sombra"]))
    if nombre:
        lin, f = _ajustar(nombre, fuente, max_txt, 66, 38, borde_frac=0.05)
        b = max(2, f.size // 20)
        for l in lin:
            filas.append((l, f, pal["texto"], b, pal["texto_borde"]))
    if cupon:
        lin, f = _ajustar(cupon, _FUENTE_CUPON, max_txt, 28, 20, dos_lineas=False)
        filas.append((lin[0], f, pal["marco"] if pal["nombre"] != "blanco_rojo" else pal["sombra"], 0, pal["sombra"]))
    altos = [int(_alto(f) * 0.95) for _, f, _, _, _ in filas]
    tw = max(_ancho(d0, t, f, b) for t, f, _, b, _ in filas)
    ew, eh = int(tw + punta + 90), int(sum(altos) + 56)
    cuerda = 70
    im = Image.new("RGBA", (ew + 20, eh + cuerda + 20))
    d = ImageDraw.Draw(im)
    y0, y1 = cuerda, cuerda + eh
    mid = (y0 + y1) / 2
    forma = [(punta, y0), (ew, y0), (ew, y1), (punta, y1), (6, mid)]
    d.polygon(forma, fill=pal["fondo"])
    d.line(forma + [forma[0]], fill=pal["marco"], width=7, joint="curve")
    # puntadas por dentro
    ins = 16
    interior = [(punta + 6, y0 + ins), (ew - ins, y0 + ins), (ew - ins, y1 - ins),
                (punta + 6, y1 - ins), (6 + ins + 8, mid)]
    for (ax, ay), (bx, by) in zip(interior, interior[1:] + interior[:1]):
        n = max(1, int(math.hypot(bx - ax, by - ay) // 22))
        for i in range(0, n, 2):
            t0, t1 = i / n, min(1, (i + 1) / n)
            d.line((ax + (bx - ax) * t0, ay + (by - ay) * t0, ax + (bx - ax) * t1, ay + (by - ay) * t1),
                   fill=pal["marco"], width=3)
    # agujero con su arandela y el cordel que sube
    hx, hy = punta - 6, mid
    d.ellipse((hx - 16, hy - 16, hx + 16, hy + 16), fill=pal["marco"])
    d.ellipse((hx - 8, hy - 8, hx + 8, hy + 8), fill=(0, 0, 0, 0))
    pts = [(hx, hy - 8)]
    for i in range(1, 13):
        t = i / 12
        pts.append((hx + 60 * t + 20 * math.sin(t * math.pi), hy - 8 - (hy - 8) * t))
    d.line(pts, fill=pal["marco_osc"], width=5, joint="curve")
    # filas de texto
    cx = punta + (ew - punta) / 2
    y = y0 + 28
    for (t, f, col, b, bc), a in zip(filas, altos):
        _texto_c(d, cx, y + a / 2, t, f, col, b, bc)
        y += a
    e = _emoji(v["emojis"][0], 64)
    if e is not None:
        im.alpha_composite(e, (ew - 50, max(0, y0 - 40)))
    return _sombra(im)


# ---------------------------------------------------------------------------
# Animación de cierre
# ---------------------------------------------------------------------------
def _ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def _rebote(x: float) -> float:
    """easeOutBounce: cae y rebota dos veces, cada vez menos."""
    x = max(0.0, min(1.0, x))
    n, dd = 7.5625, 2.75
    if x < 1 / dd:
        return n * x * x
    if x < 2 / dd:
        x -= 1.5 / dd
        return n * x * x + 0.75
    if x < 2.5 / dd:
        x -= 2.25 / dd
        return n * x * x + 0.9375
    x -= 2.625 / dd
    return n * x * x + 0.984375


def _flecha(pal: dict, largo: int = 300) -> Image.Image:
    """Flecha gorda apuntando a la DERECHA (se gira al pegar)."""
    im = Image.new("RGBA", (largo + 20, 200))
    d = ImageDraw.Draw(im)
    L = largo
    pts = [(10, 70), (L - 90, 70), (L - 90, 20), (L + 10, 100), (L - 90, 180), (L - 90, 130), (10, 130)]
    d.polygon(pts, fill=pal["marco"])
    d.line(pts + [pts[0]], fill=pal["sombra"], width=10, joint="curve")
    return im


def _estrella(r: int, col) -> Image.Image:
    im = Image.new("RGBA", (2 * r + 2, 2 * r + 2))
    d = ImageDraw.Draw(im)
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((r + 1 + rr * math.cos(a), r + 1 + rr * math.sin(a)))
    d.polygon(pts, fill=col)
    return im


def _copo(r: int, col) -> Image.Image:
    im = Image.new("RGBA", (2 * r + 2, 2 * r + 2))
    d = ImageDraw.Draw(im)
    c = r + 1
    for i in range(6):
        a = i * math.pi / 3
        x, y = c + r * math.cos(a), c + r * math.sin(a)
        d.line((c, c, x, y), fill=col, width=max(2, r // 5))
        for s in (-1, 1):
            b = a + s * 0.6
            mx, my = c + r * 0.6 * math.cos(a), c + r * 0.6 * math.sin(a)
            d.line((mx, my, mx + r * 0.3 * math.cos(b), my + r * 0.3 * math.sin(b)),
                   fill=col, width=max(2, r // 6))
    return im


def _con_alfa(im: Image.Image, k: float) -> Image.Image:
    if k >= 0.999:
        return im
    out = im.copy()
    out.putalpha(im.getchannel("A").point(lambda a: int(a * max(0.0, k))))
    return out


class _Animador:
    """Pinta los fotogramas de la animación (lienzo de la mitad de abajo).

    `t` es el tiempo desde el arranque. Cada animación acaba con la flecha
    quieta señalando la diana y un leve rebote hasta el final del vídeo. Las
    piezas (flecha ya girada, caja, tapa, partículas) se precalculan: lo que
    se hace por fotograma es pegar sprites pequeños sobre un lienzo vacío.
    """

    FL_K = 0.5

    def __init__(self, variante: dict, semilla: str):
        self.v = variante
        self.pal = variante["paleta"]
        self.rnd = random.Random(hashlib.sha256(f"anim|{semilla}".encode()).hexdigest())
        self.flecha = _flecha(self.pal)
        fs = self.flecha.resize((int(self.flecha.width * self.FL_K), int(self.flecha.height * self.FL_K)),
                                Image.LANCZOS)
        self.flecha_abajo = fs.rotate(-90, expand=True, resample=Image.BICUBIC)
        self.dx, self.dy = DIANA[0], DIANA[1] - REG_Y0
        getattr(self, f"_prep_{variante['anim']}")()

    # --- utilidades ---------------------------------------------------------
    def _pega(self, lienzo, im, cx, cy):
        lienzo.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))

    def _flecha_en(self, lienzo, cx, cy, ang_deg, escala):
        sc = escala * self.FL_K
        fl = self.flecha.resize((max(1, int(self.flecha.width * sc)), max(1, int(self.flecha.height * sc))))
        fl = fl.rotate(-ang_deg, expand=True, resample=Image.BICUBIC)
        self._pega(lienzo, fl, cx, cy)

    def _flecha_quieta(self, lienzo, t_desde):
        self._pega(lienzo, self.flecha_abajo, self.dx, self.dy + 9 * math.sin(t_desde * 7))

    @property
    def fin_movimiento(self) -> float:
        """A partir de aquí solo se mueve la flecha (rebote)."""
        return {"caja_flecha": 1.95, "lluvia": 2.8, "lazo": 2.6}[self.v["anim"]]

    def fotograma(self, t: float) -> Image.Image:
        lienzo = Image.new("RGBA", (W, REG_H))
        getattr(self, f"_pinta_{self.v['anim']}")(lienzo, t)
        return lienzo

    # --- caja_flecha (el prototipo aprobado) ---------------------------------
    def _prep_caja_flecha(self):
        pal = self.pal
        BS = 260
        c = Image.new("RGBA", (BS, BS))
        d = ImageDraw.Draw(c)
        d.rounded_rectangle((0, 0, BS - 1, BS - 1), 18, fill=pal["fondo"], outline=pal["sombra"], width=6)
        d.rectangle((BS / 2 - 22, 0, BS / 2 + 22, BS), fill=pal["marco"])
        d.rectangle((0, BS * 0.42, BS, BS * 0.42 + 40), fill=pal["marco"])
        w, h = int(BS * 1.16), 64
        tp = Image.new("RGBA", (w, h + 110))
        d = ImageDraw.Draw(tp)
        d.rounded_rectangle((0, 110, w - 1, 110 + h), 14, fill=pal["fondo"], outline=pal["sombra"], width=6)
        d.rectangle((w / 2 - 24, 110, w / 2 + 24, 110 + h), fill=pal["marco"])
        lz = _lazo(200, pal)
        tp.alpha_composite(lz, (int(w / 2 - 100), 112 - int(lz.height * 0.62)))
        self.bs = 110
        k = self.bs / BS
        self.k = k
        self.caja = c.resize((self.bs, self.bs), Image.LANCZOS)
        self.tapa = tp.resize((int(tp.width * k), int(tp.height * k)), Image.LANCZOS)
        self.bx, self.by = int(W * 0.30), int(H * 0.80) - REG_Y0
        cols = self.pal["confeti"]
        self.chispas = [(self.rnd.uniform(0, 2 * math.pi), self.rnd.uniform(300, 700),
                         self.rnd.choice(cols), self.rnd.uniform(6, 14)) for _ in range(45)]

    def _pinta_caja_flecha(self, fr, t):
        u = t * 1.8
        if u < 0.45:
            y = self.by - 250 * (1 - _ease(u / 0.45))
        else:
            y = self.by + (-12 * math.sin((u - 0.45) * 14) * math.exp(-(u - 0.45) * 6) if u < 1.0 else 0)
        ang = 7 * math.sin(u * 40) if 0.55 < u < 1.05 else 0
        abre = u - 1.1
        # La caja se desvanece cuando la flecha ya ha llegado: si se queda,
        # tapa el carrito de TikTok, que está justo debajo.
        k_caja = 1.0 if abre < 1.6 else max(0.0, 1 - (abre - 1.6) / 0.5)
        if k_caja > 0:
            c = self.caja.rotate(ang, expand=True, resample=Image.BICUBIC) if ang else self.caja
            self._pega(fr, _con_alfa(c, k_caja), self.bx, y)
        top = int(y) - self.bs // 2
        if abre < 0:
            tp = self.tapa.rotate(ang, expand=True, resample=Image.BICUBIC) if ang else self.tapa
            fr.alpha_composite(tp, (self.bx - tp.width // 2, top - tp.height + int(68 * self.k)))
            return
        if abre < 0.7:
            k = _ease(abre / 0.7)
            tp = _con_alfa(self.tapa.rotate(-60 * k, expand=True, resample=Image.BICUBIC), 1 - k)
            fr.alpha_composite(tp, (int(self.bx + 70 * k - tp.width / 2),
                                    int(top - tp.height + 68 * self.k - 110 * k)))
        d = ImageDraw.Draw(fr)
        if abre < 1.2:
            al = int(200 * (1 - abre / 1.2))
            for i in range(12):
                a = i * math.pi / 6 + abre
                r1, r2 = 30 + 80 * _ease(abre / 0.5), 50 + 150 * _ease(abre / 0.6)
                d.line((self.bx + r1 * math.cos(a), top + r1 * math.sin(a),
                        self.bx + r2 * math.cos(a), top + r2 * math.sin(a)),
                       fill=self.pal["marco"] + (al,), width=4)
        if abre < 1.6:
            for a, v, col, r in self.chispas:
                px = self.bx + math.cos(a) * v * abre * 0.4
                py = top + math.sin(a) * v * abre * 0.32 + 150 * abre * abre
                al = int(255 * (1 - abre / 1.6))
                r *= 0.5
                d.ellipse((px - r, py - r, px + r, py + r), fill=col + (al,))
        fa = abre - 0.15
        if fa < 0:
            return
        if fa >= 0.9:
            self._flecha_quieta(fr, fa - 0.9)
            return
        k = _ease(fa / 0.9)
        p0 = (self.bx, top - 20)
        cx = p0[0] + (self.dx - p0[0]) * k
        cy = p0[1] + (self.dy - p0[1]) * k - 110 * math.sin(math.pi * k)
        self._flecha_en(fr, cx, cy, -90 - 180 * k, 0.3 + 0.7 * _ease(fa / 0.4))

    # --- lluvia: copos y estrellas + flecha que cae con rebote ---------------
    def _prep_lluvia(self):
        cols = self.pal["confeti"]
        self.copos = []
        for _ in range(42):
            r = self.rnd.randint(9, 20)
            spr = (_estrella(r, self.rnd.choice(cols)) if self.rnd.random() < 0.5
                   else _copo(r, (255, 255, 255)))
            self.copos.append((spr, self.rnd.uniform(0, W), self.rnd.uniform(-REG_H * 0.6, 0),
                               self.rnd.uniform(260, 520), self.rnd.uniform(0, 6.28),
                               self.rnd.uniform(18, 50), self.rnd.uniform(-90, 90)))
        self.brillos = [(self.rnd.uniform(0, 2 * math.pi), self.rnd.uniform(140, 320),
                         self.rnd.choice(cols)) for _ in range(26)]

    def _pinta_lluvia(self, fr, t):
        if t < 2.8:
            alfa = min(1.0, t / 0.3) * (1.0 if t < 2.2 else max(0.0, 1 - (t - 2.2) / 0.6))
            for spr, x0, y0, vel, fase, amp, giro in self.copos:
                y = y0 + vel * t
                if y < -30 or y > REG_H + 30:
                    continue
                x = x0 + amp * math.sin(t * 2.2 + fase)
                # Arriba del lienzo entran fundidos: no se ve el corte del borde.
                k = alfa * min(1.0, max(0.0, y / 120))
                s = spr.rotate(giro * t, resample=Image.BICUBIC) if giro else spr
                self._pega(fr, _con_alfa(s, k), x, y)
        # flecha: cae desde arriba girada hacia abajo con rebote
        fa = t - 0.55
        if fa < 0:
            return
        dur = 0.8
        if fa >= dur:
            # brillo al aterrizar
            ab = fa - dur
            if ab < 0.8:
                d = ImageDraw.Draw(fr)
                for a, v, col in self.brillos:
                    r = 5
                    px = self.dx + math.cos(a) * v * _ease(ab / 0.8)
                    py = self.dy + 40 + math.sin(a) * v * 0.6 * _ease(ab / 0.8)
                    d.ellipse((px - r, py - r, px + r, py + r), fill=col + (int(255 * (1 - ab / 0.8)),))
            self._flecha_quieta(fr, ab)
            return
        k = _rebote(fa / dur)
        y = (self.dy - 380) + 380 * k
        self._flecha_en(fr, self.dx, y, 90, 0.6 + 0.4 * min(1.0, fa / 0.3))

    # --- lazo: aparece, se agita, estalla en confeti y deja la flecha --------
    def _prep_lazo(self):
        self.lazo = _lazo(230, self.pal)
        self.lx, self.ly = int(W * 0.30), int(H * 0.79) - REG_Y0
        cols = self.pal["confeti"]
        self.confeti = []
        for _ in range(60):
            w, h = self.rnd.randint(8, 16), self.rnd.randint(14, 26)
            pz = Image.new("RGBA", (w, h), self.rnd.choice(cols) + (255,))
            self.confeti.append((pz, self.rnd.uniform(0, 2 * math.pi), self.rnd.uniform(250, 650),
                                 self.rnd.uniform(-400, 400)))
        mitad = self.lazo.width // 2
        self.lazada_i = self.lazo.crop((0, 0, mitad, self.lazo.height))
        self.lazada_d = self.lazo.crop((mitad, 0, self.lazo.width, self.lazo.height))

    def _pinta_lazo(self, fr, t):
        x, y = self.lx, self.ly
        if t < 0.9:
            if t < 0.35:
                sc = 1.12 * _ease(t / 0.35)
            else:
                sc = 1.0 + 0.12 * math.exp(-(t - 0.35) * 8)
            ang = 9 * math.sin(t * 34) if t > 0.4 else 0
            lz = self.lazo.resize((max(1, int(self.lazo.width * sc)), max(1, int(self.lazo.height * sc))))
            if ang:
                lz = lz.rotate(ang, expand=True, resample=Image.BICUBIC)
            self._pega(fr, lz, x, y)
            return
        e = t - 0.9
        # las dos lazadas salen despedidas a los lados y se desvanecen
        if e < 0.6:
            k = _ease(e / 0.6)
            for im, s in ((self.lazada_i, -1), (self.lazada_d, 1)):
                r = im.rotate(s * -50 * k, expand=True, resample=Image.BICUBIC)
                self._pega(fr, _con_alfa(r, 1 - k), x + s * (im.width / 2 + 140 * k), y - 80 * k)
        if e < 1.7:
            al = 1 - max(0.0, (e - 1.1) / 0.6)
            for pz, a, v, giro in self.confeti:
                px = x + math.cos(a) * v * e * 0.55
                py = y + math.sin(a) * v * e * 0.45 + 420 * e * e
                if py > REG_H:
                    continue
                r = pz.rotate(giro * e, expand=True)
                self._pega(fr, _con_alfa(r, al), px, py)
        fa = e - 0.05
        dur = 0.65
        if fa < 0:
            return
        if fa >= dur:
            self._flecha_quieta(fr, fa - dur)
            return
        k = _ease(fa / dur)
        cx = x + (self.dx - x) * k
        cy = y + (self.dy - y) * k - 90 * math.sin(math.pi * k)
        self._flecha_en(fr, cx, cy, 90 + 25 * (1 - k), 0.2 + 0.8 * k)


def superponer_animacion(video_in: Path, out_path: Path, t0: float, variante: dict,
                         semilla: str, on_log: OnLog = _noop) -> Path:
    """Pega la animación desde `t0` hasta el final del vídeo.

    Los fotogramas van por pipe (rawvideo RGBA) a ffmpeg y solo desde `t0`:
    con `setpts` se colocan en su sitio y, antes, `overlay` deja pasar el
    vídeo tal cual. Así no se pintan ni se mandan fotogramas vacíos.
    """
    from src.nicho_pov_bof.pipeline.duration_match import probe_duration

    dur = probe_duration(video_in)
    t0 = max(0.0, min(float(t0), max(0.0, dur - 0.5)))
    anim = _Animador(variante, semilla)
    n = int(math.ceil((dur - t0) * FPS)) + 1
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-i", str(video_in),
        "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{REG_H}", "-r", str(FPS), "-i", "pipe:0",
        "-filter_complex",
        f"[1:v]setpts=PTS-STARTPTS+{t0:.3f}/TB[a];"
        f"[0:v][a]overlay=0:{REG_Y0}:eof_action=pass:format=auto[v]",
        "-map", "[v]", "-map", "0:a?", "-c:a", "copy",
        "-t", f"{dur:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        quieto: dict[int, bytes] = {}
        for i in range(n):
            t = i / FPS
            if t >= anim.fin_movimiento:
                # Ya solo rebota la flecha: el rebote es periódico, así que se
                # reutilizan los fotogramas de un ciclo en vez de repintarlos.
                ciclo = int(round(2 * math.pi / 7 * FPS))
                clave = int(round((t - anim.fin_movimiento) * FPS)) % ciclo
                if clave not in quieto:
                    quieto[clave] = anim.fotograma(t).tobytes()
                p.stdin.write(quieto[clave])
            else:
                p.stdin.write(anim.fotograma(t).tobytes())
        p.stdin.close()
    except BrokenPipeError:
        pass
    err = p.stderr.read().decode("utf-8", "replace") if p.stderr else ""
    if p.wait() != 0:
        raise RuntimeError(f"ffmpeg animación regalo: {err.strip()[-300:]}")
    on_log(f"[regalo] animación '{variante['anim']}' desde {t0:.2f}s")
    return out_path


# ---------------------------------------------------------------------------
# Sonido (sintetizado: nada con derechos)
# ---------------------------------------------------------------------------
SR = 48000
# Pico del sfx mezclado. La voz sale limitada a 0.9 (`_filtro_voz`); 0.25 son
# unos -11 dB por debajo: se oye el golpe sin tapar ni una sílaba.
_SFX_PICO = 0.25


def _ping(f, dur, dec):
    t = np.arange(int(SR * dur)) / SR
    return (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * 2.01 * f * t)
            + 0.2 * np.sin(2 * np.pi * 3.02 * f * t)) * np.exp(-t * dec)


def _norm(x, pico=1.0):
    return x / (np.abs(x).max() + 1e-9) * pico


def _pop(rng):
    t = np.arange(int(SR * 0.25)) / SR
    return _norm(np.sin(2 * np.pi * (180 * np.exp(-t * 18) + 60) * t) * np.exp(-t * 22)
                 + 0.3 * rng.normal(size=len(t)) * np.exp(-t * 90))


def _estrella_fugaz(rng):
    L = int(SR * 1.8)
    x = np.zeros(L)
    for i in range(26):
        st = int(SR * 0.035 * i)
        f = 900 * 2 ** (i / 9) * (1 + rng.uniform(-0.02, 0.02))
        p = _ping(f, 0.9, 6) * (0.5 + 0.5 * np.sin(np.pi * i / 26))
        x[st:st + len(p)] += p[:L - st]
    n = rng.normal(size=L)
    t = np.arange(L) / SR
    n = np.convolve(n, np.ones(6) / 6, "same") - np.convolve(n, np.ones(60) / 60, "same")
    x += 0.6 * n * np.exp(-((t - 0.45) / 0.3) ** 2)
    for dd, g in ((0.11, 0.35), (0.23, 0.18)):
        k = int(SR * dd)
        x[k:] += g * x[:-k]
    return _norm(x)


def _ding(rng):
    return _norm(_ping(1568, 1.2, 4) + 0.6 * _ping(2093, 1.2, 5))


def _ding_doble(rng):
    a = _ping(1760, 0.9, 5)
    b = _ping(2349, 1.1, 4)
    x = np.zeros(int(SR * 1.3))
    x[:len(a)] += a
    k = int(SR * 0.12)
    x[k:k + len(b)] += 0.8 * b[:len(x) - k]
    return _norm(x)


def _cascabeles(rng):
    """Cascabeles de trineo: ráfagas de ruido metálico (agudo) en ritmo."""
    L = int(SR * 0.9)
    x = np.zeros(L)
    for i in range(6):
        st = int(SR * (0.12 * i + rng.uniform(0, 0.02)))
        n = int(SR * 0.12)
        t = np.arange(n) / SR
        r = rng.normal(size=n)
        r = r - np.convolve(r, np.ones(8) / 8, "same")     # paso alto
        tono = sum(np.sin(2 * np.pi * f * t) for f in (5200, 6300, 7400)) * 0.2
        x[st:st + n] += ((r + tono) * np.exp(-t * 35))[:L - st] * (1 - 0.08 * i)
    return _norm(x)


def _arpegio(notas, paso, dec, dur_nota=1.0):
    L = int(SR * (paso * len(notas) + dur_nota))
    x = np.zeros(L)
    for i, f in enumerate(notas):
        p = _ping(f, dur_nota, dec)
        st = int(SR * paso * i)
        x[st:st + len(p)] += p[:L - st]
    return _norm(x)


def _whoosh(rng):
    L = int(SR * 0.6)
    t = np.arange(L) / SR
    n = rng.normal(size=L)
    # barrido: el filtro se abre conforme avanza (media móvil cada vez más corta)
    out = np.zeros(L)
    trozos = 12
    for i in range(trozos):
        a, b = i * L // trozos, (i + 1) * L // trozos
        k = max(2, int(40 - 36 * i / trozos))
        out[a:b] = np.convolve(n, np.ones(k) / k, "same")[a:b]
    return _norm(out * np.sin(np.pi * t / t[-1]) ** 2)


def _brillo(rng):
    L = int(SR * 1.2)
    x = np.zeros(L)
    for _ in range(18):
        st = int(rng.uniform(0, 0.6) * SR)
        p = _ping(rng.uniform(2200, 4200), 0.5, 9) * rng.uniform(0.4, 1)
        x[st:st + len(p)] += p[:L - st]
    return _norm(x)


def _pluck(rng):
    t = np.arange(int(SR * 0.4)) / SR
    return _norm(np.sin(2 * np.pi * 523 * t) * np.exp(-t * 14) + 0.5 * np.sin(2 * np.pi * 1046 * t) * np.exp(-t * 20))


# Qué suena en cada golpe de la animación. Ganancia relativa por golpe: el de
# «señala» es el que importa (coincide con «carrito naranja»).
COMBINACIONES = {
    "pop_estrella_ding": {"entra": (_pop, 0.7), "abre": (_estrella_fugaz, 0.8), "senala": (_ding, 1.0)},
    "campanillas": {"entra": (_cascabeles, 0.6),
                    "abre": (lambda r: _arpegio((1047, 1319, 1568, 2093), 0.07, 5), 0.8),
                    "senala": (_ding, 0.9)},
    "whoosh_brillo": {"entra": (_whoosh, 0.6), "abre": (_brillo, 0.7), "senala": (_ding_doble, 1.0)},
    "carillon": {"entra": (_pluck, 0.6),
                 "abre": (lambda r: _arpegio((784, 988, 1175, 1568, 1976), 0.11, 3.5, 1.2), 0.8),
                 "senala": (lambda r: _arpegio((1568, 2093), 0.09, 4), 0.9)},
}


def generar_sfx(variante: dict, eventos: dict[str, float], destino: Path, semilla: str = "") -> Path:
    """WAV mono 48 kHz con los golpes en su sitio (t=0 es el arranque de la
    animación; el retraso hasta `t0` lo pone `adelay` en la mezcla)."""
    rng = np.random.default_rng(int.from_bytes(hashlib.sha256(f"sfx|{semilla}".encode()).digest()[:4], "big"))
    combo = COMBINACIONES[variante["sonido"]]
    piezas = []
    for ev, t in eventos.items():
        gen, g = combo[ev]
        piezas.append((int(t * SR), gen(rng) * g))
    L = max(st + len(x) for st, x in piezas) + SR // 10
    mix = np.zeros(L)
    for st, x in piezas:
        mix[st:st + len(x)] += x
    mix = _norm(mix, _SFX_PICO)
    # rampa de 5 ms al principio y al final: sin chasquido
    r = int(SR * 0.005)
    mix[:r] *= np.linspace(0, 1, r)
    mix[-r:] *= np.linspace(1, 0, r)
    with wave.open(str(destino), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())
    return destino


def eventos_de(variante: dict) -> dict[str, float]:
    """Cuándo suena cada golpe (segundos desde el arranque de la animación),
    sacado de los tiempos de `_Animador`: caja que cae / se abre / la flecha
    llega; en «lluvia» el «señala» es el PRIMER bote de la flecha, no cuando
    se queda quieta, que es cuando se oye el golpe."""
    return {
        "caja_flecha": {"entra": 0.25, "abre": 0.62, "senala": 1.18},
        "lluvia": {"entra": 0.0, "abre": 0.55, "senala": 0.84},
        "lazo": {"entra": 0.05, "abre": 0.9, "senala": 1.6},
    }[variante["anim"]]
