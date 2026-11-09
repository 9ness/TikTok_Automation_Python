import importlib.util
from pathlib import Path

_p = Path(__file__).resolve().parents[1] / "scripts/estadisticas_movil/planificar_dia.py"
_s = importlib.util.spec_from_file_location("planificar_dia_t", _p)
pd = importlib.util.module_from_spec(_s)
_s.loader.exec_module(pd)


def it(id_, titulo, t=1, color="verde", up=False, epoca="navidad", modo="con_ia", **k):
    d = {"id": id_, "titulo": titulo, "semaforo": {"color": color}, "uploaded": up,
         "epoca": epoca, "nicho": "rv", "modo": modo, "video_listo_at": t}
    d.update(k)
    return d


def fila(c, vpv, ver, videos=5, ventas=1.0):
    return {"clave": c, "ventas_por_video": vpv, "veredicto": ver, "videos": videos, "ventas": ventas}


def test_candidatos_filtra():
    items = [it("a", "A"), it("b", "B", color="amarillo"), it("c", "C", up=True),
             it("d", "D", sin_stock=True), it("e", "E", rehacer=True)]
    assert [i["id"] for i in pd.candidatos(items)] == ["a"]


def test_orden_celo_reno_luego_ventas_luego_antiguo():
    items = [it("x", "Taza", t=1), it("y", "Cinta de celo", t=9), it("z", "Árbol", t=2),
             it("w", "Bota", t=1, epoca="neutro"), it("r", "Pegatina de renos", t=5)]
    rk = [fila("Árbol", 2, "mantener"), fila("Taza", 1, "mantener")]
    o = [i["id"] for i in pd.ordenar(items, rk)]
    assert o[:2] == ["r", "y"] or o[:2] == ["y", "r"]
    assert o[2:5] == ["z", "x", "w"]


def test_no_repite_seguido_y_excluye_dejar():
    items = [it(f"a{k}", "A", t=k) for k in range(3)] + [it(f"b{k}", "B", t=k) for k in range(3)] + [it("d", "D")]
    sel = pd.seleccionar(pd.ordenar(items, []), 10, {"D"}, max_por_producto=99)
    prods = [pd.producto_de(i) for i in sel]
    assert "D" not in prods
    assert all(x != y for x, y in zip(prods, prods[1:]))
    assert len(sel) == 6


def test_un_solo_producto_no_se_repite():
    sel = pd.seleccionar([it("a1", "A"), it("a2", "A")], 5, set())
    assert len(sel) == 1


def test_caption_sin_precios_ni_cupones():
    c = pd.caption_de({"caption": "Solo 9,99 € hoy! Usa tu cupón ya. Gran taza #oferta #navidad #taza", "titulo": "T", "epoca": "navidad"})
    assert "€" not in c and "cup" not in c.lower() and "#oferta" not in c
    n = c.count("#")
    assert 3 <= n <= 4


def test_caption_sin_caption_usa_titulo():
    c = pd.caption_de({"titulo": "Taza bonita", "epoca": "neutro"})
    assert c.startswith("Taza bonita") and 3 <= c.count("#") <= 4


def test_formato_nunca_sin_ia():
    assert pd.formato_produccion([]) == "genjutsu"
    assert pd.formato_produccion([{"clave": "rv/genjutsu", "veredicto": "dejar"}]) == "con_ia"


def test_produccion_stock_y_probar():
    items = [it("a1", "A"), it("a2", "A", up=True), it("p1", "P", up=True), it("q1", "Q", up=True)]
    rk = [fila("A", 3, "producir más"), fila("P", 0, "pocos datos", videos=1, ventas=0),
          fila("Q", 0, "dejar", videos=6, ventas=0)]
    r = pd.plan_produccion(items, rk, [])
    por = {x["producto"]: x for x in r["producir"]}
    assert por["A"]["cantidad"] >= 3 and "Q" not in por
    assert por["P"]["cantidad"] == 1 and por["P"]["motivo"].startswith("probar")
    assert all(x["formato"] == "genjutsu" for x in r["producir"])
    assert r["stock_total"] == 1


def test_max_dos_por_producto_y_no_probar_caros(tmp_path=None):
    import importlib.util
    from pathlib import Path
    ruta = Path(__file__).resolve().parent.parent / "scripts" / "estadisticas_movil" / "planificar_dia.py"
    spec = importlib.util.spec_from_file_location("planificar_dia_extra", ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    items = [{"id": f"a{k}", "producto": "A"} for k in range(5)] + [{"id": f"b{k}", "producto": "B"} for k in range(5)]
    orig = m.producto_de
    m.producto_de = lambda i: i["producto"]
    try:
        sel = m.seleccionar(items, 10, set())
    finally:
        m.producto_de = orig
    assert len(sel) == 4
    assert m._NO_PROBAR.search("Sofá Litbird en U") and m._NO_PROBAR.search("Colchón DEWINNER")
    assert m._raiz("Libro 100000 Porqués infantil") & m._raiz("100000 Porqués · mal padre")
    assert not (m._raiz("Copas navideñas de cristal") & m._raiz("Proyector LED árbol de Navidad"))
