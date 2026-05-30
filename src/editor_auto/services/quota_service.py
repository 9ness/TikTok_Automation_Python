"""Servicio de cuota y ventana horaria para Editor Auto.

Contiene la lógica que decide si un vídeo concreto puede encolarse YA
o si debe esperar (cuota agotada / fuera de ventana / espaciado mínimo).

API pública:
    check_can_enqueue(user) -> QuotaDecision
    register_enqueue(user) -> None      # incrementa contadores

Reset perezoso: la primera llamada del día/mes detecta el cambio de
fecha y resetea los contadores correspondientes en UsageStats.

Usuarios sin suscripción → tratados como "test" → siempre ok, sin
límites, sin ventana, sin espaciado.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from src.editor_auto.models import EditorUser, Plan
from src.editor_auto.repos import PlanRepo, UserRepo

logger = logging.getLogger("editor_auto.quota")


DecisionKind = Literal[
    "ok",                  # encolar inmediato
    "no_subscription",     # rechazado: sin plan activo (no test)
    "inactive_subscription",
    "tool_not_allowed",
    "daily_limit",
    "monthly_limit",
    "outside_window",
    "spacing",
    "promo_exhausted",
]


@dataclass(frozen=True)
class QuotaDecision:
    """Resultado del check.

    Attrs:
        ok: True si puede encolarse YA.
        kind: razón categorizada (para UI).
        message: texto en español para el log/UI.
        retry_after_seconds: si !ok pero el bloqueo es temporal
            (window/spacing), segundos hasta el próximo intento útil.
            None si el bloqueo NO se resuelve solo (límite agotado).
    """

    ok: bool
    kind: DecisionKind
    message: str
    retry_after_seconds: int | None = None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _today_iso() -> str:
    return _now_utc().strftime("%Y-%m-%d")


def _this_month_iso() -> str:
    return _now_utc().strftime("%Y-%m")


def _reset_if_needed(user: EditorUser) -> bool:
    """Resetea contadores perezosamente si cambió día/mes.

    Devuelve True si modificó algo (caller debe persistir).
    """
    today = _today_iso()
    month = _this_month_iso()
    modified = False
    if user.usage.last_reset_date != today:
        user.usage.daily_videos_used = 0
        user.usage.last_reset_date = today
        modified = True
    if user.usage.month_period != month:
        user.usage.monthly_videos_used = 0
        user.usage.month_period = month
        modified = True
    return modified


def _in_window(plan: Plan, user: EditorUser | None = None) -> tuple[bool, int]:
    """¿Estamos dentro de la ventana horaria? Usa el override del usuario
    si está, si no la del plan.

    Devuelve (ok, segundos_hasta_proxima_apertura).
    """
    now = _now_utc()
    h = now.hour
    start = plan.processing_window_start_hour
    end = plan.processing_window_end_hour
    if user is not None:
        if user.window_start_hour_override is not None:
            start = int(user.window_start_hour_override)
        if user.window_end_hour_override is not None:
            end = int(user.window_end_hour_override)

    # Caso normal: start < end (ej. 8→18)
    if start < end:
        if start <= h < end:
            return True, 0
        # Fuera de ventana. Calcular cuándo abre la siguiente.
        if h < start:
            target = now.replace(hour=start, minute=0, second=0, microsecond=0)
        else:
            # Pasada la ventana de hoy → mañana
            from datetime import timedelta
            target = (now + timedelta(days=1)).replace(
                hour=start, minute=0, second=0, microsecond=0,
            )
        delta = int((target - now).total_seconds())
        return False, max(delta, 60)

    # Caso ventana 24h (start == end == 0) o cobertura total
    if start == 0 and end >= 23:
        return True, 0

    # Caso ventana cruza medianoche (ej. 22→4) — no usado por defecto
    # pero soportado por completitud.
    if start <= h or h < end:
        return True, 0
    from datetime import timedelta
    target = now.replace(hour=start, minute=0, second=0, microsecond=0)
    if h >= end and h < start:
        target = now.replace(hour=start, minute=0, second=0, microsecond=0)
    delta = int((target - now).total_seconds())
    if delta < 0:
        target = (now + timedelta(days=1)).replace(
            hour=start, minute=0, second=0, microsecond=0,
        )
        delta = int((target - now).total_seconds())
    return False, max(delta, 60)


def _spacing_remaining(user: EditorUser, plan: Plan) -> int:
    """Segundos restantes hasta poder encolar otro vídeo respetando
    `plan.spacing_minutes`. 0 si ya se puede."""
    if plan.spacing_minutes <= 0:
        return 0
    last = user.usage.last_enqueue_at
    if not last:
        return 0
    try:
        last_dt = datetime.fromisoformat(last)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
    except Exception:
        return 0
    elapsed = (_now_utc() - last_dt).total_seconds()
    needed = plan.spacing_minutes * 60
    return max(0, int(needed - elapsed))


def check_can_enqueue(
    user: EditorUser, *, tool_ids: list[str] | None = None,
) -> QuotaDecision:
    """Decide si `user` puede encolar un vídeo ahora.

    Args:
        user: EditorUser cargado.
        tool_ids: lista de tools habilitadas en el flujo del user. Si se
            pasa, valida que el plan las permita.

    Mutates user.usage en caso de reset perezoso (caller debe persistir
    si el resultado es ok y se acaba encolando — usar register_enqueue).
    """
    # Sin plan: por defecto SIN restricciones. PERO si el admin puso un
    # `daily_video_limit_override` por usuario, lo respetamos igualmente
    # (caso "configuro máx/día sin asignar plan todavía"). El delay de
    # encolado es independiente — lo aplica el watcher por usuario.
    if user.subscription is None:
        ov = user.daily_video_limit_override
        if ov is not None and ov > 0:
            _reset_if_needed(user)
            if user.usage.daily_videos_used >= ov:
                now = _now_utc()
                from datetime import timedelta
                tomorrow = (now + timedelta(days=1)).replace(
                    hour=0, minute=0, second=0, microsecond=0,
                )
                secs = int((tomorrow - now).total_seconds())
                return QuotaDecision(
                    ok=False, kind="daily_limit",
                    message=(
                        f"cuota diaria agotada ({user.usage.daily_videos_used}/"
                        f"{ov}). Se restablece a medianoche UTC."
                    ),
                    retry_after_seconds=secs,
                )
            return QuotaDecision(
                ok=True, kind="ok",
                message=f"sin plan · {user.usage.daily_videos_used + 1}/{ov} hoy",
            )
        return QuotaDecision(
            ok=True, kind="ok", message="user de prueba (sin plan, sin cuotas)",
        )

    sub = user.subscription
    if sub.status not in ("active", "trial"):
        return QuotaDecision(
            ok=False, kind="inactive_subscription",
            message=f"suscripción {sub.status} — sin acceso al servicio",
        )

    plan = PlanRepo().get(sub.plan_id)
    if plan is None:
        return QuotaDecision(
            ok=False, kind="no_subscription",
            message=f"plan {sub.plan_id} no encontrado (¿borrado?)",
        )

    # Validar tools permitidas del plan
    if tool_ids and plan.allowed_tools:
        for tid in tool_ids:
            if tid not in plan.allowed_tools:
                return QuotaDecision(
                    ok=False, kind="tool_not_allowed",
                    message=(
                        f"el plan '{plan.slug}' no incluye la herramienta "
                        f"'{tid}'. Tools permitidas: {plan.allowed_tools}"
                    ),
                )

    # Reset diario/mensual
    _reset_if_needed(user)

    # Límite diario — el override por usuario gana al del plan.
    eff_daily = (
        user.daily_video_limit_override
        if user.daily_video_limit_override is not None
        else plan.daily_video_limit
    )
    if eff_daily > 0 and user.usage.daily_videos_used >= eff_daily:
        # Cuántos segundos hasta medianoche UTC
        now = _now_utc()
        from datetime import timedelta
        tomorrow = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        secs = int((tomorrow - now).total_seconds())
        return QuotaDecision(
            ok=False, kind="daily_limit",
            message=(
                f"cuota diaria agotada ({user.usage.daily_videos_used}/"
                f"{eff_daily}). Se restablece a medianoche UTC."
            ),
            retry_after_seconds=secs,
        )

    # Límite mensual
    if (
        plan.monthly_video_limit is not None
        and user.usage.monthly_videos_used >= plan.monthly_video_limit
    ):
        return QuotaDecision(
            ok=False, kind="monthly_limit",
            message=(
                f"cuota mensual agotada "
                f"({user.usage.monthly_videos_used}/{plan.monthly_video_limit})."
            ),
        )

    # Ventana horaria
    in_win, retry = _in_window(plan, user)
    if not in_win:
        h = _now_utc().hour
        return QuotaDecision(
            ok=False, kind="outside_window",
            message=(
                f"fuera de ventana de procesamiento "
                f"({plan.processing_window_start_hour}:00–"
                f"{plan.processing_window_end_hour}:00 UTC, ahora son las {h}:00)."
            ),
            retry_after_seconds=retry,
        )

    # Espaciado entre encolados
    spacing = _spacing_remaining(user, plan)
    if spacing > 0:
        return QuotaDecision(
            ok=False, kind="spacing",
            message=(
                f"espaciado mínimo {plan.spacing_minutes}min — "
                f"quedan {spacing // 60}min {spacing % 60}s."
            ),
            retry_after_seconds=spacing,
        )

    return QuotaDecision(
        ok=True, kind="ok",
        message=(
            f"plan {plan.slug} — "
            f"{user.usage.daily_videos_used + 1}/{eff_daily or '∞'} hoy"
        ),
    )


def register_enqueue(user: EditorUser, *, persist: bool = True) -> EditorUser:
    """Incrementa contadores tras un encolado exitoso. Persiste por
    defecto.

    No revalida cuota — el caller ya hizo `check_can_enqueue` antes.
    """
    _reset_if_needed(user)
    user.usage.daily_videos_used += 1
    user.usage.monthly_videos_used += 1
    user.usage.total_videos_ever += 1
    user.usage.last_enqueue_at = _now_utc().isoformat()
    if persist:
        UserRepo().save(user)
    return user
