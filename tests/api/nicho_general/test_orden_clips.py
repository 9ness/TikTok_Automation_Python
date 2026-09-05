"""Ordenar los tres clips del UGC por lo que se dice en cada uno.

Es la pieza que puede equivocarse EN SILENCIO: si los ordena mal, el anuncio
sale con la CTA delante y el fallo solo se ve reproduciéndolo entero. Por eso
se prueba con transcripciones como las de verdad —Whisper se come palabras y
cambia alguna— y con clips que no son del producto.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.nicho_general.pipeline import video_editor as ve


ESCENAS = [
    {"guion": "Entrenar en casa se complica cuando te falta material y tus rutinas se quedan cortas."},
    {"guion": "Este set combina mancuernas y barra con varios discos, cierres y agarres acolchados."},
    {"guion": "Han ajustado el precio. Ve al carrito naranja y revisa tus cupones."},
]
CLIPS = [Path("/tmp/b.mp4"), Path("/tmp/c.mp4"), Path("/tmp/a.mp4")]


@pytest.fixture
def transcripciones(monkeypatch):
    def poner(mapa: dict[str, str]):
        monkeypatch.setattr(ve, "_transcribir", lambda c, w, l: mapa[str(c)])
    return poner


def test_los_pone_en_el_orden_de_las_escenas(transcripciones):
    """Aunque se suban desordenados, que es lo normal: el selector de ficheros
    los da por nombre y los clips se llaman como los deja Flow."""
    transcripciones({
        "/tmp/b.mp4": "este set combina mancuernas y barra con varios discos cierres y agarres",
        "/tmp/c.mp4": "han ajustado el precio ve al carrito naranja revisa tus cupones",
        "/tmp/a.mp4": "entrenar en casa se complica cuando te falta material y las rutinas se quedan cortas",
    })
    orden = ve.ordenar_clips(CLIPS, ESCENAS, Path("/tmp"), lambda _m: None)
    assert [p.name for p in orden] == ["a.mp4", "b.mp4", "c.mp4"]


def test_si_no_son_de_este_producto_no_se_inventa_un_orden(transcripciones):
    """Dos textos en español ya se parecen un 0,3 solo por las letras: sin un
    umbral alto, cualquier cosa daba un orden 'bueno'."""
    transcripciones(dict.fromkeys(
        [str(c) for c in CLIPS], "receta de tarta de zanahoria con nueces y canela",
    ))
    assert ve.ordenar_clips(CLIPS, ESCENAS, Path("/tmp"), lambda _m: None) == CLIPS


def test_sin_transcripcion_se_respeta_como_se_subieron(transcripciones):
    """Whisper caído o clip mudo: mejor el anuncio con las escenas cambiadas
    —que se ve al reproducirlo— que ningún anuncio."""
    transcripciones(dict.fromkeys([str(c) for c in CLIPS], ""))
    assert ve.ordenar_clips(CLIPS, ESCENAS, Path("/tmp"), lambda _m: None) == CLIPS


def test_un_solo_clip_no_se_toca():
    assert ve.ordenar_clips(CLIPS[:1], ESCENAS, Path("/tmp"), lambda _m: None) == CLIPS[:1]


class TestRecorteDeGuiones:
    """La segunda pasada cuando los guiones no caben en el clip.

    Aquí sí se reintenta —al revés que en el POV BOF Largo—: allí el montaje
    cuadra el vídeo a la voz, pero un clip de Omni dura lo que dura y la frase
    que no quepa se corta por la mitad.
    """

    def _escenas(self, largos: list[int]) -> list[dict]:
        return [
            {"n": i + 1, "titulo": "", "prompt_imagen": "img", "prompt_video": "vid",
             "guion": "x" * n, "caracteres": n}
            for i, n in enumerate(largos)
        ]

    def test_se_queda_con_lo_mas_corto(self, monkeypatch):
        from src.nicho_general.services import escenas as svc

        cortas = [
            {"n": 1, "guion": "corto uno", "prompt_video": "vid"},
            {"n": 2, "guion": "corto dos", "prompt_video": "vid"},
            {"n": 3, "guion": "corto tres", "prompt_video": "vid"},
        ]
        monkeypatch.setattr(
            "src.tiktok_shop.api.gemini.generate_json",
            lambda *a, **k: {"escenas": cortas},
        )
        salida = svc._acortar(
            "p", "d", None, self._escenas([200, 200, 200]), 136, lambda _m: None,
        )
        assert [e["caracteres"] for e in salida] == [9, 9, 10]

    def test_si_devuelve_algo_mas_largo_no_se_acepta(self, monkeypatch):
        """Pedir que acorte y que devuelva MÁS pasa: entonces vale lo de antes."""
        from src.nicho_general.services import escenas as svc

        monkeypatch.setattr(
            "src.tiktok_shop.api.gemini.generate_json",
            lambda *a, **k: {"escenas": [{"n": i + 1, "guion": "y" * 300} for i in range(3)]},
        )
        originales = self._escenas([200, 190, 180])
        salida = svc._acortar("p", "d", None, originales, 136, lambda _m: None)
        assert [e["caracteres"] for e in salida] == [200, 190, 180]

    def test_si_no_devuelve_las_mismas_escenas_se_deja_lo_anterior(self, monkeypatch):
        from src.nicho_general.services import escenas as svc

        monkeypatch.setattr(
            "src.tiktok_shop.api.gemini.generate_json",
            lambda *a, **k: {"escenas": [{"n": 1, "guion": "solo una"}]},
        )
        originales = self._escenas([200, 190, 180])
        assert svc._acortar("p", "d", None, originales, 136, lambda _m: None) == originales
