"""Tab Radar de Productos — descubrimiento automático de ganadores con
inyección de ADS + generador de carruseles.

Dos sub-secciones:
  🔍 Descubrir  — escanea EchoTik, puntúa, filtra y guarda candidatos.
                  Importa los ganadores a `Product` con un click.
  🎠 Carruseles — genera el guion de carrusel (slides + texto + caption)
                  de un producto importado, listo para Nano Banana 2.

La sección replica la estrategia del operador de 100€/día: «selecciona
productos con inyección de ADS y POCOS creadores — esa es la clave».
"""

from __future__ import annotations

import json

import streamlit as st

from src.tiktok_shop.api import echotik_cloud
from src.tiktok_shop.config import REGION_FLAGS
from src.tiktok_shop.pipeline.carousel_director import generate_carousel
from src.tiktok_shop.repos import DiscoveryRepo, ProductRepo
from src.tiktok_shop.services import discovery_service
from src.tiktok_shop.services.ads_signal import DiscoveryFilters, ScoreParams


def render() -> None:
    st.subheader("🔍 Radar de Productos")
    st.caption(
        "Descubre productos ganadores con **inyección de ADS** y **pocos "
        "creadores** (estrategia GMV Max). Importa los mejores y genera "
        "carruseles — tú solo creas, la búsqueda te la ahorras."
    )

    if not echotik_cloud.echotik_is_configured():
        st.warning(
            "⚠️ EchoTik no configurado. Define `ECHOTIK_API_USER` y "
            "`ECHOTIK_API_PASSWORD` en `.env` para usar el Radar. "
            "(Sin esto el descubrimiento no puede leer ventas reales.)"
        )

    sub = st.tabs(["🔎 Descubrir", "🗓️ Plan 7 días", "📅 Calendario", "🎠 Carruseles"])
    with sub[0]:
        _render_discover()
    with sub[1]:
        _render_week_plan()
    with sub[2]:
        _render_calendar()
    with sub[3]:
        _render_carousels()


