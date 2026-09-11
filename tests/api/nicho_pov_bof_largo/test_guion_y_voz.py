"""Nicho POV BOF Largo: lo propio de este nicho.

Lo que se prueba es donde estaba el riesgo real:

1. **El tope de caracteres no recorta.** El documento del curso pide 260 "para
   15 segundos", pero su propio ejemplo tiene 357 y a 18 car/s eso son 20s.
   Forzar los 260 con reintentos dejaba el guion telegráfico, así que ahora
   solo se AVISA. Si alguien vuelve a meter un bucle de recorte, esto se cae.
2. **El sexo se respeta y la voz se sortea dentro de él.**
3. **El prompt va literal**, sin resumir: resumirlo ya empeoró el guion una vez.
"""

from __future__ import annotations

import random

import pytest

from src.nicho_pov_bof_largo import config
from src.nicho_pov_bof_largo.services import guionista, voz


class TestGuion:
    def _gemini(self, monkeypatch, respuesta: dict):
        monkeypatch.setattr(
            "src.tiktok_shop.api.gemini.generate_json",
            lambda system, user, images=None: respuesta,
        )

    def test_devuelve_los_tres_campos(self, monkeypatch: pytest.MonkeyPatch):
        self._gemini(monkeypatch, {
            "nombre": "Protector Solar",
            "guion": "Han ajustado el precio de este protector solar mineral.",
            "subliminal": "Protector Solar\\na mejor precio ahora mismo",
        })
        r = guionista.escribir(titulo="Protector Solar SPF 50", tienda="Freshly")
        assert r["nombre"] == "Protector Solar"
        assert r["guion"].startswith("Han ajustado el precio")
        # El `\n` escapado del modelo tiene que quedar como salto de verdad.
        assert r["subliminal"] == "Protector Solar\na mejor precio ahora mismo"

    def test_un_guion_largo_se_avisa_pero_NO_se_recorta(
        self, monkeypatch: pytest.MonkeyPatch,
    ):
        largo = "x" * (config.GUION_MAX_CARACTERES + 80)
        self._gemini(monkeypatch, {"nombre": "n", "guion": largo, "subliminal": "a\nb"})
        avisos: list[str] = []
        r = guionista.escribir(titulo="algo", on_log=avisos.append)
        assert len(r["guion"]) == len(largo), "el guion NO debe recortarse"
        assert any("caracteres" in a for a in avisos), "tiene que avisar"

    def test_sin_guion_es_error(self, monkeypatch: pytest.MonkeyPatch):
        self._gemini(monkeypatch, {"nombre": "n", "guion": "", "subliminal": ""})
        with pytest.raises(ValueError, match="no devolvió guion"):
            guionista.escribir(titulo="algo")

    def test_el_prompt_va_literal(self, monkeypatch: pytest.MonkeyPatch):
        """El del curso, sin resumir: resumirlo empeoró el guion una vez."""
        visto: dict = {}

        def _fake(system, user, images=None):
            visto["system"] = system
            visto["user"] = user
            return {"nombre": "n", "guion": "g", "subliminal": "a\nb"}

        monkeypatch.setattr("src.tiktok_shop.api.gemini.generate_json", _fake)
        guionista.escribir(titulo="Gorra negra", tienda="ACME", caption="una gorra")
        assert config.prompt_guion() in visto["system"]
        # La foto nunca va sola: siempre con la descripción (lo pide el prompt).
        assert "Gorra negra" in visto["user"] and "ACME" in visto["user"]


class TestVoz:
    def test_sortea_dentro_del_sexo(self):
        ids_hombre = {v["id"] for v in config.VOCES["hombre"]}
        for semilla in range(15):
            elegida = voz.elegir_voz("hombre", random.Random(semilla))
            assert elegida["id"] in ids_hombre

    def test_usa_mas_de_una_voz(self):
        """Si siempre saliera la misma, el sorteo no estaría sorteando."""
        vistas = {voz.elegir_voz("mujer", random.Random(s))["id"] for s in range(30)}
        assert len(vistas) > 1

    def test_sexo_desconocido_es_error(self):
        with pytest.raises(ValueError, match="sexo debe ser"):
            voz.elegir_voz("robot")

    def test_sin_api_key_falla_claro(self, monkeypatch: pytest.MonkeyPatch, tmp_path):
        monkeypatch.setattr(config, "fish_api_key", lambda: "")
        with pytest.raises(RuntimeError, match="FISH_API_KEY"):
            voz.sintetizar("hola", tmp_path / "v.mp3", sexo="hombre")


class TestMinimoDePlazos:
    """Ningún guion puede decir "en pedidos de más de 30 euros".

    Era la condición del curso y dejó de ser cierta: TikTok ofrece el pago a
    plazos en pedidos pequeños (capturado el 3 de septiembre de 2026 un
    producto de 20,99 € con tres pagos). Decirlo es mentir al espectador y
    encima empujarle a llenar el carrito para llegar a un mínimo que no
    existe. Hay 300+ guiones escritos con esa frase, así que se limpian al
    vuelo — al pintarlos y, sobre todo, antes de locutarlos.
    """

    @pytest.mark.parametrize("frase", [
        "y podrás financiarlo en cómodos plazos en pedidos superiores a 30 euros",
        "y divide tu pago en cómodos plazos si tu pedido supera los 30 euros",
        "puedes pagarlo cómodamente en varios plazos en pedidos de más de 30 €",
        "y podrás financiarlo en cómodos plazos, en pedidos superiores a 30 euros",
    ])
    def test_se_quita_la_condicion_y_la_frase_sigue_entera(self, frase):
        limpio = config.sin_minimo_plazos(f"Bla bla. {frase}. Ve al carrito naranja.")
        assert "30" not in limpio
        assert "plazos" in limpio          # la frase se queda, sin la condición
        assert "  " not in limpio

    def test_es_idempotente(self):
        una = config.sin_minimo_plazos(
            "Y podrás financiarlo en cómodos plazos en pedidos superiores a 30 euros."
        )
        assert config.sin_minimo_plazos(una) == una

    def test_no_toca_un_guion_que_no_lo_dice(self):
        guion = "Han ajustado el precio. Ve al carrito naranja y aplica tus cupones."
        assert config.sin_minimo_plazos(guion) == guion

    def test_el_cierre_del_pov_bof_ya_no_pone_condicion(self):
        from src.nicho_pov_bof import config as pov_config

        for plazos in (True, False):
            for envio in (True, False):
                literal = pov_config._cta(plazos, envio)["CTA_LITERAL"]
                assert "30" not in literal
                if plazos:
                    assert "plazos" in literal.lower()


