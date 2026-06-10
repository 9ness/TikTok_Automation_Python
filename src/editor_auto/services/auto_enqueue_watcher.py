"""Background watcher que encola automáticamente vídeos nuevos en
`entrada/` de los usuarios con `auto_enqueue=True`.

Modelo: polling cada `INTERVAL_S` segundos. No usamos inotify porque
las carpetas viven en un mount rclone (Drive) y los eventos del FS no
son fiables ahí. Polling cada 30s da latencia aceptable para un
flujo "subir vídeo → procesar" cuando el server está 24/7.

Reglas:
  - Solo escanea usuarios con `auto_enqueue=True` y `deleted=False`.
  - Ignora archivos con `mtime` < `MIN_FILE_AGE_S` segundos: rclone
    podría aún estar sincronizando un upload en curso.
  - Llama exactamente al MISMO endpoint que el botón Encolar (via
    helper de orquestación interno), así la lógica de move + crear
    job + companion .txt es idéntica.
  - Errors per file se loguean pero NO paran el loop: si un vídeo
    falla, los siguientes se siguen encolando.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

logger = logging.getLogger("editor_auto.auto_enqueue")


# Intervalo entre polls. 30s = latencia máxima desde que el archivo
# aparece en entrada/ hasta que se encola. Suficiente para el caso de
# uso (cliente sube de noche, ve resultado por la mañana).
INTERVAL_S = 30.0

# Edad mínima del archivo antes de considerarlo "estable". Defensa
# contra encolar un upload en progreso (rclone aún subiendo desde
# Drive). Tomado del `mtime`. 60s da margen generoso para cualquier
# vídeo razonable hasta ~500MB en redes domésticas.
MIN_FILE_AGE_S = 60.0

# Margen EXTRA cuando el flow del usuario tiene `silence_cutter_scripted`
# Y aún no existe el companion `<stem>.txt`. Damos tiempo a que el
# cliente suba el .txt (que a menudo lo hace después del vídeo). Si
# pasados estos segundos sigue sin haber companion, se encola igual y
# la tool hace fallback automático a modo sin guion.
SCRIPTED_NO_COMPANION_AGE_S = 180.0


def _user_has_scripted(user) -> bool:
    """¿El flow del usuario incluye `silence_cutter_scripted` habilitado?"""
    return any(
        s.enabled and s.tool_id == "silence_cutter_scripted"
        for s in (user.tool_flow or [])
    )


def _list_pending_videos(user) -> list[dict[str, Any]]:
    """Vídeos en `entrada/` del usuario que están listos para encolar.

    Reglas:
      1. `mtime + MIN_FILE_AGE_S < now` (general, evita uploads en curso).
      2. Si flow es scripted Y no hay companion `.txt`, esperamos hasta
         `SCRIPTED_NO_COMPANION_AGE_S` por si el cliente sube el .txt
         poco después del vídeo. Pasado ese tiempo, encolamos igual
         (la tool hará fallback a modo sin guion).
    """
    from src.editor_auto.services import folder_manager

    try:
        files = folder_manager.list_files(user.name, "entrada")
    except Exception as e:
        logger.warning(
            "[auto_enqueue] list_files falló para %s: %s", user.name, e,
        )
        return []
    now = time.time()
    is_scripted = _user_has_scripted(user)
    # Cuenta atrás por usuario: el vídeo debe llevar al menos
    # `auto_enqueue_delay_minutes` en entrada/ antes de auto-encolarse.
    # Siempre respeta el min-age global anti-uploads-en-curso. El admin
    # puede saltarse la cuenta atrás con "Encolar ya" (endpoint manual).
    user_delay_s = max(0, int(getattr(user, "auto_enqueue_delay_minutes", 0) or 0)) * 60
    min_age = max(MIN_FILE_AGE_S, user_delay_s)
    out: list[dict[str, Any]] = []
    for f in files:
        mtime = float(f.get("modified_at") or 0.0)
        if mtime <= 0:
            continue
        age = now - mtime
        if age < min_age:
            continue
        # Scripted + sin companion → margen extra para que llegue el .txt
        if is_scripted and not f.get("script") and age < SCRIPTED_NO_COMPANION_AGE_S:
            logger.debug(
                "[auto_enqueue] esperando companion .txt para %s/%s "
                "(edad %.0fs / %.0fs)",
                user.name, f["filename"], age, SCRIPTED_NO_COMPANION_AGE_S,
            )
            continue
        out.append(f)
    return out


def _enqueue_one(user, filename: str) -> bool:
    """Replica la lógica de `POST /folders/enqueue` para un vídeo.

    Devuelve True si OK, False si error. Diseño "fail-safe": ante
    CUALQUIER fallo el vídeo queda en `entrada/` (donde estaba) para
    que el operador pueda encolarlo manualmente desde la UI. Si el
    `move_file` ya tuvo éxito pero la creación del job falla, se
    intenta un rollback (cola → entrada) para no dejar el archivo
    huérfano en `cola/`.

    Antes de encolar, comprueba la cuota del user con `quota_service`.
    Si la cuota está agotada o está fuera de la ventana horaria, el
    vídeo se deja en `entrada/` y se reintenta en próximas pasadas. Esto
    es lo que permite la ilusión de "edición humana en horario laboral":
    aunque el cliente suba 20 vídeos a las 02:00, solo se procesan según
    el plan (ej. 5/día entre las 8:00 y las 18:00).
    """
    from src.editor_auto.services import folder_manager, quota_service
    from src.editor_auto.config import user_subfolder
    # CRÍTICO: usar la MISMA cola que la API (dependencies.get_queue), NO la
    # factory de Streamlit (manager.get_queue con @st.cache_resource). En el
    # proceso FastAPI, manager.get_queue crea una SEGUNDA JobQueue con sus
    # propios workers sobre el mismo queue_state.json → las dos colas divergen
    # y el race de arranque (workers antes de set_dispatcher) mata jobs con
    # "No hay dispatcher registrado". dependencies.get_queue es el singleton
    # único del proceso, con dispatcher ya registrado.
    from src.api.dependencies import get_queue
    from src.queue.models import JobMode

    # 0. CHECK DE CUOTA + VENTANA HORARIA.
    tool_ids = [s.tool_id for s in user.tool_flow if s.enabled]
    decision = quota_service.check_can_enqueue(user, tool_ids=tool_ids)
    if not decision.ok:
        logger.debug(
            "[auto_enqueue] %s/%s diferido — %s (%s)",
            user.name, filename, decision.kind, decision.message,
        )
        return False

    # 1. Detectar companion .txt opcional (NO crítico — si falla,
    #    seguimos sin guion y la tool hará fallback).
    companion_script = ""
    try:
        companion_script = (
            folder_manager.read_script_companion(
                user.name, "entrada", filename,
            ) or ""
        )
    except Exception as e:
        logger.warning(
            "[auto_enqueue] companion check falló (%s/%s): %s",
            user.name, filename, e,
        )

    # 2. Mover entrada → cola. Si falla, el vídeo sigue en entrada/.
    try:
        move_result = folder_manager.move_file(
            user.name, "entrada", "cola", filename,
        )
    except Exception as e:
        logger.warning(
            "[auto_enqueue] move entrada→cola falló para %s/%s — "
            "vídeo sigue en entrada/, encólalo manual si hace falta: %s",
            user.name, filename, e,
        )
        return False
    final_filename = move_result["filename_new"]
    input_path = os.path.join(
        user_subfolder(user.name, "cola"), final_filename,
    )

    # 3. Crear el job en la cola. Si esto falla TRAS el move,
    #    rollback: devolvemos el archivo a entrada/ para que el
    #    operador pueda re-encolar manual.
    try:
        from src.utils import load_config
        cfg = load_config()
        temp_folder = cfg["paths"]["temp_folder"]

        queue = get_queue()
        title = f"{user.name} · {final_filename}"
        n_enabled = sum(1 for s in user.tool_flow if s.enabled)
        if n_enabled > 0:
            title += f" · {n_enabled} tool(s)"

        job = queue.enqueue(
            mode=JobMode.EDITOR_AUTO,
            title=title,
            enqueued_by=user.name,
            params={
                "user_id": user.id,
                "user_name": user.name,
                "input_path": input_path,
                "source": "entrada",
                "source_filename": final_filename,
                "temp_folder": temp_folder,
                "script": companion_script,
                "tools_used": [
                    s.tool_id for s in user.tool_flow if s.enabled
                ],
                "tool_count": n_enabled,
                "auto_enqueued": True,
            },
        )
        logger.info(
            "[auto_enqueue] encolado %s/%s → job %s (companion=%s)",
            user.name, final_filename, job.id[:8],
            "sí" if companion_script else "no",
        )
        # Registrar consumo de cuota. NO crítico si falla — el job ya
        # está en cola y se procesará; lo peor es que el siguiente check
        # use contadores levemente desactualizados.
        try:
            quota_service.register_enqueue(user)
        except Exception as e:
            logger.warning(
                "[auto_enqueue] register_enqueue falló para %s: %s",
                user.name, e,
            )
        return True
    except Exception as e:
        # Rollback: mover cola → entrada para no perder el archivo.
        logger.warning(
            "[auto_enqueue] creación de job falló para %s/%s — "
            "rollback cola→entrada: %s",
            user.name, final_filename, e,
        )
        try:
            folder_manager.move_file(
                user.name, "cola", "entrada", final_filename,
            )
            logger.info(
                "[auto_enqueue] rollback OK · %s vuelve a entrada/",
                final_filename,
            )
        except Exception as rb_err:
            # Si TAMBIÉN falla el rollback, el archivo queda en cola/.
            # Lo logueamos LOUD para que el operador lo arregle a mano
            # (la UI permite mover cola→entrada con un click).
            logger.error(
                "[auto_enqueue] ❌ ROLLBACK FALLÓ para %s/%s — archivo "
                "queda en cola/, revisa manualmente: %s",
                user.name, final_filename, rb_err,
            )
        return False


def _utc_today() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).date().isoformat()


def _maybe_revoke_output(repo, user, today: str) -> bool:
    """Si el acceso a `salida` se concedió un día ANTERIOR y el usuario tiene
    `auto_revoke_output_daily`, revoca ese acceso para sus known_share_emails.
    Así, al cambiar de día, el admin vuelve a controlar cuándo se ven los
    vídeos. Devuelve True si revocó algo. Nunca rompe."""
    if not getattr(user, "auto_revoke_output_daily", True):
        return False
    rel = getattr(user, "output_released_on", None)
    if not rel or rel == today:
        return False
    from src.editor_auto.services import drive_sharing
    if not drive_sharing.is_configured():
        return False
    emails = {
        e.strip().lower()
        for e in (user.known_share_emails or [])
        if e and "@" in e
    }
    revoked = 0
    try:
        shares = drive_sharing.list_shares(user.name)
        for p in (shares.get("salida") or []):
            pe = (p.get("email") or "").strip().lower()
            pid = p.get("id") or p.get("permission_id")
            if pe and pe in emails and pid:
                try:
                    drive_sharing.revoke_permission(user.name, "salida", pid)
                    revoked += 1
                except Exception as e:
                    logger.warning(
                        "[auto_revoke] revoke %s/%s falló: %s", user.name, pe, e,
                    )
    except Exception as e:
        logger.warning("[auto_revoke] list_shares %s falló: %s", user.name, e)
        return False
    # Limpiar el flag (ya no hay acceso del día pendiente de revocar).
    user.output_released_on = None
    try:
        repo.save(user)
    except Exception:
        pass
    if revoked:
        logger.info(
            "[auto_revoke] %s: revocado acceso a salida de %d email(s) "
            "(cambió el día)", user.name, revoked,
        )
    return revoked > 0


def _scan_once() -> dict[str, int]:
    """Una pasada completa: itera usuarios y encola sus vídeos pendientes.

    Devuelve un dict `{username: n_encolados}` solo para los que tuvieron
    algo encolado, para logging resumido.
    """
    from src.editor_auto.repos.user_repo import UserRepo

    repo = UserRepo()
    users = repo.list_all() or []
    today = _utc_today()
    encolados_per_user: dict[str, int] = {}
    for u in users:
        if u.deleted:
            continue
        # Revocar acceso a salida si cambió el día (independiente de auto_enqueue).
        try:
            _maybe_revoke_output(repo, u, today)
        except Exception as e:
            logger.warning("[auto_revoke] tick %s falló: %s", u.name, e)
        if not getattr(u, "auto_enqueue", False):
            continue
        pending = _list_pending_videos(u)
        if not pending:
            continue
        n_ok = 0
        for f in pending:
            if _enqueue_one(u, f["filename"]):
                # Tras encolar uno, recargamos el user para que el
                # siguiente loop iter use el `last_enqueue_at` recién
                # actualizado y respete `spacing_minutes`. Si el plan
                # tiene espaciado >0, los demás vídeos quedarán
                # diferidos en esta pasada y se intentarán en la próxima.
                refreshed = repo.get(u.id)
                if refreshed:
                    u = refreshed
                n_ok += 1
        if n_ok > 0:
            encolados_per_user[u.name] = n_ok
    return encolados_per_user


async def watcher_loop(stop_event: asyncio.Event) -> None:
    """Loop principal — corre hasta que `stop_event` se setea.

    Cada vuelta:
      1. `_scan_once()` en un thread (es bloqueante: I/O al FS,
         repos a Redis HTTP, etc).
      2. Espera `INTERVAL_S` o hasta `stop_event` (lo que llegue antes).
    """
    logger.info(
        "[auto_enqueue] watcher arrancado (interval=%.0fs, min_age=%.0fs)",
        INTERVAL_S, MIN_FILE_AGE_S,
    )
    while not stop_event.is_set():
        try:
            result = await asyncio.to_thread(_scan_once)
            if result:
                summary = ", ".join(f"{n}×{u}" for u, n in result.items())
                logger.info("[auto_enqueue] tick: %s", summary)
        except Exception as e:
            # Defensa contra cualquier excepción inesperada — no rompe
            # el loop bajo ninguna circunstancia.
            logger.exception("[auto_enqueue] tick falló: %s", e)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=INTERVAL_S)
        except asyncio.TimeoutError:
            pass
    logger.info("[auto_enqueue] watcher detenido limpiamente")
