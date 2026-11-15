"""Cierre neutro al azar (Néstor, 9/11/2026): mitad sin «aplica tus cupones»."""

import random

from src.nicho_pov_bof_largo import config


def test_escalera_neutra_sin_cupones_y_reconocible():
    for plazos in (False, True):
        for envio in (False, True):
            neutra = config.ctas_posibles(plazos, envio, neutro=True)
            normal = config.ctas_posibles(plazos, envio)
            assert len(neutra) == len(normal)
            assert list(neutra) == sorted(neutra, key=len)
            for cta in neutra:
                assert "cupon" not in cta.lower()
                assert config.cuerpo_sin_cta(f"Cuerpo del guion. {cta}") == "Cuerpo del guion."
            assert all("plazos" not in c for c in neutra) or plazos
            assert all("envío gratis" not in c for c in neutra) or envio


def test_inversa_manda_sobre_neutro():
    assert config.ctas_posibles(True, True, inversa=True, neutro=True) == config.ctas_posibles(
        True, True, inversa=True)


def test_sorteo_mitad_y_mitad():
    rng = random.Random(7)
    n = sum(config.toca_cierre_neutro(rng) for _ in range(2000))
    assert 850 < n < 1150


def test_ningun_cierre_afirma_cupones():
    """«aplica tus cupones» promete un cupón que la ficha puede no tener (11/11)."""
    import itertools

    from src.nicho_pov_bof_largo import config as cfg

    for plazos, envio, inversa, neutro in itertools.product([False, True], repeat=4):
        for cta in cfg.ctas_posibles(plazos, envio, inversa=inversa, neutro=neutro):
            assert "aplica tus cupones" not in cta.lower(), cta
            assert "tus cupones" not in cta.lower(), cta
    assert "aplica" not in cfg.cta_final(True, True).lower()


def test_ctas_para_locutar_manual_y_ficha():
    """15/11: un guion de guardar_guion no se reescribe y el cierre no promete
    plazos/envío que la ficha no trae (el precio solo no basta)."""
    assert config.ctas_para_locutar({}, True, True, "x. Lo tienes en el carrito naranja.", manual=True) == ()
    # Precio alto pero ficha sin plazos/envío: nada de promesas en el cierre.
    for neutro in (False, True):
        ctas = config.ctas_para_locutar({"precio": "89"}, True, True, "Cuerpo.", neutro=neutro)
        assert ctas
        assert all("plazos" not in c and "envío gratis" not in c for c in ctas)
    # Ficha que SÍ lo trae: se ofrece.
    ctas = config.ctas_para_locutar({"plazos": "si", "envio": "gratis"}, True, True, "Cuerpo.")
    assert any("plazos" in c for c in ctas) and any("envío gratis" in c for c in ctas)
