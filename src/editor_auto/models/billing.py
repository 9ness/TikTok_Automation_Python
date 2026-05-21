"""Modelos de billing/planes/referidos para Editor Auto.

Diseño:
- `Plan` es un catálogo: define límites diarios, tools permitidas, precio,
  ventana de procesamiento. Editable por admin desde UI.
- `Subscription` se embebe en `EditorUser` (no es entidad separada). Cada
  user tiene 0..1 suscripción activa. None = "user de prueba" (sin límites).
- `UsageStats` también embebida en `EditorUser`. Contadores rolling de
  vídeos por día/mes. Reset perezoso en el servicio de cuota.
- `ReferralCode` es entidad separada (indexada por code). Cada user tiene
  su propio code (autogenerado) y puede referenciar el code de otro al
  registrarse → descuentos en el siguiente periodo de facturación.

Pricing reference (€/mes, sin IVA):
- Trial:    0      ·  5 vídeos totales (one-shot)
- Starter:  149    ·  3 vídeos/día
- Pro:      249    ·  5 vídeos/día        ← ★ oferta primeros 20 usuarios
- Studio:   549    · 10 vídeos/día
- Agencia:  999+   ·  custom (manual)

Margen: coste por vídeo ~0.05$. 5 vídeos/día × 30 = 150 vídeos/mes ≈ 7.5$
de coste. Revenue 249€ ≈ ~270$ → ~97% margen bruto (sin contar fixed costs).
"""

from __future__ import annotations

import secrets
import string
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _this_month_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _gen_referral_code() -> str:
    """Code corto, fácil de comunicar verbalmente. 8 chars uppercase
    alfanumérico evitando confusos (0/O, 1/I/L)."""
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))


