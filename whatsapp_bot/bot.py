"""Lógica del bot: qué contestar a cada mensaje.

Orden de prioridad:
1. Si Néstor lleva ese chat (lo pidió el cliente o Néstor escribió desde el
   móvil), el bot calla.
2. Lo fijo (precios, estado de los vídeos, enviar vídeos, pagar, hablar con
   Néstor) se contesta con datos reales, sin IA.
3. El resto, con Haiku y la FAQ; si la IA no sabe, se avisa a Néstor.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Any

from . import precios
from .almacen import Almacen
from .config import MODELO_IA, Ajustes
from .editor import ClienteEditor, ErrorEditor
from .eventos import EcoNegocio, EstadoEnvio, Evento, MensajeEntrante
from .horario import ZONA, abierto, leer_horario
from .ia import Asistente
from .meta import ClienteMeta, ErrorMeta
from .panel import Panel

log = logging.getLogger("whatsapp_bot.bot")

MAX_VIDEO_BYTES = 16 * 1024 * 1024  # más grande, WhatsApp solo lo acepta como documento
MAX_DOC_BYTES = 100 * 1024 * 1024
MAX_VIDEOS_POR_ENVIO = 5
AVISO_FUERA_HORARIO_CADA_S = 12 * 3600

BOTONES_MENU = [("precios", "💶 Precios"), ("video", "🎬 Mis vídeos"), ("humano", "🙋 Hablar con Néstor")]
RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
RE_CODIGO = re.compile(r"\b(\d{4,8})\b")
RE_LO_QUIERO = re.compile(r"quiero el plan\s+(.+?)\s*\(", re.IGNORECASE)

PALABRAS = {
    "menu": ("menu", "hola", "buenas", "buenos dias", "buenas tardes", "buenas noches", "inicio",
             "ayuda", "bot", "hey", "ola"),
    "precios": ("precio", "precios", "planes", "tarifa", "tarifas", "cuanto cuesta", "cuanto vale"),
    "video": ("video", "videos", "mis videos", "estado", "como va", "cuota", "cuantos me quedan"),
    "enviar": ("enviamelos", "mandamelos", "enviame", "mandame", "enviar videos", "pasamelos"),
    "pagar": ("pagar", "pago", "contratar", "comprar", "quiero contratar", "lo quiero"),
    "humano": ("nestor", "humano", "persona", "agente", "hablar con alguien", "hablar con nestor"),
    "desvincular": ("desvincular", "quitar mi cuenta"),
}
ESTADOS = {
    "listo": "✅ listo",
    "en_revision": "👀 en revisión",
    "editando": "✂️ editando",
    "en_cola": "⏳ en cola",
    "fallido": "⚠️ con un problema",
}


def _plano(texto: str) -> str:
    cambios = str.maketrans("áéíóúü", "aeiouu")
    return re.sub(r"[^\w\s@.]", "", (texto or "").lower().translate(cambios)).strip()


def intencion(texto: str) -> str:
    """Qué pide el cliente con ese texto ('' si no está claro)."""
    plano = _plano(texto)
    if not plano:
        return ""
    for nombre in ("humano", "desvincular", "enviar", "pagar", "precios", "video", "menu"):
        for palabra in PALABRAS[nombre]:
            if plano == palabra or (len(plano) <= 40 and re.search(rf"\b{re.escape(palabra)}\b", plano)):
                return nombre
    return ""


class Bot:
    def __init__(self, ajustes: Ajustes, almacen: Almacen, meta: ClienteMeta,
                 editor: ClienteEditor, ia: Asistente, panel: Panel) -> None:
        self.aj = ajustes
        self.db = almacen
        self.meta = meta
        self.editor = editor
        self.ia = ia
        self.panel = panel
        try:
            self._tramos = leer_horario(ajustes.horario)
        except ValueError:
            log.warning("WHATSAPP_HORARIO mal escrito: se atiende siempre")
            self._tramos = []

    # ── utilidades ──────────────────────────────────────────────────────────
    def abierto_ahora(self, ahora: datetime | None = None) -> bool:
        return abierto(self._tramos, ahora)

    def tope_alcanzado(self) -> bool:
        return self.aj.tope_mes > 0 and self.db.salientes_del_mes() >= self.aj.tope_mes

    def _anotar(self, wa_id: str, wamid: str, texto: str, tipo: str, origen: str) -> None:
        self.db.registrar(wa_id, "sale", origen, texto, tipo=tipo, wamid=wamid or None)

    def decir(self, wa_id: str, texto: str, botones: list[tuple[str, str]] | None = None,
              origen: str = "bot") -> bool:
        """Manda texto (con botones si los hay) y lo deja en el registro."""
        try:
            if botones:
                wamid = self.meta.enviar_botones(wa_id, texto, botones)
            else:
                wamid = self.meta.enviar_texto(wa_id, texto)
        except ErrorMeta as exc:
            log.warning("no se pudo contestar a %s: %s", wa_id[-4:], exc)
            self.db.registrar(wa_id, "sale", "error", f"[sin enviar: {exc.mensaje}] {texto}")
            return False
        self._anotar(wa_id, wamid, texto, "interactive" if botones else "text", origen)
        return True

    def _avisar(self, texto: str, *, urgente: bool = True) -> None:
        self.panel.avisar(texto, notificar=urgente and self.abierto_ahora())

    def _quien(self, wa_id: str) -> str:
        nombre = self.db.chat(wa_id).get("nombre") or ""
        return f"{nombre} (+{wa_id})" if nombre else f"+{wa_id}"

    # ── entrada ─────────────────────────────────────────────────────────────
    def procesar(self, evento: Evento) -> None:
        if isinstance(evento, MensajeEntrante):
            self._entrante(evento)
        elif isinstance(evento, EcoNegocio):
            self._eco(evento)
        elif isinstance(evento, EstadoEnvio):
            self.db.marcar_estado(evento.wamid, evento.estado)

    def _eco(self, eco: EcoNegocio) -> None:
        """Néstor ha escrito desde el móvil: el bot se calla un rato en ese chat."""
        if self.db.es_nuestro(eco.wamid):
            return  # es el eco de un mensaje del propio bot
        wa_id = self.db.clave_chat(eco.wa_id, eco.user_id)
        if not self.db.registrar(wa_id, "eco", "nestor", eco.texto, tipo=eco.tipo, wamid=eco.wamid,
                                 ts=eco.ts or None):
            return
        self.db.pausar(wa_id, self.aj.silencio_tras_nestor_min * 60, "nestor")
        self.db.poner_espera(wa_id)

    def _entrante(self, m: MensajeEntrante) -> None:
        wa_id = self.db.clave_chat(m.wa_id, m.user_id)
        texto = m.texto or f"[{m.tipo}]"
        if not self.db.registrar(wa_id, "entra", "cliente", texto, tipo=m.tipo, wamid=m.wamid,
                                 ts=m.ts or None):
            return  # Meta reintenta los webhooks: ese mensaje ya se atendió
        self.db.anotar_entrante(wa_id, m.nombre)
        que = m.boton_id or intencion(m.texto)

        if self.db.pausado(wa_id):
            motivo = self.db.chat(wa_id).get("motivo_pausa")
            if motivo == "humano" and que == "menu":
                self.db.reanudar(wa_id)  # el cliente vuelve al bot por su cuenta
            else:
                return

        if self.tope_alcanzado():
            self._aviso_tope()
            return

        if not self.abierto_ahora():
            self._fuera_de_horario(wa_id)

        chat = self.db.chat(wa_id)
        if m.tipo not in ("text", "interactive", "button") and not m.texto:
            self.decir(wa_id, "Por aquí solo leo texto 🙂 Dime qué necesitas o elige una opción:",
                       BOTONES_MENU)
            return

        lo_quiero = RE_LO_QUIERO.search(m.texto or "")
        if lo_quiero:
            self._contratar(wa_id, precios.plan_por_nombre(lo_quiero.group(1)), m.texto)
            return
        if que == "humano":
            self._humano(wa_id, m.texto)
            return
        if chat.get("esperando") and not que:
            if self._vinculacion(wa_id, chat, m.texto):
                return
        if que:
            self.db.poner_espera(wa_id)
        if que == "menu":
            self._menu(wa_id)
        elif que == "precios":
            self.decir(wa_id, precios.texto_precios(),
                       [("pagar", "Quiero contratar"), ("video", "🎬 Mis vídeos")])
        elif que == "video":
            self._estado(wa_id, sin_telefono=not m.wa_id.isdigit())
        elif que == "enviar":
            self._enviar_videos(wa_id)
        elif que == "pagar":
            self._contratar(wa_id, precios.plan_por_nombre(m.texto), m.texto)
        elif que == "desvincular":
            self._desvincular(wa_id)
        else:
            self._libre(wa_id)

    # ── respuestas fijas ────────────────────────────────────────────────────
    def _menu(self, wa_id: str) -> None:
        self.decir(
            wa_id,
            f"¡Hola! Soy el asistente de {self.aj.nombre_negocio} 👋\n"
            "Te digo precios, cómo van tus vídeos o te paso con Néstor. ¿Qué necesitas?",
            BOTONES_MENU,
        )

    def _fuera_de_horario(self, wa_id: str) -> None:
        ultimo = self.db.chat(wa_id).get("aviso_fuera_horario") or 0
        if time.time() - ultimo < AVISO_FUERA_HORARIO_CADA_S:
            return
        self.db.marcar_aviso_fuera_horario(wa_id)
        self.decir(
            wa_id,
            f"Ahora mismo Néstor no está (atiende {self._horario_legible()}). "
            "Yo sí te puedo decir precios y cómo van tus vídeos, y si necesitas hablar con él "
            "le dejo el aviso para cuando vuelva.",
        )

    def _horario_legible(self) -> str:
        if not self._tramos:
            return "a cualquier hora"
        nombres = ["", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        partes = []
        for dias, ini, fin in self._tramos:
            orden = sorted(dias)
            if len(orden) == 7:
                cuando = "todos los días"
            elif len(orden) > 1 and orden == list(range(orden[0], orden[-1] + 1)):
                cuando = f"de {nombres[orden[0]]} a {nombres[orden[-1]]}"
            else:
                cuando = ", ".join(nombres[d] for d in orden)
            partes.append(f"{cuando} de {ini // 60}:{ini % 60:02d} a {fin // 60}:{fin % 60:02d}")
        return " y ".join(partes)

    def _aviso_tope(self) -> None:
        mes = datetime.now(ZONA).strftime("%Y-%m")
        if self.db.dato("aviso_tope") == mes:
            return
        self.db.poner_dato("aviso_tope", mes)
        self.panel.avisar(
            f"WhatsApp del Editor: el bot ha llegado a {self.aj.tope_mes} mensajes este mes y deja de "
            "contestar para no pagar a Meta. Contesta tú desde el móvil o sube WHATSAPP_TOPE_MES.",
            notificar=True, nivel="grave",
        )

    def _humano(self, wa_id: str, texto: str = "", motivo: str = "pide hablar contigo") -> None:
        self.db.pausar(wa_id, self.aj.pausa_humano_min * 60, "humano")
        self.db.poner_espera(wa_id)
        if self.abierto_ahora():
            cuerpo = "Hecho, aviso a Néstor y te contesta él por aquí en cuanto pueda 🙌"
        else:
            cuerpo = (f"Hecho, le dejo el aviso a Néstor. Ahora no está (atiende "
                      f"{self._horario_legible()}); te contesta en cuanto vuelva.")
        self.decir(wa_id, cuerpo + "\nSi quieres volver conmigo, escribe «menú».")
        resumen = f": «{texto[:140]}»" if texto else ""
        self._avisar(f"WhatsApp del Editor: {self._quien(wa_id)} {motivo}{resumen}. "
                     "El bot está callado en ese chat.")

    def _contratar(self, wa_id: str, plan: precios.Plan | None, texto: str = "") -> None:
        if plan is None:
            self.decir(wa_id, precios.texto_precios() + "\n\n¿Cuál te interesa? Escríbeme el nombre del plan.")
            return
        partes = [precios.texto_plan(plan)]
        if plan.a_medida:
            partes.append("Este plan se prepara a medida: Néstor te escribe por aquí para ver tu estilo.")
        elif self.aj.enlace_pago or self.aj.datos_pago:
            partes.append("Para contratarlo:")
            if self.aj.enlace_pago:
                partes.append(self.aj.enlace_pago)
            if self.aj.datos_pago:
                partes.append(self.aj.datos_pago)
            partes.append("En cuanto Néstor vea el pago te activa el plan y te avisa por aquí.")
        else:
            partes.append("Néstor te pasa ahora la forma de pago por aquí y te activa el plan.")
        self.decir(wa_id, "\n\n".join(partes))
        self.db.pausar(wa_id, self.aj.pausa_humano_min * 60, "humano")
        email = RE_EMAIL.search(texto or "")
        cuenta = f" (cuenta {email.group(0)})" if email else ""
        self._avisar(f"WhatsApp del Editor: {self._quien(wa_id)} quiere contratar el plan "
                     f"{plan.nombre}{cuenta}. Falta cobrar y activarlo.")

    # ── vídeos y cuenta ─────────────────────────────────────────────────────
    def _ficha(self, wa_id: str) -> dict[str, Any] | None:
        """Ficha del cliente en el editor; None si el editor no contesta."""
        try:
            return self.editor.cliente(wa_id)
        except ErrorEditor as exc:
            log.warning("el editor no contesta: %s", exc)
            return None

    def _estado(self, wa_id: str, sin_telefono: bool = False) -> None:
        if sin_telefono:  # Meta no nos ha dado el teléfono: no se puede vincular solo
            self._humano(wa_id, motivo="pregunta por sus vídeos y WhatsApp no da su teléfono")
            return
        ficha = self._ficha(wa_id)
        if ficha is None:
            self.decir(wa_id, "Ahora mismo no puedo consultar tus vídeos. Prueba en unos minutos "
                              f"o míralos en tu panel: {self.aj.web_publica}",
                       [("humano", "🙋 Hablar con Néstor")])
            return
        if not ficha.get("vinculado"):
            self.db.poner_espera(wa_id, "email")
            self.decir(wa_id, "Para ver tus vídeos necesito saber cuál es tu cuenta. "
                              "Escríbeme el email con el que entras en la web y te mando un código.")
            return
        self.decir(wa_id, self.texto_estado(ficha), self._botones_estado(ficha))

    @staticmethod
    def _listos(ficha: dict[str, Any]) -> list[dict[str, Any]]:
        videos = []
        for dia in ficha.get("dias") or []:
            if dia.get("caducado"):
                continue
            videos += [v for v in dia.get("videos") or [] if v.get("estado") == "listo" and v.get("enlace")]
        return videos

    def _botones_estado(self, ficha: dict[str, Any]) -> list[tuple[str, str]]:
        botones = [("enviar", "📥 Enviármelos")] if self._listos(ficha) else []
        return botones + [("precios", "💶 Precios"), ("humano", "🙋 Hablar con Néstor")]

    def texto_estado(self, ficha: dict[str, Any]) -> str:
        nombre = (ficha.get("nombre") or "").split(" ")[0]
        lineas = [f"Hola{' ' + nombre if nombre else ''} 👋"]
        if ficha.get("baneado"):
            return lineas[0] + "\nTu cuenta está en pausa. Escribe «Néstor» y lo vemos."
        if ficha.get("es_prueba"):
            lineas.append(f"Estás en la prueba gratis: te quedan {int(ficha.get('prueba_restantes') or 0)} vídeos.")
        else:
            plan = next((p for p in precios.PLANES if p.id == ficha.get("plan_id")), None)
            nombre_plan = plan.nombre if plan else (ficha.get("plan_id") or "tu plan")
            lineas.append(f"Plan {nombre_plan}: hoy te quedan {int(ficha.get('quedan_hoy') or 0)} "
                          f"de {int(ficha.get('limite_dia') or 0)} vídeos.")
        dias = [d for d in ficha.get("dias") or [] if d.get("total")]
        if not dias:
            lineas.append(f"No tienes vídeos en marcha. Súbelos en tu panel: {self.aj.web_publica}")
            return "\n".join(lineas)
        for dia in dias[:3]:
            lineas.append("")
            lineas.append(f"📅 {dia.get('dia')}: {dia.get('listos', 0)} de {dia.get('total', 0)} listos")
            for video in (dia.get("videos") or [])[:8]:
                lineas.append(f"  {ESTADOS.get(video.get('estado'), video.get('estado'))} · {video.get('nombre')}")
            if dia.get("caducado"):
                lineas.append("  (ya se borraron del panel)")
            elif dia.get("caduca") and dia.get("listos"):
                lineas.append(f"  Descárgalos antes del {dia['caduca']}.")
        return "\n".join(lineas)

    def _enviar_videos(self, wa_id: str) -> None:
        ficha = self._ficha(wa_id)
        if ficha is None or not ficha.get("vinculado"):
            self._estado(wa_id)
            return
        listos = self._listos(ficha)
        if not listos:
            self.decir(wa_id, "Todavía no hay ningún vídeo listo. En cuanto estén te aviso por aquí.")
            return
        for video in listos[:MAX_VIDEOS_POR_ENVIO]:
            self._enviar_un_video(wa_id, video)
        if len(listos) > MAX_VIDEOS_POR_ENVIO:
            self.decir(wa_id, f"Te he mandado {MAX_VIDEOS_POR_ENVIO} de {len(listos)}. "
                              f"El resto, en tu panel: {self.aj.web_publica}")

    def _enviar_un_video(self, wa_id: str, video: dict[str, Any]) -> None:
        nombre = str(video.get("nombre") or "video.mp4")
        enlace = str(video["enlace"])
        peso = int(video.get("bytes") or 0)
        try:
            if 0 < peso <= MAX_VIDEO_BYTES:
                wamid = self.meta.enviar_video(wa_id, enlace, nombre)
                self._anotar(wa_id, wamid, nombre, "video", "bot")
                return
            if 0 < peso <= MAX_DOC_BYTES:
                wamid = self.meta.enviar_documento(wa_id, enlace, nombre)
                self._anotar(wa_id, wamid, nombre, "document", "bot")
                return
        except ErrorMeta as exc:
            log.warning("no se pudo mandar el vídeo: %s", exc)
        self.decir(wa_id, f"🎬 {nombre}\n{enlace}")

    def _vinculacion(self, wa_id: str, chat: dict[str, Any], texto: str) -> bool:
        """Pasos de vincular el WhatsApp con la cuenta. True si se ha contestado."""
        try:
            if chat["esperando"] == "email":
                email = RE_EMAIL.search(texto or "")
                if not email:
                    return False  # está hablando de otra cosa
                resp = self.editor.pedir_codigo(wa_id, email.group(0).lower())
                if resp.get("ok"):
                    self.db.poner_espera(wa_id, "codigo", email.group(0).lower())
                    self.decir(wa_id, "Si ese email tiene cuenta, te acaba de llegar un código. "
                                      "Escríbemelo aquí (mira también en spam).")
                elif resp.get("motivo") == "demasiados":
                    self.db.poner_espera(wa_id)
                    self.decir(wa_id, "Has pedido demasiados códigos. Prueba dentro de un rato o "
                                      "escribe «Néstor».")
                else:
                    self.decir(wa_id, "No he podido mandar el código. Revisa el email y escríbemelo otra vez.")
                return True
            if chat["esperando"] == "codigo":
                codigo = RE_CODIGO.search(texto or "")
                if not codigo:
                    return False
                resp = self.editor.confirmar_codigo(wa_id, codigo.group(1))
                if resp.get("ok"):
                    self.db.poner_espera(wa_id)
                    self.decir(wa_id, "¡Listo! Este WhatsApp ya está unido a tu cuenta ✅")
                    self._estado(wa_id)
                elif resp.get("motivo") == "codigo":
                    self.decir(wa_id, "Ese código no es. Míralo otra vez y escríbemelo.")
                else:  # caducado o demasiados intentos
                    self.db.poner_espera(wa_id, "email")
                    self.decir(wa_id, "Ese código ya no vale. Escríbeme tu email y te mando otro.")
                return True
        except ErrorEditor as exc:
            log.warning("vinculación sin editor: %s", exc)
            self.decir(wa_id, "Ahora mismo no puedo comprobarlo. Prueba en unos minutos.")
            return True
        return False

    def _desvincular(self, wa_id: str) -> None:
        try:
            self.editor.desvincular(wa_id)
        except ErrorEditor:
            self.decir(wa_id, "Ahora mismo no puedo hacerlo. Prueba en unos minutos.")
            return
        self.decir(wa_id, "Hecho: este WhatsApp ya no está unido a ninguna cuenta.")

    # ── texto libre ─────────────────────────────────────────────────────────
    def _contexto(self, wa_id: str) -> str:
        if not wa_id.isdigit() or not self.editor.configurado:
            return ""
        ficha = self._ficha(wa_id)
        if not ficha or not ficha.get("vinculado"):
            return "No sabemos quién es: su WhatsApp no está vinculado a ninguna cuenta."
        return self.texto_estado(ficha)

    def _libre(self, wa_id: str) -> None:
        dia = datetime.now(ZONA).strftime("%Y-%m-%d")
        if not self.ia.activo or self.db.sumar_uso_ia(wa_id, dia) > self.aj.ia_max_dia_por_chat:
            self.decir(wa_id, "No te he entendido del todo 😅 Elige una opción o escribe «Néstor» "
                              "y te paso con él:", BOTONES_MENU)
            return
        r = self.ia.responder(self.db.historial(wa_id, 16), self._contexto(wa_id))
        if r is None:
            self.decir(wa_id, "No te he entendido del todo 😅 Elige una opción o escribe «Néstor» "
                              "y te paso con él:", BOTONES_MENU)
            return
        self.db.anotar_ia(wa_id, MODELO_IA, r.entrada + r.cache_lectura + r.cache_escritura, r.salida, r.usd)
        try:
            self.editor.apuntar_coste(MODELO_IA, r.entrada, r.salida, r.cache_lectura, r.cache_escritura)
        except ErrorEditor:
            pass  # el gasto ya queda apuntado aquí
        if r.derivar:
            ultimo = next((h["texto"] for h in reversed(self.db.historial(wa_id, 6))
                           if h["direccion"] == "entra"), "")
            self._humano(wa_id, ultimo, motivo="pregunta algo que el bot no sabe")
            return
        self.decir(wa_id, r.texto, origen="ia")

    # ── avisos que manda el editor ──────────────────────────────────────────
    def aviso_videos_listos(self, telefono: str, nombre: str, dia: str, listos: int,
                            caduca: str = "") -> dict[str, Any]:
        """«Tus vídeos están listos». Gratis dentro de las 24 h; fuera, plantilla (de pago)."""
        wa_id = re.sub(r"\D", "", telefono or "")
        if not wa_id or listos <= 0:
            return {"enviado": False, "motivo": "datos"}
        if self.tope_alcanzado():
            self._aviso_tope()
            return {"enviado": False, "motivo": "tope_mes"}
        primero = (nombre or "").split(" ")[0]
        if self.db.ventana_abierta(wa_id):
            if self.db.pausado(wa_id) and self.db.chat(wa_id).get("motivo_pausa") == "nestor":
                return {"enviado": False, "motivo": "lo_lleva_nestor"}
            texto = (f"🎬 {primero + ', t' if primero else 'T'}us {listos} vídeos del {dia} ya están editados."
                     + (f" Descárgalos antes del {caduca}." if caduca else ""))
            ok = self.decir(wa_id, texto, [("enviar", "📥 Enviármelos")], origen="aviso")
            return {"enviado": ok, "via": "texto"} if ok else {"enviado": False, "motivo": "error_envio"}
        if not self.aj.plantillas_de_pago:
            return {"enviado": False, "motivo": "ventana_cerrada"}
        try:
            wamid = self.meta.enviar_plantilla(
                wa_id, "videos_listos", [primero or "hola", str(listos), dia, caduca or "que caduquen"]
            )
        except ErrorMeta as exc:
            return {"enviado": False, "motivo": "error_envio", "error": exc.mensaje}
        self._anotar(wa_id, wamid, f"[plantilla videos_listos] {listos} vídeos del {dia}", "template", "aviso")
        return {"enviado": True, "via": "plantilla"}
