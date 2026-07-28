"""Montaje del vídeo final del Nicho POV BOF (Programa 4 — Tiktok Shop AI Pro).

El operador sube un vídeo bruto (generado fuera con Veo3 o Kling) + elige la
voz/frase; esta pieza hace TODA la edición hasta dejar el MP4 listo para
Drive.

Orden del pipeline (cada paso escribe un fichero intermedio en `work_dir`
para poder depurar si algo falla a mitad de camino):

  1. Quitar marca de agua — SOLO si `origen == "veo3"` (Kling no la lleva).
  2. Normalizar a 1080x1920 @ 30fps (cover-fit + crop). Se hace ANTES de
     cuadrar duración porque `duration_match` asume que el vídeo YA tiene el
     tamaño final: solo toca duración, no resolución.
  3. Cuadrar la duración del vídeo con la del audio (`duration_match`, ya
     existente — se reusa tal cual, sin tocarlo).
  4. Quemar el bloque de 3 líneas de texto (gancho / título / CTA).
  5. Superponer la flecha `.mov` (alpha nativo) en el instante detectado con
     Whisper sobre el audio locutado.
  6. Mux del audio final sobre el vídeo (el vídeo llega mudo: los pasos
     2 y 3 lo dejan sin pista de audio).

Reutiliza a propósito el "motor" de texto+emoji+flecha de
`tiktok_shop/pipeline/ready_video.py` (helpers privados, ver
`NICHO_POV_BOF_MODULE.md` → tabla "Piezas del repo que se reutilizan"): es
una decisión de diseño explícita del módulo, no una mezcla accidental de
lógica de programas. Los valores de posición/escala de la flecha en
`ready_video.py` (`_ARROW_CX/_ARROW_CY/_ARROW_SCALE_W`) coinciden con los de
`config.ARROW_CX/CY/SCALE_W` de este módulo, así que reusar su función de
overlay es seguro.
"""

from __future__ import annotations

import random
import re
import subprocess
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from src.font_resolver import _bundled_fonts_dir
from src.nicho_pov_bof import config
from src.nicho_pov_bof.pipeline.duration_match import (
    _run,
    match_video_to_audio,
    probe_duration,
)
from src.tiktok_shop.pipeline.ready_video import (
    _ARROW_FILES,
    _emoji_run_img,
    _overlay_arrow_ffmpeg,
    _pick_arrow,
    _seg_width,
    _split_runs,
)
from src.tiktok_shop.pipeline.watermark_remover import remove_watermark

OnLog = Callable[[str], None]
OnProgress = Callable[[float, str], None]
_noop: OnLog = lambda _msg: None
_noop_progress: OnProgress = lambda _pct, _label: None

# ---------------------------------------------------------------------------
# Colores del glow (ver spec: gancho magenta/rosa, CTA cyan).
# ---------------------------------------------------------------------------
_HOOK_GLOW_COLOR = (255, 0, 170)   # magenta/rosa
_CTA_GLOW_COLOR = (0, 220, 255)    # cyan
_TITLE_STROKE = (0, 0, 0)          # título: blanco con borde negro, sin glow


def _font_path(name: str = "Montserrat-ExtraBold.ttf") -> str:
    """Misma resolución de fuente que `ready_video.py`: bundled del repo, o
    fallback a DejaVu si el asset no está presente en el entorno."""
    p = Path(_bundled_fonts_dir()) / name
    return str(p) if p.exists() else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


# ---------------------------------------------------------------------------
# Paso 1 — Marca de agua
# ---------------------------------------------------------------------------
def _strip_watermark(video_in: Path, out_path: Path, origen: str, on_log: OnLog) -> Path:
    origen = (origen or "").strip().lower()
    if origen == "veo3":
        on_log("[1/6] Veo3 → quitando marca de agua…")
        remove_watermark(
            str(video_in), str(out_path),
            watermark_type="veo_flow", log_callback=on_log,
        )
        return out_path
    if origen == "kling":
        on_log("[1/6] Kling → sin marca de agua, se salta el paso")
        return video_in
    # Origen desconocido: nunca abortamos por esto (regla del proyecto de no
    # romper el pipeline por un dato opcional/raro); asumimos sin marca.
    on_log(f"[1/6] origen desconocido '{origen}' — se asume sin marca de agua")
    return video_in


