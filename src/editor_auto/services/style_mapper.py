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
_PRESET_STYLES: dict[str, dict] = {
    "classic":     {"text": "#FFFFFF", "hl": "#FFFFFF", "stroke": "#000000", "sw": 2, "mode": "none",       "pill": False},
    "yellow":      {"text": "#FFE600", "hl": "#FFE600", "stroke": "#000000", "sw": 2, "mode": "none",       "pill": False},
    "pill-black":  {"text": "#FFFFFF", "hl": "#000000", "stroke": "#000000", "sw": 0, "mode": "pill",       "pill": True},
    "pill-white":  {"text": "#000000", "hl": "#FFFFFF", "stroke": "#FFFFFF", "sw": 0, "mode": "pill",       "pill": True},
    "neon":        {"text": "#FF3EA5", "hl": "#FF3EA5", "stroke": "#000000", "sw": 0, "mode": "glow",       "pill": False},
    "cyan-glow":   {"text": "#22D3EE", "hl": "#22D3EE", "stroke": "#000000", "sw": 0, "mode": "glow",       "pill": False},
    "hard-shadow": {"text": "#FFFFFF", "hl": "#FFFFFF", "stroke": "#000000", "sw": 3, "mode": "none",       "pill": False},
    "thick":       {"text": "#FFFFFF", "hl": "#FFFFFF", "stroke": "#000000", "sw": 4, "mode": "none",       "pill": False},
    "impact":      {"text": "#FFFFFF", "hl": "#FFFFFF", "stroke": "#000000", "sw": 2, "mode": "none",       "pill": False, "case": "UPPERCASE"},
    "gradient":    {"text": "#22D3EE", "hl": "#A855F7", "stroke": "#000000", "sw": 1, "mode": "color_swap", "pill": False},
}
_DEFAULT_PRESET_ID = "classic"

# Únicas flechas reales en Assets/flechas (el preflight valida contra esto).
_ALLOWED_ARROWS = {"flecha_roja.mov", "flecha_negra.mov"}

# Mapa fontId (web `FONTS`) → candidatos de filename de fuente (registry).
# Se resuelve con fonts_registry.find_by_path (primer match disponible).
_FONT_CANDIDATES: dict[str, list[str]] = {
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

    steps: list[ToolStep] = [
        ToolStep(tool_id="silence_cutter", enabled=True, config=_with_defaults("silence_cutter", {})),
    ]

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

    base_subs = _with_defaults("subs_auto", {})
    font_path = _resolve_font_path(sub.get("fontId"), base_subs.get("font_path", ""))
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
    }
    steps.append(ToolStep(tool_id="subs_auto", enabled=True, config=_with_defaults("subs_auto", subs_overrides)))

    if arr.get("enabled"):
        rot = int(_f(arr.get("rotation"), 0)) % 360
        # Saneo: solo existen estas flechas reales. Valores viejos/ inválidos
        # (p.ej. "simple" de presets SVG antiguos) caen a flecha_roja.mov, si no
        # el preflight aborta el job ("'simple' no está en Assets/flechas").
        shape = str(arr.get("shapeId") or "").strip()
        if shape not in _ALLOWED_ARROWS:
            shape = "flecha_roja.mov"
        arrow_overrides = {
            "sticker_file": shape,
            "color_mode": "fixed",
            "position_x_pct": round(_clamp(_f(arr.get("x"), 0.5) * 100, 0, 100), 1),
            "position_y_pct": round(_clamp(_f(arr.get("y"), 0.5) * 100, 0, 100), 1),
            "scale_width_pct": round(_clamp(25.0 * _f(arr.get("scale"), 1.0), 5, 80), 1),
            "rotation_deg": rot,
        }
        steps.append(ToolStep(tool_id="sticker_arrow", enabled=True, config=_with_defaults("sticker_arrow", arrow_overrides)))

    return steps
