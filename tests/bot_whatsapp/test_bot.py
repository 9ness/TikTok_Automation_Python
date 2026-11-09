"""El bot entero con el webhook simulado (mensajes de ejemplo de Meta, firmados)."""
from __future__ import annotations

import itertools
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from whatsapp_bot import precios
from whatsapp_bot.almacen import Almacen
from whatsapp_bot.app import crear_app, plantillas_propuestas
from whatsapp_bot.bot import intencion
from whatsapp_bot.config import CABECERA_SECRETO, MODELO_IA, Ajustes
from whatsapp_bot.firma import calcular_firma
from whatsapp_bot.horario import ZONA
from whatsapp_bot.ia import MARCA_NESTOR, Asistente, coste_usd, prompt_sistema, turnos
from whatsapp_bot.meta import ClienteMeta

from . import ejemplos
from .falsos import EditorFalso, IAFalsa, MetaFalso, PanelFalso, ficha

SECRETO = "app-secret-de-prueba"
ADMIN = {"Authorization": "Bearer token-admin"}
_n = itertools.count(1)


def ajustes(**cambios: Any) -> Ajustes:
    base = dict(
        verify_token="verifica-123", app_secret=SECRETO, access_token="t", phone_number_id=ejemplos.PHONE_NUMBER_ID,
        waba_id=ejemplos.WABA_ID, editor_api_url="http://editor.test", editor_api_key="k",
        anthropic_api_key="", panel_url="http://panel.test", panel_token="p", horario="siempre",
        admin_token="token-admin", interno_token="token-interno", url_publica="https://wa.test",
    )
    base.update(cambios)
    return Ajustes(**base)


class Banco:
    """La app con sus dobles y atajos para mandarle webhooks."""

    def __init__(self, **cambios: Any) -> None:
        ia = cambios.pop("ia", None) or IAFalsa(activo=False)
        self.aj = ajustes(**cambios)
        self.db = Almacen()
        self.meta = MetaFalso()
        self.editor = EditorFalso()
        self.ia = ia
        self.panel = PanelFalso()
        self.app = crear_app(self.aj, almacen=self.db, meta=self.meta, editor=self.editor,
                             ia=self.ia, panel=self.panel)
        self.http = TestClient(self.app)

    def webhook(self, payload: dict[str, Any], *, firma: str | None = None, cabeceras: dict[str, str] | None = None):
        cuerpo = json.dumps(payload).encode()
        if cabeceras is None:
            cabeceras = {"X-Hub-Signature-256": firma or calcular_firma(cuerpo, SECRETO)}
        return self.http.post("/webhook", content=cuerpo,
                              headers={"Content-Type": "application/json", **cabeceras})

    def dice(self, cuerpo: str, wa_id: str = ejemplos.CLIENTE) -> None:
        assert self.webhook(ejemplos.texto(cuerpo, wa_id=wa_id, wamid=f"wamid.T{next(_n)}")).status_code == 200

    def pulsa(self, boton_id: str, wa_id: str = ejemplos.CLIENTE) -> None:
        r = self.webhook(ejemplos.boton(boton_id, boton_id, wa_id=wa_id, wamid=f"wamid.B{next(_n)}"))
        assert r.status_code == 200


@pytest.fixture
def b() -> Banco:
    return Banco()


# ── webhook: verificación y firma ───────────────────────────────────────────
def test_verificacion_de_meta_devuelve_el_challenge(b: Banco):
    r = b.http.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "verifica-123",
                                       "hub.challenge": "1158201444"})
    assert r.status_code == 200 and r.text == "1158201444"
    assert r.headers["content-type"].startswith("text/plain")
    mal = b.http.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "otro",
                                         "hub.challenge": "1"})
    assert mal.status_code == 403


def test_webhook_sin_firma_o_con_firma_mala_se_rechaza(b: Banco):
    assert b.webhook(ejemplos.texto("hola"), cabeceras={}).status_code == 401
    assert b.webhook(ejemplos.texto("hola"), firma="sha256=" + "0" * 64).status_code == 401
    assert b.meta.enviados == []


def test_sin_app_secret_no_se_acepta_nada():
    banco = Banco(app_secret="")
    assert banco.webhook(ejemplos.texto("hola")).status_code == 503


def test_webhook_repetido_no_contesta_dos_veces(b: Banco):
    payload = ejemplos.texto("hola", wamid="wamid.REPE")
    b.webhook(payload)
    b.webhook(payload)  # Meta reintenta
    assert len(b.meta.enviados) == 1


