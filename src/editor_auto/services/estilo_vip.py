"""Estilo VIP desde un vídeo de referencia del cliente.

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
_FONTS = Path(__file__).resolve().parents[3] / "assets" / "fonts"
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _fuentes() -> dict[str, str]:
    return {p.stem: str(p) for p in sorted(_FONTS.glob("*.ttf")) if "Emoji" not in p.stem}


def estilo_desde_video(video: str) -> dict:
    """Devuelve la config parcial de `vip_overlays` para ese estilo. Lanza si falla."""
    from src.editor_auto.api import claude_client

    dur = float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
        timeout=60).decode().strip())
    jpg = _hoja(_fotogramas(video, dur, N_FOTOGRAMAS))
    fuentes = _fuentes()
    instr = (_PROMPT.read_text(encoding="utf-8").replace("{n}", str(N_FOTOGRAMAS))
             .replace("{dur}", f"{dur:.0f}").replace("{fuentes}", ", ".join(fuentes)))
    m = claude_client.modelo()
    resp = claude_client._client().messages.create(
        model=m, max_tokens=16000,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.b64encode(jpg).decode()}},
            {"type": "text", "text": instr}]}],
    )
    try:
        cost_tracking.record_claude(input_tokens=int(resp.usage.input_tokens or 0),
                                    output_tokens=int(resp.usage.output_tokens or 0),
                                    model=m, detail=f"editor_auto.estilo_vip ({m})")
    except Exception:  # noqa: BLE001
        pass
    raw = "".join(b.text for b in resp.content if b.type == "text")
    if "{" not in raw:
        raise RuntimeError(f"estilo_vip: la IA no devolvió JSON (stop_reason={resp.stop_reason})")
    data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])

    cfg: dict = {"preset": "personalizado"}
    for k in ("color_alerta", "color_dato", "color_ok", "color_neutro"):
        if _HEX.match(str(data.get(k, ""))):
            cfg[k] = data[k].upper()
    if data.get("fuente") in fuentes:
        cfg["font_path"] = fuentes[data["fuente"]]
    if data.get("densidad_rotulos") in ("baja", "media", "alta"):
        cfg["densidad_rotulos"] = data["densidad_rotulos"]
    for k in ("gancho", "fotos", "zooms", "color_grade"):
        if isinstance(data.get(k), bool):
            cfg[k] = data[k]
    try:
        cfg["rotulo_y_pct"] = max(5.0, min(60.0, float(data.get("rotulo_y_pct", 16))))
    except (TypeError, ValueError):
        pass
    cfg["notas_estilo"] = str(data.get("notas_estilo") or "")[:1500]
    return cfg


if __name__ == "__main__":  # python -m src.editor_auto.services.estilo_vip <video>
    import sys
    print(json.dumps(estilo_desde_video(sys.argv[1]), ensure_ascii=False, indent=1))
