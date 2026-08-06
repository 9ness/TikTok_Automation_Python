"""La venta se atribuye a un NICHO, elegido por el operador.

El mismo producto se graba con varios nichos (POV BOF, POV BOF Largo, BOF
Cine…), así que de qué nicho salió la venta no se puede adivinar: lo apunta él
al marcarla.

El índice es UNO SOLO a propósito. Con un índice por nicho, ver "todas las
ventas" obligaría a leer N índices y mezclarlos; con uno solo y un campo
`nicho`, tanto la vista mezclada (la de por defecto) como el filtro son una
sola lectura.
"""

from __future__ import annotations

import pytest

from src.nicho_pov_bof.repos import product_repo


class RedisFalso:
    def __init__(self) -> None:
        self.kv: dict = {}
        self.sets: dict[str, set] = {}
        self.prefix = "nicho_pov_bof:"

    def is_available(self) -> bool:
        return True

    def get_json(self, k):
        return self.kv.get(k)

    def set_json(self, k, v):
        self.kv[k] = v
        return True

    def sadd(self, k, m):
        self.sets.setdefault(k, set()).add(m)
        return True

    def srem(self, k, m):
        self.sets.get(k, set()).discard(m)
        return True

    def smembers(self, k):
        return list(self.sets.get(k, set()))

    def mget_json(self, ks):
        return [self.kv.get(k) for k in ks]

    def delete(self, k):
        self.kv.pop(k, None)
        return True


@pytest.fixture
def redis_falso(monkeypatch: pytest.MonkeyPatch) -> RedisFalso:
    r = RedisFalso()
    monkeypatch.setattr(product_repo, "get_nicho_pov_bof_redis", lambda: r)
    monkeypatch.setattr(product_repo, "_require_redis", lambda: r)
    return r


class TestAtribucionPorNicho:
    def test_la_venta_guarda_el_nicho(self, redis_falso):
        d = product_repo.marcar_vendido(
            "aleatorios_1", "carpeta", "1", titulo="Gorra", nicho="pov_bof_largo",
        )
        assert d["nicho"] == "pov_bof_largo"

    def test_sin_nicho_queda_sin_atribuir(self, redis_falso):
        """No se inventa uno: aparece en el total pero no cuenta para nadie."""
        d = product_repo.marcar_vendido("s", "f", "1", titulo="X")
        assert d["nicho"] == ""

    def test_por_defecto_salen_todos_mezclados(self, redis_falso):
        product_repo.marcar_vendido("s", "f", "1", nicho="pov_bof")
        product_repo.marcar_vendido("s", "f", "2", nicho="pov_bof_largo")
        product_repo.marcar_vendido("s", "f", "3", nicho="gorras")
        assert len(product_repo.ranking_vendidos()) == 3

    def test_se_puede_filtrar_por_nicho(self, redis_falso):
        product_repo.marcar_vendido("s", "f", "1", nicho="pov_bof")
        product_repo.marcar_vendido("s", "f", "2", nicho="pov_bof_largo")
        product_repo.marcar_vendido("s", "f", "3", nicho="pov_bof_largo")
        largo = product_repo.ranking_vendidos("pov_bof_largo")
        assert {d["producto"] for d in largo} == {"2", "3"}

    def test_remarcar_conserva_el_nicho(self, redis_falso):
        """Sumar unidades o volver a marcar no debe borrar la atribución."""
        product_repo.marcar_vendido("s", "f", "1", nicho="bof_cine")
        product_repo.marcar_vendido("s", "f", "1", titulo="Nuevo título")
        assert product_repo.ranking_vendidos()[0]["nicho"] == "bof_cine"

    def test_se_puede_corregir_el_nicho(self, redis_falso):
        """Si se equivoca al apuntarlo, volver a marcar con otro lo cambia."""
        product_repo.marcar_vendido("s", "f", "1", nicho="pov_bof")
        product_repo.marcar_vendido("s", "f", "1", nicho="gorras")
        assert product_repo.ranking_vendidos()[0]["nicho"] == "gorras"


class TestCatalogoDeNichos:
    def test_estan_los_nichos_que_generan_video(self):
        for k in ("pov_bof", "pov_bof_largo", "bof_cine", "ropa", "ropa_personas"):
            assert k in product_repo.NICHOS_VENTA

    def test_hay_una_salida_para_lo_que_no_encaja(self):
        assert "otro" in product_repo.NICHOS_VENTA
