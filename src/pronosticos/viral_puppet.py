"""Muñeco 2D (viejo sabio) con lip-sync por amplitud de voz para el estilo VIRAL.

Sin GPU ni modelos pesados: el personaje (`munecos/sabio.png`) viene SIN BOCA
(la boca original se borró con inpaint, dejando piel lisa bajo el bigote), así
que aquí se dibuja la boca animada directamente sobre piel limpia — sin parches
ni doble boca. Se precalculan K estados (cerrada→abierta) y, por fotograma, se
elige según el volumen (RMS) de la VOZ.

Si se cambia el personaje, recalibrar _MOUTH_* (centro/ancho de la boca) y
asegurarse de que el asset NO tiene boca dibujada.
"""

from __future__ import annotations

# Posición de la boca en coords del PNG del sabio SIN BOCA (1024×1536).
_MOUTH_CX, _MOUTH_CY = 492, 540
_MOUTH_HW = 74                       # medio-ancho de la boca
_LINE = (74, 42, 28, 255)            # color del trazo del cartoon (labios)
_K = 12                              # nº de estados de apertura (suave)


def _draw_mouth(img, cx, cy, hw, openness: float) -> None:
    """Dibuja la boca animada sobre la piel limpia (sin tapar nada: el asset no
    tiene boca). Cerrada = sonrisa suave; abierta = labios + dientes + lengua."""
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    oh = int(3 + openness * 38)
    if openness < 0.08:
        d.arc([cx - hw, cy - 22, cx + hw, cy + 22], start=15, end=165,
              fill=_LINE, width=11)
    else:
        t, b = cy - oh, cy + oh
        d.ellipse([cx - hw - 7, t - 7, cx + hw + 7, b + 7], fill=_LINE)         # labios
        d.ellipse([cx - hw, t, cx + hw, b], fill=(125, 55, 55, 255))            # cavidad
        th = max(5, int(oh * 0.5))
        d.rounded_rectangle([cx - hw + 12, t, cx + hw - 12, t + th], radius=6,
                            fill=(248, 243, 232, 255))                          # dientes
        if openness > 0.45:
            d.ellipse([cx - 40, b - int(oh * 0.7), cx + 40, b],
                      fill=(206, 96, 96, 255))                                  # lengua


def _voice_envelope(audio_path: str, duration: float, fps: int):
    """Envolvente de volumen (RMS) de la voz, normalizada 0..1, una por fotograma.

    Lee el audio con ffmpeg → WAV PCM y lo decodifica con `wave` (NO con MoviePy
    `to_soundarray`, roto con esta numpy → devolvía silencio y la boca no se movía)."""
    import numpy as np
    import os
    import subprocess
    import tempfile
    import wave
    n = int(duration * fps) + 1
    sr = 22050
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        subprocess.run(
            ["ffmpeg", "-y", "-i", audio_path, "-vn", "-ac", "1",
             "-ar", str(sr), "-acodec", "pcm_s16le", tmp],
            capture_output=True, timeout=120,
        )
        with wave.open(tmp, "rb") as w:
            sr = w.getframerate()
            raw = w.readframes(w.getnframes())
        snd = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    except Exception:
        return np.zeros(n)
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except Exception:
                pass
    if snd.size == 0:
        return np.zeros(n)
    hop = max(1, int(sr / fps))
    env = np.zeros(n)
    for i in range(n):
        seg = snd[i * hop:(i + 1) * hop]
        if len(seg):
            env[i] = float(np.sqrt(np.mean(seg ** 2)))
    p = float(np.percentile(env, 90))
    if p <= 0:
        p = float(env.max()) or 1e-6
    env = np.clip(env / p, 0.0, 1.0)
    env = np.where(env < 0.10, 0.0, env)   # umbral de silencio
    return env


def build_puppet_clip(char_path: str, voice_audio_path: str, duration: float,
                      video_size: tuple[int, int], fps: int = 30,
                      height_frac: float = 0.43, bottom_margin_frac: float = 0.12):
    """Devuelve un clip MoviePy del muñeco con la boca sincronizada a la voz,
    arriba-centrado en la mitad inferior. None si algo falla (cae a sin muñeco)."""
    import numpy as np
    from PIL import Image
    from moviepy.editor import ImageClip, VideoClip

    full = Image.open(char_path).convert("RGBA")
    ow, oh_px = full.size
    W, H = video_size
    target_h = int(H * height_frac)
    scale = target_h / oh_px
    target_w = max(1, int(ow * scale))

    rgb_states: list = []
    alpha = None
    for k in range(_K):
        im = full.copy()
        _draw_mouth(im, _MOUTH_CX, _MOUTH_CY, _MOUTH_HW, k / (_K - 1))
        im = im.resize((target_w, target_h), Image.Resampling.LANCZOS)
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

    # Movimiento sutil de "vida": bote vertical (más al hablar) + leve vaivén
    # lateral. Solo anima la posición (barato), sin rigging de brazos.
    import math
    base_y = H - target_h - int(H * bottom_margin_frac)
    x_center = (W - target_w) // 2

    def _pos(t):
        i = min(n - 1, int(t * fps))
        e = float(env[i])
        bob = math.sin(t * 2 * math.pi * 1.7) * (3.0 + 9.0 * e)   # rebote, más al hablar
        sway = math.sin(t * 2 * math.pi * 0.45) * 7.0             # vaivén lento
        return (int(x_center + sway), int(base_y + bob))

    return clip.set_position(_pos)
