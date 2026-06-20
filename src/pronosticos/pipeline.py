"""Orquestador del nicho 'Pronósticos Diarios' v2.

Cambio crítico vs v1: el guion YA viene hecho desde Redis (key
`daily_bets_tiktok_video:YYYY-MM`). Lo escribe un workflow separado en
bet-ai-master con OpenAI gpt-5.4 + datos verificables de API-Sports. Aquí
solo lo consumimos.

Pipeline:
  Redis (script) → TTS único (MiniMax) → Whisper (word_timings)
                → detección CTA "linkcito" → carruseles por pick
                → stock por equipo → composición MoviePy con perfil.png en CTA
                → MP4 vertical 9:16 con duración real del audio
"""

from __future__ import annotations

import json
import os
import random
import shutil
import tempfile
from datetime import date, timedelta
from typing import Callable

from moviepy.editor import (
    AudioFileClip, ColorClip, CompositeAudioClip, CompositeVideoClip, ImageClip,
    VideoFileClip,
)

from src import locutor

import numpy as np

from .carousel_renderer import render_pick_card
from .data_loader import get_picks, load_chosen_version, publish_video_url
from .league_overlay import (
    build_league_overlay_image, find_league_overlay_anchor, resolve_league_logos,
)
from .segment_locator import find_money_anchor, find_segments
from .stock_search import get_clips_pool, parse_match, search_clip


def _noop(_msg: str) -> None: ...


# Estilo de subtítulos específico del nicho Pronósticos:
# - Una palabra a la vez (max_words_per_chunk=1)
# - Sin píldora de fondo (pill_enabled=False) — solo texto blanco con borde negro grueso
# - Posición Y baja (78%) — replica el estilo del vídeo de referencia
# - Lowercase para tono coloquial/insider
PRONOSTICOS_SUB_STYLE = {
    "font_path": r"C:\Windows\Fonts\impact.ttf",
    "font_scale": 0.055,
    "text_color": "#FFFFFF",
    "stroke_color": "#000000",
    "stroke_width": 8,
    "pill_enabled": False,
    "case_mode": "lowercase",
    "max_words_per_chunk": 1,
    "y_position_pct": 0.78,
    "pill_radius": 10,
    "pill_pad_x_pct": 0.010,
    "pill_pad_y_pct": 0.005,
    "line_spacing_pct": 0.015,
    "word_spacing_multiplier": 0.65,
    "highlight_color": "#000000",   # ignorado al estar pill_enabled=False
}

# Verde "victoria" para resaltar texto de pick + cifra del bote en subtítulos.
# Tono brillante con buen contraste sobre el stroke negro grueso (stroke_width=8).
PRONOSTICOS_PICK_COLOR = "#3CD05E"


