import importlib.util
from pathlib import Path

_p = Path(__file__).resolve().parent.parent / "scripts/estadisticas_movil/ventas_atribuidas.py"
_s = importlib.util.spec_from_file_location("ventas_atribuidas", _p)
qv = importlib.util.module_from_spec(_s)
_s.loader.exec_module(qv)


def V(p, f, dia):
    return {"producto": p, "formato": f, "epoca": "neutro", "dia": dia}


def test_reparto_peso_decae():
    vids = [V("a", "x", "2026-11-01"), V("b", "y", "2026-11-02")]
    vids, sin = qv.atribuir(vids, [{"fecha": "2026-11-02", "ventas": 3, "gmv": 30}], 4, 0.5)
    a, b = vids
    assert round(a["ventas"] + b["ventas"], 6) == 3
    assert b["ventas"] > a["ventas"] and sin["ventas"] == 0


def test_sin_videos_en_ventana_va_a_sin_atribuir():
    vids = [V("a", "x", "2026-10-01")]
    vids, sin = qv.atribuir(vids, [{"fecha": "2026-11-02", "ventas": 2, "gmv": 10}], 4, 0.6)
    assert vids[0]["ventas"] == 0 and sin["ventas"] == 2 and sin["dias"] == ["2026-11-02"]


def test_no_cuenta_videos_posteriores():
    vids = [V("a", "x", "2026-11-05")]
    vids, sin = qv.atribuir(vids, [{"fecha": "2026-11-02", "ventas": 1, "gmv": 5}])
    assert vids[0]["ventas"] == 0 and sin["ventas"] == 1


def test_ranking_y_veredicto():
    vids = [dict(V("buena", "f1", "2026-11-01"), ventas=1.0, gmv=0.0) for _ in range(2)]
    vids += [dict(V("mala", "f2", "2026-11-01"), ventas=0.0, gmv=0.0) for _ in range(5)]
    f = qv.recomendar(qv.ranking(vids, "producto"))
    d = {x["clave"]: x for x in f}
    assert f[0]["clave"] == "buena"
    assert d["buena"]["veredicto"] == "producir más"
    assert d["mala"]["veredicto"] == "dejar"


def test_videos_subidos_normaliza():
    items = [{"id": "rv|1", "uploaded": True, "uploaded_at": 1794143163, "titulo": "T", "nicho": "rv",
              "modo": "con_ia", "epoca": "navidad"}, {"uploaded": False, "uploaded_at": 1}]
    v = qv.videos_subidos(items)
    assert len(v) == 1 and v[0]["formato"] == "rv/con_ia" and v[0]["epoca"] == "navidad"


def test_analizar_e2e():
    items = [{"uploaded": True, "uploaded_at": 1794143163, "titulo": "T", "nicho": "rv", "modo": "sin_ia"}]
    dia = qv.videos_subidos(items)[0]["dia"]
    r = qv.analizar({"dias": [{"fecha": dia, "ventas": 2, "gmv": 40}]}, items)
    assert r["por_producto"][0]["ventas"] == 2 and r["sin_atribuir"]["ventas"] == 0
