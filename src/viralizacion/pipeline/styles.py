"""Presets de subtítulo/filtro que rotan por "ronda" (para que las réplicas
se vean distintas si la v1 no viraliza). Registro en `STYLE_PRESETS`, orden
de rotación en `STYLE_ORDER`.

- **A "Clásico"**: línea completa blanca, borde negro, centrada — el estilo
  ya validado por el operador.
- **B "Reveal"**: UNA palabra en pantalla cada vez, cambiando de molde
  tipográfico (`_STACK_MOLDES`) + grano más denso como firma visual.
- **C "Cinemático"**: karaoke por palabra (palabra activa en blanco, resto
  en negro) + grade frío/cálido + viñeta más fuerte + barras de letterbox
  que entran al arrancar el b-roll.
- **D "Teal & Orange"** (texto como C) y **F "Hora dorada"** (texto como B):
  reaprovechan un `build_ass` existente y cambian el grade, la viñeta y la
  transición — son variantes de color.
- **E "Cascada"**: las palabras caen desordenadas por la pantalla
  (`\\pos` por palabra, posición y molde sorteados) sobre un plano con motas
  de polvo negras a la deriva.
- **G "Cuadrado"**: marco cuadrado de esquinas redondeadas sobre fondo negro
  y palabras que se van apilando con tipografía variada.
- **H "Resaltado"**: mismo marco cuadrado, Montserrat ExtraBold en MAYÚSCULAS
  abajo, la frase se va escribiendo y la palabra que suena va en amarillo.

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
# Estilo B — Reveal (una palabra cada vez, tipografía variada)
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
    film_specks: int = 0
    # Encaja el vídeo en un CUADRADO con esquinas redondeadas centrado sobre
    # negro (estilo de los vídeos de reflexión que funcionan en TikTok).
    square_frame: bool = False
    # Tipografía propia del estilo. `font_name` es el nombre de FAMILIA que
    # lee libass (no el del fichero) y `fonts_dir` la carpeta donde buscarla.
    # None = la global de config (DejaVu Sans del sistema).
    font_name: str | None = None
    fonts_dir: str | None = None


STYLE_PRESETS: dict[str, StylePreset] = {
    "classic": StylePreset(
        key="classic",
        label="A · Clásico",
        build_ass=build_ass_classic,
        # Limpio: solo el plano respirando. Es el estilo ya validado.
        ken_burns=0.10,
    ),
    "reveal": StylePreset(
        key="reveal",
        label="B · Reveal",
        build_ass=build_ass_reveal,
        # Firma visual extra: grano/"polvo" más denso que el base (alls=8).
        # NOTA (decisión de diseño, ver VIRALIZACION_MODULE.md): se intentó
        # un overlay de puntos discretos vía `geq` pero resultaba muy lento
        # de renderizar en vídeos largos (~30-60s a 1080x1920x30fps) — se
        # usa como fallback un `noise` bastante más denso/visible que el de
        # Estilo A, que cumple el mismo propósito de "firma" diferenciadora.
        noise_filter_override="noise=alls=14:allf=t+u:c0s=1",
        # Grano fuerte + rayaduras: el más "sucio" y reconocible.
        film_scratches=3,
    ),
    "cinematic": StylePreset(
        key="cinematic",
        label="C · Cinemático",
        build_ass=build_ass_cinematic,
        vignette_angle="PI/3.5",
        eq_extra={"gamma_r": 1.06, "gamma_b": 0.94},
        post_subtitle_filters=_entering_bars(),
        ken_burns=0.12,
        vignette_breathe=0.15,
    ),
    # --- Variantes cinematográficas (D/E/F) -------------------------------
    # Solo cambian el GRADING y la TRANSICIÓN respecto a las anteriores; la
    # posición del subtítulo se deja igual a propósito (decisión del operador:
    # mover el texto entre ciclos perjudica la lectura en el feed).
    "teal_orange": StylePreset(
        key="teal_orange",
        label="D · Teal & Orange",
        build_ass=build_ass_cinematic,
        vignette_angle="PI/3.8",
        # Look de blockbuster: sombras frías, pieles cálidas.
        eq_extra={"gamma_r": 1.10, "gamma_b": 0.90},
        pre_subtitle_filters=["colorbalance=rs=-0.12:bs=0.18:rm=0.06:bm=-0.05"],
        # Disolución suave y larga: encadenado "de cine" en vez de corte a negro.
        transition_landscape=("dissolve", 0.7),
        ken_burns=0.14,
        light_leaks=2,
    ),
    "noir": StylePreset(
        key="noir",
        label="E · Cascada",
        build_ass=build_ass_cascade,
        # Viñeta suave: con el grade oscuro anterior (era blanco y negro) se
        # usaba PI/3.2 y en color dejaba las esquinas casi negras.
        vignette_angle="PI/4.2",
        # Antes este estilo era blanco y negro (`colorchannelmixer`): el
        # operador lo descartó, el paisaje en B/N no vende. Ahora es color
        # con contraste alto y la firma visual la ponen las motas de polvo.
        eq_extra={"gamma": 0.95},
        noise_filter_override="noise=alls=11:allf=t+u",
        # Antes `fadeblack` (era el estilo "cine negro"): en un montaje de
        # planos cortos metía un fogonazo a negro cada pocos segundos. Ahora
        # que es a color, encadenado normal.
        transition_landscape=("fade", 0.5),
        # Sin zoom: quieto, contrastado y sucio de película.
        film_scratches=5,
        film_specks=2,
        vignette_breathe=0.12,
    ),
    "cuadrado": StylePreset(
        key="cuadrado",
        label="G · Cuadrado",
        build_ass=build_ass_stacked,
        square_frame=True,
        # Sin viñeta ni letterbox: el marco negro ya enmarca la imagen, y
        # oscurecer los bordes del cuadrado lo ensuciaría.
        vignette_angle="PI/5.0",
        eq_extra={"gamma_r": 1.04, "gamma_b": 0.97},
        transition_landscape=("dissolve", 0.6),
        ken_burns=0.10,
    ),
    "highlight": StylePreset(
        key="highlight",
        label="H · Resaltado",
        build_ass=build_ass_highlight,
        # Mismo marco que el estilo G, que es el que funciona.
        square_frame=True,
        # Montserrat ExtraBold: es la tipografía de los vídeos de referencia
        # y ya venía en `assets/fonts` (la usa Creator Reward).
        font_name="Montserrat ExtraBold",
        fonts_dir=bundled_fonts_dir(),
        vignette_angle="PI/5.0",
        eq_extra={"gamma_r": 1.02, "gamma_b": 0.99},
        transition_landscape=("dissolve", 0.55),
        ken_burns=0.10,
    ),
    "golden": StylePreset(
        key="golden",
        label="F · Hora dorada",
        build_ass=build_ass_reveal,
        vignette_angle="PI/4.5",
        # Cálido y luminoso, tipo atardecer.
        eq_extra={"gamma_r": 1.12, "gamma_g": 1.02, "gamma_b": 0.88},
        pre_subtitle_filters=["colorbalance=rs=0.10:gs=0.03:bs=-0.10"],
        # Fundido a blanco: rompe visualmente con todos los demás ciclos.
        transition_landscape=("fadewhite", 0.5),
        ken_burns=0.12,
        light_leaks=3,
    ),
}

# Orden de rotación automática cuando el operador no elige estilo por ronda.
STYLE_ORDER = [
    "classic", "reveal", "cinematic", "teal_orange", "noir", "golden",
    "cuadrado", "highlight",
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
