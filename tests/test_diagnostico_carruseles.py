"""scripts/estadisticas_movil/diagnostico_carruseles.py: causas de que los carruseles no vendan (sin red)."""
import datetime as dt
import importlib.util
import json
from pathlib import Path

import pytest

RUTA = Path(__file__).resolve().parent.parent / "scripts" / "estadisticas_movil" / "diagnostico_carruseles.py"


@pytest.fixture(scope="module")
def d():
    spec = importlib.util.spec_from_file_location("diag_carr_test", RUTA)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ts(fecha: str, hora: int = 12) -> float:
    return dt.datetime.fromisoformat(f"{fecha}T{hora:02d}:00:00+01:00").timestamp()


TOTE = "https://www.tiktok.com/view/product/111"


def carr(i, titulo, fecha, hora=20, url="https://www.tiktok.com/view/product/{}", tienda="Zihua"):
    return {"id": f"c{i}", "titulo": titulo, "caption": titulo, "subido": True, "subido_at": ts(fecha, hora),
            "product_url": url.format(500 + i) if "{}" in url else url, "tienda": tienda}


def datos(carruseles, actualizado="2026-11-30"):
    return {
        "usuario": "ana",
        "videos": [{"id": "mm|1", "titulo": "Bolso tote elegante", "caption": "Bolso tote elegante de gran capacidad 😍",
                    "product_url": TOTE, "uploaded": True, "uploaded_at": ts("2026-10-03", 15), "nicho": "mm", "modo": "mm_bolso_pov20"}],
        "carruseles": carruseles,
        "ventas": {"actualizado": actualizado,
                   "meses": [{"mes": "2026-10", "productos": [
                       {"titulo": "Bolso tote de alta capacidad negro", "ventas": 15},
                       {"titulo": "Chaqueta de punto", "ventas": 3},
                       {"titulo": "Sac cabas femme", "ventas": 2}]}],
                   "contenidos": [{"caption": "Bolso tote elegante de gran capacidad #moda", "tipo": "Vídeo", "pedidos": 8}]},
    }


@pytest.mark.parametrize("texto,cat", [
    ("Bolso tote negro", "bolso"), ("Sac cabas femme", "bolso"), ("Botas altas de piel", "calzado"),
    ("Conjunto pantalón y chaqueta", "conjunto"), ("Abrigo largo", "abrigo/chaqueta"),
    ("Pantalón ancho", "pantalón/falda"), ("Jersey de punto", "parte de arriba"), ("Lámpara", "otra"),
])
def test_categoria(d, texto, cat):
    assert d.categoria(texto) == cat


def test_franja(d):
    assert d._franja(3) == "noche (19-6)" and d._franja(10) == "mañana (6-14)"
    assert d._franja(15) == "tarde (14-19)" and d._franja(21) == "noche (19-6)"


def test_url_valida(d):
    assert d.url_valida(TOTE) and d.url_valida("https://shop.tiktok.com/pdp/123")
    assert not d.url_valida("") and not d.url_valida("https://shein.com/x")


def test_leer_fases(d):
    lineas = [json.dumps({"id": "c1", "fases": {"rapido": {"producto_buscar": 1, "producto_anadir": 2}}}),
              json.dumps({"id": "c2", "fases": {"rapido": {"producto_buscar": 1}}}), "", "no json"]
    assert d.leer_fases(lineas) == {"c1": True, "c2": False}


def test_sin_ventana_es_la_primera_causa(d):
    cs = [carr(i, "Chaqueta acolchada", "2026-11-06") for i in range(4)]
    r = d.diagnosticar(datos(cs, actualizado="2026-11-07"))
    assert r["causas"][0]["causa"] == "sin datos todavía"
    assert all(f["ventana"] == 1 for f in r["carruseles"])


def test_categoria_distinta_y_hora(d):
    cs = [carr(i, "Chaqueta acolchada", "2026-11-01", 21) for i in range(6)]
    r = d.diagnosticar(datos(cs))
    nombres = [c["causa"] for c in r["causas"]]
    assert "sin datos todavía" not in nombres
    assert "categoría distinta de la que vende" in nombres
    assert "hora distinta de la que vende" in nombres
    assert r["categorias_venta"]["bolso"] == 17
    assert r["vendedores"][0]["hora"] == 15


def test_carrito_y_repeticion(d):
    cs = [carr(i, "Bolso tote", "2026-11-01", 15, url=TOTE) for i in range(3)] + [carr(9, "Bolso", "2026-11-01", 15, url="")]
    r = d.diagnosticar(datos(cs), fases={"c0": True, "c1": False})
    por = {c["causa"]: c for c in r["causas"]}
    assert "1 sin enlace" in por["carrito sin enlazar"]["detalle"] and "1 subidos sin" in por["carrito sin enlazar"]["detalle"]
    assert "×3" in por["repetición"]["detalle"]
    assert r["carrito_sin_registro"] == 2
    assert "categoría distinta de la que vende" not in por


def test_vistas_studio(d):
    cs = [carr(i, "Bolso tote", "2026-11-01", 15) for i in range(3)]
    studio = [{"id": "c0", "vistas": 100}, {"caption": "Bolso tote", "vistas": 50}]
    r = d.diagnosticar(datos(cs), studio=studio)
    assert r["carruseles"][0]["vistas"] == 100
    assert any(c["causa"] == "poca distribución" for c in r["causas"])


def test_informe_y_main(d, tmp_path, capsys):
    f = tmp_path / "a.json"
    f.write_text(json.dumps(datos([carr(1, "Chaqueta", "2026-11-06")], "2026-11-07")), encoding="utf-8")
    fases = tmp_path / "f.jsonl"
    fases.write_text(json.dumps({"id": "c1", "fases": {"r": {"producto_anadir": 1}}}) + "\n", encoding="utf-8")
    out = tmp_path / "i.md"
    assert d.main(["ana", "--desde-fichero", str(f), "--fases", str(fases), "--out", str(out)]) == 0
    md = out.read_text(encoding="utf-8")
    assert md.startswith("# Por qué no venden los carruseles de ana")
    assert "sin datos todavía" in md and "| bolso | 17 | 0 |" in md
    assert "Vídeos con pedidos" in capsys.readouterr().out


def test_sin_carruseles(d):
    r = d.diagnosticar({"videos": [], "carruseles": [], "ventas": {}})
    assert r["causas"] == [] and "Nada claro" in d.informe_md(r)
