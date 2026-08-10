"""Nicho POV BOF Largo (Programa 4 — Tiktok Shop AI Pro).

Es el Nicho POV BOF con UNA diferencia de fondo: la voz no sale de un banco de
frases grabadas, sino de un **guion escrito para ESE producto** por la IA y
locutado con Fish Audio. Como el guion habla del producto concreto, dura más
que las frases genéricas (~20s en vez de ~11), y por eso el vídeo son **dos
clips de 10s** pegados en vez de uno.

Todo lo demás es idéntico y se reutiliza tal cual: mismas carpetas de Drive,
mismas fotos, mismos textos extraídos, mismo bloque de gancho/título/CTA, misma
flecha y el mismo montador.

**La duración la manda el audio.** Se pegan los dos clips (~20s) y se recorta a
la duración exacta de la voz con `match_video_to_audio`, que ya hace las dos
cosas: si sobra vídeo lo corta y si falta lo alarga rebobinando. O sea que un
guion de 18s deja un vídeo de 18s, sin tocar la velocidad.

**Por qué su propio progreso y no el del POV BOF**: haber hecho un producto
allí no significa haberlo hecho aquí — son vídeos distintos del mismo producto.
"""

from __future__ import annotations

import os
from pathlib import Path

REDIS_PREFIX = os.getenv("NICHO_POV_BOF_LARGO_REDIS_PREFIX", "nicho_pov_bof_largo:")

# Las MISMAS fuentes del Nicho POV BOF: mismo Drive, mismas carpetas, mismas
# fotos. Se importan para que añadir una fuente valga para los dos.
from src.nicho_pov_bof.config import SOURCES, source_path  # noqa: E402,F401

# ---------------------------------------------------------------------------
# Clips
# ---------------------------------------------------------------------------
# Dos clips de ~10s. Hasta que no están los dos subidos no se encola nada: con
# uno solo no hay vídeo que montar (mismo criterio que el BOF Cinematográfico).
CLIPS_POR_VIDEO = 2
CLIP_TARGET_S = 10.0

# ---------------------------------------------------------------------------
# Guion
# ---------------------------------------------------------------------------
# El prompt es del operador y va LITERAL, sin resumir (`prompts/guion.md`).
#
# OJO con el tope de caracteres: el documento original pide 260 "para un vídeo
# de 15 segundos", pero su PROPIO ejemplo tiene 357 y a 18 car/s eso son 20s,
# no 15. Forzar los 260 con reintentos deja el guion telegráfico ("¿Piel grasa?
# ¿Residuo blanco?"). Así que el tope real es el que cabe en los dos clips.
CARACTERES_POR_SEGUNDO = 18.2      # medido con voces reales de Fish
GUION_MAX_CARACTERES = int(CLIPS_POR_VIDEO * CLIP_TARGET_S * CARACTERES_POR_SEGUNDO)  # 364


def prompts_dir() -> Path:
    return Path(__file__).resolve().parent / "prompts"


def prompt_guion() -> str:
    return (prompts_dir() / "guion.md").read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------------
# Voces (Fish Audio)
# ---------------------------------------------------------------------------
# Banco elegido por el operador escuchando muestras. El operador solo elige
# SEXO; la voz concreta se sortea, igual que en el POV BOF con sus mp3.
#
# Son `reference_id` de la biblioteca pública de Fish. Se eligieron de título
# genérico a propósito: las voces más usadas del catálogo español son clones de
# personas identificables (Farid Dieck, Mario Castañeda…) y usarlas en vídeos
# de afiliación es suplantación.
VOCES: dict[str, list[dict[str, str]]] = {
    "hombre": [
        {"id": "51cdce697d8c4624b3135d473b4754e6", "label": "Vendedor Amable"},
        {"id": "a0bd834b585944ba8200643a8b5dc405", "label": "audio hombre vendedor"},
        {"id": "c5a26d53f9fa41dc92479d065a2c9b8e", "label": "Voz Vendedor Colombiano"},
        {"id": "77087ce820a74b2793a67371db067e89", "label": "Luquitas Influencer"},
        {"id": "d2ee7bb7cb3946d1b1994c1e4a6ff44e", "label": "MY COMBOY (El vaqueroff)"},
    ],
    "mujer": [
        {"id": "b08746cb224a4277a14b901c3591c3b9", "label": "voz publicidad"},
        {"id": "3fa82ba878ca4740ac6bba8ae0c38d76", "label": "Voz Clara Influencer 1"},
        {"id": "a67aae7d95154eecb6ad61c766de7afb", "label": "Ely Bell's influencer"},
        {"id": "560b6e4e2e824ef5b87e8158544974af", "label": "Voz de Influencer"},
        {"id": "c42b307a13c746d09f46d6799fd0f71f", "label": "Chica influencer"},
        {"id": "9ba6a6e4ecd84af58b7913f3944f54f2", "label": "influencer"},
        {"id": "ad03df9a92704fa9a0d931225754d057", "label": "Vendedora (joven)"},
        {"id": "677365711ffb439e80a57f6c737f6baa", "label": "Vendedora virsl"},
        {"id": "58852a3fb88946a18a1be7c69ed13774", "label": "Vendedora belixe"},
        {"id": "9e13aa87d990415fb435b63562cb6893", "label": "Voz Vendedora Amigable"},
        {"id": "c16b3df04d9c4e9b9264091c2e6baa45", "label": "Voz vendedora viral ttw"},
    ],
}

