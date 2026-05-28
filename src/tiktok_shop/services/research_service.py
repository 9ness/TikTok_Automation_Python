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
from src.tiktok_shop.models.product import ResearchContext, ViralVideoSummary


LogCallback = Callable[[str], None]


def _noop(_msg: str) -> None: ...


def deep_research_product(
    product: Product,
    *,
    max_videos_to_analyze: int = 5,
    max_tiktok_search_results: int = 10,
    log_callback: LogCallback = _noop,
) -> ResearchContext:
    """Investiga el producto en web + TikTok y devuelve ResearchContext
    relleno. No persiste — el caller decide cuándo guardar."""
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

    if apify_cloud.apify_is_configured():
        log_callback(
            f"🎬 Fase 2/3: buscando top {max_tiktok_search_results} vídeos "
            f"virales en TikTok via Apify…"
        )
        try:
            apify_results = apify_cloud.search_tiktok_videos(
                query=product.name,
                limit=max_tiktok_search_results,
                sort_by="popular",
                log_callback=log_callback,
            )
            cost_estimate += 0.008

            # Cost tracking
            try:
                from src.cost_tracking import record_apify_cloud
                record_apify_cloud(
                    items_count=len(apify_results),
                    queries_count=1,
                    detail=f"tiktok search '{product.name}'",
                )
            except Exception:
                pass

            # Tomamos top max_videos_to_analyze para análisis visual con Gemini.
            # Más caro pero mucho más útil que solo metadata.
            videos_to_analyze = apify_results[:max_videos_to_analyze]
            log_callback(
                f"  ✓ {len(apify_results)} encontrados, analizando los top "
                f"{len(videos_to_analyze)} con Gemini video…"
            )

            top_videos, viral_patterns, proven_hooks = _analyze_top_videos(
                videos_to_analyze, product, log_callback=log_callback,
            )
            cost_estimate += 0.02 * len(videos_to_analyze)
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
    # FASE 3: ensamblar ResearchContext
    # ════════════════════════════════════════════════════════════════
    elapsed = time.time() - started
    log_callback(
        f"✅ Investigación completada en {elapsed:.1f}s · "
        f"coste estimado ~${cost_estimate:.3f}"
    )

    return ResearchContext(
        customer_pains=customer_pains[:15],
        customer_benefits=customer_benefits[:15],
        objections=objections[:10],
        viral_patterns=viral_patterns[:10],
        top_videos=top_videos,
        niche_keywords=niche_keywords[:20],
        niche_inspiration=niche_inspiration[:10],
        competitive_diff=competitive_diff[:10],
        proven_hooks=proven_hooks[:15],
        analyzed_at=datetime.now(timezone.utc).isoformat(),
        sources_reviews_count=len(customer_pains) + len(customer_benefits),
        sources_videos_count=len(top_videos),
        research_cost_usd=round(cost_estimate, 4),
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

    # NOTE: ProductPhotos solo tiene `source` y `generated` — no `imported`.
    # photos_summary se conserva para futuro si se quiere mandar como info,
    # pero ahora mismo no se inyecta en el user_prompt (Gemini no necesita
    # los filenames para investigar reviews/web).
    user_prompt = f"""Producto: {product.name}
Marca: {product.brand or '—'}
Categoría: {product.category}
Subcategoría: {product.subcategory or '—'}
Audiencia: {', '.join(product.target_audience) if product.target_audience else '—'}
Key features actuales: {', '.join(product.key_features) if product.key_features else '—'}
Idioma target: {product.language}

Investiga este producto en la web y devuelve los listados estructurados.
Si el producto es para mercado español (es_*), las pains/benefits/objections
deben estar en español natural (no traducciones literales del inglés)."""

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
) -> tuple[list[ViralVideoSummary], list[str], list[str]]:
    """Descarga los top N vídeos y los analiza con Gemini 2.5 Pro.
    Devuelve (resúmenes, patrones agregados, hooks probados)."""
    summaries: list[ViralVideoSummary] = []
    tmp_dir = tempfile.mkdtemp(prefix="research_videos_")
    video_paths: list[str] = []

    try:
        # Descargar todos los MP4
        for idx, item in enumerate(apify_items):
            meta = apify_cloud.extract_video_metadata(item)
            if not meta.get("mp4_url"):
                continue
            try:
                dest = os.path.join(tmp_dir, f"viral_{idx}.mp4")
                apify_cloud.download_tiktok_video(meta["mp4_url"], dest)
                video_paths.append(dest)
                summaries.append(ViralVideoSummary(
                    url=meta["url"],
                    view_count=meta["view_count"],
                    like_count=meta["like_count"],
                    comment_count=meta["comment_count"],
                    duration_s=meta["duration_s"],
                ))
                log_callback(
                    f"  ⬇️ Vídeo {idx+1} descargado · "
                    f"{meta['view_count']:,} views · {meta['duration_s']:.0f}s"
                )
            except Exception as e:
                log_callback(f"  ⚠️ Vídeo {idx+1} falló descarga: {e}")
                continue

        if not video_paths:
            log_callback("  ❌ No se pudo descargar ningún vídeo")
            return [], [], []

        # Análisis BATCH con Gemini (todos los vídeos en una sola llamada)
        log_callback(
            f"  🧠 Gemini 2.5 Pro analizando {len(video_paths)} vídeos juntos…"
        )
        patterns_text = _gemini_batch_video_analysis(
            video_paths, product, log_callback=log_callback,
        )
        analysis = _parse_video_analysis(patterns_text)

        # Aplicar per-video data al summary
        per_video = analysis.get("per_video", [])
        for i, vid_data in enumerate(per_video):
            if i < len(summaries) and isinstance(vid_data, dict):
                summaries[i].hook_text = str(vid_data.get("hook_text", ""))[:200]
                summaries[i].hook_category = str(vid_data.get("hook_category", ""))[:50]
                summaries[i].script_structure = str(vid_data.get("structure", ""))[:300]
                summaries[i].visual_patterns = [
                    str(v)[:120] for v in (vid_data.get("visual_patterns") or [])
                ][:5]
                summaries[i].cta_used = str(vid_data.get("cta", ""))[:120]
                summaries[i].music_mood = str(vid_data.get("music_mood", ""))[:50]

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
    *, log_callback: LogCallback,
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

    user_prompt = f"""Producto del que son estos vídeos:
- Nombre: {product.name}
- Categoría: {product.category}
- Idioma target: {product.language}

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
