"""Quitar marca de agua de vídeos generados por Veo 3 / Gemini.

Veo 3 (Google) y Gemini Flow ponen marca de agua estática en la esquina
inferior-derecha del vídeo:
  - Flow:        texto "Veo" blanco semi-translúcido
  - Chat/Gemini: estrella sparkle 4-puntas (logo Gemini)

Como son posiciones estáticas, usamos el filtro `delogo` de ffmpeg —
diseñado exactamente para esto (originalmente quitar logos de canales de
TV grabados). Difumina la zona con interpolación de píxeles circundantes.

Calidad: muy buena para watermarks pequeños en zona uniforme. Para zonas
con detalles complejos detrás (ej. ojos sobre el watermark) la pérdida
es perceptible pero TikTok-aceptable.

Coordenadas verificadas empíricamente con capturas de vídeos reales
720×1280 (9:16 vertical). Las almacenamos como porcentajes para que
el filtro escale automáticamente a otras resoluciones (1080×1920, 480×854).

Coste: $0 (ffmpeg local, sin API externa).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal


LogCallback = Callable[[str], None]


def _noop(_msg: str) -> None: ...


WatermarkType = Literal["veo_flow", "gemini_chat", "auto"]


@dataclass(frozen=True)
class WatermarkBox:
    """Caja del watermark como porcentajes del frame (0-100)."""
    x_pct: float
    y_pct: float
    w_pct: float
    h_pct: float
    label: str


# Coordenadas medidas sobre frames 720×1280 (capturas reales del user).
# Convertidas a porcentajes para que escalen a 1080×1920 o 480×854 sin
# tocar el código.
WATERMARK_BOXES: dict[str, WatermarkBox] = {
    # Veo Flow: texto "Veo" blanco en esquina inferior-derecha.
    # Frame 720×1280 → x≈635, y≈1230, w≈70, h≈35.
    "veo_flow": WatermarkBox(
        x_pct=88.0, y_pct=96.0, w_pct=10.0, h_pct=3.0,
        label="Veo Flow",
    ),
    # Gemini Chat: estrella sparkle 4-puntas (logo Gemini).
    # Frame 720×1280 → x≈595, y≈1175, w≈45, h≈45.
    "gemini_chat": WatermarkBox(
        x_pct=83.0, y_pct=92.0, w_pct=6.5, h_pct=3.5,
        label="Gemini Chat",
    ),
}


class WatermarkRemoverError(RuntimeError):
    """Error procesando el vídeo (ffmpeg falló, archivo inválido, etc)."""


def _ffprobe_dimensions(input_path: str) -> tuple[int, int]:
    """Devuelve (width, height) del vídeo. Levanta si no se puede leer."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "json", input_path,
            ],
            capture_output=True, text=True, timeout=30, check=True,
        )
    except subprocess.CalledProcessError as e:
        raise WatermarkRemoverError(
            f"ffprobe falló: {e.stderr[:200]}"
        )
    except FileNotFoundError:
        raise WatermarkRemoverError("ffprobe no encontrado en el sistema")
    try:
        data = json.loads(result.stdout)
        stream = data["streams"][0]
        return int(stream["width"]), int(stream["height"])
    except (KeyError, IndexError, ValueError, json.JSONDecodeError) as e:
        raise WatermarkRemoverError(f"ffprobe respuesta inválida: {e}")


def _box_to_pixels(box: WatermarkBox, width: int, height: int) -> tuple[int, int, int, int]:
    """Convierte WatermarkBox % a (x, y, w, h) en píxeles. Añade pequeño
    padding (+2px en cada lado) para asegurar cobertura completa."""
    x = max(0, int(round(width * box.x_pct / 100.0)) - 2)
    y = max(0, int(round(height * box.y_pct / 100.0)) - 2)
    w = min(width - x, int(round(width * box.w_pct / 100.0)) + 4)
    h = min(height - y, int(round(height * box.h_pct / 100.0)) + 4)
    # delogo necesita w >= 4 y h >= 4 (mínimo del filtro).
    w = max(4, w)
    h = max(4, h)
    return x, y, w, h


