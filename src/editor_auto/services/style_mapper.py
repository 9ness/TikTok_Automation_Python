"""Mapea el estilo elegido por el cliente en la web (StyleConfig de
nebulabs-media) al `tool_flow` del Editor Auto.

El cliente configura subtítulos + flecha en la web (editor visual). Aquí lo
traducimos a las herramientas reales: corte de silencios + subtítulos
(`subs_auto`) + flecha CTA opcional (`sticker_arrow`). El orchestrator
reordena por peso, así que el orden de la lista no importa.

Esquema de entrada (web `StyleConfig`):
    {
      "subtitle": {presetId, fontId, mode("word"|"phrase"), x, y, scale},
      "arrow": {enabled, shapeId(".mov"), x, y, scale, rotation},
    }

Las equivalencias de preset son aproximadas (se refinarán). Partimos del
`default_config()` real de cada tool (valores correctos para el servidor) y
solo sobrescribimos las claves visuales relevantes.
"""

from __future__ import annotations

from typing import Any

from src.editor_auto.models import ToolStep
from src.editor_auto.tools import REGISTRY

# Mapa presetId (web `SUB_PRESETS`) → claves visuales del motor `subs_auto`.
# La web define 10 estilos con CSS aproximado; aquí los reproducimos con las
# claves reales del render (text_color/stroke/highlight_mode/pill…). El motor
# lee estas claves directamente, así que el resultado coincide con la web.
# highlight_mode ∈ {pill, color_swap, underline, box_outline, glow, none}.
# Cada estilo: text/hl/stroke/sw(stroke px)/mode(highlight)/pill + font (ttf).
_PRESET_STYLES: dict[str, dict] = {
    "clean":         {"text": "#FFFFFF", "hl": "#FFFFFF", "stroke": "#000000", "sw": 2, "mode": "none",       "pill": False, "font": "Montserrat-ExtraBold.ttf"},
    "purple-pill":   {"text": "#FFFFFF", "hl": "#7C3AED", "stroke": "#000000", "sw": 0, "mode": "pill",       "pill": True,  "font": "Montserrat-Black.ttf"},
    "red-pill":      {"text": "#FFFFFF", "hl": "#EF2D2D", "stroke": "#000000", "sw": 0, "mode": "pill",       "pill": True,  "font": "Montserrat-Black.ttf"},
    "blue-pill":     {"text": "#FFFFFF", "hl": "#2563EB", "stroke": "#000000", "sw": 0, "mode": "pill",       "pill": True,  "font": "Montserrat-Black.ttf"},
    "yellow-swap":   {"text": "#FFFFFF", "hl": "#FDE047", "stroke": "#000000", "sw": 2, "mode": "color_swap", "pill": False, "font": "Montserrat-Black.ttf"},
    "cyan-swap":     {"text": "#FFFFFF", "hl": "#22D3EE", "stroke": "#000000", "sw": 2, "mode": "color_swap", "pill": False, "font": "Montserrat-Black.ttf"},
    "anton-cyan":    {"text": "#22D3EE", "hl": "#22D3EE", "stroke": "#000000", "sw": 0, "mode": "glow",       "pill": False, "font": "anton.ttf", "case": "UPPERCASE"},
    "anton-white":   {"text": "#FFFFFF", "hl": "#FFFFFF", "stroke": "#000000", "sw": 2, "mode": "none",       "pill": False, "font": "anton.ttf", "case": "UPPERCASE"},
    "marker":        {"text": "#FDE047", "hl": "#FDE047", "stroke": "#000000", "sw": 1, "mode": "none",       "pill": False, "font": "PermanentMarker-Regular.ttf"},
    "caveat":        {"text": "#FDE047", "hl": "#FDE047", "stroke": "#000000", "sw": 1, "mode": "none",       "pill": False, "font": "Caveat-Bold.ttf"},
    "bangers":       {"text": "#FFFFFF", "hl": "#FDE047", "stroke": "#000000", "sw": 2, "mode": "color_swap", "pill": False, "font": "Bangers-Regular.ttf"},
    "luckiest":      {"text": "#FFFFFF", "hl": "#FFFFFF", "stroke": "#000000", "sw": 2, "mode": "none",       "pill": False, "font": "LuckiestGuy-Regular.ttf"},
    "fredoka":       {"text": "#FFFFFF", "hl": "#FFFFFF", "stroke": "#000000", "sw": 3, "mode": "none",       "pill": False, "font": "Fredoka-SemiBold.ttf"},
    "typewriter":    {"text": "#FFFFFF", "hl": "#FFFFFF", "stroke": "#000000", "sw": 1, "mode": "none",       "pill": False, "font": "CourierPrime-Bold.ttf"},
    "italic-shadow": {"text": "#FFFFFF", "hl": "#FFFFFF", "stroke": "#000000", "sw": 1, "mode": "none",       "pill": False, "font": "Montserrat-BlackItalic.ttf"},
}
_DEFAULT_PRESET_ID = "clean"

