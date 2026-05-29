"""Investigación profunda del producto: Gemini web search + Apify
TikTok scraping + Gemini video analysis → `ResearchContext`.

Flujo del botón "Reanalizar profundamente":

  1. Gemini con Google Search grounding busca reviews del producto en
     Amazon/AliExpress/marca → extrae pains, benefits, objections.

  2. Apify busca el producto en TikTok → devuelve top 10 vídeos virales
     por views/likes con metadata + URLs MP4 descargables.

  3. Para los top 5 vídeos: descarga MP4 → Gemini 2.5 Pro analiza
     vídeo completo (visual + audio) → extrae hook, structure, patterns.

  4. Apify scrape comentarios del top 1-2 vídeos → objeciones reales.

  5. Gemini agrega TODO en un ResearchContext estructurado.

  6. Lo guarda en `product.research_context`. Los prompts directores
     (scripted, music, ab_variants) leen este contexto al generar
     guiones → mejor calidad sin invención.

Coste típico por reanálisis completo:
  - Gemini grounded search: ~$0.05
  - Apify TikTok search:    ~$0.005
  - Gemini video analysis × 5: ~$0.10
  - Agregación final:       ~$0.02
  → TOTAL ~$0.17 por producto, una vez.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from src.tiktok_shop.api import apify_cloud, gemini
from src.tiktok_shop.models import Product
from src.tiktok_shop.models.product import (
    ResearchContext, TrendingSound, ViralVideoSummary,
)


LogCallback = Callable[[str], None]


def _noop(_msg: str) -> None: ...


def deep_research_product(
    product: Product,
    *,
    max_videos_to_analyze: int = 5,
    max_tiktok_search_results: int = 10,
    extra_markets: list[str] | None = None,
    log_callback: LogCallback = _noop,
) -> ResearchContext:
    """Investiga el producto en web + TikTok y devuelve ResearchContext
    relleno. No persiste — el caller decide cuándo guardar.

    `extra_markets`: países extra (ej. ["US","GB"]) que se buscan ADEMÁS
    del mercado nativo cuando éste tiene pocos vídeos virales. Permite
    sacar fórmulas ganadoras de mercados grandes (US/UK) y adaptarlas a
    España. Si None, default ["US","GB"]."""
    if extra_markets is None:
        extra_markets = ["US", "GB"]
    started = time.time()
    cost_estimate = 0.0
    log_callback(f"🔬 Iniciando investigación profunda de '{product.name}'…")

    # ════════════════════════════════════════════════════════════════
    # FASE 1: Gemini grounded search — reviews y nicho
    # ════════════════════════════════════════════════════════════════
    log_callback("📚 Fase 1/3: buscando reviews + nicho con Gemini Web Search…")
    research_text = _gemini_web_research(product, log_callback=log_callback)
    structured = _parse_research_text(research_text)
    cost_estimate += 0.06

    customer_pains = structured.get("pains", [])
    customer_benefits = structured.get("benefits", [])
    objections = structured.get("objections", [])
    niche_keywords = structured.get("keywords", [])
    niche_inspiration = structured.get("inspiration", [])
    competitive_diff = structured.get("differentiators", [])

    log_callback(
        f"  ✓ {len(customer_pains)} pains · {len(customer_benefits)} benefits · "
        f"{len(objections)} objections · {len(niche_keywords)} keywords"
    )

    # ════════════════════════════════════════════════════════════════
    # FASE 2: Apify TikTok search → top vídeos virales
    # ════════════════════════════════════════════════════════════════
    top_videos: list[ViralVideoSummary] = []
    viral_patterns: list[str] = []
    proven_hooks: list[str] = []
    trending_sounds: list[TrendingSound] = []
    audience_questions: list[str] = []
    comments_count = 0

    if apify_cloud.apify_is_configured():
        # TikTok no encuentra resultados con queries largas tipo
        # "UMAY cinta de correr doméstica 2,5HP, protege tus rodillas, ...".
        # Acortamos a una query searchable: brand + primeras palabras clave.
        # Quitamos comas y dejamos máx 8 palabras significativas.
        raw = (product.name or "").replace(",", " ").replace(".", " ")
        words = [w for w in raw.split() if len(w) > 2][:8]
        if product.brand and product.brand.lower() not in raw.lower():
            words = [product.brand] + words[:7]
        tiktok_query = " ".join(words) or product.name
        home_country = _home_country(product.language)
        log_callback(
            f"🎬 Fase 2/4: buscando top {max_tiktok_search_results} vídeos "
            f"en TikTok [{home_country}] con query: '{tiktok_query}'…"
        )
        try:
            apify_results, apify_queries = _multi_market_search(
                tiktok_query,
                home_country=home_country,
                extra_markets=extra_markets,
                limit=max_tiktok_search_results,
                min_home_organic=max_videos_to_analyze,
                log_callback=log_callback,
            )

            # Cost tracking (real — el job activo lo acumula)
            try:
                from src.cost_tracking import record_apify_cloud
                record_apify_cloud(
                    items_count=len(apify_results),
                    queries_count=apify_queries,
                    detail=f"tiktok search '{product.name}' x{apify_queries} markets",
                )
            except Exception:
                pass

            # Agregamos sonidos trending de TODOS los resultados (no solo
            # los analizados) — más muestra = mejor señal de qué audio
            # está reventando en el nicho.
            trending_sounds = _aggregate_trending_sounds(apify_results)
            if trending_sounds:
                log_callback(
                    f"  🎵 {len(trending_sounds)} sonidos trending detectados "
                    f"(top: {trending_sounds[0].title or trending_sounds[0].music_id})"
                )

            # Split paid vs organic por engagement rate. Como TikTok no
            # expone ventas por vídeo (sobre todo en ES), usamos el ratio
            # de interacción como proxy: ads = muchas views/poco engagement,
            # orgánico = engagement alto. Analizamos ambos buckets para
            # extraer las DOS fórmulas por separado.
            paid_items, organic_items = _split_paid_organic(
                apify_results, n_each=max_videos_to_analyze,
            )
            log_callback(
                f"  ✓ {len(apify_results)} encontrados → "
                f"{len(organic_items)} orgánicos + {len(paid_items)} pagados "
                f"para analizar con Gemini"
            )

            org_v, org_p, org_h = ([], [], [])
            paid_v, paid_p, paid_h = ([], [], [])
            if organic_items:
                org_v, org_p, org_h = _analyze_top_videos(
                    organic_items, product, log_callback=log_callback,
                    traffic_type="organic",
                )
            if paid_items:
                paid_v, paid_p, paid_h = _analyze_top_videos(
                    paid_items, product, log_callback=log_callback,
                    traffic_type="paid",
                )
            # Orgánicos primero (mejor señal de fórmula que convierte).
            top_videos = org_v + paid_v
            # Dedup de patrones/hooks preservando orden (orgánico primero).
            def _dedup(seq: list[str]) -> list[str]:
                seen: set[str] = set()
                out: list[str] = []
                for x in seq:
                    k = x.strip().lower()
                    if k and k not in seen:
                        seen.add(k)
                        out.append(x)
                return out
            viral_patterns = _dedup(org_p + paid_p)
            proven_hooks = _dedup(org_h + paid_h)

            # ════════════════════════════════════════════════════════════
            # FASE 3: comentarios de los top vídeos → preguntas/objeciones
            # reales del público (más afiladas que las reviews de Amazon).
            # ════════════════════════════════════════════════════════════
            top_urls = [v.url for v in top_videos[:3] if v.url]
            if top_urls:
                log_callback(
                    f"💬 Fase 3/4: comentarios de los top {len(top_urls)} vídeos…"
                )
                try:
                    comments = apify_cloud.scrape_tiktok_comments(
                        top_urls,
                        max_comments_per_video=30,
                        log_callback=log_callback,
                    )
                    comments_count = len(comments)
                    try:
                        from src.cost_tracking import record_apify_cloud
                        record_apify_cloud(
                            items_count=comments_count,
                            queries_count=len(top_urls),
                            detail=f"comments '{product.name}'",
                        )
                    except Exception:
                        pass
                    if comments:
                        extra_obj, audience_questions = _analyze_comments(
                            comments, product, log_callback=log_callback,
                        )
                        # Fusionar objeciones de comentarios con las de reviews
                        # (sin duplicar por texto normalizado).
                        seen = {o.strip().lower() for o in objections}
                        for o in extra_obj:
                            if o.strip().lower() not in seen:
                                objections.append(o)
                                seen.add(o.strip().lower())
                except Exception as e:
                    log_callback(f"  ⚠️ Comentarios fallaron ({e}) — sigo")
        except apify_cloud.ApifyError as e:
            log_callback(f"⚠️ Apify falló ({e}) — sigo sin patrones virales")
        except Exception as e:
            log_callback(f"⚠️ Apify error inesperado ({e}) — sigo")
    else:
        log_callback(
            "⚠️ Apify no configurado (APIFY_API_TOKEN). Saltamos Fase 2 — "
            "el research_context tendrá solo info de reviews."
        )

    # ════════════════════════════════════════════════════════════════
    # FASE 4: ensamblar ResearchContext
    # ════════════════════════════════════════════════════════════════
    elapsed = time.time() - started

    # Coste REAL del job activo (Gemini + Apify trackeados). Si no hay
    # tracker (call directa en test), cae al estimado heurístico.
    real_cost = cost_estimate
    try:
        from src.cost_tracking import get_active
        job = get_active()
        if job is not None and job.total_usd > 0:
            real_cost = job.total_usd
    except Exception:
        pass

    log_callback(
        f"✅ Investigación completada en {elapsed:.1f}s · "
        f"coste real ~${real_cost:.3f}"
    )

    return ResearchContext(
        customer_pains=customer_pains[:15],
        customer_benefits=customer_benefits[:15],
        objections=objections[:15],
        viral_patterns=viral_patterns[:10],
        top_videos=top_videos,
        niche_keywords=niche_keywords[:20],
        niche_inspiration=niche_inspiration[:10],
        competitive_diff=competitive_diff[:10],
        proven_hooks=proven_hooks[:15],
        audience_questions=audience_questions[:15],
        trending_sounds=trending_sounds[:8],
        analyzed_at=datetime.now(timezone.utc).isoformat(),
        sources_reviews_count=len(customer_pains) + len(customer_benefits),
        sources_videos_count=len(top_videos),
        sources_comments_count=comments_count,
        research_cost_usd=round(real_cost, 4),
    )


# ═════════════════════════════════════════════════════════════════════
# Fase 1: Gemini grounded web search
# ═════════════════════════════════════════════════════════════════════
def _gemini_web_research(
    product: Product, *, log_callback: LogCallback,
) -> str:
    """Llama a Gemini 2.5 Pro con Google Search grounding pidiendo que
    investigue reviews + nicho. Devuelve texto plano estructurado."""
    system_prompt = """You are a TikTok Shop conversion research expert. Your job is to research a product on the web and extract structured insights that will be used to craft viral video scripts.

