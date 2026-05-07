"""Widget global de cola que se renderiza en cada modo de la app.

Botón compacto "🧵 Cola" arriba a la derecha que despliega popover con:
- Trabajo en ejecución (progreso, tiempo restante, hitos del job)
- Pendientes (ordenables/cancelables vía sub-popover por job)
- Completados/fallidos recientes (con reproductor de vídeo embebido)

Auto-refresca cada 2s mientras haya jobs vivos usando `st.fragment`.
"""

from __future__ import annotations

import os
from datetime import datetime

import streamlit as st

from .manager import get_queue
from .models import MODE_LABELS, JobStatus


# ============================================================
# Helpers
# ============================================================
def _format_seconds(s: float) -> str:
    if s < 60:
        return f"{s:.0f}s"
    m, sec = divmod(int(s), 60)
    if m < 60:
        return f"{m}m {sec:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"


def _has_fragment() -> bool:
    return hasattr(st, "fragment")


# Prefijos de logs que el usuario considera "hitos" (cambios de etapa,
# éxitos, errores). Las líneas técnicas como "Procesando segmento 1_Trump"
# se filtran fuera por defecto — están detrás de un toggle.
_MILESTONE_PREFIXES = (
    "✅", "❌", "⚠️", "🚀", "🎉", "🛑",
    "🎙️", "🎬", "📝", "🎣", "🔤", "🔊", "📢", "📂",
    "▶️", "🏭", "🩺", "🏆",
)


def _filter_log_milestones(logs: list[str]) -> list[str]:
    """Devuelve solo las líneas que son hitos para el usuario (las que
    empiezan con un emoji de los `_MILESTONE_PREFIXES`). El resto son
    logs técnicos accesibles tras un toggle."""
    out = []
    for line in logs:
        body = line.strip().lstrip("- ").lstrip()
        if not body:
            continue
        if any(body.startswith(p) for p in _MILESTONE_PREFIXES):
            out.append(body)
    return out


def _format_filesize(path: str) -> str:
    """Devuelve '12.4 MB' o '?' si no se puede medir."""
    try:
        b = os.path.getsize(path)
        if b < 1024 * 1024:
            return f"{b / 1024:.0f} KB"
        return f"{b / (1024 * 1024):.1f} MB"
    except Exception:
        return "?"


# ============================================================
# Punto de entrada — botón flotante
# ============================================================
def render_queue_widget(persist_dir: str | None = None) -> None:
    """Renderiza el botón de cola como popover (no inline). Llamar una
    sola vez al principio de cada vista."""
    queue = get_queue(persist_dir)

    running = queue.get_running()
    pending = queue.get_pending()
    badge_count = len(pending) + (1 if running else 0)

    if running:
        label = f"🎬 Cola · {badge_count}"
    elif pending:
        label = f"🧵 Cola · {badge_count}"
    else:
        label = "🧵 Cola"

    if _has_fragment() and (running or pending):
        @st.fragment(run_every=2)
        def _live_block():
            _render_inner(queue)
        with st.popover(label, use_container_width=False):
            _live_block()
    else:
        with st.popover(label, use_container_width=False):
            _render_inner(queue)


# ============================================================
# Cuerpo del panel
# ============================================================
def _render_inner(queue) -> None:
    running = queue.get_running()
    pending = queue.get_pending()
    finished = queue.get_finished(limit=8)

    # ---------- ACTUAL ----------
    if running:
        st.markdown("**🎬 Generando ahora**")
        _render_running(running, queue)
    else:
        st.caption("⏸️ Sin trabajos activos.")

    # ---------- PENDIENTES ----------
    if pending:
        st.markdown(f"**🕐 En cola ({len(pending)})**")
        for i, job in enumerate(pending):
            _render_pending(job, queue, position=i, total=len(pending))

    # ---------- RECIENTES ----------
    if finished:
        with st.expander(f"✅ Recientes ({len(finished)})", expanded=False):
            for job in finished:
                _render_finished(job, queue)
            if st.button("🗑️ Limpiar recientes",
                         key="queue_clear_finished",
                         use_container_width=True):
                queue.clear_finished()
                st.rerun()


