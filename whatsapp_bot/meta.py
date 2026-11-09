"""Cliente mínimo de WhatsApp Cloud API (Graph API de Meta, o vía 360dialog).

Con ``WHATSAPP_PROVEEDOR=360dialog`` los mensajes llevan el mismo cuerpo pero
van a ``waba-v2.360dialog.io`` con la cabecera ``D360-API-KEY``.

Solo lo que usa el bot: enviar texto, botones, un vídeo o documento por
enlace y plantillas; y las lecturas con las que la página «Conectar WhatsApp»
comprueba que todo está bien (número, suscripción del webhook, plantillas).

El token nunca se escribe en logs ni en excepciones.
"""
from __future__ import annotations

from typing import Any

import httpx

from .config import CABECERA_SECRETO, Ajustes

MAX_BOTONES = 3
MAX_TITULO_BOTON = 20
MAX_TEXTO = 4096


class ErrorMeta(Exception):
    """La Graph API contestó con error (se guarda código y mensaje, sin token)."""

    def __init__(self, estado: int, mensaje: str, codigo: int | None = None) -> None:
        super().__init__(f"Meta {estado}: {mensaje}")
        self.estado = estado
        self.mensaje = mensaje
        self.codigo = codigo


class ClienteMeta:
    def __init__(self, ajustes: Ajustes, cliente: httpx.Client | None = None) -> None:
        self._aj = ajustes
        self._http = cliente or httpx.Client(timeout=15.0)

    # ── base ────────────────────────────────────────────────────────────────
    def _url(self, ruta: str) -> str:
        if self._aj.es_360:
            return f"{self._aj.d360_base}/{ruta.lstrip('/')}"
        return f"{self._aj.graph_base}/{self._aj.graph_version}/{ruta.lstrip('/')}"

    def _pedir(self, metodo: str, ruta: str, **kwargs: Any) -> dict[str, Any]:
        if self._aj.es_360:
            cabeceras = {"D360-API-KEY": self._aj.d360_api_key}
        else:
            cabeceras = {"Authorization": f"Bearer {self._aj.access_token}"}
        try:
            resp = self._http.request(metodo, self._url(ruta), headers=cabeceras, **kwargs)
        except httpx.HTTPError as exc:  # red caída, timeout…
            raise ErrorMeta(0, f"sin conexión con Meta ({type(exc).__name__})") from None
        try:
            datos = resp.json()
        except ValueError:
            datos = {}
        if resp.status_code >= 400:
            err = datos.get("error") if isinstance(datos, dict) else None
            err = err if isinstance(err, dict) else {}
            raise ErrorMeta(
                resp.status_code,
                str(err.get("message") or f"HTTP {resp.status_code}"),
                err.get("code"),
            )
        return datos if isinstance(datos, dict) else {}

    def _ruta_mensajes(self) -> str:
        return "messages" if self._aj.es_360 else f"{self._aj.phone_number_id}/messages"

    def _enviar(self, wa_id: str, cuerpo: dict[str, Any]) -> str:
        """Manda un mensaje y devuelve su wamid."""
        datos = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": wa_id}
        datos.update(cuerpo)
        resp = self._pedir("POST", self._ruta_mensajes(), json=datos)
        mensajes = resp.get("messages") or [{}]
        return str(mensajes[0].get("id", ""))

    # ── envíos ──────────────────────────────────────────────────────────────
    def enviar_texto(self, wa_id: str, texto: str, *, vista_previa: bool = True) -> str:
        return self._enviar(
            wa_id,
            {"type": "text", "text": {"body": texto[:MAX_TEXTO], "preview_url": vista_previa}},
        )

    def enviar_botones(self, wa_id: str, texto: str, botones: list[tuple[str, str]]) -> str:
        """Hasta 3 botones de respuesta: lista de (id, título ≤ 20 caracteres)."""
        return self._enviar(
            wa_id,
            {
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": texto[:1024]},
                    "action": {
                        "buttons": [
                            {"type": "reply", "reply": {"id": bid, "title": titulo[:MAX_TITULO_BOTON]}}
                            for bid, titulo in botones[:MAX_BOTONES]
                        ]
                    },
                },
            },
        )

    def enviar_video(self, wa_id: str, enlace: str, pie: str = "") -> str:
        """Vídeo por enlace público HTTPS (Meta lo descarga; MP4 H.264 + AAC)."""
        video: dict[str, Any] = {"link": enlace}
        if pie:
            video["caption"] = pie[:1024]
        return self._enviar(wa_id, {"type": "video", "video": video})

    def enviar_documento(self, wa_id: str, enlace: str, nombre: str, pie: str = "") -> str:
        doc: dict[str, Any] = {"link": enlace, "filename": nombre}
        if pie:
            doc["caption"] = pie[:1024]
        return self._enviar(wa_id, {"type": "document", "document": doc})

    def enviar_plantilla(
        self,
        wa_id: str,
        nombre: str,
        variables: list[str] | None = None,
        *,
        idioma: str = "es",
        sufijo_url: str | None = None,
    ) -> str:
        """Plantilla aprobada. ``sufijo_url`` rellena el botón de URL dinámica."""
        componentes: list[dict[str, Any]] = []
        if variables:
            componentes.append(
                {"type": "body", "parameters": [{"type": "text", "text": v} for v in variables]}
            )
        if sufijo_url is not None:
            componentes.append(
                {
                    "type": "button",
                    "sub_type": "url",
                    "index": "0",
                    "parameters": [{"type": "text", "text": sufijo_url}],
                }
            )
        plantilla: dict[str, Any] = {"name": nombre, "language": {"code": idioma}}
        if componentes:
            plantilla["components"] = componentes
        return self._enviar(wa_id, {"type": "template", "template": plantilla})

    def marcar_leido(self, wamid: str) -> None:
        self._pedir(
            "POST",
            self._ruta_mensajes(),
            json={"messaging_product": "whatsapp", "status": "read", "message_id": wamid},
        )

    # ── comprobaciones para «Conectar WhatsApp» ─────────────────────────────
    def numero(self) -> dict[str, Any]:
        """Datos del número: teléfono, nombre verificado, calidad…"""
        if self._aj.es_360:
            return self._pedir("GET", "health_status", params={"fields": "display_phone_number"})
        campos = (
            "display_phone_number,verified_name,quality_rating,code_verification_status,"
            "platform_type,is_on_biz_app,name_status,messaging_limit_tier"
        )
        return self._pedir("GET", self._aj.phone_number_id, params={"fields": campos})

    def webhook_suscrito(self) -> tuple[bool, str]:
        """(¿nos llegan los webhooks?, detalle)."""
        if self._aj.es_360:
            url = str(self._pedir("GET", "v1/configs/webhook").get("url") or "")
            esperada = f"{self._aj.url_publica}/webhook"
            if not url:
                return False, "360dialog no tiene ninguna URL de webhook puesta"
            if self._aj.url_publica and url != esperada:
                return False, f"360dialog manda los webhooks a otra URL ({url})"
            return True, url
        apps = list(self._pedir("GET", f"{self._aj.waba_id}/subscribed_apps").get("data") or [])
        if not apps:
            return False, "ninguna app suscrita a la cuenta de WhatsApp"
        return True, f"{len(apps)} app suscrita"

    def suscribir_app(self) -> bool:
        """Meta: suscribe la app al WABA. 360dialog: le dice a qué URL mandar los webhooks."""
        if self._aj.es_360:
            if not self._aj.url_publica or not self._aj.webhook_secreto:
                raise ErrorMeta(0, "falta WHATSAPP_URL_PUBLICA o WHATSAPP_WEBHOOK_SECRETO")
            self._pedir(
                "POST",
                "v1/configs/webhook",
                json={
                    "url": f"{self._aj.url_publica}/webhook",
                    "headers": {CABECERA_SECRETO: self._aj.webhook_secreto},
                },
            )
            return True
        return bool(self._pedir("POST", f"{self._aj.waba_id}/subscribed_apps").get("success"))

    def plantillas(self) -> list[dict[str, Any]]:
        if self._aj.es_360:
            datos = self._pedir("GET", "v1/configs/templates")
            return list(datos.get("waba_templates") or datos.get("data") or [])
        datos = self._pedir(
            "GET",
            f"{self._aj.waba_id}/message_templates",
            params={"fields": "name,status,category,language,rejected_reason", "limit": 100},
        )
        return list(datos.get("data") or [])

    def crear_plantilla(self, definicion: dict[str, Any]) -> dict[str, Any]:
        """Envía una plantilla a revisión (la aprueba Meta, tarda de minutos a un día)."""
        ruta = "v1/configs/templates" if self._aj.es_360 else f"{self._aj.waba_id}/message_templates"
        return self._pedir("POST", ruta, json=definicion)
