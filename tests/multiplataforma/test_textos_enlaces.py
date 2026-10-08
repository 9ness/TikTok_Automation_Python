from __future__ import annotations

import pytest

from src.multiplataforma.services import enlaces, textos

AVISO = "En calidad de Afiliado de Amazon, obtengo ingresos por las compras adscritas que cumplen los requisitos aplicables"


def test_enlace_amazon():
    assert enlaces.enlace_amazon("b0abc12345", "ness-21") == "https://www.amazon.es/dp/B0ABC12345?tag=ness-21"
    with pytest.raises(enlaces.EnlaceInvalido):
        enlaces.enlace_amazon("corto", "ness-21")
    with pytest.raises(enlaces.EnlaceInvalido):
        enlaces.enlace_amazon("B0ABC12345", "")


def test_shein_tal_cual_y_acortadores_fuera():
    url = "https://onelink.shein.com/abc/xyz?aff=1"
    assert enlaces.resolver(enlace=url) == url
    for malo in ("https://bit.ly/x", "https://amzn.to/abc", "http://www.amazon.es/dp/B0ABC12345"):
        with pytest.raises(enlaces.EnlaceInvalido):
            enlaces.resolver(enlace=malo)


def test_aviso_amazon_en_todas_y_enlace_segun_plataforma():
    url = enlaces.enlace_amazon("B0ABC12345", "ness-21")
    t = textos.construir(titulo="Lámpara LED", caption="Ilumina tu escritorio", enlace=url,
                         hashtags=["#led", "casa", "deco", "hogar", "tech", "luz", "extra"])
    for p, txt in t["textos"].items():
        assert AVISO in txt, p
    assert url in t["textos"]["threads"]
    assert url not in t["textos"]["facebook"] and "primer comentario" in t["textos"]["facebook"]
    assert url in t["comentario"] and AVISO in t["comentario"]
    assert url not in t["textos"]["instagram"]
    assert t["textos"]["instagram"].count("#") == 5
    assert t["textos"]["threads"].count("#") == 1


def test_sin_amazon_no_hay_aviso_y_threads_cabe():
    t = textos.construir(titulo="Vestido", caption="x" * 900, enlace="https://es.shein.com/p-1.html")
    assert AVISO not in t["textos"]["threads"]
    assert len(t["textos"]["threads"]) <= 500
    assert "https://es.shein.com/p-1.html" in t["textos"]["threads"]
    assert "{" not in t["textos"]["instagram"]
