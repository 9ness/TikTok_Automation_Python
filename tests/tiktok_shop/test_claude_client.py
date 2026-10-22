"""Cliente Claude de AI Pro: elección de modelo y respaldo Gemini (sin red)."""

from types import SimpleNamespace

from src.tiktok_shop.api import claude, gemini


class _Stream:
    def __init__(self, resp):
        self.resp = resp

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.resp


def _respuesta(texto, stop="end_turn"):
    usage = SimpleNamespace(input_tokens=10, output_tokens=5,
                            cache_creation_input_tokens=0, cache_read_input_tokens=0)
    return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=texto)],
                           usage=usage)


def _cliente_falso(monkeypatch, texto, stop="end_turn"):
    llamadas = []

    def stream(**kw):
        llamadas.append(kw)
        return _Stream(_respuesta(texto, stop))

    monkeypatch.setattr(claude, "_client",
                        lambda: SimpleNamespace(messages=SimpleNamespace(stream=stream)))
    monkeypatch.setenv("ANTHROPIC_API_KEY_AI_PRO", "x")
    monkeypatch.delenv("AI_PRO_LLM", raising=False)
    return llamadas


def test_texto_sin_fotos_va_a_haiku_sin_pensar(monkeypatch):
    llamadas = _cliente_falso(monkeypatch, '```json\n{"a": 1}\n```')
    assert claude.generate_json("sys", "hola") == {"a": 1}
    assert llamadas[0]["model"] == claude.MODELOS["texto"]
    assert llamadas[0]["thinking"] == {"type": "disabled"}


def test_texto_con_fotos_pasa_a_lectura(monkeypatch):
    llamadas = _cliente_falso(monkeypatch, '{"a": 1}')
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
    claude.generate_json("sys", "", images=[png])
    assert llamadas[0]["model"] == claude.MODELOS["lectura"]
    assert llamadas[0]["output_config"] == {"effort": claude.ESFUERZO["lectura"]}
    assert "thinking" not in llamadas[0]


def test_guion_lleva_esfuerzo(monkeypatch):
    llamadas = _cliente_falso(monkeypatch, '{"guion": "x"}')
    claude.generate_json("sys", "u", tarea="guion")
    assert llamadas[0]["model"] == claude.MODELOS["guion"]
    assert llamadas[0]["output_config"] == {"effort": claude.ESFUERZO["guion"]}


def test_rechazo_cae_a_gemini(monkeypatch):
    _cliente_falso(monkeypatch, "", stop="refusal")
    monkeypatch.setattr(gemini, "generate_json", lambda *a, **k: {"de": "gemini"})
    assert claude.generate_json("sys", "u", temperature=0.2) == {"de": "gemini"}


def test_interruptor_y_audio_van_a_gemini(monkeypatch):
    llamadas = _cliente_falso(monkeypatch, '{"a": 1}')
    monkeypatch.setattr(gemini, "generate_json", lambda *a, **k: {"de": "gemini"})
    assert claude.generate_json("s", "u", audios=["x.wav"]) == {"de": "gemini"}
    monkeypatch.setenv("AI_PRO_LLM", "gemini")
    assert claude.generate_json("s", "u") == {"de": "gemini"}
    assert llamadas == []
