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

# Lo que el prompt del curso pide AÑADIR al final de la respuesta: el nombre
# del producto con el aviso de no pegarlo en el generador. Es una nota para el
# operador, no algo que diga la chica — pero viene dentro de `dice` y, tal
# cual, el vídeo lo LEE en alto ("...Nombre de producto (No añadir a orden de
# video en grok ni onmi) Lumiira pantalón...").
_COLETILLAS = ("nombre de producto", "(no añadir", "no añadir a orden")


def _limpiar_dice(dice: str) -> str:
    """Deja solo lo que se dice: sin comillas y sin la nota del final."""
    texto = " ".join((dice or "").split())
    plano = _sin_acentos(texto)
    corte = min(
        (plano.find(c) for c in _COLETILLAS if plano.find(c) != -1),
        default=-1,
    )
    if corte > 0:
        texto = texto[:corte]
    return texto.strip().strip("«»\"'' ").strip()


def _sin_acentos(txt: str) -> str:
    import unicodedata

    plano = unicodedata.normalize("NFKD", txt or "")
    return "".join(c for c in plano if not unicodedata.combining(c)).lower()


def recortar(dice: str, tope: int) -> str:
    """Corta por la última frase que quepa. Nunca a mitad de palabra.

    Se usa cuando la reescritura sigue saliéndose: aquí la voz la pone el
    generador, así que lo que no cabe en el clip no se oye a medias — se corta
    en seco donde toque, y mejor que sea en un punto.
    """
    dice = dice.strip()
    if len(dice) <= tope:
        return dice
    # Se mira también el final exacto: una frase que acaba justo en el tope
    # cabe entera.
    recorte = dice[: tope + 1]
    mejor = max(recorte.rfind(sep) for sep in (".", "!", "?", ";"))
    if mejor > tope * 0.5:
        return recorte[: mejor + 1].strip()
    # Sin punto a mano, por una coma, cerrando ahí la frase.
    coma = recorte.rfind(", ")
    if coma > tope * 0.6:
        return recorte[:coma].strip() + "."
    # Y si tampoco, NO se corta: media frase en el vídeo ("…mangas murciélago
    # tan.") es peor que un clip justo. Se devuelve tal cual y quien llama avisa.
    return dice


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


