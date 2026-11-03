"""Revisión visual barata de un vídeo ya editado (revisor automático).

Hoja de 12 fotogramas numerados en UNA imagen → Claude (Haiku) dice si se
entregaría; negros y congelados los mide ffmpeg (gratis y exacto). Coste
~0,001 $ y ~5 s por vídeo (banco 3/11/2026: detectó subtítulo cortado y
negros, sin falsos positivos en salidas buenas; Sonnet daba uno y costaba 15x).

No ve errores de TEXTO (palabra mal escrita): eso lo cubren las comprobaciones
del cortador. Nunca lanza: si algo falla devuelve None y el vídeo se aprueba
como antes. Apagable con `EDITOR_AUTO_REVISION_VISUAL=0`.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path

from src import cost_tracking

logger = logging.getLogger(__name__)

N_FOTOGRAMAS = 12
_ANCHO = 240
_PROMPT = Path(__file__).resolve().parent.parent / "prompts" / "revision_visual.md"


def activa() -> bool:
    on = os.getenv("EDITOR_AUTO_REVISION_VISUAL", "1").strip() not in ("0", "false", "no")
    return on and bool(os.getenv("ANTHROPIC_API_KEY_EDITOR_AUTO"))


def _duracion(video: str) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
        timeout=60,
    )
    return float(out.decode().strip())


def _hoja(video: str, dur: float) -> bytes:
    from PIL import Image, ImageDraw

    frames = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(N_FOTOGRAMAS):
            t = dur * (i + 0.5) / N_FOTOGRAMAS
            p = os.path.join(tmp, f"{i:02d}.jpg")
            subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", video, "-frames:v", "1",
                 "-vf", f"scale={_ANCHO}:-2", "-y", p],
                check=True, timeout=60,
            )
            frames.append(Image.open(p).convert("RGB"))
    w, h = frames[0].size
    cols, g = 4, 8  # separación gris: el negro de un fotograma no se confunde con el fondo
    rows = (len(frames) + cols - 1) // cols
    hoja = Image.new("RGB", (cols * (w + g) + g, rows * (h + g) + g), (128, 128, 128))
    d = ImageDraw.Draw(hoja)
    for i, im in enumerate(frames):
        x, y = g + (i % cols) * (w + g), g + (i // cols) * (h + g)
        hoja.paste(im.resize((w, h)), (x, y))
        d.rectangle([x, y, x + 26, y + 20], fill=(255, 230, 0))
        d.text((x + 5, y + 4), str(i + 1), fill="black")
    buf = io.BytesIO()
    hoja.save(buf, "JPEG", quality=80)
    return buf.getvalue()


def _negros_congelados(video: str) -> tuple[list[str], list[str]]:
    det = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", video, "-vf", "blackdetect=d=0.3,freezedetect=d=3",
         "-an", "-f", "null", "-"],
        capture_output=True, text=True, timeout=600,
    ).stderr
    negros = [l.split("]")[-1].strip() for l in det.splitlines() if "black_start" in l]
    congelados = [l.split("]")[-1].strip() for l in det.splitlines() if "freeze_start" in l]
    return negros, congelados


def revisar(video: str) -> dict | None:
    """{"entregable": bool, "fallos": [...], "nota": str, "negros": [...],
    "congelados": [...]} o None si no se pudo revisar."""
    if not activa() or not video or not os.path.exists(video):
        return None
    try:
        from src.editor_auto.api import claude_client

        dur = _duracion(video)
        jpg = _hoja(video, dur)
        negros, congelados = _negros_congelados(video)
        instr = (_PROMPT.read_text(encoding="utf-8")
                 .replace("{n}", str(N_FOTOGRAMAS)).replace("{dur}", f"{dur:.0f}"))
        m = claude_client.modelo()
        resp = claude_client._client().messages.create(
            model=m, max_tokens=4000,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                             "data": base64.b64encode(jpg).decode()}},
                {"type": "text", "text": instr},
            ]}],
        )
        try:
            cost_tracking.record_claude(
                input_tokens=int(resp.usage.input_tokens or 0),
                output_tokens=int(resp.usage.output_tokens or 0),
                model=m, detail=f"editor_auto.revision_visual ({m})",
            )
        except Exception:  # noqa: BLE001 — el coste nunca rompe la revisión
            pass
        raw = "".join(b.text for b in resp.content if b.type == "text").strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw).strip()
        i = raw.find("{")
        res = json.loads(raw[i:] if i >= 0 else raw)
        res["negros"], res["congelados"] = negros, congelados
        if negros or congelados:
            res["entregable"] = False
        res["entregable"] = bool(res.get("entregable", True))
        return res
    except Exception as e:  # noqa: BLE001 — nunca bloquea una entrega por fallar
        logger.warning("[revision_visual] no pude revisar %s: %s", video, e)
        return None


def resumen(res: dict) -> str:
    partes = [f"#{f.get('fotograma')} {f.get('tipo')}: {f.get('detalle')}" for f in res.get("fallos") or []]
    if res.get("negros"):
        partes.append(f"negros: {'; '.join(res['negros'])}")
    if res.get("congelados"):
        partes.append(f"congelados: {'; '.join(res['congelados'])}")
    return " · ".join(partes) or (res.get("nota") or "")
