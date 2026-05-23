"""Genera VideoPresets para un producto usando Gemini con los 2
directores:

- `music_bof_director.md`    → 8-10 presets musicales (sin voz, 8-15s)
- `scripted_bof_director.md` → 10-15 presets scripted (uno por ángulo)

Cada preset trae `seedance_prompt` y `veo3_prompt` para ser compatible
con los 4 tiers (Standard/Advanced/Pro/Veo3). Cost tracking automático
vía generate_json — el caller debería estar dentro de un start_job.

Las fotos source del producto se envían a Gemini como contexto VISUAL
para que pueda (a) describir mejor los prompts y (b) elegir, para cada
preset, hasta 3 fotos a adjuntar manualmente al pegar el prompt de
Veo 3 en Gemini chat / Flow (`veo3_photo_filenames`).

Nunca lanza: si Gemini falla, devuelve [] + log warning. El endpoint
decide qué reportar al user.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Literal

from src.tiktok_shop.api.gemini import (
    DEFAULT_MODEL,
    generate_json,
    is_configured,
    load_system_prompt,
)
from src.tiktok_shop.models import Product, VideoPreset, make_preset_id
from src.tiktok_shop.models.video_preset import (
    TEXT_OVERLAY_ANIMATIONS,
    TEXT_OVERLAY_POSITIONS,
    CtaArrowStyle,
    SubtitleStyle,
    TextOverlayStyle,
)


_VALID_ARROW_STICKERS = {"flecha_negra.mov", "flecha_roja.mov"}

# Duración mínima por clip de Seedance (Atlas Cloud). Si quieres 2 clips
# necesitas al menos 8s totales. Para menos → single_shot forzoso.
_MIN_CLIP_DURATION_S = 4


def _resolve_shot_strategy(
    *,
    duration_s: int,
    kind: str,
    style: str,
    raw_shot_style: Any,
    raw_strategy: Any,
    compatible_tiers: list[str],
) -> tuple[str, str]:
    """Decide (shot_style, strategy) aplicando solo reglas duras de
    capacidad del modelo + respetando la elección del LLM/usuario.

    REGLAS DURAS (failsafes que NO se pueden saltar — derivan de
    limitaciones del modelo, no de preferencia estética):
    - duration_s < 8 → forzoso "single_shot" (Seedance mín por clip = 4s,
      no caben 2 clips, así que con < 8s solo cabe 1 plano).
    - kind=scripted + style=creator_pov → single_shot (persona hablando
      con lip-sync requiere continuidad, los cortes rompen el sync).
    - compatible_tiers SOLO veo3_prompt_only → single_shot (Veo 3 nativo
      es 1 toma de ≤10s).

    Para todo lo demás (duración ≥ 8s, voiceover, music): respeta la
    elección que Gemini propuso. "auto" se traduce a una sugerencia
    razonable basada en duración (≤10s tiende a single, >10s a multi)
    pero NO bloquea — Gemini puede pedir multi en 8s si encaja.
    """
    proposed = str(raw_shot_style or "auto").lower().strip()
    if proposed not in ("single_shot", "multi_shot", "auto"):
        proposed = "auto"
    strat = str(raw_strategy or "dynamic").lower().strip()
    if strat not in ("cinematic", "dynamic"):
        strat = "dynamic"

    # ── Hard rules (limitaciones del modelo) ──
    if duration_s < 8:
        return "single_shot", "cinematic"
    if kind == "scripted" and style == "creator_pov":
        return "single_shot", "cinematic"
    only_veo3 = compatible_tiers and all(
        t == "veo3_prompt_only" for t in compatible_tiers
    )
    if only_veo3:
        return "single_shot", "cinematic"

    # ── Auto: sugerencia razonable, pero permisiva ──
    if proposed == "auto":
        # Por defecto, vídeos cortos (≤10s) suelen verse mejor en single
        # shot (un plano elegante). Pero si Gemini propuso `dynamic` en
        # strategy (señal de que quiere movimiento), respetamos su voto.
        if duration_s <= 10 and strat == "cinematic":
            return "single_shot", "cinematic"
        # Caso 8-10s con strategy=dynamic → permite multi_shot (2×4s o
        # 4+5s, etc). 11-30s → casi siempre multi.
        return "multi_shot", "dynamic"

    # Usuario/Gemini eligió explícitamente
    if proposed == "single_shot":
        return "single_shot", "cinematic"
    # multi_shot: respetamos aunque la duración sea 8s (mínimo viable)
    return "multi_shot", "dynamic"


_VALID_TONES = {"energetic", "calm", "persuasive", "serious", "playful"}
_VALID_BACKGROUNDS = {"none", "black_bar", "blur"}

# Mapping locale → instrucciones para Gemini. Determina el idioma EXACTO
# del voice_script, hooks, CTA, text_overlay. Default es_ES (España).
_LANGUAGE_INSTRUCTIONS: dict[str, str] = {
    "es_ES": (
        "Idioma: ESPAÑOL DE ESPAÑA (castellano peninsular). Usa 'vosotros' "
        "no 'ustedes'. Modismos y vocabulario españoles ('flipas', 'súper', "
        "'currar', 'curro', 'guay', 'tío/tía' con moderación). Acento "
        "neutro de España. NUNCA mezcles voseo latinoamericano."
    ),
    "es_LATAM": (
        "Idioma: ESPAÑOL LATINOAMERICANO neutro. Usa 'ustedes' no "
        "'vosotros'. Vocabulario panregional sin localismos fuertes. "
        "Acento neutro latino (NO Castilla)."
    ),
    "en_US": (
        "Language: AMERICAN ENGLISH. Use American spellings (color, "
        "favor). Natural, casual TikTok voiceover energy."
    ),
    "en_UK": (
        "Language: BRITISH ENGLISH. Use British spellings (colour, "
        "favourite). British expressions where natural ('mate', 'brilliant')."
    ),
    "pt_BR": (
        "Idioma: PORTUGUÊS DO BRASIL. Usa vocabulário brasileiro, não "
        "português europeu."
    ),
    "fr_FR": "Langue : FRANÇAIS (France).",
}


def _language_block(product: Any) -> str:
    """Bloque de instrucciones de idioma para inyectar en el user_prompt
    de Gemini. Default a es_ES si el producto no tiene `language` o tiene
    un código no reconocido."""
    lang = getattr(product, "language", None) or "es_ES"
    instr = _LANGUAGE_INSTRUCTIONS.get(lang) or _LANGUAGE_INSTRUCTIONS["es_ES"]
    return (
        f"\n=== IDIOMA OBLIGATORIO ({lang}) ===\n{instr}\n"
        f"TODO el contenido (voice_script, hooks_alternatives, cta, "
        f"oratory_tips, text_overlay, title, keywords) debe estar en "
        f"este idioma. seedance_prompt y veo3_prompt SIEMPRE en inglés "
        f"(es lo que el modelo espera)."
    )

# Máximo de fotos source que pasamos a Gemini como contexto visual al
# generar presets. Más infla el coste (Gemini cobra por tile) y rara vez
# aporta: con 6 ya tiene packshot + lifestyle + texture. El user puede
# tener más fotos en el producto — Gemini solo ve estas y solo de éstas
# puede elegir las que adjuntar a Veo 3.
_MAX_PHOTOS_FOR_GEMINI = 6
# Máximo de fotos que Gemini puede elegir como reference para Veo 3.
# Veo 3 oficial (API) acepta 1; en Gemini chat / Flow puedes pegar varias
# y aporta contexto visual extra (packshot + lifestyle + textura).
_MAX_VEO3_PHOTOS = 3


def _collect_product_photos(product) -> tuple[list[str], list[str]]:
    """Devuelve `(filenames, paths)` de hasta `_MAX_PHOTOS_FOR_GEMINI`
    fotos source no borradas del producto que existan en disco. Orden:
    igual que están en `product.photos.source`. Si no hay fotos en disco
    → devuelve ([], [])."""
    filenames: list[str] = []
    paths: list[str] = []
    for p in product.photos.source:
        if p.deleted or not p.local_path:
            continue
        if not os.path.exists(p.local_path):
            continue
        filenames.append(p.filename)
        paths.append(p.local_path)
        if len(paths) >= _MAX_PHOTOS_FOR_GEMINI:
            break
    return filenames, paths


def _sanitize_veo3_photo_filenames(
    raw: Any, *, available: list[str],
) -> list[str]:
    """Filtra a los filenames que Gemini puede haber referenciado en su
    output, validando que cada uno exista en la lista que le pasamos
    (`available`). De-dup, máximo `_MAX_VEO3_PHOTOS`. Si Gemini no
    referenció nada o todo es inválido → fallback al primer filename
    available (mejor que vacío para el user; siempre puede editarlo)."""
    if not available:
        return []
    if not isinstance(raw, list):
        # Fallback: 1 sola foto packshot (la primera available).
        return [available[0]]
    seen: set[str] = set()
    out: list[str] = []
    available_set = set(available)
    for x in raw:
        if not isinstance(x, str):
            continue
        # Gemini a veces devuelve el path entero o solo el basename.
        # Normalizamos a basename.
        name = os.path.basename(x.strip())
        if name in available_set and name not in seen:
            seen.add(name)
            out.append(name)
            if len(out) >= _MAX_VEO3_PHOTOS:
                break
    if not out:
        return [available[0]]
    return out


def _parse_overlay_style(raw: Any) -> TextOverlayStyle:
    """Sanea el objeto text_overlay_style que devuelva Gemini."""
    if not isinstance(raw, dict):
        return TextOverlayStyle()
    pos = raw.get("position", "top_center")
    if pos not in TEXT_OVERLAY_POSITIONS:
        pos = "top_center"
    anim = raw.get("animation", "fade_in")
    if anim not in TEXT_OVERLAY_ANIMATIONS:
        anim = "fade_in"
    bg = raw.get("background", "none")
    if bg not in _VALID_BACKGROUNDS:
        bg = "none"
    try:
        size = int(raw.get("size_px", 56))
    except (TypeError, ValueError):
        size = 56
    try:
        stroke = int(raw.get("stroke_width", 6))
    except (TypeError, ValueError):
        stroke = 6
    try:
        duration = float(raw.get("duration_s", 4.0))
    except (TypeError, ValueError):
        duration = 4.0
    return TextOverlayStyle(
        font=str(raw.get("font", ""))[:200],
        size_px=max(12, min(200, size)),
        color=_safe_hex(raw.get("color"), default="#FFFFFF"),
        stroke_color=_safe_hex(raw.get("stroke_color"), default="#000000"),
        stroke_width=max(0, min(20, stroke)),
        position=pos,
        animation=anim,
        uppercase=bool(raw.get("uppercase", True)),
        background=bg,
        duration_s=max(0.5, min(30.0, duration)),
    )


def _safe_hex(val: Any, *, default: str) -> str:
    if not isinstance(val, str):
        return default
    s = val.strip()
    if s.startswith("#") and (len(s) == 7 or len(s) == 4):
        return s.upper()
    return default


def _safe_tone(val: Any, *, default: str = "energetic") -> str:
    if isinstance(val, str) and val.lower() in _VALID_TONES:
        return val.lower()
    return default


def _parse_cta_arrow_style(raw: Any) -> CtaArrowStyle:
    """Sanea cta_arrow_style devuelto por Gemini."""
    if not isinstance(raw, dict):
        return CtaArrowStyle()
    sticker = str(raw.get("sticker_file", "flecha_negra.mov"))
    if sticker not in _VALID_ARROW_STICKERS:
        sticker = "flecha_negra.mov"
    try:
        x = float(raw.get("position_x_pct", 50.0))
        y = float(raw.get("position_y_pct", 75.0))
        scale = float(raw.get("scale_width_pct", 25.0))
        dur = float(raw.get("duration_seconds", 4.0))
        # Default 90° = apunta abajo (al carrito nativo TikTok). Asset
        # base de la flecha apunta a la derecha por defecto.
        rot = int(raw.get("rotation_deg", 90))
    except (TypeError, ValueError):
        x, y, scale, dur, rot = 50.0, 75.0, 25.0, 4.0, 90
    return CtaArrowStyle(
        enabled=bool(raw.get("enabled", False)),
        sticker_file=sticker,
        position_x_pct=max(0.0, min(100.0, x)),
        position_y_pct=max(0.0, min(100.0, y)),
        scale_width_pct=max(5.0, min(60.0, scale)),
        rotation_deg=max(-180, min(180, rot)),
        flip_horizontal=bool(raw.get("flip_horizontal", False)),
        flip_vertical=bool(raw.get("flip_vertical", False)),
        duration_seconds=max(0.5, min(10.0, dur)),
        show_at_end=bool(raw.get("show_at_end", True)),
    )


def _parse_subtitle_style(raw: Any) -> SubtitleStyle:
    """Sanea subtitle_style devuelto por Gemini."""
    if not isinstance(raw, dict):
        return SubtitleStyle()
    pos = raw.get("position", "bottom_center")
    if pos not in TEXT_OVERLAY_POSITIONS:
        pos = "bottom_center"
    anim = raw.get("animation", "fade_in")
    if anim not in TEXT_OVERLAY_ANIMATIONS:
        anim = "fade_in"
    try:
        size = int(raw.get("size_px", 42))
    except (TypeError, ValueError):
        size = 42
    try:
        stroke = int(raw.get("stroke_width", 5))
    except (TypeError, ValueError):
        stroke = 5
    try:
        max_words = int(raw.get("max_words_per_line", 3))
    except (TypeError, ValueError):
        max_words = 3
    try:
        margin_x = float(raw.get("margin_x_pct", 8.0))
    except (TypeError, ValueError):
        margin_x = 8.0
    return SubtitleStyle(
        enabled=bool(raw.get("enabled", True)),
        font=str(raw.get("font", ""))[:200],
        size_px=max(20, min(120, size)),
        color=_safe_hex(raw.get("color"), default="#FFFFFF"),
        stroke_color=_safe_hex(raw.get("stroke_color"), default="#000000"),
        stroke_width=max(0, min(20, stroke)),
        position=pos,
        highlight_color=_safe_hex(raw.get("highlight_color"), default="#FFE066"),
        max_words_per_line=max(1, min(8, max_words)),
        uppercase=bool(raw.get("uppercase", False)),
        animation=anim,
        margin_x_pct=max(0.0, min(25.0, margin_x)),
    )

logger = logging.getLogger("tiktok_shop.preset_generator")


# Veo 3 solo genera hasta 10s nativo. Si Gemini propone un preset
# con duración mayor, lo eliminamos de compatible_tiers en código.
VEO3_MAX_DURATION_S = 10

ALL_TIERS = ["standard", "advanced", "pro", "veo3_prompt_only"]
TIERS_WITHOUT_VEO3 = ["standard", "advanced", "pro"]
# Tiers que NO pueden generar persona hablando a cámara con lip-sync.
# Standard/Advanced solo animan la foto del producto (i2v) — no pueden
# inventar a alguien hablando. Pro puede SI le das foto de persona.
TIERS_INCOMPATIBLE_WITH_CREATOR_POV = ["standard", "advanced"]


def _sanitize_tiers(tiers: list[str], *, duration_s: int, style: str) -> list[str]:
    """Aplica las reglas de compatibilidad reales:
      - clampa Veo 3 si duration > 10s
      - quita standard/advanced si style=creator_pov (no pueden lip-sync)
      - filtra strings inválidos.
    Si el resultado queda vacío, devuelve los compatibles "más seguros".
    """
    valid = {"standard", "advanced", "pro", "veo3_prompt_only"}
    out = [t for t in tiers if t in valid]

    if duration_s > VEO3_MAX_DURATION_S:
        out = [t for t in out if t != "veo3_prompt_only"]

    if style == "creator_pov":
        out = [t for t in out if t not in TIERS_INCOMPATIBLE_WITH_CREATOR_POV]

    if not out:
        # Fallback razonable: si la regla nos dejó sin tiers, al menos
        # pro siempre puede (con foto de persona o multi-shot)
        out = ["pro"]
        if duration_s <= VEO3_MAX_DURATION_S and style != "voiceover_required":
            out.append("veo3_prompt_only")
    # De-dup preservando orden
    seen: set[str] = set()
    deduped = []
    for t in out:
        if t not in seen:
            seen.add(t)
            deduped.append(t)
    return deduped


PresetKind = Literal["music", "scripted", "both"]


def generate_presets(
    product: Product,
    *,
    kind: PresetKind = "both",
    n_music: int = 8,
    n_scripted: int = 12,
) -> tuple[list[VideoPreset], list[str]]:
    """Llama a Gemini con uno o ambos directores y devuelve presets.

    Devuelve `(presets, warnings)`. `warnings` contiene los errores que
    no rompieron del todo (ej. "music director falló pero scripted OK").
    """
    if not is_configured():
        return [], ["Gemini no configurado."]

    out: list[VideoPreset] = []
    warnings: list[str] = []

    if kind in ("music", "both"):
        try:
            music_presets, lib_warnings = _generate_music(product, n=n_music)
            out.extend(music_presets)
            warnings.extend(lib_warnings)
        except Exception as e:
            logger.warning("[preset_gen] music falló: %s", e)
            warnings.append(f"Music director falló: {e}")

    if kind in ("scripted", "both"):
        try:
            scripted_presets = _generate_scripted(product, n=n_scripted)
            out.extend(scripted_presets)
        except Exception as e:
            logger.warning("[preset_gen] scripted falló: %s", e)
            warnings.append(f"Scripted director falló: {e}")

    return out, warnings


# ---------------------------------------------------------------------------
# Music director
# ---------------------------------------------------------------------------
def _generate_music(
    product: Product, *, n: int = 8,
) -> tuple[list[VideoPreset], list[str]]:
    system = load_system_prompt("music_bof_director.md")
    photo_filenames, photo_paths = _collect_product_photos(product)
    photos_block = (
        "Fotos del producto disponibles (te las paso como imágenes en "
        "este mismo prompt, en el MISMO ORDEN):\n"
        + "\n".join(f"  - {fn}" for fn in photo_filenames)
        + "\n\nPara CADA preset, elige hasta 3 filenames de esta lista "
          "en `veo3_photo_filenames` (la(s) que mejor encajen con el "
          "ángulo / escena del veo3_prompt). DEBES referenciar los "
          "filenames EXACTAMENTE como están arriba.\n"
    ) if photo_filenames else (
        "El producto no tiene fotos source disponibles — deja "
        "`veo3_photo_filenames: []` en cada preset.\n"
    )
    user_prompt = (
        f"Contexto del producto:\n"
        f"- Nombre: {product.name}\n"
        f"- Marca: {product.brand or '(sin marca)'}\n"
        f"- Categoría: {product.category}"
        f"{' / ' + product.subcategory if product.subcategory else ''}\n"
        f"- Precio real: {_fmt_price(product)}\n"
        f"- Precio para hooks de ahorro/comparativa: {_hook_price_suggestion(product) or '(N/A)'}\n"
        f"- Audiencia objetivo: {', '.join(product.target_audience) or '(genérico)'}\n"
        f"- Key features: {', '.join(product.key_features) or '(sin definir)'}\n"
        f"- Selling points: {', '.join(product.selling_points) or '(sin definir)'}\n"
        f"{_language_block(product)}\n\n"
        f"{photos_block}\n"
        f"Genera EXACTAMENTE {n} presets musicales. Sigue el schema al pie de la letra."
    )

    result = generate_json(
        system_prompt=system, user_prompt=user_prompt,
        model=DEFAULT_MODEL, temperature=0.85,
        images=photo_paths or None,
    )
    if not isinstance(result, dict):
        return [], ["Music director devolvió respuesta no-dict."]

    presets_raw = result.get("presets") or []
    presets: list[VideoPreset] = []
    for p in presets_raw:
        if not isinstance(p, dict):
            continue
        try:
            duration = _clamp_int(p.get("duration_s"), 8, 15, 12)
            # Música: voiceover-style por definición (sin persona hablando)
            # → todos los tiers compatibles, salvo cap Veo 3 a 10s.
            proposed_tiers = p.get("compatible_tiers") or list(ALL_TIERS)
            if not isinstance(proposed_tiers, list):
                proposed_tiers = list(ALL_TIERS)
            tiers = _sanitize_tiers(
                [str(t) for t in proposed_tiers],
                duration_s=duration,
                style="voiceover",
            )
            shot_style, strategy_val = _resolve_shot_strategy(
                duration_s=duration,
                kind="music",
                style="voiceover",
                raw_shot_style=p.get("shot_style"),
                raw_strategy=p.get("strategy"),
                compatible_tiers=tiers,
            )
            preset = VideoPreset(
                id=make_preset_id(),
                kind="music",
                name=str(p.get("name", "Music preset"))[:120],
                angle="",
                style="voiceover",
                shot_style=shot_style,
                strategy=strategy_val,
                duration_s=duration,
                text_overlay=str(p.get("text_overlay", ""))[:200],
                text_overlay_style=_parse_overlay_style(p.get("text_overlay_style")),
                # Música → sin voz → subtítulos desactivados por defecto.
                # Si el user los activa luego en el editor, se muestran.
                subtitle_style=SubtitleStyle(enabled=False),
                cta_arrow_style=_parse_cta_arrow_style(p.get("cta_arrow_style")),
                music_mood=str(p.get("music_mood", "trendy_uplifting"))[:60],
                # Música = sin voz por definición
                voice_id=None,
                voice_tone="energetic",
                seedance_prompt=str(p.get("seedance_prompt", ""))[:500],
                veo3_prompt=str(p.get("veo3_prompt", ""))[:1500],
                veo3_photo_filenames=_sanitize_veo3_photo_filenames(
                    p.get("veo3_photo_filenames"), available=photo_filenames,
                ),
                source="music_bof",
                compatible_tiers=tiers,
            )
            presets.append(preset)
        except Exception as e:
            logger.warning("[preset_gen.music] item inválido ignorado: %s", e)
            continue

    # Las libraries no las persistimos en VideoPreset — el caller puede
    # querer guardarlas en product.hooks_library / similar. Por ahora
    # solo las logueamos como info — futura iteración las integra.
    overlays_lib = result.get("text_overlays_library") or []
    voice_lib = result.get("voice_lines_library") or []
    if overlays_lib or voice_lib:
        logger.info(
            "[preset_gen.music] librerías generadas (no persistidas): "
            "%d overlays, %d voice lines",
            len(overlays_lib), len(voice_lib),
        )

    return presets, []


# ---------------------------------------------------------------------------
# Scripted director
# ---------------------------------------------------------------------------
def _generate_scripted(product: Product, *, n: int = 12) -> list[VideoPreset]:
    system = load_system_prompt("scripted_bof_director.md")
    photo_filenames, photo_paths = _collect_product_photos(product)
    photos_block = (
        "Fotos del producto disponibles (te las paso como imágenes en "
        "este mismo prompt, en el MISMO ORDEN):\n"
        + "\n".join(f"  - {fn}" for fn in photo_filenames)
        + "\n\nPara CADA preset, elige hasta 3 filenames de esta lista "
          "en `veo3_photo_filenames` (la(s) que mejor encajen con el "
          "ángulo / escena del veo3_prompt). DEBES referenciar los "
          "filenames EXACTAMENTE como están arriba.\n"
    ) if photo_filenames else (
        "El producto no tiene fotos source disponibles — deja "
        "`veo3_photo_filenames: []` en cada preset.\n"
    )
    user_prompt = (
        f"Contexto del producto:\n"
        f"- Nombre: {product.name}\n"
        f"- Marca: {product.brand or '(sin marca)'}\n"
        f"- Categoría: {product.category}"
        f"{' / ' + product.subcategory if product.subcategory else ''}\n"
        f"- Precio real: {_fmt_price(product)}\n"
        f"- Precio para hooks de ahorro/comparativa: {_hook_price_suggestion(product) or '(N/A)'}\n"
        f"- Audiencia objetivo: {', '.join(product.target_audience) or '(genérico)'}\n"
        f"- Key features: {', '.join(product.key_features) or '(sin definir)'}\n"
        f"- Selling points: {', '.join(product.selling_points) or '(sin definir)'}\n"
        f"{_language_block(product)}\n\n"
        f"{photos_block}\n"
        f"Genera EXACTAMENTE {n} presets scripted, cada uno con un ÁNGULO "
        f"distinto del menú. Sigue el schema al pie de la letra."
    )

    result = generate_json(
        system_prompt=system, user_prompt=user_prompt,
        model=DEFAULT_MODEL, temperature=0.85,
        images=photo_paths or None,
    )
    if not isinstance(result, dict):
        return []

    presets_raw = result.get("presets") or []
    presets: list[VideoPreset] = []
    for p in presets_raw:
        if not isinstance(p, dict):
            continue
        try:
            duration = _clamp_int(p.get("duration_s"), 8, 60, 20)
            # Gemini decide voiceover vs creator_pov. Default seguro:
            # voiceover (más compatible).
            raw_style = str(p.get("style", "voiceover")).lower().strip()
            style = raw_style if raw_style in ("voiceover", "creator_pov") else "voiceover"

            proposed_tiers = p.get("compatible_tiers") or list(ALL_TIERS)
            if not isinstance(proposed_tiers, list):
                proposed_tiers = list(ALL_TIERS)
            tiers = _sanitize_tiers(
                [str(t) for t in proposed_tiers],
                duration_s=duration,
                style=style,
            )
            shot_style, strategy_val = _resolve_shot_strategy(
                duration_s=duration,
                kind="scripted",
                style=style,
                raw_shot_style=p.get("shot_style"),
                raw_strategy=p.get("strategy"),
                compatible_tiers=tiers,
            )

            preset = VideoPreset(
                id=make_preset_id(),
                kind="scripted",
                name=str(p.get("name", "Scripted preset"))[:120],
                angle=str(p.get("angle", ""))[:30],
                style=style,
                shot_style=shot_style,
                strategy=strategy_val,
                duration_s=duration,
                title=str(p.get("title", ""))[:200],
                voice_script=str(p.get("voice_script", ""))[:3000],
                hooks_alternatives=[
                    str(h)[:200] for h in (p.get("hooks_alternatives") or [])
                ][:8],
                cta=str(p.get("cta", ""))[:200],
                oratory_tips=str(p.get("oratory_tips", ""))[:500],
                keywords=[
                    str(k)[:60] for k in (p.get("keywords") or [])
                ][:10],
                text_overlay=str(p.get("text_overlay", ""))[:200],
                text_overlay_style=_parse_overlay_style(p.get("text_overlay_style")),
                subtitle_style=_parse_subtitle_style(p.get("subtitle_style")),
                cta_arrow_style=_parse_cta_arrow_style(p.get("cta_arrow_style")),
                music_mood=str(p.get("music_mood", "subtle_chill"))[:60],
                voice_id=None,  # se selecciona al editar el preset
                voice_tone=_safe_tone(p.get("voice_tone")),
                seedance_prompt=str(p.get("seedance_prompt", ""))[:500],
                veo3_prompt=str(p.get("veo3_prompt", ""))[:2000],
                veo3_photo_filenames=_sanitize_veo3_photo_filenames(
                    p.get("veo3_photo_filenames"), available=photo_filenames,
                ),
                source="scripted_bof",
                compatible_tiers=tiers,
            )
            presets.append(preset)
        except Exception as e:
            logger.warning("[preset_gen.scripted] item inválido ignorado: %s", e)
            continue
    return presets


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _fmt_price(product: Product) -> str:
    p = getattr(product.tiktok_shop, "price_eur", None)
    if p is None:
        return "(sin definir)"
    return f"{float(p):.2f}€"


def _hook_price_suggestion(product: Product) -> str:
    """Devuelve el precio "atractivo" para usar en hooks de tipo ahorro/precio.
    Política: ~30% menos que el real, redondeado hacia abajo a un número
    psicológico (acabado en 5 o 0, prefiriendo barreras enteras como 10, 20,
    30…). Justificación: existen cupones / descuentos / outlets, y un precio
    bajo en el hook llama más al scroll-stop. El user puede editar el preset
    después si el precio quedó muy lejos del real."""
    p = getattr(product.tiktok_shop, "price_eur", None)
    if p is None or p <= 0:
        return ""
    real = float(p)
    target = real * 0.70  # 30% off
    # Redondeo a barrera "por menos de X" psicológica
    if target < 5:
        suggested = max(2, int(target))           # "menos de 3€" etc
    elif target < 10:
        suggested = max(5, int(target))           # 5, 6, 7, 8, 9
    elif target < 50:
        # Redondeo hacia abajo al siguiente múltiplo de 5 (10, 15, 20, 25…)
        suggested = max(10, (int(target) // 5) * 5)
    elif target < 200:
        suggested = (int(target) // 10) * 10      # 50, 60, 70…
    else:
        suggested = (int(target) // 50) * 50      # 200, 250, 300…
    return f"{suggested}€ (precio real: {real:.2f}€, sugerencia ~30% menos para hooks de ahorro)"


def _clamp_int(val: Any, lo: int, hi: int, default: int) -> int:
    try:
        v = int(val)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))