# ═════════════════════════════════════════════════════════════════════
# 🔎 Descubrir
# ═════════════════════════════════════════════════════════════════════
def _render_discover() -> None:
    with st.expander("⚙️ Configuración del scan", expanded=False):
        from src.tiktok_shop.config import (
            ECHOTIK_REGION_OPTIONS, ECHOTIK_UNSUPPORTED_EU,
        )
        region_labels = st.multiselect(
            "Países a escanear", list(ECHOTIK_REGION_OPTIONS.keys()),
            default=["🇪🇸 España"], key="radar_regions",
            help="EchoTik solo cubre estos mercados. Cada país añade × sus "
                 "llamadas (keywords × países), ojo con la cuota.",
        )
        st.caption(
            "ℹ️ TikTok Shop EU sin datos en EchoTik (no seleccionables): "
            + ", ".join(ECHOTIK_UNSUPPORTED_EU)
        )
        col1, col2 = st.columns(2)
        with col1:
            use_ranklist = st.checkbox(
                "🏆 Incluir top ventas (ranklist)", value=False, key="radar_ranklist",
                help="El ranklist de EchoTik suele venir SIN métricas (todo a 0) "
                     "→ se filtra. Mejor usar keywords abajo. Déjalo off salvo que "
                     "tu plan sí devuelva datos en el ranklist.",
            )
            deep_ads = st.checkbox(
                "📢 Deducir GMV Max (vídeos)", value=True,
                key="radar_deepads",
                help="Analiza los vídeos del top N para deducir si el producto "
                     "está impulsado con GMV Max (1 request/producto).",
            )
            ads_source = st.radio(
                "Fuente de la señal ADS",
                ["EchoTik (engagement + ventas, barato)",
                 "Apify (etiqueta AD real de TikTok)"],
                key="radar_adssource", disabled=not deep_ads,
                help="EchoTik: deduce por views↑/engagement↓ + ventas por vídeo. "
                     "Apify: lee la etiqueta AD real (branded content) que TikTok "
                     "pone en los vídeos — la que se mira a ojo en Kalodata.",
            )
            per_source = st.slider(
                "Productos por fuente", 5, 50, 20, key="radar_persource",
            )
        with col2:
            max_infl = st.slider(
                "Máx creadores (pocos = mejor)", 20, 1000, 200, step=10,
                key="radar_maxinfl",
            )
            min_gmv = st.number_input(
                "GMV mínimo (€)", min_value=0, value=300, step=100,
                key="radar_mingmv",
                help="Calibrado a España (mercado pequeño). Súbelo para US/UK.",
            )
            min_score = st.slider(
                "Score mínimo", 0, 100, 25, key="radar_minscore",
            )
            require_ads = st.checkbox(
                "Exigir señal de ADS (media/fuerte)", value=False,
                key="radar_reqads",
            )

        keywords_raw = st.text_area(
            "Nichos / keywords a escanear (uno por línea)",
            value="crocs\nventilador techo\ncreatina\nbotella termo\nhumidificador",
            key="radar_keywords",
            help="Cada línea = una búsqueda EchoTik (/product/list, trae ventas + "
                 "creadores + views). Es la fuente principal del Radar. Pon tus nichos.",
        )

    if st.button("🔍 Escanear ahora", type="primary", key="radar_scan_btn"):
        regions = [ECHOTIK_REGION_OPTIONS[lbl] for lbl in region_labels] or ["ES"]
        keywords = [k.strip() for k in keywords_raw.splitlines() if k.strip()]
        filters = DiscoveryFilters(
            max_influencers=int(max_infl),
            min_gmv_eur=float(min_gmv),
            min_score=float(min_score),
            require_ads_signal=bool(require_ads),
        )
        with st.status(f"🛰️ Escaneando {len(regions)} país(es)…", expanded=True) as status:
            def _log(msg: str) -> None:
                status.write(msg)

            total = 0
            try:
                ads_provider = "apify" if ads_source.startswith("Apify") else "echotik"
                for code in regions:
                    flag = REGION_FLAGS.get(code, "")
                    status.write(f"\n{flag} === {code} ===")
                    results = discovery_service.discover(
                        region=code,
                        keywords=keywords,
                        use_ranklist=use_ranklist,
                        per_source_limit=int(per_source),
                        deep_ads_check=deep_ads,
                        ads_provider=ads_provider,
                        filters=filters,
                        score_params=ScoreParams(comp_zero_above=max(60, int(max_infl) + 50)),
                        log_callback=_log,
                    )
                    total += len(results)
                status.update(
                    label=f"✅ {total} ganadores en {len(regions)} país(es)",
                    state="complete", expanded=False,
                )
            except Exception as e:
                status.update(label=f"❌ Error: {e}", state="error")
                st.exception(e)

    # Listado persistente (sobrevive reruns/sesiones)
    st.divider()
    repo = DiscoveryRepo()
    with st.spinner("📡 Cargando candidatos del Radar…"):
        candidates = repo.list_all()

    if not candidates:
        st.info("Sin candidatos todavía. Pulsa **Escanear ahora**.")
        return

    n_imported = sum(1 for c in candidates if c.imported)
    head_cols = st.columns([3, 1])
    with head_cols[0]:
        st.markdown(f"**{len(candidates)} candidatos** · {n_imported} importados")
    with head_cols[1]:
        if st.button("🧹 Limpiar no importados", key="radar_clear"):
            n = repo.clear_non_imported()
            st.toast(f"🧹 {n} candidatos eliminados")
            st.rerun()

    for c in candidates:
        _render_candidate_card(c)


