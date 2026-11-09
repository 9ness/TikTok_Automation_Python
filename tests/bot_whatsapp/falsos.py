"""Dobles de prueba: WhatsApp, editor, IA y panel sin red."""
from __future__ import annotations

from typing import Any

from whatsapp_bot.editor import ErrorEditor
from whatsapp_bot.ia import RespuestaIA
from whatsapp_bot.meta import ErrorMeta


class MetaFalso:
    def __init__(self) -> None:
        self.enviados: list[dict[str, Any]] = []
        self.falla = False
        self.falla_video = False
        self.remotas: list[dict[str, Any]] = []
        self.creadas: list[str] = []
        self.suscrita = True

    def _apunta(self, tipo: str, wa_id: str, **datos: Any) -> str:
        if self.falla:
            raise ErrorMeta(400, "fuera de la ventana de 24 h", 131047)
        self.enviados.append({"tipo": tipo, "a": wa_id, **datos})
        return f"wamid.BOT{len(self.enviados)}"

    def enviar_texto(self, wa_id: str, texto: str, **_: Any) -> str:
        return self._apunta("texto", wa_id, texto=texto)

    def enviar_botones(self, wa_id: str, texto: str, botones: list[tuple[str, str]]) -> str:
        return self._apunta("botones", wa_id, texto=texto, botones=[b[0] for b in botones])

    def enviar_video(self, wa_id: str, enlace: str, pie: str = "") -> str:
        if self.falla_video:
            raise ErrorMeta(400, "vídeo no admitido")
        return self._apunta("video", wa_id, enlace=enlace, texto=pie)

    def enviar_documento(self, wa_id: str, enlace: str, nombre: str, pie: str = "") -> str:
        return self._apunta("documento", wa_id, enlace=enlace, texto=nombre)

    def enviar_plantilla(self, wa_id: str, nombre: str, variables: list[str] | None = None, **_: Any) -> str:
        return self._apunta("plantilla", wa_id, texto=nombre, variables=variables or [])

    def numero(self) -> dict[str, Any]:
        return {"display_phone_number": "+34 600 11 12 22", "verified_name": "Nebulabs Media",
                "quality_rating": "GREEN", "is_on_biz_app": True}

    def webhook_suscrito(self) -> tuple[bool, str]:
        return (True, "1 app suscrita") if self.suscrita else (False, "ninguna app suscrita")

    def suscribir_app(self) -> bool:
        self.suscrita = True
        return True

    def plantillas(self) -> list[dict[str, Any]]:
        return list(self.remotas)

    def crear_plantilla(self, definicion: dict[str, Any]) -> dict[str, Any]:
        self.creadas.append(definicion["name"])
        return {"id": "1", "status": "PENDING"}

    # ayudas para los tests
    def textos(self) -> list[str]:
        return [e["texto"] for e in self.enviados]

    def ultimo(self) -> dict[str, Any]:
        return self.enviados[-1]


def ficha(**cambios: Any) -> dict[str, Any]:
    base = {
        "vinculado": True, "email": "laura@example.com", "nombre": "Laura Pérez", "plan_id": "pro",
        "es_prueba": False, "baneado": False, "limite_dia": 5, "usados_hoy": 2, "quedan_hoy": 3,
        "prueba_restantes": 0, "hoy": "2026-11-09", "envio_abierto": False,
        "dias": [{
            "dia": "2026-11-09", "total": 3, "listos": 2, "en_revision": 0, "en_curso": 1, "fallidos": 0,
            "todo_listo": False, "caduca": "2026-11-16", "caducado": False,
            "videos": [
                {"nombre": "gancho.mp4", "estado": "listo", "enlace": "https://x.test/d/1", "bytes": 9_000_000},
                {"nombre": "largo.mp4", "estado": "listo", "enlace": "https://x.test/d/2", "bytes": 40_000_000},
                {"nombre": "tercero.mp4", "estado": "editando", "enlace": "", "bytes": 0},
            ],
        }],
    }
    base.update(cambios)
    return base


class EditorFalso:
    configurado = True

    def __init__(self) -> None:
        self.ficha: dict[str, Any] = {"vinculado": False}
        self.caido = False
        self.codigo = "123456"
        self.pedidos: list[tuple[str, str]] = []
        self.costes: list[tuple[str, int, int]] = []
        self.desvinculados: list[str] = []

    def cliente(self, telefono: str) -> dict[str, Any]:
        if self.caido:
            raise ErrorEditor("sin conexión")
        return self.ficha

    def pedir_codigo(self, telefono: str, email: str) -> dict[str, Any]:
        self.pedidos.append((telefono, email))
        return {"ok": True}

    def confirmar_codigo(self, telefono: str, codigo: str) -> dict[str, Any]:
        if codigo != self.codigo:
            return {"ok": False, "motivo": "codigo"}
        self.ficha = ficha()
        return {"ok": True, "email": "laura@example.com", "nombre": "Laura Pérez"}

    def desvincular(self, telefono: str) -> dict[str, Any]:
        self.desvinculados.append(telefono)
        self.ficha = {"vinculado": False}
        return {"ok": True}

    def apuntar_coste(self, modelo: str, entrada: int, salida: int, *_: Any) -> dict[str, Any]:
        self.costes.append((modelo, entrada, salida))
        return {"ok": True, "usd": 0.0}

    def alcanzable(self) -> tuple[bool, str]:
        return (False, "sin conexión") if self.caido else (True, "contesta")


class IAFalsa:
    def __init__(self, texto: str = "Claro, te cuento.", derivar: bool = False, activo: bool = True) -> None:
        self.activo = activo
        self.texto = texto
        self.derivar = derivar
        self.falla = False
        self.llamadas: list[tuple[list[dict[str, Any]], str]] = []

    def responder(self, historial: list[dict[str, Any]], contexto: str = "") -> RespuestaIA | None:
        self.llamadas.append((historial, contexto))
        if self.falla:
            return None
        return RespuestaIA(texto="" if self.derivar else self.texto, derivar=self.derivar,
                           entrada=900, salida=60, usd=0.00012)


class PanelFalso:
    configurado = True

    def __init__(self) -> None:
        self.avisos: list[dict[str, Any]] = []

    def avisar(self, texto: str, *, notificar: bool = False, nivel: str = "aviso") -> bool:
        self.avisos.append({"texto": texto, "notificar": notificar, "nivel": nivel})
        return True
