"""Herramienta: sticker de flecha animada como CTA al final del vídeo.

Pone una flecha animada (MOV/WebM/GIF con canal alpha) sobre el vídeo en
el momento en que el speaker dice "carrito / comprar / aquí / etc." o,
si no se detecta ninguna keyword, durante los últimos N segundos.

Assets esperados en `<TIKTOK_EDITOR>/Assets/flechas/*.{mov,webm,gif}`. El
operador deposita los archivos a mano; la API los lista para que el
frontend ofrezca un dropdown. MOV con codec ProRes 4444 / Animation y
WebM VP9 con alpha funcionan nativos en FFmpeg sin pre-procesado.

Pipeline:

1) Whisper transcribe el vídeo POST-cortes (los timestamps del Whisper
   pre-cortes ya no son válidos tras `silence_cutter`).
2) Buscar primera ocurrencia de cualquier `trigger_keyword` en el último
   tercio del vídeo (filtro anti-falso-positivo: si el speaker dice
   "compra" al principio no es CTA).
3) Calcular ventana del overlay: `[match_t - lead_s, match_t - lead_s + duration_s]`.
4) Fallback: si no hay match, ventana = `[duration - fallback_s, duration]`.
5) FFmpeg `overlay=enable='between(t,T0,T1)'` con `-stream_loop -1` para
   que el sticker se repita mientras dure su ventana.

Position_weight = 80 (entre silence_cutter=10 y subs_auto=90).
"""

from __future__ import annotations

import os
import re
import subprocess
import time
import unicodedata
from pathlib import Path
from typing import Any

from src.editor_auto.config import (
    TOOL_POSITION_WEIGHTS,
    TOOL_STICKER_ARROW,
    arrows_folder,
)

from .base import ToolContext


# Extensiones soportadas para los stickers. MOV + WebM = alpha real;
# GIF = alpha binario (acepta pero menos suave).
STICKER_EXTS = {".mov", ".webm", ".gif", ".apng", ".png"}

# Keywords default — CTA típico TikTok Shop afiliado español. El operador
# puede sobreescribir vía config; las comparamos contra el transcript
# normalizado (lowercase, sin acentos, sin puntuación).
_DEFAULT_KEYWORDS = (
    "carrito,comprar,compra,aqui,abajo,link,perfil,enlace,"
    "tienda,comprad,comprarlo,compralo,checkout"
)


