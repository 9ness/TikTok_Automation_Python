"""Variantes sin créditos de un vídeo en verde (`src/replicar_viral/variantes.py`):
detección de píldora y flecha con fotogramas sintéticos, receta, caja a tapar,
ganchos, música, anti-duplicado y registro. Sin ffmpeg, red, Drive ni Haiku."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from src.replicar_viral import variantes as va
from src.replicar_viral import video
from tests.replicar_viral.test_video import MP4, entorno  # noqa: F401 — fixture

np = pytest.importorskip("numpy")

UTC = dt.timezone.utc
FPS = 4


def _ts(dia: int, hora: int = 12) -> float:
    return dt.datetime(2026, 11, dia, hora, tzinfo=UTC).timestamp()


def _fotogramas(segundos: int = 10):
    return np.full((segundos * FPS, 480, 270, 3), 90, dtype="uint8")


def _con_pildora(fr, hasta_s: float = 4.0):
    n = int(hasta_s * FPS)
    fr[:n, 60:90, 45:225] = 255
    fr[:n, 70:80, 70:200] = 20            # el texto: filas con poco blanco, márgenes blancos
    return fr


def _con_flecha(fr, desde_s: float):
    fr[int(desde_s * FPS):, 380:420, 20:48] = (250, 210, 40)
    return fr


def _analisis(planos, fin_pildora=4.0, dur=10.0):
    return {"duracion": dur, "pildora": {"x": 180, "y": 232, "w": 720, "h": 136, "fin": fin_pildora},
            "planos": [{"ini": a, "fin": b, "flecha": f} for a, b, f in planos]}


CUATRO = [(0, 2.5, False), (2.5, 5, False), (5, 7.5, True), (7.5, 10, True)]


# --- detección -------------------------------------------------------------
def test_detecta_la_pildora_aunque_el_texto_la_cruce():
    p = va.detectar_pildora(_con_pildora(_fotogramas()), FPS)
    assert p == {"x": 180, "y": 232, "w": 720, "h": 136, "fin": 4.0}


def test_sin_pildora_y_pildora_descentrada_no_cuentan():
    assert va.detectar_pildora(_fotogramas(), FPS) is None
    fr = _fotogramas()
    fr[:16, 60:90, 5:150] = 255           # un rótulo a la izquierda no es el gancho
    assert va.detectar_pildora(fr, FPS) is None


def test_detecta_desde_cuando_sale_la_flecha():
    f = va.detectar_flecha(_con_flecha(_fotogramas(), 6.0), 10.0, FPS)
    assert f and f["desde"] == 6.0


def test_amarillo_todo_el_video_o_ninguno_no_es_flecha():
    assert va.detectar_flecha(_fotogramas(), 10.0, FPS) is None
    assert va.detectar_flecha(_con_flecha(_fotogramas(), 0.0), 10.0, FPS) is None
    assert va.detectar_flecha(_con_flecha(_fotogramas(), 9.5), 10.0, FPS) is None      # menos de 1 s


# --- receta ----------------------------------------------------------------
def test_ordenes_solo_mueve_la_cabeza_y_la_cola_con_flecha_no_se_toca():
    assert va.ordenes(_analisis(CUATRO)) == [[1, 0, 2, 3]]
    tres = _analisis([(0, 1.5, False), (1.5, 3, False), (3, 4.5, False), (4.5, 10, True)])
    todos = va.ordenes(tres)
    assert len(todos) == 5 and all(o[-1] == 3 for o in todos)
    assert todos[0][0] != 0 and [0, 1, 2, 3] not in todos


def test_ordenes_descarta_el_que_alarga_el_gancho():
    # con el plano 1 delante, la píldora vieja se vería hasta el segundo 7
    assert va.ordenes(_analisis([(0, 5, False), (5, 8, False), (8, 10, True)])) == []
    assert va._fin_gancho([1, 0, 2, 3], _analisis(CUATRO)["planos"], 4.0) == 5.0


def test_receta_reparte_orden_estilo_y_espejo():
    a = _analisis(CUATRO)
    r1, r2, r3 = (va.receta(a, n, espejo=True) for n in (1, 2, 3))
    assert [r["pildora"] for r in (r1, r2, r3)] == ["negra", "amarilla", "blanca"]
    assert len({r["movimiento"] for r in (r1, r2, r3)}) == 3
    assert r1["orden"] == [1, 0, 2, 3] and r1["orden_cambia"]
    assert r2["orden"] == [0, 1, 2, 3] and not r2["orden_cambia"]       # 1 y 2 no se parecen
    assert [r["espejo"] for r in (r1, r2, r3)] == [True, False, True]
    assert not va.receta(a, 1)["espejo"]                                # el espejo hay que pedirlo
    with pytest.raises(va.ErrorVariante):
        va.receta(a, 4)


def test_receta_de_video_hablado_no_reordena():
    r = va.receta(_analisis(CUATRO), 1, conservar_audio=True)
    assert r["orden"] == [0, 1, 2, 3] and r["conservar_audio"] and not r["orden_cambia"]


def test_caja_tapada_cubre_la_pildora_vieja_con_zoom_y_espejo():
    a = _analisis(CUATRO)
    c = va.caja_tapada(a["pildora"], va.receta(a, 1), a, 5.0)
    assert c["x"] < 180 and c["x"] + c["w"] > 900 and c["y"] < 232 and c["y"] + c["h"] > 330
    ladeada = {"x": 100, "y": 232, "w": 600, "h": 136, "fin": 4.0}
    e = va.caja_tapada(ladeada, va.receta(a, 1, espejo=True), a, 5.0)
    assert e["x"] < 100 and e["x"] + e["w"] > 980                       # la vieja y su reflejo
    assert e["x"] >= 0 and e["x"] + e["w"] <= va.W + 1
    assert va.caja_tapada(None, va.receta(a, 1), a, 5.0) is None


def test_pintar_pildora_tapa_la_caja_entera(tmp_path):
    if not (va.FUENTES / "TikTokSans-Bold.ttf").is_file():
        pytest.skip("sin fuentes")
    from PIL import Image

    tapa = {"x": 180, "y": 232, "w": 720, "h": 136}
    c = va.pintar_pildora("Mira cómo quedan en la mesa de Nochebuena 🥂", tapa, "negra", tmp_path / "p.png")
    assert c["x"] <= 180 and c["y"] <= 232 and c["x"] + c["w"] >= 900 and c["y"] + c["h"] >= 368
    im = Image.open(tmp_path / "p.png")
    assert im.size == (va.W, va.H)
    assert im.getpixel((190, 300))[3] == 255 and im.getpixel((540, 1500))[3] == 0
    banda = va.pintar_pildora("Mira cómo quedan en la mesa de Nochebuena 🥂",
                              {"x": 5, "y": 232, "w": 1070, "h": 136}, "blanca", tmp_path / "b.png")
    assert banda["x"] == 0 and banda["w"] == va.W
    with pytest.raises(va.ErrorVariante):
        va.pintar_pildora("  ", tapa, "negra", tmp_path / "v.png")


# --- gancho y música -------------------------------------------------------
@pytest.mark.parametrize("texto,vale", [
    ("Mira cómo quedan en la mesa antes de la cena 🥂", True),
    ("Ahora por solo 9,99 € en el carrito amarillo 🛒", False),
    ("Hoy tiene un 50 % menos y no lo sabías 😱", False),
    ("Con este descuento no te lo puedes perder 🎁", False),
    ("El mejor dispensador de celo que he probado 😍", False),
    ("Aplica tu cupón antes de que se acabe 🎟️", False),
    ("Muy corto 🎁", False),
    ("x" * 96, False),
])
def test_gancho_valido(texto, vale):
    assert va.gancho_valido(texto) is vale


def test_cada_variante_lleva_otra_pista_de_otro_estilo(tmp_path):
    pistas = [Path(f"/m/{e}/{k}.mp3") for e in ("jazz", "lofi", "pop") for k in (1, 2)]
    elegidas = [va.elegir_pista("96805ab4bed8", n, pistas) for n in (1, 2, 3)]
    assert len({p.parent.name for p in elegidas}) == 3
    assert elegidas == [va.elegir_pista("96805ab4bed8", n, pistas) for n in (1, 2, 3)]
    with pytest.raises(va.ErrorVariante):
        va.elegir_pista("x", 1, [])
    for nombre in ("lofi_otono/a.mp3", "lofi_otono/notas.txt", "otro_estilo/b.mp3"):
        (tmp_path / nombre).parent.mkdir(exist_ok=True)
        (tmp_path / nombre).write_bytes(b"x")
    assert [p.name for p in va.banco(tmp_path)] == ["a.mp3"]


# --- anti-duplicado --------------------------------------------------------
def _docs():
    return [
        {"id": "o1", "uploaded": True, "uploaded_at": _ts(10)},
        {"id": "v1", "variante": {"de": "rv|o1", "n": 1}, "uploaded": False},
        {"id": "v2", "variante": {"de": "o1", "n": 2}, "uploaded": False},
        {"id": "o2", "uploaded": False},
        {"id": "v3", "variante": {"de": "o2", "n": 1}, "uploaded": False},
        {"id": "s1", "uploaded": False},
    ]


def test_familias():
    assert va.familias(_docs()) == {"o1": "o1", "v1": "o1", "v2": "o1", "o2": "o2", "v3": "o2"}


def test_bloqueadas_tres_dias_y_nunca_antes_que_el_original():
    docs = _docs()
    b = va.bloqueadas(docs, dt.date(2026, 11, 12), tz=UTC)
    assert set(b) == {"v1", "v2", "v3"}
    assert "13/11" in b["v1"] and "original" in b["v3"]
    assert set(va.bloqueadas(docs, dt.date(2026, 11, 13), tz=UTC)) == {"v3"}
    # sube la variante 1 el día 13: la 2 espera otros tres días
    docs[1].update(uploaded=True, uploaded_at=_ts(13))
    assert set(va.bloqueadas(docs, dt.date(2026, 11, 15), tz=UTC)) == {"v2", "v3"}
    assert set(va.bloqueadas(docs, dt.date(2026, 11, 16), tz=UTC)) == {"v3"}


def test_el_dia_de_subida_es_el_de_espana():
    # 23:30 UTC del día 10 ya es día 11 en Madrid
    docs = [{"id": "o1", "uploaded": True, "uploaded_at": _ts(10, 23) + 1800},
            {"id": "v1", "variante": {"de": "o1", "n": 1}, "uploaded": False}]
    assert "v1" in va.bloqueadas(docs, dt.date(2026, 11, 13))
    assert va.bloqueadas(docs, dt.date(2026, 11, 14)) == {}


def test_una_por_familia_al_dia():
    fam = va.familias(_docs())
    assert va.una_por_familia(["rv|v1", "rv|s1", "rv|v2", "rv|o1", "rv|v3"], fam) == ["rv|v1", "rv|s1", "rv|v3"]


# --- registro --------------------------------------------------------------
GANCHO = "Mira cómo quedan en la mesa antes de la cena 🥂"


@pytest.fixture
def original(entorno, tmp_path, monkeypatch):  # noqa: F811
    from src.mis_tandas import servicio as mt

    (tmp_path / "o.mp4").write_bytes(MP4)
    doc = video.registrar("nestor2", modo="con_ia", origen=tmp_path / "o.mp4", titulo="Copas navideñas",
                          product_url="https://www.tiktok.com/view/product/1729123456789",
                          caption="Para la cena", hashtags="#copas #navidad")
    colores = {f"rv|{doc['id']}": {"color": "verde"}}
    monkeypatch.setattr(mt, "semaforos", lambda u: colores)
    (tmp_path / "v.mp4").write_bytes(MP4 + b"v")
    return doc, colores, tmp_path / "v.mp4"


def test_registrar_variante_hereda_el_producto_y_queda_sin_semaforo(original):
    doc, colores, mp4 = original
    v = va.registrar_variante("nestor2", f"rv|{doc['id']}", mp4, n=1, gancho=GANCHO)
    assert v["id"] != doc["id"] and v["variante"]["de"] == doc["id"] and v["variante"]["n"] == 1
    assert v["producto"] == doc["producto"] and v["caption"] == "Para la cena"
    assert v["hashtags"] == ["#copas", "#navidad"] and "VARIANTE 1" in v["notas"]
    assert Path(v["video_path"]).read_bytes() == MP4 + b"v"
    assert video.ver("nestor2", v["id"])["variante"]["gancho"] == GANCHO
    assert f"rv|{v['id']}" not in colores                               # sin revisar: el semáforo lo pone quien la mira
    assert video.resumen(v)["variante"] == {"de": doc["id"], "n": 1, "gancho": GANCHO}
    assert video.resumen(doc)["variante"] is None
    e = va.estado_publicacion("nestor2", dt.date(2026, 11, 10))
    assert e["familia"] == {doc["id"]: doc["id"], v["id"]: doc["id"]}
    assert "original" in e["bloqueadas"][v["id"]]


def test_registrar_variante_solo_de_un_original_en_verde(original):
    doc, colores, mp4 = original
    colores.clear()
    with pytest.raises(va.ErrorVariante, match="verde"):
        va.registrar_variante("nestor2", doc["id"], mp4, n=1, gancho=GANCHO)
    assert len(video.listar("nestor2")) == 1


def test_registrar_variante_topes(original):
    doc, colores, mp4 = original
    with pytest.raises(va.ErrorVariante):
        va.registrar_variante("nestor2", doc["id"], mp4, n=4, gancho=GANCHO)
    with pytest.raises(va.ErrorVariante, match="gancho"):
        va.registrar_variante("nestor2", doc["id"], mp4, n=1, gancho="Ahora por solo 9,99 € en el carrito 🛒")
    v1 = va.registrar_variante("nestor2", doc["id"], mp4, n=1, gancho=GANCHO)
    with pytest.raises(va.ErrorVariante, match="ya está registrada"):
        va.registrar_variante("nestor2", doc["id"], mp4, n=1, gancho=GANCHO)
    colores[f"rv|{v1['id']}"] = {"color": "verde"}
    with pytest.raises(va.ErrorVariante, match="ya es una variante"):
        va.registrar_variante("nestor2", v1["id"], mp4, n=2, gancho=GANCHO)
    va.registrar_variante("nestor2", doc["id"], mp4, n=2, gancho=GANCHO)
    va.registrar_variante("nestor2", doc["id"], mp4, n=3, gancho=GANCHO)
    assert len(video.listar("nestor2")) == 4