def test_360dialog_usa_la_cabecera_secreta():
    banco = Banco(proveedor="360dialog", d360_api_key="k", webhook_secreto="s3creto", app_secret="")
    assert banco.webhook(ejemplos.texto("hola"), cabeceras={}).status_code == 401
    assert banco.webhook(ejemplos.texto("hola"), cabeceras={CABECERA_SECRETO: "otro"}).status_code == 401
    assert banco.webhook(ejemplos.texto("hola"), cabeceras={CABECERA_SECRETO: "s3creto"}).status_code == 200
    assert banco.meta.ultimo()["tipo"] == "botones"
    sin_secreto = Banco(proveedor="360dialog", d360_api_key="k", webhook_secreto="", app_secret="")
    assert sin_secreto.webhook(ejemplos.texto("hola"), cabeceras={}).status_code == 503


# ── menú, precios y contratar ───────────────────────────────────────────────
def test_hola_da_el_menu_con_tres_botones(b: Banco):
    b.dice("Hola!")
    ultimo = b.meta.ultimo()
    assert ultimo["tipo"] == "botones" and ultimo["botones"] == ["precios", "video", "humano"]
    assert ultimo["a"] == ejemplos.CLIENTE


@pytest.mark.parametrize("frase, esperado", [
    ("hola", "menu"), ("¿Cuánto cuesta?", "precios"), ("precios", "precios"), ("mis vídeos", "video"),
    ("quiero hablar con Néstor", "humano"), ("envíamelos", "enviar"), ("quiero contratar", "pagar"),
    ("me gustaría saber si editáis vídeos horizontales de una hora para YouTube", ""),
])
def test_intencion(frase: str, esperado: str):
    assert intencion(frase) == esperado


def test_precios_salen_de_la_tabla_sin_inventar(b: Banco):
    b.pulsa("precios")
    texto = b.meta.ultimo()["texto"]
    for plan in precios.PLANES:
        assert plan.nombre in texto
        assert str(precios.precio_mes(plan)) in texto
    assert b.meta.ultimo()["botones"][0] == "pagar"
    assert len(texto) <= 1024  # límite del cuerpo de un mensaje con botones


def test_mensaje_de_la_web_lo_quiero_pasa_a_nestor(b: Banco):
    b.dice("Hola, quiero el plan Pro (5 vídeos/día). Mi cuenta: laura@example.com")
    assert "Pro" in b.meta.ultimo()["texto"]
    assert len(b.panel.avisos) == 1 and "laura@example.com" in b.panel.avisos[0]["texto"]
    b.dice("¿me dices algo?")  # el chat ya es de Néstor: el bot calla
    assert len(b.meta.enviados) == 1


def test_contratar_con_enlace_de_pago_configurado():
    banco = Banco(enlace_pago="https://paga.test/pro", datos_pago="Bizum 600 000 000")
    banco.dice("quiero contratar el plan studio")
    texto = banco.meta.ultimo()["texto"]
    assert "https://paga.test/pro" in texto and "Bizum 600 000 000" in texto and "Studio" in texto


def test_contratar_sin_decir_plan_pregunta_cual(b: Banco):
    b.pulsa("pagar")
    assert "¿Cuál te interesa?" in b.meta.ultimo()["texto"]
    assert b.panel.avisos == []


# ── vídeos: vinculación, estado y envío ─────────────────────────────────────
def test_vinculacion_por_codigo_y_estado(b: Banco):
    b.pulsa("video")
    assert "email" in b.meta.ultimo()["texto"]
    b.dice("es Laura@Example.com")
    assert b.editor.pedidos == [(ejemplos.CLIENTE, "laura@example.com")]
    b.dice("000000")
    assert "no es" in b.meta.ultimo()["texto"]
    b.dice("mi código es 123456")
    textos = b.meta.textos()
    assert any("ya está unido" in t for t in textos)
    estado = b.meta.ultimo()
    assert "Plan Pro: hoy te quedan 3 de 5" in estado["texto"]
    assert "2 de 3 listos" in estado["texto"] and "gancho.mp4" in estado["texto"]
    assert estado["botones"][0] == "enviar"