class StickerArrowTool:
    tool_id: str = TOOL_STICKER_ARROW
    display_name: str = "Sticker flecha CTA"
    description: str = (
        "Superpone una flecha animada apuntando al carrito/perfil cuando "
        "el speaker dice 'comprar/aquí/carrito/link' o en los últimos "
        "segundos del vídeo. Acepta MOV/WebM/GIF con canal alpha."
    )
    position_weight: int = TOOL_POSITION_WEIGHTS[TOOL_STICKER_ARROW]

    def default_config(self) -> dict[str, Any]:
        return {
            # Archivo dentro de Assets/flechas/. UI lista los disponibles
            # vía GET /api/v1/editor-auto/stickers/arrows. Si está vacío,
            # la tool falla limpio en run().
            "sticker_file": "",
            # Posición del CENTRO del sticker como % del frame. 0,0 = top-left.
            "position_x_pct": 50.0,   # centro horizontal
            "position_y_pct": 80.0,   # parte baja (típico CTA "abajo")
            # Tamaño del sticker como % del ancho del vídeo. 20% = sticker
            # de ~216px en un 1080p. Más legible que escala absoluta.
            "scale_width_pct": 25.0,
            # Rotación en grados (0 / 90 / 180 / 270). El sticker base apunta
            # en una dirección; rotándolo apunta arriba/abajo/izq/der.
            "rotation_deg": 0,
            # Espejado: invierte horizontal/vertical (útil para que una
            # flecha que apunta a la derecha apunte a la izquierda sin
            # necesidad de un asset nuevo).
            "flip_horizontal": False,
            "flip_vertical": False,
            # Detección
            "trigger_keywords": _DEFAULT_KEYWORDS,
            # Estrategia ante varias ocurrencias del keyword:
            #   "first" → primera ocurrencia (legacy, útil si el CTA es al inicio)
            #   "last"  → última ocurrencia (DEFAULT — típico CTA al final)
            #   "all"   → todas las ocurrencias (flechas múltiples)
            "match_strategy": "last",
            # Cuánto antes del keyword aparece el sticker (s).
            "lead_seconds": 1.0,
            # Cuánto se mantiene visible (s).
            "duration_seconds": 3.5,
            # Fallback si no hay keyword: aparece en los últimos N s del vídeo.
            "fallback_last_seconds": 4.0,
            # Solo buscar keyword en el último X% del vídeo (anti-falso-positivo).
            "search_last_fraction": 0.5,
            # Tolerancia a errores de Whisper (edit-distance 1 para keywords
            # ≥5 chars). Capta variantes tipo "carrito"↔"carito" o
            # "comprar"↔"compra" sin que el operador tenga que listarlas.
            "fuzzy_match": True,
            # Re-transcribir el vídeo post-cortes (Whisper local, sin coste).
            # Si lo desactivas, solo funciona el fallback de últimos N s.
            "transcribe_for_detection": True,
            # `large-v3` por defecto — máxima precisión para detectar
            # gatillos en audio rápido/sucio. Más lento pero el trade-off
            # vale la pena (detección errónea = flecha en el sitio
            # equivocado). Puedes bajar a `medium`/`small` si quieres.
            "whisper_model_size": "large-v3",
            "ai_language": "es",
        }

    def config_schema(self) -> list[dict[str, Any]]:
        return [
            {"key": "sticker_file",
             "label": "Sticker (archivo en Assets/flechas/)",
             "type": "select_sticker"},   # widget custom en frontend
            {"key": "position_x_pct",
             "label": "Posición X (% desde la izquierda)",
             "type": "float", "min": 0.0, "max": 100.0, "step": 1.0},
            {"key": "position_y_pct",
             "label": "Posición Y (% desde arriba)",
             "type": "float", "min": 0.0, "max": 100.0, "step": 1.0},
            {"key": "scale_width_pct",
             "label": "Tamaño (% del ancho del vídeo)",
             "type": "float", "min": 5.0, "max": 80.0, "step": 1.0},
            {"key": "rotation_deg",
             "label": "Rotación (grados, 0–359)",
             "type": "int", "min": 0, "max": 359, "step": 15},
            {"key": "flip_horizontal",
             "label": "Espejar horizontal", "type": "bool"},
            {"key": "flip_vertical",
             "label": "Espejar vertical", "type": "bool"},
            {"key": "trigger_keywords",
             "label": "Palabras gatillo (separadas por coma)",
             "type": "string"},
            {"key": "match_strategy",
             "label": "Si hay varias ocurrencias del gatillo",
             "type": "select",
             "options": ["first", "last", "all"]},
            {"key": "fuzzy_match",
             "label": "Tolerar errores de transcripción (carrito↔carito)",
             "type": "bool"},
            {"key": "lead_seconds",
             "label": "Aparece N segundos ANTES del gatillo",
             "type": "float", "min": 0.0, "max": 5.0, "step": 0.1},
            {"key": "duration_seconds",
             "label": "Duración visible (s)",
             "type": "float", "min": 0.5, "max": 15.0, "step": 0.5},
            {"key": "fallback_last_seconds",
             "label": "Fallback: últimos N segundos si no hay gatillo",
             "type": "float", "min": 1.0, "max": 15.0, "step": 0.5},
            {"key": "search_last_fraction",
             "label": "Buscar solo en último % del vídeo (anti-falso-positivo)",
             "type": "float", "min": 0.1, "max": 1.0, "step": 0.05},
            {"key": "transcribe_for_detection",
             "label": "Transcribir para detectar gatillos (recomendado)",
             "type": "bool"},
            {"key": "whisper_model_size", "label": "Modelo Whisper",
             "type": "select",
             "options": ["tiny", "base", "small", "medium", "large-v3"]},
            {"key": "ai_language", "label": "Idioma audio (ISO 639-1)",
             "type": "string"},
        ]

    def descriptor(self):  # type: ignore[override]
        from .base import ToolDescriptor
        return ToolDescriptor(
            tool_id=self.tool_id,
            display_name=self.display_name,
            description=self.description,
            position_weight=self.position_weight,
            default_config=self.default_config(),
            config_schema=self.config_schema(),
        )

    def run(
        self,
        *,
        input_path: str,
        output_path: str,
        config: dict[str, Any],
        ctx: ToolContext,
    ) -> str:
        sticker_file = (config.get("sticker_file") or "").strip()
        if not sticker_file:
            raise RuntimeError(
                "sticker_arrow: 'sticker_file' vacío — elige un archivo en "
                "la configuración (Assets/flechas/)."
            )
        sticker_path = _resolve_sticker_path(sticker_file)
        if not sticker_path:
            raise RuntimeError(
                f"sticker_arrow: no encuentro '{sticker_file}' en "
                f"{arrows_folder()}. Comprueba que el archivo existe y la "
                f"extensión es {sorted(STICKER_EXTS)}."
            )
        ctx.on_log(f"[sticker_arrow] Sticker: {sticker_path}")

        # 1) Duración del vídeo post-cortes
        ctx.on_progress(0.05, "📏 Calculando duración…")
        duration = _probe_duration(input_path)
        ctx.on_log(f"[sticker_arrow] Duración input: {duration:.1f}s")

        # 2) Detectar timestamp(s) del gatillo (opcional). Soporta múltiples
        # ocurrencias según `match_strategy` (first / last / all).
        keyword_matches: list[dict] = []
        if bool(config.get("transcribe_for_detection", True)):
            ctx.on_progress(0.15, "🎙️ Whisper para detectar gatillo…")
            try:
                from src.subtitles_only import (
                    extract_audio_from_video,
                    transcribe_with_reference,
                )
                tmp_dir = Path(ctx.temp_folder)
                tmp_dir.mkdir(parents=True, exist_ok=True)
                tmp_audio = str(
                    tmp_dir / f"sticker_arrow_{ctx.job_id}_{int(time.time())}.wav"
                )
                extract_audio_from_video(input_path, tmp_audio)
                words = transcribe_with_reference(
                    tmp_audio,
                    reference_script=None,
                    model_size=config.get("whisper_model_size", "large-v3"),
                    language=config.get("ai_language", "es") or None,
                    audio_type="speech",
                    progress_callback=lambda f, m: ctx.on_progress(
                        0.15 + f * 0.40, m
                    ),
                )
                try:
                    os.remove(tmp_audio)
                except OSError:
                    pass

                keywords = _parse_keywords(config.get("trigger_keywords", ""))
                search_from_s = duration * float(
                    1.0 - max(0.1, min(1.0, float(config.get(
                        "search_last_fraction", 0.5
                    ))))
                )
                fuzzy = bool(config.get("fuzzy_match", True))
                strategy = str(config.get("match_strategy", "last")).lower()
                if strategy not in ("first", "last", "all"):
                    strategy = "last"
                all_matches = _find_keyword_matches(
                    words=words, keywords=keywords,
                    after_t=search_from_s,
                    fuzzy=fuzzy,
                )
                if all_matches:
                    if strategy == "first":
                        selected = [all_matches[0]]
                    elif strategy == "all":
                        selected = all_matches
                    else:  # "last"
                        selected = [all_matches[-1]]
                    keyword_matches = selected
                    summary = " · ".join(
                        f"'{m['word']}'@{m['start']:.2f}s"
                        for m in selected
                    )
                    ctx.on_log(
                        f"[sticker_arrow] 🎯 {len(all_matches)} ocurrencia(s) "
                        f"de gatillo encontradas (estrategia={strategy}, "
                        f"fuzzy={fuzzy}, buscando desde {search_from_s:.1f}s). "
                        f"Aplicando: {summary}"
                    )
                else:
                    ctx.on_log(
                        f"[sticker_arrow] Sin gatillo en último "
                        f"{int((1 - search_from_s / duration) * 100)}% "
                        f"({len(keywords)} keywords probadas, fuzzy={fuzzy})"
                    )
            except Exception as e:
                ctx.on_log(
                    f"[sticker_arrow] ⚠️ Detección Whisper falló ({e}) — "
                    f"caigo al fallback de últimos N segundos."
                )

        # 3) Calcular ventana(s) del overlay
        lead = max(0.0, float(config.get("lead_seconds", 1.0)))
        dur_overlay = max(0.5, float(config.get("duration_seconds", 3.5)))
        windows: list[tuple[float, float]] = []
        if keyword_matches:
            for m in keyword_matches:
                ws = max(0.0, float(m["start"]) - lead)
                we = min(duration, ws + dur_overlay)
                if we > ws:
                    windows.append((ws, we))
            source = "keyword"
        else:
            fallback = max(1.0, float(config.get("fallback_last_seconds", 4.0)))
            ws = max(0.0, duration - fallback)
            windows.append((ws, duration))
            source = "fallback"
        # Mergeamos ventanas solapadas (p. ej. dos matches separados por
        # menos de `duration_seconds` ⇒ una sola ventana extendida) para
        # que ffmpeg no haga overlays redundantes.
        windows = _merge_overlapping_windows(windows)
        windows_str = ", ".join(
            f"[{ws:.2f}, {we:.2f}]" for ws, we in windows
        )
        ctx.on_log(
            f"[sticker_arrow] {len(windows)} ventana(s) overlay {windows_str} "
            f"(source={source})"
        )

        # 4) FFmpeg overlay
        ctx.on_progress(0.65, "🎬 Aplicando overlay…")
        # `rotation_deg` ∈ [0, 359]. Múltiplos de 90 usan `transpose`
        # (lossless, rápido); el resto cae al filtro `rotate` con
        # interpolación bilinear y fondo transparente.
        try:
            rotation_deg = int(str(config.get("rotation_deg", 0)).strip())
        except (TypeError, ValueError):
            rotation_deg = 0
        rotation_deg = rotation_deg % 360
        _apply_overlay_ffmpeg(
            input_path=input_path,
            sticker_path=sticker_path,
            output_path=output_path,
            windows=windows,
            position_x_pct=float(config.get("position_x_pct", 50.0)),
            position_y_pct=float(config.get("position_y_pct", 80.0)),
            scale_width_pct=float(config.get("scale_width_pct", 25.0)),
            rotation_deg=rotation_deg,
            flip_horizontal=bool(config.get("flip_horizontal", False)),
            flip_vertical=bool(config.get("flip_vertical", False)),
            log=ctx.on_log,
        )
        ctx.on_progress(1.0, "✅ Sticker aplicado")
        return output_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _resolve_sticker_path(filename: str) -> str | None:
    """Resuelve `filename` contra `Assets/flechas/`. Acepta solo basename;
    rechaza rutas absolutas o `..` para evitar leer fuera de la carpeta."""
    if not filename:
        return None
    base = os.path.basename(filename)
    if base != filename or ".." in base:
        return None
    candidate = os.path.join(arrows_folder(), base)
    if not os.path.isfile(candidate):
        return None
    ext = os.path.splitext(base)[1].lower()
    if ext not in STICKER_EXTS:
        return None
    return candidate


