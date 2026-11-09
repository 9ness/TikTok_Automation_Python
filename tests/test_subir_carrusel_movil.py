"""Los puntos del Oppo no pueden moverse: la subida nocturna depende de ellos."""
import importlib.util
import io
import urllib.error
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

RUTA = Path(__file__).resolve().parent.parent / "scripts" / "subir_carrusel_movil.py"


@pytest.fixture
def m(monkeypatch):
    spec = importlib.util.spec_from_file_location("subir_carrusel_movil_test", RUTA)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.delenv("MOVIL_PERFIL", raising=False)
    return mod


def test_perfiles_con_las_mismas_claves(m):
    # Banderas solo del Mi 8 (Android 10); el código las lee con .get() y faltan = False en el OPPO
    solo_mi8 = {"sin_combos", "lista_en_dump", "ficha_en_caliente"}
    assert set(m.PERFILES["oppo"]) == set(m.PERFILES["mi8"]) - solo_mi8


def test_oppo_conserva_los_puntos_probados(m):
    o = m.PERFILES["oppo"]
    esperado = {
        "swipe_ficha": (720, 2600, 720, 1200), "swipe_sonido": (720, 900, 720, 2800), "mas": (720, 3024),
        "galeria": (141, 2991), "album": (688, 243), "y_max_album": 400, "rejilla": (417, 552, 477, 483),
        "pildora_sonido": (660, 372), "fila_favorito": (600, 1845), "cerrar_panel_sonido": (720, 750),
        "y_max_sonido": 500, "caption": (700, 980), "atras": (96, 237), "enlace_x": 720,
        "enlace_y_defecto": 2116, "cerrar_enlace": (1341, 2226), "x_pildora_x": 906, "anadir_x": 1188,
        "anadir_ys": (840, 1044), "confirmar_producto": (720, 1698), "anadir_abajo": (720, 2970),
        "sugerencia": (723, 578), "vaciar": (1188, 405), "historial": (340, 759),
        "zona_comerciales": (450, 1500), "buscar_comercial": (1296, 402), "check_comercial": (1278, 640),
    }
    assert {k: o[k] for k in esperado} == esperado


@pytest.mark.parametrize("salida,nombre", [
    ("Physical size: 1440x3168\n", "oppo"),
    ("Physical size: 1080x2248\n", "mi8"),
    ("Physical size: 1440x3168\nOverride size: 1080x2376\n", "oppo"),
])
def test_elige_por_wm_size_y_pregunta_una_vez(m, monkeypatch, salida, nombre):
    llamadas = []
    monkeypatch.setattr(m, "adb", lambda *a, **k: llamadas.append(a) or salida)
    assert m.perfil() is m.PERFILES[nombre]
    m.pt("mas")
    assert len(llamadas) == 1


def test_movil_perfil_manda_sin_preguntar(m, monkeypatch):
    monkeypatch.setenv("MOVIL_PERFIL", "mi8")
    monkeypatch.setattr(m, "adb", lambda *a, **k: pytest.fail("no debe llamar a adb"))
    assert m.perfil() is m.PERFILES["mi8"]


@pytest.mark.parametrize("salida", ["Physical size: 720x1280\n", "error: closed\n"])
def test_tamano_desconocido_para(m, monkeypatch, salida):
    monkeypatch.setattr(m, "adb", lambda *a, **k: salida)
    with pytest.raises(SystemExit):
        m.perfil()


def test_perfil_desconocido_para(m, monkeypatch):
    monkeypatch.setenv("MOVIL_PERFIL", "nokia")
    with pytest.raises(SystemExit):
        m.perfil()


def test_toque_foto_en_oppo(m, monkeypatch):
    monkeypatch.setenv("MOVIL_PERFIL", "oppo")
    toques = []
    monkeypatch.setattr(m, "tap", lambda x, y, e: toques.append((x, y, e)))
    m.toque_foto(4)
    assert toques == [(417 + 477, 552 + 483, 1)]


def _zip():
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("1.jpg", b"x")
    return b.getvalue()


def _caducado(url):
    return urllib.error.HTTPError(url, 410, "caducado", None, None)


