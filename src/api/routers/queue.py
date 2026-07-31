"""Endpoints de la cola de jobs (lectura + cancelación + descarga de MP4)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response, status
from fastapi.responses import FileResponse

from src.api.config import APISettings, get_settings
from src.api import users
from src.api.dependencies import get_current_user, get_queue, get_web_user
from src.api.exceptions import (
    JobNotFoundError,
    UnauthorizedError,
    ValidationError,
    VideoFileNotFoundError,
)
from src.api.schemas.queue import ActiveJobResponse, QueueStateResponse
from src.queue.manager import JobQueue
from src.queue.models import Job, JobMode, JobStatus


router = APIRouter(
    prefix="/api/v1/queue",
    tags=["queue"],
    dependencies=[Depends(get_current_user)],
)


_FINAL_STATUSES = (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)


def _to_response(job: Job) -> ActiveJobResponse:
    return ActiveJobResponse(
        job_id=job.id,
        mode=job.mode.value,
        title=job.title,
        status=job.status.value,
        progress_percent=round(max(0.0, min(1.0, job.progress)) * 100, 2),
        current_step=job.progress_label or "",
        estimated_remaining_seconds=job.eta_s,
        elapsed_seconds=job.elapsed_s,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        enqueued_by=job.enqueued_by,
        error=job.error,
        result_path=job.result_path,
        params=_safe_params(job.params),
        scheduled_for=getattr(job, "scheduled_for", None),
        duration_seconds=job.duration_seconds,
    )


def _safe_params(params: dict) -> dict:
    """Subset de params relevantes para el frontend. Excluye flags internos
    como `_cancel_requested` y `temp_folder`."""
    keys = {
        "user_id", "product_id", "tier", "duration", "resolution",
        "hook_category", "hook_text", "audience", "voice_id", "with_voice",
        "language", "is_shoppable", "ai_disclosure", "strategy", "n_angles",
        "regenerated_from",
    }
    return {k: v for k, v in (params or {}).items() if k in keys}


# ---------------------------------------------------------------------------
# GET /queue
# ---------------------------------------------------------------------------
def _parse_mode_filter(mode_csv: str | None) -> set[JobMode] | None:
    """Parse `?mode=tiktok_shop,presidents` → set de JobMode. Lanza
    ValidationError si algún valor no es válido."""
    if not mode_csv:
        return None
    raw_values = [m.strip() for m in mode_csv.split(",") if m.strip()]
    if not raw_values:
        return None
    try:
        return {JobMode(v) for v in raw_values}
    except ValueError as e:
        valid = sorted(m.value for m in JobMode)
        raise ValidationError(
            f"Modo desconocido en filtro: {e}. Modos válidos: {valid}",
            details={"input": mode_csv, "valid_modes": valid},
        )


@router.get("", response_model=QueueStateResponse)
def get_queue_state(
    queue: Annotated[JobQueue, Depends(get_queue)],
    mode: str | None = Query(
        default=None,
        description="CSV de modos para filtrar (ej. 'tiktok_shop,presidents'). Default: todos.",
    ),
    finished_limit: int = Query(default=5, ge=1, le=100),
    de: str | None = Query(
        default=None,
        description=(
            "De quién ver los trabajos. Solo un admin puede pedir los de "
            "otro; 'todos' los mezcla. Por defecto, los propios."
        ),
    ),
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> QueueStateResponse:
    mode_filter = _parse_mode_filter(mode)
    all_jobs = queue.get_all()
    if mode_filter is not None:
        all_jobs = [j for j in all_jobs if j.mode in mode_filter]

    # Cada uno ve LO SUYO. Un admin puede pedir la de otro o la de todos; a
    # quien no lo es se le ignora el parámetro (no basta con ocultarlo en la
    # interfaz: la URL se puede escribir a mano).
    admin = users.es_admin(usuario)
    quiere = (de or "").strip() if admin else ""
    if quiere != "todos":
        objetivo = quiere or usuario
        if objetivo:
            all_jobs = [j for j in all_jobs if (j.enqueued_by or "") == objetivo]

    # Aviso para el admin: cuántos trabajos hay de los DEMÁS ahora mismo.
    otros: dict[str, int] = {}
    if admin:
        for j in queue.get_all():
            duenio = (j.enqueued_by or "").strip()
            if duenio and duenio != usuario and j.status in (
                JobStatus.PENDING, JobStatus.RUNNING
            ):
                otros[duenio] = otros.get(duenio, 0) + 1
    active = [
        j for j in all_jobs
        if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
    ]
    finished = [j for j in all_jobs if j.status in _FINAL_STATUSES]
    finished.sort(key=lambda j: j.finished_at or 0, reverse=True)
    return QueueStateResponse(
        active_jobs=[_to_response(j) for j in active],
        pending_count=sum(1 for j in active if j.status == JobStatus.PENDING),
        running_count=sum(1 for j in active if j.status == JobStatus.RUNNING),
        recent_completed=[_to_response(j) for j in finished[:finished_limit]],
        viendo=quiere or usuario or "",
        es_admin=admin,
        activos_de_otros=otros,
    )


# ---------------------------------------------------------------------------
# GET /queue/{job_id}
# ---------------------------------------------------------------------------
@router.get("/{job_id}", response_model=ActiveJobResponse)
def get_job(
    job_id: str,
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> ActiveJobResponse:
    for j in queue.get_all():
        if j.id == job_id:
            return _to_response(j)
    raise JobNotFoundError(
        f"Job '{job_id}' no encontrado.",
        details={"job_id": job_id},
    )


# ---------------------------------------------------------------------------
# GET /queue/{job_id}/summary — resumen ejecutivo del job (editor_auto)
# ---------------------------------------------------------------------------
# Lee `temp_work/editor_diagnostic_<job_id>.json` y devuelve métricas
# pre-procesadas (duración antes/después, % cortado, quality score,
# breakdown de cortes por fuente, false-starts detectados, silencios
# remanentes). El frontend lo consume para mostrar un dialog ejecutivo
# en lugar de logs raw.
@router.get("/{job_id}/summary")
def get_job_summary(
    job_id: str,
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> dict:
    import json
    import os

    job = next((j for j in queue.get_all() if j.id == job_id), None)
    if job is None:
        raise JobNotFoundError(
            f"Job '{job_id}' no encontrado.",
            details={"job_id": job_id},
        )

    # Base: info del propio job (siempre disponible)
    gen_s: float | None = None
    if job.finished_at is not None and job.started_at is not None:
        gen_s = max(0.0, job.finished_at - job.started_at)
    elif job.elapsed_s:
        gen_s = job.elapsed_s

    # Coste total del job — lookup DIRECTO `cost:job:{id}` en Redis.
    # Antes hacíamos `list_jobs(limit=2000)` (scan completo de hasta 2000
    # jobs) por cada card → con 7 cards = 14000 reads → la card tardaba
    # >30s en mostrar el coste. Lookup directo es ~10ms.
    total_cost_usd: float | None = None
    cost_lines_count = 0
    try:
        from src.tiktok_shop.repos.redis_base import get_shop_redis
        redis = get_shop_redis()
        if redis.is_available():
            raw = redis.get_json(f"cost:job:{job.id}")
            if raw:
                total_cost_usd = float(raw.get("total_usd") or 0.0)
                cost_lines_count = len(raw.get("lines") or [])
    except Exception:
        pass

    base: dict = {
        "job_id": job.id,
        "status": job.status.value,
        "mode": job.mode.value,
        "title": job.title,
        "generation_seconds": gen_s,
        "output_duration_seconds": job.duration_seconds,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "total_cost_usd": total_cost_usd,
        "cost_lines_count": cost_lines_count,
        "error": job.error,
        "has_diagnostic": False,
    }

    # Para jobs TikTok Shop: lookup del Generation vía gen_id de params
    # (lo escribe el runner al crear gen). Extraemos campos útiles para
    # el dialog Resumen — el más importante hoy es `clips_renderer` que
    # indica qué modelo realmente renderizó cada clip (Hailuo/Kling/Wan).
    if job.mode.value == "tiktok_shop":
        gen_id = (job.params or {}).get("gen_id")
        if isinstance(gen_id, str) and gen_id:
            try:
                from src.tiktok_shop.repos import GenerationRepo
                gen_obj = GenerationRepo().get(gen_id)
                if gen_obj is not None:
                    base["tier_used"] = gen_obj.tier_used
                    base["model_used"] = gen_obj.model_used or None
                    base["clips_renderer"] = list(gen_obj.clips_renderer or [])
            except Exception:
                pass

    # Buscar `editor_diagnostic_<job_id>.json` en temp_work (la herramienta
    # silence_cutter lo escribe ahí). Si no existe, devolvemos solo `base`.
    candidate_paths: list[str] = []
    tf = job.params.get("temp_folder") if job.params else None
    if isinstance(tf, str):
        candidate_paths.append(os.path.join(tf, f"editor_diagnostic_{job.id}.json"))
    candidate_paths.append(
        os.path.join(os.getcwd(), "temp_work", f"editor_diagnostic_{job.id}.json")
    )

    diag_path = next((p for p in candidate_paths if os.path.exists(p)), None)
    if not diag_path:
        return base

    try:
        with open(diag_path, "r", encoding="utf-8") as f:
            diag = json.load(f)
    except Exception as e:
        base["diagnostic_error"] = str(e)
        return base

    base["has_diagnostic"] = True
    base["diagnostic_path"] = diag_path

    phases = diag.get("phases", {}) or {}
    final = diag.get("final", {}) or {}
    audit = diag.get("audit", {}) or {}

    input_dur = diag.get("video_duration_s")
    output_dur = job.duration_seconds or audit.get("output_duration_s")
    total_cut = final.get("total_cut_s", 0.0)
    cut_pct = (total_cut / input_dur * 100.0) if input_dur else None

    # Auto-trim head/tail — la fase devuelve la lista de cuts; tomamos los
    # 2 extremos si existen (el primero es head si empieza en 0, el último
    # es tail si termina en input_duration).
    auto_trim_cuts = (phases.get("auto_trim") or {}).get("cuts") or []
    head_trim_s: float | None = None
    tail_trim_s: float | None = None
    for c in auto_trim_cuts:
        s = float(c.get("start", 0))
        e = float(c.get("end", 0))
        if s < 0.5:
            head_trim_s = round(e - s, 2)
        elif input_dur and e > input_dur - 0.5:
            tail_trim_s = round(e - s, 2)

    # Inter-word gaps
    iwg = phases.get("inter_word_gap") or {}
    n_long_gaps = int(iwg.get("n_cuts", 0))
    iwg_preview = (iwg.get("cuts") or [])[:5]

    # Phantom words detectados
    phantoms = phases.get("phantom_words") or {}
    n_phantoms = int(phantoms.get("n_phantoms_detected", 0))

    # False-starts (pasada 2 IA)
    pass2 = phases.get("ai_pass2_false_starts") or {}
    n_false_starts = int(pass2.get("n_cuts_parsed", 0))
    false_starts_preview = []
    for c in (pass2.get("raw_cuts") or [])[:5]:
        false_starts_preview.append({
            "kind": c.get("kind"),
            "first_attempt": c.get("first_attempt"),
            "kept_version": c.get("kept_version"),
            "reason": c.get("reason"),
        })

    # IA general (pasada 1) — cuenta de cuts por reason
    ai_general = phases.get("ai") or {}
    ai_cuts_by_reason = ai_general.get("cuts_by_reason") or {}

    # Quality + silencios remanentes
    quality_score = audit.get("quality_score")
    quality_verdict = audit.get("verdict")
    needs_requeue = bool(audit.get("needs_requeue", False))
    transcription_ok = bool(audit.get("transcription_ok", True))
    n_loose_words = int(audit.get("n_loose_words", 0))
    loose_words_preview = [
        p.get("text") for p in (audit.get("loose_words_preview") or [])[:6]
    ]
    n_surviving_stretched = int(audit.get("n_surviving_stretched", 0))
    n_remaining = int(audit.get("n_internal_silences", 0))
    remaining_preview = []
    for s in (audit.get("internal_silences_preview") or [])[:5]:
        before = ((s.get("context") or {}).get("before_word") or {}).get("word")
        after = ((s.get("context") or {}).get("after_word") or {}).get("word")
        remaining_preview.append({
            "duration_s": s.get("duration_s"),
            "input_start": s.get("input_start"),
            "input_end": s.get("input_end"),
            "before_word": before,
            "after_word": after,
        })

    base.update({
        "input_duration_seconds": input_dur,
        "output_duration_seconds_calc": output_dur,
        "cut_duration_seconds": round(total_cut, 2) if total_cut else 0.0,
        "cut_pct": round(cut_pct, 1) if cut_pct is not None else None,
        "cuts_by_source": final.get("cuts_by_source") or {},
        "n_cuts_merged": int(final.get("n_cuts_merged", 0)),
        "n_keep_segments": int(final.get("n_keep_intervals", 0)),
        "head_trim_seconds": head_trim_s,
        "tail_trim_seconds": tail_trim_s,
        "n_long_gaps_cut": n_long_gaps,
        "long_gaps_preview": iwg_preview,
        "n_phantom_words": n_phantoms,
        "n_false_starts_cut": n_false_starts,
        "false_starts_preview": false_starts_preview,
        "ai_cuts_by_reason": ai_cuts_by_reason,
        "quality_score": quality_score,
        "quality_verdict": quality_verdict,
        # Veredicto EXPLICABLE: etiqueta + dimensiones (Contenido/Ritmo/
        # Limpieza) + avisos de baja confianza. Lo que el operador lee de
        # un vistazo para saber QUÉ puntuó, no solo el número.
        "verdict_detail": audit.get("verdict_detail"),
        # Auto-corrección: intentos y mejora de score por reintento
        # (p.ej. [{"attempt":1,"score_before":94,"score_after":100,...}]).
        "self_heal": diag.get("self_heal"),
        "needs_requeue": needs_requeue,
        "transcription_ok": transcription_ok,
        "n_loose_words": n_loose_words,
        "loose_words_preview": loose_words_preview,
        "n_surviving_stretched": n_surviving_stretched,
        "n_silences_remaining": n_remaining,
        "silences_remaining_preview": remaining_preview,
        "tools_used": job.params.get("tools_used") if job.params else None,
    })
    return base


# ---------------------------------------------------------------------------
# GET /queue/{job_id}/logs — logs línea-a-línea del job (lazy fetch)
# ---------------------------------------------------------------------------
# Razón para tenerlo separado del `/queue/{id}`: cada job acumula hasta 200
# líneas y nos meteríamos un payload pesado en cada snapshot del WS. Aquí
# se piden solo cuando el frontend abre el dialog "Ver logs".
@router.get("/{job_id}/logs")
def get_job_logs(
    job_id: str,
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> dict:
    for j in queue.get_all():
        if j.id == job_id:
            return {
                "job_id": j.id,
                "status": j.status.value,
                "title": j.title,
                "lines": list(j.logs),
                "error": j.error,
                "current_step": j.progress_label,
                "started_at": j.started_at,
                "finished_at": j.finished_at,
            }
    raise JobNotFoundError(
        f"Job '{job_id}' no encontrado.",
        details={"job_id": job_id},
    )


# ---------------------------------------------------------------------------
# DELETE /queue/{job_id} — cancel/remove (+ opcionalmente borra el MP4)
# ---------------------------------------------------------------------------
# Rutas seguras donde se permite el borrado físico — anti path-traversal.
# Solo aceptamos paths bajo los roots de Drive de los 3 programas; si el
# `result_path` cae fuera (ej. en un /etc/), rechazamos para no permitir
# que un job manipulado borre archivos arbitrarios del server.
def _is_path_under_safe_roots(path: str) -> bool:
    import os
    abs_path = os.path.abspath(path)
    safe_roots: list[str] = []
    try:
        from src.editor_auto.config import resolve_editor_root
        safe_roots.append(os.path.abspath(resolve_editor_root()))
    except Exception:
        pass
    try:
        from src.tiktok_shop.config import resolve_shop_root
        safe_roots.append(os.path.abspath(resolve_shop_root()))
    except Exception:
        pass
    try:
        from src.utils import load_config
        cfg = load_config()
        out = cfg.get("paths", {}).get("output_folder")
        if out:
            safe_roots.append(os.path.abspath(out))
    except Exception:
        pass
    for root in safe_roots:
        if not root:
            continue
        try:
            if os.path.commonpath([abs_path, root]) == root:
                return True
        except ValueError:
            # Drive letters distintos en Windows → commonpath lanza ValueError
            continue
    return False


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def cancel_or_remove_job(
    job_id: str,
    queue: Annotated[JobQueue, Depends(get_queue)],
    delete_file: bool = False,
) -> Response:
    """- Si el job está activo (pending/running) → lo CANCELA.
    - Si el job está en estado final → lo QUITA del historial persistente.
    - Si `delete_file=true` Y el job está en estado final Y tiene
      `result_path` válido bajo una raíz segura → borra también el MP4
      del disco (Drive Desktop sincronizará el borrado a Google Drive).
    """
    import os as _os

    job = next((j for j in queue.get_all() if j.id == job_id), None)
    if job is None:
        raise JobNotFoundError(
            f"Job '{job_id}' no encontrado.",
            details={"job_id": job_id},
        )

    file_deleted = False
    file_error: str | None = None
    if delete_file and job.status in _FINAL_STATUSES and job.result_path:
        if _is_path_under_safe_roots(job.result_path):
            try:
                if _os.path.exists(job.result_path):
                    _os.remove(job.result_path)
                    file_deleted = True
                # Borrar también el .json adyacente de metadata si existe
                # (caso TikTok Shop: `<video>.mp4` + `<video>.json`).
                stem, ext = _os.path.splitext(job.result_path)
                meta = stem + ".json"
                if _os.path.exists(meta):
                    try:
                        _os.remove(meta)
                    except OSError:
                        pass
            except OSError as e:
                file_error = f"{type(e).__name__}: {e}"
        else:
            file_error = (
                f"result_path fuera de raíces seguras: {job.result_path}"
            )

    if job.status in _FINAL_STATUSES:
        queue.remove(job_id)
    else:
        queue.cancel(job_id)

    # 204 si todo bien. Si delete_file fue solicitado pero falló, usamos
    # un 207 con info — pero como el frontend espera 204, devolvemos 204
    # y dejamos el error en un header para visibilidad.
    headers = {}
    if delete_file:
        headers["X-File-Deleted"] = "1" if file_deleted else "0"
        if file_error:
            headers["X-File-Error"] = file_error[:200]
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=headers)


# ---------------------------------------------------------------------------
# POST /queue/{job_id}/reorder — sube/baja un PENDING en la cola
# ---------------------------------------------------------------------------
@router.post(
    "/{job_id}/reorder",
    status_code=status.HTTP_204_NO_CONTENT,
)
def reorder_job(
    job_id: str,
    queue: Annotated[JobQueue, Depends(get_queue)],
    direction: str,
) -> Response:
    """Reordena un job PENDING en la cola.

    Query param `direction`:
      - `up`   → sube 1 posición (swap con el PENDING anterior)
      - `down` → baja 1 posición
      - `top`  → mueve al principio (próximo en ejecutarse cuando un
                 worker quede libre)

    Si el job no es PENDING o ya está en el extremo correspondiente,
    devuelve 204 igualmente (idempotente, no rompe la UI).
    """
    direction = (direction or "").lower().strip()
    if direction not in ("up", "down", "top"):
        raise ValidationError(
            "direction debe ser 'up', 'down' o 'top'.",
            details={"direction": direction},
        )
    if direction == "up":
        queue.move_up(job_id)
    elif direction == "down":
        queue.move_down(job_id)
    else:
        queue.move_to_top(job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# PATCH /queue/{job_id}/schedule — cambia o quita la hora programada
# ---------------------------------------------------------------------------
@router.patch(
    "/{job_id}/schedule",
    status_code=status.HTTP_200_OK,
)
def reschedule_job(
    job_id: str,
    payload: dict,
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> dict:
    """Cambia la hora programada de un job PENDING. Body:
       { "scheduled_for": "2026-01-15T02:30:00" }  → ISO 8601
       { "scheduled_for": null }                   → desprogramar (ejecuta ya)

    Solo aplica a jobs en estado PENDING. RUNNING/COMPLETED/FAILED no
    se pueden reprogramar.
    """
    raw = payload.get("scheduled_for") if isinstance(payload, dict) else None
    scheduled_ts: float | None = None
    if raw is not None and raw != "":
        try:
            from datetime import datetime
            import time as _t
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            ts = dt.timestamp()
            # Si la nueva hora está en el pasado (o casi), desprogramamos.
            scheduled_ts = ts if ts > _t.time() + 30 else None
        except (ValueError, AttributeError) as e:
            raise ValidationError(
                f"scheduled_for inválido — esperado ISO 8601. Error: {e}",
                details={"scheduled_for": raw},
            )
    ok = queue.reschedule(job_id, scheduled_ts)
    if not ok:
        raise JobNotFoundError(
            f"Job '{job_id}' no encontrado o no está en estado PENDING.",
            details={"job_id": job_id},
        )
    return {"job_id": job_id, "scheduled_for": scheduled_ts}


# ---------------------------------------------------------------------------
# DELETE /queue/recent — vacía el historial de jobs finalizados
# ---------------------------------------------------------------------------
@router.delete(
    "/recent/all",
    status_code=status.HTTP_200_OK,
)
def clear_recent(
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> dict:
    """Elimina TODOS los jobs en estado final del historial persistente.
    Los jobs activos (pending/running) NO se tocan."""
    removed = queue.clear_finished()
    return {"removed": removed}


# ---------------------------------------------------------------------------
# Router secundario sin auth global — para <video src> / <a download> que
# no pueden mandar headers `X-API-Key`. Acepta `?api_key=` como fallback.
# ---------------------------------------------------------------------------
video_router = APIRouter(
    prefix="/api/v1/queue",
    tags=["queue"],
)


def _find_job(queue: JobQueue, job_id: str) -> Job:
    for j in queue.get_all():
        if j.id == job_id:
            return j
    raise JobNotFoundError(
        f"Job '{job_id}' no encontrado.",
        details={"job_id": job_id},
    )


def _auth_or_raise(settings: APISettings, header: str | None, query: str | None) -> None:
    if not settings.api_key:
        return
    provided = header or query
    if not provided or provided != settings.api_key:
        raise UnauthorizedError("API key inválida o ausente.")


@video_router.get("/{job_id}/video")
def stream_job_video(
    job_id: str,
    queue: Annotated[JobQueue, Depends(get_queue)],
    settings: Annotated[APISettings, Depends(get_settings)],
    api_key: Annotated[str | None, Query()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> FileResponse:
    _auth_or_raise(settings, x_api_key, api_key)
    job = _find_job(queue, job_id)
    if not job.result_path:
        raise VideoFileNotFoundError(
            f"Job '{job_id}' no tiene MP4 asociado.",
            details={"job_id": job_id, "status": job.status.value},
        )
    path = Path(job.result_path)
    if not path.exists() or not path.is_file():
        raise VideoFileNotFoundError(
            f"Archivo no existe en disco: {job.result_path}",
            details={"job_id": job_id, "path": job.result_path},
        )
    return FileResponse(path=str(path), media_type="video/mp4", filename=path.name)


@video_router.get("/{job_id}/download")
def download_job_video(
    job_id: str,
    queue: Annotated[JobQueue, Depends(get_queue)],
    settings: Annotated[APISettings, Depends(get_settings)],
    api_key: Annotated[str | None, Query()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> FileResponse:
    _auth_or_raise(settings, x_api_key, api_key)
    job = _find_job(queue, job_id)
    if not job.result_path:
        raise VideoFileNotFoundError(
            f"Job '{job_id}' no tiene MP4 asociado.",
            details={"job_id": job_id},
        )
    path = Path(job.result_path)
    if not path.exists() or not path.is_file():
        raise VideoFileNotFoundError(
            f"Archivo no existe en disco: {job.result_path}",
            details={"job_id": job_id, "path": job.result_path},
        )
    # FileResponse con `filename=` añade Content-Disposition: attachment
    return FileResponse(
        path=str(path),
        media_type="application/octet-stream",
        filename=path.name,
        headers={"Content-Disposition": f'attachment; filename="{path.name}"'},
    )


@video_router.get("/{job_id}/drive-search-url")
def drive_search_url(
    job_id: str,
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> dict:
    """Devuelve una URL de búsqueda en Drive con el nombre del MP4.
    No requiere Drive API — solo construye `drive.google.com/drive/search?q=...`.

    El usuario tendrá que estar logueado en Drive en el navegador para que
    funcione. Si no encontramos el archivo localmente devolvemos None.
    """
    job = _find_job(queue, job_id)
    if not job.result_path:
        return {"url": None, "filename": None}
    filename = os.path.basename(job.result_path)
    from urllib.parse import quote
    return {
        "url": f"https://drive.google.com/drive/search?q={quote(filename)}",
        "filename": filename,
    }