# ---------------------------------------------------------------------------
# Paso 2 — Normalizar resolución/fps
# ---------------------------------------------------------------------------
def _normalize_resolution(video_in: Path, out_path: Path, on_log: OnLog) -> Path:
    """Cover-fit (escala cubriendo el frame + recorte centrado) a
    1080x1920 @ 30fps. `setsar=1` evita que un SAR raro del vídeo de origen
    deforme el recorte."""
    w, h, fps = config.TARGET_W, config.TARGET_H, config.TARGET_FPS
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},fps={fps},setsar=1"
    )
    _run([
        "ffmpeg", "-y", "-v", "error", "-i", str(video_in),
        "-vf", vf, "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        str(out_path),
    ], on_log)
    return out_path


# ---------------------------------------------------------------------------
# Paso 4 — Bloque de texto (gancho / título / CTA)
# ---------------------------------------------------------------------------
def _render_text_line(
    text: str, *, font_size: int, max_w: int,
    fill: tuple, stroke: tuple, max_lines: int = 1,
) -> "Image.Image | None":
    """Renderiza una línea (o varias, hasta `max_lines`) de texto+emoji a
    PNG con relleno + borde. Mismo enfoque que `ready_video._render_text_png`
    pero con límite de líneas (el título puede ocupar hasta 2)."""
    text = (text or "").strip()
    if not text:
        return None
    font = ImageFont.truetype(_font_path(), font_size)
    stroke_w = max(3, int(font_size * 0.13))
    emoji_size = int(font_size * 0.92)
    gap = int(font_size * 0.06)
    d0 = ImageDraw.Draw(Image.new("RGBA", (10, 10)))

    def w_of(s: str) -> float:
        return _seg_width(_split_runs(s), font, d0, emoji_size, gap)

    # Los saltos de línea que ya trae el texto se RESPETAN: Gemini devuelve el
    # título repartido en columnas de <=4 palabras y ese reparto está pensado
    # para leerse de un vistazo. Solo se re-parte una línea si aun así no cabe.
    lines: list[str] = []
    for bloque in text.split("\n"):
        bloque = bloque.strip()
        if not bloque:
            continue
        cur = ""
        for word in bloque.split():
            test = (cur + " " + word).strip()
            if w_of(test) <= max_w or not cur:
                cur = test
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)

    # Si sobran líneas se DESCARTAN las últimas, no se funden en una sola:
    # fundirlas producía una línea que se salía de la zona segura y aparecía
    # cortada por los lados en el vídeo.
    if len(lines) > max_lines:
        lines = lines[:max_lines]

    line_h = int(font_size * 1.22)
    pad = stroke_w + 10
    line_ws = [w_of(ln) for ln in lines]
    W = int(max(line_ws, default=0)) + pad * 2
    H = line_h * len(lines) + pad * 2
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        x = (W - line_ws[i]) / 2
        y = pad + i * line_h
        for k, t in _split_runs(ln):
            if k == "emoji":
                em = _emoji_run_img(t, emoji_size)
                if em is not None:
                    ey = int(y + (font_size - emoji_size) / 2 + font_size * 0.10)
                    img.paste(em, (int(x), ey), em)
                    x += em.width + gap
            else:
                d.text((x, y), t, font=font, fill=fill,
                       stroke_width=stroke_w, stroke_fill=stroke)
                x += d0.textlength(t, font=font)
    return img


def _add_glow(img: "Image.Image", color: tuple, *, radius: int = 16, passes: int = 2) -> "Image.Image":
    """Añade un halo de color detrás del texto: usa el canal alpha del PNG
    como máscara, la rellena de `color` y la difumina con GaussianBlur
    (varias pasadas = glow más suave/ancho); el texto original se pega
    encima nítido. Devuelve un canvas más grande (margen = 3×radius) para
    que el halo no quede recortado en los bordes."""
    pad = radius * 3
    W, H = img.size
    canvas = Image.new("RGBA", (W + pad * 2, H + pad * 2), (0, 0, 0, 0))
    alpha = img.split()[-1]
    glow_alpha = Image.new("L", canvas.size, 0)
    glow_alpha.paste(alpha, (pad, pad))
    glow_layer = Image.new("RGBA", canvas.size, tuple(color) + (0,))
    glow_layer.putalpha(glow_alpha)
    for _ in range(max(1, passes)):
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius))
    canvas = Image.alpha_composite(canvas, glow_layer)
    canvas.paste(img, (pad, pad), img)
    return canvas


