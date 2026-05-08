"""Tab 'Generar Vídeo' — wizard que combina usuario × producto y dispara la cola.

5 tiers oficiales:
  🟢 standard / 🟡 advanced / 🔴 pro (Atlas Cloud automático)
  🟣 veo3_prompt_only / 🍌 nano_banana_prompt_only (prompt-only, manual)
"""

from __future__ import annotations

import os

import streamlit as st

from src.queue import JobMode, get_queue
from src.tiktok_shop.config import (
    ATLAS_TIERS, DEFAULT_VIDEO_STRATEGY, DURATIONS, RESOLUTIONS,
    STRATEGY_CONFIG, VIDEO_MODELS, VIDEO_STRATEGIES, atlas_is_configured,
)
from src.tiktok_shop.repos import ProductRepo, UserRepo, VoiceRepo
from src.tiktok_shop.services import estimate_cost
from src.tiktok_shop.services.pilot_tracker import can_publish_shoppable


def render() -> None:
    user_repo = UserRepo()
    product_repo = ProductRepo()
    voice_repo = VoiceRepo()

    with st.spinner("🎬 Cargando usuarios y productos disponibles…"):
        users = user_repo.list_all()
        products = product_repo.list_all()

    if not users:
        st.warning("Necesitas al menos una cuenta TikTok. Ve al tab '👥 Usuarios TikTok'.")
        return
    if not products:
        st.warning("Necesitas al menos un producto. Ve al tab '📦 Productos'.")
        return

    # Paso 1 — selección user × product (persistida en session_state para que
    # la sidebar de TikTok Shop pueda mostrar quién está activo)
    col_u, col_p = st.columns(2)
    with col_u:
        user_id = st.selectbox(
            "👤 Cuenta TikTok",
            options=[u.id for u in users],
            format_func=lambda uid: next(u.username for u in users if u.id == uid),
            key="_shop_gen_user_id",
        )
        u = next(usr for usr in users if usr.id == user_id)
    with col_p:
        assigned = [p for p in products if p.id in u.assigned_products]
        if not assigned:
            st.error(
                f"La cuenta {u.username} no tiene productos asignados. "
                "Asigna en el tab '👥 Usuarios TikTok'."
            )
            # Limpia el producto previo (pudo quedar de otra cuenta)
            st.session_state.pop("_shop_gen_product_id", None)
            return
        product_id = st.selectbox(
            "📦 Producto",
            options=[p.id for p in assigned],
            format_func=lambda pid: next(p.name for p in assigned if p.id == pid),
            key="_shop_gen_product_id",
        )
        p = next(pr for pr in assigned if pr.id == product_id)

    st.divider()

    # Paso 1 (cont) — fotos disponibles (source vs generated)
    # Filtra eliminadas (soft-delete) y archivos sin disco. Las miniaturas
    # se muestran en grid horizontal denso vía `st.image([...])`.
    active_src = [
        ph for ph in p.photos.source
        if not ph.deleted and ph.local_path and os.path.exists(ph.local_path)
    ]
    active_gen = [
        ph for ph in p.photos.generated
        if not ph.deleted and ph.local_path and os.path.exists(ph.local_path)
    ]
    deleted_src = sum(1 for ph in p.photos.source if ph.deleted)
    deleted_gen = sum(1 for ph in p.photos.generated if ph.deleted)

    cols = st.columns(2)
    with cols[0]:
        label = f"📸 photos_source · **{len(active_src)}**"
        if deleted_src:
            label += f" *({deleted_src} ⌫)*"
        st.caption(label)
        if active_src:
            _render_photo_grid([ph.local_path for ph in active_src[:8]])
        else:
            st.caption("(sin fotos source válidas)")
    with cols[1]:
        if active_gen:
            label = f"✨ photos_generated · **{len(active_gen)}** (preferido)"
            if deleted_gen:
                label += f" *({deleted_gen} ⌫)*"
            st.caption(label)
            _render_photo_grid([ph.local_path for ph in active_gen[:8]])
        else:
            st.caption("✨ photos_generated · vacío *(usará source)*")

    if p.needs_nano_banana_regeneration and not active_gen:
        st.warning(
            "🍌 Las fotos source son limitadas. Considera generar fotos premium con "
            "Nano Banana 2 desde el tab '📦 Productos' antes de renderizar."
        )

    # Paso 2 — Tier selector con tooltips compactos (1 línea)
    st.markdown("**Tier de generación**")
    _TIER_TOOLTIPS = {
        "standard": "Volumen, validación, A/B de hooks.",
        "advanced": "Productos prometedores. 2.6× el coste de Standard.",
        "pro": "Hero ads. Multi-shot nativo, hasta 9 fotos. Solo productos validados.",
        "veo3_prompt_only": "Premium manual: prompt para Gemini chat (plan Pro). Coste $0.",
        "nano_banana_prompt_only": "Prompt para crear FOTOS premium (no vídeos).",
    }
    tier_options = [k for k in VIDEO_MODELS]
    tier = st.radio(
        "Tier",
        tier_options,
        index=tier_options.index(p.video_config.default_tier)
        if p.video_config.default_tier in tier_options
        else 0,
        format_func=lambda k: f"{VIDEO_MODELS[k]['tier_color']} {VIDEO_MODELS[k]['name']} — ${VIDEO_MODELS[k]['cost_per_second']}/s",
        horizontal=False,
        label_visibility="collapsed",
    )
    # Tooltip del tier seleccionado en una sola línea (en lugar de mostrar
    # las 5 descripciones a la vez con `captions=`). Más compacto.
    st.caption(f"ℹ️ {_TIER_TOOLTIPS.get(tier, '')}")

    is_atlas_tier = tier in ATLAS_TIERS

    if is_atlas_tier and not atlas_is_configured():
        st.error(
            "❌ Atlas Cloud no está configurado. Define `ATLASCLOUD_API_KEY` en "
            "`.env` para usar tiers Standard/Advanced/Pro. "
            "Mientras tanto puedes usar 🟣 Veo 3 o 🍌 Nano Banana 2 (prompt-only)."
        )

    # Paso 3 — Estrategia de vídeo (FUNC 5) — solo Standard/Advanced.
    # Pro = 1 clip multi-shot por diseño; Veo3/Nano Banana no aplica.
    video_strategy = DEFAULT_VIDEO_STRATEGY
    if tier in ("standard", "advanced"):
        st.markdown("**Estrategia de vídeo**")
        strat_options = list(VIDEO_STRATEGIES)
        video_strategy = st.radio(
            "Estrategia",
            strat_options,
            index=strat_options.index(DEFAULT_VIDEO_STRATEGY),
            format_func=lambda s: f"{STRATEGY_CONFIG[s]['label']} — {STRATEGY_CONFIG[s]['tagline']}",
            horizontal=False,
            label_visibility="collapsed",
            key="_shop_gen_strategy",
        )

    # Paso 4 — Configuración técnica (duración + resolución + preview en 1 fila)
    duration = 8 if tier == "veo3_prompt_only" else 0 if tier == "nano_banana_prompt_only" else None
    resolution = "720p"
    if tier in ATLAS_TIERS:
        col1, col2, col3 = st.columns([1, 1, 1.2])
        with col1:
            duration = st.selectbox(
                "Duración total (s)",
                DURATIONS,
                index=DURATIONS.index(p.video_config.default_duration)
                if p.video_config.default_duration in DURATIONS else 3,
            )
        with col2:
            # Filtrar resoluciones permitidas para este tier (per doc Atlas):
            res_choices = [
                r for r, info in RESOLUTIONS.items()
                if tier in info.get("tiers_supported", ())
            ]
            default_res = p.video_config.default_resolution if p.video_config.default_resolution in res_choices else res_choices[0]
            resolution = st.selectbox(
                "Resolución",
                res_choices,
                index=res_choices.index(default_res),
            )
        with col3:
            # Preview reactivo de clips — recalcula al cambiar strategy o duration.
            from src.tiktok_shop.utils.duration_splitter import describe_split, split_duration
            clips_plan = split_duration(int(duration), tier, video_strategy)
            st.caption("Plan")
            st.markdown(f"📐 {describe_split(clips_plan)}")
    elif tier == "veo3_prompt_only":
        st.caption("Veo 3: duración fija 8s, single continuous shot.")

    # Paso 3.5 — Selección granular de fotos por clip (FUNC 3)
    # Solo para tiers Atlas. La asignación se guarda como params del job.
    # `effective_photos` = lista que el runner usará (best_available filtra
    # eliminadas y prefiere generated > source). El usuario verá las MISMAS
    # fotos que el pipeline final, no las marcadas como deleted.
    clip_photo_overrides: list[int] | None = None
    pro_ref_photo_overrides: list[int] | None = None
    if tier in ATLAS_TIERS:
        effective_photos = active_gen if active_gen else active_src
        if effective_photos:
            clip_photo_overrides, pro_ref_photo_overrides = _render_photo_assignment_ui(
                product_id=p.id, tier=tier, duration=int(duration or 0),
                photos=effective_photos, strategy=video_strategy,
            )

    # Paso 4 — Hook + audiencia (no aplica a nano_banana_prompt_only)
    if tier != "nano_banana_prompt_only":
        st.markdown("**Hook + audiencia**")
        col4, col5 = st.columns(2)
        with col4:
            hook_options = ["custom"] + [h.category for h in p.hooks_library]
            hook_choice = st.selectbox(
                "Hook category",
                hook_options,
                format_func=lambda x: "✏️ Custom" if x == "custom" else x,
            )
            if hook_choice == "custom":
                hook_text = st.text_area("Hook custom", placeholder="POV: descubres...")
            else:
                template = next((h.template for h in p.hooks_library if h.category == hook_choice), "")
                hook_text = st.text_area("Hook (editable)", value=template)
        with col5:
            audience_options = p.target_audience or ["Generalista"]
            audience = st.selectbox("Audiencia objetivo", audience_options)

        # Paso 5 — Voz (solo para tiers que generan vídeo)
        if is_atlas_tier:
            voices = voice_repo.list_all(include_presets=True)
            voice_options = {v.minimax_voice_id: v.name for v in voices}
            col_v1, col_v2 = st.columns([3, 1])
            with col_v1:
                voice_id = st.selectbox(
                    "🗣️ Voz",
                    options=list(voice_options.keys()),
                    format_func=lambda vid: voice_options[vid],
                    index=0,
                )
            with col_v2:
                with_voice = st.checkbox("Activar voz", value=True)
        else:
            voice_id = "Spanish_EnergeticBoy"
            with_voice = False
    else:
        # Nano Banana: solo configuramos número de ángulos
        hook_choice, hook_text, audience = "n/a", "", ""
        voice_id = ""
        with_voice = False
        st.markdown("**Configuración Nano Banana 2**")
        n_angles = st.slider("Número de fotos a pedir", 4, 8, 5)

    # Paso 6 — TikTok Shop metadata
    st.markdown("**TikTok Shop**")
    if is_atlas_tier or tier == "veo3_prompt_only":
        col6, col7 = st.columns(2)
        with col6:
            is_shoppable = st.checkbox(
                "🛒 Vídeo shoppable (cuenta hacia Pilot Program)",
                value=False,
                disabled=(tier == "veo3_prompt_only"),  # los manuales no se pre-marcan
            )
            if is_shoppable and not can_publish_shoppable(u):
                st.error(
                    f"⚠️ {u.username} ha agotado los 5 shoppable de la semana. "
                    "Desmarca o espera al reset semanal."
                )
        with col7:
            ai_disclosure = st.checkbox(
                "🤖 AI disclosure", value=True, disabled=True,
                help="Obligatorio en TikTok. Marcado siempre.",
            )
    else:
        is_shoppable = False
        ai_disclosure = True

    # Paso 7 — Coste estimado (dinámico — se recalcula en cada rerun de Streamlit)
    if tier in ATLAS_TIERS:
        voice_chars_estimate = (duration or 15) * 18
        cost = estimate_cost(
            tier=tier,
            duration=duration or 15,
            resolution=resolution,
            voice_chars=voice_chars_estimate,
            with_voice=with_voice,
        )
        breakdown = (
            f"vídeo ${cost['video_generation']} ({tier} {duration}s {resolution})"
            f" + voz ${cost['voice_tts']} (~{voice_chars_estimate} chars)"
            if with_voice else
            f"vídeo ${cost['video_generation']} ({tier} {duration}s {resolution}) — sin voz"
        )
        st.info(f"💰 Coste estimado: **${cost['total']:.3f}** · {breakdown}")
    else:
        st.info("💰 Coste: $0 (prompt-only — generación manual en Gemini chat)")

    # Botón encolar
    st.divider()
    blocked_atlas = is_atlas_tier and not atlas_is_configured()
    if st.button(
        "🚀 Encolar generación",
        type="primary",
        use_container_width=True,
        disabled=blocked_atlas,
    ):
        if is_shoppable and not can_publish_shoppable(u):
            st.error("Bloqueado: límite semanal alcanzado.")
            return

        queue = get_queue()  # usa el mismo dir-default que main.py (normalizado)
        params = {
            "user_id": u.id,
            "product_id": p.id,
            "tier": tier,
            "duration": duration or (8 if tier == "veo3_prompt_only" else 0),
            "resolution": resolution,
            "hook_category": hook_choice if hook_choice != "custom" else "custom",
            "hook_text": hook_text,
            "audience": audience,
            "voice_id": voice_id,
            "with_voice": with_voice,
            "language": u.default_language,
            "is_shoppable": is_shoppable,
            "ai_disclosure": ai_disclosure,
            "temp_folder": "./temp_work",
            # FUNC 3: asignación manual de fotos (None si auto-asignación IA)
            "clip_photo_overrides": clip_photo_overrides,
            "pro_ref_photo_overrides": pro_ref_photo_overrides,
            # FUNC 5: estrategia de vídeo (cinematic / dynamic)
            "strategy": video_strategy,
        }
        if tier == "nano_banana_prompt_only":
            params["n_angles"] = int(n_angles)

        title = f"{u.username} · {p.name} · {VIDEO_MODELS[tier]['tier_color']} {VIDEO_MODELS[tier]['name']}"
        current_user = st.session_state.get("_current_user")
        job = queue.enqueue(
            JobMode.TIKTOK_SHOP, title=title, params=params,
            enqueued_by=current_user,
        )
        st.toast(f"➕ Encolado ({job.id[:8]}) — mira el botón 🎬 Cola arriba a la derecha.", icon="🛒")
        st.success(f"✅ Encolado ({job.id[:8]}). Mira la cola arriba a la derecha.")


