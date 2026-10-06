"""«Rehacer» de Moda Mujer · Aleatorios: es del VÍDEO (producto + modo)."""

from __future__ import annotations

import pytest

from src.mis_tandas import fuentes, servicio
from src.nicho_ropa.repos import product_repo as ropa_repo

CARPETA = "mujer_web__Carpeta_13"


class FakeRopaRedis:
    prefix = ""

    def __init__(self) -> None:
        self.data: dict = {}

    def is_available(self) -> bool:
        return True

    def get_json(self, k):
        return self.data.get(k)

    def set_json(self, k, v):
        self.data[k] = v
        return True

    def mget_json(self, ks):
        return [self.data.get(k) for k in ks]

    def set_nx(self, k, v, ttl_s=30):
        if k in self.data:
            return False
        self.data[k] = v
        return True

    def delete(self, k):
        self.data.pop(k, None)


@pytest.fixture()
def rr(monkeypatch):
    r = FakeRopaRedis()
    monkeypatch.setattr(ropa_repo, "get_nicho_ropa_redis", lambda: r)
    # Ana: textos en el común, sus vídeos (dos modos + multimodo) en el suyo.
    r.data[f"productos:{CARPETA}"] = {"productos": {"3": {"titulo": "Pantalón"}}}
    r.data[f"productos:{CARPETA}:u:ana"] = {"productos": {"3": {"modos": {
        "tienda_colores": {"video_path": "/v/tc.mp4", "video_listo_at": 100},
        "calle_dividido": {"video_path": "/v/cd.mp4", "video_listo_at": 110},
    }}}}
    return r


def _vista(usuario="ana"):
    return {v["modo"]: v for v in ropa_repo.videos_aleatorios([CARPETA], usuario)}


def test_rehacer_es_del_modo_y_no_del_producto(rr):
    ropa_repo.marcar_rehacer_modo(CARPETA, "3", "tienda_colores", "ana", rehacer=True, nota="🔴 color distinto")
    v = _vista()
    assert v["tienda_colores"]["rehacer"] is True
    assert v["tienda_colores"]["rehacer_nota"] == "🔴 color distinto"
    assert v["calle_dividido"]["rehacer"] is False
    # No toca la raíz (la del multimodo) ni el documento común.
    prod = rr.data[f"productos:{CARPETA}:u:ana"]["productos"]["3"]
    assert "rehacer" not in prod
    assert "rehacer" not in rr.data[f"productos:{CARPETA}"]["productos"]["3"]


def test_montar_el_nuevo_lo_quita_y_conserva_el_puesto(rr):
    ropa_repo.marcar_rehacer_modo(CARPETA, "3", "tienda_colores", "ana", rehacer=True, nota="x")
    ropa_repo.guardar_video(CARPETA, "3", "tienda_colores", "/v/tc2.mp4", 500, usuario="ana")
    v = _vista()["tienda_colores"]
    assert v["rehacer"] is False and v["rehecho"] is True
    assert v["video_listo_at"] == 500 and v["primer_listo_at"] == 100


def test_montar_otro_modo_no_quita_el_rehacer(rr):
    ropa_repo.marcar_rehacer_modo(CARPETA, "3", "tienda_colores", "ana", rehacer=True, nota="x")
    ropa_repo.guardar_video(CARPETA, "3", "calle_dividido", "/v/cd2.mp4", 600, usuario="ana")
    assert _vista()["tienda_colores"]["rehacer"] is True


def test_montar_aleatorios_no_quita_el_rehacer_del_multimodo(rr):
    doc = rr.data[f"productos:{CARPETA}:u:ana"]["productos"]["3"]
    doc["rehacer"] = True  # el del multimodo vive en la raíz
    ropa_repo.guardar_video(CARPETA, "3", "tienda_colores", "/v/tc2.mp4", 500, usuario="ana")
    assert rr.data[f"productos:{CARPETA}:u:ana"]["productos"]["3"]["rehacer"] is True


def test_quitar_y_modo_invalido(rr):
    ropa_repo.marcar_rehacer_modo(CARPETA, "3", "tienda_colores", "ana", rehacer=True, nota="x")
    ropa_repo.marcar_rehacer_modo(CARPETA, "3", "tienda_colores", "ana", rehacer=False)
    assert _vista()["tienda_colores"]["rehacer"] is False
    with pytest.raises(ValueError):
        ropa_repo.marcar_rehacer_modo(CARPETA, "3", "multimodo", "ana", rehacer=True)


def test_marcar_alea_desde_mis_tandas(rr, monkeypatch):
    id_ = f"alea|{CARPETA}|3|tienda_colores"
    fila = fuentes._fila(id=id_, nicho="alea", carpeta=CARPETA, producto="3", modo="tienda_colores",
                         puede_rehacer=True, video_listo_at=100.0)
    otra = fuentes._fila(id=f"alea|{CARPETA}|3|calle_dividido", nicho="alea", carpeta=CARPETA,
                         producto="3", modo="calle_dividido", puede_rehacer=True)
    monkeypatch.setattr(servicio, "_fila_de", lambda u, i: fila)
    servicio._cache["ana"] = (1e18, [fila, otra])
    try:
        out = servicio.marcar("ana", id_, rehacer=True, rehacer_nota="🔴 cambia el color")
        assert out["rehacer"] is True and out["rehacer_nota"] == "🔴 cambia el color"
        assert fila["rehacer"] is True and otra["rehacer"] is False  # solo ese vídeo
        assert _vista()["tienda_colores"]["rehacer"] is True
    finally:
        servicio._cache.clear()


def test_semaforo_rojo_marca_rehacer_en_alea(monkeypatch):
    from tests.mis_tandas.test_servicio import FakeRedis

    monkeypatch.setattr(servicio, "_redis", lambda: FakeRedis())
    id_ = f"alea|{CARPETA}|3|tienda_colores"
    monkeypatch.setattr(servicio, "_fila_de", lambda u, i: fuentes._fila(
        id=id_, nicho="alea", puede_rehacer=True, video_listo_at=100.0))
    marcados = []
    monkeypatch.setattr(servicio, "marcar", lambda u, i, **kw: marcados.append((i, kw)) or {"ok": True})
    out = servicio.poner_semaforo("ana", id_, "rojo", "otro color")
    assert out["rehacer"] is True and marcados[0][1]["rehacer"] is True