def _render_text_block_png(textos: dict, layout: str = "gancho_cta_titulo") -> "Image.Image | None":
    """Compone las 3 líneas (gancho / título / CTA) en un único PNG
    apilado verticalmente y centrado, listo para hacer overlay estático
    sobre el vídeo.

    `layout` decide el orden de las líneas. Se prueban DOS disposiciones a la
    vez (mitad de los productos cada una) para comparar cuál rinde mejor con
    datos reales, en vez de elegir a ojo:

    - `gancho_cta_titulo`: gancho, CTA y el nombre del producto debajo. Es la
      que usa el curso de referencia.
    - `gancho_titulo_cta`: el nombre en medio y la llamada cerrando el bloque.
    """
    gancho = (textos.get("gancho") or "").strip()
    titulo = (textos.get("titulo") or "").strip()
    cta = (textos.get("cta") or "").strip()
    max_w = int(config.TARGET_W * (config.SAFE_X[1] - config.SAFE_X[0]))

    def _render_gancho():
        if not gancho:
            return None
        # Gancho: MAYÚSCULAS, relleno blanco + glow magenta/rosa.
        im = _render_text_line(
            gancho.upper(), font_size=config.HOOK_FONT_SIZE, max_w=max_w,
            fill=(255, 255, 255), stroke=(0, 0, 0), max_lines=1,
        )
        return _add_glow(im, _HOOK_GLOW_COLOR) if im is not None else None

    def _render_titulo():
        if not titulo:
            return None
        # Título: blanco con borde negro, hasta 2 líneas, SIN glow.
        return _render_text_line(
            titulo, font_size=config.TITLE_FONT_SIZE, max_w=max_w,
            fill=(255, 255, 255), stroke=_TITLE_STROKE, max_lines=3,
        )

    def _render_cta():
        if not cta:
            return None
        # CTA: relleno blanco + glow cyan.
        im = _render_text_line(
            cta, font_size=config.CTA_FONT_SIZE, max_w=max_w,
            fill=(255, 255, 255), stroke=(0, 0, 0), max_lines=1,
        )
        return _add_glow(im, _CTA_GLOW_COLOR) if im is not None else None

    orden = (
        (_render_gancho, _render_titulo, _render_cta)
        if layout == "gancho_titulo_cta"
        else (_render_gancho, _render_cta, _render_titulo)
    )
    parts = [im for im in (render() for render in orden) if im is not None]

    if not parts:
        return None

    line_gap = 16
    block_w = max(p.width for p in parts)
    block_h = sum(p.height for p in parts) + line_gap * (len(parts) - 1)

    # Red de seguridad: el ajuste por palabras mide solo el TEXTO, pero cada
    # línea añade después el borde y el halo, así que el bloque puede acabar
    # más ancho que la zona segura y salir cortado por los lados en TikTok.
    # Si pasa, se reescala el bloque entero (mejor un texto algo menor que uno
    # recortado).
    if block_w > max_w:
        factor = max_w / block_w
        parts = [
            p.resize((max(1, int(p.width * factor)), max(1, int(p.height * factor))),
                     Image.LANCZOS)
            for p in parts
        ]
        block_w = max(p.width for p in parts)
        block_h = sum(p.height for p in parts) + line_gap * (len(parts) - 1)

    block = Image.new("RGBA", (block_w, block_h), (0, 0, 0, 0))
    y = 0
    for p in parts:
        block.paste(p, (int((block_w - p.width) / 2), y), p)
        y += p.height + line_gap
    return block


def _burn_text_block(video_in: Path, textos: dict, out_path: Path, on_log: OnLog,
                     layout: str = "gancho_cta_titulo") -> Path:
    block = _render_text_block_png(textos or {}, layout)
    if block is None:
        on_log("[4/6] sin textos que quemar — se copia el vídeo tal cual")
        _run(["ffmpeg", "-y", "-v", "error", "-i", str(video_in), "-c", "copy",
              str(out_path)], on_log)
        return out_path

    png_path = out_path.with_suffix(".png")
    block.save(png_path)

    # Centro del bloque en TEXT_BLOCK_Y (dentro de la zona segura vertical);
    # clamp para que no se salga por arriba si el bloque es muy alto (3
    # líneas con emojis grandes).
    y_center = config.TEXT_BLOCK_Y * config.TARGET_H
    y_top = int(y_center - block.height / 2)
    safe_top = int(config.SAFE_Y[0] * config.TARGET_H)
    y_top = max(safe_top, y_top)

    _run([
        "ffmpeg", "-y", "-v", "error",
        "-i", str(video_in), "-i", str(png_path),
        "-filter_complex", f"[0:v][1:v]overlay=(main_w-overlay_w)/2:{y_top}[v]",
        "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-c:a", "copy",
        str(out_path),
    ], on_log)
    on_log(f"[4/6] texto quemado (bloque {block.width}x{block.height}px @ y={y_top})")
    return out_path


