"""Tab 'Usuarios TikTok' — listado + creación + asignación de productos."""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from src.tiktok_shop.config import (
    COUNTRY_OPTIONS, LANGUAGE_OPTIONS, NICHE_OPTIONS, VIDEO_MODELS,
    user_drive_folder,
)
from src.tiktok_shop.models import TikTokUser
from src.tiktok_shop.repos import ProductRepo, UserRepo
from src.tiktok_shop.services import days_in_pilot, weeks_progress
from src.tiktok_shop.utils.validators import (
    require_non_empty, validate_tiktok_username,
)


def render() -> None:
    user_repo = UserRepo()
    product_repo = ProductRepo()

    if st.button("➕ Crear usuario TikTok", use_container_width=True, type="primary"):
        st.session_state["_shop_show_user_wizard"] = True

    if st.session_state.get("_shop_show_user_wizard"):
        _wizard_create_user(user_repo)
        st.divider()

    st.subheader("👥 Cuentas activas")
    with st.spinner("👥 Cargando cuentas desde Redis…"):
        users = user_repo.list_all()
    if not users:
        st.info("Aún no hay cuentas TikTok. Pulsa '➕ Crear usuario TikTok'.")
        return

    for u in users:
        _render_user_card(u, user_repo, product_repo)


def _render_user_card(u: TikTokUser, user_repo: UserRepo, product_repo: ProductRepo) -> None:
    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            badge = "🟢 Graduada" if u.status == "graduated" else "🟡 Pilot"
            st.markdown(f"**{u.username}** · {badge}")
            st.caption(f"{u.display_name} · {u.niche} · {u.language}/{u.country}")
        with c2:
            if u.status == "pilot":
                w = weeks_progress(u)
                d = days_in_pilot(u)
                pp = u.pilot_program
                st.caption(
                    f"📅 Día {d}/30 · 🎬 {pp.shoppable_videos_published}/6 vids · "
                    f"💰 {pp.orders_generated}/10 órdenes · 🩺 CHR {u.creator_health_rating}"
                )
                st.caption(
                    f"📺 Esta semana: {w['shoppable_used']}/5 shoppable usados "
                    f"(reset {w['reset_at'] or 'sin fecha'})"
                )
            else:
                st.caption(f"🎉 Graduada · {u.followers_count} followers")
        with c3:
            confirm_key = f"_confirm_del_user_{u.id}"
            if st.session_state.get(confirm_key):
                if st.button("⚠️ Confirmar borrado", key=f"confirm_btn_{u.id}", type="primary"):
                    user_repo.delete(u.id)
                    st.session_state.pop(confirm_key, None)
                    st.success(f"Cuenta {u.username} borrada.")
                    st.rerun()
                if st.button("❌ Cancelar", key=f"cancel_del_{u.id}"):
                    st.session_state.pop(confirm_key, None)
                    st.rerun()
            else:
                if st.button("🗑️", key=f"del_user_{u.id}", help="Borrar cuenta (pide confirmación)"):
                    st.session_state[confirm_key] = True
                    st.rerun()

        with st.expander(f"🔗 Productos asignados ({len(u.assigned_products)})"):
            _render_assignments(u, user_repo, product_repo)


def _render_assignments(u: TikTokUser, user_repo: UserRepo, product_repo: ProductRepo) -> None:
    products = product_repo.list_all()
    if not products:
        st.info("Crea productos primero en el tab '📦 Productos'.")
        return

    options = {p.id: f"{p.name} (`{p.slug}`)" for p in products}
    current = [pid for pid in u.assigned_products if pid in options]
    selected = st.multiselect(
        "Asigna productos a esta cuenta",
        options=list(options.keys()),
        format_func=lambda pid: options[pid],
        default=current,
        key=f"assign_{u.id}",
    )
    if set(selected) != set(current):
        if st.button("💾 Guardar asignaciones", key=f"save_assign_{u.id}"):
            for pid in selected:
                if pid not in u.assigned_products:
                    user_repo.assign_product(u.id, pid)
            for pid in list(u.assigned_products):
                if pid not in selected:
                    user_repo.unassign_product(u.id, pid)
            st.success("Asignaciones actualizadas.")
            st.rerun()


def _wizard_create_user(repo: UserRepo) -> None:
    st.subheader("🪄 Nueva cuenta TikTok")
    with st.form("shop_user_wizard", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            username = st.text_input("Username (con @) *", placeholder="@cuenta_skincare_es")
            display_name = st.text_input("Display name", placeholder="Skincare Tips España")
            niche = st.selectbox("Nicho", NICHE_OPTIONS, index=0)
        with col2:
            language = st.selectbox("Idioma", LANGUAGE_OPTIONS, index=0)
            country = st.selectbox("País", COUNTRY_OPTIONS, index=0)
            chr_value = st.number_input("CHR inicial", min_value=0, max_value=300, value=200)

        tier_options = [k for k in VIDEO_MODELS if VIDEO_MODELS[k].get("type") != "prompt_only" or k == "veo3_prompt_only"]
        default_tier = st.selectbox(
            "Tier de generación por defecto",
            tier_options,
            index=tier_options.index("standard") if "standard" in tier_options else 0,
            format_func=lambda k: f"{VIDEO_MODELS[k]['tier_color']} {VIDEO_MODELS[k]['name']}",
            help="Cuando generes vídeos para esta cuenta, este será el tier preseleccionado. Editable en cada generación.",
        )

        col_a, col_b = st.columns([1, 1])
        with col_a:
            submitted = st.form_submit_button("💾 Crear cuenta", type="primary", use_container_width=True)
        with col_b:
            cancel = st.form_submit_button("❌ Cancelar", use_container_width=True)

    if cancel:
        st.session_state["_shop_show_user_wizard"] = False
        st.rerun()

    if submitted:
        # === Validación inputs ===
        ok, err = require_non_empty(username, "Username")
        if not ok:
            st.error(err)
            return
        # Normalizar @ antes de validar formato
        if not username.startswith("@"):
            username = "@" + username
        ok, err = validate_tiktok_username(username)
        if not ok:
            st.error(err)
            return
        ok, err = require_non_empty(display_name, "Display name")
        if not ok:
            # display_name no es estrictamente obligatorio (cae al handle), permito vacío
            display_name = username[1:]

        if repo.get_by_username(username) is not None:
            st.error(f"Ya existe la cuenta {username}.")
            return

        user = TikTokUser(
            username=username,
            display_name=display_name or username[1:],
            niche=niche,
            language=language,
            country=country,
            default_language=language,
            default_video_tier=default_tier,
            creator_health_rating=int(chr_value),
        )

        # Crear carpeta Drive sincronizada
        folder = user_drive_folder(username)
        Path(folder, "products").mkdir(parents=True, exist_ok=True)
        # Escribe _profile.json para inspección manual desde Drive
        profile_path = os.path.join(folder, "_profile.json")
        try:
            import json
            with open(profile_path, "w", encoding="utf-8") as f:
                json.dump(user.model_dump(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            st.warning(f"⚠️ No se pudo escribir _profile.json: {e}")

        user.drive_folder = folder
        repo.save(user)
        st.session_state["_shop_show_user_wizard"] = False
        st.success(f"✅ Cuenta {username} creada en `{folder}`.")
        st.rerun()
