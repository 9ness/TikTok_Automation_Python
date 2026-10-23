"""Fixtures comunes a todas las suites."""

import pytest


@pytest.fixture(autouse=True)
def _ai_pro_sin_claude(monkeypatch):
    """Los tests simulan `gemini.generate_json`; el cliente Claude de AI Pro
    delega en él con el interruptor puesto, así ningún test llama a la API real
    aunque el entorno tenga la clave. Los del cliente Claude lo quitan.
    Igual el Editor Auto: sus tests no deben gastar en Claude."""
    monkeypatch.setenv("AI_PRO_LLM", "gemini")
    monkeypatch.setenv("EDITOR_AUTO_LLM", "openai")
