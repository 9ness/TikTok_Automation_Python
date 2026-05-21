"""Modelo de usuario del programa Editor Auto.

Cada usuario tiene UN flujo (lista de ToolStep) que se ejecuta sobre el
vídeo input al generar. El orden de las herramientas en `tool_flow` es
indicativo — el orchestrator reordena por `position_weight` para garantizar
flujo correcto (ej. cortar antes que poner subs).

La config de cada herramienta vive embebida en `ToolStep.config` para que
la UI pueda editarla por usuario sin tocar otras entidades.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from .billing import Subscription, UsageStats


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ToolStep(BaseModel):
    """Una herramienta dentro del flujo de un usuario.

    Attrs:
        tool_id: slug canónico de la herramienta (ej. "subs_auto",
            "silence_cutter"). Debe existir en `tools.registry`.
        enabled: si False, se ignora al ejecutar (útil para deshabilitar
            temporalmente sin perder config).
        config: dict libre con la config específica de la herramienta.
            La forma la define cada `BaseTool.default_config()`.
    """

    tool_id: str
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class EditorUser(BaseModel):
    """Usuario del Editor Auto. UN flujo por usuario (por ahora)."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    name: str                      # nombre carpeta (sin @ — esto no es TikTok)
    display_name: str = ""
    description: str = ""
    tool_flow: list[ToolStep] = Field(default_factory=list)
    drive_folder: str | None = None     # path local Drive sincronizado
    # Lista de emails conocidos a los que se les ha dado acceso a alguna
    # carpeta alguna vez. Se actualiza al hacer share (append si nuevo).
    # Permite a la UI mostrarlos siempre — el admin puede re-conceder o
    # revocar acceso a esos emails con un click sin re-tipearlos.
    # `revoke_permission` NO los elimina; solo el endpoint de
    # `forget_share_email` los borra explícitamente.
    known_share_emails: list[str] = Field(default_factory=list)
    # Si `auto_enqueue=True`, un background watcher escanea periódicamente
    # la carpeta entrada/ de este usuario y encola los vídeos nuevos sin
    # intervención. Pensado para clientes "set and forget": suben vídeo a
    # Drive → en <1 minuto el job arranca. Vídeos con mtime < 30s se
    # ignoran para no encolar uploads aún en progreso.
    auto_enqueue: bool = False
    # Billing — opcional. `subscription=None` significa "user de prueba"
    # (sin cuotas ni ventana horaria). Útil para QA, betas internos, demos.
    subscription: Subscription | None = None
    usage: UsageStats = Field(default_factory=UsageStats)
    # Code propio (auto-generado al activar primera suscripción o al pulsar
    # "generar code" en UI). Otros users pueden usarlo al registrarse para
    # darle descuento al owner el mes siguiente.
    referral_code: str | None = None
    # Code que ESTE user usó al registrarse (si lo hizo). Solo lectura tras
    # creación — no se puede cambiar a posteriori.
    referred_by_code: str | None = None
    deleted: bool = False
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)

    def touch(self) -> None:
        self.updated_at = _now_iso()

    def enabled_steps(self) -> list[ToolStep]:
        return [s for s in self.tool_flow if s.enabled]
