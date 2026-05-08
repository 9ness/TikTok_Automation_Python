"""Tests del límite de palabras-por-segundo del strategist (BUG 1).

Verifican:
- count_words: cuenta correcta ignorando puntuación.
- max_words_for_duration: tabla coincide con el system prompt.
- generate_strategy: si Gemini devuelve script largo, reintenta; si todos
  los reintentos fallan, trunca duro.
"""

from __future__ import annotations

import pytest

import src.tiktok_shop.pipeline.strategist as strat_mod
from src.tiktok_shop.pipeline.strategist import (
    count_words,
    generate_strategy,
    max_words_for_duration,
)


# ---------------------------------------------------------------------------
# count_words
# ---------------------------------------------------------------------------
class TestCountWords:
    def test_empty(self):
        assert count_words("") == 0
        assert count_words(None) == 0  # type: ignore[arg-type]

    def test_simple(self):
        assert count_words("hola mundo") == 2

    def test_ignores_punctuation(self):
        # Puntos, comas, signos no cuentan como palabras
        assert count_words("Hola, mundo. ¿Cómo estás?") == 4

    def test_multiple_spaces(self):
        assert count_words("uno  dos   tres") == 3

    def test_real_voiceover(self):
        text = (
            "POV: descubres las gominolas que sustituyen tu creatina en polvo. "
            "Cuatro mil quinientos miligramos en una sola dosis."
        )
        # 10 (POV/descubres/las/gominolas/que/sustituyen/tu/creatina/en/polvo)
        # + 8 (Cuatro/mil/quinientos/miligramos/en/una/sola/dosis)
        assert count_words(text) == 18


# ---------------------------------------------------------------------------
# max_words_for_duration: debe coincidir con la tabla del system prompt
# ---------------------------------------------------------------------------
class TestMaxWordsForDuration:
    # 2.7 wps (BUG B fix) → tabla actualizada en `content_strategist.md`
    @pytest.mark.parametrize("duration,expected", [
        (5, 13),
        (10, 27),
        (12, 32),
        (15, 40),
        (20, 54),
        (24, 64),
        (25, 67),
        (30, 81),
    ])
    def test_table_matches_prompt(self, duration: int, expected: int):
        assert max_words_for_duration(duration) == expected


# ---------------------------------------------------------------------------
# generate_strategy con validación de word-count
# ---------------------------------------------------------------------------
class TestGenerateStrategyWordLimit:
    def test_first_attempt_within_limit_returns_immediately(self, monkeypatch):
        """Si el primer intento está EN el rango [min, max], no reintenta."""
        calls = []

        def fake_generate_json(system, user_msg, **kw):
            calls.append(user_msg)
            # Para 5s: min=9, max=13 → 10 palabras está en rango
            return {
                "voiceover_script": "Diez palabras simples no excede pero llega al mínimo objetivo limpio.",
                "video_structure": [],
            }

        monkeypatch.setattr(strat_mod, "generate_json", fake_generate_json)
        monkeypatch.setattr(strat_mod, "is_configured", lambda: True)
        # Stub load_system_prompt
        monkeypatch.setattr(strat_mod, "load_system_prompt", lambda _f: "FAKE_SYSTEM")

        result = generate_strategy(
            {"key_features": []},
            audience="x", hook_category="curiosity",
            duration_seconds=5,  # rango [9, 13] palabras
            product_name="Test",
        )
        assert "voiceover_script" in result
        assert len(calls) == 1  # 1 sola llamada

    def test_first_attempt_exceeds_retries_with_shorten_request(self, monkeypatch):
        """Si excede, reintenta y la 2ª vez encaja."""
        attempts = []

        def fake_generate_json(system, user_msg, **kw):
            attempts.append(user_msg)
            if len(attempts) == 1:
                # Primer intento: 50 palabras (> 40 límite para 15s a 2.7 wps)
                long_text = " ".join(["palabra"] * 50)
                return {"voiceover_script": long_text}
            # Segundo intento: 30 palabras (OK, está bajo el límite de 40)
            short_text = " ".join(["palabra"] * 30)
            return {"voiceover_script": short_text}

        monkeypatch.setattr(strat_mod, "generate_json", fake_generate_json)
        monkeypatch.setattr(strat_mod, "is_configured", lambda: True)
        monkeypatch.setattr(strat_mod, "load_system_prompt", lambda _f: "FAKE_SYSTEM")

        result = generate_strategy(
            {}, audience="x", hook_category="x",
            duration_seconds=15,  # límite 40 (2.7 wps)
            max_retries=2,
        )
        assert len(attempts) == 2
        # El segundo prompt debe contener instrucción de ACORTAR
        assert "ACORTA" in attempts[1]
        assert "40 palabras" in attempts[1]
        assert count_words(result["voiceover_script"]) == 30

    def test_all_retries_fail_truncates_hard(self, monkeypatch):
        """Si tras todos los reintentos sigue largo, trunca duro al límite."""
        def fake_generate_json(system, user_msg, **kw):
            # Siempre devuelve 60 palabras (> 40 límite a 2.7 wps)
            return {"voiceover_script": " ".join(["palabra"] * 60)}

        monkeypatch.setattr(strat_mod, "generate_json", fake_generate_json)
        monkeypatch.setattr(strat_mod, "is_configured", lambda: True)
        monkeypatch.setattr(strat_mod, "load_system_prompt", lambda _f: "FAKE_SYSTEM")

        result = generate_strategy(
            {}, audience="x", hook_category="x",
            duration_seconds=15, max_retries=2,
        )
        n = count_words(result["voiceover_script"])
        assert n <= 40, f"Tras truncar duro debe estar bajo 40 palabras, está en {n}"

    def test_truncates_at_punctuation_when_possible(self):
        """El truncado prefiere cortar en `.` o `,` si está cerca del límite."""
        text = (
            "Una frase corta. Otra que también es corta y bonita. "
            "Y luego mucho más relleno que no debería aparecer en el resultado final."
        )
        # 7 + 8 = 15 palabras antes del relleno; +14 relleno = 29 total
        truncated = strat_mod._truncate_to_words(text, max_words=15)
        # Debe terminar en punto
        assert truncated.endswith(".")
        assert count_words(truncated) <= 15

    def test_mock_strategy_when_gemini_disabled(self, monkeypatch):
        """Si Gemini no configurado, devuelve mock sin tocar word-limit."""
        monkeypatch.setattr(strat_mod, "is_configured", lambda: False)
        result = generate_strategy(
            {}, audience="x", hook_category="x", duration_seconds=15,
        )
        assert result["voiceover_script"].startswith("(Gemini no configurado")
