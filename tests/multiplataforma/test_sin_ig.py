"""Cuentas sin productos en Instagram (config.SIN_IG, Néstor 20/11/2026)."""
from __future__ import annotations

from src.multiplataforma import config, publicador
from src.multiplataforma.repos import publicaciones_repo
from tests.multiplataforma.test_publicador import AHORA, _cuenta, _pub


def test_plataformas_de(monkeypatch):
    monkeypatch.setattr(config, "SIN_IG", frozenset({"casa"}))
    assert config.plataformas_de("casa", "producto", config.PLATAFORMAS) == ["facebook", "threads", "pinterest"]
    assert config.plataformas_de("casa", "carrusel", config.PLATAFORMAS)[0] == "facebook"
    assert "instagram" in config.plataformas_de("casa", "calentar", config.PLATAFORMAS)
    assert "instagram" in config.plataformas_de("otra", "producto", config.PLATAFORMAS)


def test_publicador_quita_ig_de_producto_colado(tmp_path, sin_red, monkeypatch):
    monkeypatch.setattr(config, "SIN_IG", frozenset({"casa"}))
    _cuenta()
    prod = _pub(tmp_path / "v.mp4", tipo="producto")
    cal = _pub(tmp_path / "c.mp4", tipo="calentar")
    publicador.publicar_pendientes(AHORA, http=sin_red, sleep=lambda s: None)
    p = publicaciones_repo.get(prod.id)
    assert "instagram" not in p.plataformas and "instagram" not in p.estado
    assert p.estado["facebook"] == config.ESTADO_SIMULADO
    assert publicaciones_repo.get(cal.id).estado["instagram"] == config.ESTADO_SIMULADO


def test_ig_ya_publicado_no_se_toca(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SIN_IG", frozenset({"casa"}))
    _cuenta()
    p = _pub(tmp_path / "v.mp4", tipo="producto")
    p.estado["instagram"] = config.ESTADO_PUBLICADO
    publicaciones_repo.guardar(p)
    inf = publicador.publicar_una(publicaciones_repo.get(p.id), ahora=AHORA, dry_run=True)
    assert "sin_instagram" not in inf
