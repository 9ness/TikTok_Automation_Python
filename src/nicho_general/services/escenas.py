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
    '   {{"n": 1, "titulo": "...", "resumen": "...", "prompt_imagen": "...",\n'
    '    "prompt_video": "...",\n'
    '    "guion": "solo lo que se dice en voz alta", "caracteres": 0}},\n'
    "   {{\"n\": 2, ...}}, …\n"
    " ]}}\n"
    "La lista tiene EXACTAMENTE {escenas} escenas, con `n` de 1 a {escenas} y "
    "en orden. Ni una más ni una menos: cada escena es un clip que hay que "
    "generar aparte.\n"
    # El "mensaje subliminal" del curso, que en el POV BOF va quemado en el
    # vídeo. Aquí hacía falta por otra razón: el diagnóstico de la agencia
    # marca como defecto que no haya TEXTO y pide un gancho en el primer
    # segundo que diga de qué producto se habla. Cuatro líneas exactas.
    "Añade además, fuera de las escenas, un campo `bloque_texto` con el "
    "mensaje que se quema en pantalla al principio del anuncio. Son CUATRO "
    "líneas, una por renglón, con esta forma exacta y sin preguntas:\n"
    "Han ajustado el precio de\n"
    "[NOMBRE CORTO DEL PRODUCTO]\n"
    "Revisa también tus cupones de descuento\n"
    "para mejorarlo aún más.\n"
    "Sustituye SOLO la segunda línea por el nombre corto del producto (dos o "
    "tres palabras, con la marca si la tiene). No pongas el nombre de la "
    "tienda, ni precios, ni porcentajes.\n"
    # Sirve para UNA cosa: al volver con las tres imágenes generadas, saber
    # cuál es cuál. Con el escenario y la luz no se distingue nada —son iguales
    # en las tres a propósito—; lo que las separa es qué hace la persona.
    "El campo `resumen` es UNA frase corta en español que diga qué HACE la "
    "persona en esa foto, para reconocerla de un vistazo: «mira el producto "
    "pensativa», «lo sujeta y sonríe a cámara», «señala el carrito». Sin "
    "escenario, sin luz, sin ropa y sin adjetivos de más.\n"
    "El campo `prompt_video` debe llevar dentro el guion hablado y la identidad "
    "vocal completa, palabra por palabra igual en las {escenas} escenas, tal y "
    "como "
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
    "2. EL MISMO ESCENARIO en las {escenas} escenas, descrito con las mismas "
    "palabras: si la primera pasa en el salón, todas pasan en ese salón. "
    "Cambiar de habitación entre clips convierte el anuncio en tres vídeos "
    "sueltos.\n"
    "3. En los prompts de IMAGEN, la persona NO sostiene móviles, tablets ni "
    "nada que no sea el producto. Para la llamada a la acción no hace falta "
    "enseñar una pantalla: eso lo dice la voz. Un móvil en la mano tapa el "
    "producto y encima cambia de una escena a otra.\n"
    # Cada escena se genera por separado, así que sin una referencia de tamaño
    # el generador la decide por su cuenta: la misma plancha salía cubriendo la
    # isla entera en una escena y como una bandeja pequeña en otra. El curso
    # pide que el producto conserve sus "proporciones" y esto es lo que lo hace
    # comprobable.
    "7. Da la ESCALA del producto y repítela igual en las {escenas} escenas: "
    "cuánto mide y qué ocupa respecto a lo que tiene al lado (la encimera, la "
    "placa, las manos de la persona). Las medidas salen de la ficha; si no las "
    "ves, dilo con una comparación («del ancho de dos quemadores», «le cabe en "
    "una mano»). Sin eso, el mismo producto sale gigante en una escena y "
    "diminuto en la siguiente, y se nota al pegar los clips.\n"
    # El fallo más caro de la escena de dolor: el generador no tiene otro
    # objeto al que echarle la culpa, así que ensucia o estropea EL PRODUCTO
    # que se está vendiendo. Con la plancha de parrilla fue literal —"una
    # parrilla sucia" y "la plancha de parrilla" son la misma palabra— y salió
    # el producto lleno de grasa en el anuncio que lo promociona.
    "8. En la escena del PUNTO DE DOLOR, lo que falla NUNCA es el producto. Lo "
    "viejo, sucio, roto o incómodo tiene que ser OTRA cosa concreta y nombrada "
    "(el utensilio de siempre, el electrodoméstico, el mueble, la superficie), "
    "y lo dices explícitamente: «lo sucio es X, nunca el producto». El "
    "producto, si aparece en esa escena, sale impecable y a un lado, separado "
    "de eso que falla. Cuidado cuando el producto y lo que falla se llamen "
    "parecido: ahí hay que repetirlo dos veces.\n"
    # Copiar la identidad vocal palabra por palabra —lo que manda el curso— no
    # basta para el ACENTO: cada clip se sintetiza aparte desde esa descripción
    # y "acento peninsular neutro" es demasiado blando. En la plancha salieron
    # dos clips en peninsular y uno tirando a latino, y eso se nota más que un
    # cambio de mueble. Hace falta la marca fonética y la prohibición expresa.
    "9. En la identidad vocal, CLAVA el acento y prohíbe el otro. El anuncio es "
    "para España: escribe «acento español de España (castellano peninsular), "
    "NUNCA latinoamericano», y dale la marca concreta — distinción, la z y la "
    "c ante e o i suenan como la 'th' inglesa, nada de seseo, entonación y "
    "vocabulario de España. Va dentro de la identidad vocal, así que se copia "
    "igual en las {escenas} escenas.\n"
    # Y lo que de verdad decide el acento no es la descripción de la voz sino
    # las PALABRAS del guion: en la plancha, la única escena que salió en
    # peninsular fue la que decía "y encima" y "es una pelea"; las otras tres
    # eran neutras —una hablaba de "pulgadas"— y salieron en latino, que es lo
    # que el modelo ha oído más.
    "10. Escribe el guion hablado en español DE ESPAÑA, con vocabulario y giros "
    "de aquí («vale», «un montón», «una pasada», «de verdad», «encima»), y "
    "nunca en español neutro internacional. Las medidas, en centímetros y "
    "escritas con letra, jamás en pulgadas. El acento con el que se locuta lo "
    "decide lo que se DICE, no solo la identidad vocal: con un texto neutro "
    "sale acento latino aunque le pidas peninsular.\n"
    # El documento del curso dice "no añadas indicaciones sobre música", y con
    # eso el generador la pone cuando le apetece: unos clips salen con banda
    # sonora y otros no, y al pegarlos la música entra y sale de golpe. Hay que
    # prohibirla explícitamente — no basta con no mencionarla.
    "11. Termina cada `prompt_video` diciendo que el clip NO lleva música de "
    "fondo, ni banda sonora, ni efectos de sonido añadidos: lo único que se "
    "oye es la voz de la persona hablando, con el sonido natural de la escena. "
    "Va en las {escenas}, con las mismas palabras.\n"
    "4. Describe el producto SOLO como se ve en su foto. No le añadas piezas, "
    "luces encendidas, pantallas ni accesorios que no aparezcan en ella, "
    "aunque el título los mencione: la foto es lo que se adjunta al generar, "
    "así que todo lo que no esté ahí se lo inventa el generador y sale "
    "distinto en cada escena. De esas características ya habla la voz.\n"
    # Con guiones largos se le mandan también las capturas de características,
    # y ahí vienen fotos de catálogo del producto en OTROS sitios (una barbacoa
    # en el jardín, un fregadero, una mesa puesta). Sin esta regla las toma por
    # ambientación y escribe un escenario distinto en cada escena — que es
    # justo lo que rompe la ilusión de que el anuncio es un solo vídeo.
    "6. Las fotos que te mando pueden incluir capturas de características "
    "(medidas, materiales, qué trae) y fotos de catálogo del producto en sitios "
    "distintos. Están SOLO para que leas lo que el producto ES y hace. NO son "
    "la ambientación del anuncio: el escenario lo eliges tú, es UNO solo para "
    "las {escenas} escenas, y lo describes con las mismas palabras en todas. "
    "Descríbelo con detalles concretos y repetibles (los muebles, la encimera, "
    "qué se ve al fondo), no como «una cocina moderna y luminosa»: cada escena "
    "se genera por separado y con una frase vaga sale una casa distinta cada "
    "vez. Tampoco describas el peinado ni la ropa — salen de la foto de la "
    "persona.\n"
    "5. La longitud del guion es un TOPE, no una sugerencia: {tope} caracteres "
    "como máximo, contando espacios y signos. El clip dura {segundos} segundos "
    "exactos y lo que no dé tiempo a decir se pierde a media frase. CUENTA "
    "cada guion antes de responder y, si se pasa aunque sea por poco, "
    "reescríbelo más corto — no lo entregues confiando en que quepa."
)