# ---------------------------------------------------------------------------
# Paso 5 — Flecha .mov
# ---------------------------------------------------------------------------
def _to_wav_16k_mono(audio_path: Path, out_wav: Path, on_log: OnLog) -> None:
    _run([
        "ffmpeg", "-y", "-v", "error", "-i", str(audio_path),
        "-ac", "1", "-ar", "16000", str(out_wav),
    ], on_log)


def _find_arrow_window(audio_path: Path, work_dir: Path, on_log: OnLog) -> tuple[float, float]:
    """Devuelve `(t0, t1)`: ventana en la que debe verse la flecha.

    Transcribe el audio locutado con Whisper y busca la primera palabra que
    contenga alguna de `config.ARROW_KEYWORDS`. La flecha entra
    `ARROW_LEAD_S` segundos ANTES de esa palabra. Si Whisper no detecta
    ninguna palabra gatillo (o falla), la flecha sale desde el principio del
    vídeo — nunca abortamos el pipeline por esto (asset/paso opcional)."""
    try:
        from src.subtitles import transcribe

        wav_path = work_dir / "arrow_audio_16k.wav"
        _to_wav_16k_mono(audio_path, wav_path, on_log)
        words = transcribe(str(wav_path), model_size="base", language="es")
    except Exception as exc:  # noqa: BLE001 — nunca abortar por esto
        on_log(f"[flecha] Whisper falló ({str(exc)[:120]}) — flecha desde el inicio")
        return 0.0, config.ARROW_DURATION_S

    hit = None
    for w in words:
        token = re.sub(r"[^a-záéíóúñ]", "", (w.get("word") or "").lower())
        if any(kw in token for kw in config.ARROW_KEYWORDS):
            hit = w
            break

    if hit is None:
        on_log("[flecha] sin palabra gatillo detectada — flecha desde el inicio")
        return 0.0, config.ARROW_DURATION_S

    t0 = max(0.0, float(hit["start"]) - config.ARROW_LEAD_S)
    on_log(f"[flecha] '{hit['word']}' detectada en {hit['start']:.2f}s → flecha en {t0:.2f}s")
    return t0, t0 + config.ARROW_DURATION_S


