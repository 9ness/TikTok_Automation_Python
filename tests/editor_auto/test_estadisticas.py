"""Estadísticas locales (SQLite) del Editor Auto y de nebulabsmedia.com."""
from __future__ import annotations

import pytest

from src.editor_auto.services import estadisticas as est

UA_MOVIL = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Mobile Safari"
UA_PC = "Mozilla/5.0 (Windows NT 10.0) Chrome/120"


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR_STATS_DB", str(tmp_path / "s" / "editor.sqlite"))
    monkeypatch.setenv("EDITOR_STATS_SALT", "sal-test")
    est._reset_para_tests()
    yield
    est._reset_para_tests()


def _job(jid, user, ini, seg, coste, tools="subs+cut"):
    return {"job_id": jid, "program": "editor_auto", "user": user, "started_at": ini,
            "finished_at": ini + seg, "total_usd": coste, "meta": {"tools_key": tools},
            "lines": []}


def test_beacon_filtra_bots_rutas_y_tipos():
    assert est.registrar_beacon(tipo="visita", ruta="/precios?x=1", ref="https://www.tiktok.com/",
                                utm=None, ip="1.2.3.4", agente=UA_MOVIL)
    assert not est.registrar_beacon(tipo="visita", ruta="/panel", ref=None, utm=None,
                                    ip="1.2.3.4", agente=UA_PC)
    assert not est.registrar_beacon(tipo="visita", ruta="/", ref=None, utm=None,
                                    ip="1.2.3.4", agente="Googlebot/2.1")
    assert not est.registrar_beacon(tipo="pago", ruta="/", ref=None, utm=None,
                                    ip="1.2.3.4", agente=UA_PC)  # solo pasos web
    c = est._db()
    fila = c.execute("SELECT ruta, origen, movil, sesion FROM eventos").fetchall()
    assert len(fila) == 1
    ruta, origen, movil, sesion = fila[0]
    assert (ruta, origen, movil) == ("/precios", "tiktok", 1)
    assert "1.2.3.4" not in sesion  # no se guarda la IP


def test_sesion_cambia_cada_dia_y_no_guarda_ip():
    a = est.sesion_anonima("1.2.3.4", UA_PC, "2026-11-09")
    b = est.sesion_anonima("1.2.3.4", UA_PC, "2026-11-10")
    assert a != b and len(a) == 16


def test_embudo_cuenta_sesiones_unicas_y_porcentajes():
    for _ in range(3):  # misma persona recargando = 1
        est.registrar_beacon(tipo="visita", ruta="/", ref=None, utm=None, ip="1.1.1.1", agente=UA_PC)
    est.registrar_beacon(tipo="visita", ruta="/", ref=None, utm=None, ip="2.2.2.2", agente=UA_PC)
    est.registrar_beacon(tipo="precios", ruta="/precios", ref=None, utm=None, ip="2.2.2.2", agente=UA_PC)
    cid = est.cuenta_id("a@b.com")
    assert est.registrar_evento("prueba_empezada", cuenta=cid, unico=True)
    assert not est.registrar_evento("prueba_empezada", cuenta=cid, unico=True)
    pasos = {p["paso"]: p for p in est.embudo()}
    assert pasos["visita"]["n"] == 2
    assert pasos["precios"]["n"] == 1 and pasos["precios"]["desde_anterior"] == 50.0
    assert pasos["prueba_empezada"]["n"] == 1


def test_evento_desconocido_no_se_apunta():
    assert not est.registrar_evento("hackeo")


def test_trabajo_idempotente_y_solo_editor():
    est.registrar_trabajo(_job("j1", "ana", 1_762_700_000, 120, 0.05))
    est.registrar_trabajo(_job("j1", "ana", 1_762_700_000, 120, 0.05))  # repetido
    est.registrar_trabajo({**_job("j2", "ana", 1_762_700_000, 10, 1.0), "program": "tiktok_shop"})
    n = est._db().execute("SELECT COUNT(*) FROM trabajos").fetchone()[0]
    assert n == 1


def test_coste_por_video_y_por_herramientas():
    ini = __import__("time").time() - 3600
    est.registrar_trabajo(_job("a", "ana", ini, 100, 0.02, "subs"))
    est.registrar_trabajo(_job("b", "ana", ini, 300, 0.06, "subs+cut"))
    est.registrar_trabajo(_job("c", "luis", ini, 200, 0.04, "subs+cut"))
    r = est.coste_por_video()
    assert r["videos"] == 3
    assert r["coste_usd"] == pytest.approx(0.12)
    assert r["coste_medio_usd"] == pytest.approx(0.04)
    assert r["seg_medio"] == pytest.approx(200.0)
    assert r["seg_max"] == pytest.approx(300.0)
    top = r["por_herramientas"][0]
    assert top["herramientas"] == "subs+cut" and top["videos"] == 2