Use Google Search to find:
1. Real customer reviews on Amazon, AliExpress, and brand websites
2. TikTok comments and discussions about this product or similar products
3. Reddit/forums where the niche audience hangs out
4. Competitor products and their positioning

Output STRICTLY in this Markdown structure (no preamble, no explanations):

## PAINS
- <one specific pain customers mention, verbatim feeling, in Spanish if product is for ES market>
- ...

## BENEFITS
- <specific benefit mentioned in real reviews, in Spanish>
- ...

## OBJECTIONS
- <real concern/doubt people have before buying>
- ...

## KEYWORDS
- <SEO keyword used in the niche>
- ...

## INSPIRATION
- <content angle or trend in the niche>
- ...

## DIFFERENTIATORS
- <what this product does better than competitors>
- ...

Be specific. Use real customer language. Avoid generic marketing speak."""

    # Datos del producto que pasamos a Gemini para que investigue mejor.
    # Cuanta más info concreta tenga (URL TikTok Shop, precio, selling
    # points), mejor entiende el contexto y encuentra reviews relevantes.
    tts = getattr(product, "tiktok_shop", None)
    tiktok_url = getattr(tts, "product_url", None) if tts else None
    price_eur = getattr(tts, "price_eur", None) if tts else None
    selling_points = getattr(product, "selling_points", []) or []

    user_prompt = f"""Producto: {product.name}