class Plan(BaseModel):
    """Catálogo de planes — admin los edita desde la UI.

    Attrs:
        slug: identificador estable URL-safe (ej. "starter", "pro").
            NO se renombra una vez creado — los `Subscription.plan_id`
            apuntan por id, no por slug.
        daily_video_limit: máximo de vídeos/día. 0 = ilimitado.
        monthly_video_limit: tope total/mes (None = sin tope mensual).
        allowed_tools: lista de tool_id permitidos. [] = todas.
        processing_window_start_hour / _end_hour: ventana de procesamiento
            (UTC). El watcher solo encola dentro de este rango para simular
            que un humano edita en horario laboral. Ej. 8→18 = entre las
            08:00 y las 18:00 UTC.
        spacing_minutes: mínimo de minutos entre encolados consecutivos del
            mismo usuario. 0 = sin espaciado (encolar todo lo posible).
        price_eur_monthly: precio mensual en € (referencia — el cobro va
            por fuera por PayPal/Stripe).
        is_promo: si True, plan promocional (ej. early-bird). `promo_slots_*`
            limitan quién puede contratarlo.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    slug: str
    name: str
    description: str = ""

    daily_video_limit: int = 0
    monthly_video_limit: int | None = None
    allowed_tools: list[str] = Field(default_factory=list)

    processing_window_start_hour: int = 8
    processing_window_end_hour: int = 18
    # Espaciado mínimo entre encolados consecutivos del MISMO user. NO es
    # tiempo de edición (eso lo decide el runner ~6-8min/vídeo). Sirve para
    # que la salida del cliente parezca progresiva ("editor humano trabajando")
    # y no salgan los N vídeos a la vez.
    spacing_minutes: int = 0

    # Prioridad en cola. Mayor = se procesa antes que los demás cuando
    # comparten ventana. 0 = baja (Trial/Starter), 50 = normal (Pro),
    # 100 = alta (Studio), 200 = top (Agencia/Enterprise).
    queue_priority: int = 0
    # Delay artificial post-encolado antes de que el runner lo pueda
    # ejecutar. Sirve para "ralentizar" planes baratos sin tocar el
    # output del cliente (sigue siendo realista). 0 = sin delay extra.
    queue_delay_minutes: int = 0

    # Nivel de soporte — string libre, lo lee la UI para badge.
    # Valores sugeridos: "ninguno", "email", "telegram", "telegram_vip",
    # "dedicado_24_7"
    support_level: str = "email"

    # Bullets visibles en la tarjeta del plan. Frase corta por feature.
    # El admin los puede editar libremente desde la UI — son texto
    # marketing, no afectan al comportamiento del backend.
    features: list[str] = Field(default_factory=list)

    price_eur_monthly: float = 0.0
    price_eur_setup_once: float = 0.0

    is_active: bool = True
    is_promo: bool = False
    promo_slots_total: int | None = None
    promo_slots_used: int = 0

    sort_order: int = 100
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)

    def touch(self) -> None:
        self.updated_at = _now_iso()

    def tool_is_allowed(self, tool_id: str) -> bool:
        if not self.allowed_tools:
            return True
        return tool_id in self.allowed_tools


class Subscription(BaseModel):
    """Suscripción de un user a un Plan. Embebida en EditorUser.

    `None` en `EditorUser.subscription` significa "test user" → sin
    cuotas ni ventana horaria (admin/QA/yo).

    Attrs:
        plan_id: id del Plan.
        status: "active" | "paused" | "cancelled" | "trial"
        started_at: fecha alta (ISO).
        current_period_start / _end: ventana de facturación actual.
            Por defecto el día del mes en que se activó (ej. activó el 15
            → períodos van del 15 al 14 del mes siguiente).
        discount_pct_next_period: descuento a aplicar el SIGUIENTE período
            por referidos acumulados (0.0–0.5).
        notes: campo libre admin (ej. "pagó por PayPal el 14/may").
    """

    plan_id: str
    status: str = "active"
    started_at: str = Field(default_factory=_now_iso)
    current_period_start: str = Field(default_factory=_now_iso)
    current_period_end: str | None = None
    discount_pct_next_period: float = 0.0
    notes: str = ""


class UsageStats(BaseModel):
    """Contadores rolling de uso. Embebido en EditorUser.

    El servicio de cuota (`quota_service`) hace reset perezoso:
    - Si `last_reset_date != today` → daily_videos_used = 0
    - Si `month_period != this_month` → monthly_videos_used = 0

    De este modo no hace falta un cronjob para resetear — el primer check
    del día/mes lo hace.
    """

    daily_videos_used: int = 0
    monthly_videos_used: int = 0
    total_videos_ever: int = 0
    last_reset_date: str = Field(default_factory=_today_iso)
    month_period: str = Field(default_factory=_this_month_iso)
    last_enqueue_at: str | None = None


class ReferralUse(BaseModel):
    """Una aplicación concreta del code de un user."""

    referred_user_id: str
    referred_user_name: str
    used_at: str = Field(default_factory=_now_iso)
    discount_pct_applied: float = 0.25
    valid_until_period: str | None = None  # YYYY-MM al que aplica el descuento


class ReferralCode(BaseModel):
    """Code propietario de un user. Cuando otro user se registra con este
    code, se anota una `ReferralUse` y el owner recibe descuento en el
    siguiente período de facturación.

    Reglas (configurables luego):
    - Primer referido: 25% off mes siguiente
    - Dos+ referidos en el mismo mes: 50% off (cap)
    - El descuento se acumula en `EditorUser.subscription.discount_pct_next_period`
    """

    code: str = Field(default_factory=_gen_referral_code)
    owner_user_id: str
    owner_user_name: str
    uses: list[ReferralUse] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now_iso)

    def discount_for_period(self, period_yyyy_mm: str) -> float:
        """Descuento total acumulado para un período concreto. Cap 0.5."""
        pct = 0.0
        for u in self.uses:
            if u.valid_until_period == period_yyyy_mm:
                pct += u.discount_pct_applied
        return min(pct, 0.5)