def _render_candidate_card(c) -> None:
    score = c.score
    badge = "🟢" if score.total >= 70 else ("🟡" if score.total >= 45 else "🟠")
    ads_emoji = {"fuerte": "📢🔥", "media": "📢", "baja": "🔇", "desconocida": "❔"}.get(
        c.ads.verdict, "❔")
    boosted_badge = (
        f"🚀 GMV Max probable ({c.ads.gmv_max_likelihood:.0f}/100)"
        if c.ads.probable_boosted
        else (f"{ads_emoji} GMV Max {c.ads.verdict} ({c.ads.gmv_max_likelihood:.0f}/100)"
              if c.ads.checked else "❔ ADS sin comprobar")
    )

    with st.container(border=True):
        cols = st.columns([1, 4, 2])
        with cols[0]:
            if c.cover_url:
                st.image(c.cover_url, use_container_width=True)
            st.markdown(f"### {badge} {score.total:.0f}")
        with cols[1]:
            title = c.name or f"Producto {c.product_id}"
            flag = REGION_FLAGS.get(c.region, "")
            if c.tiktok_url:
                st.markdown(f"{flag} **[{title}]({c.tiktok_url})**")
            else:
                st.markdown(f"{flag} **{title}**")
            st.caption(
                f"👥 {c.influencer_count} creadores · 💶 €{(c.gmv_30d or c.gmv):,.0f} GMV · "
                f"🎬 {c.video_count} vídeos · 💰 {c.commission_pct:.0f}%"
            )
            if c.ads.probable_boosted:
                st.markdown(f"**{boosted_badge}**")
            else:
                st.caption(boosted_badge)
            if c.ads.reasons:
                st.caption("📢 " + " · ".join(c.ads.reasons[:3]))
            # Desglose del score
            st.progress(min(1.0, score.total / 100.0))
        with cols[2]:
            if c.imported:
                st.success("✅ Importado", icon="📦")
                if st.button("📦 Pack completo", key=f"pack_{c.product_id}",
                             help="Fotos + research + estilos de vídeo + carruseles + prompts en la carpeta."):
                    _build_single_pack(c)
            else:
                if st.button("📥 Importar", key=f"imp_{c.product_id}", type="primary"):
                    with st.spinner("Importando + descargando cover…"):
                        try:
                            discovery_service.import_candidate(c)
                            st.toast(f"✅ '{c.name}' importado")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")
            with st.popover("📊 Score"):
                st.write({
                    "ADS injection": score.ads_injection,
                    "Pocos creadores": score.low_competition,
                    "Demanda": score.demand,
                    "Momentum": score.momentum,
                    "Comisión": score.commission,
                })
                if c.ads.checked:
                    st.caption(
                        f"Vídeos analizados: {c.ads.videos_analyzed} · "
                        f"ad-like: {c.ads.ad_like_videos} · "
                        f"ad-like con ventas: {c.ads.ad_like_with_sales}"
                    )


def _build_single_pack(candidate) -> None:
    """Construye el pack completo de un candidato ya importado."""
    from src.tiktok_shop.services.creation_pack import PackOptions, build_pack
    product = ProductRepo().get(candidate.imported_product_id or "")
    if product is None:
        st.error("Producto importado no encontrado.")
        return
    with st.status(f"📦 Pack de '{product.name}'…", expanded=True) as status:
        try:
            res = build_pack(
                product, options=PackOptions(), discovered=candidate,
                log_callback=status.write,
            )
            status.update(
                label=f"✅ Pack listo · 🎠 {res.carousels_generated} · 🎥 {res.presets_generated} · 🖼️ {res.photos_downloaded}",
                state="complete", expanded=False,
            )
            st.toast(f"📦 Carpeta lista en {res.folder}")
        except Exception as e:
            status.update(label=f"❌ Error: {e}", state="error")
            st.exception(e)