def _overlay_arrow(video_in: Path, audio_path: Path, work_dir: Path, out_path: Path, on_log: OnLog) -> Path:
    t0, t1 = _find_arrow_window(audio_path, work_dir, on_log)
    # Rotamos el punto de partida de la lista de flechas al azar por vídeo:
    # aquí no hay concepto de "versión" (a diferencia de ready_video), así
    # que un índice aleatorio basta para dar variedad entre productos.
    arrow_mov = _pick_arrow(random.randrange(len(_ARROW_FILES)))
    if not arrow_mov:
        on_log("[5/6] sin flechas disponibles en disco — se continúa sin ella")
        return video_in
    # OJO: NO se puede reusar `_overlay_arrow_ffmpeg` de ready_video aquí.
    # Esa función se apoya en `-shortest` para cortar el `-stream_loop -1` de
    # la flecha, y eso solo funciona si el vídeo lleva pista de AUDIO. En este
    # pipeline el audio se mezcla DESPUÉS (paso 6), así que el vídeo llega
    # mudo, `-shortest` no tiene nada que acotar y el bucle de la flecha
    # generaba un vídeo de 28 MINUTOS a partir de uno de 13 segundos.
    # Aquí se acota con `-t` explícito, que no depende de que haya audio.
    dur = probe_duration(video_in)
    sw_px = int(config.TARGET_W * config.ARROW_SCALE_W)
    enable = f"between(t,{t0:.3f},{t1:.3f})"
    filter_complex = (
        f"[1:v]scale={sw_px}:-2,format=rgba[s];"
        f"[0:v][s]overlay="
        f"x=(main_w*{config.ARROW_CX})-(overlay_w/2):"
        f"y=(main_h*{config.ARROW_CY})-(overlay_h/2):"
        f"enable='{enable}'[v]"
    )
    try:
        _run([
            "ffmpeg", "-y", "-v", "error",
            "-i", str(video_in),
            "-stream_loop", "-1", "-i", arrow_mov,
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-t", f"{dur:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-movflags", "+faststart", str(out_path),
        ], on_log)
    except RuntimeError as e:
        on_log(f"[5/6] overlay de flecha falló ({e}) — se continúa sin ella")
        return video_in
    return out_path


# ---------------------------------------------------------------------------
# Paso 6 — Mezcla de audio
# ---------------------------------------------------------------------------
def _mux_audio(video_in: Path, audio_in: Path, out_path: Path, on_log: OnLog) -> Path:
    """Sustituye la pista de audio del vídeo por `audio_in` (la locución ya
    recortada de silencios). El vídeo llega mudo desde el paso 3
    (`duration_match` genera el resultado con `-an`), así que esto es un mux
    directo, no una mezcla de varias pistas."""
    _run([
        "ffmpeg", "-y", "-v", "error",
        "-i", str(video_in), "-i", str(audio_in),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart",
        str(out_path),
    ], on_log)
    return out_path


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------
def build_video(
    *,
    raw_video: Path,
    audio_path: Path,
    textos: dict,
    origen: str,
    output_path: Path,
    work_dir: Path,
    layout: str = "gancho_cta_titulo",
    on_log: OnLog = _noop,
    on_progress: OnProgress = _noop_progress,
) -> Path:
    """Monta el vídeo final de un producto del Nicho POV BOF.

    `textos` = {"gancho", "titulo", "cta"} (strings, cualquiera puede venir
    vacío — el bloque de texto omite las líneas ausentes).
    `origen` = "veo3" | "kling" (determina si se quita marca de agua).

    Devuelve `output_path`. Nunca deja un archivo a medias en destino: solo
    se escribe ahí en el último paso (mux de audio), tras el cual el vídeo
    ya está completo.
    """
    raw_video = Path(raw_video)
    audio_path = Path(audio_path)
    output_path = Path(output_path)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    on_progress(0.0, "Preparando…")

    # 1) Marca de agua
    no_wm = _strip_watermark(raw_video, work_dir / "01_no_watermark.mp4", origen, on_log)
    on_progress(0.10, "Marca de agua")

    # 2) Normalizar resolución/fps
    on_log("[2/6] Normalizando a 1080x1920 @ 30fps…")
    normalized = _normalize_resolution(no_wm, work_dir / "02_normalized.mp4", on_log)
    on_progress(0.28, "Normalizado")

    # 3) Cuadrar duración con el audio (módulo ya existente, tal cual)
    on_log("[3/6] Cuadrando duración con el audio…")
    audio_dur = probe_duration(audio_path)
    matched = match_video_to_audio(
        normalized, audio_dur, work_dir / "duration", on_log=on_log,
    )
    on_progress(0.48, "Duración cuadrada")

    # 4) Bloque de texto
    on_log("[4/6] Quemando texto (gancho/título/CTA)…")
    texted = _burn_text_block(matched, textos or {}, work_dir / "04_texted.mp4", on_log, layout)
    on_progress(0.66, "Texto quemado")

    # 5) Flecha .mov
    on_log("[5/6] Superponiendo flecha…")
    arrowed = _overlay_arrow(texted, audio_path, work_dir, work_dir / "05_arrow.mp4", on_log)
    on_progress(0.84, "Flecha superpuesta")

    # 6) Mux de audio final → destino
    on_log("[6/6] Mezclando audio final…")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _mux_audio(arrowed, audio_path, output_path, on_log)
    on_progress(1.0, "Listo")

    dur_out = probe_duration(output_path)
    on_log(f"✅ Vídeo final: {output_path.name} ({dur_out:.2f}s)")
    return output_path


def layout_for_producto(producto: str) -> str:
    """Reparte las dos disposiciones mitad y mitad, por número de producto.

    Determinista a propósito: el producto 3 siempre sale con el mismo orden,
    así que al comparar resultados se sabe qué disposición llevaba cada vídeo
    sin tener que anotarlo aparte.
    """
    try:
        n = int("".join(c for c in str(producto) if c.isdigit()) or 0)
    except ValueError:
        n = 0
    return "gancho_cta_titulo" if n % 2 else "gancho_titulo_cta"