Marca: {product.brand or '—'}
Categoría: {product.category}
Subcategoría: {product.subcategory or '—'}
Precio: {f'{price_eur} €' if price_eur else '—'}
URL TikTok Shop: {tiktok_url or '—'}
Audiencia: {', '.join(product.target_audience) if product.target_audience else '—'}
Key features actuales: {', '.join(product.key_features) if product.key_features else '—'}
Selling points: {', '.join(selling_points) if selling_points else '—'}
Idioma target: {product.language}

Investiga este producto en la web y devuelve los listados estructurados.
Usa la URL de TikTok Shop si la tienes para ver fotos del producto real y
así buscar mejor. Si el producto es para mercado español (es_*), las
pains/benefits/objections deben estar en español natural (no traducciones
literales del inglés)."""

    log_callback("  🌐 Gemini buscando en Amazon/AliExpress/foros con Web Search…")
    try:
        text = gemini.generate_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model="gemini-2.5-pro",        # Pro para mejor razonamiento + search
            enable_web_search=True,
            expect_json=False,             # incompatible con tools
            temperature=0.4,
        )
        return text
    except Exception as e:
        log_callback(f"  ⚠️ Gemini search falló ({e}). Intentando sin search…")
        # Fallback sin grounding: aún devuelve algo útil basado en
        # conocimiento del modelo + photos del producto.
        try:
            text = gemini.generate_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt + "\n\n(Si no tienes acceso a búsqueda web, infiere de tu conocimiento general sobre este tipo de productos.)",
                model="gemini-2.5-flash",
                enable_web_search=False,
                expect_json=False,
                temperature=0.5,
            )
            return text
        except Exception as e2:
            log_callback(f"  ❌ Gemini fallback también falló: {e2}")
            return ""


def _parse_research_text(text: str) -> dict[str, list[str]]:
    """Parsea el output Markdown de _gemini_web_research a listas
    estructuradas. Tolerante a variaciones de formato."""
    out: dict[str, list[str]] = {
        "pains": [], "benefits": [], "objections": [],
        "keywords": [], "inspiration": [], "differentiators": [],
    }
    section_map = {
        "PAINS": "pains", "DOLORES": "pains",
        "BENEFITS": "benefits", "BENEFICIOS": "benefits",
        "OBJECTIONS": "objections", "OBJECIONES": "objections",
        "KEYWORDS": "keywords", "PALABRAS CLAVE": "keywords",
        "INSPIRATION": "inspiration", "INSPIRACIÓN": "inspiration", "INSPIRACION": "inspiration",
        "DIFFERENTIATORS": "differentiators", "DIFERENCIADORES": "differentiators",
    }
    current_key: str | None = None
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        # Heading "## X" or "# X" or "**X**"
        if s.startswith("#"):
            heading = s.lstrip("#").strip().upper()
            current_key = section_map.get(heading)
            continue
        if s.startswith("**") and s.endswith("**"):
            heading = s.strip("*").upper()
            current_key = section_map.get(heading)
            continue
        # Bullet "- ..." or "* ..."
        if current_key and (s.startswith("-") or s.startswith("*")):
            item = s.lstrip("-* ").strip()
            if item and len(item) > 2:
                out[current_key].append(item[:200])  # cap length
    return out


# ═════════════════════════════════════════════════════════════════════
# Fase 2: Análisis de vídeos TikTok con Gemini
# ═════════════════════════════════════════════════════════════════════
def _analyze_top_videos(
    apify_items: list[dict[str, Any]],
    product: Product,
    *, log_callback: LogCallback,
    traffic_type: str = "",
) -> tuple[list[ViralVideoSummary], list[str], list[str]]:
    """Descarga los top N vídeos y los analiza con Gemini 2.5 Pro.
    Devuelve (resúmenes, patrones agregados, hooks probados).

    `traffic_type` ("organic"/"paid") se etiqueta en cada summary y se
    pasa a Gemini como contexto para que contraste las dos fórmulas."""
    summaries: list[ViralVideoSummary] = []
    tmp_dir = tempfile.mkdtemp(prefix="research_videos_")
    video_paths: list[str] = []

    # Índice del summary que sí pudimos descargar — usado para mapear
    # per_video del análisis Gemini de vuelta al summary correcto.
    downloaded_indexes: list[int] = []
    try:
        # SIEMPRE creamos el summary con metadata Apify (URL, views, likes)
        # aunque no podamos descargar el MP4 — la UI necesita las URLs.
        for idx, item in enumerate(apify_items):
            meta = apify_cloud.extract_video_metadata(item)
            if not meta.get("url"):
                continue  # sin URL TikTok no sirve ni para UI
            summary = ViralVideoSummary(
                url=meta["url"],
                view_count=meta["view_count"],
                like_count=meta["like_count"],
                comment_count=meta["comment_count"],
                duration_s=meta["duration_s"],
                traffic_type=traffic_type,
                country=str(item.get("_market") or ""),
                music_id=meta.get("music_id", ""),
                music_title=meta.get("music_name", ""),
                music_author=meta.get("music_author", ""),
                music_is_original=bool(meta.get("music_is_original", False)),
                music_url=meta.get("music_url", ""),
            )
            summaries.append(summary)
            summary_idx = len(summaries) - 1

            # Intentar descarga para análisis Gemini (opcional)
            if not meta.get("mp4_url"):
                log_callback(f"  📋 Vídeo {idx+1} sin mp4_url — solo metadata")
                continue
            try:
                dest = os.path.join(tmp_dir, f"viral_{idx}.mp4")
                apify_cloud.download_tiktok_video(meta["mp4_url"], dest)
                video_paths.append(dest)
                downloaded_indexes.append(summary_idx)
                log_callback(
                    f"  ⬇️ Vídeo {idx+1} descargado · "
                    f"{meta['view_count']:,} views · {meta['duration_s']:.0f}s"
                )
            except Exception as e:
                log_callback(f"  ⚠️ Vídeo {idx+1} falló descarga: {e}")
                continue

        if not video_paths:
            log_callback(
                f"  ⚠️ No se pudo descargar ningún vídeo — guardando "
                f"{len(summaries)} URLs sin análisis Gemini"
            )
            return summaries, [], []

        # Análisis BATCH con Gemini (todos los vídeos en una sola llamada)
        label = {"organic": "ORGÁNICOS (engagement alto)",
                 "paid": "de ALCANCE PAGADO (views altas, engagement bajo)"}.get(
            traffic_type, "")
        log_callback(
            f"  🧠 Gemini 2.5 Pro analizando {len(video_paths)} vídeos "
            f"{label or 'juntos'}…"
        )
        patterns_text = _gemini_batch_video_analysis(
            video_paths, product, log_callback=log_callback,
            traffic_label=label,
        )
        analysis = _parse_video_analysis(patterns_text)

        # Aplicar per-video data al summary correcto (los analizados son
        # un subset de summaries — mapeo vía downloaded_indexes).
        per_video = analysis.get("per_video", [])
        for i, vid_data in enumerate(per_video):
            if i >= len(downloaded_indexes) or not isinstance(vid_data, dict):
                continue
            target = downloaded_indexes[i]
            if target >= len(summaries):
                continue
            summaries[target].hook_text = str(vid_data.get("hook_text", ""))[:200]
            summaries[target].hook_category = str(vid_data.get("hook_category", ""))[:50]
            summaries[target].script_structure = str(vid_data.get("structure", ""))[:300]
            summaries[target].visual_patterns = [
                str(v)[:120] for v in (vid_data.get("visual_patterns") or [])
            ][:5]
            summaries[target].cta_used = str(vid_data.get("cta", ""))[:120]
            summaries[target].music_mood = str(vid_data.get("music_mood", ""))[:50]

        viral_patterns = [
            str(p)[:200] for p in (analysis.get("aggregated_patterns") or [])
        ][:10]
        proven_hooks = [
            str(h)[:200] for h in (analysis.get("proven_hooks") or [])
        ][:15]
        return summaries, viral_patterns, proven_hooks
    finally:
        # Cleanup temp videos
        for vp in video_paths:
            try:
                Path(vp).unlink(missing_ok=True)
            except OSError:
                pass
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass


def _gemini_batch_video_analysis(
    video_paths: list[str], product: Product,
    *, log_callback: LogCallback, traffic_label: str = "",
) -> str:
    """Manda los N vídeos a Gemini en una sola llamada pidiendo análisis
    individual + patrones agregados."""
    system_prompt = """Eres un experto en TikTok Shop viral marketing. Te paso N vídeos virales del MISMO producto. Tu tarea: analizar cada uno individualmente Y extraer patrones agregados que se repiten.

