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
