"""Guion locutado + mensaje subliminal, por producto, con Gemini.

El prompt es del operador y va LITERAL (`prompts/guion.md`): se le pasa tal
cual, sin resumirlo. Resumirlo ya salió mal una vez — la versión condensada
perdía matices y el guion salía sin gracia.

Lo único que se añade al final es el formato de salida (JSON), porque aquí no
hay una persona leyendo la respuesta como en ChatGPT.

**Una segunda pasada por longitud, no un bucle.** Forzar el tope a base de
reintentos deja frases telegráficas ("¿Piel grasa? ¿Residuo blanco?"), así que
durante un tiempo no se recortó nada: total, el montaje cuadra la duración y
pide un clip más. Con los clips de pago eso dejó de ser gratis — medida la
Carpeta_1 del Inventario General, los DIEZ guiones se pasaban (331 a 503
caracteres para un tope de 356) y ninguno cabía en dos clips de 8 s: entre 3 y
4 clips por vídeo, o sea un 50-100 % más de créditos por pasarse de largo.

Así que si se pasa se pide UNA reescritura, enseñándole por cuánto se pasó (a
secas devuelve lo mismo de largo). Si vuelve más largo o vacío, se queda el
primero: un guion bueno y largo sigue valiendo más que uno roto.
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
            f"[{etiqueta}] guion de {len(guion)} caracteres para un tope de "
            f"{tope}: se pide una reescritura más corta."
        )
        try:
            corto = _acortar(
                (prompt or config.prompt_guion(plazos)), descripcion, imagenes,
                guion, tope, on_log,
            )
        except Exception as e:  # noqa: BLE001 — lo de antes vale, aunque largo
            on_log(f"[{etiqueta}] no se pudo acortar: {e}")
            corto = ""
        if corto:
            on_log(f"[{etiqueta}] recortado a {len(corto)} caracteres")
            guion = corto
        elif len(guion) > tope:
            on_log(
                f"[{etiqueta}] sigue en {len(guion)}: se usa igual, pero puede "
                "pedir un clip más."
            )

    return {
        "nombre": " ".join(str(datos.get("nombre") or titulo).split()),
        "guion": guion,
        # El subliminal va en DOS líneas; el modelo a veces las manda con
        # `\n` literal escapado y a veces con salto real.
        "subliminal": str(datos.get("subliminal") or "").replace("\\n", "\n").strip(),
    }


def _acortar(
    prompt: str, descripcion: str, imagenes, guion: str, tope: int,
    on_log: OnLog,
) -> str:
    """Segunda pasada SOLO por longitud. Devuelve "" si no mejora.

    Se le enseña lo que escribió y por cuánto se pasó: pedirlo a secas otra vez
    devuelve un guion igual de largo, porque el modelo no sabe que ya falló.
    """
    from src.tiktok_shop.api.gemini import generate_json

    # Se le pide MENOS de lo que cabe. Medido: pidiéndole 356 devolvió 375 —a
    # cinco caracteres de no caber en dos clips de 8 s—, y esa diferencia
    # cuesta un clip entero. Apuntando un 10% por debajo aterriza dentro.
    pedido = int(tope * 0.9)
    aviso = (
        f"\n\nATENCIÓN: tu guion anterior tenía {len(guion)} caracteres y no "
        f"cabe. Tiene que quedarse en {pedido} caracteres o menos. Este era:"
        f"\n«{guion}»\n\nDevuelve el MISMO JSON, con "
        "el mismo producto y la misma estructura, pero con el guion por debajo "
        f"de esos {pedido} caracteres. No quites la llamada a la acción del "
        "final: di lo mismo con menos palabras.\n"
        # Lo que salió mal la primera vez: recortando por el medio dejó «lo
        # bueno que tiene esta bicicleta es que con portaequipajes y
        # conectividad app» — sin verbo. Lo va a LEER una voz en alto, así que
        # una frase rota se oye.
        "IMPORTANTE: el guion lo lee una voz en alto, así que todas las frases "
        "tienen que estar completas y bien construidas, con su verbo. Si no "
        "cabe todo, QUITA características enteras —una o dos— en vez de "
        "recortar por el medio: mejor decir menos cosas y decirlas bien que "
        "nombrarlas todas a trozos."
    )
    datos = generate_json(prompt + _FORMATO + aviso, descripcion, images=imagenes)
    if not isinstance(datos, dict):
        return ""
    nuevo = " ".join(str(datos.get("guion") or "").split())
    # Solo se acepta lo que de verdad sea más corto.
    return nuevo if nuevo and len(nuevo) < len(guion) else ""
