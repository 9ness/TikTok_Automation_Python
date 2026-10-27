"""Acabado de texto «regalo» del montaje POV BOF / POV BOF Largo.

Lo que se protege aquí: que varíe de verdad entre productos (lo pidió el
dueño: «que no sea siempre lo mismo»), que no varíe para el MISMO producto
(un remontaje tiene que salir igual) y que ningún texto fijo prometa nada.
"""
import pytest

from src.nicho_pov_bof.pipeline import regalo
from src.nicho_pov_bof_largo import config

SEMILLAS = [f"productos_web/Carpeta {i // 5}/{i}" for i in range(20)]
VETADAS = ("perfecto", "tu cupón", "tu cupon", "black friday", "envío", "envio", "llega")


def test_determinista_por_semilla():
    for s in SEMILLAS:
        assert regalo.elegir_variante(s) == regalo.elegir_variante(s)


def test_productos_distintos_salen_distintos():
    vs = [regalo.elegir_variante(s) for s in SEMILLAS]
    assert len({v["forma"] for v in vs}) >= 3
    assert len({v["anim"] for v in vs}) >= 3
    assert len({v["sonido"] for v in vs}) >= 3
    assert len({v["paleta"]["nombre"] for v in vs}) >= 3
    assert len({v["fuente"] for v in vs}) >= 3


def test_minimos_de_variedad():
    assert len(regalo.FORMAS) >= 4
    assert len(regalo.PALETAS) >= 4
    assert len(regalo.FUENTES) >= 3
    assert len(regalo.ANIMACIONES) >= 3
    assert len(regalo.SONIDOS) >= 3
    assert set(regalo.SONIDOS) == set(regalo.COMBINACIONES)


@pytest.mark.parametrize("texto", regalo.FRASES + regalo.CUPONES)
def test_ningun_texto_fijo_promete(texto):
    bajo = texto.lower()
    for veto in VETADAS:
        assert veto not in bajo, (texto, veto)


def test_el_cupon_se_sugiere():
    for c in regalo.CUPONES:
        assert c.lower().startswith(("revisa si", "mira si"))


def test_estilo_texto_regalo_en_el_largo():
    assert "regalo" in config.ESTILOS_TEXTO
    assert config.estilo_texto_valido("", "regalo") == "regalo"
    assert config.estilo_texto_valido("regalo", "dolor") == "regalo"
    # Los demás no cambian.
    assert config.estilo_texto_valido("", "dolor") == "blanco"
    assert config.estilo_texto_valido("clasico", "regalo") == ""


def _variante_de(forma):
    for i in range(500):
        v = regalo.elegir_variante(f"humo-{i}")
        if v["forma"] == forma:
            return v
    raise AssertionError(f"ninguna semilla da la forma {forma}")


@pytest.mark.parametrize("forma", regalo.FORMAS)
@pytest.mark.parametrize("titulo", [
    "3 Gnomos suecos con luz",
    "Plancha de parrilla VEVOR\npara barbacoa y teppanyaki",
    "Señal ¿añoñí? ÁÉÍÓÚ",
])
def test_humo_rotulo_de_cada_forma(forma, titulo):
    im = regalo.render_rotulo({"titulo": titulo}, _variante_de(forma))
    assert im is not None and im.mode == "RGBA"
    assert im.width <= 1080
    assert im.height <= regalo._MAX_H


def test_rotulo_sin_piezas_no_pinta_nada():
    v = _variante_de("caja")
    assert regalo.render_rotulo({"titulo": "Algo"}, v, piezas=set()) is None


def test_nombre_arriesgado_se_limpia():
    nombre = regalo.nombre_seguro({"titulo": "Cafetera barata de cápsulas"})
    assert "barat" not in nombre.lower()
    assert "Cafetera" in nombre


@pytest.mark.parametrize("anim", regalo.ANIMACIONES)
def test_animacion_acaba_con_la_flecha_en_el_carrito(anim):
    v = dict(_variante_de("caja"), anim=anim)
    a = regalo._Animador(v, "x")
    for t in (0.0, 0.5, 1.0, 1.5):
        a.fotograma(t)
    fin = a.fotograma(a.fin_movimiento + 1.0)
    bb = fin.getbbox()
    assert bb is not None
    # Lo único que queda es la flecha, alrededor del carrito.
    cx = (bb[0] + bb[2]) / 2
    cy = (bb[1] + bb[3]) / 2 + regalo.REG_Y0
    assert abs(cx - regalo.DIANA[0]) < 60 and abs(cy - regalo.DIANA[1]) < 60


@pytest.mark.parametrize("sonido", regalo.SONIDOS)
def test_sfx_se_genera(sonido, tmp_path):
    import wave

    v = dict(_variante_de("caja"), sonido=sonido)
    wav = regalo.generar_sfx(v, regalo.eventos_de(v), tmp_path / "s.wav", "x")
    with wave.open(str(wav)) as w:
        assert w.getframerate() == 48000
        assert w.getnframes() > 48000 // 2
