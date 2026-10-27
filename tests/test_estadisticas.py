"""Fusión del documento de estadísticas por mes/fecha."""

from src.estadisticas import repo


class _Fake:
    prefix = "estadisticas:"

    def __init__(self):
        self.d = {}

    def is_available(self):
        return True

    def get_json(self, k):
        return self.d.get(k)

    def set_json(self, k, v):
        self.d[k] = v
        return True


def test_fusiona_meses_y_dias(monkeypatch):
    fake = _Fake()
    monkeypatch.setattr(repo, "_redis", lambda: fake)
    repo.guardar("ness", {"meses": [{"mes": "2026-06", "gmv": 1}], "actualizado": "2026-10-27"})
    out = repo.guardar("ness", {"meses": [{"mes": "2026-05", "gmv": 2}, {"mes": "2026-06", "ventas": 3}],
                                "dias": [{"fecha": "2026-10-01", "clics": 5}]})
    assert [m["mes"] for m in out["meses"]] == ["2026-05", "2026-06"]
    assert out["meses"][1] == {"mes": "2026-06", "gmv": 1, "ventas": 3}
    assert out["dias"][0]["clics"] == 5
    assert out["actualizado"] == "2026-10-27"