# Pool del modo INTELIGENTE (auto): flechas SIMPLES — entre estas elige el
# motor la de más contraste con el fondo. No incluye los estilos animados para
# no cambiar la FORMA que espera el cliente (solo el color).
_SMART_POOL = {
    "flecha_roja.mov", "flecha_negra.mov", "flecha_blanca.mov",
    "flecha_amarilla.mov", "flecha_cyan.mov", "flecha_verde.mov",
}

# Flechas reales válidas en Assets/flechas (el preflight valida contra esto):
# simples + estilos animados (avanza/pulso/rebote/triple, en blanca y roja).
_ALLOWED_ARROWS = _SMART_POOL | {
    "flecha_avanza_blanca.mov", "flecha_avanza_roja.mov",
    "flecha_pulse_blanca.mov", "flecha_pulse_roja.mov",
    "flecha_bob_blanca.mov", "flecha_bob_roja.mov",
    "flecha_triple_blanca.mov", "flecha_triple_roja.mov",
    "flecha_izq_roja.mov", "flecha_izq_amarilla.mov",
    "flecha_abajo_triple_blanca.mov",
}

# Mapa fontId (web `FONTS`) → candidatos de filename de fuente (registry).
# Se resuelve con fonts_registry.find_by_path (primer match disponible).
_FONT_CANDIDATES: dict[str, list[str]] = {
    # Tipografías reales (bundled en assets/fonts).
    "montserrat":      ["Montserrat-ExtraBold.ttf"],
    "montserratBlack": ["Montserrat-Black.ttf"],
    "montserratItalic": ["Montserrat-BlackItalic.ttf"],
    "anton":           ["anton.ttf", "Anton-Regular.ttf"],
    "luckiest":        ["LuckiestGuy-Regular.ttf"],
    "marker":          ["PermanentMarker-Regular.ttf"],
    "caveat":          ["Caveat-Bold.ttf"],
    "bangers":         ["Bangers-Regular.ttf"],
    "courier":         ["CourierPrime-Bold.ttf"],
    "fredoka":         ["Fredoka-SemiBold.ttf"],
    # Compat con ids antiguos (sistema).
    "sans":      ["calibri.ttf", "segoeui.ttf", "arial.ttf"],
    "black":     ["ariblk.ttf", "impact.ttf", "arialbd.ttf"],
    "rounded":   ["trebucbd.ttf", "trebuc.ttf", "segoeui.ttf"],
    "serif":     ["georgiab.ttf", "georgia.ttf", "times.ttf"],
    "mono":      ["consolab.ttf", "consola.ttf"],
    "handwrite": ["comicbd.ttf", "comic.ttf"],
}


def _resolve_font_path(font_id: str | None, fallback: str) -> str:
    """Resuelve fontId web → path absoluto de fuente del servidor."""
    from src.fonts_registry import find_by_path

    for cand in _FONT_CANDIDATES.get(font_id or "", []):
        entry = find_by_path(cand)
        if entry:
            return str(entry["path"])
    return fallback


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _f(v: Any, default: float) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _with_defaults(tool_id: str, overrides: dict) -> dict:
    """Config = default_config() del tool (server-correcto) + overrides."""
    base: dict = {}
    tool = REGISTRY.get(tool_id)
    if tool is not None:
        try:
            base = dict(tool.default_config())
        except Exception:
            base = {}
    base.update(overrides)
    return base


