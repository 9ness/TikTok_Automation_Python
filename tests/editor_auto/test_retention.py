"""Caducidad de vídeos de clientes web (retention_sweeper + config)."""
from __future__ import annotations

import os
import time
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from src.editor_auto import config
from src.editor_auto.services import retention_sweeper as rs


class _R:
    def __init__(self):
        self.kv: dict = {}
        self.sets: dict[str, set] = {}

    def get_str(self, k):
        return self.kv.get(k)

    def set_str(self, k, v):
        self.kv[k] = v

    def get_json(self, k):
        return self.kv.get(k)

    def smembers(self, k):
        return list(self.sets.get(k, set()))

    def _cmd(self, c):
        op, k, *rest = c
        if op == "DEL":
            for x in [k, *rest]:
                self.kv.pop(x, None)
                self.sets.pop(x, None)
        elif op == "SREM":
            self.sets.get(k, set()).difference_update(rest)
        elif op == "SADD":
            self.sets.setdefault(k, set()).update(rest)


HOY = date(2026, 11, 9)


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    r = _R()
    monkeypatch.setattr(rs, "get_editor_redis", lambda: r)
    monkeypatch.setattr("src.editor_auto.repos.redis_base.get_editor_redis", lambda: r)
    monkeypatch.setattr(rs, "_today", lambda: HOY)
    base = tmp_path / "u"
    for f in ("user_folder",):
        monkeypatch.setattr(rs, f, lambda n: str(base))
    monkeypatch.setattr(rs, "user_input_folder", lambda n: str(base / "entrada"))
    monkeypatch.setattr(rs, "user_output_folder", lambda n: str(base / "salida"))
    monkeypatch.setattr(rs, "user_recovery_folder", lambda n: str(base / "recuperacion"))
    monkeypatch.delenv("EDITOR_RETENTION_DAYS", raising=False)
    monkeypatch.delenv("EDITOR_RETENTION_SOURCE_DAYS", raising=False)
    return r, base


def _dia(base, sub, d: date, fichero="v.mp4"):
    p = base / sub / d.isoformat()
    p.mkdir(parents=True, exist_ok=True)
    (p / fichero).write_bytes(b"x" * 10)
    return p


def _user(override=None):
    return SimpleNamespace(id="U", name="cli", retention_days_override=override)


def test_config_por_defecto_y_override(entorno):
    r, _ = entorno
    assert config.retention_days() == 30
    assert config.retention_source_days() == 10
    r.set_str("settings:retention_days", "15")
    assert config.retention_days() == 15
    assert config.user_retention_days(_user()) == 15
    assert config.user_retention_days(_user(0)) == 0
    assert config.day_expires_at(_user(0), "2026-11-01") is None
    assert config.day_expires_at(_user(10), "2026-11-01") == "2026-11-11"


def test_borra_lo_caducado_y_respeta_lo_reciente(entorno):
    r, base = entorno
    viejo_in = _dia(base, "entrada", HOY - timedelta(days=11))
    nuevo_in = _dia(base, "entrada", HOY - timedelta(days=10))
    viejo_out = _dia(base, "salida", HOY - timedelta(days=31))
    nuevo_out = _dia(base, "salida", HOY - timedelta(days=30))
    rec = base / "recuperacion"
    rec.mkdir()
    (rec / "viejo.mp4").write_bytes(b"x")
    (rec / "nuevo.mp4").write_bytes(b"x")
    t = time.time() - 11 * 86400
    os.utime(rec / "viejo.mp4", (t, t))
    d = (HOY - timedelta(days=31)).isoformat()
    r.sets[f"webdays_sent:U"] = {d}
    r.kv[f"webday_jobs:U:{d}"] = [{"job_id": "j1"}]

    sim = rs.sweep_user(_user(), dry_run=True, open_ids=set())
    assert len(sim) == 3 and viejo_in.exists() and viejo_out.exists()

    rs.sweep_user(_user(), dry_run=False, open_ids=set())
    assert not viejo_in.exists() and nuevo_in.exists()
    assert not viejo_out.exists() and nuevo_out.exists()
    assert not (rec / "viejo.mp4").exists() and (rec / "nuevo.mp4").exists()
    assert rs.expired_days("U") == {d}
    assert d not in r.sets["webdays_sent:U"]
    assert f"webday_jobs:U:{d}" not in r.kv


def test_no_borra_con_trabajos_abiertos_ni_con_permiso(entorno):
    r, base = entorno
    d = HOY - timedelta(days=40)
    ent = _dia(base, "entrada", d)
    sal = _dia(base, "salida", d)
    r.kv[f"webday_jobs:U:{d.isoformat()}"] = [{"job_id": "abierto"}]
    assert rs.sweep_user(_user(), dry_run=False, open_ids={"abierto"}) == []
    assert ent.exists() and sal.exists()
    # Permiso especial: editados nunca; originales sí (sin trabajos abiertos).
    hechos = rs.sweep_user(_user(0), dry_run=False, open_ids=set())
    assert [h["tipo"] for h in hechos] == ["originales"]
    assert sal.exists() and not ent.exists()


def test_sin_cola_no_borra_nada(entorno, monkeypatch):
    monkeypatch.setattr(rs, "open_job_ids", lambda queue=None: None)
    monkeypatch.setattr(rs.UserRepo, "list_all", lambda self: [_user()])
    assert rs.sweep(dry_run=False) == []


def test_lo_que_el_montaje_no_deja_lo_borra_la_cuenta_de_subidas(entorno, monkeypatch):
    """Originales subidos por la web: no son de la cuenta del montaje (EIO)."""
    _, base = entorno
    viejo = _dia(base, "entrada", HOY - timedelta(days=20))
    llamadas = []
    from src.editor_auto.services import drive_uploads

    def _rm_falla(p):
        raise OSError(5, "Input/output error")

    def _api(user, rel):
        llamadas.append((user, rel))
        import shutil
        shutil.rmtree(viejo, ignore_errors=True)
        return True

    monkeypatch.setattr(rs.shutil, "rmtree", lambda p, ignore_errors=False: (
        None if ignore_errors else _rm_falla(p)))
    monkeypatch.setattr(drive_uploads, "is_configured", lambda: True)
    monkeypatch.setattr(drive_uploads, "delete_user_path", _api)
    hechos = rs.sweep_user(_user(), dry_run=False, open_ids=set())
    assert llamadas == [("cli", ["entrada", viejo.name])]
    assert not hechos[0].get("error")

    # Si la API tampoco puede, queda el error y no se da por borrado.
    viejo2 = _dia(base, "entrada", HOY - timedelta(days=21))
    monkeypatch.setattr(drive_uploads, "delete_user_path", lambda u, r: False)
    hechos = rs.sweep_user(_user(), dry_run=False, open_ids=set())
    assert hechos[0].get("error") and viejo2.exists()
