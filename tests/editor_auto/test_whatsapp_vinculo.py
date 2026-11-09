"""Tests del vinculo WhatsApp <-> cuenta web (sin red)."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from src.editor_auto.services import whatsapp_vinculo as v


class FakeR:
    def __init__(self):
        self.kv = {}
        self.sets = {}
        self.ttl = {}

    def is_available(self):
        return True

    def get_str(self, k):
        x = self.kv.get(k)
        return x if isinstance(x, str) else None

    def set_str(self, k, val):
        self.kv[k] = val
        return True

    def get_json(self, k):
        x = self.kv.get(k)
        return json.loads(x) if isinstance(x, str) and x[:1] in "{[" else None

    def set_json(self, k, val):
        self.kv[k] = json.dumps(val)
        return True

    def delete(self, k):
        return self.kv.pop(k, None) is not None

    def incr(self, k):
        self.kv[k] = str(int(self.kv.get(k, "0")) + 1)
        return int(self.kv[k])

    def expire(self, k, s):
        self.ttl[k] = s
        return True

    def sadd(self, k, m):
        self.sets.setdefault(k, set()).add(m)

    def smembers(self, k):
        return list(self.sets.get(k, []))


class FakeWeb:
    def __init__(self, cuentas):
        self.c = cuentas

    def get(self, email):
        return self.c.get((email or "").strip().lower())


CUENTA = {"email": "ana@x.com", "username": "Ana", "planId": "pro"}


@pytest.mark.parametrize("txt,esp", [
    ("+34 612-345-678", "34612345678"),
    ("612345678", "34612345678"),
    ("0034612345678", "34612345678"),
    ("(+52) 55 1234 5678", "525512345678"),
    ("12345", ""), ("", ""), (None, ""), ("1" * 16, ""),
    ("512345678", "512345678"),  # 9 digitos que no empiezan por 6-9: se deja
])
def test_normalizar(txt, esp):
    assert v.normalizar_telefono(txt) == esp


def _pedir(r, tel="612345678", email="ana@x.com", enviados=None):
    enviados = enviados if enviados is not None else []
    res = v.pedir_codigo(tel, email, redis=r, web_repo=FakeWeb({"ana@x.com": CUENTA}),
                         enviar=lambda to, s, h, t: enviados.append((to, s, t)) or {"ok": True})
    return res, enviados


def test_pedir_y_confirmar():
    r = FakeR()
    res, env = _pedir(r)
    assert res == {"ok": True}
    assert env[0][0] == ["ana@x.com"]
    cod = r.get_json("wa:codigo:34612345678")["codigo"]
    assert len(cod) == 6 and cod in env[0][2]
    assert r.ttl["wa:codigo:34612345678"] == 900
    ok = v.confirmar_codigo("+34 612 345 678", cod, redis=r, web_repo=FakeWeb({"ana@x.com": CUENTA}))
    assert ok == {"ok": True, "email": "ana@x.com", "nombre": "Ana"}
    assert v.email_de("612345678", redis=r) == "ana@x.com"
    assert v.telefono_de("ANA@x.com", redis=r) == "34612345678"
    assert r.get_json("wa:codigo:34612345678") is None
    assert v.desvincular("612345678", redis=r) is True
    assert v.email_de("612345678", redis=r) == "" and v.telefono_de("ana@x.com", redis=r) == ""
    assert v.desvincular("612345678", redis=r) is False


def test_cuenta_inexistente_no_se_revela():
    r = FakeR()
    env = []
    res = v.pedir_codigo("612345678", "nadie@x.com", redis=r, web_repo=FakeWeb({}),
                         enviar=lambda *a: env.append(a) or {"ok": True})
    assert res == {"ok": True} and env == []


def test_telefono_invalido_y_sin_email():
    r = FakeR()
    assert v.pedir_codigo("12", "a@b.c", redis=r, enviar=lambda *a: {})["motivo"] == "telefono"
    # sin enviar inyectado y SMTP sin configurar
    from src.editor_auto.services import email_notify
    orig = email_notify.is_configured
    email_notify.is_configured = lambda: False
    try:
        assert v.pedir_codigo("612345678", "a@b.c", redis=r)["motivo"] == "sin_email"
    finally:
        email_notify.is_configured = orig


def test_limite_de_peticiones():
    r = FakeR()
    for _ in range(3):
        assert _pedir(r)[0]["ok"] is True
    assert _pedir(r)[0] == {"ok": False, "motivo": "demasiados"}
    assert r.ttl["wa:pedidos:34612345678"] == 3600


def test_codigo_malo_intentos_y_caducado():
    r = FakeR()
    web = FakeWeb({"ana@x.com": CUENTA})
    assert v.confirmar_codigo("612345678", "123456", redis=r, web_repo=web)["motivo"] == "caducado"
    _pedir(r)
    real = r.get_json("wa:codigo:34612345678")["codigo"]
    mal = "000000" if real != "000000" else "111111"
    for _ in range(4):
        assert v.confirmar_codigo("612345678", mal, redis=r, web_repo=web)["motivo"] == "codigo"
    assert v.confirmar_codigo("612345678", mal, redis=r, web_repo=web)["motivo"] == "intentos"
    # bloqueado aunque ahora acierte
    assert v.confirmar_codigo("612345678", real, redis=r, web_repo=web) == {"ok": False, "motivo": "intentos"}
    assert v.email_de("612345678", redis=r) == ""


def test_revincular_limpia_el_anterior():
    r = FakeR()
    web = FakeWeb({"ana@x.com": CUENTA})
    r.set_str("wa:by_email:ana@x.com", "34699999999")
    r.set_str("wa:by_phone:34699999999", "ana@x.com")
    _pedir(r)
    cod = r.get_json("wa:codigo:34612345678")["codigo"]
    assert v.confirmar_codigo("612345678", cod, redis=r, web_repo=web)["ok"]
    assert v.email_de("699999999", redis=r) == ""
    assert v.telefono_de("ana@x.com", redis=r) == "34612345678"


# ───────────── resumen_cliente ─────────────

def _montar(monkeypatch, *, cuenta, jobs, jobs_meta, hoy="2026-11-09"):
    from src.api.routers.editor_auto import web_upload as wu
    from src.editor_auto import config as cfg
    from src.editor_auto.models import EditorUser
    from src.queue.models import Job, JobStatus
    import src.editor_auto.repos.web_account_repo as war

    monkeypatch.setenv("WEB_UPLOAD_SECRET", "s3cret")
    monkeypatch.setenv("EDITOR_BOX_PUBLIC_URL", "https://box.test/")
    r = FakeR()
    r.set_str("wa:by_phone:34612345678", "ana@x.com")
    user = EditorUser(name="ana", account_email="ana@x.com")
    web = FakeWeb({"ana@x.com": cuenta})
    monkeypatch.setattr(wu, "get_editor_redis", lambda: r)
    monkeypatch.setattr(war, "get_web_account_repo", lambda: web)
    monkeypatch.setattr(cfg, "manual_approval_enabled", lambda: False)
    monkeypatch.setattr(cfg, "day_send_open", lambda d: True)
    monkeypatch.setattr(wu, "_job_score", lambda j: 95)
    monkeypatch.setattr(wu, "_job_deliverable", lambda j, s: True)
    import src.editor_auto.services.retention_sweeper as rs
    monkeypatch.setattr(rs, "expired_days", lambda uid: set())
    objs = []
    for jid, st, out in jobs:
        j = Job(mode="editor_auto", title=jid, params={})
        j.id = jid
        j.status = JobStatus(st)
        j.result_path = out
        objs.append(j)
    queue = SimpleNamespace(get_all=lambda: objs)
    for dia, metas in jobs_meta.items():
        r.set_json(f"webday_jobs:{user.id}:{dia}", metas)
        r.sadd(f"webdays_sent:{user.id}", dia)
    repo = SimpleNamespace(get_by_account_email=lambda e: user)
    return r, web, repo, queue, user


def test_resumen_no_vinculado():
    assert v.resumen_cliente("612345678", redis=FakeR()) == {"vinculado": False}


def test_resumen_con_cuota_y_enlaces(monkeypatch):
    r, web, repo, queue, user = _montar(
        monkeypatch, cuenta=dict(CUENTA),
        jobs=[("j1", "completed", "/x/a_editado.mp4"), ("j2", "completed", "/x/b_editado.mp4"),
              ("j3", "running", None)],
        jobs_meta={
            "2026-11-09": [{"job_id": "j1", "filename": "a.mp4"}, {"job_id": "j3", "filename": "c.mp4"}],
            "2026-11-08": [{"job_id": "j2", "filename": "b.mp4"}],
        },
    )
    res = v.resumen_cliente("+34612345678", redis=r, web_repo=web, user_repo=repo, queue=queue)
    assert res["vinculado"] and res["plan_id"] == "pro" and res["es_prueba"] is False
    assert (res["limite_dia"], res["usados_hoy"], res["quedan_hoy"]) == (5, 2, 3)
    assert res["prueba_restantes"] is None and res["hoy"]
    d_hoy, d_ayer = res["dias"]
    assert d_hoy["dia"] == "2026-11-09" and d_ayer["dia"] == "2026-11-08"
    # todo-o-nada: hoy hay uno editando, el listo se retiene
    assert d_hoy["listos"] == 0 and d_hoy["en_revision"] == 1 and d_hoy["en_curso"] == 1
    assert d_hoy["todo_listo"] is False and d_hoy["videos"][0]["enlace"] is None
    assert d_ayer["todo_listo"] and d_ayer["listos"] == 1
    vid = d_ayer["videos"][0]
    assert vid["estado"] == "listo" and vid["nombre"] == "b_editado.mp4"
    assert vid["enlace"].startswith(
        "https://box.test/api/v1/editor-auto/web/download?day=2026-11-08&file=b_editado.mp4&ticket=")
    from src.api.web_ticket import verify_ticket
    c = verify_ticket(vid["enlace"].split("ticket=")[1])
    assert c.email == "ana@x.com" and c.scope == "download"


def test_resumen_prueba(monkeypatch):
    r, web, repo, queue, _ = _montar(
        monkeypatch, cuenta={"email": "ana@x.com", "name": "Ana", "planId": None, "trialVideos": 2},
        jobs=[], jobs_meta={},
    )
    res = v.resumen_cliente("612345678", redis=r, web_repo=web, user_repo=repo, queue=queue)
    assert res["es_prueba"] and res["prueba_restantes"] == 2 and res["quedan_hoy"] == 2
    assert res["dias"] == [] and res["nombre"] == "Ana"
