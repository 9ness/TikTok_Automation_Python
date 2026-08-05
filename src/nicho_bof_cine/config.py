"""Nicho BOF Cinematográfico (Programa 4 — módulo 10 del curso).

Es el Nicho POV BOF sin la mano: en vez de un POV con el producto en la mano,
el producto está colocado en un sitio real y la cámara hace un paneo alrededor.
Cambian los dos prompts (imagen y vídeo) y cambia el montaje de entrada; todo
lo demás —carpetas de Drive, fotos, textos, voces, gancho/título/CTA, flecha—
es exactamente igual, y se reutiliza tal cual.

Dos cosas propias de este nicho:

1. **Son DOS vídeos por producto.** El prompt de imagen se usa para generar dos
   imágenes y de cada una sale un clip de ~5s. Los dos se pegan seguidos, así
   que hasta que no están los dos subidos no hay nada que montar.
2. **La duración se cuadra cambiando la VELOCIDAD.** Los dos clips suman ~10s y
   las frases locutadas rondan 10-12s. En el POV BOF eso se resuelve rebobinando
   el final, pero aquí el plano es un paneo continuo y el rebobinado se ve
   clarísimo (la cámara va y vuelve). Ralentizar un 5% un movimiento de cámara
   no lo nota nadie.

El progreso es INDEPENDIENTE del Nicho POV BOF aunque las carpetas sean las
mismas: completar "1 Pront Flow" allí no la completa aquí — son vídeos
distintos del mismo producto.
"""

from __future__ import annotations

import os
from pathlib import Path

REDIS_PREFIX = os.getenv("NICHO_BOF_CINE_REDIS_PREFIX", "nicho_bof_cine:")

# Las MISMAS fuentes del Nicho POV BOF: mismo Drive, mismas carpetas, mismas
# fotos. Se importan para que añadir una fuente valga para los dos.
from src.nicho_pov_bof.config import SOURCES, source_path  # noqa: E402,F401


def prompts_dir() -> Path:
    return Path(__file__).resolve().parent / "prompts"


def _sin_comentario(texto: str) -> str:
    """Quita la nota `<!-- ... -->` de cabecera: explica el prompt a quien lea
    el archivo, pero no debe acabar en el portapapeles del operador."""
    if "-->" in texto:
        texto = texto.split("-->", 1)[1]
    return texto.strip()


def prompt_imagen() -> str:
    return _sin_comentario((prompts_dir() / "prompt_imagen.md").read_text(encoding="utf-8"))


def prompt_video() -> str:
    return _sin_comentario((prompts_dir() / "prompt_video.md").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Montaje
# ---------------------------------------------------------------------------
# Cuántos clips hacen falta antes de montar. Con uno solo no se encola nada: el
# vídeo quedaría a medias y habría que rehacerlo.
CLIPS_POR_VIDEO = 2

# Hasta dónde se puede estirar o encoger el vídeo para que cuadre con la voz.
# Un paneo de cámara al 0,90 pasa desapercibido; por debajo empieza a
# arrastrarse y se nota. Fuera de este rango se recorta/alarga como en el POV
# BOF en vez de deformar el movimiento.
VELOCIDAD_MIN = 0.85
VELOCIDAD_MAX = 1.15


def video_dir() -> Path:
    """Dónde quedan los vídeos montados."""
    from src.nicho_pov_bof.services.audio_bank import mount_root

    raiz = mount_root()
    if raiz:
        destino = raiz / "NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Nicho_BOF_Cine" / "videos"
    else:
        destino = Path(os.getenv("API_TEMP_ROOT", "/tmp")) / "nicho_bof_cine" / "videos"
    destino.mkdir(parents=True, exist_ok=True)
    return destino
