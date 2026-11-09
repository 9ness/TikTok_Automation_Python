"""scripts/estadisticas_movil/plan_produccion.py: reparto diario hacia el formato que vende (sin red)."""
import datetime as dt
import importlib.util
import json
from pathlib import Path

import pytest

RUTA = Path(__file__).resolve().parent.parent / "scripts" / "estadisticas_movil" / "plan_produccion.py"


@pytest.fixture(scope="module")
def p():
    spec = importlib.util.spec_from_file_location("plan_prod_test", RUTA)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ts(fecha: str) -> float:
    return dt.datetime.fromisoformat(f"{fecha}T12:00:00+01:00").timestamp()


def vid(i, modo, titulo, fecha="2026-10-10", url=None, subido=True):
    return {"id": f"v{i}", "nicho": "mm", "modo": modo, "titulo": titulo, "caption": titulo,
            "product_url": url or f"https://www.tiktok.com/view/product/{900 + i}", "tienda": "T",
            "uploaded": subido, "uploaded_at": ts(fecha) if subido else 0}


def datos():
    vids = [vid(1, "mm_bolso_pov20", "Bolso tote elegante", url="https://www.tiktok.com/view/product/111")]
    vids += [vid(10 + i, "mm_espejo", f"Vestido largo {i}") for i in range(6)]          # 6 con ventana, 0 ventas → dejar
    vids += [vid(20 + i, "mm_maniqui", f"Jersey punto {i}") for i in range(2)]           # pocos → sin datos
    vids += [vid(30, "mm_botas_1", "Botas camperas", url="https://www.tiktok.com/view/product/333")]
    vids += [vid(40 + i, "mm_espejo", f"Chaqueta nueva {i}", fecha="2026-11-06") for i in range(6)]  # sin ventana
    vids += [vid(50, "mm_bolso_pov20", "Bolso bandolera nuevo", subido=False),
             vid(51, "mm_bolso_pov20", "Bolso hobo ante", fecha="2026-10-12")]
    return {"usuario": "ana", "videos": vids, "carruseles": [],
            "ventas": {"actualizado": "2026-11-07",
                       "meses": [{"mes": "2026-10", "productos": [
                           {"titulo": "Bolso tote elegante", "ventas": 9},
                           {"titulo": "Botas camperas", "ventas": 1}]}],
                       "contenidos": [{"caption": "Bolso tote elegante", "tipo": "Vídeo", "pedidos": 9},
                                      {"caption": "Botas camperas", "tipo": "Vídeo", "pedidos": 1}]}}


def test_clasificar(p):
    f = {x["formato"]: x for x in p.clasificar(datos())}
    assert f["multimodo bolso_pov20"]["estado"] == "vende"
    assert f["multimodo botas_1"]["estado"] == "vende"
    assert f["multimodo maniqui"]["estado"] == "sin datos"
    esp = f["multimodo espejo"]
    assert esp["publicados"] == 12 and esp["con_ventana"] == 6 and esp["estado"] == "dejar"


def test_clasificar_sin_ventana_no_deja(p):
    d = datos()
    d["ventas"]["actualizado"] = "2026-10-11"   # todo publicado hace ≤1 día
    f = {x["formato"]: x for x in p.clasificar(d)}
    assert f["multimodo espejo"]["estado"] == "sin datos"


@pytest.mark.parametrize("pesos,total,esperado", [
    ({"a": 1, "b": 1, "c": 1}, 4, {"a": 2, "b": 1, "c": 1}),
    ({"a": 3, "b": 1}, 6, {"a": 5, "b": 1}),  # empate de restos: gana el primero
    ({"a": 1}, 0, {"a": 0}),
])
def test_redondeo(p, pesos, total, esperado):
    r = p._redondeo(pesos, total)
    assert r == esperado and sum(r.values()) == total


def test_reparto_cupo_y_sin_dejar(p):
    fmts = p.clasificar(datos())
    r = p.reparto(fmts, 6)
    assert sum(r.values()) == 6
    assert r["multimodo bolso_pov20"] >= 3
    assert "multimodo espejo" not in r
    assert r.get("multimodo maniqui") == 1


def test_reparto_sin_nada_que_venda(p):
    fmts = [{"formato": "x", "estado": "sin datos", "publicados": 1, "tasa": 0},
            {"formato": "y", "estado": "dejar", "publicados": 9, "tasa": 0}]
    assert p.reparto(fmts, 4) == {"x": 4}
    assert p.reparto([], 4) == {}


def test_reparto_explorar_sobrante_va_al_top(p):
    fmts = [{"formato": "top", "estado": "vende", "publicados": 5, "tasa": 1.0},
            {"formato": "nuevo", "estado": "sin datos", "publicados": 0, "tasa": 0}]
    assert p.reparto(fmts, 10, explorar=0.3) == {"top": 9, "nuevo": 1}


def test_candidatos_bolso(p):
    c = p.candidatos(datos(), "bolso")
    assert [x["titulo"] for x in c][:1] == ["Bolso tote elegante"] and c[0]["ventas"] == 9
    nuevo = next(x for x in c if x["titulo"] == "Bolso bandolera nuevo")
    assert nuevo["publicados"] == 0 and nuevo["en_cola"] == 1
    assert all("Vestido" not in x["titulo"] for x in c)


def test_plan_informe_y_main(p, tmp_path, capsys):
    f = tmp_path / "a.json"
    f.write_text(json.dumps(datos()), encoding="utf-8")
    out = tmp_path / "plan.md"
    assert p.main(["ana", "--desde-fichero", str(f), "--cupo", "6", "--out", str(out)]) == 0
    md = out.read_text(encoding="utf-8")
    assert md.startswith("# Plan de producción de ana") and "categoría que vende: **bolso**" in md
    assert "× multimodo bolso_pov20" in md and "## Dejar de hacer" in md and "multimodo espejo:" in md
    assert "Candidatos (bolso)" in capsys.readouterr().out


def test_plan_vacio(p):
    r = p.plan({"videos": [], "carruseles": [], "ventas": {}})
    assert r["reparto"] == {} and r["candidatos"] == []
    assert "Sin datos para repartir" in p.informe_md(r)
