"""Guion locutado + mensaje subliminal, por producto, con Gemini.

El prompt es del operador y va LITERAL (`prompts/guion.md`): se le pasa tal
cual, sin resumirlo. Resumirlo ya salió mal una vez — la versión condensada
perdía matices y el guion salía sin gracia.

Lo único que se añade al final es el formato de salida (JSON), porque aquí no
hay una persona leyendo la respuesta como en ChatGPT.

**Sin bucle de recorte.** El documento pide 260 caracteres, pero su propio
ejemplo tiene 357; forzar los 260 con reintentos deja frases telegráficas
("¿Piel grasa? ¿Residuo blanco? ¿Maquillaje mal?"). Si el guion se pasa de lo
que cabe en los dos clips solo se AVISA: el montaje ya cuadra la duración, y un
guion bueno y un poco largo vale más que uno corto y roto.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from src.nicho_pov_bof_largo import config

OnLog = Callable[[str], None]
_noop: OnLog = lambda _m: None

_FORMATO = (
    '\n\nDevuelve SOLO un JSON, sin nada más:\n'
    '{"nombre": "...", "guion": "...", "subliminal": "primera linea\\nsegunda linea"}'
)


def escribir(
    *,
    titulo: str,
    tienda: str = "",
    caption: str = "",
    foto: Path | None = None,
    on_log: OnLog = _noop,
) -> dict:
    """`{nombre, guion, subliminal}` para un producto.

    `foto` es la foto limpia. El prompt insiste en NO mandar la foto sola, así
    que siempre va acompañada de la descripción; si no hay foto se manda solo
    el texto (Gemini se apaña, pero el guion sale más genérico).
    """
    from src.tiktok_shop.api.gemini import generate_json

    descripcion = f"Producto: {titulo.strip()}."
    if tienda:
        descripcion += f" Tienda: {tienda.strip()}."
    if caption:
        descripcion += f" Descripción: {caption.strip()}"

    imagenes = [str(foto)] if foto else None
    datos = generate_json(config.prompt_guion() + _FORMATO, descripcion, images=imagenes)
    if not isinstance(datos, dict):
        raise ValueError(f"Gemini devolvió algo que no es un objeto: {type(datos).__name__}")

    guion = " ".join(str(datos.get("guion") or "").split())
    if not guion:
        raise ValueError("Gemini no devolvió guion")

    if len(guion) > config.GUION_MAX_CARACTERES:
        on_log(
            f"[nicho_pov_bof_largo] guion de {len(guion)} caracteres; en {config.CLIPS_POR_VIDEO} "
            f"clips de {config.CLIP_TARGET_S:.0f}s caben ~{config.GUION_MAX_CARACTERES}. "
            "El vídeo se alargará para que quepa la voz entera."
        )

    return {
        "nombre": " ".join(str(datos.get("nombre") or titulo).split()),
        "guion": guion,
        # El subliminal va en DOS líneas; el modelo a veces las manda con
        # `\n` literal escapado y a veces con salto real.
        "subliminal": str(datos.get("subliminal") or "").replace("\\n", "\n").strip(),
    }