def remove_watermark(
    input_path: str,
    output_path: str,
    *,
    watermark_type: WatermarkType = "veo_flow",
    log_callback: LogCallback = _noop,
) -> str:
    """Quita la marca de agua del vídeo. Devuelve `output_path`.

    Args:
        input_path: Path al .mp4 de entrada.
        output_path: Path al .mp4 de salida (se crea si no existe).
        watermark_type:
            - "veo_flow": texto "Veo" abajo-derecha (default).
            - "gemini_chat": estrella Gemini abajo-derecha.
            - "auto": aplica AMBAS cajas (cubre los dos casos sin saber el origen).
        log_callback: para emitir progreso a la UI.

    Raises:
        WatermarkRemoverError si ffmpeg falla o el input no es válido.
    """
    in_p = Path(input_path)
    if not in_p.is_file():
        raise WatermarkRemoverError(f"Input no existe: {input_path}")

    width, height = _ffprobe_dimensions(input_path)
    log_callback(f"📐 Vídeo {width}×{height}px detectado")

    if watermark_type == "auto":
        boxes = [WATERMARK_BOXES["veo_flow"], WATERMARK_BOXES["gemini_chat"]]
    elif watermark_type in WATERMARK_BOXES:
        boxes = [WATERMARK_BOXES[watermark_type]]
    else:
        raise WatermarkRemoverError(
            f"watermark_type inválido: {watermark_type}. "
            f"Opciones: {list(WATERMARK_BOXES.keys()) + ['auto']}"
        )

    # Compose filter chain: aplica delogo por cada caja.
    delogo_filters: list[str] = []
    for box in boxes:
        x, y, w, h = _box_to_pixels(box, width, height)
        delogo_filters.append(f"delogo=x={x}:y={y}:w={w}:h={h}:show=0")
        log_callback(
            f"🚿 {box.label} → caja ({x},{y}) {w}×{h}px"
        )
    vfilter = ",".join(delogo_filters)

    # Asegurar directorio output
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", vfilter,
        # Re-encode con calidad alta (CRF 18) — preserva calidad visual.
        # H.264 + preset fast = buen balance velocidad/calidad. Para vídeos
        # de 10s (uso TikTok Shop) tarda 2-4s.
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        # Audio: copia stream original sin re-encode (más rápido + sin pérdida).
        "-c:a", "copy",
        "-movflags", "+faststart",
        output_path,
    ]
    log_callback(f"🎬 Ejecutando ffmpeg delogo…")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600, check=True,
        )
    except subprocess.CalledProcessError as e:
        raise WatermarkRemoverError(
            f"ffmpeg falló (exit {e.returncode}): {e.stderr[-500:]}"
        )
    except subprocess.TimeoutExpired:
        raise WatermarkRemoverError("ffmpeg timeout >10min (vídeo muy largo?)")
    except FileNotFoundError:
        raise WatermarkRemoverError("ffmpeg no encontrado en el sistema")

    if not Path(output_path).is_file() or Path(output_path).stat().st_size < 1000:
        raise WatermarkRemoverError(
            "ffmpeg corrió pero el output está vacío o corrupto"
        )

    out_size_mb = Path(output_path).stat().st_size / (1024 * 1024)
    log_callback(f"✅ Output {out_size_mb:.2f} MB en {output_path}")
    return output_path


def remove_watermark_to_temp(
    input_path: str,
    *,
    watermark_type: WatermarkType = "veo_flow",
    log_callback: LogCallback = _noop,
) -> str:
    """Conveniencia: procesa a un archivo temp y devuelve el path. El
    caller es responsable de borrarlo o moverlo a destino final."""
    suffix = Path(input_path).suffix or ".mp4"
    tmp = tempfile.NamedTemporaryFile(
        prefix="nowatermark_", suffix=suffix, delete=False,
    )
    tmp.close()
    try:
        return remove_watermark(
            input_path, tmp.name,
            watermark_type=watermark_type,
            log_callback=log_callback,
        )
    except Exception:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise


