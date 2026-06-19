"""Muñeco 2D (viejo sabio) con lip-sync por amplitud de voz para el estilo VIRAL.

Sin GPU ni modelos pesados: se precalculan K estados de boca (cerrada→abierta)
sobre la imagen del personaje y, por fotograma, se elige el estado según el
volumen (RMS) de la VOZ. El muñeco se coloca abajo-centrado, encima de todo.

La caja de la boca está calibrada para el asset actual `munecos/sabio.png`
(1024×1536). Si se cambia el personaje, hay que recalibrar MOUTH_* (ver
README de cómo se localizó con una rejilla).
"""

from __future__ import annotations

# Caja de la boca en coords del PNG original del sabio (1024×1536).
_MOUTH_CX, _MOUTH_CY = 502, 420
_MOUTH_RX, _MOUTH_RY = 108, 44      # elipse de relleno (tapa la boca estática)
_MOUTH_HW = 86                       # medio-ancho de la boca animada
_SKIN = (240, 131, 74, 255)          # color piel muestreado del cartoon
_K = 7                               # nº de estados de apertura


def _draw_mouth(img, cx, cy, rx, ry, hw, skin, openness: float) -> None:
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    # 1) tapar la boca estática con piel
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=skin)
    # 2) boca animada (cavidad que crece con la apertura)
    h = int(max(2, ry * 0.09) + openness * (ry * 0.9))
    d.ellipse([cx - hw, cy - h - 6, cx + hw, cy + h + 6], fill=(90, 50, 40, 255))   # labios
    d.ellipse([cx - hw + 8, cy - h, cx + hw - 8, cy + h], fill=(120, 55, 55, 255))  # cavidad
    if openness > 0.25:
        teeth_h = max(4, int(h * 0.35))
        d.rectangle([cx - hw + 14, cy - h, cx + hw - 14, cy - h + teeth_h], fill=(245, 240, 230, 255))
        d.ellipse([cx - int(hw * 0.5), cy + int(h * 0.2), cx + int(hw * 0.5), cy + h], fill=(200, 90, 90, 255))


def _voice_envelope(audio_path: str, duration: float, fps: int):
    """Envolvente de volumen (RMS) de la voz, normalizada 0..1, una por fotograma."""
    import numpy as np
    from moviepy.editor import AudioFileClip
    n = int(duration * fps) + 1
    try:
        a = AudioFileClip(audio_path)
        sr = 22050
        snd = a.to_soundarray(fps=sr)
        a.close()
    except Exception:
        return np.zeros(n)
    if getattr(snd, "ndim", 1) == 2:
        snd = snd.mean(axis=1)
    hop = max(1, int(sr / fps))
    env = np.zeros(n)
    for i in range(n):
        seg = snd[i * hop:(i + 1) * hop]
        if len(seg):
            env[i] = float(np.sqrt(np.mean(seg ** 2)))
    p = float(np.percentile(env, 92))
    if p <= 0:
        p = float(env.max()) or 1e-6
    env = np.clip(env / p, 0.0, 1.0)
    env = np.where(env < 0.12, 0.0, env)   # umbral de silencio
    return env


def build_puppet_clip(char_path: str, voice_audio_path: str, duration: float,
                      video_size: tuple[int, int], fps: int = 30,
                      height_frac: float = 0.43, bottom_margin_frac: float = 0.0):
    """Devuelve un clip MoviePy del muñeco con la boca sincronizada a la voz,
    posicionado abajo-centrado. None si algo falla (el pipeline cae a sin muñeco)."""
    import numpy as np
    from PIL import Image
    from moviepy.editor import ImageClip, VideoClip

    base = Image.open(char_path).convert("RGBA")
    ow, oh = base.size
    W, H = video_size
    target_h = int(H * height_frac)
    scale = target_h / oh
    target_w = max(1, int(ow * scale))
    base = base.resize((target_w, target_h), Image.Resampling.LANCZOS)

    cx, cy = int(_MOUTH_CX * scale), int(_MOUTH_CY * scale)
    rx, ry = int(_MOUTH_RX * scale), int(_MOUTH_RY * scale)
    hw = int(_MOUTH_HW * scale)

    rgb_states: list = []
    alpha = None
    for k in range(_K):
        im = base.copy()
        _draw_mouth(im, cx, cy, rx, ry, hw, _SKIN, k / (_K - 1))
        arr = np.array(im)
        rgb_states.append(np.ascontiguousarray(arr[:, :, :3]))
        if alpha is None:
            alpha = (arr[:, :, 3].astype("float32") / 255.0)

    env = _voice_envelope(voice_audio_path, duration, fps)
    n = len(env)

    def make_frame(t):
        i = min(n - 1, int(t * fps))
        k = int(round(float(env[i]) * (_K - 1)))
        return rgb_states[k]

    video = VideoClip(make_frame, duration=duration)
    mask = ImageClip(alpha, ismask=True).set_duration(duration)
    clip = video.set_duration(duration).set_mask(mask)
    y = H - target_h - int(H * bottom_margin_frac)
    return clip.set_position(("center", y))
