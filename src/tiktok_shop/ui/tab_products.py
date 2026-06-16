"""Tab 'Productos' — listado + creación con wizard single-form (8 secciones).

Decisiones:
- Single-form con `st.expander` por sección (consistente con el resto de la app).
- Paso 7 (Nano Banana 2): se ejecuta DESPUÉS de crear el producto base; necesita
  fotos source guardadas para que Gemini las analice. Por eso el paso 7 vive
  fuera del form principal — primero se guarda el producto, luego se ofrece la
  generación de prompt + upload zone para fotos generadas.
"""

from __future__ import annotations

import io
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from src.tiktok_shop.config import (
    DEFAULT_TIER, NICHE_OPTIONS, VIDEO_MODELS, VIDEO_STYLES,
    product_drive_folder, product_photos_generated_folder,
    product_photos_source_folder, product_prompt_templates_folder,
)
from src.tiktok_shop.models import (
    Hook, PerformanceHistory, Product, ProductPhoto, ProductPhotos,
    TikTokShopMeta, VideoConfig,
)
from src.tiktok_shop.models.product import slugify
from src.tiktok_shop.pipeline import analyze_product, generate_nano_banana_prompt
from src.tiktok_shop.repos import ProductRepo
from src.tiktok_shop.services import product_service as ps
from src.tiktok_shop.utils.photo_quality import (
    any_photo_low_resolution, needs_nano_banana_regeneration,
)
from src.tiktok_shop.utils.validators import (
    require_non_empty, validate_photo_upload, validate_tiktok_shop_url,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def render() -> None:
    repo = ProductRepo()

    col_top1, col_top2 = st.columns([3, 1])
    with col_top2:
        if st.button("➕ Crear producto", use_container_width=True, type="primary"):
            st.session_state["_shop_show_wizard"] = True

    if st.session_state.get("_shop_show_wizard"):
        _wizard_create(repo)
        st.divider()

    st.subheader("📦 Catálogo")
    with st.spinner("📦 Cargando catálogo desde Redis…"):
        products = repo.list_all()
    if not products:
        st.info("Aún no hay productos. Pulsa '➕ Crear producto'.")
        return

    # Filtro por origen (manual vs Radar) para que no se mezclen.
    n_manual = sum(1 for p in products if getattr(p, "origin", "manual") != "radar")
    n_radar = sum(1 for p in products if getattr(p, "origin", "manual") == "radar")
    origin_filter = st.radio(
        "Origen",
        [f"Todos ({len(products)})", f"✍️ Manuales ({n_manual})", f"🔍 Radar ({n_radar})"],
        horizontal=True, key="prod_origin_filter", label_visibility="collapsed",
    )
    if origin_filter.startswith("✍️"):
        products = [p for p in products if getattr(p, "origin", "manual") != "radar"]
    elif origin_filter.startswith("🔍"):
        products = [p for p in products if getattr(p, "origin", "manual") == "radar"]

    for p in products:
        _render_product_card(p, repo)


def _build_pack_for_product(p: Product) -> None:
    """Construye el pack completo de un producto (fotos + research + estilos
    + carruseles + carpeta). Mismo flujo que el Radar, para productos creados
    a mano (flujo de descubrimiento manual con el panel web de EchoTik)."""
    from src.tiktok_shop.services.creation_pack import PackOptions, build_pack

    with st.status(f"📦 Pack de '{p.name}'…", expanded=True) as status:
        try:
            res = build_pack(p, options=PackOptions(), log_callback=status.write)
            status.update(
                label=(f"✅ Pack listo · 🎠 {res.carousels_generated} · "
                       f"🎥 {res.presets_generated} · 🖼️ {res.photos_downloaded}"),
                state="complete", expanded=False,
            )
            st.toast(f"📦 Carpeta lista en {res.folder}")
        except Exception as e:
            status.update(label=f"❌ Error: {e}", state="error")
            st.exception(e)


def _render_product_card(p: Product, repo: ProductRepo) -> None:
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([1.5, 2.2, 1, 1])

        # Foto preview: prefiere generated[0], fallback source[0]
        preview_photos, _origin = p.photos.best_available()
        with c1:
            if preview_photos and preview_photos[0].local_path and os.path.exists(preview_photos[0].local_path):
                st.image(preview_photos[0].local_path, use_container_width=True)
            else:
                st.markdown("*sin fotos*")

        with c2:
            tier_def = VIDEO_MODELS.get(p.video_config.default_tier, {})
            tier_badge = tier_def.get("tier_color", "⚪") + " " + tier_def.get("name", p.video_config.default_tier)
            origin_badge = "🔍 Radar" if getattr(p, "origin", "manual") == "radar" else "✍️ Manual"
            st.markdown(f"**{p.name}**  ·  {tier_badge}  ·  `{origin_badge}`")
            st.caption(f"`{p.slug}` · {p.category}/{p.subcategory or '-'} · {p.brand or 'sin marca'}")
            if p.tiktok_shop.price_eur is not None:
                st.caption(f"💶 {p.tiktok_shop.price_eur:.2f}€ · 🏷️ {p.tiktok_shop.commission_rate * 100:.0f}%")
            if p.needs_nano_banana_regeneration:
                st.caption("🍌 Sugerido: regenerar fotos con Nano Banana 2")

        with c3:
            # Contadores: solo activas (no eliminadas). Si hay eliminadas
            # añadimos pista visual ("3 (1 ⌫)") para que el operador sepa
            # que hay fotos soft-deleted recuperables.
            active_src = sum(1 for ph in p.photos.source if not ph.deleted)
            del_src = sum(1 for ph in p.photos.source if ph.deleted)
            active_gen = sum(1 for ph in p.photos.generated if not ph.deleted)
            del_gen = sum(1 for ph in p.photos.generated if ph.deleted)
            st.metric(
                "Source", active_src,
                delta=f"{del_src} ⌫" if del_src else None,
                delta_color="off",
                help=f"{del_src} eliminadas (soft-delete, recuperables)" if del_src else None,
            )
            st.metric(
                "Generated", active_gen,
                delta=f"{del_gen} ⌫" if del_gen else None,
                delta_color="off",
                help=f"{del_gen} eliminadas (soft-delete, recuperables)" if del_gen else None,
            )

        with c4:
            if st.button("✏️", key=f"edit_prod_{p.id}", help="Editar producto"):
                st.session_state[f"_edit_for_{p.id}"] = True
            if st.button("🍌", key=f"nb_prod_{p.id}", help="Generar fotos premium con Nano Banana 2"):
                st.session_state[f"_nano_banana_for_{p.id}"] = True
            if st.button("📦", key=f"pack_prod_{p.id}",
                         help="Pack completo: fotos + research vídeos ganadores + estilos + carruseles + carpeta"):
                _build_pack_for_product(p)
            # Borrado en 2 clicks: primer click marca pendiente, segundo confirma
            confirm_key = f"_confirm_del_prod_{p.id}"
            if st.session_state.get(confirm_key):
                if st.button("⚠️ Confirmar", key=f"confirm_btn_{p.id}", type="primary",
                             help=f"Borrar '{p.name}' definitivamente"):
                    repo.delete(p.id)
                    st.session_state.pop(confirm_key, None)
                    st.success(f"Producto '{p.name}' borrado.")
                    st.rerun()
                if st.button("❌", key=f"cancel_del_{p.id}", help="Cancelar"):
                    st.session_state.pop(confirm_key, None)
                    st.rerun()
            else:
                if st.button("🗑️", key=f"del_prod_{p.id}", help="Borrar producto (pide confirmación)"):
                    st.session_state[confirm_key] = True
                    st.rerun()

        # Editor inline (visible al pulsar ✏️)
        if st.session_state.get(f"_edit_for_{p.id}"):
            _render_edit_wizard(p, repo)

        # Paso 7 inline: bloque Nano Banana 2 (visible al pulsar 🍌)
        if st.session_state.get(f"_nano_banana_for_{p.id}"):
            _render_nano_banana_block(p, repo)


def _render_edit_wizard(p: Product, repo: ProductRepo) -> None:
    """Editor de producto inline con todos los campos editables.

    Secciones (expanders):
      1. Identidad y precio
      2. Audiencia y selling points (listas editables)
      3. Configuración técnica (tier, duración, resolución, estilos)
      4. Voz preferida
      5. Hooks library (CRUD)
      6. Gestión de fotos (source + generated, soft-delete + tipos)
      7. Re-analizar con Gemini
      8. Slug rename (peligroso, expander oculto)
    """
    with st.container(border=True):
        st.markdown(f"### ✏️ Editando — `{p.slug}`")

        # ---------- 1. Identidad y precio ----------
        with st.expander("1. Identidad y precio", expanded=True):
            new_name = st.text_input("Nombre comercial *", value=p.name, key=f"e_name_{p.id}")
            c1, c2 = st.columns(2)
            with c1:
                new_brand = st.text_input("Marca", value=p.brand or "", key=f"e_brand_{p.id}")
                new_category = st.selectbox(
                    "Categoría", NICHE_OPTIONS,
                    index=NICHE_OPTIONS.index(p.category) if p.category in NICHE_OPTIONS else 0,
                    key=f"e_cat_{p.id}",
                )
                new_subcategory = st.text_input(
                    "Subcategoría", value=p.subcategory or "", key=f"e_subcat_{p.id}",
                )
            with c2:
                new_price = st.number_input(
                    "Precio EUR", min_value=0.0,
                    value=float(p.tiktok_shop.price_eur or 0.0), step=0.5,
                    key=f"e_price_{p.id}",
                )
                new_commission = st.slider(
                    "Comisión (%)", 0, 50,
                    int(round(p.tiktok_shop.commission_rate * 100)),
                    key=f"e_comm_{p.id}",
                ) / 100.0
                new_url = st.text_input(
                    "URL TikTok Shop", value=p.tiktok_shop.product_url or "",
                    key=f"e_url_{p.id}",
                )
                new_pid = st.text_input(
                    "Product ID TikTok Shop", value=p.tiktok_shop.product_id or "",
                    key=f"e_pid_{p.id}",
                )

        # ---------- 2. Audiencia y selling points ----------
        with st.expander("2. Audiencia y selling points", expanded=False):
            audience_text = st.text_area(
                "Audiencias objetivo (una por línea)",
                value="\n".join(p.target_audience),
                key=f"e_aud_{p.id}", height=120,
            )
            features_text = st.text_area(
                "Key features (una por línea)",
                value="\n".join(p.key_features),
                key=f"e_feat_{p.id}", height=120,
            )
            sp_text = st.text_area(
                "Selling points (uno por línea)",
                value="\n".join(p.selling_points),
                key=f"e_sp_{p.id}", height=120,
            )

        # ---------- 3. Configuración técnica ----------
        with st.expander("3. Configuración técnica", expanded=False):
            tier_options = [k for k in VIDEO_MODELS]
            new_tier = st.selectbox(
                "Tier por defecto", tier_options,
                index=tier_options.index(p.video_config.default_tier)
                if p.video_config.default_tier in tier_options else 0,
                format_func=lambda k: f"{VIDEO_MODELS[k]['tier_color']} {VIDEO_MODELS[k]['name']}",
                key=f"e_tier_{p.id}",
            )
            cc1, cc2 = st.columns(2)
            with cc1:
                new_duration = st.selectbox(
                    "Duración (s)", [5, 10, 12, 15, 20, 24, 25, 30],
                    index=[5, 10, 12, 15, 20, 24, 25, 30].index(p.video_config.default_duration)
                    if p.video_config.default_duration in [5, 10, 12, 15, 20, 24, 25, 30] else 3,
                    key=f"e_dur_{p.id}",
                )
            with cc2:
                res_options = ["480p", "720p", "1080p-SR", "1440p-SR"]
                new_res = st.selectbox(
                    "Resolución", res_options,
                    index=res_options.index(p.video_config.default_resolution)
                    if p.video_config.default_resolution in res_options else 1,
                    key=f"e_res_{p.id}",
                )
            new_styles = st.multiselect(
                "Estilos preferidos", VIDEO_STYLES,
                default=[s for s in p.video_config.preferred_styles if s in VIDEO_STYLES],
                key=f"e_styles_{p.id}",
            )
            new_complex = st.checkbox(
                "Packaging con texto complejo (override manual)",
                value=p.video_config.has_complex_packaging,
                key=f"e_complex_{p.id}",
                help="Si marcas esto, los directors evitarán close-ups que requieran "
                     "renderizar el texto del packaging (Seedance Fast no lo recrea bien).",
            )

        # ---------- 4. Voz preferida ----------
        with st.expander("4. Voz preferida", expanded=False):
            from src.tiktok_shop.repos import VoiceRepo
            voices = VoiceRepo().list_all(include_presets=True)
            voice_options = [""] + [v.minimax_voice_id for v in voices]
            voice_labels = {"": "(usar default del usuario)"}
            voice_labels.update({v.minimax_voice_id: v.name for v in voices})
            current_voice = p.video_config.voice_preference.voice_id or ""
            new_voice = st.selectbox(
                "Voice ID preferida",
                voice_options,
                index=voice_options.index(current_voice) if current_voice in voice_options else 0,
                format_func=lambda vid: voice_labels.get(vid, vid),
                key=f"e_voice_{p.id}",
            )
            new_tone = st.selectbox(
                "Tono preferido", ["energetic", "calm", "informative"],
                index=["energetic", "calm", "informative"].index(p.video_config.voice_preference.tone),
                key=f"e_tone_{p.id}",
            )

        # ---------- 5. Hooks library ----------
        with st.expander(f"5. Hooks library ({len(p.hooks_library)})", expanded=False):
            _render_hooks_editor(p, repo)

        # ---------- 6. Gestión de fotos (sub-section pesada) ----------
        with st.expander("6. Fotos del producto", expanded=False):
            _render_photos_management(p, repo)

        # ---------- 7. Re-analizar con Gemini ----------
        with st.expander("7. Re-analizar con Gemini", expanded=False):
            st.caption(
                "Re-ejecuta el análisis Gemini Vision con las fotos source actuales "
                "(no eliminadas). Actualiza key_features, audiencias sugeridas y selling "
                "points. **Sobrescribe** lo que tengas escrito a mano arriba."
            )
            last = p.last_analyzed_at or "(nunca)"
            st.caption(f"Último análisis: {last}")
            if st.button("🤖 Re-analizar ahora", key=f"e_reanalyze_{p.id}"):
                with st.spinner("Analizando con Gemini…"):
                    try:
                        analysis = ps.re_analyze_with_gemini(p)
                        if analysis:
                            repo.save(p)
                            st.success(
                                f"✅ Análisis OK. {len(p.key_features)} features, "
                                f"{len(p.target_audience)} audiencias actualizadas. "
                                f"Recarga el editor para ver cambios."
                            )
                            st.rerun()
                        else:
                            st.warning("Sin fotos source válidas — análisis cancelado.")
                    except Exception as e:
                        st.error(f"Análisis falló: {e}")

        # ---------- 8. Renombrar slug (peligroso) ----------
        with st.expander("8. ⚠️ Renombrar slug (afecta carpeta Drive)", expanded=False):
            st.caption(
                "Cambiar el slug renombra la carpeta `_products/<slug>/` y actualiza "
                "los `local_path` de las fotos. Los **vídeos ya generados** (en "
                "`_users/<user>/products/<old_slug>/videos/`) NO se mueven."
            )
            new_slug_input = st.text_input(
                "Nuevo slug (se normaliza automáticamente)",
                value=p.slug, key=f"e_slug_{p.id}",
            )
            move_folder = st.checkbox(
                "Renombrar también la carpeta en Drive",
                value=True, key=f"e_move_{p.id}",
            )
            if st.button("🔄 Renombrar slug", key=f"e_rename_{p.id}"):
                ok = ps.rename_product_slug(
                    p, new_slug=new_slug_input, move_drive_folder=move_folder,
                )
                if ok:
                    repo.save(p)
                    st.success(f"✅ Slug ahora `{p.slug}`")
                    st.rerun()
                else:
                    st.warning("Sin cambios (mismo slug o error renombrando carpeta).")

        # ---------- Botones finales: guardar / cancelar ----------
        st.divider()
        bcol1, bcol2 = st.columns(2)
        with bcol1:
            if st.button("💾 Guardar cambios", key=f"e_save_{p.id}", type="primary",
                         use_container_width=True):
                # Validar antes
                ok, err = require_non_empty(new_name, "Nombre comercial")
                if not ok:
                    st.error(err)
                    return
                ok, err = validate_tiktok_shop_url(new_url, required=False)
                if not ok:
                    st.error(err)
                    return
                # Aplicar cambios al modelo
                p.name = new_name.strip()
                p.brand = new_brand.strip() or None
                p.category = new_category
                p.subcategory = new_subcategory.strip() or None
                p.tiktok_shop.price_eur = new_price if new_price > 0 else None
                p.tiktok_shop.commission_rate = new_commission
                p.tiktok_shop.product_url = new_url.strip() or None
                p.tiktok_shop.product_id = new_pid.strip() or None
                p.target_audience = [s.strip() for s in audience_text.splitlines() if s.strip()]
                p.key_features = [s.strip() for s in features_text.splitlines() if s.strip()]
                p.selling_points = [s.strip() for s in sp_text.splitlines() if s.strip()]
                p.video_config.default_tier = new_tier
                p.video_config.default_duration = new_duration
                p.video_config.default_resolution = new_res
                p.video_config.preferred_styles = new_styles
                p.video_config.has_complex_packaging = new_complex
                p.video_config.voice_preference.voice_id = new_voice or None
                p.video_config.voice_preference.tone = new_tone
                p.touch()
                repo.save(p)
                st.session_state.pop(f"_edit_for_{p.id}", None)
                st.success(f"✅ Producto `{p.slug}` actualizado")
                st.rerun()
        with bcol2:
            if st.button("❌ Cerrar sin guardar", key=f"e_close_{p.id}",
                         use_container_width=True):
                st.session_state.pop(f"_edit_for_{p.id}", None)
                st.rerun()


def _render_hooks_editor(p: Product, repo: ProductRepo) -> None:
    """CRUD de hooks_library inline."""
    if not p.hooks_library:
        st.caption("Sin hooks. Añade el primero abajo.")
    for i, h in enumerate(p.hooks_library):
        c1, c2, c3 = st.columns([1, 3, 0.4])
        with c1:
            new_cat = st.text_input(
                "Categoría", value=h.category, key=f"h_cat_{p.id}_{i}",
                label_visibility="collapsed",
            )
        with c2:
            new_tpl = st.text_input(
                "Template", value=h.template, key=f"h_tpl_{p.id}_{i}",
                label_visibility="collapsed",
            )
        with c3:
            if st.button("🗑️", key=f"h_del_{p.id}_{i}"):
                ps.remove_hook(p, index=i)
                repo.save(p)
                st.rerun()
        # Detectar cambio sin botón guardar (auto-save por hook)
        if new_cat != h.category or new_tpl != h.template:
            ps.update_hook(p, index=i, category=new_cat, template=new_tpl)
            # No persistimos en cada keystroke — se persiste al "Guardar cambios" del editor

    st.divider()
    cc1, cc2, cc3 = st.columns([1, 3, 0.6])
    with cc1:
        new_h_cat = st.text_input("Cat", key=f"h_new_cat_{p.id}",
                                   placeholder="ej: curiosity")
    with cc2:
        new_h_tpl = st.text_input("Template", key=f"h_new_tpl_{p.id}",
                                   placeholder="POV: descubres...")
    with cc3:
        if st.button("➕", key=f"h_add_{p.id}"):
            if new_h_cat and new_h_tpl:
                ps.add_hook(p, category=new_h_cat, template=new_h_tpl)
                repo.save(p)
                st.rerun()


def _render_photos_management(p: Product, repo: ProductRepo) -> None:
    """Gestión avanzada de fotos source y generated.

    Cada foto: preview + tipo (dropdown) + tier-preference toggles + delete.
    Plus: upload zone para añadir nuevas en cualquiera de las dos buckets.
    """
    types_options = ["packshot", "lifestyle", "detail", "in_use", "macro"]
    tier_options = ["standard", "advanced", "pro"]

    def _render_bucket(bucket_name: str, photos: list[ProductPhoto], in_source: bool) -> None:
        active = [ph for ph in photos if not ph.deleted]
        deleted = [ph for ph in photos if ph.deleted]
        st.markdown(f"**{bucket_name}** · {len(active)} activas, {len(deleted)} eliminadas")
        if not active:
            st.caption("(vacía)")
        for ph in active:
            with st.container(border=True):
                pc1, pc2, pc3 = st.columns([1, 3, 0.6])
                with pc1:
                    if ph.local_path and os.path.exists(ph.local_path):
                        st.image(ph.local_path, use_container_width=True)
                    else:
                        st.caption("(no en disco)")
                with pc2:
                    st.caption(f"`{ph.filename}`")
                    current_type = ph.type if ph.type in types_options else None
                    new_type = st.selectbox(
                        "Tipo", types_options,
                        index=types_options.index(current_type) if current_type else 0,
                        key=f"ph_type_{p.id}_{bucket_name}_{ph.filename}",
                    )
                    if new_type != ph.type:
                        ps.update_photo_type(
                            p, filename=ph.filename, new_type=new_type, in_source=in_source,
                        )
                    # Tier preference toggles
                    cols_t = st.columns(len(tier_options))
                    for ti, tier in enumerate(tier_options):
                        with cols_t[ti]:
                            checked = tier in ph.preferred_for_tiers
                            if st.checkbox(
                                f"prefer {tier}", value=checked,
                                key=f"ph_pref_{p.id}_{bucket_name}_{ph.filename}_{tier}",
                            ) != checked:
                                ps.toggle_photo_preferred_tier(
                                    p, filename=ph.filename, tier=tier, in_source=in_source,
                                )
                with pc3:
                    if st.button("🗑️", key=f"ph_del_{p.id}_{bucket_name}_{ph.filename}",
                                  help="Eliminar (soft-delete, no borra del disco)"):
                        ps.mark_photo_deleted(p, filename=ph.filename, in_source=in_source)
                        repo.save(p)
                        st.rerun()
        if deleted:
            with st.expander(f"🗑️ Eliminadas ({len(deleted)})", expanded=False):
                st.caption(
                    "Las fotos soft-deleted siguen en disco. Puedes **restaurarlas** "
                    "(vuelven al listado activo) o **borrarlas permanentemente** "
                    "(elimina archivo del Drive — irreversible)."
                )
                for ph in deleted:
                    dc1, dc2, dc3, dc4 = st.columns([1, 2.5, 1, 1])
                    with dc1:
                        if ph.local_path and os.path.exists(ph.local_path):
                            st.image(ph.local_path, use_container_width=True)
                        else:
                            st.caption("(archivo ya no en disco)")
                    with dc2:
                        st.caption(f"~~`{ph.filename}`~~")
                        st.caption(f"📁 `{ph.local_path or '?'}`")
                    with dc3:
                        # Solo permitir restaurar si el archivo sigue en disco
                        can_restore = bool(ph.local_path and os.path.exists(ph.local_path))
                        if st.button("↩️ Restaurar",
                                      key=f"ph_restore_{p.id}_{bucket_name}_{ph.filename}",
                                      disabled=not can_restore,
                                      help="Volver al listado activo" if can_restore else "Archivo no en disco"):
                            ps.restore_photo(
                                p, filename=ph.filename, in_source=in_source,
                            )
                            repo.save(p)
                            st.rerun()
                    with dc4:
                        # Hard-delete con confirmación de 2 clicks
                        confirm_key = f"_confirm_hd_{p.id}_{bucket_name}_{ph.filename}"
                        if st.session_state.get(confirm_key):
                            if st.button("⚠️ Sí, borrar",
                                          key=f"hd_yes_{p.id}_{bucket_name}_{ph.filename}",
                                          type="primary"):
                                ps.hard_delete_photo(
                                    p, filename=ph.filename, in_source=in_source,
                                )
                                st.session_state.pop(confirm_key, None)
                                repo.save(p)
                                st.toast(f"🗑️ `{ph.filename}` borrada del disco", icon="⚠️")
                                st.rerun()
                            if st.button("❌",
                                          key=f"hd_no_{p.id}_{bucket_name}_{ph.filename}"):
                                st.session_state.pop(confirm_key, None)
                                st.rerun()
                        else:
                            if st.button("🗑️ Borrar disco",
                                          key=f"hd_btn_{p.id}_{bucket_name}_{ph.filename}",
                                          help="Borrar definitivamente del Drive (irreversible)"):
                                st.session_state[confirm_key] = True
                                st.rerun()

    _render_bucket("📷 Source", p.photos.source, in_source=True)

    # Upload zone source
    new_source = st.file_uploader(
        "Añadir fotos a source (jpg/png/webp)",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        key=f"upload_src_{p.id}",
    )
    if new_source:
        new_origin = st.selectbox(
            "Origen de estas fotos nuevas",
            ["internet", "own", "tiktok_shop_url"],
            key=f"upload_src_origin_{p.id}",
        )
        if st.button("📤 Subir source", key=f"upload_src_btn_{p.id}"):
            for f in new_source:
                ok, err = validate_photo_upload(filename=f.name, num_bytes=len(f.getvalue()))
                if not ok:
                    st.error(f"`{f.name}`: {err}")
                    continue
                ps.add_source_photo(
                    p, filename=f.name, bytes_data=f.getvalue(),
                    origin=new_origin,
                )
            repo.save(p)
            st.success(f"✅ {len(new_source)} fotos añadidas a source")
            st.rerun()

    st.divider()
    _render_bucket("✨ Generated", p.photos.generated, in_source=False)

    new_gen = st.file_uploader(
        "Añadir fotos a generated (manual, p.ej. desde Nano Banana 2)",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        key=f"upload_gen_{p.id}",
    )
    if new_gen:
        gen_type = st.selectbox(
            "Tipo de plano para todas",
            ["packshot", "lifestyle", "detail", "in_use", "macro"],
            key=f"upload_gen_type_{p.id}",
        )
        if st.button("📤 Subir generated", key=f"upload_gen_btn_{p.id}"):
            for f in new_gen:
                ok, err = validate_photo_upload(filename=f.name, num_bytes=len(f.getvalue()))
                if not ok:
                    st.error(f"`{f.name}`: {err}")
                    continue
                ps.add_generated_photo(
                    p, filename=f.name, bytes_data=f.getvalue(),
                    photo_type=gen_type,
                )
            repo.save(p)
            st.success(f"✅ {len(new_gen)} fotos añadidas a generated")
            st.rerun()


def _render_nano_banana_block(p: Product, repo: ProductRepo) -> None:
    """Workflow Nano Banana 2 — 4 pasos:

    1. Análisis de fotos source actuales con Gemini (qué hay, qué falta).
    2. Checklist de planos a generar (con sugerencias inteligentes).
    3. Genera prompt optimizado (Gemini con `nano_banana_director.md`).
    4. Output: zip + instrucciones + upload zone con tipo por foto.
    """
    with st.container(border=True):
        st.markdown("### 🍌 Nano Banana 2 — fotos premium")
        st.caption(
            "Workflow guiado: analizar → elegir planos → generar prompt → subir fotos."
        )

        active_source = [ph for ph in p.photos.source
                         if not ph.deleted and ph.local_path and os.path.exists(ph.local_path)]
        source_photos = [ph.local_path for ph in active_source]
        if not source_photos:
            st.error("Este producto no tiene fotos source válidas. Súbelas primero.")
            if st.button("❌ Cerrar", key=f"nb_close_empty_{p.id}"):
                st.session_state.pop(f"_nano_banana_for_{p.id}", None)
                st.rerun()
            return

        # ============================================================
        # Paso 1: Análisis previo de fotos source
        # ============================================================
        st.markdown("**Paso 1 — Análisis de fotos source actuales**")
        existing_types = sorted({ph.type for ph in active_source if ph.type})
        all_types = ["packshot", "lifestyle", "detail", "in_use", "macro"]
        missing_types = [t for t in all_types if t not in existing_types]
        ec1, ec2 = st.columns(2)
        with ec1:
            st.caption(f"📷 Tienes ({len(active_source)} fotos):")
            for t in all_types:
                count = sum(1 for ph in active_source if ph.type == t)
                if count:
                    st.caption(f"  ✅ {t}: {count}")
        with ec2:
            st.caption("📋 Planos que te faltan:")
            for t in missing_types:
                st.caption(f"  ❌ {t}")
            if not missing_types:
                st.caption("  🎉 Tienes todos los tipos básicos.")

        st.divider()

        # ============================================================
        # Paso 2: Checklist de planos a generar
        # ============================================================
        st.markdown("**Paso 2 — ¿Qué planos generar?**")
        suggested_defaults = (missing_types + ["packshot", "macro"])[:5]
        # Dedup preservando orden
        seen = set()
        suggested_defaults = [
            t for t in suggested_defaults
            if not (t in seen or seen.add(t))
        ]
        use_cases = st.multiselect(
            "Tipos de plano (sugerencia auto: faltantes + esenciales)",
            all_types,
            default=suggested_defaults,
            key=f"nb_uc_{p.id}",
            help="Marcados por defecto los que TE FALTAN según el análisis del paso 1.",
        )
        custom_extra = st.text_input(
            "Descripción libre extra (opcional)",
            placeholder="ej: comparativa antes/después, en mano con luz natural, etc.",
            key=f"nb_extra_{p.id}",
        )
        n_angles = st.slider(
            "Número total de fotos a pedir", 4, 8, max(4, len(use_cases)),
            key=f"nb_n_{p.id}",
        )

        st.divider()

        # ============================================================
        # Paso 3: Generar prompt + Cerrar
        # ============================================================
        st.markdown("**Paso 3 — Generar prompt para Gemini chat**")
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("🪄 Generar prompt", key=f"nb_gen_{p.id}", type="primary",
                         use_container_width=True):
                with st.spinner("Generando prompt con Gemini…"):
                    description = " · ".join(filter(None, [
                        p.brand or "",
                        " · ".join(p.selling_points[:3]),
                        custom_extra.strip() if custom_extra else "",
                    ])) or p.name
                    prompt = generate_nano_banana_prompt(
                        product_name=p.name,
                        product_description=description,
                        use_cases=use_cases or ["packshot", "lifestyle", "macro"],
                        n_angles=n_angles,
                        photo_paths=source_photos,
                    )
                    st.session_state[f"_nb_prompt_{p.id}"] = prompt
                    # Persistir prompt en prompt_templates/
                    templates_dir = product_prompt_templates_folder(p.slug)
                    Path(templates_dir).mkdir(parents=True, exist_ok=True)
                    with open(os.path.join(templates_dir, "nano_banana_prompt.txt"),
                              "w", encoding="utf-8") as f:
                        f.write(prompt)
        with col_b:
            if st.button("❌ Cerrar", key=f"nb_close_{p.id}", use_container_width=True):
                st.session_state.pop(f"_nano_banana_for_{p.id}", None)
                st.session_state.pop(f"_nb_prompt_{p.id}", None)
                st.rerun()

        # ============================================================
        # Paso 4: Output — prompt + zip + instrucciones + upload
        # ============================================================
        prompt = st.session_state.get(f"_nb_prompt_{p.id}")
        if prompt:
            st.divider()
            st.markdown("**Paso 4 — Pega en Gemini chat y sube las fotos generadas**")

            st.markdown("**📋 Prompt generado**")
            st.code(prompt, language="text", wrap_lines=True)

            zip_bytes = _zip_photos(source_photos)
            ic1, ic2 = st.columns(2)
            with ic1:
                st.download_button(
                    "📥 Descargar fotos source (zip)",
                    data=zip_bytes,
                    file_name=f"{p.slug}_source_photos.zip",
                    mime="application/zip",
                    use_container_width=True,
                )
            with ic2:
                st.caption("📖 Pasos a seguir:")
                st.caption("1. Abre [gemini.google.com](https://gemini.google.com) (plan Pro)")
                st.caption("2. Selecciona modelo Nano Banana 2")
                st.caption("3. Sube las fotos descargadas")
                st.caption("4. Pega el prompt y espera 4-8 fotos generadas")
                st.caption("5. Guárdalas en tu PC y súbelas abajo")

            st.divider()
            st.markdown("**📤 Sube aquí las fotos generadas (cada una con su tipo)**")
            uploaded = st.file_uploader(
                "Fotos premium (jpg/png/webp)",
                type=["jpg", "jpeg", "png", "webp"],
                accept_multiple_files=True,
                key=f"nb_upload_{p.id}",
            )
            if uploaded:
                # Por cada foto subida, dropdown de tipo independiente
                st.caption("Asigna el tipo de plano a cada foto:")
                photo_types: dict[str, str] = {}
                for i, f in enumerate(uploaded):
                    fcols = st.columns([1, 2])
                    with fcols[0]:
                        try:
                            st.image(f.getvalue(), use_container_width=True)
                        except Exception:
                            st.caption(f"`{f.name}`")
                    with fcols[1]:
                        st.caption(f"`{f.name}`")
                        # Sugerencia: el primer use_case del usuario, rotando
                        default_type = use_cases[i % max(1, len(use_cases))] if use_cases else "packshot"
                        if default_type not in all_types:
                            default_type = "packshot"
                        photo_types[f.name] = st.selectbox(
                            "Tipo", all_types,
                            index=all_types.index(default_type),
                            key=f"nb_uptype_{p.id}_{i}",
                            label_visibility="collapsed",
                        )

                if st.button("📤 Confirmar subida y guardar", key=f"nb_upload_btn_{p.id}",
                              type="primary", use_container_width=True):
                    saved = 0
                    for f in uploaded:
                        ok, err = validate_photo_upload(
                            filename=f.name, num_bytes=len(f.getvalue()),
                        )
                        if not ok:
                            st.error(f"`{f.name}`: {err}")
                            continue
                        ps.add_generated_photo(
                            p, filename=f.name, bytes_data=f.getvalue(),
                            photo_type=photo_types.get(f.name, "packshot"),
                            prompt_used=prompt,
                        )
                        saved += 1
                    repo.save(p)
                    st.success(
                        f"✅ {saved} fotos premium añadidas. El próximo vídeo "
                        "usará estas por defecto."
                    )
                    st.session_state.pop(f"_nano_banana_for_{p.id}", None)
                    st.session_state.pop(f"_nb_prompt_{p.id}", None)
                    st.rerun()


def _zip_photos(paths: list[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in paths:
            if os.path.exists(p):
                zf.write(p, os.path.basename(p))
    return buf.getvalue()


def _wizard_create(repo: ProductRepo) -> None:
    st.subheader("🪄 Wizard — nuevo producto")
    with st.form("shop_product_wizard", clear_on_submit=False):

        with st.expander("Paso 1-3 · Identidad y precio", expanded=True):
            name = st.text_input("Nombre comercial *", placeholder="Primal Pump - Gominolas Creatina")
            col1, col2 = st.columns(2)
            with col1:
                brand = st.text_input("Marca", placeholder="Primal Pump")
                category = st.selectbox("Categoría", NICHE_OPTIONS, index=NICHE_OPTIONS.index("otros"))
                subcategory = st.text_input("Subcategoría", placeholder="creatina")
            with col2:
                price = st.number_input("Precio EUR", min_value=0.0, value=0.0, step=0.5)
                commission = st.slider("Comisión (%)", 0, 50, 10) / 100.0
                tiktok_url = st.text_input("URL TikTok Shop", placeholder="https://www.tiktok.com/...")
                tiktok_product_id = st.text_input("Product ID TikTok Shop (opcional)")

        with st.expander("Paso 1 (continuación) · Fotos source", expanded=True):
            st.caption("Sube 1-5 fotos originales (Amazon, web fabricante, propias). Se guardan en `photos_source/`.")
            uploaded = st.file_uploader(
                "Fotos JPG/PNG",
                type=["jpg", "jpeg", "png", "webp"],
                accept_multiple_files=True,
            )
            origin = st.selectbox(
                "Origen de estas fotos",
                ["internet", "own", "tiktok_shop_url"],
                index=0,
            )

        with st.expander("Paso 2 · Análisis Gemini Vision", expanded=True):
            analyze_with_gemini = st.checkbox(
                "🤖 Analizar fotos con Gemini al guardar (autocompleta features/audiencia/quality flag)",
                value=True,
            )

        with st.expander("Paso 5 · Configuración técnica del vídeo", expanded=False):
            col3, col4, col5 = st.columns(3)
            tier_options = [k for k in VIDEO_MODELS if VIDEO_MODELS[k].get("type") != "prompt_only" or k == "veo3_prompt_only"]
            with col3:
                default_tier = st.selectbox(
                    "Tier por defecto",
                    tier_options,
                    index=tier_options.index(DEFAULT_TIER) if DEFAULT_TIER in tier_options else 0,
                    format_func=lambda k: f"{VIDEO_MODELS[k]['tier_color']} {VIDEO_MODELS[k]['name']}",
                )
            with col4:
                default_duration = st.selectbox("Duración (s)", [5, 10, 15], index=2)
            with col5:
                default_resolution = st.selectbox("Resolución", ["720p", "1080p"], index=0)

            preferred_styles = st.multiselect(
                "Estilos preferidos",
                VIDEO_STYLES,
                default=["asmr_macro", "lifestyle_aspirational"],
            )

        col_a, col_b = st.columns([1, 1])
        with col_a:
            submitted = st.form_submit_button("💾 Crear producto", type="primary", use_container_width=True)
        with col_b:
            cancel = st.form_submit_button("❌ Cancelar", use_container_width=True)

    if cancel:
        st.session_state["_shop_show_wizard"] = False
        st.rerun()

    if submitted:
        # === Validación de inputs antes de tocar disco ===
        ok, err = require_non_empty(name, "Nombre comercial")
        if not ok:
            st.error(err)
            return
        ok, err = validate_tiktok_shop_url(tiktok_url, required=False)
        if not ok:
            st.error(err)
            return
        # Validar cada foto subida (extensión + tamaño)
        for f in (uploaded or []):
            ok, err = validate_photo_upload(filename=f.name, num_bytes=len(f.getvalue()))
            if not ok:
                st.error(f"Foto `{f.name}`: {err}")
                return

        slug = slugify(name)
        if repo.get_by_slug(slug) is not None:
            st.error(f"Ya existe un producto con slug `{slug}`. Cambia el nombre.")
            return

        product = Product(
            slug=slug,
            name=name.strip(),
            brand=(brand or None) and brand.strip(),
            category=category,
            subcategory=(subcategory or None) and subcategory.strip(),
            tiktok_shop=TikTokShopMeta(
                product_url=tiktok_url or None,
                product_id=tiktok_product_id or None,
                commission_rate=commission,
                price_eur=price if price > 0 else None,
            ),
            video_config=VideoConfig(
                default_tier=default_tier,
                default_duration=default_duration,
                default_resolution=default_resolution,
                preferred_styles=preferred_styles,
            ),
            performance_history=PerformanceHistory(),
        )

        # 1. Crear estructura Drive
        drive_folder = product_drive_folder(slug)
        photos_source_dir = product_photos_source_folder(slug)
        photos_generated_dir = product_photos_generated_folder(slug)
        templates_dir = product_prompt_templates_folder(slug)
        for d in (drive_folder, photos_source_dir, photos_generated_dir, templates_dir):
            Path(d).mkdir(parents=True, exist_ok=True)
        product.drive_folder = drive_folder

        # 2. Persistir fotos source
        source_photo_objs: list[ProductPhoto] = []
        for f in (uploaded or []):
            dest = os.path.join(photos_source_dir, f.name)
            with open(dest, "wb") as out:
                out.write(f.getbuffer())
            source_photo_objs.append(ProductPhoto(
                filename=f.name,
                local_path=dest,
                origin=origin,
                added_at=_now_iso(),
            ))
        product.photos = ProductPhotos(source=source_photo_objs, generated=[])

        # 3. Análisis Gemini (opcional)
        gemini_flag = False
        if analyze_with_gemini and source_photo_objs:
            with st.spinner("🤖 Analizando con Gemini…"):
                try:
                    analysis = analyze_product(
                        [ph.local_path for ph in source_photo_objs if ph.local_path],
                        extra_context=f"name={name}, brand={brand or ''}",
                    )
                    product.target_audience = analysis.get("suggested_audiences", [])[:5]
                    product.key_features = analysis.get("key_features", [])
                    product.selling_points = analysis.get("selling_points", [])
                    product.video_config.has_complex_packaging = bool(
                        analysis.get("has_complex_packaging_text", False)
                    )
                    gemini_flag = bool(analysis.get("needs_nano_banana_regeneration", False))
                    if not product.subcategory and analysis.get("subcategory"):
                        product.subcategory = analysis["subcategory"]
                    product.hooks_library = _default_hooks(product.category)
                    if product.video_config.has_complex_packaging:
                        st.warning(
                            "📦 Detectado packaging con texto complejo. "
                            "Considera tier `pro` (Reference-to-Video recrea texto mejor)."
                        )
                    st.success("✅ Análisis Gemini aplicado")
                except Exception as e:
                    st.warning(f"⚠️ Análisis Gemini falló: {e}. Producto guardado sin análisis.")

        # 4. Decisión combinada Gemini flag + PIL resolution check
        source_paths = [ph.local_path for ph in source_photo_objs if ph.local_path]
        product.needs_nano_banana_regeneration = needs_nano_banana_regeneration(
            gemini_flag=gemini_flag, photo_paths=source_paths,
        )
        if product.needs_nano_banana_regeneration:
            low_res = any_photo_low_resolution(source_paths)
            reasons = []
            if gemini_flag:
                reasons.append("Gemini detectó calidad insuficiente")
            if low_res:
                reasons.append("alguna foto <1024px")
            st.warning(
                f"🍌 Recomendado: regenera fotos con Nano Banana 2 ({'; '.join(reasons)}). "
                f"Pulsa el botón 🍌 en la card del producto."
            )

        repo.save(product)
        st.session_state["_shop_show_wizard"] = False
        st.success(f"✅ Producto `{slug}` creado.")
        st.rerun()


def _default_hooks(_category: str) -> list[Hook]:
    """Banco de hooks default (placeholder hasta tener performance data por categoría)."""
    return [
        Hook(category="curiosity", template="POV: descubres el {producto} que..."),
        Hook(category="problem_solution", template="¿Cansado de {pain}? Esto cambió mi rutina."),
        Hook(category="social_proof", template="Mi madre lleva 1 mes con esto y..."),
    ]
