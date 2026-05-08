"""Tests del MIN_WORDS objetivo en el strategist (BUG mayo 2026 — guion corto).

Bug: Gemini tiende a errar por defecto y devolver guiones cortos (20 palabras
para 15s = ~7s de audio sobre 14s de video). El editor mantiene el video
completo, pero los últimos segundos quedan en silencio sobre los frames de
Atlas. Para vídeos de TikTok Shop esto se siente "vacío".

Fix: validar también un MÍNIMO (~75% del máximo) y reintentar con instrucción
"EXTIENDE" si Gemini se queda corto. Al cabo de `max_retries` intentos sin
éxito, aceptamos el guion corto con warning (no truncamos ni inventamos
palabras).
"""

from __future__ import annotations

import src.tiktok_shop.pipeline.strategist as strat_mod
from src.tiktok_shop.pipeline.strategist import (
    generate_strategy,
    max_words_for_duration,
    min_words_for_duration,
)


# ---------------------------------------------------------------------------
# min_words_for_duration: tabla
# ---------------------------------------------------------------------------
class TestMinWordsTable:
    def test_min_is_around_75_pct_of_max(self):
        """min_words debe ser ~75% de max_words (con drift por int truncation
        en duraciones cortas, ej. 5s → 9/13 = 0.69)."""
        for duration in [5, 10, 12, 15, 20, 24, 25, 30]:
            mn = min_words_for_duration(duration)
            mx = max_words_for_duration(duration)
            ratio = mn / mx if mx else 0
            assert 0.65 <= ratio <= 0.80, (
                f"duration={duration}s: min={mn}, max={mx}, ratio={ratio:.2f} "
                f"fuera de [0.65, 0.80]"
            )

    def test_min_lt_max(self):
        """min < max siempre, para que haya un rango [min, max] válido."""
        for d in [5, 10, 15, 20, 30]:
            assert min_words_for_duration(d) < max_words_for_duration(d)

    def test_specific_values(self):
        """Valores exactos para las duraciones más comunes."""
        # 15s: max=40, min ≈ 30 (75%)
        assert max_words_for_duration(15) == 40
        assert min_words_for_duration(15) == 30
        # 10s: max=27, min=20
        assert max_words_for_duration(10) == 27
        assert min_words_for_duration(10) == 20
        # 5s: max=13, min=9
        assert max_words_for_duration(5) == 13
        assert min_words_for_duration(5) == 9


