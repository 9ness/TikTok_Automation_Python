"""Tests del fallback dual-key en `src/tiktok_shop/api/gemini.py`.

Sin requests reales — todo mockeado patcheando `_call_with_key`.
Cubrimos los 3 casos pedidos:
  1. Quota agotada en FREE → reintenta con PAID → OK.
  2. Ambas funcionan → usa FREE.
  3. Quota agotada en ambas → propaga error.

Plus: variantes con solo FREE / solo PAID / solo legacy / ninguna.
"""

from __future__ import annotations

import pytest

import src.tiktok_shop.api.gemini as gemini_mod
from src.tiktok_shop.api.gemini import (
    DEFAULT_MODEL,
    _get_gemini_keys,
    _is_quota_error,
    generate_text,
    is_configured,
)


# ---------------------------------------------------------------------------
# Helpers para simular errores Gemini (sin importar google.api_core en tests)
# ---------------------------------------------------------------------------
class _FakeQuotaError(Exception):
    """Simula `google.api_core.exceptions.ResourceExhausted` (429)."""

    def __init__(self, retry_after_s: int = 30):
        msg = (
            f"429 You exceeded your current quota. "
            f"retry_delay {{ seconds: {retry_after_s} }} "
            f"quota_metric: \"generativelanguage.googleapis.com/...\""
        )
        super().__init__(msg)
        self.__class__.__name__ = "ResourceExhausted"


class _FakeAuthError(Exception):
    """Simula error 401/403 (no es quota)."""

    def __init__(self):
        super().__init__("401 PERMISSION_DENIED: API key invalid")


# ---------------------------------------------------------------------------
# Setup: limpiar env vars antes de cada test
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in (
        "GOOGLE_GEMINI_KEY_FREE", "GOOGLE_GEMINI_KEY_PAID",
        "GOOGLE_AI_API_KEY", "GOOGLE_GEMINI_KEY",
    ):
        monkeypatch.delenv(k, raising=False)
    yield


@pytest.fixture
def no_real_sleep(monkeypatch):
    """No queremos esperar `time.sleep(delay+1)` en los tests de retry."""
    monkeypatch.setattr(gemini_mod.time, "sleep", lambda _s: None)


