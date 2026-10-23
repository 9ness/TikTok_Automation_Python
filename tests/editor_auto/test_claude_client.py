"""Editor Auto: Claude primero y OpenAI de respaldo (sin red)."""

from types import SimpleNamespace

import pytest

from src.editor_auto.api import claude_client, openai_client


class _Stream:
    def __init__(self, resp):
        self.resp = resp

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.resp


def _claude_falso(monkeypatch, texto, stop="end_turn"):
    llamadas = []
    usage = SimpleNamespace(input_tokens=10, output_tokens=5,
                            cache_creation_input_tokens=0, cache_read_input_tokens=0)
    resp = SimpleNamespace(stop_reason=stop, usage=usage,
                           content=[SimpleNamespace(type="text", text=texto)])

    def stream(**kw):
        llamadas.append(kw)
        return _Stream(resp)

    monkeypatch.setattr(claude_client, "_client",
                        lambda: SimpleNamespace(messages=SimpleNamespace(stream=stream)))
    monkeypatch.setenv("ANTHROPIC_API_KEY_EDITOR_AUTO", "x")
    monkeypatch.delenv("EDITOR_AUTO_LLM", raising=False)
    monkeypatch.delenv("EDITOR_AUTO_CLAUDE_MODEL", raising=False)
    return llamadas


def test_va_a_claude_haiku_sin_pensar(monkeypatch):
    llamadas = _claude_falso(monkeypatch, '```json\n{"cuts": []}\n```')
    out = openai_client.analyze_transcript_json(system_prompt="s", user_payload={"a": 1},
                                                model="gpt-5.4", seed=7)
    assert out == {"cuts": []}
    assert llamadas[0]["model"] == claude_client.MODELO
    assert llamadas[0]["thinking"] == {"type": "disabled"}


def test_sonnet_lleva_esfuerzo(monkeypatch):
    llamadas = _claude_falso(monkeypatch, '{"cuts": []}')
    monkeypatch.setenv("EDITOR_AUTO_CLAUDE_MODEL", "claude-sonnet-5-5")
    openai_client.analyze_transcript_json(system_prompt="s", user_payload={})
    assert llamadas[0]["output_config"] == {"effort": claude_client.ESFUERZO}
    assert "thinking" not in llamadas[0]


def test_fallo_de_claude_cae_a_openai(monkeypatch):
    _claude_falso(monkeypatch, "", stop="refusal")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    vistos = []

    class _OpenAI:
        def __init__(self, **kw):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kw):
            vistos.append(kw["model"])
            msg = SimpleNamespace(content='{"de": "openai"}')
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=None)

    import openai
    monkeypatch.setattr(openai, "OpenAI", _OpenAI)
    out = openai_client.analyze_transcript_json(system_prompt="s", user_payload={}, model="gpt-5.4")
    assert out == {"de": "openai"} and vistos == ["gpt-5.4"]


def test_sin_openai_el_fallo_de_claude_se_propaga(monkeypatch):
    _claude_falso(monkeypatch, "no es json")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError):
        openai_client.analyze_transcript_json(system_prompt="s", user_payload={})


def test_interruptor_vuelve_a_openai(monkeypatch):
    llamadas = _claude_falso(monkeypatch, "{}")
    monkeypatch.setenv("EDITOR_AUTO_LLM", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert not openai_client.is_configured()
    with pytest.raises(RuntimeError):
        openai_client.analyze_transcript_json(system_prompt="s", user_payload={})
    assert llamadas == []