class TestConfig:
    def test_el_tope_sale_de_la_duracion_que_se_quiere(self):
        """El tope NO es "lo que quepa en los clips" sino la duración decidida.

        Se separaron a propósito: con clips de 8s, "lo que quepa" daba 683
        caracteres —guiones del doble de largos sin que nadie los pidiera—. El
        formato dice 16s y de ahí salen los caracteres."""
        esperado = int(config.GUION_OBJETIVO_S * config.CARACTERES_POR_SEGUNDO)
        assert config.GUION_MAX_CARACTERES == esperado

    def test_no_hay_voces_repetidas_entre_sexos(self):
        assert not (
            {v["id"] for v in config.VOCES["hombre"]}
            & {v["id"] for v in config.VOCES["mujer"]}
        )


class TestElCierreSeReconoce:
    """El cierre hay que saber encontrarlo: es la pieza con la que se cuadra."""

    def test_lo_pilla_aunque_no_empiece_por_el_verbo_del_curso(self):
        """Gemini no siempre escribe "Ve al carrito naranja".

        Cuando escribía "Clica el carrito naranja para aplicar cupones…" el
        cierre se quedaba sin reconocer, y entonces ni se le quitaba la promesa
        que el producto no cumple ni servía para ajustar la duración: el vídeo
        salía de 13,6s.
        """
        g = (
            "Han optimizado el precio de esta mesita LED. Ofrece carga "
            "inalámbrica. Clica el carrito naranja para aplicar cupones."
        )
        assert config.cuerpo_sin_cta(g).endswith("inalámbrica.")
        assert config.cambiar_cta(g, config.CTA_CUPONES).endswith(config.CTA_CUPONES)

    def test_sin_cierre_no_se_inventa_nada(self):
        g = "Un guion cualquiera que no manda a ningún sitio."
        assert config.cuerpo_sin_cta(g) == ""
        assert config.cambiar_cta(g, config.CTA_CUPONES) == g

    def test_al_cambiarlo_no_se_pegan_las_palabras(self):
        g = "Es cómoda. Ve al carrito naranja y aplica tus cupones."
        assert " Ve al carrito" in config.cambiar_cta(g, config.CTA_ENVIO)


class TestEncaje:
    """El puzzle: cierre + acelerón para caer en la ventana de duración."""

    def _dentro(self, cuerpo_car: int, cps: float, ventana=(15.0, 16.0)) -> float:
        from src.nicho_pov_bof_largo.services import voz

        cta, tempo, dur = voz.encaje_cta(
            "x" * cuerpo_car, cps, config.ctas_posibles(True, True), ventana=ventana,
        )
        assert 1.0 <= tempo <= config.VOZ_TEMPO_MAX
        return dur

    def test_un_guion_corto_se_rellena_con_el_cierre(self):
        """Primero se alarga el cierre; bajar el tempo es el segundo recurso."""
        from src.nicho_pov_bof_largo.services import voz

        cta, _t, dur = voz.encaje_cta(
            "x" * 150, 17.8, config.ctas_posibles(True, True), ventana=(15.0, 16.0),
        )
        assert len(cta) > len(config.CTA_CUPONES)
        assert 15.0 <= dur <= 16.0 + config.VENTANA_TOLERANCIA_S

    def test_un_guion_largo_se_queda_con_el_cierre_corto(self):
        from src.nicho_pov_bof_largo.services import voz

        cta, tempo, _d = voz.encaje_cta(
            "x" * 270, 17.8, config.ctas_posibles(True, True), ventana=(15.0, 16.0),
        )
        assert cta == config.CTA_CUPONES
        assert tempo > 1.0

    def test_queda_dentro_con_todas_las_voces_del_banco(self):
        """Un guion de tamaño normal tiene que encajar con cualquiera."""
        from src.nicho_pov_bof_largo.services import velocidad_voz

        for banco in config.VOCES.values():
            for v in banco:
                cps = velocidad_voz.caracteres_por_segundo(v["id"])
                dur = self._dentro(200, cps)
                assert 15.0 <= dur <= 16.0 + config.VENTANA_TOLERANCIA_S, v["label"]

    def test_pasarse_un_segundo_pesa_menos_que_no_llegar(self):
        """Un vídeo de 16,6s no se nota; uno de 14,3s no puntúa en el reto."""
        from src.nicho_pov_bof_largo.services import voz

        _cta, _t, dur = voz.encaje_cta(
            "x" * 165, 16.7, config.ctas_posibles(True, True), ventana=(15.0, 16.0),
        )
        assert dur >= 15.0
