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

import re
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
    '{{"voz": "la identidad vocal completa, tal y como la pide el documento",\n'
    ' "escenas": [\n'
    '   {{"n": 1, "titulo": "...", "prompt_imagen": "...", "prompt_video": "...",\n'
    '    "guion": "solo lo que se dice en voz alta", "caracteres": 0}},\n'
    "   {{\"n\": 2, ...}}, {{\"n\": 3, ...}}\n"
    " ]}}\n"
    "El campo `prompt_video` debe llevar dentro el guion hablado y la identidad "
    "vocal completa, palabra por palabra igual en las tres escenas, tal y como "
    "exige el documento. `guion` es ese mismo texto hablado repetido aparte "
    "para poder contarlo, y `caracteres` su longitud.\n"
    # Dos cosas que el documento pide pero que se le olvidan en cuanto se
    # pone a escribir, y las dos rompen la ilusión de que es un solo vídeo:
    "\nDOS REGLAS QUE NO PUEDES SALTARTE:\n"
    "1. NO describas a la persona. Ni su edad, ni su sexo, ni su papel (nada "
    "de «una joven madre de 28-35 años» ni «un chico deportista»): la persona "
    "ya existe y va adjunta como imagen. Refiérete a ella SIEMPRE y solo como "
    "«la persona de la imagen de referencia». Cualquier descripción que añadas "
    "pelea con la foto real y sale otra persona.\n"
    "2. EL MISMO ESCENARIO en las tres escenas, descrito con las mismas "
    "palabras: si la primera pasa en el salón, las tres pasan en ese salón. "
    "Cambiar de habitación entre clips convierte el anuncio en tres vídeos "
    "sueltos.\n"
    "3. En los prompts de IMAGEN, la persona NO sostiene móviles, tablets ni "
    "nada que no sea el producto. Para la llamada a la acción no hace falta "
    "enseñar una pantalla: eso lo dice la voz. Un móvil en la mano tapa el "
    "producto y encima cambia de una escena a otra.\n"
    "4. Si el producto tiene luces, pantallas o partes que se encienden, di en "
    "las TRES escenas si están encendidas y de qué color, con las mismas "
    "palabras. Decir solo «la luz es visible» hace que cada generación se la "
    "invente y el producto cambie entre clips.\n"
    "5. La longitud del guion es un TOPE, no una sugerencia: {tope} caracteres "
    "como máximo, contando espacios y signos. El clip dura {segundos} segundos "
    "exactos y lo que no dé tiempo a decir se pierde a media frase. CUENTA "
    "cada guion antes de responder y, si se pasa aunque sea por poco, "
    "reescríbelo más corto — no lo entregues confiando en que quepa."
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

    meta = config.DURACIONES[config.duracion_valida(duracion)]
    prompt = config.prompt_guion(
        gancho, duracion, plazos=plazos, sexo_personaje=sexo_personaje,
    ) + _FORMATO.format(tope=meta["caracteres"], segundos=meta["segundos"])
    datos = generate_json(
        prompt, descripcion, images=[str(f) for f in (fotos or [])] or None,
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

    tope = meta["caracteres"]
    largas = [e for e in escenas if e["caracteres"] > tope * 1.15]
    if largas:
        # AQUÍ SÍ se reintenta, al revés que en el POV BOF Largo: allí el
        # montaje cuadra el vídeo a la voz, pero un clip de Omni dura lo que
        # dura y la frase que no quepa se corta por la mitad. Una sola vez —si
        # a la segunda tampoco entra, se avisa y se usa igual.
        on_log(
            f"[nicho_general] guiones largos para {meta['segundos']}s "
            f"(tope {tope}): "
            + ", ".join(f'{e["n"]}={e["caracteres"]}' for e in largas)
            + ". Pidiendo que los acorte…"
        )
        try:
            escenas = _acortar(
                prompt, descripcion, fotos, escenas, tope, on_log,
            )
        except Exception as e:  # noqa: BLE001 — lo de antes vale, aunque largo
            on_log(f"[nicho_general] no se pudieron acortar: {e}")
        largas = [e for e in escenas if e["caracteres"] > tope * 1.15]
        if largas:
            on_log(
                "[nicho_general] siguen largos: "
                + ", ".join(f'{e["n"]}={e["caracteres"]}' for e in largas)
                + ". Se usan igual, pero revisa que la voz no se corte."
            )
    # La voz suelta y la de dentro tienen que ser la misma: si el modelo se
    # inventa una distinta por escena, los tres clips suenan a tres personas.
    if voz and any(voz[:40] not in e["prompt_video"] for e in escenas):
        on_log(
            "[nicho_general] ojo: la identidad vocal no aparece igual en las "
            "tres escenas. Revísalo antes de generar los clips."
        )
    for aviso in _revisar(escenas):
        on_log(f"[nicho_general] {aviso}")
    return {"voz": voz, "escenas": escenas}


# Palabras con las que se pone a describir a la persona en vez de remitirse a
# la foto ("una joven madre de 30 años…"). Con el personaje adjunto, esa
# descripción pelea con la imagen real y sale otra persona.
_INVENTA_PERSONA = re.compile(
    r"\b(un|una)\s+(joven|chico|chica|hombre|mujer|madre|padre|se[ñn]or\w*|"
    r"muchach\w+|adolescente)\b|\b\d{2}\s*[-–]\s*\d{2}\s*a[ñn]os\b",
    re.IGNORECASE,
)


def _acortar(
    prompt: str, descripcion: str, fotos, escenas: list[dict], tope: int,
    on_log: OnLog,
) -> list[dict]:
    """Segunda pasada SOLO por longitud, enseñándole lo que se pasó.

    Se le manda lo que escribió y por cuánto se pasó cada guion: pedirlo a
    secas otra vez devolvía guiones igual de largos, porque el modelo no sabe
    que ya falló.
    """
    from src.tiktok_shop.api.gemini import generate_json

    cuentas = "; ".join(
        f'escena {e["n"]}: {e["caracteres"]} caracteres' for e in escenas
    )
    aviso = (
        f"\n\nATENCIÓN: en tu respuesta anterior los guiones se pasaron del "
        f"tope de {tope} caracteres ({cuentas}). Devuelve el MISMO JSON con "
        "las mismas escenas, el mismo escenario y la misma identidad vocal, "
        "pero con cada guion reescrito por debajo del tope. No quites la CTA "
        "ni cambies de qué va cada escena: di lo mismo con menos palabras."
    )
    datos = generate_json(
        prompt + aviso, descripcion,
        images=[str(f) for f in (fotos or [])] or None,
    )
    nuevas = (datos or {}).get("escenas") if isinstance(datos, dict) else None
    if not isinstance(nuevas, list) or len(nuevas) != len(escenas):
        on_log("[nicho_general] el recorte no devolvió las mismas escenas; se deja lo anterior")
        return escenas

    salida = []
    for viejo, nuevo in zip(escenas, nuevas):
        if not isinstance(nuevo, dict):
            salida.append(viejo)
            continue
        guion = " ".join(str(nuevo.get("guion") or "").split())
        # Solo se acepta lo que de verdad sea más corto: si el modelo devuelve
        # otra cosa más larga, nos quedamos con lo que ya teníamos.
        if not guion or len(guion) >= viejo["caracteres"]:
            salida.append(viejo)
            continue
        salida.append({
            **viejo,
            "prompt_video": str(nuevo.get("prompt_video") or viejo["prompt_video"]).strip(),
            "guion": guion,
            "caracteres": len(guion),
        })
    return salida


def _revisar(escenas: list[dict]) -> list[str]:
    """Avisos de lo que rompe la continuidad, sin bloquear nada.

    No se reintenta: un anuncio con un aviso se puede usar igual —y el
    operador lo ve al leer el prompt—, mientras que reintentar cuesta otra
    llamada y tampoco garantiza que salga mejor.
    """
    avisos = []
    inventadas = [e["n"] for e in escenas if _INVENTA_PERSONA.search(e["prompt_imagen"])]
    if inventadas:
        avisos.append(
            f"las escenas {inventadas} describen a la persona en vez de "
            "remitirse a la foto de referencia: puede salir otra cara."
        )
    return avisos
