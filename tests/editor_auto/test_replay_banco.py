"""Banco de regresión sin gasto: la grabadora de llamadas de pago (sin red)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "editor_auto"))

from replay import Grabadora, ReplayMiss  # noqa: E402

from src.editor_auto.api import claude_client, gemini_client, openai_client  # noqa: E402
from src.editor_auto.tools import silence_cutter  # noqa: E402


@pytest.fixture
def reales(monkeypatch):
    """Sustituye las llamadas «reales» por contadores (nada sale a la red)."""
    llamadas = {"deepgram": 0, "openai": 0, "claude": 0, "gemini": 0}

    def dg(payload, *, language=None, model="nova-3", offset=0.0):
        llamadas["deepgram"] += 1
        return [{"word": "hola", "start": 1.0 + offset, "end": 1.5 + offset}]

    def ia(nombre):
        def f(**kw):
            llamadas[nombre] += 1
            return {"cuts": [[0, 1]], "de": nombre, "n": llamadas[nombre]}
        return f

    monkeypatch.setattr(silence_cutter, "_deepgram_words", dg)
    monkeypatch.setattr(openai_client, "analyze_transcript_json", ia("openai"))
    monkeypatch.setattr(claude_client, "analyze_transcript_json", ia("claude"))
    monkeypatch.setattr(gemini_client, "analyze_transcript_json", ia("gemini"))
    return llamadas


def test_record_y_replay_misma_respuesta_sin_llamar(tmp_path, reales):
    with Grabadora("record", str(tmp_path)):
        a = openai_client.analyze_transcript_json(system_prompt="s", user_payload={"w": 1})
        w = silence_cutter._deepgram_words(b"audio", language="es")
    assert reales["openai"] == 1 and reales["deepgram"] == 1

    with Grabadora("replay", str(tmp_path)) as g:
        b = openai_client.analyze_transcript_json(system_prompt="s", user_payload={"w": 1})
        w2 = silence_cutter._deepgram_words(b"audio", language="es")
    assert a == b and w == w2
    assert reales["openai"] == 1 and reales["deepgram"] == 1  # no volvió a llamar
    assert g.stats["hits"] == 2


def test_replay_sin_grabar_no_llama(tmp_path, reales):
    with Grabadora("replay", str(tmp_path)):
        with pytest.raises(ReplayMiss):
            claude_client.analyze_transcript_json(system_prompt="s", user_payload={})
        with pytest.raises(ReplayMiss):
            silence_cutter._deepgram_words(b"x", language="es")
    assert sum(reales.values()) == 0


def test_offline_nunca_llama(reales):
    with Grabadora("offline", None):
        with pytest.raises(ReplayMiss):
            gemini_client.analyze_transcript_json(system_prompt="s", user_payload={})
    assert sum(reales.values()) == 0


def test_entrada_distinta_no_reusa(tmp_path, reales):
    with Grabadora("record", str(tmp_path)):
        openai_client.analyze_transcript_json(system_prompt="s", user_payload={"w": 1})
    with Grabadora("replay", str(tmp_path)):
        with pytest.raises(ReplayMiss):
            openai_client.analyze_transcript_json(system_prompt="s", user_payload={"w": 2})


def test_deepgram_offset_se_aplica_al_reproducir(tmp_path, reales):
    with Grabadora("record", str(tmp_path)):
        silence_cutter._deepgram_words(b"tramo", language="es", offset=0.0)
    with Grabadora("replay", str(tmp_path)):
        w = silence_cutter._deepgram_words(b"tramo", language="es", offset=10.0)
    assert w[0]["start"] == pytest.approx(11.0)
    assert reales["deepgram"] == 1


def test_desinstalar_restaura(tmp_path, reales):
    antes = openai_client.analyze_transcript_json
    with Grabadora("offline", None):
        assert openai_client.analyze_transcript_json is not antes
    assert openai_client.analyze_transcript_json is antes


def test_comparar_detecta_empeoramiento():
    import silence_regression as sr
    base = [{"video": "a", "score": 90}, {"video": "b", "score": 80, "error": None}]
    act = [{"video": "a", "score": 88}, {"video": "b", "score": 85, "error": None}]
    assert sr.comparar(act, base) == ["a: score 90 → 88"]
    assert sr.comparar([{"video": "b", "score": None, "error": "X"}], base)


def test_tipo_proceso():
    import silence_regression as sr
    assert sr._tipo_proceso(["ffmpeg", "-i", "a", "-c:v", "libx264", "o.mp4"]) == "ffmpeg codificar"
    assert sr._tipo_proceso(["ffmpeg", "-i", "a", "-vn", "o.wav"]) == "ffmpeg audio"
    assert sr._tipo_proceso(["ffprobe", "x"]) == "ffprobe"
