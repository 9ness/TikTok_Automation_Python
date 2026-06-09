"""Background sweeper de BORRADORES sin enviar (subidos a `entrada/<día>/`
pero nunca mandados a edición).

Política HÍBRIDA (la elegida con el cliente):
  1) RECORDATORIO: si hoy hay borradores sin enviar y se acerca el cierre,
     email "tienes vídeos sin mandar a edición" (una vez al día).
  2) ARRASTRAR: al pasar el día, los borradores sin enviar se mueven al
     PRÓXIMO día abierto con cuota libre del usuario → reaparecen donde sí
     se pueden enviar y el cliente decide.
  3) BORRAR (último recurso): si un borrador lleva sin enviarse > GRACE_DAYS
     (por su mtime), se borra para liberar Drive.

Modelo: polling cada INTERVAL_S (igual que el watcher de auto-enqueue; el FS
es un mount rclone y los eventos no son fiables). Idempotente y defensivo:
cualquier error por usuario/archivo se loguea y NO para el loop.

Notas de diseño:
  - "Enviado" = filename en el set Redis `webday_sentfiles:{user}:{day}` que
    escribe el endpoint web al mandar a edición. No tocamos esos archivos.
  - "Espacio" en un día = nº de vídeos en `entrada/<día>/` (enviados + borra-
    dores) < cuota diaria del plan (o 3 para prueba; admin = sin tope).
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from datetime import date, datetime, timedelta

from src.editor_auto.config import (
    is_valid_day,
    day_send_open,
    send_cutoff_hour,
    send_cutoff_minute,
    user_input_folder,
    user_input_day_folder,
)
from src.editor_auto.repos import PlanRepo, UserRepo
from src.editor_auto.repos.redis_base import get_editor_redis

logger = logging.getLogger("editor_auto.draft_sweeper")

INTERVAL_S = 1800.0          # cada 30 min
GRACE_DAYS = 3               # borrar borradores sin enviar más viejos que esto
CARRY_WINDOW_DAYS = 14       # cuántos días adelante buscar hueco
REMINDER_BEFORE_CUTOFF_MIN = 120  # ventana de recordatorio antes del cierre
_TRIAL_DAY_CAP = 3           # tope/día razonable para usuarios en prueba
EXTS = (".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm")

_SENT_KEY = "webday_sentfiles:"
_REMIND_KEY = "webday_reminded:"


def _tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Europe/Madrid")
    except Exception:
        return None


def _today() -> date:
    return datetime.now(_tz()).date()


def _sent_files(user_id: str, day: str) -> set[str]:
    try:
        return set(get_editor_redis().smembers(f"{_SENT_KEY}{user_id}:{day}") or [])
    except Exception:
        return set()


def _is_video(name: str) -> bool:
    return os.path.splitext(name)[1].lower() in EXTS


def _video_count_in_day(user_name: str, day: str) -> int:
    try:
        return sum(1 for f in os.listdir(user_input_day_folder(user_name, day)) if _is_video(f))
    except OSError:
        return 0


def _day_cap(user) -> int:
    """Cuota diaria efectiva para decidir 'espacio' al arrastrar. El override
    por usuario gana; luego el plan; si no, un tope blando de prueba."""
    if user.daily_video_limit_override is not None and user.daily_video_limit_override > 0:
        return int(user.daily_video_limit_override)
    sub = user.subscription
    if sub and sub.status in ("active", "trial"):
        plan = PlanRepo().get(sub.plan_id)
        if plan and plan.daily_video_limit > 0:
            return int(plan.daily_video_limit)
    return _TRIAL_DAY_CAP


def _next_open_day_with_space(user, start: date, cap: int) -> str | None:
    """Primer día (desde `start`) ABIERTO para enviar y con hueco de cuota."""
    for i in range(CARRY_WINDOW_DAYS):
        d = (start + timedelta(days=i)).isoformat()
        if not day_send_open(d):
            continue
        if cap == 0 or _video_count_in_day(user.name, d) < cap:
            return d
    return None


def _carry_and_clean(user, log) -> None:
    today = _today()
    cap = _day_cap(user)
    inp = user_input_folder(user.name)
    try:
        days = os.listdir(inp)
    except OSError:
        return
    now = time.time()
    for dayname in days:
        if not is_valid_day(dayname):
            continue
        try:
            d = date.fromisoformat(dayname)
        except ValueError:
            continue
        if d >= today:
            continue  # días actuales/futuros: siguen abiertos, no se tocan
        sent = _sent_files(user.id, dayname)
        folder = user_input_day_folder(user.name, dayname)
        try:
            files = os.listdir(folder)
        except OSError:
            continue
        for f in files:
            if not _is_video(f) or f in sent:
                continue
            path = os.path.join(folder, f)
            try:
                age_days = (now - os.path.getmtime(path)) / 86400.0
            except OSError:
                continue
            if age_days > GRACE_DAYS:
                try:
                    os.remove(path)
                    log(f"[draft_sweeper] 🗑️ borrado (>{GRACE_DAYS}d sin enviar): {user.name}/{dayname}/{f}")
                except OSError as e:
                    log(f"[draft_sweeper] no pude borrar {f}: {e}")
                continue
            target = _next_open_day_with_space(user, today, cap)
            if not target:
                continue  # sin hueco ahora; reintenta en el próximo sweep
            dst_dir = user_input_day_folder(user.name, target)
            os.makedirs(dst_dir, exist_ok=True)
            dst = os.path.join(dst_dir, f)
            if os.path.exists(dst):
                continue  # colisión rara: lo dejamos para no pisar nada
            try:
                shutil.move(path, dst)
                log(f"[draft_sweeper] ➡️ arrastrado {user.name}: {dayname}/{f} → {target}/")
            except OSError as e:
                log(f"[draft_sweeper] no pude mover {f}: {e}")


def _maybe_remind(user, log) -> None:
    today = _today()
    ds = today.isoformat()
    tz = _tz()
    now = datetime.now(tz)
    cutoff = datetime(today.year, today.month, today.day,
                      send_cutoff_hour(), send_cutoff_minute(), 0, tzinfo=tz)
    # Solo dentro de la ventana [cierre-120min, cierre).
    if not (cutoff - timedelta(minutes=REMINDER_BEFORE_CUTOFF_MIN) <= now < cutoff):
        return
    r = get_editor_redis()
    flag = f"{_REMIND_KEY}{user.id}:{ds}"
    try:
        if r.get_str(flag):
            return
    except Exception:
        pass
    sent = _sent_files(user.id, ds)
    try:
        drafts = [f for f in os.listdir(user_input_day_folder(user.name, ds)) if _is_video(f) and f not in sent]
    except OSError:
        return
    if not drafts:
        return
    try:
        from src.editor_auto.repos.web_account_repo import get_web_account_repo
        from src.editor_auto.services import email_notify
        if not email_notify.is_configured():
            return
        acc = get_web_account_repo().get(user.account_email) or {}
        email = (acc.get("email") or user.account_email or "").strip()
        if not email:
            return
        res = email_notify.send_unsent_reminder(
            to=[email],
            client_name=acc.get("username") or acc.get("name") or user.name,
            count=len(drafts),
            cutoff_label=f"{send_cutoff_hour()}:{send_cutoff_minute():02d}",
            panel_link=os.getenv("EDITOR_WEB_PANEL_URL", "https://nebulabsmedia.com/panel"),
        )
        if res.get("ok"):
            r.set_str(flag, "1")
            log(f"[draft_sweeper] ✉️ recordatorio enviado a {user.name} ({len(drafts)} sin enviar)")
    except Exception as e:
        log(f"[draft_sweeper] recordatorio falló para {user.name}: {e}")


def sweep(log=logger.info) -> None:
    try:
        users = UserRepo().list_all()
    except Exception as e:
        log(f"[draft_sweeper] no pude listar usuarios: {e}")
        return
    for user in users:
        if getattr(user, "deleted", False) or not getattr(user, "account_email", None):
            continue
        try:
            _carry_and_clean(user, log)
        except Exception as e:
            log(f"[draft_sweeper] carry/clean falló {user.name}: {e}")
        try:
            _maybe_remind(user, log)
        except Exception as e:
            log(f"[draft_sweeper] remind falló {user.name}: {e}")


async def sweeper_loop(stop_event: asyncio.Event) -> None:
    """Loop de fondo. Espera INTERVAL_S entre pasadas; sale al set() del event."""
    logger.info("[draft_sweeper] arrancado (cada %.0f min)", INTERVAL_S / 60)
    # Pequeño retardo inicial para no competir con el arranque.
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=20)
        return
    except asyncio.TimeoutError:
        pass
    while not stop_event.is_set():
        try:
            await asyncio.to_thread(sweep, logger.info)
        except Exception as e:
            logger.warning("[draft_sweeper] pasada falló: %s", e)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=INTERVAL_S)
        except asyncio.TimeoutError:
            pass
