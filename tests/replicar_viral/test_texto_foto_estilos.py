"""Estilos de texto del carrusel (texto_foto): cada uno renderiza y el tamaño se valida."""

from __future__ import annotations

import pytest
from PIL import Image

from src.nicho_carruseles.services import texto_foto

NUEVOS = ["tiktok_sans", "fondo_negro", "fondo_blanco", "fondo_trans", "snap", "tiktok_medio", "tiktok_amarillo", "fondo_rosa"]
TEXTO = "¿Dónde puedo conseguir\neste conjunto? 😍"


@pytest.fixture()
def foto(tmp_path):
    p = tmp_path / "o.jpg"
    Image.new("RGB", (1080, 1440), (90, 140, 190)).save(p, "JPEG")
    return p


@pytest.mark.parametrize("estilo", NUEVOS + ["tiktok", "pildora_negra"])
def test_estilo_renderiza(foto, tmp_path, estilo):
    out = texto_foto.quemar(foto, TEXTO, tmp_path / f"{estilo}.jpg", estilo=estilo, tam_rel=0.8)
    with Image.open(out) as im, Image.open(foto) as orig:
        assert im.size == orig.size
        assert list(im.getdata()) != list(orig.getdata())


def test_fondo_negro_caja_opaca_y_trans_mas_clara(foto, tmp_path):
    a = texto_foto.quemar(foto, "Hola mundo", tmp_path / "a.jpg", estilo="fondo_negro", y_rel=0.5)
    b = texto_foto.quemar(foto, "Hola mundo", tmp_path / "b.jpg", estilo="fondo_trans", y_rel=0.5)
    # Píxel de la caja, a la izquierda del texto y dentro de la caja
    with Image.open(a) as ia, Image.open(b) as ib:
        ys = range(700, 740)
        xa = [ia.getpixel((x, 720)) for x in range(300, 800)]
        oscuro = min(sum(p) for p in xa)
        assert oscuro < 40
        xb = [ib.getpixel((x, 720)) for x in range(300, 800)]
        assert min(sum(p) for p in xb) > oscuro


def test_tam_cambia_el_texto_y_se_valida(foto, tmp_path):
    ch = texto_foto.quemar(foto, "Hola", tmp_path / "c.jpg", estilo="fondo_negro", tam_rel=0.5)
    gr = texto_foto.quemar(foto, "Hola", tmp_path / "g.jpg", estilo="fondo_negro", tam_rel=1.6)
    assert ch.stat().st_size != gr.stat().st_size
    for malo in (0.4, 1.7, "x"):
        with pytest.raises(ValueError):
            texto_foto.quemar(foto, "Hola", tmp_path / "m.jpg", tam_rel=malo)
    assert texto_foto.tam_valido(None) is None
    assert texto_foto.tam_valido(1.0) == 1.0


def test_espacios_duros_separan_dos_etiquetas():
    """«Mi mamá      Yo»: los espacios normales se juntan, los duros no."""
    from PIL import ImageFont
    font = ImageFont.truetype(texto_foto._font_path("TikTokSans-Medium.ttf"), 40)
    lineas = texto_foto._repartir("Mi   mamá" + " " * 8 + "Yo", font, 2000, 40, 4)
    assert lineas == ["Mi mamá" + " " * 8 + "Yo"]


def test_espacios_duros_al_borde_de_linea_desplazan_la_etiqueta():
    """Relleno con U+00A0 al final/principio: una etiqueta a la izquierda y otra a la derecha."""
    from PIL import ImageFont
    font = ImageFont.truetype(texto_foto._font_path("TikTokSans-Medium.ttf"), 40)
    n = "\u00a0" * 6
    assert texto_foto._repartir("Hola" + n + "\n" + n + "Adiós", font, 2000, 40, 4) == ["Hola" + n, n + "Adiós"]
