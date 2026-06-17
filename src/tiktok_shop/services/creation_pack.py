"""Creation Pack — deja un producto LISTO PARA CREAR sin que el operador
busque nada.

Para un `Product` ya importado, orquesta TODAS las piezas existentes y
escribe los resultados en su carpeta de Drive (`_products/<slug>/`):

  1. FOTOS    — busca imágenes del producto (DuckDuckGo) y descarga N a
                `photos_source/` (además de la cover que ya trae).
  2. ANÁLISIS — Gemini Vision (`analyze_product`) → audiencias, selling
                points, features, flag de packaging.
  3. RESEARCH — `deep_research_product` → analiza los VÍDEOS GANADORES del
                producto en TikTok (pains, objeciones, hooks probados,
                sonidos trending) → `research_context`.
  4. ESTILOS  — `generate_presets` → presets de vídeo (music + scripted)
                que ya tiran del research. Es "el estilo de vídeo" hecho.
  5. CARRUSEL — `generate_carousel` × N → guiones de carrusel.
  6. NANO     — `generate_nano_banana_prompt` → prompt para fotos premium.
  7. ARCHIVOS — escribe carruseles, prompt nano, presets y un `PLAN.md`
                legible en `_products/<slug>/prompt_templates/`.

`plan_week` repite esto para los top N candidatos del Radar y escribe un
`_plans/week_<fecha>.md` repartiendo productos por día (7 días).

Todo best-effort: un fallo en un paso loguea aviso y sigue. Nunca rompe la UI.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from src.tiktok_shop.config import (
    product_photos_source_folder,
    product_prompt_templates_folder,
    resolve_shop_root,
)
from src.tiktok_shop.models import Product
from src.tiktok_shop.repos import ProductRepo


LogCallback = Callable[[str], None]


def _noop(_msg: str) -> None: ...


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═════════════════════════════════════════════════════════════════════
# Opciones
# ═════════════════════════════════════════════════════════════════════
@dataclass
class PackOptions:
    """Qué pasos ejecutar al construir el pack. Todo ON por defecto =
    paquete completo. El operador puede apagar pasos para ahorrar coste."""
    download_photos: bool = True
    photos_to_download: int = 6
    analyze: bool = True
    research: bool = True
    research_markets: list[str] | None = None   # extra (US/GB) si nicho ES pequeño
    generate_video_presets: bool = True
    preset_kind: str = "both"                   # music | scripted | both
    n_music: int = 6
    n_scripted: int = 8
    n_carousels: int = 3
    carousel_slides: int = 6
    generate_nano_banana: bool = True
    write_files: bool = True


@dataclass
class PackResult:
    product_id: str
    slug: str
    name: str
    photos_downloaded: int = 0
    research_done: bool = False
    presets_generated: int = 0
    carousels_generated: int = 0
    nano_prompt: bool = False
    folder: str = ""
    warnings: list[str] = field(default_factory=list)


# ═════════════════════════════════════════════════════════════════════
# Pack de un producto
# ═════════════════════════════════════════════════════════════════════
def build_pack(
    product: Product,
    *,
    options: PackOptions | None = None,
    discovered: Any = None,   # DiscoveredProduct opcional (para el PLAN.md)
    log_callback: LogCallback = _noop,
) -> PackResult:
    """Construye el pack completo de un producto ya importado y lo persiste."""
    opt = options or PackOptions()
    repo = ProductRepo()
    res = PackResult(
        product_id=product.id, slug=product.slug, name=product.name,
        folder=os.path.dirname(product_prompt_templates_folder(product.slug)),
    )
    log_callback(f"📦 Pack de '{product.name}' (slug: {product.slug})…")

    # 1. FOTOS ────────────────────────────────────────────────────────
    if opt.download_photos:
        try:
            res.photos_downloaded = _download_more_photos(
                product, n=opt.photos_to_download, log_callback=log_callback,
            )
        except Exception as e:
            res.warnings.append(f"fotos: {e}")
            log_callback(f"  ⚠️ Fotos fallaron ({e}) — sigo")

    # 2. ANÁLISIS ──────────────────────────────────────────────────────
    if opt.analyze:
        try:
            from src.tiktok_shop.services.product_service import re_analyze_with_gemini
            analysis = re_analyze_with_gemini(product)
            if analysis:
                log_callback(
                    f"  🔍 Análisis: {len(product.target_audience)} audiencias · "
                    f"{len(product.selling_points)} selling points"
                )
        except Exception as e:
            res.warnings.append(f"análisis: {e}")
            log_callback(f"  ⚠️ Análisis falló ({e}) — sigo")

    # 3. RESEARCH (vídeos ganadores) ───────────────────────────────────
    if opt.research:
        try:
            from src.tiktok_shop.services.research_service import deep_research_product
            log_callback("  🎬 Investigando vídeos ganadores en TikTok…")
            rc = deep_research_product(
                product,
                extra_markets=opt.research_markets,
                log_callback=log_callback,
            )
            product.research_context = rc
            res.research_done = True
            log_callback(
                f"  ✓ Research: {len(rc.proven_hooks)} hooks · "
                f"{len(rc.viral_patterns)} patrones · "
                f"{len(rc.top_videos)} vídeos analizados"
            )
        except Exception as e:
            res.warnings.append(f"research: {e}")
            log_callback(f"  ⚠️ Research falló ({e}) — sigo")

    # 4. ESTILOS de vídeo (presets) ────────────────────────────────────
    if opt.generate_video_presets:
        try:
            from src.tiktok_shop.pipeline.preset_generator import generate_presets
            log_callback("  🎥 Generando estilos de vídeo (presets)…")
            presets, warns = generate_presets(
                product, kind=opt.preset_kind,  # type: ignore[arg-type]
                n_music=opt.n_music, n_scripted=opt.n_scripted,
            )
            if presets:
                product.video_presets.extend(presets)
                res.presets_generated = len(presets)
                log_callback(f"  ✓ {len(presets)} estilos de vídeo creados")
            for w in warns:
                res.warnings.append(f"presets: {w}")
        except Exception as e:
            res.warnings.append(f"presets: {e}")
            log_callback(f"  ⚠️ Presets fallaron ({e}) — sigo")

    # 5. CARRUSELES ────────────────────────────────────────────────────
    carousels: list[dict[str, Any]] = []
    if opt.n_carousels > 0:
        try:
            from src.tiktok_shop.pipeline.carousel_director import generate_carousel
            log_callback(f"  🎠 Generando {opt.n_carousels} carruseles…")
            for i in range(opt.n_carousels):
                data = generate_carousel(product, n_slides=opt.carousel_slides)
                if data and data.get("slides"):
                    carousels.append(data)
            res.carousels_generated = len(carousels)
            log_callback(f"  ✓ {len(carousels)} carruseles creados")
        except Exception as e:
            res.warnings.append(f"carruseles: {e}")
            log_callback(f"  ⚠️ Carruseles fallaron ({e}) — sigo")

    # 6. NANO BANANA prompt ────────────────────────────────────────────
    nano_prompt = ""
    if opt.generate_nano_banana:
        try:
            from src.tiktok_shop.pipeline.nano_banana_prompt_generator import (
                generate_nano_banana_prompt,
            )
            desc = " · ".join(product.selling_points[:5]) or product.name
            nano_prompt = generate_nano_banana_prompt(
                product_name=product.name, product_description=desc,
            )
            res.nano_prompt = bool(nano_prompt)
            log_callback("  🍌 Prompt Nano Banana 2 generado")
        except Exception as e:
            res.warnings.append(f"nano: {e}")
            log_callback(f"  ⚠️ Nano prompt falló ({e}) — sigo")

    # 5b. HOOKS BOFU (textos simples para A/B — consejo del operador) ───
    try:
        from src.tiktok_shop.services.hooks_generator import generate_bofu_hooks
        bofu = generate_bofu_hooks(product, n=10)
        if bofu.get("hooks"):
            product.bofu_hooks = bofu["hooks"]
            log_callback(f"  🎣 {len(bofu['hooks'])} hooks BOFU")
    except Exception as e:
        res.warnings.append(f"hooks_bofu: {e}")
        log_callback(f"  ⚠️ Hooks BOFU fallaron ({e}) — sigo")

    # Persistir el producto enriquecido ────────────────────────────────
    if carousels:
        product.carousels = carousels   # para verlos en la app sin abrir Drive
    product.touch()
    repo.save(product)

    # 7. ARCHIVOS en la carpeta de Drive ──────────────────────────────
    if opt.write_files:
        try:
            _write_pack_files(
                product, carousels=carousels, nano_prompt=nano_prompt,
                discovered=discovered, log_callback=log_callback,
            )
        except Exception as e:
            res.warnings.append(f"archivos: {e}")
            log_callback(f"  ⚠️ Escritura de archivos falló ({e}) — sigo")

    log_callback(f"✅ Pack de '{product.name}' listo en `{res.folder}`")
    return res


# ═════════════════════════════════════════════════════════════════════
# Plan semanal — top N candidatos del Radar → packs + plan por día
# ═════════════════════════════════════════════════════════════════════
def plan_week(
    *,
    n_products: int = 7,
    options: PackOptions | None = None,
    category: str = "otros",
    language: str = "es_ES",
    days: int = 7,
    per_day: int | None = None,
    only_non_imported: bool = True,
    log_callback: LogCallback = _noop,
) -> list[PackResult]:
    """Coge los top `n_products` candidatos del Radar (por score), los
    importa y construye el pack de cada uno. Escribe un `_plans/week_<fecha>.md`
    repartiendo productos por día.

    Requiere que el Radar tenga candidatos (corre un scan antes si está vacío).
    """
    from src.tiktok_shop.repos import DiscoveryRepo
    from src.tiktok_shop.services.discovery_service import import_candidate

    disc_repo = DiscoveryRepo()
    candidates = disc_repo.list_all()
    if only_non_imported:
        pool = [c for c in candidates if not c.imported]
    else:
        pool = candidates
    if not pool:
        log_callback("⚠️ Radar sin candidatos. Haz un scan en 'Descubrir' primero.")
        return []

    chosen = pool[: max(1, n_products)]
    log_callback(f"🗓️ Plan {days} días — construyendo {len(chosen)} packs…")

    results: list[PackResult] = []
    day_map: list[tuple[int, PackResult, Any]] = []
    for idx, cand in enumerate(chosen):
        log_callback(f"\n─── {idx + 1}/{len(chosen)} · {cand.name} ───")
        try:
            product = import_candidate(
                cand, category=category, language=language,
                log_callback=log_callback,
            )
            res = build_pack(
                product, options=options, discovered=cand,
                log_callback=log_callback,
            )
        except Exception as e:
            log_callback(f"  ❌ Pack falló para '{cand.name}': {e}")
            res = PackResult(
                product_id="", slug="", name=cand.name,
                warnings=[f"fatal: {e}"],
            )
        results.append(res)
        # Asignación de día: si `per_day` se da, secuencial (día 1 = primeros
        # `per_day`, día 2 = siguientes…) — así pruebas N productos por día.
        # Si no, round-robin sobre `days`.
        if per_day and per_day > 0:
            day = idx // per_day + 1
        else:
            day = (idx % max(1, days)) + 1
        day_map.append((day, res, cand))

    # Persistir el plan en Redis (para el calendario) + escribir el .md
    effective_days = max((d for d, _, _ in day_map), default=days)
    try:
        _persist_week_plan(day_map, days=effective_days, log_callback=log_callback)
    except Exception as e:
        log_callback(f"⚠️ No se pudo guardar el plan en Redis ({e})")
    try:
        _write_week_plan(day_map, days=effective_days, log_callback=log_callback)
    except Exception as e:
        log_callback(f"⚠️ No se pudo escribir el plan semanal ({e})")

    log_callback(f"\n✅ Plan listo: {len(results)} productos preparados.")
    return results


def _persist_week_plan(
    day_map: list[tuple[int, PackResult, Any]], *, days: int, log_callback: LogCallback,
) -> None:
    """Construye un WeekPlan a partir del day_map y lo guarda como plan
    actual (lo lee el calendario del Radar)."""
    from src.tiktok_shop.models.week_plan import PlanEntry, WeekPlan
    from src.tiktok_shop.repos import PlanRepo

    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entries: list[PlanEntry] = []
    for day, res, cand in day_map:
        if not res.slug:
            continue
        sc = getattr(cand, "score", None)
        ads = getattr(cand, "ads", None)
        entries.append(PlanEntry(
            day=day,
            product_id=res.product_id,
            slug=res.slug,
            name=res.name,
            score=float(getattr(sc, "total", 0.0)) if sc is not None else 0.0,
            ads_verdict=str(getattr(ads, "verdict", "")) if ads is not None else "",
            carousels=res.carousels_generated,
            presets=res.presets_generated,
        ))
    plan = WeekPlan(
        label=f"Semana {date}", date=date, days=days, entries=entries,
    )
    PlanRepo().save(plan, make_current=True)
    log_callback(f"🗓️ Plan guardado en Redis (calendario): {len(entries)} productos")


# ═════════════════════════════════════════════════════════════════════
# Helpers — fotos
# ═════════════════════════════════════════════════════════════════════
def _download_more_photos(
    product: Product, *, n: int, log_callback: LogCallback,
) -> int:
    """Busca imágenes del producto y descarga hasta `n` a photos_source.
    Evita re-descargar si el producto ya tiene >= n fotos source vivas."""
    from src.tiktok_shop.utils import image_search
    from src.tiktok_shop.utils.photo_downloader import download_image_to_product

    alive = [p for p in product.photos.source if not p.deleted]
    if len(alive) >= n:
        log_callback(f"  🖼️ Ya tiene {len(alive)} fotos source — no descargo más")
        return 0

    query = f"{product.brand or ''} {product.name}".strip()
    provider, results = image_search.search_product_images(query, num=n + 4)
    if not results:
        log_callback(f"  ⚠️ Sin imágenes para '{query}' ({provider})")
        return 0

    existing_urls = {p.url_origin for p in product.photos.source if p.url_origin}
    downloaded = 0
    need = n - len(alive)
    for item in results:
        if downloaded >= need:
            break
        url = item.get("link")
        if not url or url in existing_urls:
            continue
        photo = download_image_to_product(
            product_slug=product.slug, image_url=url,
            photo_type="packshot", origin="internet",
        )
        if photo:
            photo.url_origin = url
            product.photos.source.append(photo)
            downloaded += 1
    log_callback(f"  🖼️ {downloaded} fotos descargadas ({provider})")
    return downloaded


# ═════════════════════════════════════════════════════════════════════
# Helpers — escritura de archivos
# ═════════════════════════════════════════════════════════════════════
def _write_pack_files(
    product: Product,
    *,
    carousels: list[dict[str, Any]],
    nano_prompt: str,
    discovered: Any,
    log_callback: LogCallback,
) -> None:
    folder = Path(product_prompt_templates_folder(product.slug))
    folder.mkdir(parents=True, exist_ok=True)

    # Carruseles: JSON + TXT legible
    if carousels:
        car_dir = folder / "carousels"
        car_dir.mkdir(exist_ok=True)
        for i, c in enumerate(carousels, 1):
            (car_dir / f"carousel_{i}.json").write_text(
                json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8",
            )
            (car_dir / f"carousel_{i}.txt").write_text(
                _carousel_to_text(c), encoding="utf-8",
            )

    # Nano Banana prompt
    if nano_prompt:
        (folder / "nano_banana_prompt.txt").write_text(nano_prompt, encoding="utf-8")

    # Presets (estilos de vídeo) — resumen legible
    if product.video_presets:
        (folder / "video_presets.txt").write_text(
            _presets_to_text(product.video_presets), encoding="utf-8",
        )

    # PLAN.md — resumen ejecutivo de qué hacer con este producto
    plan_path = Path(
        os.path.dirname(product_prompt_templates_folder(product.slug))
    ) / "PLAN.md"
    plan_path.write_text(
        _product_plan_md(product, carousels=carousels, discovered=discovered),
        encoding="utf-8",
    )
    log_callback(f"  📝 Archivos escritos en `{folder}`")


def _carousel_to_text(c: dict[str, Any]) -> str:
    lines = [
        f"CONCEPTO: {c.get('concept', '')}",
        "",
        "CAPTION (copiar al subir):",
        c.get("hook_caption", ""),
        "",
        "─" * 50,
    ]
    for s in c.get("slides", []):
        lines += [
            f"\nSLIDE {s.get('slide_number', '?')} [{s.get('role', '')}] — \"{s.get('on_screen_text', '')}\"",
            "PROMPT IMAGEN (Nano Banana 2 / image model):",
            s.get("image_prompt", ""),
        ]
    if c.get("image_style_guide"):
        lines += ["", f"GUÍA DE ESTILO: {c['image_style_guide']}"]
    if c.get("human_presence_note"):
        lines += [f"PRESENCIA HUMANA: {c['human_presence_note']}"]
    return "\n".join(lines)


def _presets_to_text(presets: list) -> str:
    lines = [f"# {len(presets)} estilos de vídeo generados\n"]
    for i, p in enumerate(presets, 1):
        kind = getattr(p, "kind", "")
        angle = getattr(p, "angle", "")
        name = getattr(p, "name", "")
        dur = getattr(p, "duration_s", "")
        tiers = ", ".join(getattr(p, "compatible_tiers", []) or [])
        lines.append(f"{i}. [{kind}{'/' + angle if angle else ''}] {name} · {dur}s · tiers: {tiers}")
        script = getattr(p, "voice_script", "") or ""
        if script:
            lines.append(f"   guion: {script[:160]}")
    lines.append(
        "\n(Los presets completos están en la app → Generar Vídeo → este producto. "
        "Aquí solo el resumen.)"
    )
    return "\n".join(lines)


def _product_plan_md(
    product: Product, *, carousels: list[dict[str, Any]], discovered: Any,
) -> str:
    tts = product.tiktok_shop
    rc = product.research_context
    lines = [
        f"# {product.name}",
        "",
        f"- **Slug:** `{product.slug}`",
        f"- **TikTok Shop:** {tts.product_url or '—'}",
        f"- **Precio:** {tts.price_eur or '—'} € · **Comisión:** {tts.commission_rate * 100:.0f}%",
    ]
    if discovered is not None:
        sc = getattr(discovered, "score", None)
        ads = getattr(discovered, "ads", None)
        if sc is not None:
            lines.append(
                f"- **Score ganador:** {sc.total:.0f}/100 · "
                f"ADS: {getattr(ads, 'verdict', '—')} · "
                f"creadores: {getattr(discovered, 'influencer_count', '—')}"
            )
            if sc.reasons:
                lines.append(f"- **Por qué:** {' · '.join(sc.reasons[:5])}")
    lines += [
        "",
        f"## 👥 Audiencias\n" + ("\n".join(f"- {a}" for a in product.target_audience) or "- (pendiente)"),
        "",
        f"## ✅ Selling points\n" + ("\n".join(f"- {s}" for s in product.selling_points[:8]) or "- (pendiente)"),
    ]
    if rc.customer_pains:
        lines += ["", "## 😣 Dolores reales\n" + "\n".join(f"- {p}" for p in rc.customer_pains[:6])]
    if rc.proven_hooks:
        lines += ["", "## 🎣 Hooks probados\n" + "\n".join(f"- {h}" for h in rc.proven_hooks[:6])]
    if rc.trending_sounds:
        sounds = [getattr(s, "title", "") or getattr(s, "music_id", "") for s in rc.trending_sounds[:5]]
        lines += ["", "## 🎵 Sonidos trending\n" + "\n".join(f"- {s}" for s in sounds if s)]
    lines += [
        "",
        "## 📦 Qué tienes listo en `prompt_templates/`",
        f"- 🎠 {len(carousels)} carruseles (carousels/*.txt) — pega cada prompt en Nano Banana 2",
        f"- 🎥 {len(product.video_presets)} estilos de vídeo (video_presets.txt) — genéralos en la app",
        "- 🍌 nano_banana_prompt.txt — para fotos premium",
        f"- 🖼️ {len([p for p in product.photos.source if not p.deleted])} fotos en `photos_source/`",
        "",
        "## ▶️ Cómo crear",
        "1. Genera fotos premium con el prompt Nano Banana (opcional).",
        "2. Carruseles: genera las imágenes de cada slide y súbelas con su caption.",
        "3. Vídeos: en la app → **Generar Vídeo** → este producto → elige un preset.",
        "",
        f"_Generado: {_now_iso()}_",
    ]
    return "\n".join(lines)


def _write_week_plan(
    day_map: list[tuple[int, PackResult, Any]], *, days: int, log_callback: LogCallback,
) -> None:
    plans_dir = Path(resolve_shop_root()) / "_plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = plans_dir / f"week_{date}.md"

    by_day: dict[int, list[tuple[PackResult, Any]]] = {}
    for day, res, cand in day_map:
        by_day.setdefault(day, []).append((res, cand))

    lines = [f"# Plan de {days} días — {date}", ""]
    for day in range(1, days + 1):
        entries = by_day.get(day, [])
        lines.append(f"## Día {day}")
        if not entries:
            lines.append("- (libre)")
        for res, cand in entries:
            sc = getattr(cand, "score", None)
            score_txt = f" · score {sc.total:.0f}" if sc is not None else ""
            warn = f" ⚠️ {len(res.warnings)} avisos" if res.warnings else ""
            lines.append(
                f"- **{res.name}** (`{res.slug}`){score_txt} — "
                f"{res.carousels_generated} carruseles · {res.presets_generated} estilos · "
                f"{res.photos_downloaded} fotos{warn}"
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    log_callback(f"🗓️ Plan semanal escrito en `{path}`")
