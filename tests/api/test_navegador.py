"""El navegador remoto es solo del administrador (puerta `forward_auth` de Caddy)."""

from src.api import session


class TestPuertaDelNavegador:
    def test_admin_pasa(self, app_client, monkeypatch):
        monkeypatch.setattr(session, "usuario_de_request", lambda r: "ness")
        assert app_client.get("/api/v1/navegador/auth").status_code == 200

    def test_otro_usuario_no_pasa(self, app_client, monkeypatch):
        monkeypatch.setattr(session, "usuario_de_request", lambda r: "ana")
        assert app_client.get("/api/v1/navegador/auth").status_code == 401

    def test_sin_sesion_no_pasa(self, app_client, monkeypatch):
        monkeypatch.setattr(session, "usuario_de_request", lambda r: None)
        assert app_client.get("/api/v1/navegador/auth").status_code == 401
        assert app_client.post("/api/v1/navegador/encender").status_code == 401


class TestPuertaDeClaudeVps:
    def test_solo_admin(self, app_client, monkeypatch):
        monkeypatch.setattr(session, "usuario_de_request", lambda r: "ana")
        assert app_client.get("/api/v1/claude-vps/estado").status_code == 401
        assert app_client.post("/api/v1/claude-vps/codigo", json={"codigo": "x"}).status_code == 401
