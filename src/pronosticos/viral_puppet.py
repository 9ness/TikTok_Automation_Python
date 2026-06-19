"""Muñeco 2D (viejo sabio) con lip-sync por amplitud de voz para el estilo VIRAL.

Sin GPU ni modelos pesados: se precalculan K estados de boca (cerrada→abierta)
sobre la imagen del personaje y, por fotograma, se elige el estado según el
volumen (RMS) de la VOZ. El muñeco se coloca arriba-centrado en la mitad
inferior, encima de todo.

Boca calibrada para el asset `munecos/sabio.png` (1024×1536), que se generó con
piel lisa alrededor de la boca para que el parche se funda sin artefactos. Si se
cambia el personaje, recalibrar _MOUTH_* y _SKIN (localizar con una rejilla).
"""

from __future__ import annotations

# Caja de la boca en coords del PNG original del sabio (1024×1536).
_MOUTH_CX, _MOUTH_CY = 505, 493
_COVER_RX, _COVER_RY = 110, 52       # elipse de relleno (tapa la boca estática, con bordes difuminados)
_MOUTH_HW = 78                       # medio-ancho de la boca animada
_SKIN = (253, 172, 110, 255)         # piel lisa muestreada alrededor de la boca
_LINE = (74, 42, 28, 255)            # color del trazo del cartoon (labios)
_K = 12                              # nº de estados de apertura (suave)


def _draw_mouth(img, cx, cy, crx, cry, hw, openness: float) -> None:
    """Funde un parche de piel (bordes difuminados → sin círculo visible) sobre la
    boca estática y dibuja una boca animada encima (labios + dientes + lengua)."""
    from PIL import Image, ImageDraw, ImageFilter
    cov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(cov).ellipse([cx - crx, cy - cry, cx + crx, cy + cry], fill=_SKIN)
    a = cov.split()[3].filter(ImageFilter.GaussianBlur(max(3, int(crx * 0.08))))
    cov.putalpha(a)
    img.alpha_composite(cov)

    d = ImageDraw.Draw(img)
    oh = int(2 + openness * (cry * 0.85))   # medio-alto de la apertura
    if openness < 0.08:
        # cerrada: sonrisa suave
        d.arc([cx - hw, cy - int(cry * 0.5), cx + hw, cy + int(cry * 0.5)],
              start=18, end=162, fill=_LINE, width=max(6, int(hw * 0.12)))
    else:
        t, b = cy - oh, cy + oh
        lip = max(5, int(hw * 0.09))
        d.ellipse([cx - hw - lip, t - lip, cx + hw + lip, b + lip], fill=_LINE)          # labios
        d.ellipse([cx - hw, t, cx + hw, b], fill=(110, 45, 45, 255))                     # cavidad
        th = max(4, int(oh * 0.5))
        d.rounded_rectangle([cx - hw + 10, t, cx + hw - 10, t + th], radius=6,
                            fill=(248, 243, 232, 255))                                   # dientes
        if openness > 0.45:
            d.ellipse([cx - int(hw * 0.55), b - int(oh * 0.7), cx + int(hw * 0.55), b],
                      fill=(206, 96, 96, 255))                                           # lengua


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
                      height_frac: float = 0.43, bottom_margin_frac: float = 0.12):
    """Devuelve un clip MoviePy del muñeco con la boca sincronizada a la voz,
    arriba-centrado en la mitad inferior. None si algo falla (cae a sin muñeco)."""
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
    crx, cry = int(_COVER_RX * scale), int(_COVER_RY * scale)
    hw = int(_MOUTH_HW * scale)

    rgb_states: list = []
    alpha = None
    for k in range(_K):
        im = base.copy()
        _draw_mouth(im, cx, cy, crx, cry, hw, k / (_K - 1))
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
