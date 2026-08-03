"""Textos de cada prenda a partir de su captura con título.

El motor es el mismo del Nicho POV BOF (`extract_from_pairs`): validación,
descarte de rellenos tipo "Información no disponible" y reintento de los que
el modelo se deja. Lo que cambia aquí es el prompt —esta ropa no lleva ningún
texto quemado en el vídeo, así que no se piden gancho ni CTA— y de qué Drive
salen las fotos.
"""

from __future__ import annotations

from typing import Callable

from src.nicho_pov_bof.services import photo_pairing, text_extractor as motor
from src.nicho_ropa import config
from src.nicho_ropa.services import drive_client

OnLog = Callable[[str], None]


def _noop(_: str) -> None:
    return None


def pares(*, refresh: bool = False) -> list[dict]:
    """Productos de la carpeta, con su foto limpia y su captura con título."""
    fotos = [
        drive_client.probe_dimensions(f)
        for f in drive_client.list_photos(refresh=refresh)
    ]
    return photo_pairing.pair_folder(fotos)


def extract_texts(*, on_log: OnLog = _noop) -> dict[str, dict]:
    """`{producto: {titulo, titulo_tiktok_completo, tienda, caption, emojis}}`."""
    system = (config.prompts_dir() / "text_extractor.md").read_text(encoding="utf-8")
    return motor.extract_from_pairs(
        pares(),
        system_prompt=system,
        fetch=drive_client.fetch_photo,
        on_log=on_log,
    )
