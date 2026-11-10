"""Enlaces de la bio por el redirector del panel (cuenta clics)."""

from __future__ import annotations

from src.multiplataforma.services import enlaces_panel as ep


def _env(monkeypatch, llamadas, falla=False):
    monkeypatch.setenv("PANEL_URL", "http://panel")
    monkeypatch.setenv("PANEL_TOKEN", "t")
    monkeypatch.delenv("MULTIPLATAFORMA_ENLACE_CORTO_AMAZON", raising=False)
    ep._registrados.clear()

    def reg(*a):
        if falla:
            raise OSError("caído")
        llamadas.append(a)
    monkeypatch.setattr(ep, "_registrar", reg)


def test_shein_por_panel_y_una_vez(monkeypatch):
    ll = []
    _env(monkeypatch, ll)
    u = "https://es.shein.com/x-p-123.html?url_from=aff"
    assert ep.contado("viva_shop", "9dca47043e22cf5f", u, "Bolso") == \
        "https://panel.nebulabsmedia.com/r/viva_shop/9dca47043e22cf5f?d=links"
    ep.contado("viva_shop", "9dca47043e22cf5f", u, "Bolso")
    assert len(ll) == 1
    ep.contado("viva_shop", "9dca47043e22cf5f", u + "&x=1", "Bolso")  # destino nuevo → re-registra
    assert len(ll) == 2


def test_amazon_directo_y_fallos_directos(monkeypatch):
    ll = []
    _env(monkeypatch, ll)
    a = "https://www.amazon.es/dp/B0?tag=x-21"
    assert ep.contado("viva_shop", "abc", a, amazon=True) == a
    assert ep.contado("Viva Shop!", "abc", "https://s.com") == "https://s.com"
    _env(monkeypatch, ll, falla=True)
    assert ep.contado("viva_shop", "abc", "https://s.com") == "https://s.com"
    monkeypatch.delenv("PANEL_URL")
    assert ep.contado("viva_shop", "abc", "https://s.com") == "https://s.com"
