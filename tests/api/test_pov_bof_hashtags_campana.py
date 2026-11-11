"""Caption del POV BOF: hashtag de categoría del Black Friday de la agencia (11/11/2026)."""

import datetime as dt
from unittest import mock

from src.api.routers.nicho_pov_bof import productos


def test_crema_lleva_beauty_en_fechas_y_solo_para_ness():
    with mock.patch("src.mis_tandas.campana_bf.dt") as fdt:
        fdt.date = mock.Mock(wraps=dt.date)
        fdt.date.today.return_value = dt.date(2026, 11, 12)
        assert productos._hashtags_campana("ness", {"titulo": "Crema hidratante facial"}) == [
            "#TikTokShopBlackFriday", "#BlackFridayBeauty"]
        assert productos._hashtags_campana("ana", {"titulo": "Crema"}) == []


def test_fuera_de_fechas_vacio():
    from src.mis_tandas import campana_bf

    assert campana_bf.hashtags("ness", {"titulo": "Crema"}, hoy=dt.date(2026, 12, 1)) == []
