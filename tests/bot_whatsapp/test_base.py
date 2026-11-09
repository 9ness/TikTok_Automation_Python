"""Piezas sueltas del bot: firma, lectura del webhook, horario y almacén."""
from __future__ import annotations

from datetime import datetime

import pytest

from whatsapp_bot import horario
from whatsapp_bot.almacen import Almacen
from whatsapp_bot.eventos import EcoNegocio, EstadoEnvio, MensajeEntrante, extraer_eventos
from whatsapp_bot.firma import calcular_firma, firma_valida

from . import ejemplos


# ── firma ───────────────────────────────────────────────────────────────────
def test_firma_valida_solo_con_el_secreto_correcto():
    cuerpo = b'{"object":"whatsapp_business_account"}'
    cabecera = calcular_firma(cuerpo, "secreto")
    assert cabecera.startswith("sha256=")
    assert firma_valida(cuerpo, cabecera, "secreto")
    assert not firma_valida(cuerpo, cabecera, "otro")
    assert not firma_valida(cuerpo + b" ", cabecera, "secreto")


@pytest.mark.parametrize("cabecera", [None, "", "sha1=abc", "abc"])
def test_firma_rechaza_cabeceras_raras(cabecera):
    assert not firma_valida(b"{}", cabecera, "secreto")


def test_firma_sin_app_secret_nunca_vale():
    assert not firma_valida(b"{}", calcular_firma(b"{}", ""), "")


# ── eventos ─────────────────────────────────────────────────────────────────
def test_texto_entrante():
    (ev,) = list(extraer_eventos(ejemplos.texto("  Hola, ¿precios?  ")))
    assert isinstance(ev, MensajeEntrante)
    assert ev.wa_id == ejemplos.CLIENTE
    assert ev.texto == "Hola, ¿precios?"
    assert ev.nombre == "Lucía"
    assert ev.phone_number_id == ejemplos.PHONE_NUMBER_ID
    assert ev.ts == 1794262300


def test_boton_pulsado():
    (ev,) = list(extraer_eventos(ejemplos.boton("precios", "💶 Precios")))
    assert isinstance(ev, MensajeEntrante)
    assert ev.tipo == "interactive"
    assert ev.boton_id == "precios"
    assert ev.texto == "💶 Precios"


def test_estado_y_eco():
    (st,) = list(extraer_eventos(ejemplos.estado("wamid.X", "read")))
    assert isinstance(st, EstadoEnvio) and st.estado == "read" and st.wamid == "wamid.X"
    (eco,) = list(extraer_eventos(ejemplos.eco("Te lo miro ahora")))
    assert isinstance(eco, EcoNegocio)
    assert eco.wa_id == ejemplos.CLIENTE and eco.texto == "Te lo miro ahora"


def test_sin_telefono_usa_el_bsuid():
    payload = ejemplos.texto("hola")
    msg = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    del msg["from"]
    msg["from_user_id"] = "ES.123"
    (ev,) = list(extraer_eventos(payload))
    assert ev.wa_id == "ES.123" and ev.user_id == "ES.123"


@pytest.mark.parametrize(
    "payload",
    [{}, {"object": "page"}, {"object": "whatsapp_business_account", "entry": [{"changes": [{}]}]},
     {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "history", "value": {"x": 1}}]}]},
     None, []],
)
def test_webhooks_raros_no_rompen(payload):
    assert list(extraer_eventos(payload)) == []


# ── horario ─────────────────────────────────────────────────────────────────
def _hora(dia: int, hh: int, mm: int = 0) -> datetime:
    # 9-nov-2026 es lunes
    return datetime(2026, 11, 8 + dia, hh, mm, tzinfo=horario.ZONA)


def test_horario_por_dias():
    tramos = horario.leer_horario("12345=09:00-21:00;67=10:00-14:00")
    assert horario.abierto(tramos, _hora(1, 9))
    assert not horario.abierto(tramos, _hora(1, 8, 59))
    assert not horario.abierto(tramos, _hora(1, 21))
    assert horario.abierto(tramos, _hora(6, 13, 59))
    assert not horario.abierto(tramos, _hora(7, 15))


def test_horario_que_cruza_la_medianoche():
    tramos = horario.leer_horario("5=22:00-02:00")
    assert horario.abierto(tramos, _hora(5, 23))
    assert horario.abierto(tramos, _hora(6, 1, 30))
    assert not horario.abierto(tramos, _hora(6, 2))
    assert not horario.abierto(tramos, _hora(5, 1))


def test_horario_vacio_es_siempre_y_mal_escrito_falla():
    assert horario.leer_horario("") == [] and horario.leer_horario("siempre") == []
    assert horario.abierto([], _hora(3, 4))
    with pytest.raises(ValueError):
        horario.leer_horario("lunes a viernes")


# ── almacén ─────────────────────────────────────────────────────────────────
def test_almacen_no_repite_un_wamid():
    alm = Almacen()
    assert alm.registrar("346", "entra", "cliente", "hola", wamid="w1")
    assert not alm.registrar("346", "entra", "cliente", "hola", wamid="w1")
    assert [m["texto"] for m in alm.historial("346")] == ["hola"]


def test_almacen_pausa_ventana_y_alias():
    alm = Almacen()
    assert not alm.ventana_abierta("346", ahora=1000)
    alm.anotar_entrante("346", "Lucía", ts=1000)
    assert alm.ventana_abierta("346", ahora=1000 + 23 * 3600)
    assert not alm.ventana_abierta("346", ahora=1000 + 25 * 3600)

    alm.pausar("346", 600, "nestor", ahora=1000)
    alm.pausar("346", 60, "nestor", ahora=1000)  # no acorta la que había
    assert alm.pausado("346", ahora=1500) and not alm.pausado("346", ahora=1601)
    alm.pausar("346", 600, "humano", ahora=1000)
    alm.reanudar("346")
    assert not alm.pausado("346", ahora=1001)

    assert alm.clave_chat("346", "ES.1") == "346"
    assert alm.clave_chat("ES.1", "ES.1") == "346"  # eco que solo trae el BSUID
    assert alm.clave_chat("ES.9", "ES.9") == "ES.9"


def test_almacen_cuenta_ia_y_salientes_del_mes():
    alm = Almacen()
    assert alm.sumar_uso_ia("346", "2026-11-09") == 1
    assert alm.sumar_uso_ia("346", "2026-11-09") == 2
    assert alm.sumar_uso_ia("346", "2026-11-10") == 1

    nov = int(datetime(2026, 11, 9, 12, tzinfo=horario.ZONA).timestamp())
    oct_ = int(datetime(2026, 10, 31, 23, tzinfo=horario.ZONA).timestamp())
    alm.registrar("346", "sale", "bot", "a", wamid="s1", ts=nov)
    alm.registrar("346", "sale", "bot", "b", wamid="s2", ts=oct_)
    alm.registrar("346", "entra", "cliente", "c", wamid="e1", ts=nov)
    alm.registrar("346", "eco", "nestor", "d", wamid="e2", ts=nov)
    assert alm.salientes_del_mes(ahora=nov) == 1
    assert alm.es_nuestro("s1") and not alm.es_nuestro("e2")
