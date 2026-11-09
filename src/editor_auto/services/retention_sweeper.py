"""Caducidad de los vídeos de clientes web del Editor Auto (liberar Drive).

Política (9/11/2026):
  - EDITADOS (`salida/<día>/`): se borran `user_retention_days(user)` días
    después de su día de publicación (30 por defecto). El cliente lo ve en la
    web («Descárgalos antes del …») y en el email de listos.
  - ORIGINALES (`entrada/<día>/` y la carpeta plana `recuperacion/`): se borran
    a los `retention_source_days()` días (10: la FAQ promete
    corregir lo que se avise en 7 días desde la entrega). Nunca si el día tiene trabajos
    sin terminar (pendientes o en curso).
  - `retention_days_override` por cliente: 0 = no borrar nunca sus editados
    (permiso especial); N = N días.
  - Solo cuentas web (`account_email`). Las carpetas compartidas por Drive de
    los usuarios antiguos no se tocan.

Al caducar un día de `salida/` se borran sus claves Redis de día y el día pasa
de `webdays_sent:{uid}` a `webdays_expired:{uid}` (la web lo pinta «borrado»).

Se ejecuta desde el loop del draft_sweeper (cada `INTERVAL_S`), y a mano con
`scripts/caducidad_clientes.sh simular|ejecutar` (`dry_run`).
"""
from __future__ import annotations

import logging
import os
import shutil
import time
from datetime import date, datetime, timedelta

from src.editor_auto.config import (
    is_valid_day,
    retention_source_days,
    user_folder,
    user_input_folder,
    user_output_folder,
    user_recovery_folder,
    user_retention_days,
)
from src.editor_auto.repos import UserRepo
from src.editor_auto.repos.redis_base import get_editor_redis

logger = logging.getLogger("editor_auto.retention")

INTERVAL_S = 6 * 3600.0
_LAST_RUN_KEY = "retention:last_run"

SENT_DAYS_KEY = "webdays_sent:"
EXPIRED_DAYS_KEY = "webdays_expired:"
# Claves por {uid}:{día} que dejan de servir cuando el día caduca.
DAY_KEYS = (
    "webday_jobs:", "webday_sentfiles:", "webday_approved:", "webday_attention:",
    "webday_notified:", "webday_refunded:", "webday_carried:", "webday_reminded:",
    "webday_carry_mailed:", "webday_locked:",
)
_SENT_INDEX_KEY = "web_sent_index"


def _today() -> date:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Madrid")).date()
    except Exception:
        return date.today()


def _size(path: str) -> int:
    if os.path.isfile(path):
        try:
            return os.path.getsize(path)
        except OSError:
            return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _remove(path: str) -> None:
    if os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)


def _day_has_open_jobs(user_id: str, day: str, open_ids: set[str]) -> bool:
    """¿Algún trabajo de ese día sigue pendiente o en curso?"""
    try:
        meta = get_editor_redis().get_json(f"webday_jobs:{user_id}:{day}")
    except Exception:
        return True  # sin saberlo, no se borra
    if not isinstance(meta, list):
        return False
    return any(isinstance(m, dict) and m.get("job_id") in open_ids for m in meta)


def _expire_day_keys(user_id: str, day: str) -> None:
    r = get_editor_redis()
    keys = [f"{p}{user_id}:{day}" for p in DAY_KEYS]
    r._cmd(["DEL", *keys])
    r._cmd(["SREM", f"{SENT_DAYS_KEY}{user_id}", day])
    r._cmd(["SREM", _SENT_INDEX_KEY, f"{user_id}:{day}"])
    r._cmd(["SADD", f"{EXPIRED_DAYS_KEY}{user_id}", day])


def expired_days(user_id: str) -> set[str]:
    try:
        return set(get_editor_redis().smembers(f"{EXPIRED_DAYS_KEY}{user_id}") or [])
    except Exception:
        return set()


