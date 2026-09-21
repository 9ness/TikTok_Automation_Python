"""El guion de UNA prenda, escrito por Gemini con el prompt del curso.

El curso lo hace a mano: se copia su "pront base" en ChatGPT, se le adjunta la
foto de la ficha y él devuelve el texto ya con los datos de ESE producto, que
es lo que se pega en Flow. Eso son dos pegadas y una espera por prenda, y con
diez por carpeta es la mitad del trabajo del nicho.

Aquí se hace lo mismo pero desde el botón: se le manda a Gemini el MISMO
prompt suyo (literal, con su sexo, su duración y su frase de plazos ya
puestas) más los textos y las fotos de la prenda, y se guarda lo que devuelve.

Qué se le pide, y por qué en dos piezas:
- `dice`: SOLO lo que se oye. Es lo único que tiene tope de caracteres, porque
  es lo que tiene que caber en los 10 (u 8) segundos del clip.
- `video`: el bloque entero listo para pegar en Flow —lo que dice, la voz y el
  movimiento—. Se guarda ya montado para que en la tarjeta haya UN botón y no
  haya que recomponer nada al copiar.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

OnLog = Callable[[str], None]
_noop: OnLog = lambda _m: None

# Dónde empieza lo que se pega en el generador: la línea del diálogo. Todo lo
# de antes son instrucciones PARA ChatGPT ("no me devuelvas nada", el tope de
# caracteres…) y en Flow no pintan nada — peor: las obedece.
_LINEA_DICE = re.compile(
    r"^(?P<quien>[^\n]*?dice en español)[^\n]*:\s*$", re.MULTILINE,
)
# El ejemplo del curso va entre comillas angulares, pero la MITAD de sus
# prompts lo cierran con la de abrir (`«…«`, ver el del espejo de mujer y el
# de calle dividido). Exigiendo `»` no casaba y el bloque de vídeo salía con
# el ejemplo de los jeans dentro — con el nombre de OTRO producto.
_EJEMPLO = re.compile(r"«[^«»]*[«»]")


# Dónde partir el guion cuando el formato se graba en dos clips: en un punto,
# y si no lo hay, en una coma. Cortar por la palabra de en medio deja media
# frase en cada mitad y el generador la dice a trozos.
_CORTES = (". ", "! ", "? ", "; ", ", ")


def partir(dice: str, partes: int = 2) -> list[str]:
    """Reparte lo que se dice entre los clips, lo más a la mitad posible."""
    dice = " ".join((dice or "").split())
    if partes < 2 or not dice:
        return [dice]
    trozos, resto = [], dice
    for restantes in range(partes - 1, 0, -1):
        objetivo = len(resto) / (restantes + 1)
        corte = min(
            (
                (abs(pos + len(sep) - objetivo), pos + len(sep))
                for sep in _CORTES
                for pos in _buscar_todas(resto, sep)
            ),
            default=(0, 0),
        )[1]
        # Sin puntuación a mano se parte por el espacio más cercano al medio.
        if not corte:
            corte = _espacio_cercano(resto, objetivo)
        trozos.append(resto[:corte].strip())
        resto = resto[corte:].strip()
    trozos.append(resto)
    return [t for t in trozos if t] or [dice]


def _buscar_todas(texto: str, sep: str) -> list[int]:
    salida, i = [], texto.find(sep)
    while i != -1:
        salida.append(i)
        i = texto.find(sep, i + 1)
    return salida


def _espacio_cercano(texto: str, objetivo: float) -> int:
    espacios = _buscar_todas(texto, " ")
    if not espacios:
        return len(texto)
    return min(espacios, key=lambda p: abs(p - objetivo)) + 1


def _montar_video(prompt: str, dice: str) -> str:
    """El bloque para el generador: el prompt del curso con OTRO diálogo.

    Se compone aquí y no se le pide a la IA porque lo único que puede cambiar
    es la frase: el movimiento y la voz son del curso, palabra por palabra, y
    cada vez que un modelo los "reescribe" salen matices que nadie pidió.
    """
    m = _LINEA_DICE.search(prompt)
    if not m:
        return ""
    cuerpo = prompt[m.start():]
    # Fuera el tope de caracteres y los avisos nuestros: son para quien
    # escribe el guion, no para quien genera el vídeo.
    cuerpo = cuerpo.replace(m.group(0), m.group("quien") + ":", 1)
    for corte in ("\n\nOJO:", "\n\nATENCIÓN:"):
        if corte in cuerpo:
            cuerpo = cuerpo.split(corte)[0]
    return _EJEMPLO.sub(lambda _m: f"«{dice}»", cuerpo, count=1).strip()


# Se le pide SOLO la frase. Pedirle además el bloque entero "tal y como está
# arriba" hacía que Gemini cortara la respuesta por RECITATION (finish_reason
# 8): copiar literalmente un texto que se le acaba de dar es justo lo que ese
# filtro corta. El bloque lo monta `_montar_video`, que además garantiza que el
# movimiento sale palabra por palabra como lo publicó el curso.
_FORMATO = (
    "\n\nDevuelve SOLO un JSON, sin nada más y sin ```:\n"
    '{"dice": "solo la frase que dice la persona, sin comillas"}\n'
    "No copies el resto del prompt: solo esa frase."
)


def escribir(
    *,
    prompt: str,
    titulo: str,
    tienda: str = "",
    caption: str = "",
    precio: str = "",
    fotos: list[Path] | None = None,
    max_caracteres: int = 180,
    # En cuántos clips se graba el formato. Con dos, lo que se dice se reparte
    # a la mitad y sale un bloque de vídeo por clip: cada uno lleva SU trozo,
    # porque el generador dice todo lo que le pongas y en 8 segundos no cabe
    # el guion entero.
    partes: int = 1,
    on_log: OnLog = _noop,
) -> dict:
    """`{dice, video, videos}` para una prenda. Lanza si Gemini no lo escribe."""
    from src.tiktok_shop.api.gemini import generate_json

    descripcion = f"Producto: {titulo.strip()}."
    if precio:
        # El precio se manda como CONTEXTO (si es caro o barato cambia el tono),
        # pero el guion no lo dice: ver `_FORMATO`.
        descripcion += (
            f" Precio hoy, solo para que sepas de qué gama es: "
            f"{precio.replace('.', ',')} € — NO lo digas en el guion."
        )
    if tienda:
        descripcion += f" Tienda: {tienda.strip()}."
    if caption:
        descripcion += f" Descripción: {caption.strip()}"

    imagenes = [str(f) for f in (fotos or [])] or None
    datos = generate_json(prompt + _FORMATO, descripcion, images=imagenes)
    if not isinstance(datos, dict):
        raise ValueError(
            f"Gemini devolvió algo que no es un objeto: {type(datos).__name__}"
        )

    dice = " ".join(str(datos.get("dice") or "").split())
    if not dice:
        raise ValueError("Gemini no devolvió la frase que se dice")

    if len(dice) > max_caracteres:
        # Una reescritura, no un bucle: insistir deja frases telegráficas (el
        # mismo aprendizaje que en el POV BOF Largo). Si vuelve más larga, se
        # queda la primera y se avisa — el clip la cortará por el final.
        on_log(
            f"[nicho_ropa] la frase tiene {len(dice)} caracteres para un tope "
            f"de {max_caracteres}: se pide una reescritura."
        )
        try:
            corta = _acortar(prompt, descripcion, imagenes, dice, max_caracteres)
        except Exception as e:  # noqa: BLE001 — vale la larga antes que nada
            on_log(f"[nicho_ropa] no se pudo acortar: {e}")
            corta = {}
        if corta.get("dice"):
            on_log(f"[nicho_ropa] recortada a {len(corta['dice'])} caracteres")
            dice = corta["dice"]
        else:
            on_log("[nicho_ropa] se queda la larga: el clip la cortará al final")

    # El bloque se monta aquí con el texto del curso: la IA solo pone la frase.
    trozos = partir(dice, partes) if partes > 1 else [dice]
    videos = [_montar_video(prompt, t) or t for t in trozos]
    return {"dice": dice, "video": videos[0], "videos": videos}


def _acortar(
    prompt: str, descripcion: str, imagenes, dice: str, tope: int,
) -> dict:
    """Segunda pasada SOLO por longitud. `{}` si no sale más corta."""
    from src.tiktok_shop.api.gemini import generate_json

    # Se le pide por debajo del tope: pidiendo justo el tope aterriza encima.
    pedido = int(tope * 0.9)
    aviso = (
        f"\n\nATENCIÓN: tu frase anterior tenía {len(dice)} caracteres y no "
        f"cabe en el clip. Tiene que quedarse en {pedido} o menos. Era:\n"
        f"«{dice}»\n\nDevuelve el MISMO JSON con la misma estructura, pero "
        "diciendo lo mismo con menos palabras. NO quites la llamada a la "
        "acción del final: quita una característica entera antes que recortar "
        "por el medio — lo lee una voz en alto y una frase a trozos se oye."
    )
    datos = generate_json(prompt + _FORMATO + aviso, descripcion, images=imagenes)
    if not isinstance(datos, dict):
        return {}
    nueva = " ".join(str(datos.get("dice") or "").split())
    if not nueva or len(nueva) >= len(dice):
        return {}
    return {"dice": nueva}