def build_tool_flow(style: dict | None) -> list[ToolStep]:
    """Devuelve la lista de ToolStep equivalente al estilo del cliente.

    Siempre incluye `silence_cutter` (el corte es el núcleo de la edición) +
    `subs_auto`. Añade `sticker_arrow` solo si el cliente activó la flecha.
    """
    style = style or {}
    sub = style.get("subtitle") or {}
    arr = style.get("arrow") or {}
    cuts = style.get("cuts") or {}

    # Cada herramienta base es OPCIONAL: el cliente puede desactivarla aunque
    # venga incluida (default = activada si no se indica lo contrario).
    steps: list[ToolStep] = []
    if cuts.get("enabled", True):
        steps.append(ToolStep(tool_id="silence_cutter", enabled=True, config=_with_defaults("silence_cutter", {})))

    if not sub.get("enabled", True):
        # Subtítulos desactivados → no añadimos subs_auto. (La flecha se evalúa abajo.)
        if arr.get("enabled"):
            steps.append(_build_arrow_step(arr))
        return steps

    mode = "phrase" if sub.get("mode") == "phrase" else "word"
    pid = sub.get("presetId")
    ps = _PRESET_STYLES.get(pid, _PRESET_STYLES[_DEFAULT_PRESET_ID])
    # Formato de mayúsculas elegido por el cliente (botón "Formato" tipo TikTok).
    # "none" = respeta el caso natural del preset; el resto lo fuerza.
    _CASE_MAP = {"upper": "UPPERCASE", "lower": "lowercase", "title": "Title Case", "none": None}
    case_choice = _CASE_MAP.get(str(sub.get("caseMode") or "none"))
    case_mode = case_choice if case_choice is not None else ps.get("case", "None")
    y = _clamp(_f(sub.get("y"), 0.78), 0.05, 0.95)
    font_scale = round(_clamp(0.045 * _f(sub.get("scale"), 1.0), 0.02, 0.10), 4)
    # Ancho máx. de la caja de subtítulos (fracción del ancho del vídeo). Lo
    # elige el cliente con las asas laterales / slider. Más ancho = más
    # palabras por línea antes de saltar.
    max_width = round(_clamp(_f(sub.get("width"), 0.8), 0.3, 1.0), 3)

    base_subs = _with_defaults("subs_auto", {})
    # Fuente: la del fontId elegido; si no resuelve, la tipografía propia del
    # preset (cada estilo trae su .ttf); de último, el default del motor.
    font_path = _resolve_font_path(sub.get("fontId"), "")
    if not font_path and ps.get("font"):
        from src.fonts_registry import find_by_path
        entry = find_by_path(ps["font"])
        if entry:
            font_path = str(entry["path"])
    if not font_path:
        font_path = base_subs.get("font_path", "")
    subs_overrides = {
        "font_path": font_path,
        "text_color": ps["text"],
        "highlight_color": ps["hl"],
        "stroke_color": ps["stroke"],
        "stroke_width": int(ps["sw"]),
        "highlight_mode": ps["mode"],
        "pill_enabled": bool(ps["pill"]),
        "case_mode": case_mode,
        "y_position": y,
        "font_scale": font_scale,
        # "una palabra" fuerza 1; "varias" usa 4.
        "max_words": 1 if mode == "word" else 4,
        # Animación de entrada: pop (escala+fade) SOLO en "una palabra"; en
        # "varias" no animamos (solo cambia el resaltado de la palabra activa).
        "entrance_anim": "pop" if mode == "word" else "none",
        # Ancho de la caja → max_width del motor (subs_auto / subtitles_only).
        "max_width": max_width,
    }
    steps.append(ToolStep(tool_id="subs_auto", enabled=True, config=_with_defaults("subs_auto", subs_overrides)))

    if arr.get("enabled"):
        steps.append(_build_arrow_step(arr))

    return steps


def _build_arrow_step(arr: dict) -> ToolStep:
    """ToolStep de la flecha CTA con saneo de la flecha elegida.

    shapeId == "auto" → modo INTELIGENTE: el motor elige la flecha (forma+
    color) de más contraste con el fondo en la zona del CTA, entre todas las
    flechas disponibles."""
    rot = int(_f(arr.get("rotation"), 0)) % 360
    shape = str(arr.get("shapeId") or "").strip()
    smart = shape == "auto"
    if not smart and shape not in _ALLOWED_ARROWS:
        # Valores viejos/ inválidos (p.ej. "simple" de presets SVG antiguos)
        # caen a flecha_roja.mov, si no el preflight aborta el job.
        shape = "flecha_roja.mov"
    arrow_overrides = {
        # En smart usamos una por defecto pero el motor la sobrescribe.
        "sticker_file": "flecha_roja.mov" if smart else shape,
        "color_mode": "smart" if smart else "fixed",
        "candidate_stickers": sorted(_SMART_POOL) if smart else [],
        "position_x_pct": round(_clamp(_f(arr.get("x"), 0.5) * 100, 0, 100), 1),
        "position_y_pct": round(_clamp(_f(arr.get("y"), 0.5) * 100, 0, 100), 1),
        "scale_width_pct": round(_clamp(25.0 * _f(arr.get("scale"), 1.0), 5, 80), 1),
        "rotation_deg": rot,
    }
    return ToolStep(tool_id="sticker_arrow", enabled=True, config=_with_defaults("sticker_arrow", arrow_overrides))
