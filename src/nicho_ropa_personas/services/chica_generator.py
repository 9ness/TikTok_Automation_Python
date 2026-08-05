"""Convierte la foto de una chica en la ficha JSON del curso.

Lo que hace el operador a mano en el chat de Gemini —"te paso un prompt,
devuélvemelo con la chica de la imagen"— pero guardado y reutilizable.

Por qué importa que sea una foto suya y no la modelo de la plantilla: la ficha
del curso la tiene todo el mundo, así que si nadie la cambia todas las cuentas
publican con la misma cara. Se busca una foto por internet, se genera la ficha
con esa chica y esa modelo pasa a ser de la casa.

Lo ÚNICO que cambia es cómo es ella. El decorado, la luz, la pose, el móvil y
el bloque `clothing` —el que obliga a llevar la ropa de la imagen de
referencia— se quedan intactos: son lo que hace que la prenda salga bien
puesta, y si el modelo se pone creativo ahí el vídeo deja de servir.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from src.nicho_ropa_personas import config
from src.tiktok_shop.api.gemini import generate_json

OnLog = Callable[[str], None]
_noop: OnLog = lambda _msg: None

# Bloques que se restauran de la plantilla pase lo que pase. Aunque el prompt
# ya lo pide, un modelo se despista y reescribe el decorado o —peor— relaja el
# bloque de la ropa, y entonces la prenda sale "inspirada en" la de la foto en
# vez de calcada.
BLOQUES_INTOCABLES = (
    "clothing", "device", "pose", "photography",
    "background", "lighting", "atmosphere", "accessories",
)


def crear_desde_foto(foto: Path | bytes, *, on_log: OnLog = _noop) -> dict:
    """Ficha JSON de la plantilla del curso con la chica de la foto."""
    plantilla = config.plantilla_chica()
    system_prompt = config.prompt_crear_chica()
    user_prompt = (
        "Plantilla JSON a modificar:\n"
        f"{json.dumps(plantilla, ensure_ascii=False, indent=2)}\n\n"
        "La imagen adjunta es la chica que tiene que aparecer. Devuelve la "
        "plantilla con ella dentro."
    )

    on_log("[chica] pidiendo la ficha a Gemini…")
    imagen = foto if isinstance(foto, bytes) else str(foto)
    raw = generate_json(system_prompt, user_prompt, images=[imagen], temperature=0.4)
    if not isinstance(raw, dict):
        raise ValueError("Gemini devolvió algo que no es una ficha.")

    # Se le pregunta EXPLÍCITAMENTE si ve a alguien en vez de deducirlo
    # comparando la respuesta con la plantilla: comparar textos era frágil (el
    # modelo varía una coma entre llamadas y el aviso dejaba de saltar).
    if raw.get("hay_chica") is False:
        raise ValueError(
            "En esa foto no se ve ninguna chica: te habría devuelto la modelo "
            "de ejemplo del curso, que es la que tiene todo el mundo. Sube una "
            "foto donde se le vea la cara."
        )
    ficha = raw.get("ficha") if isinstance(raw.get("ficha"), dict) else raw
    if "subject" not in ficha:
        raise ValueError(
            "Gemini no devolvió una ficha válida (falta el bloque 'subject'). "
            "Prueba con otra foto donde se vea bien la cara."
        )

    # Segunda red, por si contesta `hay_chica: true` y aun así copia la
    # plantilla: es lo peor que puede pasar aquí, quedarte con la rubia del
    # curso —la cara que tiene todo el mundo— creyendo que es tuya.
    if _mismo_subject(ficha.get("subject"), plantilla.get("subject")):
        raise ValueError(
            "En esa foto no se ve ninguna chica: te habría devuelto la modelo "
            "de ejemplo del curso, que es la que tiene todo el mundo. Sube una "
            "foto donde se le vea la cara."
        )

    for bloque in BLOQUES_INTOCABLES:
        if bloque in plantilla:
            ficha[bloque] = plantilla[bloque]

    # `face` sí puede cambiar (tono de piel, maquillaje), pero si el modelo lo
    # borra se recupera: sin él la imagen sale con la piel plastificada.
    if "face" not in ficha and "face" in plantilla:
        ficha["face"] = plantilla["face"]

    on_log("[chica] ficha lista")
    return ficha


def _mismo_subject(a: object, b: object) -> bool:
    """¿El `subject` devuelto es el de la plantilla, sin tocar?

    Se comparan los campos que describen a la persona, no el bloque entero:
    la `description` incluye el decorado (espejo, dormitorio) y esa parte SÍ
    debe repetirse, así que compararla al completo no distinguiría nada.
    """
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    campos = ("age", "expression", "hair_color", "style")
    return all(
        str(a.get(c, "")).strip().lower() == str(b.get(c, "")).strip().lower()
        for c in campos
    )
