"""Tab 'Histórico' — dashboard de coste + lista de generaciones."""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime

import streamlit as st

from src.queue import JobMode, get_queue
from src.tiktok_shop.config import (
    ATLAS_TIERS, DURATIONS, RESOLUTIONS, VIDEO_MODELS,
)
from src.tiktok_shop.models import Product, TikTokUser, VideoGeneration
from src.tiktok_shop.repos import (
    GenerationRepo, ProductRepo, UserRepo, VoiceRepo,
)
from src.tiktok_shop.services.regenerate_service import (
    build_regen_params, build_regen_title,
)


def render() -> None:
    gen_repo = GenerationRepo()
    user_repo = UserRepo()
    product_repo = ProductRepo()

    with st.spinner("📚 Cargando histórico de generaciones (últimos 200)…"):
        generations = gen_repo.list_recent(limit=200)
    if not generations:
        st.info("Aún no hay vídeos generados. Crea uno desde '🎬 Generar Vídeo'.")
        return

    # ------------------------------------------------------------------
    # 1. Cards superiores — KPIs del mes en curso
    # ------------------------------------------------------------------
    with st.spinner("📊 Calculando agregaciones por mes…"):
        monthly = gen_repo.monthly_summary(scan_limit=200)
    months_sorted = list(monthly.keys())
    current = months_sorted[0] if months_sorted else None
    previous = months_sorted[1] if len(months_sorted) > 1 else None

    cur_total = monthly[current]["total"] if current else 0.0
    prev_total = monthly[previous]["total"] if previous else 0.0
    delta = cur_total - prev_total
    delta_fmt = f"{'+' if delta >= 0 else ''}${delta:.2f}" if previous else None

    cols = st.columns(4)
    cols[0].metric(
        f"💰 Coste mes ({current or 'sin datos'})",
        f"${cur_total:.2f}",
        delta=delta_fmt,
        delta_color="inverse",   # subir coste = rojo
    )
    cols[1].metric("📹 Total vídeos", len(generations))
    by_status: dict[str, int] = defaultdict(int)
    for g in generations:
        by_status[g.generation_status.value] += 1
    cols[2].metric("✅ Completados", by_status.get("completed", 0) + by_status.get("manual_completed", 0))
    cols[3].metric("❌ Fallos", by_status.get("failed", 0))

    # Alerta opcional: límite de gasto mensual configurable en .env
    monthly_limit = _monthly_budget_limit()
    if monthly_limit and cur_total >= monthly_limit * 0.8:
        st.warning(
            f"⚠️ Llevas ${cur_total:.2f} este mes (límite ${monthly_limit:.2f}). "
            f"Estás al {cur_total / monthly_limit * 100:.0f}%."
        )

    st.divider()

    # ------------------------------------------------------------------
    # 2. Gráficos: distribución por tier + coste por día último mes
    # ------------------------------------------------------------------
    chart_cols = st.columns(2)

    with chart_cols[0]:
        st.markdown("**Distribución por tier**")
        if current and monthly[current]["by_tier"]:
            by_tier = monthly[current]["by_tier"]
            chart_data = {VIDEO_MODELS.get(k, {}).get("name", k): v for k, v in by_tier.items()}
            st.bar_chart(chart_data, height=200)
        else:
            st.caption("Sin datos este mes")

    with chart_cols[1]:
        st.markdown("**Coste por día (últimos 30 días)**")
        per_day = _daily_cost(generations)
        if per_day:
            st.bar_chart(per_day, height=200)
        else:
            st.caption("Sin datos")

    # ------------------------------------------------------------------
    # 3. Tablas por usuario / producto
    # ------------------------------------------------------------------
    table_cols = st.columns(2)
    with table_cols[0]:
        st.markdown("**💸 Coste por usuario (todos los tiempos)**")
        per_user = _aggregate_by(generations, lambda g: g.user_id)
        if per_user:
            user_rows = []
            for uid, data in sorted(per_user.items(), key=lambda kv: kv[1]["total"], reverse=True):
                u = user_repo.get(uid)
                user_rows.append({
                    "Cuenta": u.username if u else uid[:8],
                    "Vídeos": data["count"],
                    "Coste": f"${data['total']:.2f}",
                })
            st.dataframe(user_rows, hide_index=True, use_container_width=True)

    with table_cols[1]:
        st.markdown("**🛒 Coste por producto (todos los tiempos)**")
        per_product = _aggregate_by(generations, lambda g: g.product_id)
        if per_product:
            prod_rows = []
            for pid, data in sorted(per_product.items(), key=lambda kv: kv[1]["total"], reverse=True):
                p = product_repo.get(pid)
                prod_rows.append({
                    "Producto": p.name if p else pid[:8],
                    "Vídeos": data["count"],
                    "Coste": f"${data['total']:.2f}",
                })
            st.dataframe(prod_rows, hide_index=True, use_container_width=True)

    st.divider()

    # ------------------------------------------------------------------
    # 4. Filtros + ordenación
    # ------------------------------------------------------------------
    st.subheader(f"📚 Generaciones ({len(generations)})")

    f_cols = st.columns([1.2, 1.2, 1.2, 1.2, 1])
    with f_cols[0]:
        all_users = sorted({g.user_id for g in generations})
        user_options = ["(todas)"] + all_users
        sel_user = st.selectbox(
            "Usuario", user_options,
            format_func=lambda uid: "(todas)" if uid == "(todas)" else (
                user_repo.get(uid).username if user_repo.get(uid) else uid[:8]
            ),
            key="hist_filter_user",
        )
    with f_cols[1]:
        all_products = sorted({g.product_id for g in generations})
        product_options = ["(todos)"] + all_products
        sel_prod = st.selectbox(
            "Producto", product_options,
            format_func=lambda pid: "(todos)" if pid == "(todos)" else (
                product_repo.get(pid).name if product_repo.get(pid) else pid[:8]
            ),
            key="hist_filter_product",
        )
    with f_cols[2]:
        sel_tier = st.selectbox(
            "Tier", ["(todos)", "standard", "advanced", "pro",
                     "veo3_prompt_only", "nano_banana_prompt_only"],
            key="hist_filter_tier",
        )
    with f_cols[3]:
        sel_status = st.selectbox(
            "Status", ["(todos)", "completed", "manual_completed",
                       "manual_pending", "generating", "failed"],
            key="hist_filter_status",
        )
    with f_cols[4]:
        sort_by = st.selectbox(
            "Ordenar por", ["Fecha (reciente)", "Fecha (antigua)", "Coste ↓", "Coste ↑"],
            key="hist_sort",
        )

    # Aplicar filtros
    filtered = generations
    if sel_user != "(todas)":
        filtered = [g for g in filtered if g.user_id == sel_user]
    if sel_prod != "(todos)":
        filtered = [g for g in filtered if g.product_id == sel_prod]
    if sel_tier != "(todos)":
        filtered = [g for g in filtered if g.tier_used == sel_tier]
    if sel_status != "(todos)":
        filtered = [g for g in filtered if g.generation_status.value == sel_status]

    # Aplicar ordenación
    if sort_by == "Fecha (antigua)":
        filtered = sorted(filtered, key=lambda g: g.created_at)
    elif sort_by == "Coste ↓":
        filtered = sorted(filtered, key=lambda g: g.cost.total, reverse=True)
    elif sort_by == "Coste ↑":
        filtered = sorted(filtered, key=lambda g: g.cost.total)
    # Default "Fecha (reciente)" ya viene del LIST de Redis

    if not filtered:
        st.info("Ningún registro coincide con los filtros.")
        return
    st.caption(f"Mostrando {len(filtered)} de {len(generations)}")

    for g in filtered:
        u = user_repo.get(g.user_id)
        p = product_repo.get(g.product_id)
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
            with c1:
                username = u.username if u else f"(borrada {g.user_id[:6]})"
                product_name = p.name if p else f"(borrado {g.product_id[:6]})"
                tier_def = VIDEO_MODELS.get(g.tier_used, {})
                tier_badge = f"{tier_def.get('tier_color', '⚪')} {tier_def.get('name', g.tier_used)}"
                st.markdown(f"**{username}** · {product_name}")
                st.caption(f"{tier_badge} · {g.duration_seconds}s · {g.resolution} · {g.num_clips} clip(s)")
            with c2:
                created = _fmt_iso(g.created_at)
                status_emoji = _status_emoji(g.generation_status.value)
                st.caption(f"{status_emoji} {g.generation_status.value} · {created}")
                if g.video_type == "shoppable":
                    st.caption("🛒 shoppable")
                if g.cost.estimated_at_creation is not None and g.cost.actual_after_completion is not None:
                    delta_pct = (g.cost.actual_after_completion - g.cost.estimated_at_creation) / max(g.cost.estimated_at_creation, 0.0001) * 100
                    st.caption(f"📊 est ${g.cost.estimated_at_creation:.3f} → real ${g.cost.actual_after_completion:.3f} ({delta_pct:+.0f}%)")
            with c3:
                st.metric("Coste", f"${g.cost.total:.3f}", label_visibility="collapsed")
            with c4:
                if g.local_path and os.path.exists(g.local_path):
                    if st.button("▶️", key=f"play_{g.id}", help="Reproducir"):
                        st.session_state[f"_playing_{g.id}"] = True
                if g.veo3_prompt or g.nano_banana_prompt:
                    if st.button("📋", key=f"copy_{g.id}", help="Ver prompt"):
                        st.session_state[f"_show_prompt_{g.id}"] = True
                # FUNC 2: regeneración (solo si user + product siguen existiendo)
                if u is not None and p is not None:
                    if st.button("🔁", key=f"regen_id_{g.id}",
                                  help="Regenerar idéntico (mismos params)"):
                        _enqueue_regen_identical(g, u, p)
                    if st.button("✏️🔁", key=f"regen_ch_{g.id}",
                                  help="Regenerar con cambios (wizard)"):
                        st.session_state[f"_regen_wizard_{g.id}"] = True

            if st.session_state.get(f"_playing_{g.id}"):
                st.video(g.local_path)
            if st.session_state.get(f"_regen_wizard_{g.id}") and u is not None and p is not None:
                _render_regen_wizard(g, u, p)
            if st.session_state.get(f"_show_prompt_{g.id}"):
                prompt_text = g.veo3_prompt or g.nano_banana_prompt or "(sin prompt)"
                st.code(prompt_text, language="text")
            if g.error:
                st.error(g.error)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _fmt_iso(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso


def _status_emoji(status: str) -> str:
    return {
        "completed": "✅",
        "manual_completed": "✅",
        "manual_pending": "📝",
        "generating": "⏳",
        "pending": "🕐",
        "failed": "❌",
    }.get(status, "❓")


def _aggregate_by(generations, key_fn) -> dict:
    out: dict = defaultdict(lambda: {"total": 0.0, "count": 0})
    for g in generations:
        k = key_fn(g)
        out[k]["total"] += g.cost.total
        out[k]["count"] += 1
    return out


def _daily_cost(generations) -> dict[str, float]:
    """Devuelve {YYYY-MM-DD: coste} de los últimos 30 días."""
    out: dict[str, float] = defaultdict(float)
    for g in generations:
        try:
            dt = datetime.fromisoformat((g.created_at or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        out[dt.strftime("%Y-%m-%d")] += g.cost.total
    # ordenar por fecha asc para que el bar_chart se vea cronológico
    return {k: round(v, 4) for k, v in sorted(out.items())[-30:]}


def _monthly_budget_limit() -> float | None:
    val = os.getenv("TIKTOK_SHOP_MONTHLY_BUDGET_USD")
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# FUNC 2 — Regenerar idéntico / con cambios
# ---------------------------------------------------------------------------
def _enqueue_regen_identical(
    gen: VideoGeneration, user: TikTokUser, product: Product,
) -> None:
    """Encola una regeneración idéntica al original. Sin overrides."""
    params = build_regen_params(gen, user, product)
    tier_def = VIDEO_MODELS.get(gen.tier_used, {})
    tier_label = f"{tier_def.get('tier_color', '⚪')} {tier_def.get('name', gen.tier_used)}"
    title = build_regen_title(gen, user, product, tier_label=tier_label, is_with_changes=False)

    queue = get_queue()
    current_user = st.session_state.get("_current_user")
    job = queue.enqueue(
        JobMode.TIKTOK_SHOP, title=title, params=params,
        enqueued_by=current_user,
    )
    st.toast(f"🔁 Regenerado idéntico — encolado ({job.id[:8]})", icon="🛒")


def _render_regen_wizard(
    gen: VideoGeneration, user: TikTokUser, product: Product,
) -> None:
    """Wizard inline para regenerar con cambios. Pre-rellena con valores
    del job original y permite editar tier/duración/resolución/hook/voz."""
    with st.container(border=True):
        st.markdown(f"### ✏️🔁 Regenerar `{gen.id[:8]}` con cambios")
        st.caption(
            f"Original: {gen.tier_used} · {gen.duration_seconds}s · {gen.resolution}. "
            "Edita los campos y pulsa 'Encolar regeneración'. "
            "**No se reusan asignaciones de fotos** (catálogo puede haber cambiado): "
            "el director auto-asignará con las fotos disponibles ahora."
        )

        # --- Tier (solo Atlas tiers + veo3 — nano_banana no tiene sentido aquí)
        tier_options = [
            k for k in VIDEO_MODELS
            if k != "nano_banana_prompt_only"
        ]
        new_tier = st.selectbox(
            "Tier",
            tier_options,
            index=tier_options.index(gen.tier_used) if gen.tier_used in tier_options else 0,
            format_func=lambda k: f"{VIDEO_MODELS[k]['tier_color']} {VIDEO_MODELS[k]['name']} — ${VIDEO_MODELS[k]['cost_per_second']}/s",
            key=f"_regen_tier_{gen.id}",
        )

        cc1, cc2 = st.columns(2)
        with cc1:
            if new_tier in ATLAS_TIERS:
                new_dur = st.selectbox(
                    "Duración (s)", DURATIONS,
                    index=DURATIONS.index(gen.duration_seconds)
                    if gen.duration_seconds in DURATIONS else 3,
                    key=f"_regen_dur_{gen.id}",
                )
            elif new_tier == "veo3_prompt_only":
                st.caption("Veo 3: 8s fijos.")
                new_dur = 8
            else:
                new_dur = gen.duration_seconds
        with cc2:
            if new_tier in ATLAS_TIERS:
                res_choices = [
                    r for r, info in RESOLUTIONS.items()
                    if new_tier in info.get("tiers_supported", ())
                ]
                default_res = gen.resolution if gen.resolution in res_choices else res_choices[0]
                new_res = st.selectbox(
                    "Resolución", res_choices,
                    index=res_choices.index(default_res),
                    key=f"_regen_res_{gen.id}",
                )
            else:
                new_res = gen.resolution

        # Hook (categoría + texto editables)
        hook_options = ["custom"] + [h.category for h in product.hooks_library]
        current_cat = gen.hook.category if gen.hook else "custom"
        try:
            hook_idx = hook_options.index(current_cat)
        except ValueError:
            hook_idx = 0
        new_hook_cat = st.selectbox(
            "Hook category", hook_options,
            index=hook_idx,
            format_func=lambda x: "✏️ Custom" if x == "custom" else x,
            key=f"_regen_hook_cat_{gen.id}",
        )
        new_hook_text = st.text_area(
            "Hook (editable)",
            value=gen.hook.text if gen.hook else "",
            key=f"_regen_hook_text_{gen.id}",
        )

        # Voz
        voice_repo = VoiceRepo()
        voices = voice_repo.list_all(include_presets=True)
        voice_options = [v.minimax_voice_id for v in voices]
        current_voice = gen.voice_used.voice_id if gen.voice_used else None
        try:
            voice_idx = voice_options.index(current_voice) if current_voice else 0
        except ValueError:
            voice_idx = 0
        col_v1, col_v2 = st.columns([3, 1])
        with col_v1:
            new_voice = st.selectbox(
                "🗣️ Voz", voice_options,
                index=voice_idx,
                format_func=lambda vid: next(
                    (v.name for v in voices if v.minimax_voice_id == vid), vid,
                ),
                key=f"_regen_voice_{gen.id}",
            ) if voice_options else None
        with col_v2:
            new_with_voice = st.checkbox(
                "Activar voz", value=True, key=f"_regen_with_voice_{gen.id}",
            )

        # Audiencia
        audience_options = product.target_audience or [user.niche or "Generalista"]
        new_audience = st.selectbox(
            "Audiencia", audience_options,
            key=f"_regen_aud_{gen.id}",
        )

        # Coste estimado del job nuevo
        from src.tiktok_shop.services import estimate_cost
        if new_tier in ATLAS_TIERS:
            voice_chars_estimate = (new_dur or 15) * 18
            cost = estimate_cost(
                tier=new_tier, duration=new_dur or 15, resolution=new_res,
                voice_chars=voice_chars_estimate, with_voice=new_with_voice,
            )
            st.info(f"💰 Coste estimado: **${cost['total']:.3f}**")
        else:
            st.info("💰 Coste: $0 (prompt-only)")

        # Botones finales
        bcol1, bcol2 = st.columns(2)
        with bcol1:
            if st.button(
                "🚀 Encolar regeneración",
                key=f"_regen_submit_{gen.id}",
                type="primary",
                use_container_width=True,
            ):
                overrides: dict = {
                    "tier": new_tier,
                    "duration": new_dur,
                    "resolution": new_res,
                    "hook_category": new_hook_cat if new_hook_cat != "custom" else "custom",
                    "hook_text": new_hook_text,
                    "audience": new_audience,
                    "with_voice": new_with_voice,
                }
                if new_voice:
                    overrides["voice_id"] = new_voice

                params = build_regen_params(gen, user, product, overrides=overrides)
                tier_def = VIDEO_MODELS.get(new_tier, {})
                tier_label = f"{tier_def.get('tier_color', '⚪')} {tier_def.get('name', new_tier)}"
                title = build_regen_title(
                    gen, user, product, tier_label=tier_label, is_with_changes=True,
                )
                queue = get_queue()
                current_user_name = st.session_state.get("_current_user")
                job = queue.enqueue(
                    JobMode.TIKTOK_SHOP, title=title, params=params,
                    enqueued_by=current_user_name,
                )
                st.session_state.pop(f"_regen_wizard_{gen.id}", None)
                st.toast(
                    f"🔁 Regeneración encolada con cambios ({job.id[:8]})",
                    icon="🛒",
                )
                st.rerun()
        with bcol2:
            if st.button(
                "❌ Cancelar",
                key=f"_regen_cancel_{gen.id}",
                use_container_width=True,
            ):
                st.session_state.pop(f"_regen_wizard_{gen.id}", None)
                st.rerun()