def test_cuentas_detectan_alta_y_primer_pago():
    hoy = est._hoy()
    cuentas = [{"email": "Cli@x.com", "createdAt": f"{hoy}T10:00:00Z", "trialVideos": 2},
               {"email": "admin@x.com", "createdAt": f"{hoy}T10:00:00Z", "role": "admin",
                "planId": "pro"}]
    assert est.actualizar_cuentas(cuentas, {"cli@x.com": "cli"}) == 2
    cid = est.cuenta_id("cli@x.com")
    est.registrar_evento("prueba_empezada", cuenta=cid, unico=True)
    conv = est.conversion()
    assert conv["altas"] == 1 and conv["prueba"] == 1 and conv["pago"] == 0  # admin fuera

    # Pasa a pagar: un solo evento «pago» aunque se refresque varias veces.
    cuentas[0]["planId"] = "basico"
    est.actualizar_cuentas(cuentas, {"cli@x.com": "cli"})
    est.actualizar_cuentas(cuentas, {"cli@x.com": "cli"})
    pagos = est._db().execute("SELECT COUNT(*) FROM eventos WHERE tipo='pago'").fetchone()[0]
    assert pagos == 1
    conv = est.conversion()
    assert conv["pago"] == 1 and conv["pct_pago"] == 100.0
    # No se guarda el email en claro.
    assert not est._db().execute("SELECT 1 FROM cuentas WHERE cuenta LIKE '%@%'").fetchone()


def test_por_cliente_une_cuenta_y_trabajos():
    hoy = est._hoy()
    est.actualizar_cuentas([{"email": "c@x.com", "createdAt": hoy, "trialVideos": 1}],
                           {"c@x.com": "cli"})
    t = __import__("time").time() - 60
    est.registrar_trabajo(_job("x1", "cli", t, 60, 0.03))
    est.registrar_trabajo(_job("x2", "cli", t, 120, 0.05))
    fila = est.por_cliente()[0]
    assert fila["usuario"] == "cli" and fila["videos"] == 2
    assert fila["coste_por_video"] == pytest.approx(0.04)
    assert fila["seg_medio"] == pytest.approx(90.0)


def test_resumen_completo_con_base_vacia():
    r = est.resumen()
    assert set(r) == {"rango", "embudo", "conversion", "coste", "por_dia", "clientes"}
    assert len(r["por_dia"]) == 30
    assert r["coste"]["videos"] == 0


def test_fallo_de_disco_no_lanza(monkeypatch):
    monkeypatch.setenv("EDITOR_STATS_DB", "/proc/no/se/puede/x.sqlite")
    est._reset_para_tests()
    assert est.registrar_evento("visita", sesion="s") is False
    est.registrar_trabajo(_job("z", "u", 1.0, 1, 0.0))  # no lanza


# ── Endpoints: beacon público y resumen de admin ──────────────────────────────
@pytest.fixture
def cliente():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.api.dependencies import get_current_user
    from src.api.routers.editor_auto import web_upload as w

    app = FastAPI()
    app.include_router(w.router)
    app.dependency_overrides[get_current_user] = lambda: "admin"
    w._BEACON_VENTANA.clear()
    return TestClient(app)


def test_beacon_texto_plano_y_resumen_admin(cliente):
    cuerpo = '{"tipo":"visita","ruta":"/","ref":"https://instagram.com/x"}'
    r = cliente.post("/api/v1/editor-auto/web/evento", content=cuerpo,
                     headers={"content-type": "text/plain", "user-agent": UA_MOVIL,
                              "x-forwarded-for": "9.9.9.9, 10.0.0.1"})
    assert r.status_code == 204
    # Basura: 204 igual y no apunta.
    r = cliente.post("/api/v1/editor-auto/web/evento", content="no json",
                     headers={"user-agent": UA_PC})
    assert r.status_code == 204
    res = cliente.get("/api/v1/editor-auto/web/admin/estadisticas").json()
    visita = next(p for p in res["embudo"] if p["paso"] == "visita")
    assert visita["n"] == 1
    from src.api.exceptions import ValidationError
    with pytest.raises(ValidationError):  # (la app real lo convierte en 422)
        cliente.get("/api/v1/editor-auto/web/admin/estadisticas?desde=mal")


