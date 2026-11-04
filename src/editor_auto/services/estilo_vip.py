"""Estilo VIP desde un vídeo de referencia del cliente, o contado con palabras.

El cliente enseña un vídeo con la edición que le gusta y de ahí sale la config
de `vip_overlays` (colores de las píldoras, fuente, densidad, zooms, notas
para la IA). Se guarda en su flujo y desde entonces todos sus vídeos salen con
ese estilo. Una llamada de visión (hoja de 24 fotogramas, ~0,001 $ con Haiku).
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
from pathlib import Path

from src import cost_tracking

from .revision_visual import _fotogramas, _hoja

# Más que la revisión (16): las fotos de apoyo duran ~2 s y con 16 se escapaban.
N_FOTOGRAMAS = 24

_PROMPT = Path(__file__).resolve().parent.parent / "prompts" / "vip_estilo_referencia.md"
_PROMPT_TEXTO = _PROMPT.with_name("vip_estilo_texto.md")
_FONTS = Path(__file__).resolve().parents[3] / "assets" / "fonts"
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _fuentes() -> dict[str, str]:
    return {p.stem: str(p) for p in sorted(_FONTS.glob("*.ttf")) if "Emoji" not in p.stem}


def estilo_desde_video(video: str) -> dict:
    """Devuelve la config parcial de `vip_overlays` para ese estilo. Lanza si falla."""
    dur = float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
        timeout=60).decode().strip())
    jpg = _hoja(_fotogramas(video, dur, N_FOTOGRAMAS))
    fuentes = _fuentes()
    instr = (_PROMPT.read_text(encoding="utf-8").replace("{n}", str(N_FOTOGRAMAS))
             .replace("{dur}", f"{dur:.0f}").replace("{fuentes}", ", ".join(fuentes)))
    data = _pedir([
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                     "data": base64.b64encode(jpg).decode()}},
        {"type": "text", "text": instr}])
    return _a_config(data, fuentes)


def estilo_desde_texto(texto: str) -> dict:
    """Lo mismo, pero el cliente lo cuenta con palabras. Solo trae lo que diga:
    lo que no mencione no se toca en su flujo. Una llamada de texto (~0,0005 $)."""
    fuentes = _fuentes()
    instr = (_PROMPT_TEXTO.read_text(encoding="utf-8").replace("{fuentes}", ", ".join(fuentes))
             .replace("{texto}", texto.strip()[:3000]))
    return _a_config(_pedir([{"type": "text", "text": instr}]), fuentes)


def _pedir(content: list) -> dict:
    from src.editor_auto.api import claude_client

    m = claude_client.modelo()
    resp = claude_client._client().messages.create(
        model=m, max_tokens=16000, messages=[{"role": "user", "content": content}])
    try:
        cost_tracking.record_claude(input_tokens=int(resp.usage.input_tokens or 0),
                                    output_tokens=int(resp.usage.output_tokens or 0),
                                    model=m, detail=f"editor_auto.estilo_vip ({m})")
    except Exception:  # noqa: BLE001
        pass
    raw = "".join(b.text for b in resp.content if b.type == "text")
    if "{" not in raw:
        raise RuntimeError(f"estilo_vip: la IA no devolvió JSON (stop_reason={resp.stop_reason})")
    return json.loads(raw[raw.find("{"): raw.rfind("}") + 1])


def _a_config(data: dict, fuentes: dict[str, str]) -> dict:
    """JSON de la IA → config parcial de vip_overlays (+ `_flujo` para el resto).
    Una clave ausente no se pone: con texto, lo que el cliente no dijo se queda."""
    cfg: dict = {}
    for k in ("color_alerta", "color_dato", "color_ok", "color_neutro"):
        if _HEX.match(str(data.get(k, ""))):
            cfg[k] = data[k].upper()
    if cfg:  # los colores solo cuentan en "personalizado"; sin colores, su preset sigue
        cfg["preset"] = "personalizado"
    if data.get("fuente") in fuentes:
        cfg["font_path"] = fuentes[data["fuente"]]
    if data.get("densidad_rotulos") in ("baja", "media", "alta"):
        cfg["densidad_rotulos"] = data["densidad_rotulos"]
    for k in ("gancho", "fotos", "zooms", "color_grade"):
        if isinstance(data.get(k), bool):
            cfg[k] = data[k]
    y = _clamp(data.get("rotulo_y_pct"), 5, 60)
    if y is not None:
        cfg["rotulo_y_pct"] = y
    if data.get("notas_estilo"):
        cfg["notas_estilo"] = str(data["notas_estilo"])[:1500]
    # Lo que no es de vip_overlays (subtítulos, flecha) va aparte: la UI lo
    # mezcla en esos pasos del flujo si el usuario los tiene.
    flujo = {}
    subs = _subs_cfg(data.get("subs"))
    if subs:
        flujo["subs_auto"] = subs
    flecha = _flecha_cfg(data.get("flecha"))
    if flecha:
        flujo["sticker_arrow"] = flecha
    if flujo:
        cfg["_flujo"] = flujo
    return cfg


_RESALTADO = {"color": "color_swap", "pildora": "pill", "subrayado": "underline",
              "ninguno": "none"}


def _clamp(v, lo: float, hi: float) -> float | None:
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return None


def _subs_cfg(d) -> dict:
    """Estilo de subtítulos visto en la referencia → config parcial de `subs_auto`."""
    if not isinstance(d, dict) or d.get("hay") is False:
        return {}
    out: dict = {}
    modo = _RESALTADO.get(str(d.get("resaltado", "")).lower())
    if modo:
        out["highlight_mode"] = modo
    for k_in, k_out in (("color_texto", "text_color"), ("color_resaltado", "highlight_color")):
        if _HEX.match(str(d.get(k_in, ""))):
            out[k_out] = d[k_in].upper()
    n = _clamp(d.get("palabras"), 1, 6)
    if n is not None:
        out["max_words"] = int(round(n))
    y = _clamp(d.get("y_pct"), 40, 92)
    if y is not None:
        out["y_position"] = round(y / 100, 3)
    if isinstance(d.get("mayusculas"), bool):
        out["case_mode"] = "UPPERCASE" if d["mayusculas"] else "None"
    return out


# Color de cada nombre del banco de flechas (`flecha_<forma>_<color>.mov`).
_COLORES_FLECHA = {
    "roja": (230, 40, 40), "naranja": (255, 140, 0), "amarilla": (253, 215, 50),
    "verde": (34, 197, 94), "cyan": (34, 211, 238), "azul": (40, 100, 235),
    "morada": (140, 60, 200), "rosa": (245, 110, 170), "blanca": (245, 245, 245),
    "negra": (20, 20, 20), "beige": (225, 205, 165), "marron": (125, 80, 45),
    "burdeos": (128, 20, 45),
}


def _flecha_cfg(d) -> dict:
    """Flecha vista en la referencia → la del banco más parecida (color y si es
    triple), fija en vez de "inteligente", y en el mismo sitio."""
    from src.editor_auto.tools.sticker_arrow import arrows_folder

    if not isinstance(d, dict) or d.get("hay") is False or not _HEX.match(str(d.get("color", ""))):
        return {}
    c = tuple(int(d["color"][i:i + 2], 16) for i in (1, 3, 5))
    try:
        banco = sorted(p.name for p in Path(arrows_folder()).glob("flecha_*.mov"))
    except Exception:  # noqa: BLE001
        return {}
    # Solo formas que apuntan al carrito: sencilla o triple hacia abajo.
    forma = r"abajo_triple_" if d.get("triple") else r""
    pool = [(n, _COLORES_FLECHA[m.group(1)]) for n in banco
            if (m := re.fullmatch(rf"flecha_{forma}([a-z]+)\.mov", n)) and m.group(1) in _COLORES_FLECHA]
    if not pool:
        return {}
    nombre = min(pool, key=lambda p: sum((a - b) ** 2 for a, b in zip(p[1], c)))[0]
    out: dict = {"sticker_file": nombre, "color_mode": "fixed"}
    x = _clamp(d.get("x_pct"), 0, 100)
    y = _clamp(d.get("y_pct"), 0, 100)
    if x is not None and y is not None:
        out["position_x_pct"], out["position_y_pct"] = round(x, 1), round(y, 1)
    return out


if __name__ == "__main__":  # python -m src.editor_auto.services.estilo_vip <video>
    import sys
    arg = sys.argv[1]
    f = estilo_desde_video if len(arg) < 255 and Path(arg).is_file() else estilo_desde_texto
    print(json.dumps(f(arg), ensure_ascii=False, indent=1))
