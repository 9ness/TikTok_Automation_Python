"""Modelo del feedback loop de rendimiento real.

El operador registra los vídeos que YA publicó en TikTok (URL + qué
hook/ángulo usó). Apify refresca las métricas (views/likes/...) y el
operador anota manualmente pedidos/ingresos del dashboard de afiliado.

Con esto el motor aprende qué ángulos venden DE VERDAD para este
producto/operador y los prioriza al regenerar presets (winning angles
inyectados en los prompts directores).

Layout Redis (prefijo `tiktok_shop:`):
  - `published:{video_id}` → JSON del PublishedVideo
  - `published:index:{product_id}` → SET de video_ids del producto
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_tiktok_video_id(url: str) -> str:
    """Extrae el id numérico del vídeo de una URL TikTok. Vacío si no
    matchea (no rompe — el id es solo para dedupe best-effort)."""
    if not url:
        return ""
    m = re.search(r"/video/(\d+)", url)
    if m:
        return m.group(1)
    # Formato corto vm.tiktok.com/XXXX — no tiene id numérico, usamos la
    # última parte del path.
    m = re.search(r"tiktok\.com/(?:t/)?([A-Za-z0-9]+)", url)
    return m.group(1) if m else ""


class PublishedVideo(BaseModel):
    """Un vídeo publicado por el operador + sus métricas reales."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    product_id: str
    operator: str = ""                  # username del operador que lo publicó
    tiktok_url: str = ""
    tiktok_id: str = ""                 # id numérico parseado de la URL

    # Qué fórmula usó este vídeo (para atribuir rendimiento al ángulo).
    hook_text: str = ""
    angle: str = ""                     # dolor, urgencia, prueba_social, ...
    kind: str = ""                      # music | scripted
    preset_id: str | None = None        # preset del que salió (si aplica)
    sound_used: str = ""                # music_id/título del sonido montado

    # Métricas TikTok (refrescadas vía Apify).
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0

    # Métricas de negocio (manuales — del dashboard de afiliado).
    orders: int = 0
    revenue_eur: float = 0.0

    notes: str = ""
    posted_at: str | None = None        # cuándo se publicó (user o createTime)
    metrics_updated_at: str | None = None
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)

    @property
    def engagement_rate(self) -> float:
        """(likes+comments+shares)/views. 0 si no hay views."""
        if self.views <= 0:
            return 0.0
        return (self.likes + self.comments + self.shares) / self.views

    @property
    def conversion_rate(self) -> float:
        """orders/views. 0 si no hay views."""
        if self.views <= 0:
            return 0.0
        return self.orders / self.views

    def touch(self) -> None:
        self.updated_at = _now_iso()