def test_estado_en_prueba_gratis_y_sin_videos(b: Banco):
    b.editor.ficha = ficha(es_prueba=True, prueba_restantes=2, dias=[])
    b.pulsa("video")
    texto = b.meta.ultimo()["texto"]
    assert "prueba gratis" in texto and "2 vídeos" in texto and "No tienes vídeos en marcha" in texto
    assert "enviar" not in b.meta.ultimo()["botones"]


def test_enviar_videos_pequeno_como_video_y_grande_como_documento(b: Banco):
    b.editor.ficha = ficha()
    b.pulsa("enviar")
    tipos = [(e["tipo"], e.get("enlace")) for e in b.meta.enviados]
    assert tipos == [("video", "https://x.test/d/1"), ("documento", "https://x.test/d/2")]


def test_si_whatsapp_rechaza_el_video_va_el_enlace(b: Banco):
    b.editor.ficha = ficha()
    b.meta.falla_video = True
    b.pulsa("enviar")
    assert b.meta.enviados[0]["tipo"] == "texto" and "https://x.test/d/1" in b.meta.enviados[0]["texto"]


def test_editor_caido_no_rompe(b: Banco):
    b.editor.caido = True
    b.pulsa("video")
    assert "no puedo consultar" in b.meta.ultimo()["texto"]


def test_sin_telefono_bsuid_se_deriva_a_nestor(b: Banco):
    payload = ejemplos.texto("mis videos", wamid="wamid.BSUID")
    msg = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    msg.pop("from")
    msg["from_user_id"] = "ES.13491208655302741918"
    b.webhook(payload)
    assert "aviso a Néstor" in b.meta.ultimo()["texto"] or "aviso" in b.meta.ultimo()["texto"]
    assert len(b.panel.avisos) == 1


# ── hablar con Néstor, ecos y pausas ────────────────────────────────────────
def test_hablar_con_nestor_pausa_y_avisa(b: Banco):
    b.pulsa("humano")
    assert b.db.pausado(ejemplos.CLIENTE)
    assert b.panel.avisos[0]["notificar"] is True and ejemplos.CLIENTE in b.panel.avisos[0]["texto"]
    antes = len(b.meta.enviados)
    b.dice("tengo una duda con la factura")
    assert len(b.meta.enviados) == antes  # callado
    b.dice("menú")  # el cliente vuelve al bot
    assert not b.db.pausado(ejemplos.CLIENTE) and b.meta.ultimo()["tipo"] == "botones"


def test_si_nestor_escribe_desde_el_movil_el_bot_calla(b: Banco):
    b.webhook(ejemplos.eco("Hola, soy Néstor, te lo miro", wamid="wamid.ECO_NESTOR"))
    assert b.db.pausado(ejemplos.CLIENTE)
    assert b.db.chat(ejemplos.CLIENTE)["motivo_pausa"] == "nestor"
    b.dice("hola")
    b.dice("menú")  # ni siquiera «menú» lo despierta si es Néstor quien lleva el chat
    assert b.meta.enviados == []


def test_el_eco_de_un_mensaje_del_bot_no_lo_pausa(b: Banco):
    b.dice("hola")
    b.webhook(ejemplos.eco("eco del bot", wamid="wamid.BOT1"))
    assert not b.db.pausado(ejemplos.CLIENTE)


def test_acuse_de_entrega_se_apunta(b: Banco):
    b.dice("hola")
    assert b.webhook(ejemplos.estado("wamid.BOT1", "read")).status_code == 200


def test_audio_pide_texto(b: Banco):
    b.webhook(ejemplos.audio(wamid="wamid.AUDIO_X"))
    assert "solo leo texto" in b.meta.ultimo()["texto"]


# ── horario y tope del mes ──────────────────────────────────────────────────
def _horario_cerrado() -> str:
    otro_dia = datetime.now(ZONA).isoweekday() % 7 + 1
    otro_dia = otro_dia % 7 + 1  # ni hoy ni mañana (por si el tramo cruzara la medianoche)
    return f"{otro_dia}=10:00-11:00"


def test_fuera_de_horario_avisa_una_vez_y_sigue_atendiendo():
    banco = Banco(horario=_horario_cerrado())
    banco.dice("hola")
    assert "no está" in banco.meta.enviados[0]["texto"] and banco.meta.enviados[1]["tipo"] == "botones"
    banco.pulsa("precios")
    assert len(banco.meta.enviados) == 3  # sin repetir el aviso
    banco.pulsa("humano")
    assert banco.panel.avisos[0]["notificar"] is False  # no suena de madrugada


