"""Un formato NUEVO del multimodo (hablado de un mudo ya subido) es otro vídeo:
sale sin subir y deja la tanda cerrada donde estaba el viejo."""

from __future__ import annotations

import pytest

from src.mis_tandas import config, fuentes, servicio
from src.nicho_ropa.repos import product_repo as ropa_repo
from tests.mis_tandas.test_rehacer_alea import FakeRopaRedis
from tests.mis_tandas.test_servicio import FakeRedis

CARPETA = "mujer_accesorios_web__Carpeta_1"


@pytest.fixture()
def rr(monkeypatch):
    r = FakeRopaRedis()
    monkeypatch.setattr(ropa_repo, "get_nicho_ropa_redis", lambda: r)
    r.data[f"productos:{CARPETA}"] = {"productos": {"5": {"titulo": "Bolso"}}}
    r.data[f"productos:{CARPETA}:u:ana"] = {"productos": {"5": {
        "uploaded": True, "uploaded_at": 200,
        "modos": {"mm_bolso_1": {"video_path": "/v/m.mp4", "video_listo_at": 100}},
    }}}
    return r


def _vista():
    return ropa_repo.videos_multimodo([CARPETA], "ana")[0]


def test_remontar_el_mismo_formato_sigue_subido(rr):
    ropa_repo.guardar_video(CARPETA, "5", "mm_bolso_1", "/v/m2.mp4", 300, usuario="ana")
    v = _vista()
    assert v["uploaded"] is True and v["formato"] == "mm_bolso_1"


def test_formato_nuevo_tras_subir_sale_sin_subir(rr):
    ropa_repo.guardar_video(CARPETA, "5", "mm_bolso_pov20", "/v/h.mp4", 300, usuario="ana")
    v = _vista()
    assert v["formato"] == "mm_bolso_pov20"
    assert v["uploaded"] is False and v["uploaded_at"] == 0


def _f(id_, uploaded, listo, orden):
    return fuentes._fila(id=id_, nicho="mm", modo="mm_bolso_pov20", uploaded=uploaded,
                         uploaded_at=500 if uploaded else 0, video_listo_at=listo,
                         orden_at=orden, carpeta="c", titulo=id_)


def test_sale_de_la_tanda_cerrada(monkeypatch):
    r = FakeRedis()
    monkeypatch.setattr(servicio, "_redis", lambda: r)
    servicio._cache.clear()
    lista = [_f("mm|c|1", False, 900, 900), _f("mm|c|2", True, 100, 100)]
    monkeypatch.setattr(servicio, "filas", lambda u, fresco=False: lista)
    monkeypatch.setattr(servicio, "_precalentar", lambda u, l: None)
    r.data[config.FIJAS_KEY.format(usuario="ness")] = {"tandas": [{
        "ids": ["mm|c|1", "mm|c|2"], "listo": {"mm|c|1": 100, "mm|c|2": 100},
        "completada_at": 1,
    }]}
    servicio.tandas("ness")
    fijas = r.data[config.FIJAS_KEY.format(usuario="ness")]["tandas"]
    assert fijas[0]["ids"] == ["mm|c|2"]
    assert any("mm|c|1" in t["ids"] for t in fijas[1:])


def test_alternar_intercala_formatos():
    def g(i, modo, up=False):
        return fuentes._fila(id=i, nicho="mm", modo=modo, uploaded=up, titulo=i)
    lista = [g("s", "x", True), g("a1", "tc"), g("a2", "tc"), g("a3", "tc"), g("b1", "pov"), g("c1", "calle")]
    assert [f["id"] for f in servicio._alternar(lista)] == ["s", "a1", "b1", "c1", "a2", "a3"]
