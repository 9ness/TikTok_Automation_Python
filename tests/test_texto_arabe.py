"""Texto mixto español + árabe + números (cuenta árabe, `docs/CUENTA_ARABE.md`)."""

from src import texto_arabe as ta

LRI, PDI = "⁦", "⁩"


def test_fuente_solo_con_arabe():
    assert ta.fuente_para("Tocador LED 39,90 €", "Montserrat-ExtraBold.ttf") == "Montserrat-ExtraBold.ttf"
    assert ta.fuente_para("لطلب من هنا 👇", "Montserrat-ExtraBold.ttf") == ta.FUENTE_ARABE


def test_sentido_por_la_primera_letra():
    assert ta.rtl("بثمن همزة 39,90 €")
    assert ta.rtl("🔥 39 € بثمن همزة")          # cifras y emojis no deciden
    assert not ta.rtl("Tocador LED 🔥 بثمن همزة")
    assert not ta.rtl("39,90 €")


def test_aisla_precios_y_latino_en_arabe():
    assert ta.aislar("غير ب 39,90 € بدل 59 €") == f"غير ب {LRI}39,90 €{PDI} بدل {LRI}59 €{PDI}"
    assert ta.aislar("التوصيل 24-48h") == f"التوصيل {LRI}24-48h{PDI}"


def test_sin_arabe_no_toca_nada():
    assert ta.aislar("Tocador LED 39,90 €") == "Tocador LED 39,90 €"