def test_tope_del_mes_calla_al_bot_y_avisa_una_vez():
    banco = Banco(tope_mes=2)
    banco.dice("hola")
    banco.pulsa("precios")
    banco.dice("hola otra vez")
    banco.dice("hola?")
    assert len(banco.meta.enviados) == 2
    assert len(banco.panel.avisos) == 1 and banco.panel.avisos[0]["nivel"] == "grave"


# ── IA ──────────────────────────────────────────────────────────────────────
PREGUNTA = "¿editáis también vídeos horizontales de una hora para YouTube?"


def test_pregunta_libre_va_a_la_ia_y_se_apunta_el_coste():
    banco = Banco(ia=IAFalsa("Editamos vídeos verticales cortos."))
    banco.dice(PREGUNTA)
    assert banco.meta.ultimo()["texto"] == "Editamos vídeos verticales cortos."
    assert banco.editor.costes == [(MODELO_IA, 900, 60)]
    assert banco.db.gasto_ia()["llamadas"] == 1
    historial, _ = banco.ia.llamadas[0]
    assert historial[-1]["texto"] == PREGUNTA


def test_si_la_ia_no_sabe_se_pasa_a_nestor():
    banco = Banco(ia=IAFalsa(derivar=True))
    banco.dice("quiero que me devolváis el dinero")
    assert banco.db.pausado(ejemplos.CLIENTE)
    assert "devolváis el dinero" in banco.panel.avisos[0]["texto"]


def test_sin_ia_o_si_falla_sale_el_menu():
    banco = Banco()
    banco.dice(PREGUNTA)
    assert banco.meta.ultimo()["tipo"] == "botones"
    con_fallo = IAFalsa()
    con_fallo.falla = True
    banco2 = Banco(ia=con_fallo)
    banco2.dice(PREGUNTA)
    assert banco2.meta.ultimo()["tipo"] == "botones"


def test_tope_de_ia_por_chat_y_dia():
    ia = IAFalsa()
    banco = Banco(ia=ia, ia_max_dia_por_chat=2)
    for i in range(4):
        banco.dice(f"{PREGUNTA} ({i})")
    assert len(ia.llamadas) == 2


class _Bloque:
    def __init__(self, tipo: str, texto: str = "") -> None:
        self.type = tipo
        self.text = texto
        self.thinking = texto


class _Uso:
    input_tokens = 1200
    output_tokens = 80
    cache_read_input_tokens = 0
    cache_creation_input_tokens = 0


class _Respuesta:
    usage = _Uso()

    def __init__(self, bloques: list[_Bloque], stop_reason: str = "end_turn") -> None:
        self.content = bloques
        self.stop_reason = stop_reason


class _Anthropic:
    def __init__(self, respuesta: Any) -> None:
        self.respuesta = respuesta
        self.kwargs: dict[str, Any] = {}
        self.messages = self

    def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if isinstance(self.respuesta, Exception):
            raise self.respuesta
        return self.respuesta


HISTORIAL = [
    {"direccion": "sale", "texto": "bienvenida"},
    {"direccion": "entra", "texto": "hola"},
    {"direccion": "entra", "texto": "¿hacéis B-roll?"},
]


