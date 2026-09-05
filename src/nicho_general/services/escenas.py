"""Las tres escenas del anuncio UGC, por producto, con Gemini.

El prompt es del curso y va LITERAL (`prompts/guion_{dolor,general}.md`): se le
pasa entero, sin resumirlo. Lo único que se le añade es el formato de salida en
JSON, porque su "FORMATO DE ENTREGA" está escrito para que lo lea una persona
en un chat y aquí lo lee un parser — una tilde de más en "ESCENA 2 — PRODUCTO Y
BENEFICIOS" y nos quedamos sin escena.

Se le manda la foto de la FICHA (la que tiene la descripción), no la limpia:
las características que menciona la escena 2 salen de ahí, y el propio prompt
prohíbe inventarse lo que no se vea.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from src.nicho_general import config

OnLog = Callable[[str], None]
_noop: OnLog = lambda _m: None

# Su formato de entrega, pedido como JSON. Se insiste en la voz porque es lo
# que hace que los tres clips suenen al mismo vídeo: el documento manda
# copiarla palabra por palabra dentro de cada prompt de vídeo, así que va
# DENTRO de cada uno y además suelta, para poder comprobarlo en la pantalla.
_FORMATO = (
    "\n\nDevuelve SOLO un JSON, sin texto alrededor, con esta forma exacta:\n"
    '{"voz": "la identidad vocal completa, tal y como la pide el documento",\n'
    ' "escenas": [\n'
    '   {"n": 1, "titulo": "...", "prompt_imagen": "...", "prompt_video": "...",\n'
    '    "guion": "solo lo que se dice en voz alta", "caracteres": 0},\n'
    "   {\"n\": 2, ...}, {\"n\": 3, ...}\n"
    " ]}\n"
    "El campo `prompt_video` debe llevar dentro el guion hablado y la identidad "
    "vocal completa, palabra por palabra igual en las tres escenas, tal y como "
    "exige el documento. `guion` es ese mismo texto hablado repetido aparte "
    "para poder contarlo, y `caracteres` su longitud."
)


def escribir(
    *,
    titulo: str,
    tienda: str = "",
    caption: str = "",
    fotos: list[Path] | None = None,
    gancho: str = config.GANCHO_DEFECTO,
    duracion: str = config.DURACION_DEFECTO,
    plazos: bool = False,
    sexo_personaje: str = "",
    on_log: OnLog = _noop,
) -> dict:
    """`{voz, escenas: [...3]}` para un producto.

    No hay reintento por longitud: el documento pide ~170 caracteres (136 en la
    versión de 8 s) y sus propios ejemplos se quedan en 162. Si un guion se
    pasa solo se AVISA — forzarlo con reintentos deja frases telegráficas, que
    es justo lo que aprendimos en el POV BOF Largo.
    """
    from src.tiktok_shop.api.gemini import generate_json

    descripcion = f"Producto: {titulo.strip()}."
    if tienda:
        descripcion += f" Tienda: {tienda.strip()}."
    if caption:
        descripcion += f" Descripción: {caption.strip()}"

    prompt = config.prompt_guion(
        gancho, duracion, plazos=plazos, sexo_personaje=sexo_personaje,
    )
    datos = generate_json(
        prompt + _FORMATO,
        descripcion,
        images=[str(f) for f in (fotos or [])] or None,
    )
    if not isinstance(datos, dict):
        raise ValueError(
            f"Gemini devolvió algo que no es un objeto: {type(datos).__name__}"
        )

    voz = " ".join(str(datos.get("voz") or "").split())
    crudas = datos.get("escenas") or []
    if not isinstance(crudas, list):
        raise ValueError("Gemini no devolvió la lista de escenas")

    escenas = []
    for i, e in enumerate(crudas[: config.ESCENAS], start=1):
        if not isinstance(e, dict):
            continue
        guion = " ".join(str(e.get("guion") or "").split())
        escenas.append({
            "n": int(e.get("n") or i),
            "titulo": " ".join(str(e.get("titulo") or "").split()),
            "prompt_imagen": str(e.get("prompt_imagen") or "").strip(),
            "prompt_video": str(e.get("prompt_video") or "").strip(),
            "guion": guion,
            "caracteres": len(guion),
        })

    if len(escenas) != config.ESCENAS:
        raise ValueError(
            f"Se esperaban {config.ESCENAS} escenas y llegaron {len(escenas)}."
        )
    vacias = [e["n"] for e in escenas if not e["prompt_imagen"] or not e["prompt_video"]]
    if vacias:
        raise ValueError(f"Escenas sin prompt: {vacias}")

    tope = config.DURACIONES[config.duracion_valida(duracion)]["caracteres"]
    largas = [f'{e["n"]} ({e["caracteres"]})' for e in escenas if e["caracteres"] > tope * 1.15]
    if largas:
        on_log(
            f"[nicho_general] guiones más largos de lo que cabe en "
            f"{config.DURACIONES[config.duracion_valida(duracion)]['segundos']}s "
            f"(~{tope} car): {', '.join(largas)}. No se recortan; si al montar "
            "sobra voz, se rehacen."
        )
    # La voz suelta y la de dentro tienen que ser la misma: si el modelo se
    # inventa una distinta por escena, los tres clips suenan a tres personas.
    if voz and any(voz[:40] not in e["prompt_video"] for e in escenas):
        on_log(
            "[nicho_general] ojo: la identidad vocal no aparece igual en las "
            "tres escenas. Revísalo antes de generar los clips."
        )
    return {"voz": voz, "escenas": escenas}
