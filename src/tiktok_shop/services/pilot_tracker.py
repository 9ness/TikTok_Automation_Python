"""Lógica del Pilot Program de TikTok Shop España.

Reglas:
  - Cuentas <5000 followers entran en Pilot automáticamente.
  - Límite: 5 shoppable videos / semana hasta graduación.
  - Para graduar (cumplir UNA):
      a) >=5000 followers
      b) >=6 shoppable videos publicados de >=8s + >=30 días + quiz aprobado + CHR>=176
      c) >=10 órdenes generadas con contenido shoppable + >=30 días en Pilot

El reset semanal del límite es cada lunes (UTC).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from src.tiktok_shop.config import (
    PILOT_GRADUATION_MIN_CHR,
    PILOT_GRADUATION_REQUIRED_DAYS,
    PILOT_GRADUATION_REQUIRED_ORDERS,
    PILOT_GRADUATION_REQUIRED_VIDEOS,
    PILOT_WEEKLY_SHOPPABLE_LIMIT,
)
from src.tiktok_shop.models import TikTokUser


def days_in_pilot(user: TikTokUser) -> int:
    try:
        started = datetime.fromisoformat(user.pilot_program.started_at)
    except ValueError:
        return 0
    return max(0, (datetime.now(timezone.utc) - started).days)


def _next_monday(today: date) -> date:
    days_ahead = (7 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def weeks_progress(user: TikTokUser) -> dict:
    """Devuelve dict con shoppable_used, shoppable_remaining, reset_at (ISO date)."""
    pp = user.pilot_program
    return {
        "shoppable_used": PILOT_WEEKLY_SHOPPABLE_LIMIT - pp.weekly_shoppable_remaining,
        "shoppable_remaining": pp.weekly_shoppable_remaining,
        "reset_at": pp.weekly_shoppable_reset_at,
    }


def _ensure_weekly_reset(user: TikTokUser) -> None:
    pp = user.pilot_program
    today = date.today()
    if not pp.weekly_shoppable_reset_at:
        pp.weekly_shoppable_reset_at = _next_monday(today).isoformat()
        return
    try:
        reset_at = date.fromisoformat(pp.weekly_shoppable_reset_at)
    except ValueError:
        pp.weekly_shoppable_reset_at = _next_monday(today).isoformat()
        return
    if today >= reset_at:
        pp.weekly_shoppable_remaining = PILOT_WEEKLY_SHOPPABLE_LIMIT
        pp.weekly_shoppable_reset_at = _next_monday(today).isoformat()


def can_publish_shoppable(user: TikTokUser) -> bool:
    if user.status == "graduated":
        return True
    _ensure_weekly_reset(user)
    return user.pilot_program.weekly_shoppable_remaining > 0


def update_pilot_progress(user: TikTokUser, *, video_was_shoppable: bool) -> TikTokUser:
    """Llamar tras encolar (o publicar) un vídeo shoppable.

    - Decrementa el contador semanal si shoppable.
    - Recalcula `graduation_eligible`.
    """
    _ensure_weekly_reset(user)
    pp = user.pilot_program
    if video_was_shoppable and user.status == "pilot":
        if pp.weekly_shoppable_remaining > 0:
            pp.weekly_shoppable_remaining -= 1
        pp.shoppable_videos_published += 1

    pp.graduation_eligible = _check_graduation_eligible(user)
    user.touch()
    return user


def _check_graduation_eligible(user: TikTokUser) -> bool:
    if user.status == "graduated":
        return True
    pp = user.pilot_program
    days = days_in_pilot(user)

    # Vía A: 5000+ followers
    if user.followers_count >= 5000:
        return True

    # Vía B: 6 vids shoppable + 30 días + quiz + CHR>=176
    if (
        pp.shoppable_videos_published >= PILOT_GRADUATION_REQUIRED_VIDEOS
        and days >= PILOT_GRADUATION_REQUIRED_DAYS
        and pp.quiz_passed
        and user.creator_health_rating >= PILOT_GRADUATION_MIN_CHR
    ):
        return True

    # Vía C: 10 órdenes + 30 días
    if (
        pp.orders_generated >= PILOT_GRADUATION_REQUIRED_ORDERS
        and days >= PILOT_GRADUATION_REQUIRED_DAYS
    ):
        return True

    return False
