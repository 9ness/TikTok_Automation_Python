"""Nicho POV BOF Largo (Programa 4 — Tiktok Shop AI Pro).

Es el Nicho POV BOF con UNA diferencia de fondo: la voz no sale de un banco de
frases grabadas, sino de un **guion escrito para ESE producto** por la IA y
locutado con Fish Audio. Como el guion habla del producto concreto, dura más
que las frases genéricas (~20s en vez de ~11), y por eso el vídeo son **varios
clips pegados** en vez de uno: con los clips de 8s de la plataforma nueva, un
guion de veinte segundos son tres (ver `clips_necesarios`).

Todo lo demás es idéntico y se reutiliza tal cual: mismas carpetas de Drive,
mismas fotos, mismos textos extraídos, mismo bloque de gancho/título/CTA, misma
flecha y el mismo montador.

**La duración la manda el audio.** Se pegan los clips y se recorta a
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
# Dos clips de ~10s. Hasta que no están todos los que hacen falta no se encola
# nada: con uno solo no hay vídeo que montar (mismo criterio que el BOF
# Cinematográfico).
CLIPS_POR_VIDEO = 1
# Cuánto dura un clip generado. La plataforma de vídeo los da de OCHO segundos
# (antes eran de diez); si algún día vuelven a ser de diez, se cambia aquí y
# todo lo demás —cuántos clips pedir y cuánto guion cabe— sale solo.
CLIP_TARGET_S = float(os.getenv("POV_BOF_LARGO_CLIP_S", "8"))
# Más de cuatro deja de parecer una toma continua.
CLIPS_MAXIMOS = 4
# Hasta dónde se puede estirar un clip sin que se note: el montaje ya alarga un
# poco cada uno para cuadrar con la voz (`match_video_to_audio`). Un 20% sobre
# los 8s son 9,6s, que es justo el margen que pidió el operador ("uno o dos
# segundos"). De ahí salen los cortes: 1 clip hasta ~9,5s, 2 hasta ~19s, 3
# hasta ~28,5s y 4 hasta ~38s.
CLIP_MAX_S = round(CLIP_TARGET_S * 1.2, 1)

# ---------------------------------------------------------------------------
# Guion
# ---------------------------------------------------------------------------
# El prompt es del operador y va LITERAL, sin resumir (`prompts/guion.md`).
#
# OJO con el tope de caracteres: el documento original pide 260 "para un vídeo
# de 15 segundos", pero su PROPIO ejemplo tiene 357 y a 18 car/s eso son 20s,
# no 15. Forzar los 260 con reintentos deja el guion telegráfico ("¿Piel grasa?
# ¿Residuo blanco?"). Así que el tope es la DURACIÓN que se quiere, no lo que
# quepa en los clips.
# Velocidad de locución, MEDIDA sobre vídeos ya montados (guion / duración del
# audio de Fish). No es un detalle: con el mismo guion, "audio hombre vendedor"
# corre a 23,6 car/s y "influencer" a 15,4 — 20s con una son 30s con la otra, y
# de eso depende cuántos clips hay que generar.
CARACTERES_POR_SEGUNDO = 17.8      # media de los 20 vídeos medidos
# Para decidir CUÁNTOS CLIPS se usa la voz LENTA, no la media: la voz se sortea
# después de escribir el guion, así que hay que ponerse en lo peor. Quedarse
# corto obliga a estirar el vídeo y deforma el gesto de la mano; sobrar medio
# clip no se nota, porque el montaje recorta a la duración de la voz.
CARACTERES_POR_SEGUNDO_LENTA = 15.4
# Lo que tiene que DURAR el guion, que es una decisión del formato y no del
# tamaño de los clips: el del curso cuenta el producto en unos veinte segundos.
# Antes se calculaba como "lo que quepa en los clips" y al pasar a clips de 8s
# habría dado 683 caracteres — guiones del doble de largos sin que nadie lo
# pidiera. Los clips se adaptan al guion, no al revés.
GUION_OBJETIVO_S = 20.0
GUION_MAX_CARACTERES = int(GUION_OBJETIVO_S * CARACTERES_POR_SEGUNDO)  # ~356


def segundos_de(guion: str, voz: str = "") -> float:
    """Cuánto va a durar ese guion locutado, en segundos.

    Con `voz` (el `reference_id` o su etiqueta) se usa SU velocidad medida; sin
    ella, la media. Las medidas se van afinando solas con cada vídeo que se
    monta (ver `services/velocidad_voz.py`).
    """
    n = len((guion or "").strip())
    if not n:
        return 0.0
    from src.nicho_pov_bof_largo.services import velocidad_voz

    return n / velocidad_voz.caracteres_por_segundo(voz)


def clips_necesarios(guion: str, voz: str = "") -> int:
    """Cuántos clips hacen falta para que quepa ese guion.

    La voz manda: si dura más de lo que dan los clips, el montaje tiene que
    estirarlos y el gesto de la mano se deforma. Se calcula por caracteres
    porque hay que saberlo ANTES de locutar, cuando aún no hay audio que medir.

    Sin voz elegida se cuenta con la más lenta del banco: es lo que evita
    quedarse corto justo cuando toca la que más se alarga.
    """
    n = len((guion or "").strip())
    if not n:
        return CLIPS_POR_VIDEO
    if voz:
        from src.nicho_pov_bof_largo.services import velocidad_voz

        segundos = n / velocidad_voz.caracteres_por_segundo(voz)
    else:
        segundos = n / CARACTERES_POR_SEGUNDO_LENTA
    hacen_falta = -(-int(segundos * 100) // int(CLIP_MAX_S * 100))  # techo
    return max(CLIPS_POR_VIDEO, min(CLIPS_MAXIMOS, hacen_falta))


def prompts_dir() -> Path:
    return Path(__file__).resolve().parent / "prompts"


def prompt_guion(plazos: bool = False) -> str:
    """El prompt del curso, con el bloque de plazos pegado si toca.

    El de `guion.md` va LITERAL y nunca se toca. Lo de plazos es un añadido al
    final (`guion_plazos.md`), no una versión aparte: así el guion de un
    producto caro es el mismo de siempre con una frase más, y cualquier cambio
    del curso se sigue aplicando a los dos.
    """
    base = (prompts_dir() / "guion.md").read_text(encoding="utf-8").strip()
    if not plazos:
        return base
    extra = (prompts_dir() / "guion_plazos.md").read_text(encoding="utf-8")
    # El fichero lleva una cabecera para quien lo lea en el repo; a Gemini solo
    # se le manda lo que va después del separador.
    _, _, cuerpo = extra.partition("\n---\n")
    return f"{base}\n\n{cuerpo.strip()}"


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
        {"id": "7f44c1fdaef9471488d531e66aa01e9a", "label": "Influencer 1 colombiana"},
        {"id": "b8db28cc8d7e4be4a6fc2cce8a260ca5", "label": "Voz Influencer Tuxpa Woman"},
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