# ---------------------------------------------------------------------------
# generate_strategy con re-ask EXTIENDE
# ---------------------------------------------------------------------------
class TestStrategistMinWordsTarget:
    def _setup_common(self, monkeypatch):
        monkeypatch.setattr(strat_mod, "is_configured", lambda: True)
        monkeypatch.setattr(strat_mod, "load_system_prompt", lambda _f: "FAKE")

    def test_too_short_triggers_extiende_retry(self, monkeypatch):
        """20 palabras para 15s (min=30) → reintenta con instrucción EXTIENDE."""
        self._setup_common(monkeypatch)
        attempts = []

        def fake_generate_json(system, user_msg, **kw):
            attempts.append(user_msg)
            if len(attempts) == 1:
                # Primer intento: 20 palabras (< min=30 para 15s)
                return {"voiceover_script": " ".join(["palabra"] * 20)}
            # Segundo intento: 32 palabras (en rango [30, 40])
            return {"voiceover_script": " ".join(["palabra"] * 32)}

        monkeypatch.setattr(strat_mod, "generate_json", fake_generate_json)

        result = generate_strategy(
            {}, audience="x", hook_category="x",
            duration_seconds=15, max_retries=2,
        )
        assert len(attempts) == 2, (
            f"Esperaba 2 attempts (1 corto + 1 OK). Got {len(attempts)}"
        )
        # El segundo prompt debe tener instrucción EXTIENDE
        assert "EXTIENDE" in attempts[1], (
            f"Segundo intento debe pedir EXTIENDE. Prompt: {attempts[1][-300:]}"
        )
        assert "AL MENOS 30" in attempts[1] or "al menos 30" in attempts[1].lower(), (
            "Debe mencionar el mínimo 30 palabras"
        )
        # Result en rango
        assert strat_mod.count_words(result["voiceover_script"]) == 32

    def test_too_short_after_retries_accepts_with_warning(self, monkeypatch):
        """Si tras todos los retries sigue corto, acepta sin truncar (sería
        contraproducente): el output queda corto pero el editor lo maneja
        con video completo + silencio sobre últimos frames."""
        self._setup_common(monkeypatch)

        def fake_generate_json(system, user_msg, **kw):
            # SIEMPRE devuelve 15 palabras (< min=30 para 15s)
            return {"voiceover_script": " ".join(["palabra"] * 15)}

        monkeypatch.setattr(strat_mod, "generate_json", fake_generate_json)

        result = generate_strategy(
            {}, audience="x", hook_category="x",
            duration_seconds=15, max_retries=2,
        )
        # NO se trunca ni se infla — devuelve el guion corto tal cual
        n = strat_mod.count_words(result["voiceover_script"])
        assert n == 15, f"No se debe modificar el guion corto. Got {n} words"

    def test_within_range_no_retry(self, monkeypatch):
        """En rango [min, max] desde el primer intento → 1 sola llamada."""
        self._setup_common(monkeypatch)
        calls = []

        def fake_generate_json(system, user_msg, **kw):
            calls.append(user_msg)
            return {"voiceover_script": " ".join(["palabra"] * 35)}  # 30<35<40

        monkeypatch.setattr(strat_mod, "generate_json", fake_generate_json)

        generate_strategy(
            {}, audience="x", hook_category="x",
            duration_seconds=15, max_retries=2,
        )
        assert len(calls) == 1, f"Esperaba 1 llamada, got {len(calls)}"

    def test_extiende_prompt_mentions_concrete_details(self, monkeypatch):
        """El prompt EXTIENDE debe pedir DETALLES CONCRETOS, no relleno."""
        self._setup_common(monkeypatch)
        attempts = []

        def fake_generate_json(system, user_msg, **kw):
            attempts.append(user_msg)
            return {"voiceover_script": " ".join(["palabra"] * 10)}

        monkeypatch.setattr(strat_mod, "generate_json", fake_generate_json)

        generate_strategy(
            {}, audience="x", hook_category="x",
            duration_seconds=15, max_retries=2,
        )
        # Hay al menos 1 prompt EXTIENDE — verificar que pide detalles concretos
        extiende_prompts = [a for a in attempts if "EXTIENDE" in a]
        assert extiende_prompts, "Debe haber al menos 1 prompt EXTIENDE"
        first = extiende_prompts[0].lower()
        # Debe mencionar añadir contenido sustantivo, no relleno
        assert any(kw in first for kw in [
            "detalles concretos", "beneficios", "social proof", "sensaciones"
        ]), "El prompt EXTIENDE debe pedir contenido sustantivo, no relleno"
        # Y debe rechazar relleno explícitamente
        assert "no relleno" in first or "no usar relleno" in first or (
            "conversacional" in first
        )

    def test_overflow_still_works(self, monkeypatch):
        """El comportamiento ACORTA sigue intacto — no se rompió por añadir
        EXTIENDE."""
        self._setup_common(monkeypatch)
        attempts = []

        def fake_generate_json(system, user_msg, **kw):
            attempts.append(user_msg)
            if len(attempts) == 1:
                # Primer intento: 50 palabras (> max=40)
                return {"voiceover_script": " ".join(["palabra"] * 50)}
            # Segundo: 33 palabras (en rango)
            return {"voiceover_script": " ".join(["palabra"] * 33)}

        monkeypatch.setattr(strat_mod, "generate_json", fake_generate_json)

        result = generate_strategy(
            {}, audience="x", hook_category="x",
            duration_seconds=15, max_retries=2,
        )
        assert len(attempts) == 2
        # Segundo prompt debe ser ACORTA (no EXTIENDE)
        assert "ACORTA" in attempts[1]
        assert "EXTIENDE" not in attempts[1]
        assert strat_mod.count_words(result["voiceover_script"]) == 33
