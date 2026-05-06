"""Widget global de cola que se renderiza en cada modo de la app.

Muestra:
- Trabajo en ejecución (nombre, modo, % progreso, ETA, label vivo)
- Pendientes (ordenables con ⬆️ ⬇️ ⏫, cancelables)
- Completados/fallidos recientes (con botón "abrir") + limpieza

Auto-refresca cada 2s mientras haya jobs activos usando `st.fragment`
(Streamlit ≥1.33). Si no está disponible, degrada a refresco manual.
"""

from __future__ import annotations

import os
from datetime import datetime

import streamlit as st

from .manager import get_queue
from .models import MODE_LABELS, JobStatus


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


def render_queue_widget(persist_dir: str | None = None) -> None:
    """Renderiza el botón de cola como popover (no inline). Llamar una vez
    al principio de cada vista, idealmente en una columna a la derecha del
    título.

    En vez de ocupar espacio vertical de la página, se muestra como un
    botón compacto "🧵 Cola (N)" que al pulsarlo despliega el panel
    completo (running, pending, recientes)."""
    queue = get_queue(persist_dir)

    running = queue.get_running()
    pending = queue.get_pending()
    badge_count = len(pending) + (1 if running else 0)

    # Etiqueta del botón. Si hay actividad, mostramos contador destacado.
    if running:
        label = f"🎬 Cola · {badge_count}"
    elif pending:
        label = f"🧵 Cola · {badge_count}"
    else:
        label = "🧵 Cola"

    # use_container_width=False → botón compacto (no full-width). Para
    # posicionarlo en una esquina, envolver desde el llamador con un
    # st.container(key="queue_btn_floating") que el CSS sube a fixed.
    if _has_fragment() and (running or pending):
        @st.fragment(run_every=2)
        def _live_block():
            _render_inner(queue)
        with st.popover(label, use_container_width=False):
            _live_block()
    else:
        with st.popover(label, use_container_width=False):
            _render_inner(queue)


def _render_inner(queue) -> None:
    """Cuerpo del widget — re-renderiza en cada tick del fragment."""
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


def _render_running(job, queue) -> None:
    """Tarjeta destacada del job en ejecución. Móvil-first: bloque
    compacto con badge de modo, título truncado, barra de progreso
    grande, y línea de tiempo/ETA pequeña."""
    mode_label = MODE_LABELS.get(job.mode, str(job.mode.value))
    title = job.title or job.id
    pct = max(0.0, min(1.0, job.progress))
    elapsed = _format_seconds(job.elapsed_s)
    eta = job.eta_s
    eta_str = f" · ETA ~{_format_seconds(eta)}" if eta is not None else ""

    # Tarjeta destacada (acento color primary)
    st.markdown(
        f"<div style='"
        f"padding:0.55rem 0.75rem; border-radius:10px; "
        f"background:linear-gradient(135deg, rgba(255,75,75,0.12), rgba(255,75,75,0.04)); "
        f"border-left:3px solid #FF4B4B; margin-bottom:0.4rem;'>"
        f"<div style='font-size:0.9rem; font-weight:600;'>{mode_label}</div>"
        f"<div style='font-size:0.78rem; opacity:0.8; "
        f"overflow:hidden; text-overflow:ellipsis; white-space:nowrap;'>"
        f"<code>{job.id}</code> · {title}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    st.progress(pct, text=f"{job.progress_label} · {int(pct*100)}%")
    st.caption(f"⏱️ {elapsed}{eta_str}")

    # Logs últimos (mostrar 6 en móvil para no robar pantalla)
    if job.logs:
        with st.expander("📋 Logs en vivo", expanded=False):
            tail = job.logs[-8:]
            st.markdown("\n".join(f"- {line}" for line in tail))

    if st.button("⛔ Cancelar este trabajo",
                 key=f"queue_cancel_{job.id}",
                 use_container_width=True):
        queue.cancel(job.id)
        st.toast(f"⛔ Cancelando {job.id}…")
        st.rerun()


def _render_pending(job, queue, position: int, total: int) -> None:
    """Una tarjeta por job pendiente. Móvil-first: línea principal con
    info y, debajo, un único `st.popover` "Mover" que abre menú con las
    acciones en columna (en lugar de 4 mini-botones que se apilarían
    feo en móvil)."""
    mode_label = MODE_LABELS.get(job.mode, str(job.mode.value))
    title = job.title or job.id

    # Tarjeta visual de la entrada en cola
    st.markdown(
        f"<div style='"
        f"display:flex; align-items:center; justify-content:space-between; "
        f"gap:0.5rem; padding:0.4rem 0.6rem; "
        f"background:rgba(255,255,255,0.03); border-radius:8px; "
        f"font-size:0.88rem; margin-bottom:0.3rem;'>"
        f"<div style='flex:1; min-width:0; overflow:hidden; "
        f"text-overflow:ellipsis; white-space:nowrap;'>"
        f"<b>#{position+1}</b> · {mode_label}<br>"
        f"<span style='opacity:0.75; font-size:0.78rem;'>"
        f"<code>{job.id}</code> · {title}</span>"
        f"</div></div>",
        unsafe_allow_html=True,
    )

    # Popover — botón único, abre las acciones verticales (mobile-friendly)
    with st.popover(
        f"⚙️ Mover / quitar",
        use_container_width=True,
    ):
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


def _render_finished(job, queue) -> None:
    """Tarjeta resumida de un trabajo finalizado. Acciones secundarias
    detrás de un popover para no inflar la UI en móvil."""
    mode_label = MODE_LABELS.get(job.mode, str(job.mode.value))
    title = job.title or job.id

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

    filename = (
        os.path.basename(job.result_path)
        if job.result_path else "—"
    )

    st.markdown(
        f"<div style='"
        f"padding:0.4rem 0.6rem; border-radius:8px; "
        f"background:rgba(255,255,255,0.025); "
        f"border-left:3px solid {accent}; margin-bottom:0.3rem;'>"
        f"<div style='font-size:0.85rem; font-weight:600;'>"
        f"{emoji} {mode_label}</div>"
        f"<div style='font-size:0.75rem; opacity:0.75; "
        f"overflow:hidden; text-overflow:ellipsis; white-space:nowrap;'>"
        f"{title}</div>"
        f"<div style='font-size:0.72rem; opacity:0.6;'>"
        f"🕐 {finished_at} · ⏱️ {elapsed}"
        f"{' · 📄 ' + filename if job.status == JobStatus.COMPLETED else ''}"
        f"</div></div>",
        unsafe_allow_html=True,
    )

    # Acciones detrás de popover (mobile-friendly)
    with st.popover("⚙️ Acciones", use_container_width=True):
        if job.status == JobStatus.COMPLETED and job.result_path:
            st.caption(f"📂 `{job.result_path}`")
            if st.button("📂 Abrir carpeta", key=f"queue_open_{job.id}",
                         use_container_width=True):
                try:
                    os.startfile(os.path.dirname(job.result_path))  # type: ignore[attr-defined]
                except Exception:
                    st.warning("No se pudo abrir la carpeta")
        elif job.status == JobStatus.FAILED and job.error:
            st.caption("Detalle técnico del error:")
            st.code(job.error[:1500], language=None)

        if st.button("🗑️ Quitar del historial",
                     key=f"queue_remove_{job.id}",
                     use_container_width=True,
                     type="secondary"):
            queue.remove(job.id)
            st.rerun()