def _tomorrow() -> str:
    return (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")


def _resolve_asset(*relative_parts: str) -> str | None:
    """Localiza un asset dentro de BIBLIOTECA_PRONOSTICOS_CLIPS.

    Ej: `_resolve_asset("fotos", "perfil.png")` →
        {TIKTOK_ROOT_PATH}/BIBLIOTECA_PRONOSTICOS_CLIPS/fotos/perfil.png
    """
    root = os.environ.get("TIKTOK_ROOT_PATH")
    if not root:
        return None
    folder = "BIBLIOTECA_PRONOSTICOS_CLIPS"
    cfg_path = os.path.join("config", "config.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, encoding="utf-8") as f:
                cfg = json.load(f)
            folder = cfg.get("folder_structure", {}).get("pronosticos_clips_folder", folder)
        except Exception:
            pass
    candidate = os.path.join(root, folder, *relative_parts)
    return candidate if os.path.exists(candidate) else None


def _resolve_perfil_png() -> str | None:
    """Captura del perfil TikTok para el overlay del CTA midroll.

    Path canónico: BIBLIOTECA_PRONOSTICOS_CLIPS/fotos/perfil.png
    """
    return _resolve_asset("fotos", "perfil.png")


def _resolve_background_music() -> str | None:
    """Localiza el archivo de música de fondo.

    Acepta varias ubicaciones para flexibilidad:
      - BIBLIOTECA_PRONOSTICOS_CLIPS/sfx/fondo.mp3        (default — junto a SFX)
      - BIBLIOTECA_PRONOSTICOS_CLIPS/musica/fondo.mp3
      - BIBLIOTECA_PRONOSTICOS_CLIPS/bgm/fondo.mp3
      También acepta nombres `background.mp3` y `bgm.mp3`.
    """
    candidates = [
        ("sfx", "fondo.mp3"),
        ("sfx", "background.mp3"),
        ("sfx", "bgm.mp3"),
        ("musica", "fondo.mp3"),
        ("bgm", "fondo.mp3"),
    ]
    for parts in candidates:
        path = _resolve_asset(*parts)
        if path:
            return path
    return None


def _mix_background_music(audio_clip, bgm_path: str, volume: float,
                           audio_duration: float, log) -> "object":
    """Mezcla la BGM con el audio TTS bajo el volumen indicado.

    Recorta la BGM a la duración del audio + aplica fade-out de 0.5s al final
    para evitar corte abrupto.
    """
    try:
        bgm = AudioFileClip(bgm_path).volumex(volume)
        if bgm.duration > audio_duration:
            bgm = bgm.subclip(0, audio_duration)
        # Fade-out 0.5s al final (o lo que dure si la BGM es más corta)
        fade_dur = min(0.5, bgm.duration * 0.1)
        if fade_dur > 0.05:
            from moviepy.audio.fx.audio_fadeout import audio_fadeout
            bgm = bgm.fx(audio_fadeout, fade_dur)
        composed = (
            CompositeAudioClip([audio_clip, bgm])
            .set_duration(audio_duration)
        )
        log(f"🎵 Música de fondo: {os.path.basename(bgm_path)} mezclada al {volume*100:.0f}% "
            f"({bgm.duration:.1f}s)")
        return composed
    except Exception as e:
        log(f"⚠️ No se pudo mezclar la música de fondo: {e}")
        return audio_clip


def _resolve_sfx(*candidates: str) -> str | None:
    """Localiza un SFX dentro de BIBLIOTECA_PRONOSTICOS_CLIPS/sfx/.

    Para cada candidato `name.mp3`, también prueba la variante `.wav`. Esto
    permite usar SFX sintetizados con numpy (sin dependencia de codec mp3).
    """
    for filename in candidates:
        path = _resolve_asset("sfx", filename)
        if path:
            return path
        # Intentar variante .wav del mismo nombre
        if filename.lower().endswith(".mp3"):
            wav_alt = filename[:-4] + ".wav"
            path = _resolve_asset("sfx", wav_alt)
            if path:
                return path
    return None


def _mix_sfx_at_timestamps(audio_clip, sfx_path: str, timestamps: list[float],
                           volume: float, audio_duration: float, log,
                           label: str = "SFX") -> "object":
    """Mezcla un SFX en cada timestamp dado y devuelve el audio compuesto.

    Si la lista está vacía o el sfx_path es None, devuelve audio_clip sin tocar.
    """
    if not sfx_path or not timestamps:
        return audio_clip
    try:
        sfx_layers = []
        for ts in timestamps:
            offset = max(0.0, ts - 0.05)  # 50ms de adelanto para sincronía perceptual
            if offset >= audio_duration:
                continue
            layer = AudioFileClip(sfx_path).volumex(volume).set_start(offset)
            sfx_layers.append(layer)
        if not sfx_layers:
            return audio_clip
        composed = (
            CompositeAudioClip([audio_clip] + sfx_layers)
            .set_duration(audio_duration)
        )
        log(f"🔊 {label}: mezclado en {len(sfx_layers)} momento(s) (vol={volume:.2f})")
        return composed
    except Exception as e:
        log(f"⚠️ No se pudo mezclar {label}: {e}")
        return audio_clip


def _apply_saturation(input_path: str, output_path: str, saturation: float,
                      log) -> bool:
    """Re-codifica el vídeo aplicando un filtro de saturación con ffmpeg.

    `saturation`: 1.0 = sin cambios, 1.2-1.4 = colores más vivos sin pasarse,
    >1.5 = exagerado (riesgo de "horneado").

    Devuelve True si tuvo éxito.
    """
    import subprocess
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", f"eq=saturation={saturation:.2f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        output_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            log(f"⚠️ ffmpeg saturación falló: {result.stderr[-300:]}")
            return False
        return True
    except Exception as e:
        log(f"⚠️ ffmpeg saturación excepción: {e}")
        return False


def _resize_cover(clip, W: int, H: int):
    """Encuadra `clip` para llenar W×H preservando aspect ratio (cover-fit).

    Estrategia robusta: comparar aspect ratios.
      - Si el clip es MÁS ANCHO que el target (ratio>target_ratio) → escala por
        altura y crop horizontal.
      - Si el clip es MÁS ALTO que el target (ratio<target_ratio) → escala por
        ancho y crop vertical.
      - Si ya cuadra → resize directo a (W, H).
    Esto evita el bug de la lógica anterior cuando un clip tenía dimensiones
    intermedias (la rama `clip.w<W` reescalaba en ancho descuidando el aspect
    final, llevando a frames "estirados").
    """
    if clip.w <= 0 or clip.h <= 0:
        return clip
    target_ratio = W / H
    src_ratio = clip.w / clip.h
    if abs(src_ratio - target_ratio) < 1e-3:
        # Mismo aspect → resize directo (sin distorsión, ratio idéntico)
        return clip.resize((W, H))
    if src_ratio > target_ratio:
        # Más ancho que el target: ajusta a altura H y crop horizontal
        clip = clip.resize(height=H)
        if clip.w > W:
            clip = clip.crop(x_center=clip.w / 2, width=W, height=H)
        return clip
    else:
        # Más alto que el target: ajusta a ancho W y crop vertical
        clip = clip.resize(width=W)
        if clip.h > H:
            clip = clip.crop(y_center=clip.h / 2, width=W, height=H)
        return clip


def _stock_visual(stock_path: str | None, duration: float, W: int, H: int,
                   log: Callable[[str], None] | None = None):
    """Devuelve un VideoClip silente cubriendo `duration` (loop si hace falta)."""
    if not stock_path or not os.path.exists(stock_path):
        return ColorClip(size=(W, H), color=(8, 12, 28), duration=duration)
    try:
        v = VideoFileClip(stock_path).without_audio()
        src_w, src_h = v.w, v.h
        v = _resize_cover(v, W, H)
        if log and (src_w != W or src_h != H):
            ratio = src_w / src_h if src_h else 0
            log(f"  📐 stock '{os.path.basename(stock_path)}' "
                f"src={src_w}×{src_h} (ar={ratio:.3f}) → {W}×{H}")
        if v.duration < duration:
            from moviepy.editor import vfx
            v = v.fx(vfx.loop, duration=duration)
        else:
            v = v.subclip(0, duration)
        return v.set_duration(duration)
    except Exception:
        return ColorClip(size=(W, H), color=(8, 12, 28), duration=duration)


def _ken_burns_image_silent(image_path: str, duration: float, W: int, H: int):
    img = ImageClip(image_path).set_duration(duration).resize((W, H))

    def zoom(t):
        return 1.0 + 0.06 * (t / max(duration, 0.01))

    img = img.resize(zoom)
    return CompositeVideoClip([img.set_position("center")], size=(W, H)).set_duration(duration)


def _league_overlay_clip(logo_paths: list[str], duration: float,
                          video_size: tuple[int, int],
                          y_position_pct: float = 0.30,
                          logo_height_pct: float = 0.13) -> "ImageClip | None":
    """Construye el ImageClip del overlay de ligas posicionado en y_position_pct.

    `logo_height_pct` controla el tamaño de cada logo (% del alto del frame).

    Devuelve None si no hay logos.
    """
    canvas = build_league_overlay_image(
        logo_paths, video_size, logo_height_pct=logo_height_pct,
    )
    if canvas is None:
        return None
    W, H = video_size
    arr = np.array(canvas)
    clip = ImageClip(arr, transparent=True).set_duration(duration)
    clip_h = arr.shape[0]
    y_top = int(H * y_position_pct) - clip_h // 2
    y_top = max(0, min(H - clip_h, y_top))
    return clip.set_position(("center", y_top))


def _team_shield_clip(shield_path: str, duration: float,
                       W: int, H: int, side: str,
                       height_pct: float = 0.22,
                       y_position_pct: float = 0.43,
                       x_inset_pct: float = 0.06,
                       fade_s: float = 0.15):
    """Escudo del equipo posicionado a izquierda o derecha del frame.

    `side` = "left" → escudo home;  "right" → escudo away.
    Fade in/out suave para que la aparición/desaparición no sea brusca.
    """
    img = ImageClip(shield_path).resize(height=max(80, int(H * height_pct)))
    # Cap horizontal por si el escudo es muy ancho (raro)
    max_w = int(W * 0.30)
    if img.w > max_w:
        img = img.resize(width=max_w)
    y_top = int(H * y_position_pct) - img.h // 2
    y_top = max(0, min(H - img.h, y_top))
    if side == "left":
        x_left = int(W * x_inset_pct)
    else:
        x_left = W - img.w - int(W * x_inset_pct)
    clip = img.set_position((x_left, y_top)).set_duration(duration)
    fd = min(fade_s, max(0.0, duration / 3.0))
    if fd > 0.01:
        clip = clip.crossfadein(fd).crossfadeout(fd)
    return clip


def _perfil_visual_silent(perfil_path: str, duration: float, W: int, H: int,
                           height_pct: float = 0.32,
                           y_position_pct: float = 0.36):
    """Renderiza perfil.png como overlay transparente del tamaño de los logos de liga.

    NO tapa el vídeo de stock detrás (sin bg_color negro). Posicionado en zona
    media tirando arriba para que no choque con los subtítulos (78% Y) ni con
    el header de la liga (12% Y).

    `height_pct` = altura del overlay como % del frame (default 32% ≈ 614px en 1920).
    `y_position_pct` = centro vertical del overlay como % del frame (default 36%).
    """
    img = ImageClip(perfil_path)
    target_h = max(120, int(H * height_pct))
    img = img.resize(height=target_h)
    # Si la imagen es desproporcionadamente ancha, cap horizontal al 85% del frame
    if img.w > W * 0.85:
        img = img.resize(width=int(W * 0.85))
    # Centro vertical en y_position_pct del alto
    y_top = int(H * y_position_pct) - img.h // 2
    y_top = max(0, min(H - img.h, y_top))
    return img.set_position(("center", y_top)).set_duration(duration)


def _viral_overlay_clip(png_path: str, duration: float):
    """Carga un overlay del estilo VIRAL (PNG RGBA a frame completo, con el
    elemento ya posicionado dentro) como ImageClip transparente a (0,0)."""
    from PIL import Image as _PILImage
    arr = np.array(_PILImage.open(png_path).convert("RGBA"))
    return ImageClip(arr, transparent=True).set_duration(duration).set_position((0, 0))


def _split_match(match: str) -> tuple[str, str]:
    """'Portugal vs RD Congo' → ('Portugal', 'RD Congo'). Tolerante a 'vs.'/'VS'."""
    import re
    parts = re.split(r"\s+vs\.?\s+", str(match or ""), maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return (str(match or "").strip(), "")


def _pick_bet_team(pick: dict, home: str, away: str) -> tuple[str, str]:
    """Devuelve (equipo_de_la_apuesta, el_otro). Mira el texto del pick: si nombra
    a un equipo (ej. 'Doble Oportunidad Netherlands', '+4.5 córners Ecuador') usa
    ese; si es de total sin equipo (ej. '+1.5 goles') cae al local."""
    import unicodedata

    def _norm(s: str) -> str:
        s = (s or "").lower()
        return "".join(
            c for c in unicodedata.normalize("NFD", s)
            if unicodedata.category(c) != "Mn"
        )

    text = _norm(f"{pick.get('pick', '')} {pick.get('pick_narrated', '')}")
    nh, na = _norm(home), _norm(away)
    # Si ambos aparecen, gana el que aparece antes en el texto (el sujeto del pick).
    ih = text.find(nh) if nh else -1
    ia = text.find(na) if na else -1
    if ih != -1 and (ia == -1 or ih <= ia):
        return home, away
    if ia != -1:
        return away, home
    return home, away  # apuesta de total/sin equipo → local


def _resolve_team_photo(team: str) -> str | None:
    """Primera foto guardada para un equipo en BIBLIOTECA_PRONOSTICOS_CLIPS/fotos/<equipo>/
    (la herramienta 'Fotos de partido' las guarda ahí en 9:16). None si no hay."""
    import glob
    import re
    if not team:
        return None
    # Mismo saneado que match_photos._safe_team → mismo nombre de carpeta.
    t = team.strip().replace("/", " ").replace("\\", " ")
    t = re.sub(r"[^\w\s\-]", "", t, flags=re.UNICODE).strip()
    t = re.sub(r"\s+", " ", t)
    folder = _resolve_asset("fotos", t)
    if not folder or not os.path.isdir(folder):
        return None
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
        files = sorted(glob.glob(os.path.join(folder, ext)))
        if files:
            return files[0]
    return None


def _resolve_override_photo(rel: str | None) -> str | None:
    """Foto elegida por el usuario en formato 'Equipo/archivo.jpg' → ruta absoluta."""
    if not rel:
        return None
    parts = [x for x in str(rel).split("/") if x]
    if len(parts) < 2:
        return None
    return _resolve_asset("fotos", parts[0], parts[1])


class _ClipDeck:
    """Baraja sin reposición: entrega clips en orden aleatorio y solo repite
    cuando se han usado TODOS. Estado compartido entre segmentos que usan la
    misma pool (ej: en `single_match` los N picks comparten pool, así clip A
    no sale en pick 1 y otra vez en pick 2 mientras quede B sin estrenar).
    """

    def __init__(self, clips: list[str]):
        self._clips: list[str] = list(clips)
        self._remaining: list[str] = []
        self._last: str | None = None

    @property
    def size(self) -> int:
        return len(self._clips)

    def take(self, n: int) -> list[str]:
        out: list[str] = []
        for _ in range(n):
            if not self._remaining:
                self._remaining = list(self._clips)
                random.shuffle(self._remaining)
                # Evitar que el último del ciclo anterior abra el siguiente
                if (self._last and len(self._remaining) > 1
                        and self._remaining[0] == self._last):
                    self._remaining[0], self._remaining[1] = (
                        self._remaining[1], self._remaining[0]
                    )
            clip = self._remaining.pop(0)
            self._last = clip
            out.append(clip)
        return out


def _plan_clips_for_segment(segment_dur: float, deck: _ClipDeck,
                            target_clip_dur: float = 12.0,
                            min_clip_dur: float = 8.0,
                            max_clip_dur: float = 18.0) -> list[tuple[str, float]]:
    """Decide cuántos clips usar dentro de un segmento y cuánto dura cada uno.

    Reglas:
      - Apunta a clips de ~`target_clip_dur` segundos (default 12s).
      - Mínimo `min_clip_dur` por clip (8s) — clips más cortos cansan al ojo.
      - Máximo `max_clip_dur` por clip (18s) — más largos aburren.
      - Si solo hay 1 clip o el segmento es muy corto, usa 1 solo clip.
      - No repite clips dentro de un segmento si el deck tiene suficientes.
      - El deck garantiza que entre segmentos tampoco se repite hasta agotar
        todos los clips disponibles.

    Returns: lista [(clip_path, duration), ...] cuya suma == segment_dur.
    Si el deck está vacío, devuelve []  (caller usa fondo sólido).
    """
    available = deck.size
    if available == 0 or segment_dur <= 0:
        return []

    # Caso trivial: segmento corto → 1 solo clip
    if segment_dur < min_clip_dur * 1.25:
        return [(deck.take(1)[0], segment_dur)]

    # Cuántos clips encajan apuntando a target_clip_dur
    n_ideal = max(1, round(segment_dur / target_clip_dur))
    # No más clips que los disponibles (evita repeticiones dentro del segmento)
    n_clips = min(n_ideal, available)
    # Bajar n_clips hasta que cada uno supere min_clip_dur
    while n_clips > 1 and (segment_dur / n_clips) < min_clip_dur:
        n_clips -= 1
    # Subir n_clips si cada uno excede max_clip_dur (y hay disponibilidad)
    while (segment_dur / n_clips) > max_clip_dur and n_clips < available:
        n_clips += 1

    dur_each = segment_dur / n_clips
    selected = deck.take(n_clips)
    return [(clip, dur_each) for clip in selected]


def _build_visual_timeline(audio_duration: float, picks: list[dict],
                           segments: dict, carousels: dict[int, str],
                           clip_pools: dict[str, list[str]],
                           perfil_path: str | None,
                           league_overlay: dict | None,
                           team_shields: dict | None,
                           W: int, H: int,
                           show_pick_carousel: bool = False,
                           carousel_lead_s: float = 4.0,
                           # Posiciones configurables (defaults históricos).
                           league_overlay_y_pct: float = 0.30,
                           league_logo_height_pct: float = 0.13,
                           team_shield_y_pct: float = 0.43,
                           team_shield_height_pct: float = 0.22,
                           team_shield_x_inset_pct: float = 0.06,
                           profile_cta_y_pct: float = 0.36,
                           profile_cta_height_pct: float = 0.32,
                           video_style: str = "standard",
                           viral_overlays: dict | None = None) -> list:
    """Construye el timeline de visuales usando segmentos detectados.

    Estructura por pick:
      - 0..carousel_lead_s: carrusel Ken Burns con la card del pick (~4s).
      - resto del segmento: clips de stock múltiples planificados con _plan_clips_for_segment.

    Para la intro: solo clips de stock (sin carrusel).
    Para el CTA: overlay perfil.png encima del visual base que toque.

    `clip_pools` mapea claves a listas de rutas:
      - "intro" → pool para la intro
      - str(idx) → pool para el pick idx (1, 2, 3, ...)
    """
    timeline = []

    # Decks compartidos: pools con exactamente los mismos clips reutilizan el
    # mismo deck → un clip no se repite hasta agotar la baraja, ni siquiera
    # entre segmentos distintos. Caso típico: `single_match` (todos los picks
    # con la misma pool) o intro que hereda del pick 1.
    decks_by_pool: dict[frozenset, _ClipDeck] = {}

    def _deck_for(pool: list[str]) -> _ClipDeck:
        if not pool:
            return _ClipDeck([])
        sig = frozenset(pool)
        d = decks_by_pool.get(sig)
        if d is None:
            d = _ClipDeck(pool)
            decks_by_pool[sig] = d
        return d

    # ── INTRO ──
    intro_start, intro_end = segments["intro"]
    intro_dur = max(0.0, intro_end - intro_start)
    _intro_bg = (viral_overlays or {}).get("bg_intro") if video_style == "viral" else None
    if intro_dur > 0 and _intro_bg:
        # VIRAL: foto de fondo (Ken Burns) en el gancho, en vez de stock.
        timeline.append({
            "start": intro_start, "duration": intro_dur,
            "clip_factory": lambda p=_intro_bg, dur=intro_dur: _ken_burns_image_silent(p, dur, W, H),
        })
    elif intro_dur > 0:
        intro_pool = clip_pools.get("intro") or clip_pools.get("1") or []
        plan = _plan_clips_for_segment(intro_dur, _deck_for(intro_pool))
        if plan:
            cursor = intro_start
            for clip_path, d in plan:
                timeline.append({
                    "start": cursor, "duration": d,
                    "clip_factory": lambda dur=d, p=clip_path: _stock_visual(p, dur, W, H),
                })
                cursor += d
        else:
            # Sin pool → fondo sólido
            timeline.append({
                "start": intro_start, "duration": intro_dur,
                "clip_factory": lambda dur=intro_dur: _stock_visual(None, dur, W, H),
            })

    # ── Overlay VIRAL: tarjeta de partidos durante la INTRO (gancho) ──
    if video_style == "viral" and viral_overlays and viral_overlays.get("hook") and intro_dur > 0:
        timeline.append({
            "start": intro_start, "duration": intro_dur,
            "clip_factory": lambda p=viral_overlays["hook"], dur=intro_dur: _viral_overlay_clip(p, dur),
            "is_overlay": True, "label": "viral_hook",
        })

    # ── PICKS ──
    for i, (s_start, s_end) in enumerate(segments["picks"], start=1):
        seg_dur = max(0.0, s_end - s_start)
        if seg_dur <= 0:
            continue

        # Overlay VIRAL: barra del partido durante TODO el segmento del pick.
        if video_style == "viral" and viral_overlays:
            _bar_path = (viral_overlays.get("bars") or {}).get(i)
            if _bar_path:
                timeline.append({
                    "start": s_start, "duration": seg_dur,
                    "clip_factory": lambda p=_bar_path, dur=seg_dur: _viral_overlay_clip(p, dur),
                    "is_overlay": True, "label": f"viral_bar_{i}",
                })

        # Carrusel al inicio del pick (opcional, OFF por defecto — el usuario
        # prefiere ver vídeo de stock continuo). Si se activa, ocupa los primeros
        # `carousel_lead_s` segundos del pick.
        carousel_path = carousels.get(i) if show_pick_carousel else None
        lead = min(carousel_lead_s, seg_dur * 0.4) if show_pick_carousel else 0.0
        if carousel_path and lead >= 1.5:
            timeline.append({
                "start": s_start, "duration": lead,
                "clip_factory": lambda dur=lead, p=carousel_path: (
                    _ken_burns_image_silent(p, dur, W, H)
                ),
            })
            stock_start = s_start + lead
            stock_dur = seg_dur - lead
        else:
            stock_start = s_start
            stock_dur = seg_dur

        # Stock múltiple para el resto del segmento
        if stock_dur > 0:
            _pick_bg = (
                (viral_overlays or {}).get("bg_picks", {}).get(i)
                if video_style == "viral" else None
            )
            if _pick_bg:
                # VIRAL: foto del equipo del partido (Ken Burns) como fondo del pick.
                timeline.append({
                    "start": stock_start, "duration": stock_dur,
                    "clip_factory": lambda p=_pick_bg, dur=stock_dur: _ken_burns_image_silent(p, dur, W, H),
                })
            else:
                pool = clip_pools.get(str(i)) or []
                plan = _plan_clips_for_segment(stock_dur, _deck_for(pool))
                if plan:
                    cursor = stock_start
                    for clip_path, d in plan:
                        timeline.append({
                            "start": cursor, "duration": d,
                            "clip_factory": lambda dur=d, p=clip_path: _stock_visual(p, dur, W, H),
                        })
                        cursor += d
                else:
                    timeline.append({
                        "start": stock_start, "duration": stock_dur,
                        "clip_factory": lambda dur=stock_dur: _stock_visual(None, dur, W, H),
                    })

    # ── Cap final: si los segmentos no cubren toda la duración del audio
    covered = max((e["start"] + e["duration"] for e in timeline), default=0.0)
    if covered < audio_duration - 0.05:
        pad = audio_duration - covered
        last_pool = clip_pools.get(str(len(picks))) or clip_pools.get("1") or []
        plan = _plan_clips_for_segment(pad, _deck_for(last_pool))
        if plan:
            cursor = covered
            for clip_path, d in plan:
                timeline.append({
                    "start": cursor, "duration": d,
                    "clip_factory": lambda dur=d, p=clip_path: _stock_visual(p, dur, W, H),
                })
                cursor += d
        else:
            timeline.append({
                "start": covered, "duration": pad,
                "clip_factory": lambda dur=pad: _stock_visual(None, dur, W, H),
            })

    # ── CTA overlay (perfil.png) ──
    cta_window = segments.get("cta")
    if cta_window and perfil_path:
        cta_start, cta_end = cta_window
        timeline.append({
            "start": cta_start, "duration": cta_end - cta_start,
            "clip_factory": lambda dur=(cta_end - cta_start), p=perfil_path: (
                _perfil_visual_silent(
                    p, dur, W, H,
                    height_pct=profile_cta_height_pct,
                    y_position_pct=profile_cta_y_pct,
                )
            ),
            "is_overlay": True,
            "label": "perfil_overlay",
        })
    elif cta_window and not perfil_path:
        # Diagnóstico: tenemos ventana del CTA pero no archivo perfil → marcar
        # con un label para que el caller pueda loggearlo.
        pass

    # ── Overlay escudos de equipo (single_match: home izquierda + away derecha) ──
    # Cada escudo aparece en su propio anchor (home cuando se nombra al local,
    # away cuando se nombra al visitante) pero AMBOS desaparecen a la vez,
    # tomando el final más tardío como cierre común.
    if team_shields:
        shield_dur = float(team_shields.get("duration", 2.5))
        sides_in: list[tuple[str, str, float]] = []  # (side, path, anchor_s)
        for side, key_path, key_anchor in (
            ("left", "home_path", "home_anchor"),
            ("right", "away_path", "away_anchor"),
        ):
            sp = team_shields.get(key_path)
            sa = team_shields.get(key_anchor)
            if sp and sa is not None:
                sides_in.append((side, sp, float(sa)))

        if sides_in:
            joint_end = min(audio_duration,
                             max(a + shield_dur for _, _, a in sides_in))
            for side, sp, sa_f in sides_in:
                dur = max(0.5, joint_end - sa_f)
                timeline.append({
                    "start": sa_f, "duration": dur,
                    "clip_factory": (
                        lambda d=dur, p=sp, s=side: _team_shield_clip(
                            p, d, W, H, s,
                            height_pct=team_shield_height_pct,
                            x_inset_pct=team_shield_x_inset_pct,
                            y_position_pct=team_shield_y_pct,
                        )
                    ),
                    "is_overlay": True,
                    "label": f"shield_{side}",
                })

    # ── Overlay logos de ligas (al detectar 'ligas'/'champions'/...) ──
    if league_overlay and league_overlay.get("logos") and league_overlay.get("anchor") is not None:
        anchor = float(league_overlay["anchor"])
        dur = float(league_overlay.get("duration", 3.0))
        # Cap si el anchor + duración se sale del audio
        dur = min(dur, max(0.5, audio_duration - anchor))
        logos = league_overlay["logos"]
        timeline.append({
            "start": anchor, "duration": dur,
            "clip_factory": lambda d=dur, lg=logos: _league_overlay_clip(
                lg, d, (W, H),
                y_position_pct=league_overlay_y_pct,
                logo_height_pct=league_logo_height_pct,
            ),
            "is_overlay": True,
        })

    return timeline


def _compose_video(audio_clip, timeline: list, W: int, H: int):
    """Convierte el timeline plano en un CompositeVideoClip final con el audio."""
    base_clips = []
    overlay_clips = []
    for entry in timeline:
        clip = entry["clip_factory"]().set_start(entry["start"])
        if entry.get("is_overlay"):
            overlay_clips.append(clip)
        else:
            base_clips.append(clip)

    # base_clips se renderizan en orden temporal (cubren toda la duración)
    # overlay_clips van encima (perfil.png durante el CTA)
    all_clips = base_clips + overlay_clips
    final = CompositeVideoClip(all_clips, size=(W, H))
    final = final.set_duration(audio_clip.duration).set_audio(audio_clip)
    return final


def run_pronosticos_pipeline(
    target_date: str | None = None,
    output_folder: str | None = None,
    log_callback: Callable[[str], None] | None = None,
    video_size: tuple[int, int] = (1080, 1920),
    fps: int = 30,
    voice_id_override: str | None = None,
    publish_to_redis: bool = False,
    add_subtitles: bool = True,
    use_intro_folder: bool = True,
    add_money_sfx: bool = True,
    sfx_volume: float = 0.55,
    add_clink_sfx: bool = True,
    clink_volume: float = 0.35,
    add_camera_sfx: bool = True,
    camera_volume: float = 0.45,
    add_league_overlay: bool = True,
    league_overlay_duration: float = 3.0,
    saturation: float = 1.25,
    show_pick_carousel: bool = False,
    version_id: str | None = None,
    script_override: str | None = None,
    add_background_music: bool = True,
    bgm_volume: float = 0.20,
    progress_callback: Callable[[float, str], None] | None = None,
    # Posiciones de overlays (configurables desde la UI vía preview).
    # 0.0 = top, 1.0 = bottom. Heights/insets en fracción del lado mayor.
    subtitle_y_pct: float = 0.78,
    league_overlay_y_pct: float = 0.30,
    league_logo_height_pct: float = 0.13,
    team_shield_y_pct: float = 0.43,
    team_shield_height_pct: float = 0.22,
    team_shield_x_inset_pct: float = 0.06,
    profile_cta_y_pct: float = 0.36,
    profile_cta_height_pct: float = 0.32,
    video_style: str = "standard",
    photo_overrides: dict | None = None,
) -> str:
    """Genera el MP4 final y devuelve la ruta.

    `target_date` = `YYYY-MM-DD`. Por defecto, mañana.
    `version_id`  = id de la versión del guion a usar (cuando el payload trae
                    `versions[]`). Si es None, usa `selected_version_id` del
                    payload o cae a la última.
    `script_override` = si se pasa, sustituye al `script` del payload (solo en
                    memoria, NO se guarda en Redis). Útil para que la UI edite
                    el guion ad-hoc antes de generar.
    """
    log = log_callback or _noop
    target_date = target_date or _tomorrow()
    voice_id_override = voice_id_override or os.environ.get("PRONOSTICOS_VOICE_ID")

    # Reporter de progreso (no-op si no se pasa callback)
    def _progress(pct: float, msg: str) -> None:
        if progress_callback:
            try:
                progress_callback(max(0.0, min(1.0, pct)), msg)
            except Exception:
                pass

    log(f"📅 Procesando vídeo para {target_date}"
        + (f" (versión {version_id})" if version_id else "") + "...")
    _progress(0.02, "Conectando con Redis...")

    # 1. Cargar guion ya hecho desde Redis
    log("📡 Conectando con Redis (Upstash)...")
    payload = load_chosen_version(target_date, version_id=version_id)
    chosen_id = payload.get("id", "legacy")
    chosen_trigger = payload.get("trigger", "?")
    mode = payload.get("mode", "?")
    picks = get_picks(payload)
    competition_focus = payload.get("competition_focus")

    # Override del script: edición efímera de la UI. Mantiene mode/picks/etc del payload.
    if script_override and script_override.strip() and script_override != payload.get("script"):
        script = script_override.strip()
        words_in_override = len(script.split())
        log(f"✏️ Guion EDITADO en UI (no se persiste): {words_in_override} palabras "
            f"(original: {payload.get('word_count', '?')})")
    else:
        script = payload["script"]
        log(f"✅ Guion v{chosen_id} ({chosen_trigger}) cargado: mode={mode}, picks={len(picks)}, "
            f"~{payload.get('word_count', '?')} palabras, "
            f"~{payload.get('estimated_duration_s', '?')}s estimados")
    if competition_focus:
        log(f"🏆 competition_focus: {competition_focus}")

    # Extracción de picks entre paréntesis (PronosticosAuto.md §"Picks entre paréntesis").
    # Garantía del backend bet-ai-master: cada pick va envuelto en `(...)` con el
    # texto LITERAL narrado, y `len(parens) == len(picks)` 1-a-1.
    from .pick_locator import extract_pick_texts, strip_pick_parens
    pick_texts = extract_pick_texts(script)
    tts_script = strip_pick_parens(script)
    if pick_texts:
        log(f"🟢 {len(pick_texts)} picks detectados entre paréntesis del guion")
        if picks and len(pick_texts) != len(picks):
            log(f"⚠️ Mismatch garantía: {len(pick_texts)} paréntesis vs "
                f"{len(picks)} picks en payload — bet-ai-master debería loggearlo")
    elif "(" in script:
        log("ℹ️ Guion con paréntesis pero sin picks parseables — usando fallback por keywords")

    work_dir = tempfile.mkdtemp(prefix="pronosticos_")

    # 2. TTS único (MiniMax) — todo el script en una sola pieza
    _progress(0.05, "Sintetizando voz (MiniMax)...")
    log("🎙️ Sintetizando audio con MiniMax (script completo, una sola pasada)...")
    audio_path = os.path.join(work_dir, "voice.mp3")
    locutor.generate_single_audio(tts_script, audio_path, voice_id_override=voice_id_override)
    _progress(0.20, "Voz sintetizada")

    # 3. Whisper local para word_timings
    _progress(0.22, "Transcribiendo audio (Whisper)...")
    log("📝 Transcribiendo audio con Whisper para sincronizar visuales...")
    from src.subtitles import transcribe
    word_timings = transcribe(audio_path, model_size="base", language="es")
    if not word_timings:
        log("⚠️ Whisper no devolvió palabras — el CTA no se detectará.")
    _progress(0.40, "Audio transcrito")

    # 4. Detectar segmentos (intro + picks + ventana CTA) en el audio
    audio_clip = AudioFileClip(audio_path)
    audio_duration = float(audio_clip.duration)
    segments = find_segments(word_timings, audio_duration, log_callback=log)

    # 4.a Localizar la ventana exacta de cada pick en word_timings
    # (a partir del texto entre paréntesis del script). Sirve para clink + verde.
    pick_windows: list = []
    if pick_texts and word_timings:
        from .pick_locator import find_pick_windows
        pick_windows = find_pick_windows(word_timings, pick_texts, log_callback=log)
        n_ok = sum(1 for w in pick_windows if w is not None)
        log(f"🟢 Picks localizados en audio: {n_ok}/{len(pick_texts)}")

    # 4.a.bis VIRAL: el guion viral pone el veredicto al FINAL de cada pick
    # ("Me quedo con (...)"), no una transición de apertura ("empezamos con")
    # como el clásico. Por eso recalculamos los segmentos a partir de los
    # paréntesis (pick_windows): la foto/barra de cada partido debe aparecer
    # cuando EMPIEZA a hablar de él, no al llegar al veredicto (que iba ~2s tarde).
    if (video_style == "viral" and pick_windows
            and all(w is not None for w in pick_windows) and len(pick_windows) >= 2):
        v_starts = [float(word_timings[w[0]]["start"]) for w in pick_windows]
        v_ends = [float(word_timings[w[1]]["end"]) for w in pick_windows]
        cta = segments.get("cta")
        # Gancho ≈ frase de apertura: ~45% del tiempo hasta el primer veredicto.
        intro_end = min(max(v_starts[0] * 0.45, 3.0), 8.0)
        new_picks: list = []
        prev = intro_end
        n = len(v_ends)
        for i in range(n):
            end_i = v_ends[i] if i < n - 1 else audio_duration
            # Si el CTA va justo tras este pick, extiende su foto para cubrirlo
            # (el cambio de partido ocurre al ACABAR el CTA).
            if cta and prev <= cta[0] <= end_i + 0.5 and cta[1] > end_i:
                end_i = cta[1]
            new_picks.append((prev, max(prev + 0.2, end_i)))
            prev = new_picks[-1][1]
        segments["intro"] = (0.0, intro_end)
        segments["picks"] = new_picks
        log(f"🎬 Viral: segmentos por paréntesis — intro 0–{intro_end:.1f}s, "
            f"{n} picks; cambios de foto sincronizados con el habla")

    # 4.b SFX de dinero sincronizado con la cifra del bote en la intro
    if add_money_sfx and word_timings:
        money_path = _resolve_sfx("money.mp3", "cha-ching.mp3", "dinero.mp3")
        if money_path:
            money_t = find_money_anchor(word_timings, intro_end=segments["intro"][1])
            if money_t is not None:
                # 150ms de adelanto sobre el ataque vocal (sensación de pre-cue)
                audio_clip = _mix_sfx_at_timestamps(
                    audio_clip, money_path, [max(0.0, money_t - 0.10)],
                    sfx_volume, audio_duration, log, label="💰 dinero",
                )
            else:
                # Diagnóstico: muestra los primeros tokens para ver qué transcribió Whisper
                head = " ".join((w.get("word") or "").strip() for w in word_timings[:8])
                log(f"ℹ️ No se halló palabra-número en la intro; SFX dinero omitido. "
                    f"Primeros tokens Whisper: '{head}'")
        else:
            log("ℹ️ SFX dinero no encontrado en BIBLIOTECA_PRONOSTICOS_CLIPS/sfx/")

    # 4.c SFX clink cada vez que arranca el pick textual.
    # Si tenemos pick_windows (paréntesis del guion), ancla en el inicio EXACTO
    # de cada pick. Si no, fallback a la heurística de keywords post-transición.
    if add_clink_sfx and word_timings:
        clink_path = _resolve_sfx("clink.mp3", "notification.mp3", "pick.mp3")
        if clink_path:
            anchors: list[float]
            valid_windows = [w for w in pick_windows if w is not None]
            if valid_windows:
                anchors = [float(word_timings[w[0]]["start"]) for w in valid_windows]
                log(f"🔔 Clink anclado en paréntesis del guion: {len(anchors)} picks")
            else:
                from .segment_locator import find_pick_anchors, find_pick_starts
                pick_starts = find_pick_starts(word_timings)
                log(f"🔔 Clink (fallback keywords): {len(pick_starts)} transiciones detectadas")
                anchors = find_pick_anchors(word_timings, pick_starts, log_callback=log)
            audio_clip = _mix_sfx_at_timestamps(
                audio_clip, clink_path, anchors,
                clink_volume, audio_duration, log, label="🔔 clink picks",
            )
        else:
            log("ℹ️ SFX clink no encontrado en BIBLIOTECA_PRONOSTICOS_CLIPS/sfx/")

    # 4.c.bis SFX "flash" de transición (solo estilo VIRAL): un whoosh en el
    # corte a cada pick (inicio de cada segmento), coincidiendo con la aparición
    # de la barra del partido. Gated en viral → no toca el render estándar.
    if video_style == "viral":
        flash_path = _resolve_sfx("flash.mp3", "transition.mp3", "whoosh.mp3")
        if flash_path:
            flash_anchors = [float(s) for (s, _e) in segments.get("picks", []) if s and s > 0]
            if flash_anchors:
                audio_clip = _mix_sfx_at_timestamps(
                    audio_clip, flash_path, flash_anchors,
                    sfx_volume, audio_duration, log, label="⚡ flash viral",
                )
            else:
                log("ℹ️ Estilo viral sin anclas de pick para el flash.")
        else:
            log("ℹ️ SFX flash (viral) no encontrado en BIBLIOTECA_PRONOSTICOS_CLIPS/sfx/")

    # 4.d Overlay de logos de ligas en la intro (al detectar 'ligas/champions/europa...')
    league_overlay_anchor: float | None = None
    league_logos: list[str] = []
    if add_league_overlay and word_timings and picks:
        league_overlay_anchor = find_league_overlay_anchor(
            word_timings, intro_end=segments["intro"][1],
        )
        if league_overlay_anchor is not None:
            league_logos = resolve_league_logos(picks, _resolve_asset, max_logos=3)
            if league_logos:
                log(f"🏆 Overlay de ligas: {len(league_logos)} logos a los "
                    f"{league_overlay_anchor:.2f}s ({league_overlay_duration:.1f}s en pantalla)")
            else:
                log("ℹ️ Trigger detectado pero ninguna liga del payload tiene logo en /fotos/")
                league_overlay_anchor = None
        else:
            log("ℹ️ No se halló trigger de ligas en la intro; sin overlay.")

    # 4.d.bis Escudos de equipo — vídeos de UN SOLO partido. Cubre:
    #   • mode == "single_match" (deep-dive Champions, schema clásico)
    #   • mode == "multi_match" + todos los picks del MISMO partido
    #     (caso competition_focus con un único Atlético-Arsenal repetido)
    # No se muestran cuando hay varios partidos distintos (multi_match clásico).
    team_shields_data = None
    unique_matches = {(p.get("match") or "").strip() for p in (picks or [])}
    unique_matches.discard("")
    is_solo_match = (mode == "single_match") or (len(unique_matches) == 1)
    log(f"🎯 mode={mode!r}, partidos únicos en picks: {len(unique_matches)} → "
        f"escudos: {'SÍ' if is_solo_match else 'NO'}")
    if is_solo_match and picks and word_timings:
        from .team_shield_overlay import resolve_team_shield, find_team_anchors
        home_team_solo, away_team_solo = parse_match(picks[0].get("match", ""))
        sp_home = resolve_team_shield(home_team_solo)
        sp_away = resolve_team_shield(away_team_solo)
        if sp_home or sp_away:
            ah, aa = find_team_anchors(
                word_timings, home_team_solo, away_team_solo,
                intro_end=segments["intro"][1],
            )
            team_shields_data = {
                "home_path": sp_home, "home_anchor": ah,
                "away_path": sp_away, "away_anchor": aa,
                "duration": 2.5,
            }
            log(f"🛡️ Escudos single_match: "
                f"home={home_team_solo!r} {'✓' if sp_home else '✗'}"
                + (f" @ {ah:.2f}s" if ah is not None else " (sin anchor)")
                + f" | away={away_team_solo!r} {'✓' if sp_away else '✗'}"
                + (f" @ {aa:.2f}s" if aa is not None else " (sin anchor)"))
            # Coexistencia con overlay de liga: el logo de la liga aparece
            # normalmente cuando se dice "champions/europa/...", pero se ACORTA
            # para terminar justo antes del primer escudo de equipo (sin solape
            # visual). Si el trigger de la liga es POSTERIOR al primer escudo,
            # ahí sí se suprime entero (ya no tiene hueco).
            shield_anchors = [t for t in (ah, aa) if t is not None]
            if shield_anchors and league_overlay_anchor is not None and league_logos:
                first_shield = min(shield_anchors)
                if league_overlay_anchor < first_shield:
                    gap = first_shield - league_overlay_anchor - 0.10  # 100ms colchón
                    league_overlay_duration_cap = max(0.5, gap)
                    if league_overlay_duration_cap < league_overlay_duration:
                        log(f"🏆 Overlay liga acortado a {league_overlay_duration_cap:.2f}s "
                            f"para no solaparse con escudos a partir de {first_shield:.2f}s")
                        league_overlay_duration = league_overlay_duration_cap
                else:
                    log("🛡️ Overlay de liga suprimido (su trigger es posterior a los escudos)")
                    league_overlay_anchor = None
                    league_logos = []
        else:
            log("ℹ️ Modo single_match pero ninguna carpeta de equipo trae escudo.png")

    # 4.e SFX cámara — unificado: dispara cuando aparece perfil.png (CTA),
    # logos de ligas, y/o escudos de equipo.
    if add_camera_sfx:
        camera_path = _resolve_sfx("camera.mp3", "shutter.mp3", "foto.mp3")
        if camera_path:
            camera_timestamps: list[float] = []
            if segments.get("cta"):
                camera_timestamps.append(segments["cta"][0])
            if league_overlay_anchor is not None and league_logos:
                camera_timestamps.append(league_overlay_anchor)
            if team_shields_data:
                for k_path, k_anchor in (("home_path", "home_anchor"),
                                           ("away_path", "away_anchor")):
                    if team_shields_data.get(k_path) and team_shields_data.get(k_anchor) is not None:
                        camera_timestamps.append(float(team_shields_data[k_anchor]))
            if camera_timestamps:
                audio_clip = _mix_sfx_at_timestamps(
                    audio_clip, camera_path, camera_timestamps,
                    camera_volume, audio_duration, log, label="📸 cámara",
                )
        else:
            log("ℹ️ SFX cámara no encontrado en BIBLIOTECA_PRONOSTICOS_CLIPS/sfx/")

    # 4.f Música de fondo — última capa (la voz y SFX van por encima)
    if add_background_music:
        bgm_path = _resolve_background_music()
        if bgm_path:
            audio_clip = _mix_background_music(
                audio_clip, bgm_path, bgm_volume, audio_duration, log,
            )
        else:
            log("ℹ️ Música de fondo no encontrada (busca fondo.mp3 en sfx/, musica/ o bgm/)")
    n_detected = len(segments["picks"])
    log(f"🎯 Segmentos detectados: intro {segments['intro'][0]:.1f}-{segments['intro'][1]:.1f}s "
        f"+ {n_detected} picks (esperados: {len(picks)})")
    if segments["cta"]:
        log(f"🎯 CTA midroll: {segments['cta'][0]:.1f}s → {segments['cta'][1]:.1f}s")
    else:
        log("⚠️ Sin anchor 'linkcito' — sin overlay perfil.png.")

    # Si Whisper detectó menos picks que los del payload, fallback a reparto uniforme
    if n_detected != len(picks) and len(picks) > 0:
        log(f"⚠️ Whisper no detectó todas las transiciones ({n_detected}/{len(picks)}). "
            f"Cayendo a reparto uniforme.")
        intro_end = audio_duration * 0.07  # ~7% para intro
        slot = (audio_duration - intro_end) / len(picks)
        segments["intro"] = (0.0, intro_end)
        segments["picks"] = [(intro_end + i * slot, intro_end + (i + 1) * slot)
                             for i in range(len(picks))]

    # 5. Renderizar carruseles (solo si el flag está activo — por defecto OFF)
    carousels: dict[int, str] = {}
    if show_pick_carousel:
        log(f"🖼️ Renderizando carruseles ({len(picks)} picks)...")
        carousel_dir = os.path.join(work_dir, "carousels")
        os.makedirs(carousel_dir, exist_ok=True)
        for i, pick in enumerate(picks, start=1):
            path = os.path.join(carousel_dir, f"carousel_{i}.png")
            render_pick_card(pick, i, path, video_size=video_size,
                             competition_focus=competition_focus)
            carousels[i] = path
    else:
        log("🖼️ Carrusel del pick desactivado — se mostrará solo vídeo de stock.")

    # 6. Pools de clips: por cada segmento, lista COMPLETA de la carpeta apropiada
    _progress(0.45, "Buscando clips de stock...")
    log("🎞️ Construyendo pools de clips (con caché jerárquica)...")
    clip_pools: dict[str, list[str]] = {}

    # Intro: si está activado el flag, prioriza carpeta 'intro'; si no, usa la del pick 1
    if use_intro_folder:
        intro_pool = get_clips_pool(prefer_labels=["intro"])
        if intro_pool:
            log(f"🎬 Intro: carpeta dedicada — {len(intro_pool)} clips")
        else:
            log("ℹ️ No hay carpeta 'intro' poblada — la intro hereda del pick 1")
        clip_pools["intro"] = intro_pool

    from .stock_search import _find_existing_folder as _find_dir
    for i, pick in enumerate(picks, start=1):
        home_team, away_team = parse_match(pick.get("match", ""))
        pool = get_clips_pool(
            home_team=home_team,
            away_team=away_team,
            league=pick.get("league"),
        )
        # Si la carpeta no tiene clips locales, intentar Pexels para descargar al menos 1
        if not pool:
            single = search_clip(
                league=pick.get("league"),
                country=pick.get("country"),
                sport=pick.get("sport"),
                home_team=home_team,
                away_team=away_team,
            )
            pool = [single] if single else []
        clip_pools[str(i)] = pool
        # Diagnóstico: ¿se mezclaron clips de ambos equipos o solo de uno?
        home_dir = _find_dir(home_team) if home_team else None
        away_dir = _find_dir(away_team) if away_team else None
        if home_dir and away_dir and pool:
            home_n = len(list(home_dir.glob("*.mp4")))
            away_n = len(list(away_dir.glob("*.mp4")))
            tag = f" [mix {home_team}({home_n}) + {away_team}({away_n})]" \
                  if home_n and away_n else ""
        else:
            tag = ""
        log(f"  pick #{i} ({pick.get('match', '?')}): {len(pool)} clips{tag}")

    # 7. perfil.png para CTA
    perfil_path = _resolve_perfil_png()
    if perfil_path:
        log(f"📸 perfil.png localizado: {perfil_path}")
        if not segments.get("cta"):
            log("⚠️ perfil.png existe pero no se detectó la ventana del CTA → "
                "el overlay NO se mostrará. Revisa los tokens de Whisper más arriba.")
    else:
        log("⚠️ perfil.png no encontrado en BIBLIOTECA_PRONOSTICOS_CLIPS/fotos/. "
            "Durante el CTA se mostrará el stock que toque.")

    # 8. Composición
    _progress(0.55, "Componiendo timeline visual...")
    log(f"🎬 Componiendo vídeo ({audio_duration:.1f}s)...")
    W, H = video_size
    league_overlay_data = None
    if league_overlay_anchor is not None and league_logos:
        league_overlay_data = {
            "anchor": league_overlay_anchor,
            "duration": league_overlay_duration,
            "logos": league_logos,
        }

    # ── Overlays del estilo VIRAL (tarjeta de partidos + barras con banderas) ──
    # Se generan como PNGs en work_dir y se pasan al timeline. Gated: solo viral.
    viral_overlays = None
    if video_style == "viral":
        try:
            from .viral_overlay import build_viral_hook_overlay, build_viral_match_bar
            hook_matches = []
            _seen_matches: set = set()
            for p in picks:
                _h, _a = _split_match(p.get("match", ""))
                _key = (_h.lower(), _a.lower())
                if _key in _seen_matches:
                    continue  # dos picks del mismo partido → listarlo una sola vez
                _seen_matches.add(_key)
                hook_matches.append({"home": _h, "away": _a, "time": p.get("time", "")})
            hook_png = os.path.join(work_dir, "viral_hook.png")
            build_viral_hook_overlay(hook_matches, hook_png, (W, H))
            bars: dict[int, str] = {}
            bg_picks: dict[int, str] = {}
            for i, p in enumerate(picks, start=1):
                _h, _a = _split_match(p.get("match", ""))
                bar_png = os.path.join(work_dir, f"viral_bar_{i}.png")
                build_viral_match_bar(_h, _a, target_date, p.get("time", ""), bar_png, (W, H))
                bars[i] = bar_png
                # Fondo del pick: 1) foto elegida por el usuario (override visual),
                # 2) si no, foto del EQUIPO DE LA APUESTA (o el otro si falta).
                _po = (photo_overrides or {}).get(str(i))
                photo = _resolve_override_photo(_po)
                if not photo:
                    _bet, _other = _pick_bet_team(p, _h, _a)
                    photo = _resolve_team_photo(_bet) or _resolve_team_photo(_other)
                if photo:
                    bg_picks[i] = photo
            # Fondo del gancho: override del usuario o la 1ª foto de la jornada.
            _hook_ov = _resolve_override_photo((photo_overrides or {}).get("hook"))
            bg_intro = _hook_ov or next(iter(bg_picks.values()), None)
            viral_overlays = {
                "hook": hook_png, "bars": bars,
                "bg_picks": bg_picks, "bg_intro": bg_intro,
            }
            log(f"🎨 Overlays VIRAL: tarjeta + {len(bars)} barras + "
                f"{len(bg_picks)} fotos de fondo (gancho: {'sí' if bg_intro else 'no'})")
        except Exception as e_viral:
            log(f"⚠️ Overlays viral no generados (non-fatal): {e_viral}")
            viral_overlays = None

    # team_shields_data ya se calculó arriba (paso 4.d.bis), tras decidir
    # si suprimir el overlay de liga.
    timeline = _build_visual_timeline(
        audio_duration=audio_duration,
        picks=picks,
        segments=segments,
        carousels=carousels,
        clip_pools=clip_pools,
        perfil_path=perfil_path,
        league_overlay=league_overlay_data,
        team_shields=team_shields_data,
        W=W, H=H,
        show_pick_carousel=show_pick_carousel,
        league_overlay_y_pct=league_overlay_y_pct,
        league_logo_height_pct=league_logo_height_pct,
        team_shield_y_pct=team_shield_y_pct,
        team_shield_height_pct=team_shield_height_pct,
        team_shield_x_inset_pct=team_shield_x_inset_pct,
        profile_cta_y_pct=profile_cta_y_pct,
        profile_cta_height_pct=profile_cta_height_pct,
        video_style=video_style,
        viral_overlays=viral_overlays,
    )

    # ── Muñeco viejo sabio con lip-sync (solo VIRAL), abajo-centrado, encima ──
    if video_style == "viral":
        try:
            char_path = _resolve_asset("munecos", "sabio.png")
            if char_path:
                from .viral_puppet import build_puppet_clip
                puppet = build_puppet_clip(
                    char_path, audio_path, audio_duration, (W, H), fps=fps,
                )
                if puppet is not None:
                    timeline.append({
                        "start": 0.0, "duration": audio_duration,
                        "clip_factory": (lambda c=puppet: c),
                        "is_overlay": True, "label": "muñeco_sabio",
                    })
                    log("🧙 Muñeco viejo sabio con lip-sync añadido (abajo-centro)")
            else:
                log("ℹ️ Muñeco viral no añadido: falta munecos/sabio.png en la librería.")
        except Exception as e_pup:
            log(f"⚠️ Muñeco no añadido (non-fatal): {e_pup}")

    # Log resumen del timeline (debug del overlay perfil + ligas)
    overlays = [e for e in timeline if e.get("is_overlay")]
    if overlays:
        for e in overlays:
            label = e.get("label") or "overlay"
            log(f"  ✓ {label}: {e['start']:.2f}s → {e['start']+e['duration']:.2f}s")
    elif segments.get("cta"):
        log("⚠️ Hay ventana CTA pero ningún overlay se añadió al timeline "
            "(¿perfil.png faltante o ruta mal resuelta?).")
    final = _compose_video(audio_clip, timeline, W, H)

    # 9. Guardar (nombre incluye version_id si hay varias)
    if not output_folder:
        output_folder = os.path.join(os.getcwd(), "VIDEOS_TERMINADOS")
    # Cada nicho guarda en su subcarpeta dentro de VIDEOS_TERMINADOS
    output_folder = os.path.join(output_folder, "PRONOSTICOS")
    os.makedirs(output_folder, exist_ok=True)
    suffix = f"_v{chosen_id}" if chosen_id != "legacy" else ""
    out_name = f"Pronosticos_{target_date}{suffix}.mp4"
    out_path = os.path.join(output_folder, out_name)
    if os.path.exists(out_path):
        from datetime import datetime as _dt
        out_path = os.path.join(
            output_folder,
            f"Pronosticos_{target_date}{suffix}_{_dt.now().strftime('%H%M%S')}.mp4",
        )

    _progress(0.60, "Renderizando MP4 base...")
    final.write_videofile(
        out_path, fps=fps, codec="libx264", audio_codec="aac",
        preset="ultrafast", threads=8, logger=None,
        ffmpeg_params=["-pix_fmt", "yuv420p"],
    )
    duration_s = float(final.duration)
    _progress(0.80, "MP4 base renderizado")

    # 10. Subtítulos karaoke palabra-a-palabra (estilo del nicho)
    if add_subtitles and word_timings:
        _progress(0.82, "Quemando subtítulos...")
        log("🔤 Quemando subtítulos palabra a palabra (estilo Pronósticos)...")
        try:
            from src.subtitles import render_karaoke_on_video
            from .number_parser import collapse_spanish_numbers
            from .pick_locator import annotate_word_colors
            # Convierte 'cuatro mil quinientos' → '4.500' SOLO en los subtítulos
            # (los anchors del audio ya están detectados desde los timings originales)
            sub_words = collapse_spanish_numbers(word_timings)
            collapsed = len(word_timings) - len(sub_words)
            if collapsed > 0:
                log(f"🔢 Cifras colapsadas en subtítulos: {collapsed} tokens fusionados a dígitos")
            # Pintar de VERDE-VICTORIA: cifra del bote + texto literal de cada pick
            sub_words = annotate_word_colors(
                sub_words, pick_windows, word_timings,
                pick_color=PRONOSTICOS_PICK_COLOR,
                money_color=PRONOSTICOS_PICK_COLOR,
            )
            n_green = sum(1 for w in sub_words if w.get("color"))
            if n_green:
                log(f"🟢 Subtítulos en verde-victoria: {n_green} palabras (bote + picks)")
            tmp_subs = out_path + ".subs.mp4"
            # Permitir override de la posición Y de los subs (UI: preview drag).
            subs_style = {**PRONOSTICOS_SUB_STYLE, "y_position_pct": subtitle_y_pct}
            render_karaoke_on_video(out_path, sub_words, subs_style, tmp_subs,
                                    log_callback=lambda m: log(m))
            os.replace(tmp_subs, out_path)
        except Exception as e:
            log(f"⚠️ No se quemaron subtítulos: {e}")

    # 10.b Saturación de color (post-render, ffmpeg directo)
    if saturation and abs(saturation - 1.0) > 0.01:
        _progress(0.92, "Aplicando saturación...")
        log(f"🎨 Aplicando saturación ×{saturation:.2f}...")
        tmp_sat = out_path + ".sat.mp4"
        if _apply_saturation(out_path, tmp_sat, saturation, log):
            os.replace(tmp_sat, out_path)
        else:
            try: os.remove(tmp_sat)
            except OSError: pass

    # 11. (Opcional) publicar URL
    if publish_to_redis:
        try:
            publish_video_url(target_date, out_path, duration_s,
                              version_id=str(chosen_id) if chosen_id != "legacy" else None)
            log(f"📤 URL publicada en betai:tiktokfactory_video_tomorrow (v{chosen_id})")
        except Exception as e:
            log(f"⚠️ No se pudo publicar en Redis: {e}")

    try:
        shutil.rmtree(work_dir)
    except Exception:
        pass

    _progress(1.0, "Listo")
    log(f"✨ Vídeo listo en {out_path} ({duration_s:.1f}s)")
    return out_path