# ═══════════════════════════════════════════════════════════════════════
# Magic Eraser via ProPainter (Replicate)
# ═══════════════════════════════════════════════════════════════════════
def generate_mask_png(
    width: int,
    height: int,
    watermark_type: WatermarkType,
    output_path: str,
    *,
    dilation_px: int = 6,
) -> str:
    """Genera una PNG máscara para ProPainter: negro (preserva) excepto en
    las zonas del watermark donde es blanco (zona a inpaintear).

    `dilation_px` añade margen de seguridad alrededor de la caja para
    asegurar que cubre el watermark completamente (mejor reconstrucción)."""
    try:
        from PIL import Image, ImageDraw
    except ImportError as e:
        raise WatermarkRemoverError(
            f"PIL/Pillow no instalado: {e}. Necesario para ProPainter mask."
        )

    img = Image.new("L", (width, height), color=0)  # negro
    draw = ImageDraw.Draw(img)

    if watermark_type == "auto":
        boxes = [WATERMARK_BOXES["veo_flow"], WATERMARK_BOXES["gemini_chat"]]
    elif watermark_type in WATERMARK_BOXES:
        boxes = [WATERMARK_BOXES[watermark_type]]
    else:
        raise WatermarkRemoverError(
            f"watermark_type inválido: {watermark_type}"
        )

    for box in boxes:
        x, y, w, h = _box_to_pixels(box, width, height)
        # Expansión adicional para ProPainter (gradiente fuerte)
        x = max(0, x - dilation_px)
        y = max(0, y - dilation_px)
        w = min(width - x, w + 2 * dilation_px)
        h = min(height - y, h + 2 * dilation_px)
        draw.rectangle([x, y, x + w, y + h], fill=255)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    img.save(output_path, "PNG")
    return output_path


def remove_watermark_magic(
    input_path: str,
    output_path: str,
    *,
    watermark_type: WatermarkType = "auto",
    log_callback: LogCallback = _noop,
) -> tuple[str, float | None]:
    """Magic Eraser via ProPainter en Replicate. Devuelve
    (output_path, gpu_seconds) — gpu_seconds para tracking de coste real.

    Coste típico (Nvidia A40 @ $0.000725/s, ~2× realtime):
      - 10s clip: ~$0.015
      - 30s clip: ~$0.045

    Mucho mejor calidad que `delogo` (que solo difumina). ProPainter usa
    optical flow temporal — reconstruye lo que había detrás del watermark
    tomando información de frames adyacentes.
    """
    from src.tiktok_shop.api import replicate_propainter as pp

    if not pp.replicate_propainter_is_configured():
        raise WatermarkRemoverError(
            "REPLICATE_API_TOKEN no configurada — Magic Eraser no disponible. "
            "Usa modo `fast` (delogo) o configura el token."
        )

    in_p = Path(input_path)
    if not in_p.is_file():
        raise WatermarkRemoverError(f"Input no existe: {input_path}")

    # ---- 1) Probar dimensiones + generar máscara ----
    width, height = _ffprobe_dimensions(input_path)
    log_callback(f"📐 Vídeo {width}×{height}px detectado")

    tmp_dir = tempfile.mkdtemp(prefix="propainter_mask_")
    mask_path = os.path.join(tmp_dir, "mask.png")
    generate_mask_png(width, height, watermark_type, mask_path)
    log_callback(f"🎨 Máscara generada ({watermark_type})")

    try:
        # ---- 2) Subir vídeo + máscara a Replicate Files API ----
        log_callback(f"⬆️ Subiendo vídeo + máscara a Replicate…")
        video_url = pp.upload_file(input_path)
        mask_url = pp.upload_file(mask_path)

        # ---- 3) Crear prediction ----
        log_callback(f"🪄 Encolando ProPainter…")
        job = pp.submit_propainter(video_url=video_url, mask_url=mask_url)
        log_callback(
            f"⏳ ProPainter prediction {job.prediction_id[:8]} encolado"
        )

        # ---- 4) Polling ----
        def _hb(elapsed: int, status: str) -> None:
            log_callback(
                f"⏳ ProPainter: {elapsed}s (status={status})…"
            )

        pp.wait(job, on_heartbeat=_hb)

        # ---- 5) Download ----
        log_callback(f"⬇️ Descargando resultado…")
        pp.download(job.output_url or "", output_path)

        if not Path(output_path).is_file() or Path(output_path).stat().st_size < 1000:
            raise WatermarkRemoverError(
                "ProPainter corrió pero el output está vacío o corrupto"
            )

        out_size_mb = Path(output_path).stat().st_size / (1024 * 1024)
        log_callback(
            f"✅ Magic Eraser OK · {out_size_mb:.2f} MB · "
            f"GPU={job.gpu_seconds or 'n/a'}s"
        )
        return output_path, job.gpu_seconds
    finally:
        # Cleanup máscara temp
        try:
            Path(mask_path).unlink(missing_ok=True)
            os.rmdir(tmp_dir)
        except OSError:
            pass
