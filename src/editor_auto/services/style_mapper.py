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

# El presetId de la web YA es el nombre EXACTO del preset del motor (la web usa
# los 9 presets reales), así que se pasa directo. Validamos contra esta lista.
_REAL_PRESETS = {
    "🔴 TikTok Classic (Impact + píldora)",
    "🎤 Karaoke Color Swap (Arial Black)",
    "📏 Underline News (Bahnschrift)",
    "🟦 Box Outline (Impact)",
    "💫 Neon Glow (Impact halo)",
    "🎮 Comic Pop (rosa)",
    "⚽ Stadium Yellow (Impact swap)",
    "🟫 Slab Heritage (Rockwell)",
    "📃 Phrase Static (sin marca por palabra)",
}
_DEFAULT_PRESET = "🔴 TikTok Classic (Impact + píldora)"


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
    # presetId ya es el nombre real del preset; si no es válido, default.
    pid = sub.get("presetId")
    preset = pid if pid in _REAL_PRESETS else _DEFAULT_PRESET
    y = _clamp(_f(sub.get("y"), 0.78), 0.05, 0.95)
    font_scale = round(_clamp(0.045 * _f(sub.get("scale"), 1.0), 0.02, 0.10), 4)
    subs_overrides = {
        "preset_name": preset,
        "y_position": y,
        "font_scale": font_scale,
        # "una palabra" fuerza 1; "varias" deja el natural del preset (4).
        "max_words": 1 if mode == "word" else 4,
    }
    steps.append(ToolStep(tool_id="subs_auto", enabled=True, config=_with_defaults("subs_auto", subs_overrides)))

    if arr.get("enabled"):
        rot = int(_f(arr.get("rotation"), 0)) % 360
        arrow_overrides = {
            "sticker_file": str(arr.get("shapeId") or "flecha_roja.mov"),
            "color_mode": "fixed",
            "position_x_pct": round(_clamp(_f(arr.get("x"), 0.5) * 100, 0, 100), 1),
            "position_y_pct": round(_clamp(_f(arr.get("y"), 0.5) * 100, 0, 100), 1),
            "scale_width_pct": round(_clamp(25.0 * _f(arr.get("scale"), 1.0), 5, 80), 1),
            "rotation_deg": rot,
        }
        steps.append(ToolStep(tool_id="sticker_arrow", enabled=True, config=_with_defaults("sticker_arrow", arrow_overrides)))

    return steps
