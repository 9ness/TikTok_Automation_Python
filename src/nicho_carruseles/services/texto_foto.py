"""Quema el mensaje sobre la foto del carrusel.

Blanco, negrita, con borde negro y una sombra suave — el texto nativo de
TikTok, que es lo que llevan las cuentas de referencia del curso. Sin píldora
de fondo: la caja negra delata que la foto se editó fuera de la app.

Reutiliza el motor de texto+emoji de `tiktok_shop/pipeline/ready_video.py`, igual
que hace `nicho_pov_bof/pipeline/video_editor.py`. Escribir aquí un segundo
repartidor de líneas habría significado que los emojis se pintaran distinto en
el vídeo y en el carrusel del mismo producto.

No pasa por la cola de trabajos a propósito: esto es un PNG sobre un JPEG, se
resuelve en décimas de segundo. Encolarlo solo añadiría la espera de un worker.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from src.font_resolver import _bundled_fonts_dir
from src.nicho_carruseles import config
from src.tiktok_shop.pipeline.ready_video import (
    _emoji_run_img,
    _seg_width,
    _split_runs,
)


def _font_path(name: str) -> str:
    p = Path(_bundled_fonts_dir()) / name
    return str(p) if p.exists() else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _repartir(texto: str, font: ImageFont.FreeTypeFont, max_w: float,
              emoji_size: int, gap: int) -> list[str]:
    """Parte el mensaje en líneas que quepan en `max_w`.

    Los saltos que ya trae el texto se respetan; solo se re-parte la línea que
    no cabe.
    """
    d0 = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    lineas: list[str] = []
    for bloque in texto.split("\n"):
        bloque = " ".join(bloque.split())
        if not bloque:
            continue
        actual = ""
        for palabra in bloque.split(" "):
            prueba = f"{actual} {palabra}".strip()
            if _seg_width(_split_runs(prueba), font, d0, emoji_size, gap) <= max_w or not actual:
                actual = prueba
            else:
                lineas.append(actual)
                actual = palabra
        if actual:
            lineas.append(actual)
    return lineas


def quemar(origen: Path, texto: str, destino: Path) -> Path:
    """Escribe `texto` sobre la foto y la guarda en `destino`.

    Siempre parte de la foto ORIGINAL, nunca de una ya quemada: por eso las
    versiones con texto viven en su propia carpeta (`config.SUBCARPETAS`). Si se
    quemara encima, cambiar el mensaje dejaría los dos textos superpuestos.
    """
    texto = (texto or "").strip()
    if not texto:
        raise ValueError("no hay texto que escribir en la foto")

    with Image.open(origen) as original:
        foto = original.convert("RGB")

        W, H = foto.size
        tam = max(18, int(W * config.TEXTO_TAM))
        max_w = W * config.TEXTO_ANCHO_MAX
        font = ImageFont.truetype(_font_path(config.FUENTE_TEXTO), tam)
        emoji_size = int(tam * 0.92)
        gap = max(1, int(tam * 0.06))

        lineas = _repartir(texto, font, max_w, emoji_size, gap)
        if not lineas:
            raise ValueError("no hay texto que escribir en la foto")

        borde = max(2, int(tam * config.TEXTO_BORDE))
        alto_linea = int(tam * 1.24)
        capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dib = ImageDraw.Draw(capa)
        d0 = ImageDraw.Draw(Image.new("RGBA", (10, 10)))

        alto_bloque = alto_linea * len(lineas)
        y = int(H * config.TEXTO_Y - alto_bloque / 2)
        for linea in lineas:
            ancho = _seg_width(_split_runs(linea), font, d0, emoji_size, gap)
            x = (W - ancho) / 2
            for clase, tramo in _split_runs(linea):
                if clase == "emoji":
                    em = _emoji_run_img(tramo, emoji_size)
                    if em is not None:
                        capa.paste(em, (int(x), int(y + (tam - emoji_size) / 2)), em)
                        x += em.width + gap
                else:
                    dib.text(
                        (x, y), tramo, font=font, fill=(255, 255, 255, 255),
                        stroke_width=borde, stroke_fill=(0, 0, 0, 255),
                    )
                    x += d0.textlength(tramo, font=font)
            y += alto_linea

        # Sombra: el mismo texto difuminado en negro, desplazado un poco. Es lo
        # que despega las letras de un fondo claro (una pared blanca, la ropa)
        # donde solo con el borde se leen a medias.
        sombra = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        alpha = capa.split()[-1].filter(ImageFilter.GaussianBlur(max(2, tam // 10)))
        negro = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        negro.putalpha(alpha)
        sombra.paste(negro, (0, max(2, tam // 14)), negro)

        foto.paste(sombra, (0, 0), sombra)
        foto.paste(capa, (0, 0), capa)

        destino.parent.mkdir(parents=True, exist_ok=True)
        foto.save(destino, "JPEG", quality=92)
    return destino
