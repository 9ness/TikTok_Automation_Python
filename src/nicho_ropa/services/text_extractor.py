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


def pares(carpeta: str = "", *, refresh: bool = False) -> list[dict]:
    """Productos de la carpeta, con su foto limpia y su captura con título.

    Se cachea el RESULTADO, no solo el listado: emparejar exige medir cada
    foto, y medirla exige descargarla. Con 16 fotos eso eran 18 segundos la
    primera vez que se abría la pantalla, y volvían a serlo en cuanto se
    reiniciaba la API o entraba por otro worker. Cacheado en Redis, la espera
    se paga UNA vez para todos.
    """
    from src.nicho_pov_bof.services import drive_client as pov_drive

    carpeta = carpeta or config.CARPETA_DEFECTO

    def cargar() -> list[dict]:
        fotos = [
            drive_client.probe_dimensions(f)
            for f in drive_client.list_photos(carpeta, refresh=refresh)
        ]
        # El desempate mira las imágenes, así que solo se hace con los pares
        # que la forma y el peso no distinguen — normalmente ninguno.
        return [
            photo_pairing.desempatar_por_contenido(par, drive_client.fetch_photo)
            for par in photo_pairing.pair_folder(fotos)
        ]

    return pov_drive._listar_cacheado(
        f"nicho_ropa:pares:{carpeta}", cargar, refresh=refresh,
    )


def extract_texts(carpeta: str = "", *, on_log: OnLog = _noop) -> dict[str, dict]:
    """`{producto: {titulo, titulo_tiktok_completo, tienda, caption, emojis}}`."""
    system = (config.prompts_dir() / "text_extractor.md").read_text(encoding="utf-8")
    return motor.extract_from_pairs(
        pares(carpeta),
        system_prompt=system,
        fetch=drive_client.fetch_photo,
        on_log=on_log,
    )
