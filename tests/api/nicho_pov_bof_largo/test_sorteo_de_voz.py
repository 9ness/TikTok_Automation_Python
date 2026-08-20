"""El sorteo de voz tiene que respetar el vídeo que hay.

Cada voz del banco habla a su ritmo, y la diferencia es enorme: de 14,0 a 23,6
caracteres por segundo. El mismo guion son 15 segundos con una y 25 con otra.
Como la voz se sortea DESPUÉS de que el operador haya subido los clips, sortear
a ciegas podía tocar una lenta que no cupiera — y entonces el montaje estira el
vídeo y se deforma el gesto de la mano.
"""

from __future__ import annotations

import random

import pytest

from src.nicho_pov_bof_largo import config
from src.nicho_pov_bof_largo.services import voz

# La más lenta del banco (14,0 car/s medidos).
LENTA = "79ec4c10f80e4e0592b6e2f86b650e22"


def _sortear(veces: int, **kw) -> set[str]:
    r = random.Random(7)
    return {voz.elegir_voz("hombre", r, **kw)["id"] for _ in range(veces)}


class TestElegirVoz:
    def test_sin_saber_cuanto_cabe_entran_todas(self):
        salidas = _sortear(400)
        assert LENTA in salidas

    def test_no_sortea_una_voz_que_no_quepa(self):
        """295 caracteres en dos clips (19,2s) son 21,1s a 14 car/s: no cabe."""
        salidas = _sortear(400, caracteres=295, segundos_max=2 * config.CLIP_MAX_S)
        assert LENTA not in salidas
        assert salidas, "tiene que quedar alguna voz"

    def test_si_cabe_sigue_entrando(self):
        """200 caracteres a 14 car/s son 14,3s: caben de sobra en dos clips."""
        salidas = _sortear(400, caracteres=200, segundos_max=2 * config.CLIP_MAX_S)
        assert LENTA in salidas

    def test_si_no_cabe_ninguna_se_sortea_igual(self):
        """Quedarse sin voz sería peor que estirar el vídeo un poco."""
        salidas = _sortear(50, caracteres=5000, segundos_max=1.0)
        assert salidas

    def test_con_mas_clips_vuelve_a_caber(self):
        """Es el mismo guion: lo que cambia es cuánto vídeo hay para ponerlo."""
        corto = _sortear(400, caracteres=295, segundos_max=2 * config.CLIP_MAX_S)
        largo = _sortear(400, caracteres=295, segundos_max=3 * config.CLIP_MAX_S)
        assert LENTA not in corto
        assert LENTA in largo


class TestBanco:
    def test_no_hay_ids_repetidos(self):
        ids = [v["id"] for voces in config.VOCES.values() for v in voces]
        assert len(ids) == len(set(ids))

    @pytest.mark.parametrize("sexo", config.SEXOS)
    def test_todas_tienen_id_y_nombre(self, sexo: str):
        for v in config.VOCES[sexo]:
            assert v.get("id") and v.get("label")
