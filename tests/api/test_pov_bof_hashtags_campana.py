"""Caption del POV BOF: hashtag de categoría del Black Friday de la agencia (11/11/2026)."""

import datetime as dt
from unittest import mock

from src.api.routers.nicho_pov_bof import productos


def test_categoria_por_producto_en_todas_las_cuentas():
    with mock.patch("src.mis_tandas.campana_bf.dt") as fdt:
        fdt.date = mock.Mock(wraps=dt.date)
        fdt.date.today.return_value = dt.date(2026, 11, 12)
        bf = "#TikTokShopBlackFriday"
        for u in ("ness", "mauro", "ana", "nestor2", "nes_bugallo"):
            assert productos._hashtags_campana(u, {"titulo": "Crema facial"}) == [bf, "#BlackFridayBeauty"]
            assert productos._hashtags_campana(u, {"titulo": "Mopa"}) == [bf, "#BlackFridayHome"]
        assert productos._hashtags_campana("nes_bugallo", {"titulo": "Auriculares bluetooth"}) == [
            bf, "#BlackFridayTech"]


def test_principal_hasta_el_30_sin_categoria():
    from src.mis_tandas import campana_bf

    assert campana_bf.hashtags("ana", {"titulo": "x"}, hoy=dt.date(2026, 11, 30)) == ["#TikTokShopBlackFriday"]


def test_fuera_de_fechas_vacio():
    from src.mis_tandas import campana_bf

    assert campana_bf.hashtags("ness", {"titulo": "Crema"}, hoy=dt.date(2026, 12, 1)) == []


def test_lista_fija_por_cuenta_con_la_comun_de_reserva():
    from src.nicho_pov_bof.repos import product_repo

    class R:
        def __init__(self):
            self.d = {"hashtags": {"items": [{"tag": "#comun", "nichos": []}]}}

        def is_available(self):
            return True

        def get_json(self, k):
            return self.d.get(k)

        def set_json(self, k, v):
            self.d[k] = v

    r = R()
    with mock.patch.object(product_repo, "get_nicho_pov_bof_redis", return_value=r), \
            mock.patch.object(product_repo, "_require_redis", return_value=r):
        product_repo.save_hashtags_config([{"tag": "modamujer"}, {"tag": "#tiktokshop"}], "ana")
        assert product_repo.get_hashtags("", "ana") == ["#modamujer", "#tiktokshop"]
        assert product_repo.get_hashtags("", "mauro") == ["#comun"]
        assert product_repo.get_hashtags("") == ["#comun"]
