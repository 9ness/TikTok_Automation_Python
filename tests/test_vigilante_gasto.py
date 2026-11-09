"""Vigilante de gasto y salud (#293): análisis puro con jobs falsos."""

from datetime import datetime

from scripts.vigilante_gasto_avisar import analizar
from src import vigilante_gasto as vg

AHORA = datetime(2026, 11, 15, 12, 0, tzinfo=vg.ZONA).timestamp()
DIA = 86400


def _job(mode, ts, usd, kind="claude", detail="claude-haiku-5-5 · in=10 out=5"):
    return {"mode": mode, "started_at": ts, "title": "secreto", "user": "x",
            "lines": [{"kind": kind, "units": 1, "unit_label": "x", "cost_usd": usd, "detail": detail}]}


def test_adelgazar_quita_titulos_y_saca_modelo():
    out = vg.adelgazar([_job("M", AHORA, 0.5), {"mode": "V", "started_at": AHORA, "lines": []}])
    assert out == [{"mode": "M", "ts": AHORA, "lineas": [{"kind": "claude", "modelo": "claude-haiku-5-5", "usd": 0.5}]}]
    assert vg.modelo_de({"kind": "minimax", "detail": "voz · 300 chars"}) == "minimax"


def test_resumen_hoy_y_prevision():
    jobs = vg.adelgazar([
        _job("A", AHORA - 3600, 2.0),
        _job("A", AHORA - 2 * DIA, 1.0),
        _job("B", AHORA - 3600, 0.3, kind="gemini", detail="gemini-2.5-flash · in=1"),
        _job("A", AHORA - 20 * DIA, 9.0),  # mes anterior: ni hoy ni mes
    ])
    r = vg.resumen(jobs, AHORA)
    assert r["dia"] == "2026-11-15"
    assert r["total_hoy"] == 2.3
    assert r["por_kind"] == {"claude": 2.0, "gemini": 0.3}
    assert r["por_modelo"]["claude-haiku-5-5"] == 2.0
    assert "A" not in r["media_modo_7d"]  # 1 día de historial: sin media
    assert r["claude_mes"] == 3.0
    # 14,5 días transcurridos → 3/14,5*30
    assert r["claude_prevision_mes"] == round(3.0 / 14.5 * 30, 2)


def test_aviso_modo_disparado_y_ritmo():
    jobs = [_job("A", AHORA - i * DIA, 0.5) for i in range(1, 8)] + [_job("A", AHORA - 60, 5.0)]
    r = vg.resumen(vg.adelgazar(jobs), AHORA)
    claves = {a["clave"] for a in vg.avisos_gasto(r)}
    assert "gasto:modo:A:2026-11-15" in claves
    assert "gasto:claude_ritmo:2026-11-15" not in claves  # 8,5 $ → ~17 $/mes

    caro = vg.resumen(vg.adelgazar([_job("A", AHORA - DIA, 80.0)]), AHORA)
    assert "gasto:claude_ritmo:2026-11-15" in {a["clave"] for a in vg.avisos_gasto(caro)}


def test_sin_aviso_por_centimos_ni_sin_historial():
    jobs = [_job("A", AHORA - DIA, 0.01), _job("A", AHORA - 60, 0.5), _job("N", AHORA - 60, 9.0)]
    assert vg.avisos_gasto(vg.resumen(vg.adelgazar(jobs), AHORA)) == []


def test_avisos_salud():
    assert vg.avisos_salud({"ok": True, "fallos": []}) == []
    assert vg.avisos_salud(None)[0]["clave"] == "salud:sin_respuesta"
    av = vg.avisos_salud({"ok": False, "fallos": ["drive", "cola"],
                          "drive": {"ok": False, "error": "sin montaje"},
                          "cola": {"ok": False, "atascados": [{"id": "j1", "titulo": "Tanda 3", "estado": "running", "motivo": "sin progreso"}]}})
    assert [a["clave"] for a in av] == ["salud:drive", "salud:cola"]
    assert "sin montaje" in av[0]["texto"] and "Tanda 3" in av[1]["texto"]


def test_nuevos_deduplica():
    a = [{"clave": "salud:drive", "nivel": "aviso", "texto": "x"},
         {"clave": "gasto:modo:A:2026-11-15", "nivel": "aviso", "texto": "y"}]
    env, est = vg.nuevos(a, {}, AHORA)
    assert len(env) == 2
    env, est = vg.nuevos(a, est, AHORA + 3600)
    assert env == []
    env, est = vg.nuevos(a, est, AHORA + 7 * 3600)  # salud se repite a las 6 h, gasto no
    assert [x["clave"] for x in env] == ["salud:drive"]
    env, est = vg.nuevos(a[1:], est, AHORA + 8 * 3600)  # drive resuelto → sale del estado
    assert "salud:drive" not in est and env == []


def test_analizar_recolector_caido():
    r, av = analizar(None, AHORA)
    assert r is None and av[0]["clave"] == "salud:recolector"
    r, av = analizar({"jobs": [], "salud": {"ok": True, "fallos": []}}, AHORA)
    assert r["total_hoy"] == 0 and av == []


def test_media_sobre_dias_con_gasto():
    jobs = [_job("A", AHORA - i * DIA, 1.0) for i in (1, 2, 3)] + [_job("A", AHORA - 60, 2.5)]
    r = vg.resumen(vg.adelgazar(jobs), AHORA)
    assert r["media_modo_7d"]["A"] == 1.0
    assert vg.avisos_gasto(r) == []  # 2,5 no pasa de ×3


def test_salud_sin_urls():
    av = vg.avisos_salud({"fallos": ["redis_fabrica"], "redis_fabrica": {"error": "fallo https://user:clave@host/x"}})
    assert "clave" not in av[0]["texto"] and "<url>" in av[0]["texto"]