# ---------------------------------------------------------------------------
# Helpers de UI
# ---------------------------------------------------------------------------
def _render_photo_assignment_ui(
    *,
    product_id: str,
    tier: str,
    duration: int,
    photos: list,
    strategy: str = DEFAULT_VIDEO_STRATEGY,
) -> tuple[list[int] | None, list[int] | None]:
    """Selector granular de fotos por clip (FUNC 3).

    Comportamiento por tier:
      - `standard` / `advanced`: si duración cabe en 1 clip → no UI (la única
        opción es la primera foto, no hay nada que asignar). Si duración da
        N>1 clips → toggle "Asignar manualmente"; al activar muestra N
        selectboxes (uno por clip) con todas las fotos.
      - `pro`: multi-select de fotos referencia (max 9), siempre visible.

    Returns:
        (clip_photo_overrides, pro_ref_photo_overrides) — uno o ambos `None`
        si el usuario no overridea (para que el director auto-asigne).
    """
    from src.tiktok_shop.utils.duration_splitter import split_duration

    if not photos:
        return None, None

    # Etiquetas para los selectboxes — filename + tipo si está
    def _label_for(idx: int) -> str:
        ph = photos[idx]
        type_str = f" · {ph.type}" if ph.type else ""
        return f"#{idx} · {ph.filename}{type_str}"

    if tier == "pro":
        # Pro: multi-select hasta 9 — default todas las disponibles (max 9)
        st.markdown("**📌 Fotos de referencia (multi-shot Pro)**")
        st.caption(
            "Selecciona hasta 9 fotos. El modelo decide internamente cómo "
            "alternarlas entre los shots del clip multi-shot."
        )
        all_indices = list(range(len(photos)))
        default_selected = all_indices[:9]
        selected = st.multiselect(
            "Fotos referencia",
            options=all_indices,
            default=default_selected,
            format_func=_label_for,
            max_selections=9,
            key=f"_shop_gen_pro_refs_{product_id}",
            label_visibility="collapsed",
        )
        # Si el usuario seleccionó EXACTAMENTE el default, devolvemos None
        # para que el director use su auto (que da el mismo resultado).
        if selected == default_selected:
            return None, None
        return None, selected if selected else None

    # Standard / Advanced: cuántos clips habrá (depende de la strategy)
    clips_plan = split_duration(duration, tier, strategy)
    n_clips = len(clips_plan)
    if n_clips <= 1:
        return None, None  # 1 solo clip → no hay asignación que hacer

    use_manual = st.toggle(
        f"✏️ Asignar fotos manualmente a los {n_clips} clips",
        value=False,
        key=f"_shop_gen_manual_assign_{product_id}",
        help="Por defecto el director IA decide qué foto va en cada clip. "
             "Activa para sobrescribir manualmente.",
    )
    if not use_manual:
        return None, None

    st.caption(
        f"Asigna una foto a cada uno de los {n_clips} clips. "
        f"Recuerda que `last_image` del clip K = primer frame del clip K+1 "
        f"(la app se encarga del anchoring)."
    )
    overrides: list[int] = []
    cols = st.columns(min(n_clips, 4))  # max 4 columnas; si más, va en grid
    for i, dur_s in enumerate(clips_plan):
        col = cols[i % len(cols)]
        with col:
            # Default: rotar fotos (clip 0 → foto 0, clip 1 → foto 1, etc.)
            default_idx = i % len(photos)
            sel = st.selectbox(
                f"Clip {i+1} ({dur_s}s)",
                options=list(range(len(photos))),
                index=default_idx,
                format_func=_label_for,
                key=f"_shop_gen_clip{i}_{product_id}",
            )
            overrides.append(sel)

    return overrides, None