def test_beacon_limite_por_ip(cliente, monkeypatch):
    from src.api.routers.editor_auto import web_upload as w
    monkeypatch.setattr(w, "_BEACON_MAX_MIN", 2)
    for _ in range(5):
        cliente.post("/api/v1/editor-auto/web/evento",
                     content='{"tipo":"precios","ruta":"/precios"}',
                     headers={"user-agent": UA_PC, "x-forwarded-for": "8.8.8.8"})
    n = est._db().execute("SELECT COUNT(*) FROM eventos").fetchone()[0]
    assert n == 2


def test_apuntar_envio_prueba_una_vez():
    from types import SimpleNamespace

    from src.api.routers.editor_auto import web_upload as w
    u = SimpleNamespace(account_email="p@x.com")
    w._apuntar_envio(u, 2, prueba=True)
    w._apuntar_envio(u, 1, prueba=True)
    c = est._db()
    assert c.execute("SELECT COUNT(*) FROM eventos WHERE tipo='prueba_empezada'").fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM eventos WHERE tipo='video_enviado'").fetchone()[0] == 2


def test_fallidos_cuentan_coste_no_video():
    t = __import__("time").time() - 60
    est.registrar_trabajo(_job("ok", "u", t, 60, 0.03))
    est.registrar_trabajo({**_job("ko", "u", t, 30, 0.01), "meta": {"estado": "fallido"}})
    r = est.coste_por_video()
    assert r["videos"] == 1 and r["fallidos"] == 1
    assert r["coste_medio_usd"] == pytest.approx(0.04)  # coste real por vídeo entregado


def test_margen_prorratea_plan_y_separa_pruebas(monkeypatch):
    import time
    monkeypatch.setenv("EDITOR_EUR_POR_USD", "1")
    monkeypatch.setenv("EDITOR_EUR_MIN_RENDER", "0.1")
    hoy = est._hoy()
    est.actualizar_cuentas([
        {"email": "p@x.com", "createdAt": hoy, "planId": "pro"},          # 49 €/mes
        {"email": "t@x.com", "createdAt": hoy, "trialVideos": 3},          # prueba
        {"email": "a@x.com", "createdAt": hoy, "planId": "pro", "role": "admin"},
    ], {"p@x.com": "pago", "t@x.com": "prueba", "a@x.com": "jefe"})
    t = time.time() - 300
    est.registrar_trabajo(_job("m1", "pago", t, 120, 0.5))   # 0,5 € IA + 2 min × 0,1
    est.registrar_trabajo(_job("m2", "prueba", t, 60, 0.3))
    est.registrar_trabajo(_job("m3", "jefe", t, 60, 9.0))     # admin: fuera
    est.registrar_trabajo(_job("m4", "interno", t, 60, 0.1))  # sin cuenta web
    m = est.margen()
    fila = m["clientes"][0]
    # Pagó hoy → 1 día de los 7 del rango.
    assert fila["dias"] == 1 and fila["ingreso_eur"] == pytest.approx(round(49 / 30, 2))
    assert fila["coste_eur"] == pytest.approx(0.7)
    assert m["prueba"] == {"usuarios": 1, "videos": 1, "coste_eur": pytest.approx(0.4)}
    assert [o["usuario"] for o in m["otros"]] == ["interno"]
    assert m["total"]["coste_eur"] == pytest.approx(0.7 + 0.4 + 0.2)
    assert "jefe" not in str(m)
    assert "Margen Editor" in est.informe_margen_texto(m)


def test_margen_alerta_si_baja_del_umbral(monkeypatch):
    import time
    monkeypatch.setenv("EDITOR_EUR_POR_USD", "1")
    est.actualizar_cuentas([{"email": "s@x.com", "createdAt": "2026-01-01", "planId": "starter"}],
                           {"s@x.com": "caro"})
    est.registrar_trabajo(_job("c1", "caro", time.time() - 60, 30, 5.0))
    m = est.margen()
    assert m["total"]["margen_pct"] < 50
    assert any("caro" in a for a in m["alertas"])
    from scripts import editor_informe_margen as inf
    assert inf.main([]) == 2


def test_margen_base_vacia_y_endpoint(cliente):
    m = est.margen()
    assert m["total"]["ingreso_eur"] == 0 and m["alertas"] == []
    r = cliente.get("/api/v1/editor-auto/web/admin/margen").json()
    assert "texto" in r and r["clientes"] == []
