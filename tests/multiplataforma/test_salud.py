"""Vigía de salud de Multiplataforma: incidencias y deduplicación (sin red)."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path

from src.multiplataforma.services import salud

RAIZ = Path(__file__).resolve().parents[2]
AHORA = dt.datetime(2026, 11, 9, 21, 0, tzinfo=dt.timezone.utc).timestamp()
H, D = 3600, 86400


def _claves(incs):
    return sorted(i["clave"] for i in incs)


# ── tokens y Threads ───────────────────────────────────────────────────────

def test_token_invalido_es_grave_y_notifica():
    incs = salud.de_tokens("viva_shop", {"instagram": {"valido": False, "error": "(190) Session has expired"}}, AHORA)
    assert len(incs) == 1 and incs[0]["nivel"] == "grave" and incs[0]["notificar"]
    assert "(190)" in incs[0]["texto"]


def test_token_que_caduca_pronto_y_sin_permiso_de_comentario():
    tokens = {"facebook": {"valido": True, "expira": AHORA + 2 * D, "scopes": ["pages_show_list"]},
              "instagram": {"valido": True, "expira": 0, "scopes": []}}  # 0 = no caduca
    incs = salud.de_tokens("ama_shop", tokens, AHORA)
    assert _claves(incs) == ["token:ama_shop:facebook:caduca", "token:ama_shop:facebook:sin_comentario"]


def test_token_bien_no_da_nada():
    t = {"facebook": {"valido": True, "expira": AHORA + 50 * D, "scopes": ["pages_manage_engagement"]},
         "threads": {"valido": True, "expira": None, "scopes": None}}
    assert salud.de_tokens("x", t, AHORA) == []


def test_threads_sin_renovar():
    t = {"threads": {"valido": True}}
    assert salud.de_threads("x", t, AHORA - 8 * D, AHORA) == []
    assert salud.de_threads("x", t, AHORA - 20 * D, AHORA)[0]["nivel"] == "aviso"
    assert salud.de_threads("x", t, AHORA - 55 * D, AHORA)[0]["nivel"] == "grave"
    assert salud.de_threads("x", {}, AHORA - 55 * D, AHORA) == []  # sin Threads conectado
    assert salud.de_threads("x", t, None, AHORA) == []


# ── cola ───────────────────────────────────────────────────────────────────

def _pub(cuenta, hace_s, estado, errores=None, plataformas=None):
    return {"id": "p", "cuenta": cuenta, "programada_en": AHORA - hace_s, "estado": estado,
            "plataformas": plataformas if plataformas is not None else list(estado), "errores": errores or {}}


def test_cola_atascada_fallida_y_simulado_ignorado():
    pubs = [
        _pub("viva_shop", 3 * H, {"instagram": "error"}, {"instagram": "HTTP 400 en GET https://g/1784140900 x"}),
        _pub("viva_shop", 2 * H, {"instagram": "pendiente"}),
        _pub("viva_shop", 30 * 60, {"instagram": "pendiente"}),  # aún en margen
        _pub("ama_shop", 5 * H, {"facebook": "fallido"}, {"facebook": "(9004) Only photo or video"}),
        _pub("ama_shop", 3 * D, {"facebook": "fallido"}),  # fuera de las 48 h
        _pub("ama_shop", 5 * H, {"pinterest": "simulado", "instagram": "publicado"}),
        _pub("ama_shop", 5 * H, {"threads": "pendiente"}, plataformas=["instagram"]),  # plataforma quitada
    ]
    incs = {i["clave"]: i for i in salud.de_cola(pubs, AHORA)}
    assert sorted(incs) == ["cola:ama_shop:facebook:fallida", "cola:viva_shop:instagram:atascada"]
    at = incs["cola:viva_shop:instagram:atascada"]["texto"]
    assert "2 publicación(es)" in at and "hace 3 h" in at and "<url>" in at and "1784140900" not in at
    assert "(9004)" in incs["cola:ama_shop:facebook:fallida"]["texto"]


def test_normalizar_agrupa_ids_y_urls():
    a = salud.normalizar("instagram: HTTP 400 en GET https://graph.facebook.com/v24.0/17841409006802526/x: Cannot")
    b = salud.normalizar("instagram: HTTP 400 en GET https://graph.facebook.com/v24.0/17841411685541259/x: Cannot")
    assert a == b and "<url>" in a
    assert salud.normalizar(None) == ""


# ── Facebook a cero ────────────────────────────────────────────────────────

def test_fb_cero():
    viejos = [{"ts": AHORA - 3 * D, "plays": p} for p in (0, 1, 2)]
    assert salud.de_fb_cero("x", viejos, AHORA)[0]["clave"] == "fb:x:cero"
    assert salud.de_fb_cero("x", viejos + [{"ts": AHORA - 3 * D, "plays": 40}], AHORA) == []
    recientes = [{"ts": AHORA - H, "plays": 0}] * 5  # < 48 h: no se juzga
    assert salud.de_fb_cero("x", viejos[:2] + recientes, AHORA) == []
    assert salud.de_fb_cero("x", viejos[:2] + [{"ts": AHORA - 3 * D, "plays": None}], AHORA) == []


# ── tick.log ───────────────────────────────────────────────────────────────

def _bloque(hace_s, cuerpo="{}\n"):
    iso = dt.datetime.fromtimestamp(AHORA - hace_s, dt.timezone.utc).isoformat(timespec="seconds")
    return f"=== {iso}\n{cuerpo}"


def test_log_tick_parado_y_excepcion():
    traza = "Traceback (most recent call last):\n  File \"x\"\nAttributeError: module has no attribute 'garantia_diaria_todas'\n"
    log = "basura de un bloque cortado\n" + _bloque(90 * 60) + _bloque(75 * 60, traza)
    incs = {i["clave"]: i for i in salud.de_log(log, AHORA)}
    assert incs["tick:parado"]["nivel"] == "grave" and incs["tick:parado"]["notificar"]
    assert "AttributeError" in incs["tick:excepcion"]["texto"]


def test_log_sano_y_traceback_viejo_no_cuenta():
    traza = "Traceback (most recent call last):\nValueError: x\n"
    log = _bloque(100 * 60, traza) + "".join(_bloque(m * 60) for m in (60, 45, 30, 15, 1))
    assert salud.de_log(log, AHORA) == []
    assert salud.de_log("", AHORA)[0]["clave"] == "tick:sin_datos"


# ── deduplicación ──────────────────────────────────────────────────────────

def test_filtrar_avisa_una_vez_recuerda_escala_y_resuelve():
    aviso = salud._inc("fb:x:cero", "aviso", "FB a cero")
    info = salud._inc("token:x:facebook:sin_comentario", "info", "sin permiso")
    av, est = salud.filtrar_nuevas([aviso, info], {}, AHORA)
    assert _claves(av) == ["fb:x:cero", "token:x:facebook:sin_comentario"]

    av, est = salud.filtrar_nuevas([aviso, info], est, AHORA + H)
    assert av == []

    av, est = salud.filtrar_nuevas([aviso, info], est, AHORA + 8 * D)  # recordatorio, solo el no-info
    assert _claves(av) == ["fb:x:cero"] and av[0]["texto"].startswith("Sigue igual desde hace 8 días")
    assert not av[0]["notificar"]

    grave = salud._inc("fb:x:cero", "grave", "peor", notificar=True)
    av, est = salud.filtrar_nuevas([grave, info], est, AHORA + 8 * D + H)  # escala → se avisa ya
    assert av == [grave]

    av, est = salud.filtrar_nuevas([], est, AHORA + 9 * D)  # desaparece: resuelto (el info, en silencio)
    assert len(av) == 1 and av[0]["texto"] == "✅ Resuelto: peor" and av[0]["nivel"] == "info"
    assert est == {}


def test_analizar_junta_todo():
    datos = {"cuentas": {"viva_shop": {"tokens": {"threads": {"valido": False, "error": "x"}},
                                       "threads_renovado": AHORA - 20 * D, "fb_reels": []}},
             "pubs": [_pub("viva_shop", 3 * H, {"threads": "error"})]}
    claves = _claves(salud.analizar(datos, None, AHORA))
    assert claves == ["cola:viva_shop:threads:atascada", "threads:viva_shop:sin_renovar",
                      "token:viva_shop:threads:invalido"]


# ── script del host ────────────────────────────────────────────────────────

def _script():
    spec = importlib.util.spec_from_file_location("mp_salud_av", RAIZ / "scripts" / "multiplataforma_salud_avisar.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_script_seco_no_manda_ni_guarda(tmp_path, monkeypatch, capsys):
    av = _script()
    datos = tmp_path / "d.json"
    datos.write_text(json.dumps({"cuentas": {"x": {"tokens": {"instagram": {"valido": False}}}}}))
    estado = tmp_path / "e.json"
    monkeypatch.setattr(av, "mandar", lambda *a: (_ for _ in ()).throw(AssertionError("no debe mandar")))
    monkeypatch.setattr("sys.argv", ["x", "--datos", str(datos), "--log", str(tmp_path / "no"),
                                     "--estado", str(estado), "--dry-run"])
    assert av.main() == 0
    assert not estado.exists() and "token de instagram no vale" in capsys.readouterr().out


def test_script_reintenta_lo_que_no_llego(tmp_path, monkeypatch):
    av = _script()
    datos = tmp_path / "d.json"
    datos.write_text("{roto")  # recolector caído → incidencia propia
    estado = tmp_path / "e.json"
    monkeypatch.setattr(av, "_cfg", lambda: {"PANEL_TOKEN": "t"})
    respuestas = iter(["error 500", "ok 200", "ok 200"])
    mandados = []
    monkeypatch.setattr(av, "mandar", lambda a, cfg: (mandados.append(a["clave"]), next(respuestas))[1])
    monkeypatch.setattr("sys.argv", ["x", "--datos", str(datos), "--log", str(tmp_path / "no"), "--estado", str(estado)])
    av.main()
    assert json.loads(estado.read_text()) == {}  # falló el envío: no queda como avisado
    av.main()
    guardado = json.loads(estado.read_text())
    assert "recolector:fallo" in guardado and mandados == ["recolector:fallo", "recolector:fallo"]
    av.main()
    assert len(mandados) == 2  # ya avisado: no se repite