DEVUELVE JSON con esta estructura exacta:

{
  "per_video": [
    {
      "hook_text": "el texto on-screen literal del hook (segundos 0-3)",
      "hook_category": "curiosity | problem_solution | social_proof | shocking_claim | ...",
      "structure": "0-3s: hook → 3-8s: problema → 8-12s: producto → 12-15s: CTA",
      "visual_patterns": ["primer plano producto", "transición zoom", "split-screen antes/después"],
      "cta": "el CTA usado literal",
      "music_mood": "upbeat_energetic | calm_sensorial | trap_aggressive | ..."
    },
    ...
  ],
  "aggregated_patterns": [
    "patrón visible en >=3 de los vídeos: ej 'todos abren con primer plano del producto + texto amarillo'",
    ...
  ],
  "proven_hooks": [
    "hook literal que aparece en alguno y se podría adaptar al user (en español si es ES)",
    ...
  ]
}

No inventes. Si no ves un patrón claro, deja la lista vacía. Sé específico — describe planos, transiciones, timing, NO uses adjetivos vagos."""

    context_line = (
        f"\n- IMPORTANTE: estos vídeos son {traffic_label}. "
        "Analiza qué fórmula usan específicamente para este tipo de tráfico."
        if traffic_label else ""
    )
    user_prompt = f"""Producto del que son estos vídeos:
- Nombre: {product.name}
- Categoría: {product.category}
- Idioma target: {product.language}{context_line}
- OJO: algunos vídeos pueden ser de OTROS MERCADOS (US/UK, en inglés).
  Extrae su FÓRMULA (estructura, planos, ritmo, tipo de hook, CTA) que es
  universal, pero los `proven_hooks` ADÁPTALOS al español natural de
  España (NO traduzcas literal — reescribe como lo diría un español).

Analiza los {len(video_paths)} vídeos en orden y devuelve el JSON estructurado."""

    try:
        text = gemini.generate_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model="gemini-2.5-pro",
            videos=video_paths,
            expect_json=True,
            temperature=0.3,
        )
        return text
    except Exception as e:
        log_callback(f"  ⚠️ Gemini video analysis falló: {e}")
        return "{}"


def _parse_video_analysis(text: str) -> dict[str, Any]:
    """Parsea el JSON del análisis de vídeos. Tolerante a errores."""
    if not text or not text.strip():
        return {}
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return {}


# ═════════════════════════════════════════════════════════════════════
# Búsqueda multi-mercado (España + US/UK como fallback de nicho pequeño)
# ═════════════════════════════════════════════════════════════════════
_LANG_TO_COUNTRY = {
    "es_ES": "ES", "es_LATAM": "MX", "en_US": "US", "en_UK": "GB",
    "pt_BR": "BR", "fr_FR": "FR",
}


def _home_country(language: str | None) -> str:
    return _LANG_TO_COUNTRY.get(language or "es_ES", "ES")


def _count_usable_organic(items: list[dict[str, Any]], min_eng: float = 2.0) -> int:
    """Cuántos vídeos del set tienen engagement orgánico decente."""
    n = 0
    for it in items:
        m = apify_cloud.extract_video_metadata(it)
        v = int(m.get("view_count") or 0)
        if v <= 0:
            continue
        eng = (
            int(m.get("like_count") or 0)
            + int(m.get("comment_count") or 0)
            + int(m.get("share_count") or 0)
        )
        if eng / v * 100.0 >= min_eng:
            n += 1
    return n


def _multi_market_search(
    query: str,
    *,
    home_country: str,
    extra_markets: list[str],
    limit: int,
    min_home_organic: int,
    log_callback: LogCallback,
) -> tuple[list[dict[str, Any]], int]:
    """Busca en el mercado nativo y, si éste tiene POCOS vídeos virales
    orgánicos, amplía a los mercados extra (US/UK) para sacar fórmulas
    ganadoras de mercados grandes y adaptarlas a España.

    Cada item se etiqueta con `_market` (país). Dedup por id/url.
    Devuelve (items_combinados, n_queries_lanzadas) para el cost tracking."""
    def _tag(items: list[dict[str, Any]], market: str) -> list[dict[str, Any]]:
        for it in items:
            it["_market"] = market
        return items

    seen: set[str] = set()
    combined: list[dict[str, Any]] = []

    def _add(items: list[dict[str, Any]]) -> None:
        for it in items:
            key = str(it.get("id") or it.get("webVideoUrl") or "")
            if key and key not in seen:
                seen.add(key)
                combined.append(it)

    queries = 0
    # 1) Mercado nativo
    home = _tag(apify_cloud.search_tiktok_videos(
        query=query, limit=limit, sort_by="popular",
        country=home_country, log_callback=log_callback,
    ), home_country)
    queries += 1
    _add(home)

    # 2) ¿Nicho pequeño en casa? Amplía a mercados grandes.
    home_organic = _count_usable_organic(home)
    if home_organic < min_home_organic and extra_markets:
        log_callback(
            f"  🌍 Solo {home_organic} vídeos orgánicos en {home_country} — "
            f"amplío a {', '.join(extra_markets)} para sacar fórmulas top y "
            f"adaptarlas a España"
        )
        for market in extra_markets:
            if market == home_country:
                continue
            try:
                extra = _tag(apify_cloud.search_tiktok_videos(
                    query=query, limit=limit, sort_by="popular",
                    country=market, log_callback=log_callback,
                ), market)
                queries += 1
                _add(extra)
            except Exception as e:
                log_callback(f"  ⚠️ Búsqueda {market} falló ({e}) — sigo")
    else:
        log_callback(
            f"  ✓ {home_organic} vídeos orgánicos en {home_country} — "
            f"suficiente, no amplío a otros mercados"
        )

    return combined, queries


# ═════════════════════════════════════════════════════════════════════
# Split paid (ads) vs organic por engagement rate
# ═════════════════════════════════════════════════════════════════════
def _split_paid_organic(
    apify_results: list[dict[str, Any]],
    *,
    n_each: int = 5,
    organic_min_eng: float = 2.0,   # % — engagement alto = resonó orgánico
    paid_max_eng: float = 1.0,      # % — engagement bajo = views compradas
    min_views_paid: int = 3000,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Separa los resultados en dos buckets usando el engagement rate como
    proxy de pagado/orgánico (TikTok no expone ventas por vídeo en ES).

    Devuelve (paid_items, organic_items):
      - organic: engagement ≥ organic_min_eng, ordenados por engagement abs
        (likes+comments+shares) desc → top n_each.
      - paid: engagement < paid_max_eng y views ≥ min_views_paid, ordenados
        por views desc → top n_each.
    Los vídeos en la zona ambigua (1-2%) se asignan a organic si falta
    cupo, para no desperdiciar candidatos cuando el nicho es pequeño."""
    scored = []
    for it in apify_results:
        meta = apify_cloud.extract_video_metadata(it)
        views = int(meta.get("view_count") or 0)
        if views <= 0 or not meta.get("url"):
            continue
        eng_abs = (
            int(meta.get("like_count") or 0)
            + int(meta.get("comment_count") or 0)
            + int(meta.get("share_count") or 0)
        )
        er = eng_abs / views * 100.0
        scored.append({"item": it, "views": views, "eng_abs": eng_abs, "er": er})

    organic = sorted(
        [s for s in scored if s["er"] >= organic_min_eng],
        key=lambda s: s["eng_abs"], reverse=True,
    )
    paid = sorted(
        [s for s in scored if s["er"] < paid_max_eng and s["views"] >= min_views_paid],
        key=lambda s: s["views"], reverse=True,
    )

    organic_items = [s["item"] for s in organic[:n_each]]
    paid_items = [s["item"] for s in paid[:n_each]]

    # Si el nicho es pequeño y no llenamos organic, rellenamos con los
    # ambiguos (1-2%) por engagement, sin pisar los que ya están en paid.
    if len(organic_items) < n_each:
        used = {id(x) for x in organic_items} | {id(x) for x in paid_items}
        ambiguous = sorted(
            [s for s in scored
             if paid_max_eng <= s["er"] < organic_min_eng
             and id(s["item"]) not in used],
            key=lambda s: s["eng_abs"], reverse=True,
        )
        for s in ambiguous:
            if len(organic_items) >= n_each:
                break
            organic_items.append(s["item"])
    return paid_items, organic_items