def test_enlace_caducado_pide_mis_tandas_una_vez_para_todo_el_lote(m, tmp_path, monkeypatch):
    monkeypatch.setattr(m, "CACHE", tmp_path / "c" / "tandas.json")
    viejos = [{"id": str(i), "zip": f"viejo{i}"} for i in range(6)]
    m._guardar_cache({"tandas": [{"items": viejos}]})
    pedidas = []

    def mcp(_nombre, _args):
        pedidas.append(1)
        return {"tandas": [{"items": [{"id": c["id"], "zip": "nuevo" + c["id"]} for c in viejos]}]}

    def urlopen(url, timeout=0):
        if url.startswith("viejo"):
            raise _caducado(url)
        return io.BytesIO(_zip())

    monkeypatch.setattr(m, "mcp", mcp)
    monkeypatch.setattr(m.urllib.request, "urlopen", urlopen)
    for c in viejos:
        (tmp_path / c["id"]).mkdir()
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(lambda c: m.bajar_fotos(c, tmp_path / c["id"]), viejos))
    assert len(pedidas) == 1
    assert all(any((tmp_path / c["id"]).iterdir()) for c in viejos)


def test_otro_error_de_descarga_no_reintenta(m, tmp_path, monkeypatch):
    def urlopen(url, timeout=0):
        raise urllib.error.HTTPError(url, 500, "mal", None, None)

    monkeypatch.setattr(m.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(m, "mcp", lambda *_: pytest.fail("no debe pedir Mis tandas"))
    with pytest.raises(urllib.error.HTTPError):
        m.bajar_fotos({"id": "1", "zip": "x"}, tmp_path)


# ── Orden de subida (Ama Shop sancionada por contenido repetido) ──
def _c(i, viral, prod, t=0.0):
    return {"id": i, "url": f"https://www.tiktok.com/@x/video/{viral}?lang=es",
            "product_url": f"https://www.tiktok.com/view/product/{prod}", "creado_at": t}


def _seguidos(m, lista, f):
    return [(a["id"], b["id"]) for a, b in zip(lista, lista[1:]) if f(a) == f(b)]


def test_orden_no_repite_plantilla_seguida(m):
    pend = [_c("a1", 1, 10, 1), _c("a2", 1, 11, 2), _c("a3", 1, 12, 3), _c("b1", 2, 20, 4), _c("b2", 2, 21, 5)]
    r = m.orden_subida(pend)
    assert sorted(c["id"] for c in r) == sorted(c["id"] for c in pend)
    assert _seguidos(m, r, m._plantilla) == []
    assert [c["id"] for c in r] == ["a1", "b1", "a2", "b2", "a3"]


def test_orden_no_repite_producto_seguido(m):
    pend = [_c("a", 1, 10, 1), _c("b", 2, 10, 2), _c("c", 3, 20, 3)]
    r = m.orden_subida(pend)
    assert _seguidos(m, r, m._prod) == []
    assert [c["id"] for c in r] == ["a", "c", "b"]


def test_orden_respeta_antiguedad_si_no_hay_choque(m):
    pend = [_c("z", 3, 30, 9), _c("x", 1, 10, 1), _c("y", 2, 20, 5)]
    assert [c["id"] for c in m.orden_subida(pend)] == ["x", "y", "z"]


def test_orden_sin_salida_pone_todos_igual(m):
    pend = [_c("a", 1, 10, 1), _c("b", 1, 11, 2)]
    assert [c["id"] for c in m.orden_subida(pend)] == ["a", "b"]
    assert m.orden_subida([]) == []


def test_plantilla_ignora_parametros_de_la_url(m):
    assert m._plantilla({"url": "https://t.com/@a/video/5?lang=es"}) == m._plantilla({"url": "https://t.com/@a/video/5/"})
    assert m._plantilla({"folder": "Carruseles Virales 23"}) == "Carruseles Virales 23"


def test_orden_no_toca_el_movil(m, monkeypatch):
    monkeypatch.setattr(m, "adb", lambda *a, **k: (_ for _ in ()).throw(AssertionError("adb")))
    monkeypatch.setattr(m, "mcp", lambda h, a: {"tandas": [{"items": [
        _c("v1", 1, 10, 1) | {"semaforo": {"color": "verde"}},
        _c("r1", 2, 20, 2) | {"semaforo": {"color": "rojo"}},
        _c("s1", 3, 30, 3) | {"semaforo": {"color": "verde"}, "subido": True},
        _c("v2", 1, 11, 4) | {"semaforo": {"color": "verde"}},
        _c("v3", 4, 40, 5) | {"semaforo": {"color": "verde"}},
    ]}]})
    monkeypatch.setattr(m, "_guardar_cache", lambda d: None)
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        m.ordenar()
    assert [l.split(" ·")[0] for l in buf.getvalue().splitlines()] == ["v1", "v3", "v2"]
