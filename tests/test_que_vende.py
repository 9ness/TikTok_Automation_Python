"""scripts/estadisticas_movil/que_vende.py: cruce producto × formato × ventas (sin red ni contenedor)."""
import datetime as dt
import importlib.util
from pathlib import Path

import pytest

RUTA = Path(__file__).resolve().parent.parent / "scripts" / "estadisticas_movil" / "que_vende.py"


@pytest.fixture(scope="module")
def q():
    spec = importlib.util.spec_from_file_location("que_vende_test", RUTA)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ts(fecha: str, hora: int = 12) -> float:
    return dt.datetime.fromisoformat(f"{fecha}T{hora:02d}:00:00+01:00").timestamp()


TOTE = "https://www.tiktok.com/view/product/111"
TIVOSY = "https://www.tiktok.com/view/product/222"
FALDA = "https://www.tiktok.com/view/product/333"


def datos_base():
    return {
        "usuario": "ana",
        "videos": [
            {"id": "mm|1", "nicho": "mm", "modo": "mm_bolso_pov20", "titulo": "Bolso tote elegante gran capacidad",
             "caption": "Bolso tote elegante de gran capacidad 😍👜 #moda", "product_url": TOTE,
             "uploaded": True, "uploaded_at": ts("2026-10-03")},
            {"id": "mm|2", "nicho": "mm", "modo": "mm_bolso_pov20", "titulo": "Bolso tote acolchado Tivosy",
             "caption": "Bolso tote acolchado Tivosy para portátil 😍👜", "product_url": TIVOSY,
             "uploaded": True, "uploaded_at": ts("2026-09-28")},
            # Mismo caption que el Tivosy pero subido DESPUÉS del corte de ventas: no puede llevarse pedidos.
            {"id": "rv|x", "nicho": "rv", "modo": "con_ia", "titulo": "Bolso tote acolchado Tivosy",
             "caption": "Bolso tote acolchado Tivosy para portátil 😍👜", "product_url": TIVOSY,
             "uploaded": True, "uploaded_at": ts("2026-11-08")},
            {"id": "alea|f", "nicho": "alea", "modo": "calle_dividido", "titulo": "Falda encaje negra",
             "caption": "Falda de encaje negra", "product_url": FALDA, "uploaded": True, "uploaded_at": ts("2026-11-06")},
            {"id": "mm|sin", "nicho": "mm", "modo": "mm_espejo", "titulo": "Sin subir", "caption": "x",
             "product_url": FALDA, "uploaded": False, "uploaded_at": 0},
        ],
        "carruseles": [
            {"id": "c1", "titulo": "Falda\nencaje negra", "caption": "Falda de encaje", "product_url": FALDA,
             "subido": True, "subido_at": ts("2026-11-07")},
            {"id": "c2", "titulo": "Falda encaje", "caption": "x", "product_url": FALDA, "subido": False, "subido_at": None},
        ],
        "ventas": {
            "actualizado": "2026-11-07",
            "meses": [
                {"mes": "2026-10", "productos": [
                    {"titulo": "[Black Friday] Bolso tote de alta capacidad negro elegante", "pais": "ES", "gmv": 78.68, "ventas": 6},
                    {"titulo": "[Black Friday] Borsa tote di fascia alta (negro)", "pais": "IT", "gmv": 40.95, "ventas": 2},
                    {"titulo": "Bolso tote acolchado Tivosy de 20 L", "pais": "ES", "gmv": 40.58, "ventas": 2},
                    {"titulo": "Steppte Tote Tasche von Tivosy", "pais": "DE", "gmv": 21.99, "ventas": 1},
                ]},
                {"mes": "2026-11", "productos": [
                    {"titulo": "Producto que nunca publicamos aquí", "pais": "ES", "gmv": 5, "ventas": 1},
                ]},
            ],
            "contenidos": [
                {"caption": "Bolso tote elegante de gran capacidad 😍👜 #Ofertasparati", "tipo": "Vídeo", "pedidos": 8, "importe": 119.63},
                {"caption": "Bolso tote acolchado Tivosy para portátil 😍👜 #moda", "tipo": "Vídeo", "pedidos": 3, "importe": 62.57},
                {"caption": "Caption que no está en Mis tandas", "tipo": "Vídeo", "pedidos": 1, "importe": 10},
            ],
        },
    }


