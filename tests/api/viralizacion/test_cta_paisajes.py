"""El CTA alarga el vídeo, así que hace falta MÁS paisaje.

Bug real, y de los caros: el reparto de clips se hacía con la ventana de VOZ
sola, sin sumar los ~7s de la coletilla. El preflight daba el visto bueno y el
render abortaba después con "los 13 clips asignados dan 36,3s útiles pero hacen
falta 43,1s de paisaje", tirando la tanda entera sin un solo vídeo.

Se comprueba la aritmética y que el preflight tenga en cuenta el CTA, que son
los dos sitios donde se olvidó.
"""

from __future__ import annotations

import pytest

from src.viralizacion import config
from src.viralizacion.pipeline.batch import _segundos_de_cta, reparto_con_cta


class TestRepartoConCta:
    def test_sin_cta_es_la_ventana_de_voz(self):
        total, fill = reparto_con_cta(40.0, 0.0)
        assert total == 40.0
        assert fill == pytest.approx(40.0 - config.HOOK_DUR)

    def test_el_cta_suma_al_paisaje(self):
        """Los números del fallo real: faltaban justo los segundos del CTA."""
        sin_cta = reparto_con_cta(38.9, 0.0)[1]
        con_cta = reparto_con_cta(38.9, 7.2)[1]
        assert con_cta - sin_cta == pytest.approx(7.2)
        assert con_cta == pytest.approx(43.1, abs=0.05)

    def test_un_cta_negativo_no_resta(self):
        """Defensa: un ffprobe que falle devuelve 0 o negativo y no debe
        ACORTAR el paisaje, que sería el mismo bug al revés."""
        assert reparto_con_cta(40.0, -5.0)[1] == pytest.approx(40.0 - config.HOOK_DUR)

    def test_nunca_negativo(self):
        assert reparto_con_cta(1.0, 0.0)[1] == 0.0


class TestSegundosDeCta:
    def test_sin_pedir_cta_no_suma(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(config, "admite_cta", lambda p: True)
        monkeypatch.setattr(config, "cta_files", lambda p: ["/x.mp3"])
        assert _segundos_de_cta("pablo", "no") == 0.0

    def test_un_ponente_sin_cta_no_suma(self, monkeypatch: pytest.MonkeyPatch):
        """Víctor ya lleva la coletilla dentro de sus audios."""
        monkeypatch.setattr(config, "admite_cta", lambda p: False)
        assert _segundos_de_cta("victor", "todos") == 0.0

    def test_coge_el_cta_mas_largo(self, monkeypatch: pytest.MonkeyPatch):
        """Si hay varias coletillas se reserva para la más larga: reservar de
        menos vuelve a dejar el render corto."""
        import src.viralizacion.pipeline.batch as batch

        monkeypatch.setattr(config, "admite_cta", lambda p: True)
        monkeypatch.setattr(config, "cta_files", lambda p: ["/a.mp3", "/b.mp3"])
        monkeypatch.setattr(
            batch, "ffprobe_duration", lambda p: {"/a.mp3": 5.0, "/b.mp3": 9.0}[str(p)]
        )
        assert _segundos_de_cta("pablo", "mitad") == 9.0
