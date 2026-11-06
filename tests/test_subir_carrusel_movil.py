"""Los puntos del Oppo no pueden moverse: la subida nocturna depende de ellos."""
import importlib.util
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
    assert set(m.PERFILES["oppo"]) == set(m.PERFILES["mi8"])


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
