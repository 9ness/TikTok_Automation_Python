"""Textos de cada gorra a partir de su captura con título.

El motor es el mismo del Nicho POV BOF (`extract_from_pairs`): validación,
descarte de rellenos tipo "Información no disponible" y reintento de los que el
modelo se deja. Lo que cambia es de qué Drive salen las fotos y CÓMO se
emparejan (de dos en dos por orden, ver `pairing.py`).

Este nicho no monta vídeo, así que del texto solo importan título, tienda y
caption: es lo que el operador copia al publicar.
"""

from __future__ import annotations

from typing import Callable

from src.nicho_gorras.services import pairing as photo_pairing
from src.nicho_pov_bof.services import text_extractor as motor
from src.nicho_gorras import config
from src.nicho_gorras.services import drive_client

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
        # Sin desempate por contenido: aquí la forma ya separa las dos
        # (la ficha es un pantallazo de 2,17 y la limpia ronda el cuadrado).
        return photo_pairing.pair_folder(fotos)

    return pov_drive._listar_cacheado(
        f"nicho_gorras:pares:{carpeta}", cargar, refresh=refresh,
    )


def extract_texts(carpeta: str = "", *, on_log: OnLog = _noop) -> dict[str, dict]:
    """`{producto: {titulo, titulo_tiktok_completo, tienda, caption, emojis}}`."""
    from src.nicho_ropa import config as ropa_config

    # El prompt de extracción del módulo 8 vale tal cual: pide título, título
    # de TikTok, tienda y caption leyendo la ficha, que es lo mismo que hace
    # falta aquí. Copiarlo sería tener dos que arreglar cuando falle uno.
    system = (ropa_config.prompts_dir() / "text_extractor.md").read_text(encoding="utf-8")
    return motor.extract_from_pairs(
        pares(carpeta),
        system_prompt=system,
        fetch=drive_client.fetch_photo,
        on_log=on_log,
    )