def sweep_user(user, *, dry_run: bool, open_ids: set[str], log=logger.info) -> list[dict]:
    """Borra (o lista, con dry_run) lo caducado de un usuario web.
    Devuelve [{tipo, ruta, bytes}]."""
    out: list[dict] = []
    today = _today()
    src_days = retention_source_days()
    out_days = user_retention_days(user)

    def _hit(tipo: str, path: str, day: str | None = None) -> None:
        b = _size(path)
        out.append({"usuario": user.name, "tipo": tipo, "ruta": path, "bytes": b})
        if dry_run:
            return
        try:
            _remove(path)
            log(f"[caducidad] 🗑️ {tipo} {user.name}: {os.path.basename(path)} ({b / 1e6:.0f} MB)")
        except OSError as e:
            out[-1]["error"] = str(e)
            log(f"[caducidad] no pude borrar {path}: {e}")
            return
        if tipo == "editados" and day:
            try:
                _expire_day_keys(user.id, day)
            except Exception as e:  # noqa: BLE001
                log(f"[caducidad] claves de {user.name}/{day} sin limpiar: {e}")

    # 1) Originales por día.
    if src_days > 0:
        try:
            dias = os.listdir(user_input_folder(user.name))
        except OSError:
            dias = []
        for d in sorted(dias):
            if not is_valid_day(d):
                continue
            if date.fromisoformat(d) + timedelta(days=src_days) >= today:
                continue
            if _day_has_open_jobs(user.id, d, open_ids):
                continue
            _hit("originales", os.path.join(user_input_folder(user.name), d))
        # Carpeta plana de originales ya procesados (por antigüedad del fichero).
        rec = user_recovery_folder(user.name)
        limite = time.time() - src_days * 86400
        try:
            for f in sorted(os.listdir(rec)):
                p = os.path.join(rec, f)
                if os.path.isfile(p) and os.path.getmtime(p) < limite:
                    _hit("originales", p)
        except OSError:
            pass

    # 2) Editados por día.
    if out_days > 0:
        try:
            dias = os.listdir(user_output_folder(user.name))
        except OSError:
            dias = []
        for d in sorted(dias):
            if not is_valid_day(d):
                continue
            if date.fromisoformat(d) + timedelta(days=out_days) >= today:
                continue
            if _day_has_open_jobs(user.id, d, open_ids):
                continue
            _hit("editados", os.path.join(user_output_folder(user.name), d), d)
    return out


def open_job_ids(queue=None) -> set[str] | None:
    """Ids de trabajos pendientes o en curso. Sin cola a mano usa la de la API
    YA creada (nunca abre otra: se pondría a editar). None = no se sabe."""
    try:
        from src.queue.models import JobStatus
        if queue is None:
            from src.api import dependencies as deps
            queue = getattr(deps, "_API_QUEUE", None)
        if queue is None:
            return None
        return {j.id for j in queue.get_all()
                if j.status in (JobStatus.PENDING, JobStatus.RUNNING)}
    except Exception:
        return None


def sweep(*, dry_run: bool = False, open_ids: set[str] | None = None, log=logger.info) -> list[dict]:
    try:
        users = UserRepo().list_all()
    except Exception as e:
        log(f"[caducidad] no pude listar usuarios: {e}")
        return []
    if open_ids is None:
        open_ids = open_job_ids()
    if open_ids is None:
        log("[caducidad] sin acceso a la cola: no se borra nada esta vez")
        return []
    res: list[dict] = []
    for user in users:
        if getattr(user, "deleted", False) or not getattr(user, "account_email", None):
            continue
        if not os.path.isdir(user_folder(user.name)):
            continue
        try:
            res += sweep_user(user, dry_run=dry_run, open_ids=open_ids, log=log)
        except Exception as e:  # noqa: BLE001
            log(f"[caducidad] {user.name} falló: {e}")
    return res


def maybe_sweep(open_ids: set[str] | None = None, log=logger.info) -> None:
    """Pasada real si han pasado INTERVAL_S desde la anterior (lo llama el loop
    del draft_sweeper cada 30 min). `settings:retention_enabled` = 0 la apaga."""
    r = get_editor_redis()
    try:
        if str(r.get_str("settings:retention_enabled") or "1").strip() in ("0", "false", "no"):
            return
        last = float(r.get_str(_LAST_RUN_KEY) or 0)
    except Exception:
        return
    if time.time() - last < INTERVAL_S:
        return
    r.set_str(_LAST_RUN_KEY, str(time.time()))
    hechos = sweep(dry_run=False, open_ids=open_ids, log=log)
    if hechos:
        total = sum(h["bytes"] for h in hechos if not h.get("error"))
        log(f"[caducidad] {len(hechos)} borrados, {total / 1e9:.2f} GB liberados")
