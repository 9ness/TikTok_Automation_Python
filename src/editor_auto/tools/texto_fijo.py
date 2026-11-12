"""Texto fijo quemado en todo el vídeo (12/11/2026).

Pensado para el NOMBRE DEL PRODUCTO de los vídeos que mandan los agentes
(refuerzo anti-sanción de TikTok Shop: que se vea qué producto es). Va el
último (peso 95), encima de rótulos, flecha y subtítulos, cuando ya no hay
zooms que lo corten. `vip_overlays` deja libre su franja con `franja_reservada`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..config import TOOL_POSITION_WEIGHTS, TOOL_TEXTO_FIJO
from .base import ToolContext, ToolDescriptor

_REPO = Path(__file__).resolve().parents[3]
_FONT = _REPO / "assets" / "fonts" / "Montserrat-Black.ttf"


def filtro(textfile: str, cfg: dict[str, Any], alto: int = 1920) -> str:
    """Filtro drawtext; el texto va en un fichero (`textfile`) para no escaparlo."""
    font = cfg.get("font_path") or str(_FONT)
    tam = int(cfg.get("font_size") or 56)
    y = float(cfg.get("y_pct", 10.0)) / 100
    caja = cfg.get("box_color")
    px = lambda n: max(1, round(n * alto / 1920))  # noqa: E731 — borderw no admite expresiones
    fondo = (f"box=1:boxcolor={caja}:boxborderw={px(28)}:" if caja else
             f"borderw={px(5)}:bordercolor=black@0.9:shadowx=0:shadowy={px(3)}:shadowcolor=black@0.5:")
    return (f"drawtext=fontfile='{font}':textfile='{textfile}':fontsize=h*{tam}/1920:"
            f"fontcolor={cfg.get('color') or 'white'}:{fondo}"
            f"x=(w-text_w)/2:y=h*{y:.4f}")


class TextoFijoTool:
    tool_id: str = TOOL_TEXTO_FIJO
    display_name: str = "🏷️ Texto fijo (nombre del producto)"
    description: str = "Quema un texto fijo arriba durante todo el vídeo, p. ej. el nombre del producto."
    position_weight: int = TOOL_POSITION_WEIGHTS.get(TOOL_TEXTO_FIJO, 95)

    def default_config(self) -> dict[str, Any]:
        # y 10 %: debajo de las pestañas de TikTok (zona segura). Sin caja:
        # blanco con contorno; `box_color` la pone, con margen holgado.
        return {"texto": "", "y_pct": 10.0, "font_size": 56, "color": "white",
                "box_color": "", "font_path": str(_FONT)}

    def config_schema(self) -> list[dict[str, Any]]:
        return [
            {"key": "texto", "label": "Texto (p. ej. nombre del producto)", "type": "text"},
            {"key": "y_pct", "label": "Altura (% desde arriba)", "type": "number", "min": 0, "max": 90},
        ]

    def descriptor(self) -> ToolDescriptor:
        return ToolDescriptor(
            tool_id=self.tool_id, display_name=self.display_name, description=self.description,
            position_weight=self.position_weight,
            default_config=self.default_config(), config_schema=self.config_schema(),
        )

    def run(self, *, input_path: str, output_path: str, config: dict[str, Any],
            ctx: ToolContext) -> str:
        cfg = {**self.default_config(), **(config or {})}
        texto = str(cfg.get("texto") or "").strip()
        if not texto:
            ctx.on_log("[texto_fijo] Sin texto — no toco el vídeo.")
            return _copiar(input_path, output_path)
        try:
            carpeta = Path(ctx.temp_folder or "/tmp")
            carpeta.mkdir(parents=True, exist_ok=True)
            fichero = carpeta / f"texto_fijo_{ctx.job_id}.txt"
            fichero.write_text(" ".join(texto.split()), encoding="utf-8")
            subprocess.run(
                ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", input_path, "-vf", filtro(str(fichero), cfg, _alto(input_path)),
                 "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
                 "-c:a", "copy", "-movflags", "+faststart", output_path],
                check=True, capture_output=True, timeout=900)
            ctx.on_progress(1.0, f"🏷️ «{texto}» quemado")
            return output_path
        except Exception as e:  # noqa: BLE001 — nunca rompe el flujo
            err = getattr(e, "stderr", b"") or b""
            ctx.on_log(f"[texto_fijo] ⚠️ No pude quemar el texto ({str(e)[-200:]} "
                       f"{err.decode(errors='ignore')[-300:]}) — sigo sin él.")
            return _copiar(input_path, output_path)


def _alto(ruta: str) -> int:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                              "stream=height", "-of", "csv=p=0", ruta],
                             capture_output=True, text=True, timeout=60).stdout.strip()
        return int(out.splitlines()[0])
    except Exception:  # noqa: BLE001
        return 1920


def _copiar(src: str, dst: str) -> str:
    if os.path.abspath(src) != os.path.abspath(dst):
        shutil.copyfile(src, dst)
    return dst
