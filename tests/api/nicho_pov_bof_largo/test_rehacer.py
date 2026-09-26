"""Marca "rehacer" de un vídeo del POV BOF Largo.

La pone el operador cuando ve algo mal en un vídeo montado (el producto se
mueve solo, cambia de forma…). Es de SU vídeo, se cuenta por carpeta para el
chip y se apaga sola al montar el vídeo nuevo.
"""

from __future__ import annotations

from src.nicho_pov_bof_largo.repos import product_repo


class _RedisFalso:
    def __init__(self, docs: dict):
        self.docs = docs

    def is_available(self) -> bool:
        return True

    def mget_json(self, claves):
        return [self.docs.get(k) for k in claves]


def test_cuenta_por_carpeta_solo_los_marcados(monkeypatch):
    monkeypatch.setattr(
        product_repo, "_key",
        lambda source, folder, usuario="", estilo="": f"{folder}",
    )
    docs = {
        "Carpeta_1": {"productos": {
            "1": {"rehacer": True, "rehacer_nota": "se mueve"},
            "2": {"rehacer": False},
            "3": {"video_path": "x.mp4"},
        }},
        "Carpeta_2": {"productos": {"1": {"video_path": "y.mp4"}}},
        "Carpeta_3": None,
    }
    monkeypatch.setattr(
        product_repo, "get_nicho_pov_bof_largo_redis", lambda: _RedisFalso(docs),
    )
    assert product_repo.rehacer_por_carpeta(
        "inventario_general", ["Carpeta_1", "Carpeta_2", "Carpeta_3"], "ness",
    ) == {"Carpeta_1": 1}


def test_sin_carpetas_no_lee_nada(monkeypatch):
    def no_deberia(*a, **k):
        raise AssertionError("no hay nada que leer")

    monkeypatch.setattr(product_repo, "get_nicho_pov_bof_largo_redis", lambda: _RedisFalso({}))
    monkeypatch.setattr(product_repo, "_key", no_deberia)
    assert product_repo.rehacer_por_carpeta("inventario_general", [], "ness") == {}


def test_el_resumen_del_mcp_avisa_con_la_nota():
    from src.agente_mcp import menus

    class _M:
        tipo = "largo"

    class _Ctx:
        m = _M()
        modo = ""

    r = menus.resumen(_Ctx(), {
        "producto": "6", "titulo": "Plataforma", "rehacer": True,
        "rehacer_nota": "el mando cambia", "clips_necesarios": 2,
    })
    assert r["rehacer"] == "el mando cambia"
    assert any("REHACER" in a and "el mando cambia" in a for a in r["avisos"])
