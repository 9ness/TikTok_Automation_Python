"""Banco de audios locutados del Nicho Ropa Con Personas.

Cinco voces de mujer diciendo LA MISMA frase, en
`TIKTOK_SHOP_AI_PRO/Nicho_Ropa_Personas/audios/mujer/`, nombradas
`mujer<voz>_frase<n>.mp3` — misma convención que el Nicho POV BOF para que
añadir frases nuevas no obligue a aprenderse otro esquema.

Se sortea una por vídeo, sin que el operador elija: con 60-80 productos al día
una decisión más por producto es tiempo, y lo único que importa es que las
voces salgan repartidas.

**No se nivela aquí.** El montaje ya normaliza la voz a -11 LUFS con doble
pasada, así que da igual que estas cinco lleguen entre -16 y -27 LUFS (llegan:
son 10 dB de diferencia). Normalizarlas dos veces solo añadiría bombeo.
"""

from __future__ import annotations

import random
from pathlib import Path

from src.nicho_pov_bof.services.audio_bank import mount_root
from src.nicho_ropa_personas import config

_AUDIO_EXTS = {".mp3", ".wav", ".m4a"}


def audios_dir() -> Path | None:
    root = mount_root()
    return None if root is None else root / config.AUDIO_DRIVE_SUBDIR


def list_audios() -> list[Path]:
    """Los audios disponibles, en orden estable."""
    d = audios_dir()
    if d is None or not d.is_dir():
        return []
    return sorted(
        p for p in d.iterdir()
        if p.is_file() and p.suffix.lower() in _AUDIO_EXTS
    )


def pick_random(*, rng: random.Random | None = None) -> Path:
    """Uno al azar. Falla con un mensaje útil si el banco está vacío."""
    audios = list_audios()
    if not audios:
        d = audios_dir()
        raise FileNotFoundError(
            "No hay audios locutados para el Nicho Ropa Con Personas. Se "
            f"esperan en {d or config.AUDIO_DRIVE_SUBDIR} "
            "(mujer1_frase1.mp3, mujer2_frase1.mp3…)."
        )
    return (rng or random).choice(audios)
