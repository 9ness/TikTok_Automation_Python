"""Filtros de Mis tandas: muestra gratis y reembolsable (marcas del producto)."""

from __future__ import annotations

from datetime import date, timedelta

from src.mis_tandas import servicio
from src.nicho_pov_bof.repos import product_repo
from src.nicho_pov_bof.services import marcas


def test_marcas_catalogo(monkeypatch):
    fuente = marcas.FUENTES_MARCAS[0]
    doc = {"productos": {
        "1": {"muestra_gratis": True},
        "2": {"reembolso": {"activo": True, "ventas_objetivo": 5, "ventas": 0,
                            "fecha_limite": (date.today() + timedelta(days=10)).isoformat()}},
        "3": {},
    }}
    monkeypatch.setattr(product_repo, "load_folders", lambda entradas: [doc for _ in entradas])
    videos = [{"id": f"x{p}", "source": fuente, "carpeta": "C1", "producto": p} for p in ("1", "2", "3")]
    videos.append({"id": "y", "source": "", "carpeta": "", "producto": ""})
    servicio._marcas_catalogo("ana", videos)
    assert [(v["muestra_gratis"], v["reembolsable"]) for v in videos] == [
        (True, False), (False, True), (False, False), (False, False)]
