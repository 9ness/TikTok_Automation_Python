"""scripts/estadisticas_movil/vigia_productos.py: enlaces y stock de lo que va en cola (sin red)."""
import importlib.util
import json
from pathlib import Path

import pytest

RUTA = Path(__file__).resolve().parent.parent / "scripts" / "estadisticas_movil" / "vigia_productos.py"


@pytest.fixture(scope="module")
def v():
    spec = importlib.util.spec_from_file_location("vigia_test", RUTA)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P = "https://www.tiktok.com/view/product/{}"


def datos():
    return {"usuario": "ana",
            "videos": [
                {"id": "v1", "titulo": "Bolso tote negro", "product_url": P.format(111), "uploaded": True},
                {"id": "v2", "titulo": "Bolso tote negro", "product_url": P.format(111), "uploaded": False},
                {"id": "v3", "titulo": "Botas altas", "product_url": P.format(111), "uploaded": False},   # mismo id, otra categoría
                {"id": "v4", "titulo": "Chaqueta", "product_url": "", "uploaded": False},
                {"id": "v5", "titulo": "Vestido", "product_url": "", "uploaded": True},
                {"id": "v6", "titulo": "Bolso tote negro", "product_url": P.format(222), "uploaded": False},
            ],
            "carruseles": [
                {"id": "c1", "titulo": "Sac cabas", "product_url": "https://vm.tiktok.com/ZNabc/", "subido": False},
                {"id": "c2", "titulo": "Jersey", "product_url": "https://shein.com/x", "subido": False},
                {"id": "c3", "titulo": "Falda", "product_url": "https://vm.tiktok.com/ZNmuerto/", "subido": True},
            ]}


def resolver(url):
    if "abc" in url:
        return "https://shop.tiktok.com/es/pdp/333?x=1"
    raise OSError("404")


@pytest.mark.parametrize("url,tipo", [
    ("", "vacio"), (P.format(123456), "producto"), ("https://shop.tiktok.com/es/pdp/123456?a=1", "producto"),
    ("https://vm.tiktok.com/ZNabc/", "corto"), ("https://shein.com/x", "raro"),
])
def test_tipo_enlace(v, url, tipo):
    assert v.tipo_enlace(url) == tipo


def test_con_ids_resuelve_y_cachea(v):
    cache = {}
    its = {i["id"]: i for i in v.con_ids(v.items(datos()), resolver, cache)}
    assert its["c1"]["pid"] == "333"
    assert its["c3"]["tipo_enlace"] == "corto_sin_resolver" and "https://vm.tiktok.com/ZNmuerto/" not in cache
    llamadas = []
    v.con_ids(v.items(datos()), lambda u: llamadas.append(u) or "https://www.tiktok.com/", cache)
    assert llamadas == ["https://vm.tiktok.com/ZNmuerto/"]   # lo resuelto sale de la caché; lo demás se reintenta


def test_sin_resolver_cortos_quedan_sin_id(v):
    its = {i["id"]: i for i in v.con_ids(v.items(datos()))}
    assert its["c1"]["tipo_enlace"] == "corto" and its["c1"]["pid"] == ""


def test_revisar(v):
    r = v.revisar(v.con_ids(v.items(datos()), resolver), maximo=2)
    graves = {p["id"]: p["problema"] for p in r["problemas"] if p["grave"]}
    assert graves == {"v4": "sin enlace", "c2": "enlace que no es de TikTok Shop",
}
    assert any(p["id"] == "v5" and not p["grave"] for p in r["problemas"])
    assert any(p["id"] == "c3" and not p["grave"] for p in r["problemas"])
    assert [c["pid"] for c in r["enlace_cambiado"]] == ["111"]
    assert set(r["enlace_cambiado"][0]["categorias"]) == {"bolso", "calzado"}
    assert any(set(ids) == {"111", "222"} for ids in r["titulo_con_varios_ids"].values())
    assert [c["pid"] for c in r["comprobar_stock"]] == ["111", "222"] and r["stock_pendientes_total"] == 3
    assert r["en_cola"] == 6 and r["no_subir"] == []


def test_stock_agotado_no_subir(v):
    stock = v.leer_stock([json.dumps({"product_id": "111", "estado": "agotado"}),
                          json.dumps({"product_id": 222, "estado": "en_stock"}), "basura", ""])
    assert stock == {"111": "agotado", "222": "en_stock"}
    r = v.revisar(v.con_ids(v.items(datos()), resolver), stock)
    assert sorted(i["id"] for i in r["no_subir"]) == ["v2", "v3"]   # v1 ya publicado
    assert [c["pid"] for c in r["comprobar_stock"]] == ["333"]


def test_informe_y_main(v, tmp_path, capsys):
    f = tmp_path / "a.json"
    f.write_text(json.dumps(datos()), encoding="utf-8")
    st = tmp_path / "s.jsonl"
    st.write_text(json.dumps({"product_id": "111", "estado": "agotado"}) + "\n", encoding="utf-8")
    out = tmp_path / "v.md"
    assert v.main(["ana", "--desde-fichero", str(f), "--no-resolver", "--stock", str(st), "--out", str(out)]) == 0
    md = out.read_text(encoding="utf-8")
    assert md.startswith("# Vigía de productos de ana")
    assert "⛔ No subir" in md and "v2" in md and "posible enlace cambiado" in md
    assert "stock_tiktok_movil.py 222" in md
    assert "Enlaces a arreglar" in capsys.readouterr().out


def test_vacio(v):
    r = v.revisar([])
    assert r["total"] == 0 and "0 vídeos/carruseles" in v.informe_md(r)