# ============================================================
# Tarjeta del job EN EJECUCIÓN
# ============================================================
def _render_running(job, queue) -> None:
    mode_label = MODE_LABELS.get(job.mode, str(job.mode.value))
    title = job.title or "(sin título)"
    pct = max(0.0, min(1.0, job.progress))
    elapsed = _format_seconds(job.elapsed_s)
    eta = job.eta_s

    # Tarjeta destacada
    st.markdown(
        f"<div style='"
        f"padding:0.55rem 0.75rem; border-radius:10px; "
        f"background:linear-gradient(135deg, rgba(255,75,75,0.12), rgba(255,75,75,0.04)); "
        f"border-left:3px solid #FF4B4B; margin-bottom:0.4rem;'>"
        f"<div style='font-size:0.9rem; font-weight:600;'>{mode_label}</div>"
        f"<div style='font-size:0.78rem; opacity:0.85; "
        f"overflow:hidden; text-overflow:ellipsis; white-space:nowrap;'>"
        f"{title}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Barra de progreso con etiqueta clara
    st.progress(pct, text=f"{job.progress_label} · {int(pct*100)}%")

    # Línea de tiempo + ETA explicado en lenguaje natural
    if eta is None:
        if pct < 0.15:
            eta_part = "calculando tiempo restante…"
        else:
            eta_part = ""
    else:
        eta_part = f"queda ~{_format_seconds(eta)} aprox."
    st.caption(f"⏱️ Llevamos {elapsed}{' · ' + eta_part if eta_part else ''}")

    # Hitos del job (filtrados — solo lo importante)
    if job.logs:
        milestones = _filter_log_milestones(job.logs)
        if milestones:
            st.markdown("**Progreso del trabajo:**")
            # Mostramos los últimos 5 hitos en un caja sutil
            for line in milestones[-5:]:
                st.markdown(
                    f"<div style='font-size:0.78rem; padding:0.15rem 0; "
                    f"opacity:0.9;'>{line}</div>",
                    unsafe_allow_html=True,
                )
        # Toggle para los logs técnicos completos (escondido por defecto)
        if st.toggle("Ver logs técnicos detallados",
                     key=f"queue_logs_full_{job.id}",
                     value=False):
            st.code("\n".join(job.logs[-30:]), language=None)

    if st.button("⛔ Cancelar este trabajo",
                 key=f"queue_cancel_{job.id}",
                 use_container_width=True):
        queue.cancel(job.id)
        st.toast(f"⛔ Cancelando trabajo…")
        st.rerun()


# ============================================================
# Tarjeta de un job EN COLA (pendiente)
# ============================================================
def _render_pending(job, queue, position: int, total: int) -> None:
    mode_label = MODE_LABELS.get(job.mode, str(job.mode.value))
    title = job.title or "(sin título)"

    st.markdown(
        f"<div style='"
        f"padding:0.4rem 0.6rem; "
        f"background:rgba(255,255,255,0.03); border-radius:8px; "
        f"font-size:0.88rem; margin-bottom:0.3rem;'>"
        f"<div style='font-weight:600;'>"
        f"<span style='opacity:0.6'>#{position+1}</span> · {mode_label}</div>"
        f"<div style='font-size:0.78rem; opacity:0.8; "
        f"overflow:hidden; text-overflow:ellipsis; white-space:nowrap;'>"
        f"{title}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Acciones detrás de un único popover (no llena la UI con 4 botones)
    with st.popover("⚙️ Mover / quitar", use_container_width=True):
        st.caption(f"Posición actual: #{position+1} de {total}")
        if st.button("⏫ Saltar al principio",
                     key=f"queue_top_{job.id}",
                     use_container_width=True,
                     disabled=(position == 0)):
            queue.move_to_top(job.id)
            st.rerun()
        if st.button("⬆️ Subir una posición",
                     key=f"queue_up_{job.id}",
                     use_container_width=True,
                     disabled=(position == 0)):
            queue.move_up(job.id)
            st.rerun()
        if st.button("⬇️ Bajar una posición",
                     key=f"queue_down_{job.id}",
                     use_container_width=True,
                     disabled=(position == total - 1)):
            queue.move_down(job.id)
            st.rerun()
        st.divider()
        if st.button("🗑️ Quitar de la cola",
                     key=f"queue_del_pending_{job.id}",
                     use_container_width=True,
                     type="secondary"):
            queue.cancel(job.id)
            queue.remove(job.id)
            st.rerun()


# ============================================================
# Tarjeta de un job FINALIZADO (completado/fallido/cancelado)
# ============================================================
def _render_finished(job, queue) -> None:
    mode_label = MODE_LABELS.get(job.mode, str(job.mode.value))
    title = job.title or "(sin título)"

    if job.status == JobStatus.COMPLETED:
        emoji, accent = "✅", "#3CD05E"
    elif job.status == JobStatus.FAILED:
        emoji, accent = "❌", "#E04F5F"
    else:
        emoji, accent = "⛔", "#888888"

    finished_at = (
        datetime.fromtimestamp(job.finished_at).strftime("%H:%M")
        if job.finished_at else "?"
    )
    elapsed = _format_seconds(job.elapsed_s) if job.started_at else "?"

    has_video = (
        job.status == JobStatus.COMPLETED
        and job.result_path
        and os.path.exists(job.result_path)
    )

    # Card visual: limpio sin IDs técnicos. Si hay vídeo, mostramos
    # tamaño y duración del archivo.
    extra_info = ""
    if has_video:
        size = _format_filesize(job.result_path)
        extra_info = f" · {size}"

    st.markdown(
        f"<div style='"
        f"padding:0.45rem 0.65rem; border-radius:8px; "
        f"background:rgba(255,255,255,0.025); "
        f"border-left:3px solid {accent}; margin-bottom:0.3rem;'>"
        f"<div style='font-size:0.85rem; font-weight:600;'>"
        f"{emoji} {mode_label}</div>"
        f"<div style='font-size:0.76rem; opacity:0.85; "
        f"overflow:hidden; text-overflow:ellipsis; white-space:nowrap;'>"
        f"{title}</div>"
        f"<div style='font-size:0.72rem; opacity:0.6;'>"
        f"🕐 {finished_at} · ⏱️ {elapsed}{extra_info}"
        f"</div></div>",
        unsafe_allow_html=True,
    )

    # ---------- COMPLETADO + tiene MP4 ----------
    if has_video:
        # Toggle "Ver vídeo aquí" — embebe el reproductor sin abrir popover.
        # session_state persiste el toggle entre reruns del fragment.
        play_key = f"_play_{job.id}"
        is_playing = st.session_state.get(play_key, False)
        new_playing = st.toggle(
            "▶️ Reproducir aquí" if not is_playing else "⬛ Ocultar reproductor",
            key=f"queue_play_toggle_{job.id}",
            value=is_playing,
        )
        if new_playing != is_playing:
            st.session_state[play_key] = new_playing
            st.rerun()
        if new_playing:
            try:
                st.video(job.result_path)
            except Exception as e:
                st.warning(f"No se pudo reproducir: {e}")

        # Quitar del historial — botón directo (no en popover)
        if st.button("🗑️ Quitar del historial",
                     key=f"queue_remove_{job.id}",
                     use_container_width=True,
                     type="secondary"):
            queue.remove(job.id)
            st.toast("🗑️ Quitado")
            st.rerun()

    # ---------- FALLIDO ----------
    elif job.status == JobStatus.FAILED:
        with st.popover("🔍 Ver error y opciones", use_container_width=True):
            if job.error:
                st.caption("Detalle técnico del error:")
                st.code(job.error[:1500], language=None)
            else:
                st.caption("(sin detalle del error)")
            if st.button("🗑️ Quitar del historial",
                         key=f"queue_remove_failed_{job.id}",
                         use_container_width=True,
                         type="secondary"):
                queue.remove(job.id)
                st.toast("🗑️ Quitado")
                st.rerun()

    # ---------- CANCELADO ----------
    else:
        if st.button("🗑️ Quitar del historial",
                     key=f"queue_remove_cancel_{job.id}",
                     use_container_width=True,
                     type="secondary"):
            queue.remove(job.id)
            st.toast("🗑️ Quitado")
            st.rerun()