# ---------------------------------------------------------------------------
# _get_gemini_keys: orden de prioridad
# ---------------------------------------------------------------------------
class TestKeyResolution:
    def test_no_keys(self):
        assert _get_gemini_keys() == []
        assert is_configured() is False

    def test_only_free(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_GEMINI_KEY_FREE", "key_f")
        keys = _get_gemini_keys()
        assert keys == [("free", "key_f")]
        assert is_configured() is True

    def test_only_paid(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_GEMINI_KEY_PAID", "key_p")
        assert _get_gemini_keys() == [("paid", "key_p")]

    def test_both_free_and_paid_in_order(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_GEMINI_KEY_FREE", "key_f")
        monkeypatch.setenv("GOOGLE_GEMINI_KEY_PAID", "key_p")
        assert _get_gemini_keys() == [("free", "key_f"), ("paid", "key_p")]

    def test_legacy_only_used_when_no_new_keys(self, monkeypatch):
        # Solo legacy presente
        monkeypatch.setenv("GOOGLE_GEMINI_KEY", "legacy_key")
        assert _get_gemini_keys() == [("legacy", "legacy_key")]

    def test_legacy_ignored_when_new_keys_present(self, monkeypatch):
        # Si hay FREE definida, legacy NO se incluye (evita interferir con CR)
        monkeypatch.setenv("GOOGLE_GEMINI_KEY_FREE", "key_f")
        monkeypatch.setenv("GOOGLE_GEMINI_KEY", "legacy_key")
        keys = _get_gemini_keys()
        assert ("legacy", "legacy_key") not in keys
        assert keys == [("free", "key_f")]

    def test_google_ai_api_key_alias_for_legacy(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_AI_API_KEY", "ai_key")
        assert _get_gemini_keys() == [("legacy", "ai_key")]


# ---------------------------------------------------------------------------
# _is_quota_error
# ---------------------------------------------------------------------------
class TestQuotaErrorDetection:
    def test_resource_exhausted_class_name(self):
        assert _is_quota_error(_FakeQuotaError()) is True

    def test_429_in_message(self):
        e = Exception("429 Too Many Requests")
        assert _is_quota_error(e) is True

    def test_quota_keyword(self):
        e = Exception("quota exceeded")
        assert _is_quota_error(e) is True

    def test_non_quota_error(self):
        assert _is_quota_error(_FakeAuthError()) is False

    def test_random_runtime_error(self):
        assert _is_quota_error(RuntimeError("network broke")) is False


# ---------------------------------------------------------------------------
# Caso 1 — 429 en FREE → reintenta PAID → OK
# ---------------------------------------------------------------------------
class TestFallbackFreeToPaid:
    def test_free_quota_paid_succeeds(self, monkeypatch, no_real_sleep):
        monkeypatch.setenv("GOOGLE_GEMINI_KEY_FREE", "key_f")
        monkeypatch.setenv("GOOGLE_GEMINI_KEY_PAID", "key_p")

        calls: list[str] = []

        def fake_call(api_key, **kwargs):
            calls.append(api_key)
            if api_key == "key_f":
                raise _FakeQuotaError()
            return "OK from paid"

        monkeypatch.setattr(gemini_mod, "_call_with_key", fake_call)

        result = generate_text("sys", "user")
        assert result == "OK from paid"
        # Se intentó FREE primero (1 vez), luego PAID (1 vez sin retry)
        assert calls == ["key_f", "key_p"]


# ---------------------------------------------------------------------------
# Caso 2 — Ambas funcionan → usa FREE (sin tocar PAID)
# ---------------------------------------------------------------------------
class TestPrefersFree:
    def test_both_available_uses_free(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_GEMINI_KEY_FREE", "key_f")
        monkeypatch.setenv("GOOGLE_GEMINI_KEY_PAID", "key_p")

        calls: list[str] = []

        def fake_call(api_key, **kwargs):
            calls.append(api_key)
            return f"OK from {api_key}"

        monkeypatch.setattr(gemini_mod, "_call_with_key", fake_call)

        result = generate_text("sys", "user")
        assert result == "OK from key_f"
        assert calls == ["key_f"]  # PAID NO se llamó


# ---------------------------------------------------------------------------
# Caso 3 — 429 en ambas → propaga error
# ---------------------------------------------------------------------------
class TestBothQuotaExhausted:
    def test_both_429_raises_quota_error(self, monkeypatch, no_real_sleep):
        monkeypatch.setenv("GOOGLE_GEMINI_KEY_FREE", "key_f")
        monkeypatch.setenv("GOOGLE_GEMINI_KEY_PAID", "key_p")

        calls: list[str] = []

        def fake_call(api_key, **kwargs):
            calls.append(api_key)
            raise _FakeQuotaError(retry_after_s=10)

        monkeypatch.setattr(gemini_mod, "_call_with_key", fake_call)

        with pytest.raises(_FakeQuotaError):
            generate_text("sys", "user", max_retries_on_quota=2)

        # FREE: 1 intento (no retry porque hay otra key)
        # PAID: 2 intentos (es la última key, max_retries=2)
        assert calls == ["key_f", "key_p", "key_p"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
class TestEdgeCases:
    def test_no_keys_raises_environment_error(self):
        # Sin keys del env → EnvironmentError descriptivo
        with pytest.raises(EnvironmentError, match="GOOGLE_GEMINI_KEY_FREE"):
            generate_text("sys", "user")

    def test_only_free_no_fallback(self, monkeypatch, no_real_sleep):
        # Si solo hay FREE y se agota, retry con delay (sin PAID disponible)
        monkeypatch.setenv("GOOGLE_GEMINI_KEY_FREE", "key_f")

        attempt_count = [0]

        def fake_call(api_key, **kwargs):
            attempt_count[0] += 1
            if attempt_count[0] < 2:
                raise _FakeQuotaError()
            return "OK after retry"

        monkeypatch.setattr(gemini_mod, "_call_with_key", fake_call)

        result = generate_text("sys", "user", max_retries_on_quota=3)
        assert result == "OK after retry"
        assert attempt_count[0] == 2

    def test_non_quota_error_propagates_immediately(self, monkeypatch):
        # Error no-quota (auth) NO debe probar otras keys ni reintentar
        monkeypatch.setenv("GOOGLE_GEMINI_KEY_FREE", "key_f")
        monkeypatch.setenv("GOOGLE_GEMINI_KEY_PAID", "key_p")

        calls: list[str] = []

        def fake_call(api_key, **kwargs):
            calls.append(api_key)
            raise _FakeAuthError()

        monkeypatch.setattr(gemini_mod, "_call_with_key", fake_call)

        with pytest.raises(_FakeAuthError):
            generate_text("sys", "user")

        # Solo se intenta la primera key (FREE), error auth → no fallback
        assert calls == ["key_f"]

    def test_legacy_used_as_fallback_when_no_new_keys(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_GEMINI_KEY", "legacy_key")
        calls: list[str] = []

        def fake_call(api_key, **kwargs):
            calls.append(api_key)
            return "OK"

        monkeypatch.setattr(gemini_mod, "_call_with_key", fake_call)

        result = generate_text("sys", "user")
        assert result == "OK"
        assert calls == ["legacy_key"]


# ---------------------------------------------------------------------------
# DEFAULT_MODEL (volvió a 2.5-flash)
# ---------------------------------------------------------------------------
class TestDefaultModel:
    def test_default_model_is_2_5_flash(self):
        assert DEFAULT_MODEL == "gemini-2.5-flash"

    def test_default_model_passed_through(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_GEMINI_KEY_FREE", "key_f")
        captured = {}

        def fake_call(api_key, **kwargs):
            captured["model"] = kwargs["model"]
            return "OK"

        monkeypatch.setattr(gemini_mod, "_call_with_key", fake_call)
        generate_text("sys", "user")
        assert captured["model"] == "gemini-2.5-flash"
