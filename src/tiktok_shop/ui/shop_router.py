"""Entry-point del nicho TikTok Shop dentro de la app Streamlit existente.

Se invoca desde main.py cuando `CFG["app_mode"] == "TIKTOK_SHOP"`. Renderiza
una serie de tabs (Productos / Usuarios / Generar / Voces / Histórico) sin
tocar nada del flujo Creator Reward.

UX de carga (mejora mayo 2026):
- Detecta cambio de modo (Creator Reward → TikTok Shop) y muestra toast.
- Spinner global mientras se cargan health checks + tabs.
- Cada tab tiene su propio spinner contextual con texto específico
  ("📦 Cargando productos…", "👥 Cargando cuentas…", etc.) para que el
  usuario sepa qué está cargando, no solo que "algo está cargando".
"""

from __future__ import annotations

import os

import streamlit as st

from src.tiktok_shop.config import (
    atlas_is_configured, ensure_shop_root, gemini_api_key, resolve_shop_root,
)
from src.tiktok_shop.repos import get_shop_redis


def render(_config: dict) -> None:
    # Toast informativo al cambiar de modo (Creator Reward → TikTok Shop)
    _last_mode = st.session_state.get("_shop_router_last_mode")
    if _last_mode != "TIKTOK_SHOP":
        st.toast("⏳ Cargando módulo TikTok Shop…", icon="🛒")
        st.session_state["_shop_router_last_mode"] = "TIKTOK_SHOP"

    st.header("🛒 TikTok Shop — Programa 2")

    with st.spinner("⏳ Comprobando estado del módulo (Redis, Gemini, Atlas)…"):
        _render_health_banner()

    tabs = st.tabs([
        "🔍 Radar",
        "📦 Productos",
        "👥 Usuarios TikTok",
        "🎬 Generar Vídeo",
        "🗣️ Voces",
        "📚 Histórico",
    ])

    # Cada tab tiene su propio spinner contextual dentro de su `render()`,
    # alrededor de la query Redis pesada. Aquí solo enrutamos.
    with tabs[0]:
        from .tab_radar import render as render_radar
        render_radar()
    with tabs[1]:
        from .tab_products import render as render_products
        render_products()
    with tabs[2]:
        from .tab_users import render as render_users
        render_users()
    with tabs[3]:
        from .tab_generator import render as render_generator
        render_generator()
    with tabs[4]:
        from .tab_voices import render as render_voices
        render_voices()
    with tabs[5]:
        from .tab_history import render as render_history
        render_history()


def _render_health_banner() -> None:
    """Banner de salud: muestra qué APIs están disponibles vs. degradadas."""
    redis_ok = get_shop_redis().is_available()
    gemini_ok = bool(gemini_api_key())
    atlas_ok = atlas_is_configured()
    shop_root = resolve_shop_root()

    cols = st.columns(4)
    with cols[0]:
        if redis_ok:
            st.success("✅ Redis", icon="📦")
        else:
            st.error("❌ Redis", icon="📦")
    with cols[1]:
        if gemini_ok:
            st.success("✅ Gemini", icon="🤖")
        else:
            st.warning("⚠️ Gemini (mock)", icon="🤖")
    with cols[2]:
        if atlas_ok:
            st.success("✅ Atlas/Seedance", icon="🎥")
        else:
            st.warning("⚠️ Sin Atlas (Veo3 prompt-only y modo fotos sí funcionan)", icon="🎥")
    with cols[3]:
        if shop_root and os.path.isdir(shop_root):
            st.caption(f"📁 `{shop_root}`")
        elif shop_root:
            st.warning(f"⚠️ TIKTOK_SHOP_ROOT_PATH definido pero no existe en disco:\n`{shop_root}`")
        else:
            st.error("❌ TIKTOK_SHOP_ROOT_PATH no resoluble")

    if not redis_ok:
        st.error(
            "Redis no está disponible. Define `UPSTASH_REDIS_REST_URL` y "
            "`UPSTASH_REDIS_REST_TOKEN` en `.env` para persistir productos / usuarios."
        )
        st.stop()

    # Asegura que las carpetas raíz existan al entrar a la sección
    try:
        ensure_shop_root()
    except Exception as e:
        st.error(f"No se pudo crear `TIKTOK_SHOP/`: {e}")