def _montar_video(prompt: str, dice: str, parte: int = 0) -> str:
    """El bloque para el generador: el prompt del curso con OTRO diálogo.

    Se compone aquí y no se le pide a la IA porque lo único que puede cambiar
    es la frase: el movimiento y la voz son del curso, palabra por palabra, y
    cada vez que un modelo los "reescribe" salen matices que nadie pidió.

    `parte` (1, 2…) es para los formatos partidos cuyo prompt trae UN
    movimiento por clip (`Movimiento clip 1:` / `Movimiento clip 2:`, como el
    de la tienda: de frente y luego de espaldas). Se deja solo el suyo; en los
    prompts con un único "Movimiento:" no cambia nada.
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
    if parte:
        cuerpo = solo_parte(cuerpo, parte)
    return _EJEMPLO.sub(lambda _m: f"«{dice}»", cuerpo, count=1).strip()


# Cabecera de cada bloque de movimiento por clip.
_MOVIMIENTO_CLIP = re.compile(r"^Movimiento clip (\d+):[ \t]*$", re.MULTILINE)


def solo_parte(cuerpo: str, parte: int) -> str:
    """Deja el bloque `Movimiento clip <parte>:` como "Movimiento:" y quita
    los de las demás partes. Si el texto no va por clips, sale tal cual."""
    marcas = list(_MOVIMIENTO_CLIP.finditer(cuerpo))
    if not marcas:
        return cuerpo
    comun = cuerpo[: marcas[0].start()].rstrip()
    for i, m in enumerate(marcas):
        fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(cuerpo)
        if int(m.group(1)) == int(parte):
            bloque = cuerpo[m.end():fin].strip()
            return f"{comun}\n\nMovimiento:\n\n{bloque}"
    # Sin bloque para esa parte: se queda el primero, mejor que ninguno.
    m = marcas[0]
    fin = marcas[1].start() if len(marcas) > 1 else len(cuerpo)
    return f"{comun}\n\nMovimiento:\n\n{cuerpo[m.end():fin].strip()}"


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


# Con el formato partido se piden los textos YA separados, uno por clip, como
# las escenas del Nicho General. Escribir uno largo y partirlo después dejaba
# mitades desiguales y frases cortadas por el medio: el clip 2 empezaba con
# "y además…" y uno de los dos se pasaba de lo que cabe en 8 segundos.
def _formato_clips(
    partes: int, tope: int, segundos: int, colores: bool = False,
) -> str:
    ejemplo = ", ".join(f'"lo que dice en el clip {i}"' for i in range(1, partes + 1))
    # Con `colores` (formato de la tienda) se pide ADEMÁS la lista de colores
    # que nombra, en el orden en que los dice y con el puesto el último: es lo
    # que usa el montaje para recolorear el primer fotograma en cada corte.
    donde = "en la misma tienda" if colores else "en dos sitios distintos"
    json_ejemplo = (
        '{"colores": ["rosa", "beige", "negro", "verde"], "color_puesto": "verde", '
        '"colores_hex": {"rosa": "#rrggbb", "beige": "#rrggbb", "negro": "#rrggbb", "verde": "#rrggbb"}, '
        f'"clips": [{ejemplo}]}}'
        if colores else f'{{"clips": [{ejemplo}]}}'
    )
    extra = (
        '\n"colores" son los colores que nombra al empezar el clip 1, en '
        "español, en el MISMO orden en que los dice y con el de la prenda de "
        "la foto el ÚLTIMO. Cada uno con el NOMBRE EXACTO de la variante en "
        "el selector de color de la captura de TikTok Shop (en minúsculas), "
        "sin los tachados o agotados; si la captura no enseña el selector, "
        "solo el color de la prenda de la foto. Nunca inventes un color: si "
        "solo hay uno, la lista lleva solo ese y el clip 1 no los nombra.\n"
        '"color_puesto": cuál de esos colores es el de la prenda en la foto '
        "limpia (la que se anima): mira la foto y elige el de la lista que "
        "más se le parezca. Ese va el ÚLTIMO en la lista y en la frase.\n"
        '"colores_hex": para cada color de la lista, el color MEDIO de la '
        "prenda tal como se ve en la miniatura de ESA variante (o en la foto, "
        "para el puesto), en hexadecimal MEDIDO en la imagen (no el valor "
        "típico del nombre). Es el tono real de esa tienda: un \"beige\" no "
        "es igual en dos prendas. Si no ves la miniatura, omite ese color "
        "del diccionario."
        if colores else ""
    )
    return (
        "\n\nEste vídeo se graba en "
        f"{partes} clips SEPARADOS de {segundos} segundos cada uno, {donde}, "
        "y luego se pegan. Así que no escribas un texto y lo "
        f"partas: escribe {partes} textos, uno por clip, y cada uno:\n"
        f"- con {int(tope * 0.9)} caracteres COMO MÁXIMO, contando espacios y "
        f"signos (es lo que se puede decir con calma en {segundos} segundos);\n"
        "- hecho de frases COMPLETAS: ninguna frase empieza en un clip y acaba "
        "en el otro;\n"
        "- el clip 1 abre con el gancho y las primeras características; el "
        "último cierra con la mejor referencia de la prenda.\n"
        "Entre todos siguen las reglas de arriba (variar gancho, tono y "
        "cierre, no inventar nada).\n\n"
        "Devuelve SOLO un JSON, sin nada más y sin ```:\n"
        f"{json_ejemplo}\n"
        "Solo lo que dice la persona, sin comillas, sin el nombre del producto "
        "al final y sin copiar el resto del prompt." + extra
    )


_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")


def limpiar_hex(valor, colores: list[str]) -> dict[str, str]:
    """`{color: "#rrggbb"}` solo para colores de la lista y hex válidos."""
    if not isinstance(valor, dict):
        return {}
    salida: dict[str, str] = {}
    nombres = {c.lower(): c for c in colores}
    for k, v in valor.items():
        nombre = " ".join(str(k or "").split()).strip(" .,;«»\"'").lower()
        m = _HEX.match(str(v or "").strip())
        if nombre in nombres and m:
            salida[nombres[nombre]] = "#" + m.group(1).lower()
    return salida


def limpiar_colores(valor) -> list[str]:
    """La lista de colores tal como la devolvió la IA, saneada: strings sin
    vacíos ni repetidos, en minúsculas, como mucho seis."""
    if not isinstance(valor, (list, tuple)):
        return []
    salida: list[str] = []
    for c in valor:
        nombre = " ".join(str(c or "").split()).strip(" .,;«»\"'").lower()
        # Un número o un "color" de 30 letras no es un color: fuera.
        if nombre and not nombre.isdigit() and len(nombre) <= 24 and nombre not in salida:
            salida.append(nombre)
    return salida[:6]


# Lo que se le añade a CADA bloque de vídeo de un formato partido. En 8
# segundos el generador empieza a mover los labios en el primer fotograma y
# se comía la primera palabra, y apuraba hasta el último y se comía la última
# frase: un respiro a cada lado lo evita.
def nota_tiempos(segundos: int) -> str:
    return (
        f"\n\nTiempos: el clip dura {segundos} segundos. Empieza a hablar "
        "pasado medio segundo, a ritmo natural y sin prisa, y termina la "
        "última frase antes del último segundo, dejando un instante de "
        "silencio al final. Di el texto completo, sin cortar ninguna palabra."
    )


def _clips_que_caben(
    prompt: str, descripcion: str, imagenes, clips: list[str], tope: int,
    segundos: int, on_log: OnLog,
) -> list[str]:
    """Una reescritura para los clips que se pasan; si aun así no, se cortan."""
    from src.tiktok_shop.api.gemini import generate_json

    # Dos topes: el blando (lo que se pide, con un segundo de respiro) y el
    # duro (lo que de verdad cabe en el clip, medio segundo de respiro). Entre
    # uno y otro se intenta reescribir, pero si no sale, se deja: cortar por
    # 6 caracteres de más destrozaba la frase y cabía igual.
    duro = int(tope * 1.08)
    largos = [i for i, c in enumerate(clips) if len(c) > tope]
    if not largos:
        return clips
    on_log(
        "[nicho_ropa] clips que no caben en "
        f"{segundos}s: {', '.join(f'{i + 1} ({len(clips[i])} car)' for i in largos)}"
        " — se pide una reescritura"
    )
    aviso = (
        "\n\nATENCIÓN: estos textos se pasan de "
        f"{tope} caracteres y no caben en {segundos} segundos:\n"
        + "\n".join(f"clip {i + 1} ({len(clips[i])}): «{clips[i]}»" for i in largos)
        + f"\n\nDevuelve el MISMO JSON con todos los clips, dejando cada uno en "
        f"{int(tope * 0.9)} caracteres o menos. Quita una característica entera "
        "antes que recortar una frase por la mitad: lo lee una voz en alto."
    )
    try:
        # SIN las fotos: para acortar no hacen falta, y con ellas el filtro de
        # Gemini bloqueó la segunda pasada (PROHIBITED_CONTENT) en la primera
        # prueba real —la primera, idéntica pero sin el aviso, pasó—.
        datos = generate_json(
            prompt + _formato_clips(len(clips), tope, segundos) + aviso,
            descripcion, images=None,
        )
        nuevos = [_limpiar_dice(str(c)) for c in (datos or {}).get("clips") or []]
        if len(nuevos) == len(clips) and all(nuevos):
            clips = nuevos
    except Exception as e:  # noqa: BLE001 — valen los primeros antes que nada
        on_log(f"[nicho_ropa] no se pudo reescribir: {e}")
    # Último recurso, por clip y SOLO si no cabe de verdad (tope duro).
    salida = []
    for i, c in enumerate(clips, start=1):
        if len(c) > duro:
            corto = recortar(c, duro)
            if corto == c:
                on_log(f"[nicho_ropa] ⚠️ clip {i}: {len(c)} car. y sin sitio donde cortar sin romper la frase — rehazlo")
            else:
                on_log(f"[nicho_ropa] clip {i}: {len(c)} car. → {len(corto)} (cortado por la última frase)")
            c = corto
        elif len(c) > tope:
            on_log(f"[nicho_ropa] clip {i}: {len(c)} car., algo justo pero cabe")
        salida.append(c)
    return salida


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
    # Lo que cabe en CADA clip cuando el formato se parte (0 = sin tope por
    # clip). El total puede caber y una mitad no: el corte cae en un punto,
    # no en el centro exacto.
    caracteres_clip: int = 0,
    segundos_clip: int = 8,
    # Formato de la tienda: se pide además la lista de colores que nombra
    # (ver `_formato_clips`) y sale en `colores`.
    colores: bool = False,
    # Algo más que decirle sobre las fotos adjuntas (p. ej. que la última es
    # la captura del selector de colores). Va en la descripción del producto.
    notas: str = "",
    # Colores ya sabidos (leídos de la captura o de las fotos, el puesto el
    # último): mandan sobre los que devuelva Gemini, que en un reintento sin
    # fotos se los inventa.
    colores_fijos: list[str] | None = None,
    on_log: OnLog = _noop,
) -> dict:
    """`{dice, video, videos[, colores]}` para una prenda. Lanza si Gemini no lo escribe."""
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
    if notas:
        descripcion += f" {notas.strip()}"

    imagenes = [str(f) for f in (fotos or [])] or None

    if partes > 1 and caracteres_clip:
        return _escribir_por_clips(
            prompt, descripcion, imagenes, partes, caracteres_clip,
            segundos_clip, on_log, colores=colores, colores_fijos=colores_fijos,
        )

    datos = _json_o_sin_fotos(generate_json, prompt, descripcion, imagenes, on_log, formato=_FORMATO)
    if not isinstance(datos, dict):
        raise ValueError(
            f"Gemini devolvió algo que no es un objeto: {type(datos).__name__}"
        )

    dice = _limpiar_dice(str(datos.get("dice") or ""))
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
        if len(dice) > max_caracteres:
            # Ni con la reescritura cabe. Se corta por la última frase entera:
            # dejarla larga es que el generador la corte por donde le toque, y
            # eso es media palabra al final del clip.
            dice = recortar(dice, max_caracteres)
            on_log(f"[nicho_ropa] cortada por la última frase: {len(dice)} caracteres")

    # El bloque se monta aquí con el texto del curso: la IA solo pone la frase.
    trozos = partir(dice, partes) if partes > 1 else [dice]
    if caracteres_clip:
        # Una mitad que no cabe en su clip se corta por su última frase: el
        # generador dice TODO lo que le pongas y lo que sobra se lo come.
        ajustados = [recortar(t, caracteres_clip) for t in trozos]
        for i, (antes, despues) in enumerate(zip(trozos, ajustados), start=1):
            if len(despues) < len(antes):
                on_log(
                    f"[nicho_ropa] clip {i}: {len(antes)} car. no caben en 8s, "
                    f"se queda en {len(despues)}"
                )
        trozos = ajustados
        dice = " ".join(trozos)
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
    nueva = _limpiar_dice(str(datos.get("dice") or ""))
    if not nueva or len(nueva) >= len(dice):
        return {}
    return {"dice": nueva}



# Dónde empieza lo que NO hace falta para ESCRIBIR el texto: la voz y el
# movimiento son para el generador de vídeo, y `_montar_video` los vuelve a
# pegar del prompt original. Se cortan como último recurso ante un bloqueo.
_INICIO_VOZ = re.compile(r"\n\s*Voz (femenina|masculina)", re.IGNORECASE)


def solo_instrucciones(prompt: str) -> str:
    """El prompt hasta el ejemplo (incluido), sin la voz ni el movimiento."""
    m = _INICIO_VOZ.search(prompt)
    return prompt[: m.start()].rstrip() if m else prompt


def _json_o_sin_fotos(
    generate_json, prompt: str, descripcion: str, imagenes, on_log: OnLog,
    formato: str = "",
):
    """Con las fotos; y si Gemini BLOQUEA la petición, cada vez con menos.

    El bloqueo (cero candidatos, PROHIBITED_CONTENT) no es determinista: el
    mismo texto pasa o no según la suma de "mujer + por detrás + sentadilla"
    y las fotos. Escalera: (1) tal cual, (2) sin fotos, (3) sin fotos y solo
    las instrucciones + ejemplo — la voz y el movimiento no hacen falta para
    escribir el texto y son lo que más pesa en el filtro. Mejor un guion de
    oídas que ninguno.

    `formato` (qué JSON devolver) va aparte para que el recorte del paso (3) no
    se lo coma: sin él Gemini contestaba con texto suelto y el guion se tiraba
    («no devolvió lo que se dice en los clips»). El bloqueo que más sale aquí
    es el 4 (RECITATION), no el de contenido.
    """
    from src.tiktok_shop.api.gemini import GeminiBlockedError

    intentos = [(prompt + formato, imagenes, "con fotos")]
    if imagenes:
        intentos.append((prompt + formato, None, "sin fotos"))
    corto = solo_instrucciones(prompt)
    if corto != prompt:
        intentos.append((corto + formato, None, "sin fotos y sin voz/movimiento"))
    ultimo: Exception | None = None
    for i, (texto, fotos, como) in enumerate(intentos):
        try:
            return generate_json(texto, descripcion, images=fotos)
        except GeminiBlockedError as e:
            ultimo = e
            if i + 1 < len(intentos):
                on_log(f"[nicho_ropa] {e} ({como}): se reintenta {intentos[i + 1][2]}")
    raise ultimo  # type: ignore[misc]


def _escribir_por_clips(
    prompt: str, descripcion: str, imagenes, partes: int, tope: int,
    segundos: int, on_log: OnLog, colores: bool = False,
    colores_fijos: list[str] | None = None,
) -> dict:
    """Un texto por clip, cada uno con su tope y sus tiempos."""
    from src.tiktok_shop.api.gemini import generate_json

    datos = _json_o_sin_fotos(
        generate_json, prompt, descripcion, imagenes, on_log,
        formato=_formato_clips(partes, tope, segundos, colores),
    )
    lista_colores = limpiar_colores((datos or {}).get("colores")) if colores else []
    if colores and colores_fijos and len(colores_fijos) >= 2:
        if lista_colores != list(colores_fijos):
            on_log(f"[nicho_ropa] colores del guion {lista_colores} → los leídos: {list(colores_fijos)}")
        lista_colores = list(colores_fijos)
    hex_colores = limpiar_hex((datos or {}).get("colores_hex"), lista_colores) if colores else {}
    puesto = ""
    if colores and not colores_fijos:
        # El puesto va el ÚLTIMO: es donde el montaje deja de poner fotos y
        # sigue el vídeo real. Gemini lo identifica pero no siempre lo
        # ordena (dejó "beige, marron, taupe y verde militar" llevando taupe).
        puesto = _color_de_la_lista(str((datos or {}).get("color_puesto") or ""), lista_colores)
        if puesto and lista_colores[-1] != puesto:
            lista_colores = [c for c in lista_colores if c != puesto] + [puesto]
            on_log(f"[nicho_ropa] el color puesto es «{puesto}»: pasa al final de la lista")
    if colores and len(lista_colores) < 2:
        on_log(
            "[nicho_ropa] el guion trae "
            f"{len(lista_colores)} color(es): el vídeo saldrá sin cortes de color"
        )
    clips = [_limpiar_dice(str(c)) for c in (datos or {}).get("clips") or []]
    clips = [c for c in clips if c]
    if len(clips) != partes:
        # Si devuelve uno solo (o tres), se reparte lo que haya: mejor eso que
        # tirar la llamada.
        junto = " ".join(clips) or _limpiar_dice(str((datos or {}).get("dice") or ""))
        if not junto:
            raise ValueError("Gemini no devolvió lo que se dice en los clips")
        on_log(f"[nicho_ropa] llegaron {len(clips)} clips en vez de {partes}: se reparten")
        clips = partir(junto, partes)
    clips = _clips_que_caben(prompt, descripcion, imagenes, clips, tope, segundos, on_log)
    videos = [
        (_montar_video(prompt, c, parte=i) or c) + nota_tiempos(segundos)
        for i, c in enumerate(clips, start=1)
    ]
    if colores and len(lista_colores) >= 2 and clips:
        # La frase del clip 1 tiene que enumerar los colores en ESE orden:
        # es lo que casa cada palabra con su foto al montar.
        clips[0] = forzar_enumeracion(clips[0], lista_colores, on_log)
        videos[0] = (_montar_video(prompt, clips[0], parte=1) or clips[0]) + nota_tiempos(segundos)
    salida = {"dice": " ".join(clips), "video": videos[0], "videos": videos}
    if colores:
        salida["colores"] = lista_colores
        salida["colores_hex"] = hex_colores
    return salida


def _color_de_la_lista(nombre: str, lista: list[str]) -> str:
    """El elemento de `lista` que es ese nombre (sin acentos ni mayúsculas)."""
    plano = _sin_acentos(nombre).strip(" .,;«»\"'")
    if not plano:
        return ""
    for c in lista:
        if _sin_acentos(c) == plano:
            return c
    for c in lista:
        if plano in _sin_acentos(c) or _sin_acentos(c) in plano:
            return c
    return ""


# Palabras con las que empieza un nombre de color: sirven para reconocer que
# la primera frase del clip 1 es la lista de colores aunque nombre alguno que
# no está en la lista guardada ("beige, marrón…" en una prenda sin marrón).
_PALABRAS_COLOR = frozenset((
    "negro", "negra", "blanco", "blanca", "gris", "beige", "marron", "azul",
    "verde", "rojo", "roja", "rosa", "amarillo", "naranja", "morado", "lila",
    "granate", "burdeos", "crudo", "camel", "caqui", "kaki", "taupe",
    "terracota", "mostaza", "coral", "turquesa", "plata", "dorado", "nude",
    "vino", "arena", "chocolate", "marino", "militar", "celeste", "fucsia",
    "malva", "violeta", "salmon", "hueso", "topo", "ceniza", "vainilla",
    "oliva", "denim", "cafe", "tostado", "perla", "piedra", "mocca", "moka",
))


def _es_lista_de_colores(frase: str, colores: list[str]) -> bool:
    """Si la frase es una enumeración de colores ("Gris, negro y azul")."""
    import re as _re

    partes = [x for x in _re.split(r"\s*,\s*|\s+(?:y|e)\s+", frase.strip()) if x]
    if len(partes) < 2 or any(len(x.split()) > 3 for x in partes):
        return False
    conocidos = {_sin_acentos(c) for c in colores}
    color = sum(
        1 for x in partes
        if _sin_acentos(x) in conocidos or _sin_acentos(x).split()[0] in _PALABRAS_COLOR
    )
    return color * 2 >= len(partes)


def forzar_enumeracion(texto: str, colores: list[str], on_log: OnLog = _noop) -> str:
    """El clip 1 abre SIEMPRE con la lista de colores guardada, en su orden.

    Gemini devuelve la lista y la frase por separado y no siempre casan: en
    la Carpeta 11 de mujer salió «Beige, marrón, verde militar y azul
    marino» para una chaqueta en negro, verde militar, azul marino y beige,
    y dos vestidos sin nombrar ningún color. Las imágenes y el perchero van
    con la lista, así que es la frase la que se corrige: se sustituye la
    enumeración que haya o, si no hay, se pone delante."""
    import re as _re

    if len(colores) < 2:
        return texto
    reordenado = reordenar_enumeracion(texto, colores)
    if reordenado != texto:
        return reordenado
    lista = ", ".join(colores[:-1]) + " y " + colores[-1]
    lista = lista[0].upper() + lista[1:]
    resto = texto.strip()
    m = _re.match(r"([^.!?¡¿]+)[.!?]\s*", resto)
    if m and _es_lista_de_colores(m.group(1), colores):
        if _sin_acentos(m.group(1).strip()) == _sin_acentos(lista):
            return texto
        on_log(f"[nicho_ropa] la frase nombraba «{m.group(1).strip()}»: se cambia por «{lista}»")
        resto = resto[m.end():]
    else:
        on_log(f"[nicho_ropa] la frase no nombraba los colores: se abre con «{lista}»")
    return f"{lista}. {resto}".strip()


def reordenar_enumeracion(texto: str, colores: list[str]) -> str:
    """Si el texto EMPIEZA enumerando esos colores, los deja en el orden de
    `colores` (el puesto el último). Si no encuentra la enumeración, no toca."""
    import re as _re

    resto = texto.lstrip()
    # Consumir, desde el principio, colores separados por comas / "y".
    vistos: list[str] = []
    pos = 0
    while True:
        m = _re.match(r"\s*(?:,\s*)?(?:(?:y|e)\s+)?", resto[pos:])
        arranque = pos + (m.end() if m else 0)
        hallado = None
        # Los nombres largos primero: "azul claro" antes que "azul".
        for c in sorted(colores, key=len, reverse=True):
            if _sin_acentos(resto[arranque:arranque + len(c)]) == _sin_acentos(c) and c not in vistos:
                hallado = c
                break
        if not hallado:
            break
        vistos.append(hallado)
        pos = arranque + len(hallado)
    if len(vistos) < 2 or set(vistos) != set(colores):
        return texto
    ordenados = [c for c in colores if c in vistos]
    nueva = ", ".join(ordenados[:-1]) + " y " + ordenados[-1]
    nueva = nueva[0].upper() + nueva[1:]
    return (nueva + resto[pos:]).strip()
