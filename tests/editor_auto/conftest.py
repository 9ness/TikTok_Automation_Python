"""Ningún test del editor manda correos de verdad (12/11/2026: los tests en el
contenedor, con el .env real, mandaron «[Editor] Revisar vídeo de cli» a Néstor)."""
import pytest


@pytest.fixture(autouse=True)
def _sin_emails(monkeypatch):
    from src.editor_auto.services import email_notify

    monkeypatch.setattr(email_notify, "is_configured", lambda *a, **k: False)
    monkeypatch.setattr(email_notify, "_send", lambda *a, **k: {"ok": False, "test": True})
