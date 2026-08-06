"""Presets de subtítulo/filtro que rotan por "ronda" (para que las réplicas
se vean distintas si la v1 no viraliza). Registro en `STYLE_PRESETS`, orden
de rotación en `STYLE_ORDER`.

Son SEIS: tres estilos de texto, cada uno en dos acabados.

- **A "Clásico"**: línea completa blanca, borde negro, centrada.
- **B "Frases"**: trozos de hasta 3 palabras, centrados, en Playfair Display
  Black. Sustituyó al antiguo "Reveal" palabra a palabra: con una sola palabra
  no se coge el sentido de la frase.
- **C "Karaoke"**: palabra a palabra, la activa en blanco y el resto en negro.
- **A2 / B2 / C2**: los mismos tres, con la MISMA tipografía y el mismo
  movimiento, pero con el acabado LIMPIO (`_LIMPIO`): sin polvo de celuloide,
  sin rayaduras y sin grano, con el color más claro y saturado y los bordes
  oscurecidos con una viñeta algo más suave que la de A/B/C.

Hubo otros cuatro que se retiraron el 6 ago 2026 porque no viralizaban: D
"Serif apilado", E "Cascada" y los dos del marco cuadrado, G y H. De los
cuadrados sobrevive lo bueno que tenían — su filtro claro es el de A2/B2/C2.
Sus `build_ass` se conservan más abajo (no estorban y volver a darles de alta
es una línea en el registro).

Añadir un estilo nuevo: define un `StylePreset` en `STYLE_PRESETS` con su
`build_ass` y mete su clave en `STYLE_ORDER` — no hay más sitios que tocar
(el runner y el renderer iteran sobre el registro, no hardcodean nombres)."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable

from src.viralizacion import config


# ---------------------------------------------------------------------------
# Helpers ASS comunes
# ---------------------------------------------------------------------------
def ass_time(t: float) -> str:
    if t < 0:
        t = 0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    cs = int(round((t - int(t)) * 100))
    if cs == 100:
        cs = 0
        s += 1
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_header(style_line: str) -> str:
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {config.TARGET_W}
PlayResY: {config.TARGET_H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{style_line}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _inicio_siguiente_bloque(
    lines: list[dict], idx_linea: int, fin_bloque_en_linea: int, tamano: int
) -> float | None:
    """Cuándo entra el siguiente bloque de palabras (en esta línea o en la
    siguiente). Ningún evento puede pasar de ahí: dos eventos ASS solapados
    NO se sustituyen, se APILAN, y en pantalla se lee el amasijo de las dos
    frases a la vez.
    """
    palabras = lines[idx_linea].get("words") or []
    if fin_bloque_en_linea < len(palabras):
        return float(palabras[fin_bloque_en_linea]["start"])
    for siguiente in lines[idx_linea + 1:]:
        ws = siguiente.get("words") or []
        if ws:
            return float(ws[0]["start"])
    return None


def _dialogue(start: float, end: float, text: str, layer: int = 0) -> str:
    """`layer` decide quién tapa a quién cuando dos eventos coinciden en el
    tiempo: ASS pinta primero las capas bajas. Con todo en 0 mandaba el orden
    del fichero y las palabras nuevas quedaban DEBAJO de las anteriores."""
    return f"Dialogue: {layer},{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{text}"


# ---------------------------------------------------------------------------
# Estilo A — Clásico
# ---------------------------------------------------------------------------
def build_ass_classic(lines: list[dict], preset: "StylePreset") -> str:
    style_line = (
        f"Style: Default,{config.SUB_FONT},{config.SUB_FONTSIZE},"
        f"&H00FFFFFF&,&H000000FF&,&H00000000&,&H00000000&,-1,0,0,0,100,100,0,0,1,2,0,5,"
        f"{config.SUB_MARGIN_LR},{config.SUB_MARGIN_LR},0,1"
    )
    header = _ass_header(style_line)
    events = [_dialogue(ln["start"], ln["end"], ln["text"]) for ln in lines]
    return header + "\n".join(events) + "\n"


# ---------------------------------------------------------------------------
# Estilo B — Frases cortas (máx. 3 palabras) en serif
# ---------------------------------------------------------------------------
# Cuántas palabras caben en pantalla a la vez. Tres es lo que se ve en la
# referencia que pasó el operador ("tienes que ser"): se lee de un golpe, sin
# tener que barrer la línea con la vista como en A y C.
FRASE_MAX_PALABRAS = 3


def build_ass_frases(lines: list[dict], preset: "StylePreset") -> str:
    """Trozos de hasta `FRASE_MAX_PALABRAS` palabras, centrados, en serif.

    Sustituye al antiguo "Reveal" palabra a palabra. Con una sola palabra el
    espectador no llega a coger el sentido de la frase; con tres sí, y sigue
    entrando de golpe (que es lo que aquella variante buscaba).

    La tipografía es Playfair Display Black —la serif de la referencia—, en
    blanco con sombra oscura difuminada: sobre paisaje claro el blanco a pelo
    se pierde, y un borde duro le da aire de subtítulo de karaoke, que es justo
    lo que este estilo NO es.
    """
    font = preset.font_name or config.SUB_FONT
    # Grande: en la referencia tres palabras ocupan ~la mitad del ancho. Con el
    # cuerpo base se quedaba en un tercio y parecía un subtítulo de película,
    # no el rótulo protagonista que es en este estilo.
    size = int(config.SUB_FONTSIZE * 1.9)
    style_line = (
        f"Style: Default,{font},{size},"
        # blanco, sin secundario; contorno y sombra en negro translúcido
        f"&H00FFFFFF&,&H000000FF&,&H64000000&,&H78000000&,-1,0,0,0,100,100,0,0,1,3,2,5,"
        f"{config.SUB_MARGIN_LR},{config.SUB_MARGIN_LR},0,1"
    )
    header = _ass_header(style_line)

    todas = [w for ln in lines for w in (ln.get("words") or [])]
    events: list[str] = []
    for i in range(0, len(todas), FRASE_MAX_PALABRAS):
        grupo = todas[i:i + FRASE_MAX_PALABRAS]
        start = float(grupo[0]["start"])
        end = float(grupo[-1]["end"])
        # No invadir el grupo siguiente: dos eventos ASS solapados se APILAN en
        # pantalla y se leen las dos frases a la vez.
        siguiente = i + FRASE_MAX_PALABRAS
        if siguiente < len(todas):
            end = min(end, float(todas[siguiente]["start"]))
        if end - start < 0.20:
            end = start + 0.20
        texto = " ".join(w["word"].strip() for w in grupo if w["word"].strip())
        if not texto:
            continue
        # `\blur` difumina contorno y sombra: es lo que da el halo suave de la
        # referencia en vez de un borde recortado.
        events.append(_dialogue(start, end, f"{{\\blur1.4}}{texto}"))

    return header + "\n".join(events) + "\n"


# ---------------------------------------------------------------------------
# Estilo B (antiguo) — Reveal palabra a palabra
# ---------------------------------------------------------------------------
def build_ass_reveal(lines: list[dict], preset: "StylePreset") -> str:
    """UNA palabra en pantalla cada vez, cambiando de molde tipográfico.

    Historia de este estilo: primero revelaba letra a letra acumulando la
    frase entera (con frases largas el texto se hacía diminuto), luego una
    palabra sola con glow blanco. El glow (`\\blur` con borde blanco) fundía
    las letras en un borrón: en el vídeo se veía una mancha, no una palabra.

    Ahora es una palabra a la vez con la tipografía variada del estilo
    Cuadrado (`_STACK_MOLDES`: mayúsculas/cursiva/escala/amarillo de acento),
    con borde negro nítido. Se lee siempre y cada palabra entra distinta.
    """
    # Tamaño mayor que el resto de estilos: al haber una sola palabra hay
    # sitio de sobra y el impacto es la gracia del estilo.
    font_size = int(config.SUB_FONTSIZE * 1.35)
    style_line = (
        f"Style: Default,{config.SUB_FONT},{font_size},"
        f"&H00FFFFFF&,&H000000FF&,&H00000000&,&HB0000000&,-1,0,0,0,100,100,0,0,1,4,3,5,"
        f"{config.SUB_MARGIN_LR},{config.SUB_MARGIN_LR},0,1"
    )
    header = _ass_header(style_line)
    events: list[str] = []

    # Una sola secuencia con TODAS las palabras del vídeo: hace falta para
    # saber cuándo entra la siguiente (y así no solaparlas) y para que el
    # molde avance sin reiniciarse en cada línea — reiniciando, las frases
    # cortas repetían siempre los mismos dos moldes.
    todas = [w for ln in lines for w in (ln.get("words") or [])]

    for n, w in enumerate(todas):
        start = float(w["start"])
        end = float(w["end"])
        # Whisper a veces devuelve palabras de duración ~0; sin un mínimo la
        # palabra parpadearía y no daría tiempo a leerla.
        if end - start < 0.12:
            end = start + 0.12
        # …pero ese mínimo no puede invadir la palabra siguiente: dos eventos
        # ASS solapados se apilan en pantalla y el estilo deja de ser "una
        # palabra cada vez" (se veían pares como "LO / que").
        if n + 1 < len(todas):
            end = min(end, float(todas[n + 1]["start"]))
        if end <= start:
            end = start + 0.04
        mayus, cursiva, escala, color = _STACK_MOLDES[n % len(_STACK_MOLDES)]
        txt = w["word"].upper() if mayus else w["word"].lower()
        tags = f"\\1c{color}\\fscx{int(escala * 100)}\\fscy{int(escala * 100)}"
        if cursiva:
            tags += "\\i1"
        events.append(_dialogue(start, end, f"{{{tags}}}{txt}"))

    return header + "\n".join(events) + "\n"


# ---------------------------------------------------------------------------
# Estilo C — Cinemático (karaoke por palabra, blanco/negro)
# ---------------------------------------------------------------------------
def _karaoke_text(words: list[dict], active_idx: int) -> str:
    """Palabra activa en blanco, resto en negro.

    El BORDE va invertido respecto al relleno: la palabra activa (blanca) lleva
    borde negro y las inactivas (negras) borde blanco. Sin esto la palabra
    activa era blanca con borde blanco y se perdía sobre paisajes claros
    (fachadas, cielo, mapas).
    """
    parts = []
    for j, w in enumerate(words):
        if j == active_idx:
            fill, outline = "&HFFFFFF&", "&H000000&"
        else:
            fill, outline = "&H000000&", "&HFFFFFF&"
        parts.append(f"{{\\1c{fill}\\3c{outline}}}{w['word']}")
    return " ".join(parts)


def build_ass_cinematic(lines: list[dict], preset: "StylePreset") -> str:
    # OutlineColour BLANCO (para que las palabras negras no se fundan con
    # fondos oscuros). PrimaryColour por defecto negro — se sobreescribe
    # inline con \1c en cada palabra de cada evento.
    style_line = (
        f"Style: Default,{config.SUB_FONT},{config.SUB_FONTSIZE},"
        f"&H00000000&,&H000000FF&,&H00FFFFFF&,&H00000000&,-1,0,0,0,100,100,0,0,1,2,0,5,"
        f"{config.SUB_MARGIN_LR},{config.SUB_MARGIN_LR},0,1"
    )
    header = _ass_header(style_line)
    events: list[str] = []

    for ln in lines:
        words = ln["words"]
        if not words:
            continue
        # pre-roll: antes de la 1ª palabra, todo en negro (ninguna activa)
        if words[0]["start"] > ln["start"] + 0.01:
            text = _karaoke_text(words, active_idx=-1)
            events.append(_dialogue(ln["start"], words[0]["start"], text))
        for i, w in enumerate(words):
            ev_start = w["start"]
            ev_end = words[i + 1]["start"] if i + 1 < len(words) else ln["end"]
            if ev_end <= ev_start:
                ev_end = ev_start + 0.05
            text = _karaoke_text(words, active_idx=i)
            events.append(_dialogue(ev_start, ev_end, text))

    return header + "\n".join(events) + "\n"



# ---------------------------------------------------------------------------
# Moldes tipográficos (los usan el estilo B "Reveal" y el G "Cuadrado")
# ---------------------------------------------------------------------------
# Cómo salen las palabras. Cada una coge un "molde" distinto para que el
# texto no parezca un subtítulo corrido sino un montaje hecho a mano, que es
# lo que hace reconocible este estilo en los vídeos que funcionan.
#   (mayusculas, cursiva, escala, color)
_STACK_MOLDES = [
    (True,  False, 1.00, "&HFFFFFF&"),   # MAYÚS grande, blanco
    (False, True,  0.82, "&HFFFFFF&"),   # cursiva pequeña
    (True,  False, 0.92, "&HFFFFFF&"),
    (False, False, 0.78, "&HFFFFFF&"),   # minúscula pequeña
    (True,  False, 1.06, "&H00D7FF&"),   # MAYÚS grande AMARILLO (acento)
    (False, True,  0.86, "&HFFFFFF&"),
]

# Cuántas palabras se ven a la vez antes de empezar bloque nuevo. Con más de
# 4 el bloque se come el cuadrado y deja de leerse.
_STACK_MAX = 4


def build_ass_stacked(lines: list[dict], preset: "StylePreset") -> str:
    """Las palabras van APARECIENDO y se acumulan apiladas, cada una con un
    molde tipográfico distinto (mayúsculas/cursiva/tamaño/color).

    A diferencia de `build_ass_reveal` (una palabra sola cada vez), aquí se
    ven las últimas 4 a la vez: se lee la frase entera de un golpe y el
    bloque llena el cuadrado, que es lo que da el aspecto de los vídeos de
    referencia. Al llegar a 4 se empieza bloque nuevo en vez de seguir
    apilando, o el texto se saldría del recuadro.
    """
    # Más grande que el resto de estilos: el texto vive DENTRO del cuadrado y
    # tiene que llenarlo. Con el tamaño normal el bloque se queda flotando
    # pequeño en medio y pierde la fuerza de los vídeos de referencia.
    base = int(config.SUB_FONTSIZE * 1.45)
    style_line = (
        f"Style: Default,{config.SUB_FONT},{base},"
        f"&H00FFFFFF&,&H000000FF&,&H00000000&,&HB0000000&,-1,0,0,0,100,100,0,0,1,3,3,5,"
        f"{config.SUB_MARGIN_LR},{config.SUB_MARGIN_LR},0,1"
    )
    header = _ass_header(style_line)
    events: list[str] = []

    for idx_linea, ln in enumerate(lines):
        palabras = ln.get("words") or []
        for inicio in range(0, len(palabras), _STACK_MAX):
            grupo = palabras[inicio:inicio + _STACK_MAX]
            tope = _inicio_siguiente_bloque(
                lines, idx_linea, inicio + _STACK_MAX, _STACK_MAX,
            )
            for i in range(len(grupo)):
                visibles = grupo[: i + 1]
                partes = []
                for j, w in enumerate(visibles):
                    mayus, cursiva, escala, color = _STACK_MOLDES[
                        (inicio + j) % len(_STACK_MOLDES)
                    ]
                    txt = w["word"].upper() if mayus else w["word"].lower()
                    tags = f"\\1c{color}\\fscx{int(escala*100)}\\fscy{int(escala*100)}"
                    if cursiva:
                        tags += "\\i1"
                    partes.append(f"{{{tags}}}{txt}")
                ev_start = float(grupo[i]["start"])
                ev_end = (
                    float(grupo[i + 1]["start"]) if i + 1 < len(grupo)
                    else float(grupo[i]["end"])
                )
                # La última palabra del grupo se queda un poco más para que dé
                # tiempo a leer el bloque completo antes de vaciarse.
                if i == len(grupo) - 1:
                    ev_end = max(ev_end, float(grupo[i]["end"]) + 0.25)
                if ev_end <= ev_start:
                    ev_end = ev_start + 0.12
                if tope is not None:
                    ev_end = min(ev_end, tope)
                if ev_end > ev_start:
                    events.append(_dialogue(ev_start, ev_end, "\\N".join(partes)))

    return header + "\n".join(events) + "\n"


# ---------------------------------------------------------------------------
# Estilo E — Cascada (palabras desperdigadas bajando por la pantalla)
# ---------------------------------------------------------------------------
# Como `_STACK_MOLDES` pero con más contraste de tamaño: la gracia de este
# estilo es que alterna una palabra pequeña con otra enorme en amarillo.
#   (escala, color)
#   (escala, color, cursiva, mayúsculas)
_CASCADA_MOLDES = [
    (0.58, "&HFFFFFF&", False, False),   # pequeña blanca
    (1.45, "&H00D7FF&", False, False),   # ENORME amarilla
    (0.68, "&HFFFFFF&", True,  False),   # pequeña cursiva
    (1.30, "&HFFFFFF&", False, True),    # grande blanca en MAYÚS
    (0.62, "&H00D7FF&", False, False),   # pequeña amarilla
    (1.40, "&H00D7FF&", False, True),    # ENORME amarilla en MAYÚS
    (0.74, "&HFFFFFF&", True,  False),
    (1.24, "&H00D7FF&", True,  False),   # grande amarilla cursiva
]

# Amarillo del resaltado (ASS va en BGR, no RGB).
_HIGHLIGHT_COLOR = "&H00E9FF&"

# Palabras visibles a la vez antes de vaciar y empezar cascada nueva.
_CASCADA_MAX = 4
# Desplazamientos horizontales posibles respecto al centro, en fracción del
# ancho. Se SORTEAN sin repetir dentro de cada bloque en vez de recorrerse en
# orden: un zigzag fijo izquierda-derecha-izquierda se lee como plantilla y
# cansa a los pocos vídeos.
_CASCADA_DX = [-0.20, -0.12, -0.04, 0.04, 0.13, 0.21]


def build_ass_cascade(lines: list[dict], preset: "StylePreset") -> str:
    """Palabras que se acumulan cayendo en zigzag por la pantalla.

    Cada palabra es su PROPIO evento con `\\pos`: en ASS un solo evento con
    saltos de línea comparte una única posición, así que apilar con `\\N`
    solo permite un bloque centrado. Con un evento por palabra, varios
    conviven en pantalla cada uno donde le toca.

    El ancho de cada palabra se estima para no salirse por los lados (con
    `\\pos` no hay ajuste de línea que valga: lo que se sale, se pierde).
    """
    base = int(config.SUB_FONTSIZE * 1.30)
    style_line = (
        f"Style: Default,{config.SUB_FONT},{base},"
        f"&H00FFFFFF&,&H000000FF&,&H00000000&,&HB0000000&,-1,0,0,0,100,100,0,0,1,4,3,5,"
        f"0,0,0,1"
    )
    header = _ass_header(style_line)
    events: list[str] = []

    # Alto del bloque: se centra verticalmente el conjunto de la cascada.
    # Bloque COMPACTO, casi tocándose: en la referencia las palabras se
    # solapan un poco y forman un grupo, no una lista con aire entre líneas.
    salto = int(base * 0.92)
    margen = 60

    for idx_linea, ln in enumerate(lines):
        palabras = ln.get("words") or []
        for inicio in range(0, len(palabras), _CASCADA_MAX):
            grupo = palabras[inicio:inicio + _CASCADA_MAX]
            fin_grupo = max(
                float(grupo[-1]["end"]) + 0.25,
                float(grupo[-1]["start"]) + 0.35,
            )
            # La cola de 0,25s no puede pisar el bloque siguiente —ni el de
            # esta línea ni el de la siguiente—: si no, se ven ocho palabras
            # a la vez, unas encima de otras, y la cascada se emborrona.
            tope = _inicio_siguiente_bloque(
                lines, idx_linea, inicio + _CASCADA_MAX, _CASCADA_MAX,
            )
            if tope is not None:
                fin_grupo = min(fin_grupo, tope)
            alto_bloque = salto * (len(grupo) - 1)
            y0 = (config.TARGET_H - alto_bloque) // 2
            # Posiciones y moldes sorteados por bloque: la cascada tiene que
            # caer desordenada (una arriba a la izquierda, la siguiente abajo
            # en medio…), no en zigzag regular.
            desplazamientos = random.sample(_CASCADA_DX, k=min(len(grupo), len(_CASCADA_DX)))
            molde0 = random.randrange(len(_CASCADA_MOLDES))
            for j, w in enumerate(grupo):
                escala, color, cursiva, mayus = _CASCADA_MOLDES[
                    (molde0 + j) % len(_CASCADA_MOLDES)
                ]
                txt = w["word"].upper() if mayus else w["word"].lower()
                # DejaVu Sans Bold ronda 0.62·tamaño por carácter. Basta para
                # decidir si hay que encoger o recolocar; no hace falta medir.
                ancho = len(txt) * base * escala * 0.62
                if ancho > config.TARGET_W - 2 * margen:
                    escala *= (config.TARGET_W - 2 * margen) / ancho
                    ancho = config.TARGET_W - 2 * margen
                dx = desplazamientos[j % len(desplazamientos)]
                x = config.TARGET_W / 2 + config.TARGET_W * dx
                x = min(max(x, ancho / 2 + margen), config.TARGET_W - ancho / 2 - margen)
                # Altura con holgura: el escalón fijo volvía a marcar patrón.
                y = y0 + j * salto + random.randint(-10, 10)
                tags = (
                    f"\\an5\\pos({int(x)},{int(y)})\\1c{color}"
                    f"\\fscx{int(escala * 100)}\\fscy{int(escala * 100)}"
                )
                if cursiva:
                    tags += "\\i1"
                # Cada palabra entra cuando se pronuncia y se queda hasta que
                # se vacía el grupo: así se lee la frase entera de un golpe.
                # `layer=j`: al solaparse, la palabra que acaba de entrar tapa
                # a las anteriores (que es lo que hace la referencia).
                events.append(
                    _dialogue(float(w["start"]), fin_grupo, f"{{{tags}}}{txt}", layer=j)
                )

    return header + "\n".join(events) + "\n"



# ---------------------------------------------------------------------------
# Estilo H — Frase en mayúsculas con la palabra hablada en amarillo
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Estilo D — Película vieja
# ---------------------------------------------------------------------------
# Réplica del estilo con el que una cuenta de referencia (RudySkate) viralizó
# tres vídeos seguidos de Pablo Motos: serif de alto contraste, MUY pocas
# palabras a la vez, centradas en mitad de pantalla, y grano/motas de polvo
# imitando celuloide antiguo.
#
# Dos reglas que vienen de mirar los vídeos:
#   - Nunca hay más de tres palabras en pantalla. El bloque se VACÍA antes de
#     empezar el siguiente; no se acumulan frases.
#   - Dentro del bloque las palabras van CRECIENDO hacia abajo, y el bloque
#     alterna entre letra clara con halo oscuro y letra oscura con halo claro
#     según el fondo.
_PELICULA_MAX = 3
# Escala de cada línea del bloque (crece hacia abajo).
_PELICULA_ESCALAS = (0.86, 1.05, 1.24)
# (color de letra, color del halo, grosor del halo). ASS usa BGR, no RGB.
# El bloque OSCURO necesita el halo más gordo: la letra clara sobre fondo
# oscuro se lee sola, pero la oscura solo destaca si el halo la recorta bien
# (y no siempre cae sobre un cielo claro como en los vídeos de referencia).
_PELICULA_CLARO = ("&HFFFFFF&", "&H101010&", 4)
_PELICULA_OSCURO = ("&H121212&", "&HF0F0F0&", 7)


def build_ass_pelicula(lines: list[dict], preset: "StylePreset") -> str:
    """Palabras de una en una, apiladas de tres en tres y creciendo, en el
    centro exacto de la pantalla.

    El `\\an5` (centro vertical) es deliberado: en los vídeos de referencia
    el texto vive en mitad del plano, no abajo como un subtítulo normal.
    """
    base = int(config.SUB_FONTSIZE * 1.75)
    fuente = preset.font_name or config.SUB_FONT
    style_line = (
        f"Style: Default,{fuente},{base},"
        f"&H00FFFFFF&,&H000000FF&,&H00101010&,&H90000000&,0,0,0,0,100,100,0,0,1,4,3,5,"
        f"{config.SUB_MARGIN_LR},{config.SUB_MARGIN_LR},0,1"
    )
    header = _ass_header(style_line)
    events: list[str] = []
    n_bloque = 0

    for idx_linea, ln in enumerate(lines):
        palabras = ln.get("words") or []
        for inicio in range(0, len(palabras), _PELICULA_MAX):
            grupo = palabras[inicio:inicio + _PELICULA_MAX]
            # Tope duro: dos eventos ASS solapados se APILAN en vez de
            # sustituirse, así que sin esto se verían dos frases a la vez.
            tope = _inicio_siguiente_bloque(
                lines, idx_linea, inicio + _PELICULA_MAX, _PELICULA_MAX,
            )
            letra, halo, bord = (
                _PELICULA_CLARO if n_bloque % 2 == 0 else _PELICULA_OSCURO
            )
            n_bloque += 1

            for i in range(len(grupo)):
                visibles = grupo[: i + 1]
                partes = []
                for j, w in enumerate(visibles):
                    escala = _PELICULA_ESCALAS[j % len(_PELICULA_ESCALAS)]
                    tags = (
                        f"\\1c{letra}\\3c{halo}\\4c{halo}\\bord{bord}"
                        f"\\fscx{int(escala * 100)}\\fscy{int(escala * 100)}"
                    )
                    partes.append(f"{{{tags}}}{w['word'].lower()}")
                ev_start = float(grupo[i]["start"])
                ev_end = (
                    float(grupo[i + 1]["start"]) if i + 1 < len(grupo)
                    else float(grupo[i]["end"]) + 0.30
                )
                if ev_end <= ev_start:
                    ev_end = ev_start + 0.12
                if tope is not None:
                    ev_end = min(ev_end, tope)
                if ev_end > ev_start:
                    events.append(
                        _dialogue(ev_start, ev_end, "\\N".join(partes), layer=i)
                    )

    return header + "\n".join(events) + "\n"


def bundled_fonts_dir() -> str:
    """Carpeta `assets/fonts/` del repo (las que ya usa Creator Reward)."""
    from src.font_resolver import _bundled_fonts_dir

    return _bundled_fonts_dir()


def build_ass_highlight(lines: list[dict], preset: "StylePreset") -> str:
    """La frase se va ESCRIBIENDO en mayúsculas y la palabra que suena en
    ese momento va en amarillo; las ya dichas quedan en blanco.

    Es el patrón de los vídeos de referencia del operador: al principio de
    cada frase se ve una palabra sola y, según avanza, la línea entera con
    un único término resaltado. No se pinta la frase completa desde el
    primer instante a propósito — leerla entera antes de oírla mata el
    efecto de "va apareciendo" que engancha.

    El texto va abajo dentro del cuadrado (`\an2` + `MarginV`), no centrado:
    en el centro tapa la cara del ponente.
    """
    fuente = preset.font_name or config.SUB_FONT
    style_line = (
        f"Style: Default,{fuente},{int(config.SUB_FONTSIZE * 1.45)},"
        f"&H00FFFFFF&,&H000000FF&,&H00000000&,&HA0000000&,-1,0,0,0,100,100,0,0,1,3.5,2,2,"
        f"{config.SUB_MARGIN_LR},{config.SUB_MARGIN_LR},{config.HIGHLIGHT_MARGIN_V},1"
    )
    header = _ass_header(style_line)
    events: list[str] = []

    # Cuándo entra la frase SIGUIENTE: ningún evento puede pasar de ahí. Dos
    # eventos ASS solapados no se sustituyen, se APILAN, así que el remate de
    # una frase se quedaba en pantalla debajo de la siguiente y se leía un
    # amasijo de las dos ("10 MIL METROS / COGODRILO O / TIRARSE UN AVIÓN…").
    inicios = [
        float(l["words"][0]["start"]) for l in lines if l.get("words")
    ]

    idx_frase = 0
    for ln in lines:
        palabras = ln.get("words") or []
        if not palabras:
            continue
        idx_frase += 1
        tope = inicios[idx_frase] if idx_frase < len(inicios) else None

        def _cerrar(t: float) -> float:
            return min(t, tope) if tope is not None else t

        for i, w in enumerate(palabras):
            visibles = palabras[: i + 1]
            texto = " ".join(
                f"{{\\1c{_HIGHLIGHT_COLOR if j == i else '&HFFFFFF&'}}}{p['word'].upper()}"
                for j, p in enumerate(visibles)
            )
            ini = float(w["start"])
            fin = float(palabras[i + 1]["start"]) if i + 1 < len(palabras) else float(w["end"])
            if fin <= ini:
                fin = ini + 0.08
            fin = _cerrar(fin)
            if fin > ini:
                events.append(_dialogue(ini, fin, texto))

        # Remate: la frase entera en blanco un instante después de la última
        # palabra. Sin esto el amarillo se queda congelado al final de cada
        # frase y parece que la palabra sigue sonando. Se recorta si la frase
        # siguiente ya ha entrado.
        completa = " ".join(f"{{\\1c&HFFFFFF&}}{p['word'].upper()}" for p in palabras)
        fin_frase = _cerrar(float(palabras[-1]["end"]))
        fin_remate = _cerrar(float(palabras[-1]["end"]) + 0.35)
        if fin_remate > fin_frase:
            events.append(_dialogue(fin_frase, fin_remate, completa))

    return header + "\n".join(events) + "\n"


# ---------------------------------------------------------------------------
# Barras de cine que entran con el b-roll
# ---------------------------------------------------------------------------
def _entering_bars(
    alto: int = 165,
    pasos: int = 14,
    inicio: float | None = None,
    dur: float = 0.8,
) -> list[str]:
    """Letterbox que arranca a CERO y se cierra al entrar el primer paisaje.

    El gancho es una cara hablando: taparlo con barras desde el fotograma 1
    no marca nada y encima recorta el encuadre justo donde importa. Las
    barras entran cuando cambia el plano —que es donde el ojo pide el corte—
    y ahí sí leen como "esto es una película".

    Va en PASOS con `enable` en vez de una expresión continua porque
    `drawbox` NO evalúa `x/y/w/h` por fotograma: su variable `t` es el GROSOR,
    no el tiempo, así que una expresión con `t` se evalúa mal y el filtro
    acaba pintando el frame entero de negro (comprobado). `enable` sí se
    evalúa por fotograma, así que los escalones dan un cierre que se lee
    como continuo.
    """
    if inicio is None:
        # Justo cuando entra el primer paisaje (gancho + su transición).
        inicio = config.HOOK_DUR + 0.35
    filtros: list[str] = []
    paso_dur = dur / pasos
    for i in range(pasos):
        h = round(alto * (i + 1) / pasos)
        if h <= 0:
            continue
        t0 = inicio + i * paso_dur
        if i == pasos - 1:
            # El último escalón (barra completa) se queda hasta el final.
            ventana = f":enable='gte(t,{t0:.3f})'"
        else:
            ventana = f":enable='between(t,{t0:.3f},{t0 + paso_dur:.3f})'"
        filtros.append(
            f"drawbox=x=0:y=0:w={config.TARGET_W}:h={h}:color=black:t=fill{ventana}"
        )
        filtros.append(
            f"drawbox=x=0:y={config.TARGET_H - h}:w={config.TARGET_W}:h={h}"
            f":color=black:t=fill{ventana}"
        )
    return filtros


# ---------------------------------------------------------------------------
# Registro de presets
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class StylePreset:
    key: str
    label: str
    build_ass: Callable[[list[dict], "StylePreset"], str]
    # Overrides del filtro de vídeo "película" base (vignette angle, extra
    # de eq como gamma_r/gamma_b, filtro de ruido/dust propio, y filtros
    # extra aplicados DESPUÉS de quemar los subtítulos, ej. letterbox).
    vignette_angle: str = "PI/4.2"
    eq_extra: dict = field(default_factory=dict)  # ej. {"gamma_r": 1.06, "gamma_b": 0.94}
    noise_filter_override: str | None = None  # None = usa el ruido base con jitter
    post_subtitle_filters: list[str] = field(default_factory=list)
    # Grading cinematográfico que no cabe en `eq` (colorbalance, curves…).
    # Se aplica ANTES de quemar los subtítulos, para que el texto no se tiña.
    pre_subtitle_filters: list[str] = field(default_factory=list)
    # Override de la transición entre paisajes: (tipo_xfade, duración_base).
    # None = usa `config.TRANSITION_LANDSCAPE`.
    transition_landscape: tuple[str, float] | None = None

    # --- Efectos "de cine" (repartidos entre estilos a propósito, para que
    # cada ciclo tenga una personalidad reconocible) ------------------------
    # Zoom lento tipo Ken Burns sobre los paisajes: fracción total que se
    # acerca (o aleja) a lo largo del clip. 0 = imagen quieta. Es lo que hace
    # que el plano "respire" en vez de parecer una foto fija.
    ken_burns: float = 0.0
    # Amplitud del vaivén de la viñeta (0 = fija).
    vignette_breathe: float = 0.0
    # Nº de destellos cálidos tipo fuga de luz a lo largo del vídeo.
    light_leaks: int = 0
    # Nº de rayaduras verticales tipo proyector viejo.
    film_scratches: int = 0
    # Nº de LÁMINAS de polvo superpuestas (cada una son ~130 motas que van
    # a la deriva, entrando y saliendo del encuadre). 0 = sin polvo.
    #
    # Por defecto 1: el operador quiere el polvo de celuloide en TODOS los
    # estilos, no solo en los "sucios" — es lo que tienen en común los vídeos
    # que le funcionan. Los estilos que quieran más denso lo suben.
    film_specks: int = 1
    # Viñeta y grano de la base "película". Se pueden apagar ENTEROS para los
    # estilos limpios, que solo quieren el color (ver `_LIMPIO`).
    vignette: bool = True
    film_grain: bool = True
    # Multiplicador de saturación sobre `config.EQ_BASE_SATURATION`. Se usa
    # esto en vez de meter `saturation` en `eq_extra` porque `eq_extra` PISA
    # el valor y se llevaría por delante el jitter anti-huella.
    saturation_mul: float = 1.0
    # Encaja el vídeo en un CUADRADO con esquinas redondeadas centrado sobre
    # negro (estilo de los vídeos de reflexión que funcionan en TikTok).
    square_frame: bool = False
    # Tipografía propia del estilo. `font_name` es el nombre de FAMILIA que
    # lee libass (no el del fichero) y `fonts_dir` la carpeta donde buscarla.
    # None = la global de config (DejaVu Sans del sistema).
    font_name: str | None = None
    fonts_dir: str | None = None


# ---------------------------------------------------------------------------
# Base común a TODOS los estilos
# ---------------------------------------------------------------------------
# Decisión del operador tras ver la muestra: entre un ciclo y otro solo debe
# cambiar la TIPOGRAFÍA. Nada de un grade cálido aquí y otro azulado allá, ni
# fundidos a blanco en unos y disoluciones en otros — eso hacía que la cuenta
# pareciera de cinco personas distintas.
#
# Los valores son los del antiguo "Película vieja", que es el look que validó
# en vídeo: paisaje EN COLOR, apenas oscurecido, con viñeta cerrada y la
# suciedad de celuloide encima.
_BASE = dict(
    vignette_angle="PI/3.2",
    eq_extra={"gamma": 0.94, "contrast": 1.06},
    transition_landscape=("fadeblack", 1.05),
    film_specks=2,
    film_scratches=4,
    noise_filter_override="noise=alls=10:allf=t+u",
    ken_burns=0.13,
    vignette_breathe=0.14,
)

# Base de las versiones LIMPIAS (A2, B2, C2): solo el filtro de color, las
# transiciones y los textos. Nada de efectos por pantalla — fuera el polvo de
# celuloide, las rayaduras, el grano y la viñeta.
#
# Nació para los cuadrados G y H; cuando se retiraron (no viralizaban), su
# filtro se quedó, que era lo bueno que tenían.
#
# El color sube pero se queda REALISTA: se deja el contraste base (1.14, que
# `_BASE` bajaba a 1.06) y se sube la saturación un 12% con `saturation_mul`,
# NO metiéndola en `eq_extra` — ahí pisaría el jitter que evita que todos los
# vídeos salgan con el grado idéntico.
#
# También se quita el Ken Burns: los paisajes ya son vídeo y se mueven solos,
# así que el zoom lento solo añadía un efecto encima de lo que se pidió dejar.
_LIMPIO = dict(
    # Bordes oscurecidos, como la referencia que pasó el operador: el centro
    # queda claro y las esquinas caen. Es LO ÚNICO que se recupera de la base
    # sucia — ni polvo, ni rayaduras, ni grano. Fija, sin vaivén: el latido de
    # `_BASE` es de "película vieja" y aquí desentona.
    vignette=True,
    vignette_angle="PI/3.6",
    film_grain=False,
    film_specks=0,
    film_scratches=0,
    ken_burns=0.0,
    vignette_breathe=0.0,
    saturation_mul=1.12,
    # Sin `gamma`/`contrast` que oscurezcan: los de `config` ya abren la
    # imagen (gamma 1.08, brillo 0.06) y es lo que da el aire limpio.
    eq_extra={},
    # La transición NO se toca: es de lo que el operador pidió conservar.
    transition_landscape=("fadeblack", 1.05),
)

STYLE_PRESETS: dict[str, StylePreset] = {
    # --- Los tres de siempre, con la suciedad de celuloide ---
    "classic": StylePreset(
        key="classic", label="A · Clásico", build_ass=build_ass_classic, **_BASE,
    ),
    "reveal": StylePreset(
        key="reveal", label="B · Frases", build_ass=build_ass_frases,
        font_name="Playfair Display Black", fonts_dir=bundled_fonts_dir(), **_BASE,
    ),
    "cinematic": StylePreset(
        key="cinematic", label="C · Karaoke", build_ass=build_ass_cinematic, **_BASE,
    ),
    # --- Los mismos tres, LIMPIOS ---
    # Misma tipografía y mismo movimiento de subtítulo que su original: lo
    # único que cambia es el filtro. Sin polvo, sin rayaduras, sin grano y sin
    # viñeta, y con el color claro y saturado que el operador validó en los
    # cuadrados. A pantalla completa: el marco cuadrado era de G/H, que se
    # retiraron.
    "classic_claro": StylePreset(
        key="classic_claro", label="A2 · Clásico claro",
        build_ass=build_ass_classic, **_LIMPIO,
    ),
    "reveal_claro": StylePreset(
        key="reveal_claro", label="B2 · Frases claro",
        build_ass=build_ass_frases,
        font_name="Playfair Display Black", fonts_dir=bundled_fonts_dir(), **_LIMPIO,
    ),
    "cinematic_claro": StylePreset(
        key="cinematic_claro", label="C2 · Karaoke claro",
        build_ass=build_ass_cinematic, **_LIMPIO,
    ),
}


# Orden de rotación automática cuando el operador no elige estilo por ronda.
STYLE_ORDER = [
    "classic", "reveal", "cinematic",
    "classic_claro", "reveal_claro", "cinematic_claro",
]


def get_style_for_round(round_idx: int) -> StylePreset:
    """`round_idx` es 1-based (ronda 1, 2, 3…). Rota por `STYLE_ORDER`."""
    key = STYLE_ORDER[(round_idx - 1) % len(STYLE_ORDER)]
    return STYLE_PRESETS[key]


def resolve_style(round_idx: int, round_styles: list[str] | None) -> StylePreset:
    """Estilo de una ronda: el elegido por el operador, o la rotación.

    `round_styles[i]` es el estilo de la ronda i+1. Si la lista es más corta
    que el número de rondas, las rondas sobrantes vuelven a la rotación
    automática — así elegir 2 estilos no rompe una tanda de 5 rondas.
    """
    if round_styles:
        idx = round_idx - 1
        if 0 <= idx < len(round_styles):
            key = (round_styles[idx] or "").strip()
            if key in STYLE_PRESETS:
                return STYLE_PRESETS[key]
    return get_style_for_round(round_idx)


def distribute_styles(total: int, pool: list[str] | None) -> list[str]:
    """Reparte `total` vídeos entre los estilos elegidos, a partes iguales.

    Sustituye al reparto "por ronda", que ataba el estilo al número de audios:
    con 25 vídeos y 8 audios salían 4 rondas, así que 2 de los 6 estilos no se
    usaban NUNCA por mucho que el operador los quisiera.

    Con 25 vídeos y 6 estilos salen 5,4,4,4,4,4 (los primeros se llevan el
    resto). Se devuelve INTERCALADO, no en bloques: si el proceso se corta a
    medias quedan vídeos de todos los estilos, no solo de los primeros.
    """
    keys = [k for k in (pool or []) if k in STYLE_PRESETS]
    if not keys:
        keys = list(STYLE_ORDER)
    total = max(0, int(total))
    return [keys[i % len(keys)] for i in range(total)]


def style_choices() -> list[dict]:
    """Estilos disponibles para el selector de la UI, en orden de rotación."""
    return [
        {"key": k, "label": STYLE_PRESETS[k].label}
        for k in STYLE_ORDER
        if k in STYLE_PRESETS
    ]