def test_normalizar_quita_acentos_hashtags_y_emojis(q):
    assert q.normalizar("Bolso PORTÁTIL 😍👜 #Ofertasparati #moda") == "bolso portatil"


def test_fichas_traduce_y_quita_vacias(q):
    assert q.fichas("Sac cabas femme (noir)") == {"bolso", "tote", "negro"}
    assert "black" not in q.fichas("[Black Friday] Bolso")


def test_parecido_es_asimetrico(q):
    assert q.parecido("bolso tote", "bolso tote elegante grande") == 1.0
    assert q.parecido("bolso tote elegante grande", "bolso tote") == 0.5
    assert q.parecido("", "algo") == 0.0


def test_id_producto_y_clave(q):
    assert q.id_producto(TOTE) == "111"
    assert q.clave({"product_url": TOTE, "titulo": "x"}) == "111"
    assert q.clave({"product_url": "", "titulo": "Falda encaje"}).startswith("t:")


@pytest.mark.parametrize("v,esperado", [
    ({"nicho": "rv", "modo": "con_ia"}, "réplica viral Omni"),
    ({"nicho": "rv", "modo": "genjutsu"}, "réplica Genjutsu"),
    ({"nicho": "rv", "modo": ""}, "réplica sin IA"),
    ({"nicho": "mm", "modo": "mm_bolso_pov20"}, "multimodo bolso_pov20"),
    ({"nicho": "alea", "modo": "tienda_colores"}, "aleatorios tienda_colores"),
    ({"nicho": "pov", "modo": ""}, "POV BOF"),
])
def test_formato(q, v, esperado):
    assert q.formato(v) == esperado


def test_publicados_solo_lo_subido_y_en_rango(q):
    d = datos_base()
    todos = q.publicados(d)
    assert {p["id"] for p in todos} == {"mm|1", "mm|2", "rv|x", "alea|f", "c1"}
    semana = q.publicados(d, dt.date(2026, 11, 3), dt.date(2026, 11, 9))
    assert {p["id"] for p in semana} == {"rv|x", "alea|f", "c1"}
    assert next(p for p in todos if p["id"] == "c1")["titulo"] == "Falda encaje negra"  # sin saltos de línea


def test_por_dia_cuenta_videos_y_carruseles(q):
    d = datos_base()
    pd_ = q.por_dia(q.publicados(d, dt.date(2026, 11, 3), dt.date(2026, 11, 9)))
    assert pd_[dt.date(2026, 11, 6)] == {"Vídeo": 1, "Carrusel": 0}
    assert pd_[dt.date(2026, 11, 7)] == {"Vídeo": 0, "Carrusel": 1}
    assert list(pd_) == sorted(pd_)


def test_dia_usa_hora_de_espana(q):
    # 23:30 UTC del 6/11 ya es 7/11 en España (UTC+1)
    t = dt.datetime(2026, 11, 6, 23, 30, tzinfo=dt.timezone.utc).timestamp()
    assert q._dia(t) == dt.date(2026, 11, 7)


def test_ventas_por_producto_junta_traducciones(q):
    d = datos_base()
    prods = q.ventas_por_producto(d["ventas"], q.publicados(d))
    tote = next(a for a in prods if a["clave"] == "111")
    assert tote["ventas"] == 8 and tote["gmv"] == pytest.approx(119.63)
    assert tote["paises"] == ["ES", "IT"]
    tiv = next(a for a in prods if a["clave"] == "222")
    assert tiv["ventas"] == 3 and tiv["paises"] == ["DE", "ES"]
    suelto = next(a for a in prods if not a["encontrado"])
    assert suelto["ventas"] == 1
    assert prods[0]["clave"] == "111"  # ordenado por GMV


