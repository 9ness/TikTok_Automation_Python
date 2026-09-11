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

# La más lenta del banco. Se BUSCA, no se escribe: el banco se cambia entero de
# vez en cuando (en sep 2026 salieron las veinte de vendedor y entraron diez
# conversacionales) y un id a mano deja estos tests probando una voz que ya no
# existe — pasando o fallando por el motivo equivocado.
def _mas_lenta(sexo: str = "hombre") -> str:
    from src.nicho_pov_bof_largo.services import velocidad_voz

    return min(
        config.VOCES[sexo],
        key=lambda v: velocidad_voz.caracteres_por_segundo(v["id"]),
    )["id"]


LENTA = _mas_lenta()


def _no_cabe(sexo: str = "hombre") -> int:
    """Caracteres que a la voz más lenta NO le caben en dos clips.

    Se calcula con su velocidad y con el acelerón máximo que se tolera, para
    que el número siga valiendo cuando cambie el banco o el estirado.
    """
    from src.nicho_pov_bof_largo.services import velocidad_voz

    cps = velocidad_voz.caracteres_por_segundo(LENTA)
    return int(2 * config.CLIP_MAX_S * cps * config.VOZ_TEMPO_MAX) + 20


def _sortear(veces: int, **kw) -> set[str]:
    r = random.Random(7)
    return {voz.elegir_voz("hombre", r, **kw)["id"] for _ in range(veces)}


class TestElegirVoz:
    def test_sin_saber_cuanto_cabe_entran_todas(self):
        salidas = _sortear(400)
        assert LENTA in salidas

    def test_no_sortea_una_voz_que_no_quepa(self):
        """Un guion que a la voz más lenta no le cabe ni acelerándola al tope."""
        salidas = _sortear(400, caracteres=_no_cabe(), segundos_max=2 * config.CLIP_MAX_S)
        assert LENTA not in salidas
        assert salidas, "tiene que quedar alguna voz"

    def test_si_cabe_sigue_entrando(self):
        """La mitad de lo que cabe: a la más lenta le sobra sitio."""
        salidas = _sortear(400, caracteres=_no_cabe() // 2, segundos_max=2 * config.CLIP_MAX_S)
        assert LENTA in salidas

    def test_si_no_cabe_ninguna_se_sortea_igual(self):
        """Quedarse sin voz sería peor que estirar el vídeo un poco."""
        salidas = _sortear(50, caracteres=5000, segundos_max=1.0)
        assert salidas

    def test_con_mas_clips_vuelve_a_caber(self):
        """Es el mismo guion: lo que cambia es cuánto vídeo hay para ponerlo."""
        corto = _sortear(400, caracteres=_no_cabe(), segundos_max=2 * config.CLIP_MAX_S)
        largo = _sortear(400, caracteres=_no_cabe(), segundos_max=3 * config.CLIP_MAX_S)
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


class TestClipsPara:
    """Cuántos clips hay que pedirle al operador para ese guion."""

    def _cps(self, id_voz: str) -> float:
        from src.nicho_pov_bof_largo.services import velocidad_voz

        return velocidad_voz.caracteres_por_segundo(id_voz)

    def test_un_guion_corto_no_pide_clips_de_mas(self):
        """Un guion que no llega al mínimo NO se arregla con más clips.

        Más clips dan más sitio, pero la voz dura lo que dura: si el guion se
        quedó corto, ninguna combinación llega a los 15s. El bucle terminaba
        devolviendo el máximo —cuatro clips para un vídeo de trece segundos— y
        el operador generaba dos de balde.
        """
        rapida = max(
            (v["id"] for banco in config.VOCES.values() for v in banco),
            key=self._cps,
        )
        # La mitad de lo que esa voz diría en el mínimo: no llega ni de lejos.
        cortisimo = int(self._cps(rapida) * config.DURACION_MINIMA_S * 0.5)
        pedidos = voz.clips_para(
            cortisimo, 8.0, segundos_min=config.DURACION_MINIMA_S, maximos=4,
        )
        sin_minimo = voz.clips_para(cortisimo, 8.0, maximos=4)
        assert pedidos == sin_minimo < 4

    def test_la_duracion_pedida_manda_sobre_el_minimo_del_reto(self):
        """Un vídeo DE 30 segundos necesita cuatro clips de 8, no tres.

        Con el mínimo del reto (15s) valía el primer número de clips en el que
        cupiera alguna voz, y eso son tres clips con una voz acelerada que deja
        el vídeo en 26s — veinte por ciento menos de lo prometido.
        """
        car = config.caracteres_guion(30)
        assert voz.clips_para(car, 8.0, segundos_min=30, maximos=4) == 4
        assert voz.clips_para(
            car, 8.0, segundos_min=config.DURACION_MINIMA_S, maximos=4,
        ) == 3