def _render_photo_grid(paths: list[str], thumb_px: int = 70) -> None:
    """Renderiza miniaturas en grid con tamaño UNIFORME y separación visible.

    `st.image([list], width=N)` respeta aspect ratio y deja las imágenes
    pegadas — fotos cuadradas se ven más grandes que rectangulares y queda
    desigual. Esta función pone cada foto en su propia `st.columns` con
    tamaño fijo `thumb_px×thumb_px` y un gap CSS para airearlas.

    Como Streamlit no permite `object-fit: cover` directo en `st.image`,
    usamos HTML+base64 inline que sí lo soporta — mismo patrón que el
    `image_url_provider.to_base64_data_uri` ya disponible.
    """
    from src.tiktok_shop.utils.image_url_provider import to_base64_data_uri

    valid = [p for p in paths if p and os.path.exists(p)]
    if not valid:
        return

    # Renderizamos un bloque HTML con flexbox: cada thumb es un cuadrado
    # con `object-fit: cover` (recorte centrado), border-radius suave y gap.
    html_parts = [
        '<div style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:0.5rem;">'
    ]
    for p in valid:
        try:
            data_uri = to_base64_data_uri(p)
        except Exception:
            continue
        html_parts.append(
            f'<img src="{data_uri}" '
            f'style="width:{thumb_px}px; height:{thumb_px}px; '
            f'object-fit:cover; border-radius:6px; '
            f'border:1px solid rgba(255,255,255,0.08);" />'
        )
    html_parts.append("</div>")
    st.markdown("".join(html_parts), unsafe_allow_html=True)