def test_traduccion_no_se_pega_a_otro_bolso(q):
    """«Sac cabas (negro)» no debe casar con cualquier bolso tote publicado, sino con la venta española."""
    d = datos_base()
    d["videos"].append({"id": "mm|lb", "nicho": "mm", "modo": "mm_bolso_pov20",
                        "titulo": "LingBuy bolso tote vintage negro", "caption": "LingBuy tote",
                        "product_url": "https://www.tiktok.com/view/product/999", "uploaded": True,
                        "uploaded_at": ts("2026-10-10")})
    d["ventas"]["meses"][0]["productos"].append(
        {"titulo": "[Black Friday] Sac cabas femme (negro)", "pais": "FR", "gmv": 31.72, "ventas": 2})
    prods = q.ventas_por_producto(d["ventas"], q.publicados(d))
    assert "999" not in {a["clave"] for a in prods}
    assert next(a for a in prods if a["clave"] == "111")["ventas"] == 10


def test_ventas_por_formato_respeta_el_corte(q):
    d = datos_base()
    f = q.ventas_por_formato(d["ventas"], q.publicados(d))
    # El rv|x (8/11) es posterior a «actualizado» (7/11): los 3 pedidos del Tivosy son todos del multimodo.
    assert f["multimodo bolso_pov20"]["pedidos"] == 11
    assert "réplica viral Omni" not in f
    assert f["sin localizar (Vídeo)"]["pedidos"] == 1


def test_ventas_por_formato_reparte_si_hay_varios(q):
    d = datos_base()
    d["ventas"]["actualizado"] = "2026-11-30"
    f = q.ventas_por_formato(d["ventas"], q.publicados(d))
    assert f["réplica viral Omni"]["pedidos"] == 1.5
    assert f["multimodo bolso_pov20"]["pedidos"] == 9.5


def test_con_studio_por_id_y_por_caption(q):
    pubs = q.publicados(datos_base())
    studio = [{"id": "alea|f", "vistas": 900, "estilo": "calle"},
              {"caption": "Bolso tote elegante de gran capacidad", "vistas": 5000, "clics": 40}]
    r = {p["id"]: p for p in q.con_studio(pubs, studio)}
    assert r["alea|f"]["vistas"] == 900 and r["alea|f"]["estilo"] == "calle"
    assert r["mm|1"]["vistas"] == 5000 and r["mm|1"]["clics"] == 40
    assert "vistas" not in r["c1"]
    assert "vistas" not in pubs[0]  # no modifica la entrada


def test_analizar_e_informe(q):
    d = datos_base()
    studio = [{"id": "alea|f", "vistas": 900}]
    r = q.analizar(d, dt.date(2026, 11, 3), dt.date(2026, 11, 9), studio)
    assert r["total_publicados"] == 5
    tote = next(a for a in r["productos"] if a["clave"] == "111")
    assert tote["publicados"] == 1 and tote["ventas_por_pub"] == 8.0
    assert r["formatos"][0]["formato"] == "multimodo bolso_pov20"
    falda = [t for t, n in r["mas_publicados_sin_venta"] if "Falda" in t]
    assert falda
    assert r["studio_top"][0]["id"] == "alea|f"
    md = q.informe_md(r, "ana")
    assert md.startswith("# Qué vende ana")
    assert "| Bolso tote elegante gran capacidad | 8 | 119.63 |" in md
    assert "Top vistas (Studio)" in md


def test_informe_sin_subidas(q):
    r = q.analizar({"videos": [], "carruseles": [], "ventas": {}}, dt.date(2026, 11, 3), dt.date(2026, 11, 9))
    md = q.informe_md(r)
    assert "nada marcado como subido" in md


def test_main_desde_fichero(q, tmp_path, capsys):
    import json
    f = tmp_path / "d.json"
    f.write_text(json.dumps(datos_base()), encoding="utf-8")
    out = tmp_path / "i.md"
    assert q.main(["--desde-fichero", str(f), "--out", str(out), "--dias", "400"]) == 0
    assert "Productos que venden" in out.read_text(encoding="utf-8")
    assert "Qué vende ana" in capsys.readouterr().out
