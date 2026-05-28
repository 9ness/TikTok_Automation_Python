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
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal


LogCallback = Callable[[str], None]


def _noop(_msg: str) -> None: ...


WatermarkType = Literal["veo_flow", "gemini_chat", "auto"]


def next_clean_filename(folder: str | Path) -> str:
    """Devuelve el siguiente nombre `<N>_clean.mp4` disponible en `folder`.
    Si la carpeta no existe o está vacía → `1_clean.mp4`. Si ya hay
    `1_clean.mp4` y `3_clean.mp4`, devuelve `4_clean.mp4` (toma max+1
    para no reusar números obsoletos por archivos borrados manualmente)."""
    folder_p = Path(folder)
    if not folder_p.is_dir():
        return "1_clean.mp4"
    pattern = re.compile(r"^(\d+)_clean\.mp4$", re.IGNORECASE)
    nums: list[int] = []
    for entry in folder_p.iterdir():
        m = pattern.match(entry.name)
        if m:
            try:
                nums.append(int(m.group(1)))
            except ValueError:
                pass
    next_n = (max(nums) + 1) if nums else 1
    return f"{next_n}_clean.mp4"


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
    # Coords como TOP-LEFT del bounding box (no centro). Frame 720×1280:
    # texto aprox bounding (615, 1215) tamaño 80×40. Margen extra de
    # seguridad por descendentes (letras g/j) y antialiasing.
    "veo_flow": WatermarkBox(
        x_pct=85.0, y_pct=94.5, w_pct=14.0, h_pct=5.0,
        label="Veo Flow",
    ),
    # Gemini Chat: estrella sparkle 4-puntas (logo Gemini).
    # Frame 720×1280: star center ≈(605, 1190), tamaño star+puntas ≈60×60.
    # Top-left → (575, 1160). Margen extra por puntas brillantes que se
    # extienden con anti-aliasing.
    "gemini_chat": WatermarkBox(
        x_pct=79.0, y_pct=90.0, w_pct=10.0, h_pct=6.0,
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
    """Convierte WatermarkBox % a (x, y, w, h) en píxeles. Añade padding
    de seguridad (+6px en cada lado) — cubre antialiasing, puntas
    brillantes y descendentes que se pasan del bounding visible.

    ffmpeg `delogo` requiere que la caja tenga ≥1px de borde dentro del
    frame (necesario para interpolación). Es decir x≥1, y≥1, x+w<width,
    y+h<height (estricto, no <=). Si la caja toca el borde, ffmpeg
    aborta con 'Could not open encoder before EOF'. Clampamos al margen
    seguro de 1px."""
    # Mínimo 1px desde el borde superior/izquierdo (delogo necesita
    # vecinos para interpolar).
    x = max(1, int(round(width * box.x_pct / 100.0)) - 6)
    y = max(1, int(round(height * box.y_pct / 100.0)) - 6)
    w = int(round(width * box.w_pct / 100.0)) + 12
    h = int(round(height * box.h_pct / 100.0)) + 12
    # Clamp para que x+w < width Y y+h < height (estricto).
    # Dejamos 1px de margen del borde derecho/inferior.
    if x + w >= width:
        w = width - x - 1
    if y + h >= height:
        h = height - y - 1
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
    # NOTA: el param `band=N` fue removed en ffmpeg modernos (era para
    # fade-out edge). Compensamos con padding extra en _box_to_pixels
    # (+6px por lado) — cubre antialiasing del watermark sin necesidad
    # del fade-out del filtro.
    delogo_filters: list[str] = []
    for box in boxes:
        x, y, w, h = _box_to_pixels(box, width, height)
        delogo_filters.append(
            f"delogo=x={x}:y={y}:w={w}:h={h}:show=0"
        )
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

    # ---- 1) Dimensiones + crop region ----
    width, height = _ffprobe_dimensions(input_path)
    log_callback(f"📐 Vídeo {width}×{height}px detectado")

    # Estrategia "crop + inpaint + composite": ProPainter procesa solo la
    # esquina inferior-derecha (donde están todos los watermarks). El
    # resto del frame queda INTACTO a calidad original. Esto evita el
    # CUDA OOM que ocurre al pasar el frame completo a la GPU A40, y
    # permite usar fp32 + resize_ratio=1.0 sin perder ni un píxel de
    # calidad fuera de la zona del watermark.
    crop_x, crop_y, crop_w, crop_h = _compute_crop_region(width, height)
    log_callback(
        f"✂️ Crop esquina inferior-derecha: ({crop_x},{crop_y}) {crop_w}×{crop_h}px "
        f"(resto del frame intacto)"
    )

    tmp_dir = tempfile.mkdtemp(prefix="propainter_")
    crop_video_path = os.path.join(tmp_dir, "crop.mp4")
    mask_path = os.path.join(tmp_dir, "mask.png")
    inpainted_crop_path = os.path.join(tmp_dir, "crop_inpainted.mp4")

    try:
        # ---- 2) ffmpeg: recortar zona watermark del vídeo original ----
        log_callback(f"🎬 Recortando zona watermark con ffmpeg…")
        _ffmpeg_crop_video(input_path, crop_video_path, crop_x, crop_y, crop_w, crop_h)

        # ---- 3) Generar máscara relativa al crop ----
        _generate_mask_for_crop(
            width, height, crop_x, crop_y, crop_w, crop_h,
            watermark_type, mask_path,
        )
        log_callback(f"🎨 Máscara crop-relativa generada ({watermark_type})")

        # ---- 4) Encode crop + máscara como data URIs ----
        # Replicate Files API devuelve URLs sin extension, lo que rompe
        # ProPainter (rechaza mask sin .png, falla parsing video).
        # Solución: data:URI inline. El crop pesa <500KB típicamente,
        # así que base64 es trivial.
        import base64 as _b64
        with open(crop_video_path, "rb") as _vf:
            video_b64 = _b64.b64encode(_vf.read()).decode("ascii")
        video_url = f"data:video/mp4;base64,{video_b64}"
        with open(mask_path, "rb") as _mf:
            mask_b64 = _b64.b64encode(_mf.read()).decode("ascii")
        mask_url = f"data:image/png;base64,{mask_b64}"
        log_callback(
            f"📦 Crop {len(video_b64)/1024:.1f} KB · "
            f"máscara {len(mask_b64)/1024:.1f} KB (base64)"
        )

        # ---- 5) Crear prediction ProPainter (full quality, sin downsampling) ----
        log_callback(f"🪄 Encolando ProPainter en zona watermark…")
        job = pp.submit_propainter(video_url=video_url, mask_url=mask_url)
        log_callback(
            f"⏳ ProPainter prediction {job.prediction_id[:8]} encolado"
        )

        # ---- 6) Polling ----
        def _hb(elapsed: int, status: str) -> None:
            log_callback(
                f"⏳ ProPainter: {elapsed}s (status={status})…"
            )

        pp.wait(job, on_heartbeat=_hb)

        # ---- 7) Download crop inpainted ----
        log_callback(f"⬇️ Descargando crop reconstruido…")
        pp.download(job.output_url or "", inpainted_crop_path)

        if not Path(inpainted_crop_path).is_file() or Path(inpainted_crop_path).stat().st_size < 1000:
            raise WatermarkRemoverError(
                "ProPainter corrió pero el crop output está vacío o corrupto"
            )

        # ---- 8) ffmpeg: composite crop sobre vídeo original ----
        log_callback(f"🧩 Composing crop reconstruido sobre vídeo original…")
        _ffmpeg_composite_overlay(
            input_path, inpainted_crop_path, output_path,
            crop_x, crop_y,
        )

        out_size_mb = Path(output_path).stat().st_size / (1024 * 1024)
        log_callback(
            f"✅ Magic Eraser OK · {out_size_mb:.2f} MB · "
            f"GPU={job.gpu_seconds or 'n/a'}s"
        )
        return output_path, job.gpu_seconds
    finally:
        # Cleanup temp files
        for p in (crop_video_path, mask_path, inpainted_crop_path):
            try:
                Path(p).unlink(missing_ok=True)
            except OSError:
                pass
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass


def _compute_crop_region(width: int, height: int) -> tuple[int, int, int, int]:
    """Devuelve (x, y, w, h) del crop que cubre la zona donde aparecen
    los watermarks (esquina inferior-derecha) + contexto suficiente para
    que ProPainter pueda hacer optical flow.

    Para 9:16 vertical estándar TikTok: bottom-right corner, ~40% del
    ancho × ~15% del alto. Para 720×1280 da 288×192px (mucho menos que
    el 720×1280 entero que daba CUDA OOM)."""
    # Cubre tanto Veo Flow (x: 85-100%, y: 94.5-99.5%) como Gemini Chat
    # (x: 79-89%, y: 90-96%). Margen extra de ~20% para context temporal.
    crop_x = int(round(width * 0.55))
    crop_y = int(round(height * 0.83))
    crop_w = width - crop_x
    crop_h = height - crop_y
    # ffmpeg / libx264 requieren dimensiones pares
    if crop_w % 2:
        crop_w -= 1
    if crop_h % 2:
        crop_h -= 1
    # Y coordinates pares también (algunos codecs)
    if crop_x % 2:
        crop_x += 1
        crop_w -= 1
    if crop_y % 2:
        crop_y += 1
        crop_h -= 1
    return crop_x, crop_y, crop_w, crop_h


def _ffmpeg_crop_video(
    input_path: str, output_path: str,
    x: int, y: int, w: int, h: int,
) -> None:
    """Recorta una región rectangular del vídeo con ffmpeg. Re-encode
    H264 CRF 18 (sin pérdida visible) para que ProPainter pueda procesar."""
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", f"crop={w}:{h}:{x}:{y}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-an",  # sin audio en el crop — no lo necesitamos
        output_path,
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=True)
    except subprocess.CalledProcessError as e:
        raise WatermarkRemoverError(
            f"ffmpeg crop falló (exit {e.returncode}): {e.stderr[-400:]}"
        )