# ═════════════════════════════════════════════════════════════════════
# 🗓️ Plan 7 días
# ═════════════════════════════════════════════════════════════════════
def _render_week_plan() -> None:
    st.caption(
        "Coge los mejores candidatos del Radar y deja **todo listo para crear**: "
        "importa, descarga fotos, investiga vídeos ganadores, genera estilos de "
        "vídeo + carruseles + prompts, y escribe una carpeta por producto. "
        "Tú solo creas."
    )

    repo = DiscoveryRepo()
    with st.spinner("📡 Cargando candidatos…"):
        pool = [c for c in repo.list_all() if not c.imported]
    if not pool:
        st.info(
            "No hay candidatos sin importar. Ve a **Descubrir** y haz un scan primero."
        )
        return
    st.markdown(f"**{len(pool)} candidatos disponibles** (sin importar).")

    col1, col2, col3 = st.columns(3)
    with col1:
        n_products = st.number_input(
            "Productos a preparar", 1, min(30, len(pool)),
            min(7, len(pool)), key="plan_nprod",
        )
        days = st.number_input("Repartir en N días", 1, 14, 7, key="plan_days")
    with col2:
        do_research = st.checkbox(
            "🎬 Investigar vídeos ganadores", value=True, key="plan_research",
            help="Analiza los TikToks que más venden del producto (~$0.17 c/u). "
                 "Requiere Apify configurado para análisis de vídeo.",
        )
        do_presets = st.checkbox(
            "🎥 Generar estilos de vídeo", value=True, key="plan_presets",
        )
    with col3:
        n_carousels = st.number_input("Carruseles por producto", 0, 8, 3, key="plan_ncar")
        n_photos = st.number_input("Fotos a descargar", 0, 12, 6, key="plan_nphotos")

    # Estimación de coste grosso modo (Gemini + research)
    est = float(n_products) * (
        (0.17 if do_research else 0.0) + (0.03 if do_presets else 0.0)
        + n_carousels * 0.01 + 0.02
    )
    st.caption(f"💸 Coste estimado total: ~${est:.2f} (Gemini + research). El vídeo/imagen final lo generas tú aparte.")

    if st.button("🚀 Preparar plan", type="primary", key="plan_run"):
        from src.tiktok_shop.services.creation_pack import PackOptions, plan_week

        opts = PackOptions(
            download_photos=n_photos > 0,
            photos_to_download=int(n_photos),
            research=do_research,
            generate_video_presets=do_presets,
            n_carousels=int(n_carousels),
        )
        with st.status("🛠️ Preparando plan…", expanded=True) as status:
            def _log(msg: str) -> None:
                status.write(msg)
            try:
                results = plan_week(
                    n_products=int(n_products), options=opts,
                    days=int(days), log_callback=_log,
                )
                ok = sum(1 for r in results if r.slug)
                status.update(
                    label=f"✅ {ok}/{len(results)} productos preparados",
                    state="complete", expanded=False,
                )
                st.session_state["plan_results"] = [
                    {"name": r.name, "slug": r.slug, "folder": r.folder,
                     "carousels": r.carousels_generated, "presets": r.presets_generated,
                     "photos": r.photos_downloaded, "warnings": r.warnings}
                    for r in results
                ]
            except Exception as e:
                status.update(label=f"❌ Error: {e}", state="error")
                st.exception(e)

    results = st.session_state.get("plan_results")
    if results:
        st.divider()
        st.markdown("### 📂 Productos preparados")
        from src.tiktok_shop.config import resolve_shop_root
        st.caption(f"Carpetas en `{resolve_shop_root()}/_products/` · plan en `_plans/`")
        for r in results:
            warn = f" · ⚠️ {len(r['warnings'])} avisos" if r["warnings"] else ""
            st.markdown(
                f"- **{r['name']}** (`{r['slug']}`) — "
                f"🎠 {r['carousels']} · 🎥 {r['presets']} · 🖼️ {r['photos']}{warn}"
            )
            if r["warnings"]:
                with st.expander("ver avisos"):
                    for w in r["warnings"]:
                        st.caption(f"⚠️ {w}")


# ═════════════════════════════════════════════════════════════════════
# 📅 Calendario
# ═════════════════════════════════════════════════════════════════════
def _render_calendar() -> None:
    from src.tiktok_shop.repos import PlanRepo

    repo = PlanRepo()
    with st.spinner("📅 Cargando calendario…"):
        plans = repo.list_all()
        current = repo.get_current()

    if not plans:
        st.info(
            "Aún no hay ningún plan. Genera uno en **🗓️ Plan 7 días** y aquí "
            "verás el calendario de qué producto probar cada día."
        )
        return

    # Selector de plan (por si hay varios)
    labels = {f"{p.label} · {len(p.entries)} productos": p.id for p in plans}
    default_idx = 0
    if current is not None:
        for i, p in enumerate(plans):
            if p.id == current.id:
                default_idx = i
                break
    sel = st.selectbox(
        "Plan", list(labels.keys()), index=default_idx, key="cal_plan_sel",
    )
    plan = repo.get(labels[sel])
    if plan is None:
        st.error("Plan no encontrado.")
        return

    done, total = plan.progress()
    cols = st.columns([3, 1])
    with cols[0]:
        st.markdown(f"### {plan.label}")
        st.progress(done / total if total else 0.0,
                    text=f"{done}/{total} productos probados")
    with cols[1]:
        if st.button("🗑️ Borrar plan", key="cal_del_plan"):
            repo.delete(plan.id)
            st.toast("Plan borrado")
            st.rerun()

    by_day = plan.by_day()
    verdict_emoji = {"fuerte": "📢🔥", "media": "📢", "baja": "🔇", "desconocida": "❔"}

    for day in range(1, plan.days + 1):
        entries = by_day.get(day, [])
        st.markdown(f"#### 📅 Día {day}")
        if not entries:
            st.caption("— libre —")
            continue
        for e in entries:
            with st.container(border=True):
                c1, c2 = st.columns([5, 1])
                with c1:
                    ads = verdict_emoji.get(e.ads_verdict, "")
                    badge = "✅ " if e.tested else ""
                    st.markdown(f"{badge}**{e.name}**")
                    st.caption(
                        f"⭐ score {e.score:.0f} · {ads} ADS {e.ads_verdict} · "
                        f"🎠 {e.carousels} carruseles · 🎥 {e.presets} estilos · `{e.slug}`"
                    )
                with c2:
                    new_val = st.checkbox(
                        "Probado", value=e.tested, key=f"cal_tested_{plan.id}_{e.slug}_{day}",
                    )
                    if new_val != e.tested:
                        e.tested = new_val
                        repo.save(plan, make_current=False)
                        st.rerun()


