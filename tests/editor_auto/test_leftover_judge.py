"""Revisor de SOBRANTES (3ª comprobación del cortador): filtros duros."""

from __future__ import annotations

from src.editor_auto.api import openai_client
from src.editor_auto.tools import silence_cutter as sc


def _words(texto: str) -> list[dict]:
    return [{"word": w, "start": i * 0.5, "end": i * 0.5 + 0.4}
            for i, w in enumerate(texto.split())]


TEXTO = ("hoy os traigo esto te va a dar esto te va a dar una tranquilidad "
         "enorme cuesta doce euros y lo tienes en el carrito amarillo ya")


def _judge(monkeypatch, leftovers, texto=TEXTO, budget=None):
    monkeypatch.setattr(openai_client, "is_configured", lambda: True)
    monkeypatch.setattr(openai_client, "analyze_transcript_json",
                        lambda **kw: {"leftovers": leftovers})
    ws = _words(texto)
    return sc._ai_leftover_judge(
        words=ws, keep_intervals=[(0.0, ws[-1]["end"] + 1)], language="es",
        log=lambda _m: None, call_budget=budget,
    )


def test_repeticion_real_se_marca_con_span(monkeypatch):
    budget = [2]
    r = _judge(monkeypatch, [{"type": "repeticion", "severity": 2, "confirmed": True,
                              "quote": "esto te va a dar",
                              "context": "esto te va a dar esto te va a dar una"}],
               budget=budget)
    assert r["leftover_fallos"] == 1 and r["leftover_score"] == 96
    assert r["leftovers"][0]["cut_span"] == (1.5, 3.9)  # tokens 3..7
    assert budget == [1]


def test_contenido_unico_no_es_repeticion(monkeypatch):
    r = _judge(monkeypatch, [{"type": "repeticion", "severity": 3, "confirmed": True,
                              "quote": "cuesta doce euros", "context": "cuesta doce euros"}])
    assert r["leftovers"] == [] and r["leftover_score"] == 100


def test_nunca_el_cierre(monkeypatch):
    r = _judge(monkeypatch, [{"type": "voz_ajena", "severity": 3, "confirmed": True,
                              "quote": "carrito amarillo ya", "context": "carrito amarillo ya"}])
    assert r["leftovers"] == []


def test_no_confirmado_o_cita_inventada(monkeypatch):
    r = _judge(monkeypatch, [
        {"type": "repeticion", "severity": 2, "confirmed": False,
         "quote": "esto te va a dar", "context": ""},
        {"type": "voz_ajena", "severity": 2, "confirmed": True,
         "quote": "que pasa bro", "context": "que pasa bro"},
    ])
    assert r["leftovers"] == []


def test_muletilla_con_contenido_se_descarta(monkeypatch):
    r = _judge(monkeypatch, [{"type": "muletilla", "severity": 2, "confirmed": True,
                              "quote": "tranquilidad", "context": "una tranquilidad enorme"}])
    assert r["leftovers"] == []


def test_presupuesto_agotado_no_llama(monkeypatch):
    r = _judge(monkeypatch, [], budget=[0])
    assert "skipped" in r


def test_interruptores_por_defecto_siguen_a_claude(monkeypatch):
    monkeypatch.setattr(sc, "_claude_activo", lambda: True)
    assert sc._leftover_judge_enabled({}) and not sc._coherence_prescreen({})
    monkeypatch.setattr(sc, "_claude_activo", lambda: False)
    assert not sc._leftover_judge_enabled({}) and sc._coherence_prescreen({})
    assert sc._leftover_judge_enabled({"ai_leftover_judge_enabled": True})
