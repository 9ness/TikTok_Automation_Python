"""Modo «Épico» del POV BOF Largo: golpes en el guion, dónde caen en la voz y
el prompt. El montaje de vídeo se prueba aparte (necesita ffmpeg)."""

from __future__ import annotations

from src.nicho_pov_bof_largo import config
from src.nicho_pov_bof_largo.pipeline import insertos


GUION = (
    "¿Tu espalda ya no aguanta más? [[GOLPE: ESPALDA DESTROZADA | la silla de frente]] "
    "Si pasas horas sentado, esto te interesa. Tiene reposapiés extraíble. "
    "[[GOLPE: reposapiés extraíble | el reposapiés sacado]] "
    "Han ajustado el precio. Ve al carrito naranja y aplica tus cupones."
)


def test_separa_golpes_y_limpia_el_guion():
    limpio, golpes = insertos.separar_golpes(GUION)
    assert "[[" not in limpio and "GOLPE" not in limpio
    assert limpio.startswith("¿Tu espalda ya no aguanta más? Si pasas horas")
    assert [g["texto"] for g in golpes] == ["ESPALDA DESTROZADA", "REPOSAPIÉS EXTRAÍBLE"]
    assert golpes[0]["tras"] == "¿Tu espalda ya no aguanta más?"
    assert golpes[1]["tras"] == "Tiene reposapiés extraíble."
    assert golpes[1]["escena"] == "el reposapiés sacado"


def test_respeta_el_maximo_y_sin_marcas_no_hay_golpes():
    _, golpes = insertos.separar_golpes(GUION, maximo=1)
    assert len(golpes) == 1
    limpio, golpes = insertos.separar_golpes("Un guion normal. Sin marcas.")
    assert golpes == [] and limpio == "Un guion normal. Sin marcas."


def _w(word, start, end):
    return {"word": word, "start": start, "end": end}


def test_localiza_el_final_de_la_frase_y_la_siguiente_palabra():
    palabras = [
        _w("¿Tu", 0.0, 0.2), _w("espalda", 0.2, 0.6), _w("ya", 0.6, 0.7), _w("no", 0.7, 0.8),
        _w("aguanta", 0.8, 1.2), _w("más?", 1.2, 1.6), _w("Si", 2.0, 2.1), _w("pasas", 2.1, 2.4),
        _w("tiene", 5.0, 5.2), _w("reposapiés", 5.2, 5.8), _w("extraíble.", 5.8, 6.4),
        _w("Han", 6.9, 7.0),
    ]
    _, golpes = insertos.separar_golpes(GUION)
    t = insertos.localizar(palabras, golpes)
    assert t[0] == (1.6, 2.0)
    assert t[1] == (6.4, 6.9)


def test_golpe_no_encontrado_es_none():
    _, golpes = insertos.separar_golpes(GUION)
    assert insertos.localizar([_w("otra", 0, 1), _w("cosa", 1, 2)], golpes) == [None, None]


def test_prompt_epico_es_el_de_dolor_mas_el_bloque():
    p = config.prompt_guion(False, "epico", False, 24)
    assert "MODO ÉPICO" in p and "[[GOLPE:" in p
    assert "VARIOS PUNTOS DE DOLOR" in p          # el del curso, literal
    assert "Bloque que se AÑADE" not in p         # la cabecera no va a Gemini
    assert "MODO ÉPICO" not in config.prompt_guion(False, "dolor", False, 24)
    assert config.es_epico("epico") and not config.es_epico("dolor")
    assert config.estilo_texto_de("epico") == "blanco"


def test_el_primer_golpe_siempre_tras_el_gancho():
    g = "¿Te irrita afeitarte? Esto te interesa. [[GOLPE: PIEL IRRITADA | de frente]] Tiene cabezal 9D."
    limpio, golpes = insertos.separar_golpes(g)
    assert golpes[0]["tras"] == "¿Te irrita afeitarte?"


def test_localiza_aunque_whisper_oiga_mal():
    palabras = [_w("Si", 0.0, 0.14), _w("rita", 0.14, 0.42), _w("feitarte", 0.42, 0.82),
                _w("cada", 0.82, 0.94), _w("mañana", 0.94, 1.4), _w("esto", 1.74, 2.0)]
    golpes = [{"tras": "¿Te irrita afeitarte cada mañana?", "texto": "X", "escena": ""}]
    assert insertos.localizar(palabras, golpes) == [(1.4, 1.74)]