# ═════════════════════════════════════════════════════════════════════
# 🎠 Carruseles
# ═════════════════════════════════════════════════════════════════════
def _render_carousels() -> None:
    st.caption(
        "Genera el guion de un carrusel (slides + texto + caption) listo para "
        "pegar en Nano Banana 2 y subir. Formato barato de alto volumen (~10/día)."
    )
    prod_repo = ProductRepo()
    with st.spinner("📦 Cargando productos…"):
        products = [p for p in prod_repo.list_all() if not p.deleted]

    if not products:
        st.info("No hay productos. Importa ganadores desde **Descubrir** primero.")
        return

    labels = {f"{p.name} ({p.slug})": p.id for p in products}
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        sel = st.selectbox("Producto", list(labels.keys()), key="carousel_prod")
    with col2:
        n_slides = st.number_input("Slides", 3, 10, 6, key="carousel_slides")
    with col3:
        angle = st.text_input("Ángulo (opcional)", value="", key="carousel_angle")

    if st.button("🎠 Generar carrusel", type="primary", key="carousel_gen"):
        product = prod_repo.get(labels[sel])
        if product is None:
            st.error("Producto no encontrado.")
            return
        with st.spinner("🤖 Gemini escribiendo el carrusel…"):
            try:
                data = generate_carousel(
                    product, n_slides=int(n_slides), angle=angle.strip(),
                )
                st.session_state["carousel_last"] = data
            except Exception as e:
                st.error(f"Error: {e}")
                return

    data = st.session_state.get("carousel_last")
    if not data:
        return

    st.divider()
    st.markdown(f"**Concepto:** {data.get('concept', '—')}")
    st.markdown("**Caption (copiar):**")
    st.code(data.get("hook_caption", ""), language="text")

    slides = data.get("slides", [])
    st.markdown(f"### 🖼️ {len(slides)} slides")
    for s in slides:
        with st.expander(
            f"Slide {s.get('slide_number', '?')} · {s.get('role', '')} — "
            f"{s.get('on_screen_text', '')}",
            expanded=False,
        ):
            st.markdown(f"**Texto en pantalla:** {s.get('on_screen_text', '')}")
            st.markdown("**Prompt de imagen (Nano Banana 2):**")
            st.code(s.get("image_prompt", ""), language="text")

    # Todos los prompts juntos para copiar de una
    all_prompts = "\n\n".join(
        f"[Slide {s.get('slide_number')}] {s.get('image_prompt', '')}"
        for s in slides
    )
    with st.expander("📋 Todos los prompts de imagen juntos"):
        st.code(all_prompts, language="text")

    if data.get("image_style_guide"):
        st.caption(f"🎨 {data['image_style_guide']}")
    if data.get("human_presence_note"):
        st.caption(f"🙋 {data['human_presence_note']}")

    with st.expander("🔧 JSON crudo"):
        st.code(json.dumps(data, ensure_ascii=False, indent=2), language="json")
