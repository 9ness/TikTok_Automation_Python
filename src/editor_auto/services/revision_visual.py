"""Revisión final barata de un vídeo ya editado (revisor automático).

Tres capas, de la gratis a la de pago:
  1. ffmpeg en UNA pasada: negros, congelados, silencio digital largo, vídeo
     sin audio y audio/vídeo de duraciones distintas.
  2. Geometría sin IA sobre los fotogramas: la zona con imagen frente a la
     proporción del ORIGINAL (vídeo desplazado, aplastado o girado). Los
     modelos lo justifican como "bandas de un original horizontal": en el
     banco (3/11/2026) ninguno —Haiku, Sonnet ni Opus— lo veía bien.
  3. Hoja de 16 fotogramas → Haiku: subtítulos cortados, superpuestos o
     atascados, texto tapando la cara, imagen corrupta.

Banco 3/11/2026 (9 salidas reales + 16 estropeadas): Haiku + geometría 23/25,
0 falsos positivos, ~0,0007 $ el vídeo. Sonnet de segunda opinión daba lo
mismo por 15 veces más; Opus, 2 falsos positivos. Lo único que no ve es un
zoom exagerado que corta la cabeza (no lo produce el editor).

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

N_FOTOGRAMAS = 16
_ANCHO = 300
_PROMPT = Path(__file__).resolve().parent.parent / "prompts" / "revision_visual.md"


def activa() -> bool:
    on = os.getenv("EDITOR_AUTO_REVISION_VISUAL", "1").strip() not in ("0", "false", "no")
    return on and bool(os.getenv("ANTHROPIC_API_KEY_EDITOR_AUTO"))


def _probe(video: str) -> dict:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,width,height,duration:stream_side_data=rotation:stream_tags=rotate:format=duration",
         "-of", "json", video],
        timeout=60,
    )
    return json.loads(out)


def _aspecto(probe: dict) -> float | None:
    """ancho/alto TAL COMO SE VE (los .mov del iPhone guardan la rotación aparte)."""
    for s in probe.get("streams", []):
        if s.get("codec_type") == "video" and s.get("width") and s.get("height"):
            w, h = s["width"], s["height"]
            rot = 0
            for sd in s.get("side_data_list") or []:
                if "rotation" in sd:
                    rot = int(float(sd["rotation"]))
            rot = rot or int(float((s.get("tags") or {}).get("rotate", 0) or 0))
            if abs(rot) % 180 == 90:
                w, h = h, w
            return w / h
    return None


def _fotogramas(video: str, dur: float) -> list:
    from PIL import Image

    frames = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(N_FOTOGRAMAS):
            t = dur * (i + 0.5) / N_FOTOGRAMAS
            p = os.path.join(tmp, f"{i:02d}.jpg")
            subprocess.run(
                ["ffmpeg", "-v", "error", "-threads", "2", "-ss", f"{t:.2f}", "-i", video,
                 "-frames:v", "1", "-vf", f"scale={_ANCHO}:-2", "-y", p],
                check=True, timeout=60,
            )
            frames.append(Image.open(p).convert("RGB"))
    return frames


def _hoja(frames: list) -> bytes:
    from PIL import Image, ImageDraw

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
    hoja.save(buf, "JPEG", quality=82)
    return buf.getvalue()


def _caja_contenido(frames: list, umbral: int = 22, minimo: float = 0.8) -> tuple[int, int, int, int]:
    """Caja de lo que NO es negro: una fila/columna es banda si es negra en ≥80 % de los fotogramas."""
    w, h = frames[0].size
    col_neg, fil_neg = [0] * w, [0] * h
    for im in frames:
        px = im.convert("L").resize((w, h)).load()
        for x in range(w):
            if max(px[x, y] for y in range(0, h, 4)) < umbral:
                col_neg[x] += 1
        for y in range(h):
            if max(px[x, y] for x in range(0, w, 4)) < umbral:
                fil_neg[y] += 1
    lim = len(frames) * minimo
    xs = [x for x in range(w) if col_neg[x] < lim]
    ys = [y for y in range(h) if fil_neg[y] < lim]
    if not xs or not ys:
        return (0, 0, w, h)
    return (xs[0], ys[0], xs[-1] + 1, ys[-1] + 1)


def _geometria(frames: list, aspecto_original: float | None) -> str | None:
    w, h = frames[0].size
    x0, y0, x1, y1 = _caja_contenido(frames)
    if x1 - x0 >= w * 0.97 and y1 - y0 >= h * 0.97:
        return None  # la imagen llena el cuadro
    if abs(x0 - (w - x1)) > w * 0.08:
        return f"imagen desplazada: banda negra a un lado ({x0}px / {w - x1}px de {w})"
    asp = (x1 - x0) / (y1 - y0)
    if aspecto_original and abs(asp / aspecto_original - 1) > 0.10:
        return f"imagen deformada o girada: proporción {asp:.2f}, la del original es {aspecto_original:.2f}"
    return None


def _ffmpeg_detecta(video: str, con_audio: bool) -> dict:
    """Una pasada: negros, congelados y (si hay audio) silencio digital + volumen."""
    if con_audio:
        filtros = ["-filter_complex",
                   "[0:v]scale=240:-2,blackdetect=d=0.3,freezedetect=d=3[v];"
                   "[0:a]silencedetect=n=-55dB:d=5,volumedetect[a]",
                   "-map", "[v]", "-map", "[a]"]
    else:
        filtros = ["-vf", "scale=240:-2,blackdetect=d=0.3,freezedetect=d=3", "-an"]
    err = subprocess.run(
        ["ffmpeg", "-v", "info", "-threads", "2", "-i", video, *filtros, "-f", "null", "-"],
        capture_output=True, text=True, timeout=900,
    ).stderr
    lineas = err.splitlines()
    vol = re.search(r"max_volume:\s*(-?[\d.]+|-inf) dB", err)
    return {
        "negros": [l.split("]")[-1].strip() for l in lineas if "black_start" in l],
        "congelados": [l.split("]")[-1].strip() for l in lineas if "freeze_start" in l],
        "silencios": [l.split("]")[-1].strip() for l in lineas if "silence_start" in l],
        "max_volume": None if not vol else (-999.0 if vol.group(1) == "-inf" else float(vol.group(1))),
    }


def _llamar_modelo(jpg: bytes, dur: float, res: str) -> dict:
    from src.editor_auto.api import claude_client

    instr = (_PROMPT.read_text(encoding="utf-8").replace("{n}", str(N_FOTOGRAMAS))
             .replace("{dur}", f"{dur:.0f}").replace("{res}", res))
    m = claude_client.modelo()
    resp = claude_client._client().messages.create(
        model=m, max_tokens=8000,
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
    return json.loads(raw[i:] if i >= 0 else raw)


def revisar(video: str, original: str | None = None) -> dict | None:
    """{"entregable": bool, "fallos": [...], "nota": str, ...} o None si no se
    pudo revisar. `original` es el vídeo de entrada (para la geometría)."""
    if not activa() or not video or not os.path.exists(video):
        return None
    try:
        p = _probe(video)
        dur = float(p["format"]["duration"])
        streams = p.get("streams", [])
        sv = next((s for s in streams if s.get("codec_type") == "video"), None)
        sa = next((s for s in streams if s.get("codec_type") == "audio"), None)
        if sv is None:
            return {"entregable": False, "fallos": [], "nota": "", "tecnicos": ["el archivo no tiene vídeo"]}
        tecnicos: list[str] = []
        if sa is None:
            tecnicos.append("el vídeo no tiene audio")
        elif sa.get("duration") and sv.get("duration") and abs(float(sa["duration"]) - float(sv["duration"])) > 1.0:
            tecnicos.append(f"audio y vídeo duran distinto ({float(sa['duration']):.1f}s / {float(sv['duration']):.1f}s)")

        det = _ffmpeg_detecta(video, sa is not None)
        if det["negros"]:
            tecnicos.append(f"negros: {'; '.join(det['negros'])}")
        if det["congelados"]:
            tecnicos.append(f"congelados: {'; '.join(det['congelados'])}")
        if sa is not None and det["max_volume"] is not None and det["max_volume"] < -40:
            tecnicos.append(f"audio mudo (pico {det['max_volume']} dB)")
        elif det["silencios"]:
            tecnicos.append(f"silencio total de ≥5 s: {'; '.join(det['silencios'])}")

        frames = _fotogramas(video, dur)
        asp_orig = None
        if original and os.path.exists(original):
            try:
                asp_orig = _aspecto(_probe(original))
            except Exception:  # noqa: BLE001
                asp_orig = None
        geo = _geometria(frames, asp_orig)  # sin original solo se mira el desplazamiento
        if geo:
            tecnicos.append(geo)

        res = _llamar_modelo(_hoja(frames), dur, f"{sv.get('width')}x{sv.get('height')}")
        graves = [f for f in res.get("fallos") or [] if f.get("gravedad", "grave") == "grave"]
        res["tecnicos"] = tecnicos
        res["entregable"] = not tecnicos and (res.get("entregable") is not False) and not graves
        return res
    except Exception as e:  # noqa: BLE001 — nunca bloquea una entrega por fallar
        logger.warning("[revision_visual] no pude revisar %s: %s", video, e)
        return None


def resumen(res: dict) -> str:
    partes = list(res.get("tecnicos") or [])
    for f in res.get("fallos") or []:
        if f.get("gravedad", "grave") == "grave":
            fot = f.get("fotogramas") or f.get("fotograma")
            partes.append(f"{f.get('tipo')} (fotogramas {fot}): {f.get('detalle')}")
    return " · ".join(partes) or (res.get("nota") or "")
