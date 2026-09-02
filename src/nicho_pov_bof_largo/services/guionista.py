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
    fotos: list[Path] | None = None,
    plazos: bool = False,
    prompt: str = "",
    max_caracteres: int = 0,
    etiqueta: str = "nicho_pov_bof_largo",
    on_log: OnLog = _noop,
) -> dict:
    """`{nombre, guion, subliminal}` para un producto.

    `plazos` mete en el prompt la frase de financiación (productos por encima
    del umbral de precio). Es lo ÚNICO que cambia: misma estructura, mismo
    formato de salida.

    `foto` es la foto limpia. El prompt insiste en NO mandar la foto sola, así
    que siempre va acompañada de la descripción; si no hay foto se manda solo
    el texto (Gemini se apaña, pero el guion sale más genérico).

    `fotos` son TODAS las del producto (limpia, ficha y las capturas de
    características que haya subido el operador). Hacen falta para los guiones
    largos: con el título solo no hay de qué hablar treinta segundos, y lo que
    llena ese hueco son las capturas de la ficha — material, medidas, usos.

    `prompt` y `max_caracteres` los usa el POV BOF (el corto), que pide el
    mismo JSON pero con otra estructura y 190 caracteres en vez de ~356. Se
    parametriza aquí en vez de duplicar la función: lo único distinto es el
    texto que se manda y con qué se compara el largo.
    """
    from src.tiktok_shop.api.gemini import generate_json

    descripcion = f"Producto: {titulo.strip()}."
    if tienda:
        descripcion += f" Tienda: {tienda.strip()}."
    if caption:
        descripcion += f" Descripción: {caption.strip()}"

    imagenes = [str(f) for f in (fotos or ([foto] if foto else []))] or None
    if plazos:
        on_log("[nicho_pov_bof_largo] guion con la frase de plazos (producto caro)")
    datos = generate_json(
        (prompt or config.prompt_guion(plazos)) + _FORMATO,
        descripcion,
        images=imagenes,
    )
    if not isinstance(datos, dict):
        raise ValueError(f"Gemini devolvió algo que no es un objeto: {type(datos).__name__}")

    guion = " ".join(str(datos.get("guion") or "").split())
    if not guion:
        raise ValueError("Gemini no devolvió guion")

    tope = max_caracteres or config.GUION_MAX_CARACTERES
    if len(guion) > tope:
        on_log(
            f"[{etiqueta}] guion de {len(guion)} caracteres; el objetivo eran "
            f"~{tope}. No se recorta (ver la nota de arriba): el montaje cuadra "
            "la duración y puede pedir un clip más."
        )

    return {
        "nombre": " ".join(str(datos.get("nombre") or titulo).split()),
        "guion": guion,
        # El subliminal va en DOS líneas; el modelo a veces las manda con
        # `\n` literal escapado y a veces con salto real.
        "subliminal": str(datos.get("subliminal") or "").replace("\\n", "\n").strip(),
    }