def _generate_mask_for_crop(
    orig_width: int, orig_height: int,
    crop_x: int, crop_y: int, crop_w: int, crop_h: int,
    watermark_type: WatermarkType,
    output_path: str,
    *, dilation_px: int = 6,
) -> str:
    """Genera máscara PNG para el CROP (no para el frame entero). Las
    coordenadas del watermark se traducen del frame original a relativas
    al crop."""
    try:
        from PIL import Image, ImageDraw
    except ImportError as e:
        raise WatermarkRemoverError(f"PIL/Pillow no instalado: {e}")

    img = Image.new("L", (crop_w, crop_h), color=0)
    draw = ImageDraw.Draw(img)

    if watermark_type == "auto":
        boxes = [WATERMARK_BOXES["veo_flow"], WATERMARK_BOXES["gemini_chat"]]
    elif watermark_type in WATERMARK_BOXES:
        boxes = [WATERMARK_BOXES[watermark_type]]
    else:
        raise WatermarkRemoverError(f"watermark_type inválido: {watermark_type}")

    for box in boxes:
        # Coords en frame original
        ox, oy, ow, oh = _box_to_pixels(box, orig_width, orig_height)
        # Traducir a relativo al crop
        cx = ox - crop_x - dilation_px
        cy = oy - crop_y - dilation_px
        cw = ow + 2 * dilation_px
        ch = oh + 2 * dilation_px
        # Clamp al crop bounds
        cx = max(0, cx)
        cy = max(0, cy)
        if cx + cw > crop_w:
            cw = crop_w - cx
        if cy + ch > crop_h:
            ch = crop_h - cy
        if cw > 0 and ch > 0:
            draw.rectangle([cx, cy, cx + cw, cy + ch], fill=255)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    img.save(output_path, "PNG")
    return output_path


def _ffmpeg_composite_overlay(
    base_video_path: str, overlay_video_path: str, output_path: str,
    x: int, y: int,
) -> None:
    """Compone el `overlay_video` (crop reconstruido) sobre el
    `base_video` (original full-res) en la posición (x, y). El audio
    del original se preserva sin re-encode."""
    cmd = [
        "ffmpeg", "-y",
        "-i", base_video_path,
        "-i", overlay_video_path,
        "-filter_complex", f"[0:v][1:v]overlay={x}:{y}:format=auto[outv]",
        "-map", "[outv]",
        "-map", "0:a?",  # audio del original (si existe)
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart",
        output_path,
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=True)
    except subprocess.CalledProcessError as e:
        raise WatermarkRemoverError(
            f"ffmpeg composite falló (exit {e.returncode}): {e.stderr[-400:]}"
        )
