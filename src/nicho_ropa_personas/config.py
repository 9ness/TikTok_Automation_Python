"""Nicho Ropa Con Personas (Programa 4 — módulo 7 del curso).

La prenda se enseña PUESTA por una modelo generada con IA, no en percha. Es el
hermano del módulo 8 (`src/nicho_ropa/`, sin personas): mismas fotos de Drive,
distinto prompt y distinto montaje.

El flujo tiene un paso que no existe en ningún otro nicho: **crear la chica**.
El operador busca una foto por internet, la app se la pasa a Gemini junto con
la plantilla del curso y saca un JSON con ESA chica dentro de la misma escena
(espejo, dormitorio, móvil en la mano). Ese JSON se guarda con nombre y se
copia en cada vídeo, así que la cara es siempre la misma y la cuenta tiene una
"modelo" reconocible. Es **por usuario**: la chica de uno no le sale a otro.

Ojo con la plantilla: ya trae dentro el bloque `clothing` que obliga a llevar
la ropa de la imagen de referencia. O sea que crear la chica y vestirla con el
producto es UN SOLO prompt, no dos.

Lo que se reutiliza tal cual del Nicho POV BOF, porque es idéntico:
`photo_pairing`, el emparejado limpia/ficha, `text_extractor` (con su prompt),
`audio_bank`, `duration_match` y la flecha del CTA.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

REDIS_PREFIX = os.getenv("NICHO_ROPA_PERSONAS_REDIS_PREFIX", "nicho_ropa_personas:")

# ---------------------------------------------------------------------------
# Prendas: las MISMAS carpetas de Drive que el módulo 8
# ---------------------------------------------------------------------------
# Una prenda vale para los dos nichos: en percha o puesta por la modelo. Lo que
# cambia es el prompt, no la foto. Se importan en vez de copiarlas para que
# añadir una carpeta nueva valga para los dos.
from src.nicho_ropa.config import CARPETAS, CARPETA_DEFECTO, es_carpeta_conocida  # noqa: E402,F401


def prompts_dir() -> Path:
    return Path(__file__).resolve().parent / "prompts"


def plantilla_chica() -> dict:
    """La ficha JSON del curso, ya parseada."""
    return json.loads((prompts_dir() / "plantilla_chica.json").read_text(encoding="utf-8"))


def prompt_crear_chica() -> str:
    return (prompts_dir() / "crear_chica.md").read_text(encoding="utf-8").strip()


def prompt_movimiento() -> str:
    """Prompt de animación. Se copia tal cual, sin la nota de cabecera."""
    return _sin_comentario((prompts_dir() / "movimiento_chica.md").read_text(encoding="utf-8"))


def prompt_extraer_prenda() -> str:
    """Para cuando la IA se niega a vestir a la chica (bikinis, lencería):
    aísla la prenda sobre fondo blanco para usarla como referencia."""
    return _sin_comentario((prompts_dir() / "extraer_prenda.md").read_text(encoding="utf-8"))


def _sin_comentario(texto: str) -> str:
    """Quita la nota `<!-- ... -->` de cabecera: explica el prompt a quien lea
    el archivo, pero no debe acabar en el portapapeles del operador."""
    if "-->" in texto:
        texto = texto.split("-->", 1)[1]
    return texto.strip()


# ---------------------------------------------------------------------------
# Audios locutados
# ---------------------------------------------------------------------------
# Mismo patrón que el Nicho POV BOF, pero solo voz de mujer: las cinco frases
# están grabadas con cinco voces distintas y se sortea una por vídeo, así que
# el operador no decide nada por producto.
# Ruta COMPLETA desde la raíz del mount, igual que `DRIVE_UPLOAD_ROOT` del
# POV BOF: el mount empieza en "Mi unidad", no dentro de NEBULABS.
AUDIO_DRIVE_SUBDIR = "NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Nicho_Ropa_Personas/audios/mujer"

# ---------------------------------------------------------------------------
# Montaje
# ---------------------------------------------------------------------------
# El texto va en el CENTRO, sobre la prenda — no arriba como en el POV BOF.
# Es lo que hace el nicho: la prenda se ve entera y el título encima.
TEXTO_CY = 0.42
TEXTO_ANCHO_FRAC = 0.78

# Los vídeos generados duran ~8s y las frases locutadas rondan los 11, así que
# lo normal es que falte vídeo. Se alarga rebobinando el final, igual que en el
# POV BOF (ralentizar deforma el gesto de la mano y canta).
VIDEO_TARGET_S = 8.0


# ---------------------------------------------------------------------------
# Salida
# ---------------------------------------------------------------------------
DRIVE_UPLOAD_ROOT = "NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Nicho_Ropa_Personas"


def video_dir() -> Path:
    """Dónde quedan los vídeos montados. Al Drive montado, como el resto del
    Programa 4; si no hay mount (dev local), a `API_TEMP_ROOT`."""
    from src.nicho_pov_bof.services.audio_bank import mount_root

    raiz = mount_root()
    if raiz:
        destino = raiz / DRIVE_UPLOAD_ROOT / "videos"
    else:
        destino = Path(os.getenv("API_TEMP_ROOT", "/tmp")) / "nicho_ropa_personas" / "videos"
    destino.mkdir(parents=True, exist_ok=True)
    return destino
