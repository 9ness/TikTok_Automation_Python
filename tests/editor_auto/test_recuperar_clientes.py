"""Avisos para recuperar clientes: reglas, una vez por regla, baja y simular."""
from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from src.editor_auto.services import estadisticas as est
from src.editor_auto.services import recuperar_clientes as rc

DIA = 86400
AHORA = time.time()


def _iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR_STATS_DB", str(tmp_path / "s" / "editor.sqlite"))
    monkeypatch.setenv("EDITOR_STATS_SALT", "sal-test")
    monkeypatch.delenv("EDITOR_RECUPERAR_ENVIAR", raising=False)
    est._reset_para_tests()
    yield
    est._reset_para_tests()


def _cuenta(email, *, alta_dias=5, plan=None, prueba=3, rol="standard", **kw):
    return {"email": email, "name": "Ana López", "role": rol, "planId": plan,
            "trialVideos": prueba, "createdAt": _iso(AHORA - alta_dias * DIA), **kw}


def _trabajo(usuario, hace_dias):
    ini = AHORA - hace_dias * DIA
    est.registrar_trabajo({"job_id": f"{usuario}-{hace_dias}", "program": "editor_auto",
                           "user": usuario, "started_at": ini, "finished_at": ini + 60,
                           "total_usd": 0.01, "meta": {}, "lines": []})


def _reglas(cands):
    return {c["email"]: c["regla"] for c in cands}


def test_reglas_basicas():
    _trabajo("bea", 5)    # prueba gastada, último vídeo hace 5 d
    _trabajo("eva", 1)    # prueba gastada pero reciente
    _trabajo("pro", 10)   # plan parado
    _trabajo("pro2", 2)   # plan activo
    cuentas = [
        _cuenta("ana@x.com", alta_dias=3),                     # sin empezar
        _cuenta("nuevo@x.com", alta_dias=1),                   # aún no 48 h
        _cuenta("bea@x.com", prueba=0),
        _cuenta("eva@x.com", prueba=0),
        _cuenta("pro@x.com", plan="basic", alta_dias=30),
        _cuenta("pro2@x.com", plan="basic", alta_dias=30),
        _cuenta("admin@x.com", rol="admin"),
        _cuenta("ban@x.com", banned=True),
    ]
    usuarios = {"bea@x.com": "bea", "eva@x.com": "eva", "pro@x.com": "pro", "pro2@x.com": "pro2"}
    r = _reglas(rc.candidatos(cuentas, usuarios, ahora=AHORA))
    assert r == {"ana@x.com": "sin_empezar", "bea@x.com": "prueba_gastada",
                 "pro@x.com": "plan_parado"}


def test_plan_parado_espera_a_tener_7_dias_de_datos():
    _trabajo("otro", 2)  # los datos empiezan hace 2 días
    c = [_cuenta("pro@x.com", plan="basic", alta_dias=60)]
    assert rc.candidatos(c, {}, ahora=AHORA) == []
    assert _reglas(rc.candidatos(c, {}, ahora=AHORA + 6 * DIA)) == {"pro@x.com": "plan_parado"}


def test_simular_no_manda_nada():
    enviados = []
    cands = rc.candidatos([_cuenta("ana@x.com")], {}, ahora=AHORA)
    r = rc.enviar(cands, enviar_fn=lambda *a: enviados.append(a) or {"ok": True})
    assert r == {"enviados": 0, "simulados": 1, "errores": 0} and not enviados
    assert rc.maybe_pasada() is None


def test_envio_una_vez_por_regla(monkeypatch):
    monkeypatch.setenv("EDITOR_RECUPERAR_ENVIAR", "1")
    enviados = []
    fn = lambda to, asunto, html, texto: enviados.append((to, asunto, html, texto)) or {"ok": True}
    cuentas = [_cuenta("ana@x.com")]
    assert rc.enviar(rc.candidatos(cuentas, {}, ahora=AHORA), enviar_fn=fn)["enviados"] == 1
    to, asunto, html, texto = enviados[0]
    assert to == ["ana@x.com"] and "Ana" in html and "/api/v1/editor-auto/web/baja?c=" in html
    assert rc.candidatos(cuentas, {}, ahora=AHORA) == []  # ya avisada
    # Un fallo de SMTP no cuenta como avisado.
    fallo = lambda *a: {"ok": False, "error": "smtp"}
    r = rc.enviar(rc.candidatos([_cuenta("luis@x.com")], {}, ahora=AHORA), enviar_fn=fallo)
    assert r["errores"] == 1 and rc.candidatos([_cuenta("luis@x.com")], {}, ahora=AHORA)


def test_baja_con_firma():
    cid = est.cuenta_id("ana@x.com")
    assert not rc.dar_de_baja(cid, "firma-mala")
    url = rc.enlace_baja("ana@x.com")
    firma = url.split("f=")[1]
    assert rc.dar_de_baja(cid, firma)
    assert rc.candidatos([_cuenta("ana@x.com")], {}, ahora=AHORA) == []


def test_componer_todas_las_reglas_y_sin_html_inyectado():
    for regla in rc.REGLAS:
        asunto, html, texto = rc.componer({"email": "a@x.com", "nombre": "<b>Eve", "regla": regla})
        assert asunto and "<b>Eve" not in html and "&lt;b&gt;Eve" in html
        assert "No quiero más avisos" in texto


def test_endpoint_baja(monkeypatch):
    from fastapi.testclient import TestClient
    from src.api.main import app
    cli = TestClient(app)
    cid = est.cuenta_id("ana@x.com")
    firma = rc.enlace_baja("ana@x.com").split("f=")[1]
    assert cli.get(f"/api/v1/editor-auto/web/baja?c={cid}&f=mala").status_code == 400
    r = cli.get(f"/api/v1/editor-auto/web/baja?c={cid}&f={firma}")
    assert r.status_code == 200 and "no te mandaremos" in r.text
