"""Vinculo telefono <-> cuenta web para el bot de WhatsApp del Editor Auto.

Claves NUEVAS (prefijo del editor, `editor_auto:`):
    wa:by_phone:{tel}   -> email de la cuenta
    wa:by_email:{email} -> telefono
    wa:codigo:{tel}     -> JSON {email, codigo, intentos, creado}  (TTL 15 min)
    wa:pedidos:{tel}    -> contador de peticiones de codigo        (TTL 1 h)

El codigo se envia al email de la cuenta (por eso prueba que el telefono es de
su dueno). `pedir_codigo` nunca revela si la cuenta existe.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import re
import secrets
import time
from datetime import datetime
from typing import Any
from urllib.parse import quote

logger = logging.getLogger("editor_auto.whatsapp_vinculo")

CODIGO_TTL_S = 15 * 60
PEDIDOS_TTL_S = 3600
MAX_PEDIDOS = 3
MAX_INTENTOS = 5
MAX_DIAS_RESUMEN = 3
ENLACE_TTL_S = 6 * 3600

_K_PHONE = "wa:by_phone:"
_K_EMAIL = "wa:by_email:"
_K_CODIGO = "wa:codigo:"
_K_PEDIDOS = "wa:pedidos:"


def normalizar_telefono(txt: Any) -> str:
    """Solo digitos. Quita `+`, espacios, guiones y el prefijo `00`.
    9 digitos que empiezan por 6-9 -> antepone 34. "" si no quedan 8-15."""
    d = re.sub(r"\D", "", str(txt or ""))
    if d.startswith("00"):
        d = d[2:]
    if len(d) == 9 and d[0] in "6789":
        d = "34" + d
    return d if 8 <= len(d) <= 15 else ""


def _redis(redis=None):
    if redis is not None:
        return redis
    from src.editor_auto.repos.redis_base import get_editor_redis
    return get_editor_redis()


def _web_repo(web_repo=None):
    if web_repo is not None:
        return web_repo
    from src.editor_auto.repos.web_account_repo import get_web_account_repo
    return get_web_account_repo()


def _email_norm(email: Any) -> str:
    return str(email or "").strip().lower()


def _nombre_cuenta(acc: dict | None) -> str:
    acc = acc or {}
    return str(acc.get("username") or acc.get("name") or "")


def email_de(telefono: str, *, redis=None) -> str:
    tel = normalizar_telefono(telefono)
    if not tel:
        return ""
    return _redis(redis).get_str(f"{_K_PHONE}{tel}") or ""


def telefono_de(email: str, *, redis=None) -> str:
    em = _email_norm(email)
    if not em:
        return ""
    return _redis(redis).get_str(f"{_K_EMAIL}{em}") or ""


def desvincular(telefono: str, *, redis=None) -> bool:
    tel = normalizar_telefono(telefono)
    if not tel:
        return False
    r = _redis(redis)
    em = r.get_str(f"{_K_PHONE}{tel}")
    if not em:
        return False
    r.delete(f"{_K_PHONE}{tel}")
    if r.get_str(f"{_K_EMAIL}{em}") == tel:
        r.delete(f"{_K_EMAIL}{em}")
    return True


def pedir_codigo(telefono: str, email: str, *, redis=None, web_repo=None, enviar=None) -> dict:
    """Genera un codigo de 6 digitos y lo manda al email de la cuenta.
    Devuelve siempre {"ok": True} exista o no la cuenta, salvo
    motivo = demasiados | telefono | sin_email."""
    tel = normalizar_telefono(telefono)
    if not tel:
        return {"ok": False, "motivo": "telefono"}
    if enviar is None:
        from src.editor_auto.services import email_notify
        if not email_notify.is_configured():
            return {"ok": False, "motivo": "sin_email"}
        enviar = email_notify._send
    r = _redis(redis)
    clave = f"{_K_PEDIDOS}{tel}"
    n = r.incr(clave)
    if n == 1:
        r.expire(clave, PEDIDOS_TTL_S)
    if n > MAX_PEDIDOS:
        return {"ok": False, "motivo": "demasiados"}

    em = _email_norm(email)
    acc = _web_repo(web_repo).get(em) if "@" in em else None
    if not acc:
        return {"ok": True}  # no se revela si la cuenta existe
    codigo = f"{secrets.randbelow(1_000_000):06d}"
    kc = f"{_K_CODIGO}{tel}"
    r.set_json(kc, {"email": em, "codigo": codigo, "intentos": 0, "creado": time.time()})
    r.expire(kc, CODIGO_TTL_S)
    texto = (
        f"Tu código para vincular WhatsApp: {codigo}. Caduca en 15 minutos. "
        "Si no lo has pedido, ignora este correo."
    )
    try:
        res = enviar(
            [em], "Tu código para vincular WhatsApp",
            f"<p>Tu código para vincular WhatsApp: <b>{codigo}</b>.</p>"
            "<p>Caduca en 15 minutos. Si no lo has pedido, ignora este correo.</p>",
            texto,
        )
        if not (res or {}).get("ok"):
            logger.warning("[wa] no se pudo enviar el codigo: %s", (res or {}).get("error"))
    except Exception as e:  # nunca romper ni revelar
        logger.warning("[wa] fallo enviando el codigo: %s", type(e).__name__)
    return {"ok": True}


def confirmar_codigo(telefono: str, codigo: str, *, redis=None, web_repo=None) -> dict:
    tel = normalizar_telefono(telefono)
    if not tel:
        return {"ok": False, "motivo": "caducado"}
    r = _redis(redis)
    kc = f"{_K_CODIGO}{tel}"
    dato = r.get_json(kc)
    if not isinstance(dato, dict):
        return {"ok": False, "motivo": "caducado"}
    intentos = int(dato.get("intentos") or 0)
    if intentos >= MAX_INTENTOS:
        return {"ok": False, "motivo": "intentos"}
    intentos += 1
    dato["intentos"] = intentos
    restante = max(1, int(CODIGO_TTL_S - (time.time() - float(dato.get("creado") or 0))))
    r.set_json(kc, dato)
    r.expire(kc, restante)
    dado = re.sub(r"\D", "", str(codigo or ""))
    if not hmac.compare_digest(dado.encode(), str(dato.get("codigo") or "").encode()):
        return {"ok": False, "motivo": "intentos" if intentos >= MAX_INTENTOS else "codigo"}
    em = _email_norm(dato.get("email"))
    # Si cualquiera de los dos lados estaba vinculado a otro, se limpia.
    viejo_em = r.get_str(f"{_K_PHONE}{tel}")
    if viejo_em and viejo_em != em:
        r.delete(f"{_K_EMAIL}{viejo_em}")
    viejo_tel = r.get_str(f"{_K_EMAIL}{em}")
    if viejo_tel and viejo_tel != tel:
        r.delete(f"{_K_PHONE}{viejo_tel}")
    r.set_str(f"{_K_PHONE}{tel}", em)
    r.set_str(f"{_K_EMAIL}{em}", tel)
    r.delete(kc)
    acc = _web_repo(web_repo).get(em) or {}
    return {"ok": True, "email": em, "nombre": _nombre_cuenta(acc)}


def _hoy_madrid() -> str:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    except Exception:
        return datetime.now().date().isoformat()


def _base_publica() -> str:
    return (os.getenv("EDITOR_BOX_PUBLIC_URL") or "https://factory.nebulabsmedia.com").rstrip("/")


def resumen_cliente(
    telefono: str, *, hoy: str | None = None, queue=None, redis=None,
    web_repo=None, user_repo=None,
) -> dict:
    """Estado del cliente vinculado a `telefono`: cuenta, cuota de hoy y los
    ultimos dias con trabajos. `{"vinculado": False}` si no hay vinculo."""
    tel = normalizar_telefono(telefono)
    r = _redis(redis)
    email = email_de(tel, redis=r) if tel else ""
    if not email:
        return {"vinculado": False}
    acc = _web_repo(web_repo).get(email) or {}
    if user_repo is None:
        from src.editor_auto.repos import UserRepo
        user_repo = UserRepo()
    user = user_repo.get_by_account_email(email)
    out: dict[str, Any] = {
        "vinculado": True,
        "email": email,
        "nombre": _nombre_cuenta(acc) or (user.name if user else ""),
        "plan_id": acc.get("planId") or None,
        "es_prueba": not acc.get("planId"),
        "baneado": bool(acc.get("banned")),
        "limite_dia": None, "usados_hoy": 0, "quedan_hoy": None,
        "prueba_restantes": None, "hoy": hoy or _hoy_madrid(),
        "envio_abierto": None, "dias": [],
    }
    hoy = out["hoy"]
    if user is None:
        return out  # cuenta web sin EditorUser aun (se crea al primer uso)

    # Import perezoso: web_upload importa este modulo desde _maybe_notify_ready.
    from src.api.routers.editor_auto import web_upload as wu
    from src.api.web_ticket import make_ticket
    from src.editor_auto.config import (
        WEB_PLAN_DAILY, day_expires_at, day_send_open, manual_approval_enabled,
        user_output_day_folder,
    )
    from src.queue.models import JobStatus
    if queue is None:
        from src.api.dependencies import get_queue
        queue = get_queue()

    # --- Cuota (misma logica que web_send_to_edit) ---
    is_admin = wu._is_admin(user)
    plan = wu._user_plan(user)
    web_plan = acc.get("planId")
    if web_plan:
        plan = None
    eff = 0 if is_admin else wu._effective_daily_limit(user, plan)
    trial_left = None
    if not is_admin and plan is None:
        if web_plan:
            if user.daily_video_limit_override is None:
                eff = WEB_PLAN_DAILY.get(str(web_plan), 3)
        else:
            trial_left = max(0, int(acc.get("trialVideos") or 0))
    usados = len(wu._get_day_jobs(user.id, hoy))
    quedan = max(0, eff - usados) if eff > 0 else None
    if trial_left is not None:
        quedan = trial_left if quedan is None else min(quedan, trial_left)
    out["limite_dia"] = eff if eff > 0 else None
    out["usados_hoy"] = usados
    out["quedan_hoy"] = quedan
    out["prueba_restantes"] = trial_left
    out["envio_abierto"] = bool(day_send_open(hoy) and (is_admin or usados == 0))

    # --- Dias recientes con trabajos ---
    gate = manual_approval_enabled()
    by_id = {j.id: j for j in queue.get_all()}
    terminal = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}
    dias_set = r.smembers(f"{wu._SENT_DAYS_KEY}{user.id}") or []
    dias = sorted((d for d in dias_set if wu.is_valid_day(d) and d <= hoy), reverse=True)
    base = _base_publica()
    for day in dias:
        meta = wu._get_day_jobs(user.id, day)
        if not meta:
            continue
        if len(out["dias"]) >= MAX_DIAS_RESUMEN:
            break
        approved = wu._approved_set(user.id, day)
        devueltos = wu._devueltos(user.id, day)
        items: list[dict] = []
        done = 0
        for m in meta:
            job = by_id.get(m.get("job_id"))
            if job and job.status in terminal:
                done += 1
            out_name = os.path.basename(job.result_path) if (job and job.result_path) else None
            passed = bool(
                job and job.status == JobStatus.COMPLETED and out_name
                and wu._job_deliverable(job, wu._job_score(job))
            )
            aprobado = (not gate) or bool(out_name and out_name in approved)
            if job is None or job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                estado = "fallido"
            elif job.status == JobStatus.RUNNING:
                estado = "editando"
            elif job.status == JobStatus.PENDING:
                estado = "en_cola"
            elif passed and aprobado:
                estado = "listo"
            else:
                estado = "en_revision"  # terminado pero retenido / sin aprobar
            if job and job.status == JobStatus.FAILED and m.get("filename") not in devueltos:
                retries = int((job.params or {}).get("auto_retry") or 0)
                if not wu._error_permanente(job.error) and retries < _max_retries():
                    estado = "editando"  # se re-edita solo
            items.append({"nombre": out_name or m.get("filename"), "estado": estado, "_out": out_name})
        revision = sum(1 for v in items if v["estado"] == "en_revision")
        todo_resuelto = done == len(meta) and revision == 0
        # Entrega todo-o-nada: nada se descarga hasta que el lote esta resuelto.
        if not todo_resuelto:
            for v in items:
                if v["estado"] == "listo":
                    v["estado"] = "en_revision"
        videos = []
        for v in items:
            enlace = None
            tam = None
            if v["estado"] == "listo" and v["_out"]:
                ticket = make_ticket(email, day, scope="download", ttl_s=ENLACE_TTL_S)
                enlace = (f"{base}/api/v1/editor-auto/web/download?day={day}"
                          f"&file={quote(v['_out'])}&ticket={ticket}")
                try:
                    tam = os.path.getsize(os.path.join(user_output_day_folder(user.name, day), v["_out"]))
                except Exception:
                    tam = None
            videos.append({"nombre": v["nombre"], "estado": v["estado"], "enlace": enlace, "bytes": tam})
        cuenta = lambda e: sum(1 for v in videos if v["estado"] == e)  # noqa: E731
        listos = cuenta("listo")
        try:
            from src.editor_auto.services.retention_sweeper import expired_days
            caducado = day in expired_days(user.id)
        except Exception:
            caducado = False
        out["dias"].append({
            "dia": day, "total": len(videos), "listos": listos,
            "en_revision": cuenta("en_revision"),
            "en_curso": cuenta("editando") + cuenta("en_cola"),
            "fallidos": cuenta("fallido"),
            "todo_listo": bool(listos and todo_resuelto),
            "caduca": day_expires_at(user, day), "caducado": caducado,
            "videos": videos,
        })
    return out


def _max_retries() -> int:
    from src.editor_auto.config import AUTO_REVIEW_MAX_RETRIES
    return AUTO_REVIEW_MAX_RETRIES