# ═════════════════════════════════════════════════════════════════════
# Fase 2b: agregación de sonidos trending
# ═════════════════════════════════════════════════════════════════════
def _aggregate_trending_sounds(
    apify_results: list[dict[str, Any]],
) -> list[TrendingSound]:
    """Cuenta cuántos de los top vídeos usan el mismo `music_id` y ordena
    por (frecuencia, views totales). El sonido más repetido en los vídeos
    virales del nicho es el que el operador debería montar.

    Ignora sonidos originales (musicOriginal=True) sin id reutilizable —
    esos son del creador y no se pueden montar."""
    by_id: dict[str, TrendingSound] = {}
    for item in apify_results:
        meta = apify_cloud.extract_video_metadata(item)
        mid = (meta.get("music_id") or "").strip()
        if not mid:
            continue
        views = int(meta.get("view_count") or 0)
        if mid in by_id:
            s = by_id[mid]
            s.used_count += 1
            s.total_views += views
        else:
            by_id[mid] = TrendingSound(
                music_id=mid,
                title=meta.get("music_name", ""),
                author=meta.get("music_author", ""),
                is_original=bool(meta.get("music_is_original", False)),
                url=meta.get("music_url", ""),
                used_count=1,
                total_views=views,
            )
    sounds = list(by_id.values())
    # Prioriza sonidos que se repiten; a igualdad, los de más views.
    sounds.sort(key=lambda s: (s.used_count, s.total_views), reverse=True)
    return sounds