SEXOS = tuple(VOCES)

# Modelo gratuito de Fish. El de pago es el mismo motor con licencia comercial
# plena; se cambia aquí (ver `services/voz.py` para la tarifa).
FISH_MODEL = os.getenv("FISH_MODEL", "s2.1-pro-free")
FISH_TTS_URL = "https://api.fish.audio/v1/tts"


def fish_api_key() -> str:
    return (os.getenv("FISH_API_KEY") or "").strip()


# ---------------------------------------------------------------------------
# Nivelado de la voz
# ---------------------------------------------------------------------------
# El operador la quiere "rozando la línea roja sin distorsionar". La cadena es
# la del POV BOF pero con MÁS margen de pico: con `TP=-1.5` y limitador 0.9
# —los valores de allí— una voz de Fish salió a +0,20 dBTP, o sea recortando.
# Los audios de Fish tienen picos distintos a las grabaciones humanas.
# Medido con TP=-2.0 y 0.89: -13,1/-13,6 LUFS con picos en -1,1/-1,6 dBTP.
VOZ_CADENA = (
    "acompressor=threshold=-20dB:ratio=4:attack=5:release=120:makeup=2,"
    "speechnorm=e=8:r=0.0008:l=1"
)
VOZ_LUFS = -11.0
VOZ_TP = -2.0
VOZ_LIMITER = 0.89

# ---------------------------------------------------------------------------
# Recorte de silencios (para que el vídeo no quede más largo de la cuenta)
# ---------------------------------------------------------------------------
# Fish a veces deja aire muerto al principio/final y alguna pausa larga entre
# frases. Se recorta, pero SIN dejarlo telegráfico:
#   - Principio: se quita el silencio de entrada dejando una pizca (0,08s) para
#     que no empiece cortado de golpe.
#   - Medio y final (`stop_periods=-1`): las pausas de más de `stop_duration`
#     se capan a `stop_silence` (~0,3s) en vez de eliminarse; así una pausa de
#     1,5s baja a 0,3s pero SIGUE habiendo pausa — respira, no atropella.
# `detection=peak` es conservador: solo cuenta como silencio lo que baje de
# -40 dB de pico, así que no se come el arranque suave de una palabra.
VOZ_SILENCIO = (
    "silenceremove="
    "start_periods=1:start_silence=0.08:start_threshold=-40dB:"
    "stop_periods=-1:stop_duration=0.4:stop_silence=0.3:stop_threshold=-40dB:"
    "detection=peak"
)


# ---------------------------------------------------------------------------
# Salida
# ---------------------------------------------------------------------------
DRIVE_UPLOAD_ROOT = "NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Nicho_POV_BOF_Largo"


def video_dir() -> Path:
    """Dónde quedan los vídeos montados. Al Drive montado, como el resto del
    Programa 4; si no hay mount (dev local), a `API_TEMP_ROOT`."""
    from src.nicho_pov_bof.services.audio_bank import mount_root

    raiz = mount_root()
    if raiz:
        destino = raiz / DRIVE_UPLOAD_ROOT / "videos"
    else:
        destino = Path(os.getenv("API_TEMP_ROOT", "/tmp")) / "nicho_pov_bof_largo" / "videos"
    destino.mkdir(parents=True, exist_ok=True)
    return destino