# Cuánto se le perdona a un guion antes de pedirle que lo acorte. Estaba en
# 1,15 y se bajó: con el tope de 170 caracteres de un clip de 10s, ese margen
# daba por buenos guiones de 190 —11,2 segundos de voz en un clip que dura 10—,
# y en la plancha de VEVOR le tocó justo a la escena 3, que es la de la CTA al
# carrito. Un reintento cuesta una llamada de texto; una CTA cortada a media
# frase es el vídeo entero, porque es lo único que la tienda exige.
#
# No se pone en 1,0 porque entonces reintentaría casi siempre: el modelo cuenta
# los caracteres a ojo y se pasa por dos o tres constantemente, y eso sí que
# cabe (170 caracteres son 10s justos, con 178 se va a 10,4 y el final de la
# frase todavía entra en la cola del clip).
MARGEN_TOPE = 1.05


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
    escenas_pedidas: int = 0,
    on_log: OnLog = _noop,
) -> dict:
    """`{voz, escenas: [...N]}` para un producto.

    `escenas_pedidas` son las que hacen falta para la duración que pide la
    tienda (`config.escenas_para`). Sin ella, las tres del curso.

    Si un guion se pasa del tope se pide UNA segunda pasada por longitud (ver
    `MARGEN_TOPE`) y, si a la segunda tampoco entra, se avisa y se usa igual:
    insistir más deja frases telegráficas, que es lo que se aprendió en el POV
    BOF Largo. Aquí sí se reintenta —allí no— porque allí el montaje cuadra el
    vídeo a la voz y un clip de Omni dura lo que dura.
    """
    from src.tiktok_shop.api.gemini import generate_json

    descripcion = f"Producto: {titulo.strip()}."
    if tienda:
        descripcion += f" Tienda: {tienda.strip()}."
    if caption:
        descripcion += f" Descripción: {caption.strip()}"

    meta = config.DURACIONES[config.duracion_valida(duracion)]
    cuantas = max(
        config.ESCENAS,
        min(int(escenas_pedidas or config.ESCENAS), config.ESCENAS_MAX),
    )
    prompt = config.prompt_guion(
        gancho, duracion, plazos=plazos, sexo_personaje=sexo_personaje,
        escenas=cuantas,
    ) + _FORMATO.format(
        tope=meta["caracteres"], segundos=meta["segundos"], escenas=cuantas,
    )
    datos = generate_json(
        prompt, descripcion, images=[str(f) for f in (fotos or [])] or None,
    )
    if not isinstance(datos, dict):
        raise ValueError(
            f"Gemini devolvió algo que no es un objeto: {type(datos).__name__}"
        )

    voz = " ".join(str(datos.get("voz") or "").split())
    bloque = "\n".join(
        l.strip() for l in str(datos.get("bloque_texto") or "").splitlines()
        if l.strip()
    )
    crudas = datos.get("escenas") or []
    if not isinstance(crudas, list):
        raise ValueError("Gemini no devolvió la lista de escenas")

    escenas = []
    for i, e in enumerate(crudas[:cuantas], start=1):
        if not isinstance(e, dict):
            continue
        guion = " ".join(str(e.get("guion") or "").split())
        escenas.append({
            "n": int(e.get("n") or i),
            "titulo": " ".join(str(e.get("titulo") or "").split()),
            "resumen": " ".join(str(e.get("resumen") or "").split()),
            "prompt_imagen": str(e.get("prompt_imagen") or "").strip(),
            "prompt_video": str(e.get("prompt_video") or "").strip(),
            "guion": guion,
            "caracteres": len(guion),
        })

    if len(escenas) != cuantas:
        raise ValueError(
            f"Se esperaban {cuantas} escenas y llegaron {len(escenas)}."
        )
    vacias = [e["n"] for e in escenas if not e["prompt_imagen"] or not e["prompt_video"]]
    if vacias:
        raise ValueError(f"Escenas sin prompt: {vacias}")

    tope = meta["caracteres"]
    largas = [e for e in escenas if e["caracteres"] > tope * MARGEN_TOPE]
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
        largas = [e for e in escenas if e["caracteres"] > tope * MARGEN_TOPE]
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
            f"{cuantas} escenas. Revísalo antes de generar los clips."
        )
    for aviso in _revisar(escenas):
        on_log(f"[nicho_general] {aviso}")
    return {"voz": voz, "escenas": escenas, "bloque_texto": bloque}


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
    # El documento del curso prohíbe las preguntas en el gancho ("No contener
    # preguntas en el gancho inicial") y aun así se cuelan: es la forma más
    # fácil de abrir un anuncio y el modelo tira de ella. La escena 1 con
    # pregunta hay que rehacerla — el gancho es lo único que decide si alguien
    # se queda.
    primera = next((e for e in escenas if e["n"] == 1), None)
    if primera and ("¿" in primera["guion"] or "?" in primera["guion"]):
        avisos.append(
            "la escena 1 abre con una PREGUNTA y el curso lo prohíbe: rehazla."
        )
    inventadas = [e["n"] for e in escenas if _INVENTA_PERSONA.search(e["prompt_imagen"])]
    if inventadas:
        avisos.append(
            f"las escenas {inventadas} describen a la persona en vez de "
            "remitirse a la foto de referencia: puede salir otra cara."
        )
    return avisos