# ═════════════════════════════════════════════════════════════════════
# Fase 3: análisis de comentarios → objeciones + preguntas reales
# ═════════════════════════════════════════════════════════════════════
def _analyze_comments(
    comments: list[dict[str, Any]],
    product: Product,
    *, log_callback: LogCallback,
) -> tuple[list[str], list[str]]:
    """Pasa los comentarios (texto + likes) a Gemini para extraer:
      - objections: dudas/frenos de compra reales
      - questions: preguntas que el público hace (y que el vídeo debería
        responder para neutralizar fricción)
    Devuelve (objections, questions)."""
    # Top 50 comentarios por likes — suficiente señal sin inflar el prompt.
    top = comments[:50]
    joined = "\n".join(
        f"- ({c['like_count']}❤) {c['text']}" for c in top if c.get("text")
    )
    if not joined.strip():
        return [], []

    system_prompt = """Eres un analista de conversión de TikTok Shop. Te paso comentarios REALES de vídeos virales de un producto. Tu tarea: extraer la voz del cliente.

DEVUELVE JSON EXACTO:
{
  "objections": ["freno/duda de compra real que aparece en los comentarios (ej. 'dudan de si hace mucho ruido')", ...],
  "questions": ["pregunta literal o parafraseada que el público hace y que un buen vídeo debería responder", ...]
}

Reglas:
- Máx 10 objections y 10 questions, las MÁS repetidas o con más likes.
- En el idioma del producto (español si es ES).
- NO inventes. Si el comentario no aporta, ignóralo.
- Sé específico: 'no saben si cabe en piso pequeño' mejor que 'dudas de tamaño'."""

    user_prompt = f"""Producto: {product.name}
Categoría: {product.category}
Idioma target: {product.language}

Comentarios (ordenados por likes):
{joined[:6000]}

Extrae objections + questions en JSON."""

    log_callback(f"  🧠 Gemini analizando {len(top)} comentarios…")
    try:
        text = gemini.generate_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model="gemini-2.5-flash",   # flash basta para extraer de texto
            expect_json=True,
            temperature=0.3,
        )
        data = _parse_video_analysis(text)
        objections = [str(o)[:200] for o in (data.get("objections") or [])][:10]
        questions = [str(q)[:200] for q in (data.get("questions") or [])][:10]
        log_callback(
            f"  ✓ {len(objections)} objeciones · {len(questions)} preguntas reales"
        )
        return objections, questions
    except Exception as e:
        log_callback(f"  ⚠️ Análisis de comentarios falló: {e}")
        return [], []
