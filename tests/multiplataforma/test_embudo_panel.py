from src.multiplataforma.services import embudo_panel


class _R:
    def __init__(self, d):
        self.d = d

    def hgetall(self, k):
        return self.d.get(k, {})


def test_dias_y_metricas(monkeypatch):
    r = _R({"embudo:viva:2026-11": {"v:10": 5, "c:10:a1": 2, "c:10:b2": 1, "v:11": 3, "basura": 9}})
    monkeypatch.setattr(embudo_panel, "get_redis", lambda: r)
    dias = embudo_panel.dias_del_mes("viva", 2026, 11)
    assert dias["2026-11-10"]["visitas"] == 5 and dias["2026-11-10"]["clics"] == 3
    assert dias["2026-11-11"] == {"visitas": 3, "clics": 0, "productos": {}}
    m = embudo_panel.metricas(dias["2026-11-10"], {"a1": {"titulo": "Mascarilla " + "x" * 100}})
    assert m["clics_por_producto"] == {("Mascarilla " + "x" * 100)[:80]: 2, "b2": 1}


def test_sin_panel_no_envia(monkeypatch):
    monkeypatch.delenv("PANEL_URL", raising=False)
    assert embudo_panel.enviar()["ok"] is False