def test_asistente_llama_a_haiku_con_prompt_cacheado_y_lee_solo_el_texto():
    falso = _Anthropic(_Respuesta([_Bloque("thinking", "pienso"), _Bloque("text", "Sí, en el plan Pro.")]))
    r = Asistente(ajustes(), cliente=falso).responder(HISTORIAL, "Plan Pro")
    assert r is not None and r.texto == "Sí, en el plan Pro." and not r.derivar
    assert r.usd == pytest.approx((1200 * 0.10 + 80 * 0.50) / 1_000_000)
    k = falso.kwargs
    assert k["model"] == MODELO_IA == "claude-haiku-5-5"
    assert k["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "Plan Pro" in k["system"][1]["text"]
    assert k["messages"] == [{"role": "user", "content": "hola\n¿hacéis B-roll?"}]
    assert "thinking" not in k and "temperature" not in k


@pytest.mark.parametrize("respuesta", [
    _Respuesta([_Bloque("text", f"No lo sé. {MARCA_NESTOR}")]),
    _Respuesta([], stop_reason="refusal"),
    _Respuesta([_Bloque("thinking", "solo pensó")], stop_reason="max_tokens"),
])
def test_asistente_deriva_cuando_no_hay_respuesta_util(respuesta: _Respuesta):
    r = Asistente(ajustes(), cliente=_Anthropic(respuesta)).responder(HISTORIAL)
    assert r is not None and r.derivar and r.texto == ""


def test_asistente_sin_clave_o_con_error_devuelve_none():
    assert Asistente(ajustes()).responder(HISTORIAL) is None
    assert Asistente(ajustes(), cliente=_Anthropic(RuntimeError("429"))).responder(HISTORIAL) is None


def test_prompt_sin_marcadores_sueltos_y_con_los_precios():
    texto = prompt_sistema(ajustes())
    assert not re.search(r"\{(negocio|faq|precios|web|horario)\}", texto)
    assert "Básico" in texto and MARCA_NESTOR in texto


def test_turnos_y_coste():
    assert turnos([{"direccion": "sale", "texto": "x"}]) == []
    assert coste_usd(MODELO_IA, 1_000_000, 1_000_000) == pytest.approx(0.60)


# ── aviso «vídeos listos» que manda el editor ───────────────────────────────
INTERNO = {"Authorization": "Bearer token-interno"}
AVISO = {"evento": "videos_listos", "telefono": "+34 611 222 333", "nombre": "Laura Pérez",
         "dia": "09/11", "listos": 3, "caduca": "16/11"}


def test_aviso_interno_exige_token(b: Banco):
    assert b.http.post("/interno/aviso", json=AVISO).status_code == 401
    assert b.http.post("/interno/aviso", json=AVISO, headers={"Authorization": "Bearer x"}).status_code == 401


def test_aviso_con_ventana_cerrada_no_gasta(b: Banco):
    r = b.http.post("/interno/aviso", json=AVISO, headers=INTERNO)
    assert r.json() == {"enviado": False, "motivo": "ventana_cerrada"}
    assert b.meta.enviados == []


def test_aviso_con_ventana_abierta_va_gratis_con_boton(b: Banco):
    b.dice("hola")
    r = b.http.post("/interno/aviso", json=AVISO, headers=ADMIN)  # también vale el token del panel
    assert r.json() == {"enviado": True, "via": "texto"}
    assert "Laura, tus 3 vídeos del 09/11" in b.meta.ultimo()["texto"] and b.meta.ultimo()["botones"] == ["enviar"]


def test_aviso_con_plantilla_solo_si_se_activa():
    banco = Banco(plantillas_de_pago=True)
    r = banco.http.post("/interno/aviso", json=AVISO, headers=INTERNO)
    assert r.json() == {"enviado": True, "via": "plantilla"}
    assert banco.meta.ultimo()["variables"] == ["Laura", "3", "09/11", "16/11"]


# ── panel «Conectar WhatsApp» ───────────────────────────────────────────────
def test_admin_exige_token(b: Banco):
    assert b.http.get("/admin/diagnostico").status_code == 401
    sin = Banco(admin_token="", interno_token="")
    assert sin.http.get("/admin/diagnostico", headers=ADMIN).status_code == 503


def test_diagnostico_todo_bien(b: Banco):
    b.dice("hola")
    d = b.http.get("/admin/diagnostico", headers=ADMIN).json()
    assert d["listo"] is True and d["proveedor"] == "meta" and d["faltan"] == []
    pasos = {p["id"]: p["ok"] for p in d["pasos"]}
    assert list(pasos) == ["claves", "numero", "webhook", "webhook_recibido", "plantillas", "editor", "ia", "panel"]
    assert pasos["claves"] and pasos["numero"] and pasos["webhook"] and pasos["webhook_recibido"] and pasos["editor"]
    assert pasos["plantillas"] is False and pasos["ia"] is None
    assert d["numero"] == {"telefono": "+34 600 11 12 22", "nombre": "Nebulabs Media", "calidad": "GREEN",
                           "en_app": True}
    assert d["webhook"]["url"] == "https://wa.test/webhook" and d["webhook"]["ultimo_recibido"] > 0
    assert [p["nombre"] for p in d["plantillas_propuestas"]] == [
        "recordatorio_videos_pendientes", "videos_caducan", "videos_listos"]
    assert all(p["estado"] == "sin_enviar" for p in d["plantillas_propuestas"])
    assert d["mes"] == {"enviados": 1, "tope": 950} and d["abierto_ahora"] is True
    assert "token" not in json.dumps(d).lower() and SECRETO not in json.dumps(d)


def test_diagnostico_sin_claves_dice_cuales_faltan():
    banco = Banco(access_token="", waba_id="")
    banco.aj.faltan = ["WHATSAPP_ACCESS_TOKEN", "WHATSAPP_WABA_ID"]
    d = banco.http.get("/admin/diagnostico", headers=ADMIN).json()
    assert d["listo"] is False and d["faltan"] == ["WHATSAPP_ACCESS_TOKEN", "WHATSAPP_WABA_ID"]
    assert d["numero"] is None and {p["id"]: p["ok"] for p in d["pasos"]}["numero"] is None


def test_enviar_plantillas_a_aprobar_no_repite(b: Banco):
    b.meta.remotas = [{"name": "videos_listos", "status": "APPROVED", "category": "UTILITY", "language": "es"}]
    r = b.http.post("/admin/plantillas", headers=ADMIN).json()
    assert r == {"enviadas": ["recordatorio_videos_pendientes", "videos_caducan"],
                 "ya_estaban": ["videos_listos"], "errores": []}
    d = b.http.get("/admin/diagnostico", headers=ADMIN).json()
    assert {p["nombre"]: p["estado"] for p in d["plantillas_propuestas"]}["videos_listos"] == "APPROVED"


def test_plantillas_bien_formadas():
    propuestas = plantillas_propuestas()
    assert len(propuestas) == 3
    for p in propuestas:
        assert re.fullmatch(r"[a-z0-9_]+", p["name"]) and p["language"] == "es" and p["category"] == "UTILITY"
        cuerpo = p["components"][0]
        variables = re.findall(r"\{\{(\d+)\}\}", cuerpo["text"])
        assert variables == [str(i) for i in range(1, len(variables) + 1)]
        assert len(cuerpo["example"]["body_text"][0]) == len(variables)
        assert len(cuerpo["text"]) <= 1024 and not cuerpo["text"].startswith("{{") and not cuerpo["text"].endswith("}}")


def test_prueba_pausa_reanudar_y_conversaciones(b: Banco):
    assert b.http.post("/admin/prueba", json={"telefono": "12"}, headers=ADMIN).json()["ok"] is False
    assert b.http.post("/admin/prueba", json={"telefono": "+34 611 222 333"}, headers=ADMIN).json() == {"ok": True}
    b.meta.falla = True
    assert b.http.post("/admin/prueba", json={"telefono": "34611222333"}, headers=ADMIN).json() == {
        "ok": False, "error": "fuera de la ventana de 24 h"}
    b.meta.falla = False
    b.dice("hola")
    assert b.http.post("/admin/pausa", json={"wa_id": ejemplos.CLIENTE, "minutos": 30}, headers=ADMIN).json()["ok"]
    assert b.db.pausado(ejemplos.CLIENTE)
    assert b.http.post("/admin/reanudar", json={"wa_id": ejemplos.CLIENTE}, headers=ADMIN).json()["ok"]
    assert not b.db.pausado(ejemplos.CLIENTE)
    lista = b.http.get("/admin/conversaciones", headers=ADMIN).json()["conversaciones"]
    assert lista[0]["wa_id"] == ejemplos.CLIENTE and lista[0]["mensajes"] >= 2
    chat = b.http.get("/admin/conversacion", params={"wa_id": ejemplos.CLIENTE}, headers=ADMIN).json()["mensajes"]
    assert {m["direccion"] for m in chat} == {"entra", "sale"}
    assert b.http.post("/admin/suscribir", headers=ADMIN).json() == {"ok": True}


# ── cliente de WhatsApp: Meta directo y 360dialog ───────────────────────────
def _cliente(aj: Ajustes, vistas: list[httpx.Request], respuesta: dict[str, Any] | None = None) -> ClienteMeta:
    def atiende(request: httpx.Request) -> httpx.Response:
        vistas.append(request)
        return httpx.Response(200, json=respuesta or {"messages": [{"id": "wamid.X"}]})
    return ClienteMeta(aj, httpx.Client(transport=httpx.MockTransport(atiende)))


def test_cliente_meta_manda_a_graph_con_bearer():
    vistas: list[httpx.Request] = []
    wamid = _cliente(ajustes(access_token="tok"), vistas).enviar_botones(
        "34611222333", "hola", [("a", "Un título larguísimo que se recorta"), ("b", "B"), ("c", "C"), ("d", "D")])
    assert wamid == "wamid.X"
    r = vistas[0]
    assert str(r.url) == f"https://graph.facebook.com/v27.0/{ejemplos.PHONE_NUMBER_ID}/messages"
    assert r.headers["authorization"] == "Bearer tok"
    botones = json.loads(r.content)["interactive"]["action"]["buttons"]
    assert len(botones) == 3 and len(botones[0]["reply"]["title"]) == 20


def test_cliente_360dialog_usa_su_base_y_su_cabecera():
    vistas: list[httpx.Request] = []
    aj = ajustes(proveedor="360dialog", d360_api_key="clave360", webhook_secreto="s")
    cli = _cliente(aj, vistas)
    cli.enviar_texto("34611222333", "hola")
    cli.suscribir_app()
    assert str(vistas[0].url) == "https://waba-v2.360dialog.io/messages"
    assert vistas[0].headers["d360-api-key"] == "clave360" and "authorization" not in vistas[0].headers
    assert json.loads(vistas[1].content) == {"url": "https://wa.test/webhook",
                                             "headers": {CABECERA_SECRETO: "s"}}


def test_error_de_meta_no_lleva_el_token():
    def atiende(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid OAuth access token", "code": 190}})
    cli = ClienteMeta(ajustes(access_token="tok-secreto"), httpx.Client(transport=httpx.MockTransport(atiende)))
    with pytest.raises(Exception) as exc:
        cli.enviar_texto("34611222333", "hola")
    assert "tok-secreto" not in str(exc.value) and exc.value.codigo == 190


# ── precios: iguales que la web ─────────────────────────────────────────────
def test_precios_iguales_que_pricing_ts():
    ruta = Path(os.environ.get("PRICING_TS") or Path.home() / "proyectos/nebulabs-media/lib/pricing.ts")
    if not ruta.exists():
        pytest.skip("sin pricing.ts a mano (está en el repo de la web)")
    fuente = ruta.read_text(encoding="utf-8")
    bloques = re.findall(
        r'id: "(\w+)",\s*name: "([^"]+)",\s*videosPerDay: (\d+),\s*priceMonthly: (\d+),\s*promoPriceMonthly: (\d+)',
        fuente)
    assert [(p.id, p.nombre, p.videos_dia, p.precio, p.precio_fundador) for p in precios.PLANES] == [
        (i, n, int(v), int(p), int(f)) for i, n, v, p, f in bloques]


# ── arranque real: `uvicorn --factory whatsapp_bot.app:crear_app` ────────────
def test_arranca_desde_el_entorno_sin_claves(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    for k in list(os.environ):
        if k.startswith(("WHATSAPP_", "D360_", "EDITOR_", "PANEL_", "ANTHROPIC_")):
            monkeypatch.delenv(k)
    monkeypatch.setenv("WHATSAPP_DB", str(tmp_path / "datos" / "whatsapp.db"))
    monkeypatch.setenv("WHATSAPP_ADMIN_TOKEN", "token-admin")
    http = TestClient(crear_app())
    assert http.get("/salud").json() == {"ok": True, "proveedor": "meta", "listo": False}
    d = http.get("/admin/diagnostico", headers=ADMIN).json()
    assert d["listo"] is False and "WHATSAPP_ACCESS_TOKEN" in d["faltan"] and d["ia"]["activa"] is False
    assert (tmp_path / "datos" / "whatsapp.db").exists()
    assert http.post("/webhook", content=b"{}").status_code == 503


def test_env_example_nombra_todas_las_variables_que_lee_config():
    raiz = Path(__file__).resolve().parents[2] / "whatsapp_bot"
    leidas = set(re.findall(r'e\("([A-Z0-9_]+)"', (raiz / "config.py").read_text(encoding="utf-8")))
    leidas |= set(re.findall(r'_entero\("([A-Z0-9_]+)"', (raiz / "config.py").read_text(encoding="utf-8")))
    ejemplo = set(re.findall(r"^([A-Z0-9_]+)=", (raiz / ".env.example").read_text(encoding="utf-8"), re.M))
    assert leidas - ejemplo <= {"D360_BASE", "WHATSAPP_GRAPH_VERSION", "WHATSAPP_WEB_PUBLICA", "WHATSAPP_NOMBRE_NEGOCIO"}