def _probe_duration(path: str) -> float:
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error",
             "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            timeout=30,
        )
        return float(out.decode().strip() or 0.0)
    except Exception:
        return 0.0


def _probe_video_size(path: str) -> tuple[int, int]:
    """Devuelve `(width, height)` del primer stream de vídeo. (0, 0) si falla."""
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error",
             "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "csv=p=0:s=x", path],
            timeout=30,
        )
        w_str, h_str = out.decode().strip().split("x")[:2]
        return int(w_str), int(h_str)
    except Exception:
        return 0, 0


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


_NORM_RE = re.compile(r"[^\w]+", re.UNICODE)


def _normalize(s: str) -> str:
    return _NORM_RE.sub("", _strip_accents((s or "").lower()))


def _parse_keywords(raw: str) -> list[str]:
    return [
        _normalize(k) for k in (raw or "").split(",")
        if _normalize(k)
    ]


def _find_keyword_matches(
    *,
    words: list[dict],
    keywords: list[str],
    after_t: float,
    fuzzy: bool = True,
) -> list[dict]:
    """Devuelve TODAS las palabras del transcript con `start >= after_t`
    cuya forma normalizada coincide con alguna `keyword`.

    Si `fuzzy=True`, también acepta edit-distance ≤ 1 para keywords con
    ≥5 chars normalizados — útil para capturar variantes de Whisper como
    'carrito'↔'carito' (Whisper a veces se come la doble RR) o
    'comprar'↔'compra'. Para keywords cortas (<5 chars) solo exact match
    para evitar falsos positivos tipo 'a'↔'b'.

    Devuelve lista de dicts {start, end, word, matched_keyword}.
    """
    if not keywords:
        return []
    kw_set = set(keywords)
    long_kws = [k for k in kw_set if len(k) >= 5]
    out: list[dict] = []
    for w in words:
        try:
            t = float(w.get("start", 0.0))
        except (TypeError, ValueError):
            continue
        if t < after_t:
            continue
        norm = _normalize(w.get("word", ""))
        if not norm:
            continue
        matched: str | None = None
        if norm in kw_set:
            matched = norm
        elif fuzzy and len(norm) >= 5:
            for kw in long_kws:
                if abs(len(norm) - len(kw)) <= 1 and _edit_distance_at_most_1(norm, kw):
                    matched = kw
                    break
        if matched is not None:
            out.append({
                "start": t,
                "end": float(w.get("end", t)),
                "word": w.get("word", ""),
                "matched_keyword": matched,
            })
    return out


