"""Título / tienda / caption a partir de la captura de la ficha SUBIDA.

El motor es el mismo del Nicho POV BOF (`extract_from_pairs`) con su mismo
prompt: la foto que sube el operador es exactamente la misma captura de la
ficha de TikTok Shop que allí se baja de Drive, así que lo que hay que leer no
cambia. Lo único que cambia es de dónde sale el fichero, y eso es justo lo que
el motor recibe por parámetro (`fetch`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from src.nicho_pov_bof.services import text_extractor as motor

OnLog = Callable[[str], None]


def _noop(_: str) -> None:
    return None


def _fetch_local(file_id: str, *, suffix: str = ".jpg") -> Path:
    """El "file ID" aquí ya ES la ruta en disco: no hay nada que descargar."""
    ruta = Path(file_id)
    if not ruta.is_file():
        raise ValueError(f"no está la foto: {file_id}")
    return ruta


def extraer(productos: list[dict], *, on_log: OnLog = _noop) -> dict[str, dict]:
    """`[{id, foto_ficha, foto_limpia}]` → `{id: {titulo, tienda, caption, …}}`.

    Se manda la foto de la FICHA; si un producto no la tiene se manda la
    limpia, igual que hace el POV BOF cuando en Drive solo hay una foto (el
    motor ya contempla ese caso y lo avisa por log).
    """
    pares = []
    for prod in productos:
        ficha = str(prod.get("foto_ficha") or "")
        limpia = str(prod.get("foto_limpia") or "")
        pares.append({
            "producto": str(prod.get("id") or ""),
            "titled": {"id": ficha, "name": Path(ficha).name} if ficha else None,
            "clean": {"id": limpia, "name": Path(limpia).name} if limpia else None,
        })
    if not pares:
        return {}
    import src.nicho_pov_bof as pov_pkg

    prompt = (
        Path(pov_pkg.__file__).resolve().parent / "prompts" / "text_extractor.md"
    ).read_text(encoding="utf-8")
    return motor.extract_from_pairs(
        pares,
        system_prompt=prompt,
        fetch=_fetch_local,
        on_log=on_log,
    )