def _edit_distance_at_most_1(a: str, b: str) -> bool:
    """True si Levenshtein(a, b) ≤ 1. Versión rápida sin matriz completa:
    enumera el primer mismatch y verifica que el resto coincide tras una
    sustitución / inserción / eliminación.
    """
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    # Localizar el primer índice donde difieren.
    i = 0
    while i < min(la, lb) and a[i] == b[i]:
        i += 1
    if la == lb:
        # Sustitución: rest debe coincidir exacto
        return a[i + 1:] == b[i + 1:]
    if la > lb:
        # Eliminación en `a`: rest de a[i+1:] == b[i:]
        return a[i + 1:] == b[i:]
    # Inserción en `a`: rest de a[i:] == b[i+1:]
    return a[i:] == b[i + 1:]


def _merge_overlapping_windows(
    windows: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Mergea ventanas (t_start, t_end) que se solapan o tocan en una sola.
    Útil cuando varios matches están más juntos que `duration_seconds` →
    una flecha extendida es más natural que múltiples redundantes.
    """
    if not windows:
        return []
    sorted_w = sorted(windows, key=lambda w: w[0])
    out: list[tuple[float, float]] = [sorted_w[0]]
    for s, e in sorted_w[1:]:
        ps, pe = out[-1]
        if s <= pe:
            out[-1] = (ps, max(pe, e))
        else:
            out.append((s, e))
    return out


def _apply_overlay_ffmpeg(
    *,
    input_path: str,
    sticker_path: str,
    output_path: str,
    windows: list[tuple[float, float]],
    position_x_pct: float,
    position_y_pct: float,
    scale_width_pct: float,
    rotation_deg: int = 0,
    flip_horizontal: bool = False,
    flip_vertical: bool = False,
    log,
) -> None:
    """FFmpeg overlay con stream_loop infinito del sticker.

    El sticker se escala a `scale_width_pct%` del ancho del vídeo (W*pct/100).
    Su posición es el CENTRO del sticker al porcentaje configurado del
    frame (no top-left) — más intuitivo en sliders. Para eso usamos
    `overlay=x=(W*px/100)-w/2:y=(H*py/100)-h/2` donde `w,h` son el ancho/
    alto resueltos del sticker tras el scale.

    Transformaciones del sticker (orden: flip → rotate → scale para que
    el "tamaño" sea independiente de la rotación):
      - `flip_horizontal` → `hflip`
      - `flip_vertical`   → `vflip`
      - `rotation_deg` ∈ [0, 360):
            múltiplos de 90 → `transpose` (lossless, sin remuestreo)
            resto           → `rotate=θ:c=none:ow=rotw(θ):oh=roth(θ)`
                              fondo transparente, BBox ajustado al
                              contenedor mínimo del sticker rotado

    `enable='between(t,T0,T1)'` solo dibuja el sticker en la ventana
    deseada, fuera de ella se queda transparente. Si se pasan N ventanas,
    se concatenan con `+` (OR lógico en sintaxis de expr de ffmpeg):
    `enable='between(t,T0a,T0b)+between(t,T1a,T1b)'`.

    `-stream_loop -1` repite el MOV/WebM si su duración es menor que la
    ventana de overlay (típico: loop de 2s para ventana de 4s).
    """
    if not windows:
        raise RuntimeError("sticker_arrow: lista de windows vacía")
    # Resolver pct → expresiones FFmpeg que usan W/H del vídeo:
    sw = max(0.05, scale_width_pct / 100.0)
    px = max(0.0, min(1.0, position_x_pct / 100.0))
    py = max(0.0, min(1.0, position_y_pct / 100.0))

    # Cadena de transformaciones previas al scale. Orden importa:
    # primero flip (sobre ejes del asset original), luego rotación,
    # luego scale para que el "ancho final" siempre referencie el lado
    # mayor del sticker rotado.
    pre_filters: list[str] = []
    if flip_horizontal:
        pre_filters.append("hflip")
    if flip_vertical:
        pre_filters.append("vflip")
    rot = rotation_deg % 360
    if rot == 90:
        pre_filters.append("transpose=1")
    elif rot == 180:
        pre_filters.append("transpose=1,transpose=1")
    elif rot == 270:
        pre_filters.append("transpose=2")
    elif rot != 0:
        # Rotación arbitraria con BBox ajustado y fondo transparente.
        # `c=none` mantiene el alpha del asset; `ow/oh=rotw/roth` calcula
        # el contenedor mínimo del sticker rotado (sin recortar esquinas).
        angle_rad = f"{rot}*PI/180"
        pre_filters.append(
            f"rotate={angle_rad}:c=none:ow=rotw({angle_rad}):oh=roth({angle_rad})"
        )
    pre_chain = (",".join(pre_filters) + ",") if pre_filters else ""

    # Filter complex:
    #   [1:v] (flip/rotate),scale=W*sw:-2,format=rgba [s];
    #   [0:v][s] overlay=x:y:enable='between(t,T0,T1)' [v]
    # `format=rgba` asegura que el alpha del MOV/WebM/GIF se preserve.
    #
    # IMPORTANTE: `main_w`/`main_h` son variables de `scale2ref` / `overlay`
    # y NO son válidas en un `scale` plano (ffmpeg 5.x del container las
    # rechaza con "Expressions with scale2ref variables are not valid in
    # scale filter"). En `overlay` SÍ son válidas. Para el scale del
    # sticker probamos el width real del input vía ffprobe y usamos un
    # literal. Si ffprobe falla (raro), caemos a 1080 como tamaño TikTok
    # típico — mejor que reventar.
    main_w_px, _main_h_px = _probe_video_size(input_path)
    if main_w_px <= 0:
        main_w_px = 1080
    sticker_w_px = max(2, int(round(main_w_px * sw)))
    if sticker_w_px % 2 != 0:
        sticker_w_px -= 1
    enable_expr = "+".join(
        f"between(t,{ws:.3f},{we:.3f})" for ws, we in windows
    )
    filter_complex = (
        f"[1:v]{pre_chain}scale={sticker_w_px}:-2,format=rgba[s];"
        f"[0:v][s]overlay="
        f"x=(main_w*{px})-(overlay_w/2):"
        f"y=(main_h*{py})-(overlay_h/2):"
        f"enable='{enable_expr}'[v]"
    )

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
        "-i", input_path,
        "-stream_loop", "-1", "-i", sticker_path,
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-c:a", "copy",
        "-shortest",        # detener cuando se acaba el input de vídeo
        "-movflags", "+faststart",
        output_path,
    ]
    log(
        f"[sticker_arrow] FFmpeg overlay · scale={sw*100:.0f}% · "
        f"pos=({px*100:.0f}%, {py*100:.0f}%) · rot={rotation_deg}° · "
        f"hflip={flip_horizontal} vflip={flip_vertical} · "
        f"{len(windows)} ventana(s)"
    )
    proc = subprocess.run(cmd, capture_output=True, timeout=900)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="ignore")[-500:]
        raise RuntimeError(f"FFmpeg falló: {err}")
