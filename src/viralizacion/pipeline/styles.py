"""3 presets de subtítulo/filtro que rotan por "ronda" (para que las
réplicas se vean distintas si la v1 no viraliza).

- **A "Clásico"** (ronda 1, 4, 7…): línea completa blanca, borde negro,
  centrada — el estilo ya validado por el operador.
- **B "Reveal"** (ronda 2, 5, 8…): las letras aparecen una a una (efecto
  "escritura"), con un glow blanco breve en la última letra revelada.
  + overlay de grano más denso como firma visual extra.
- **C "Cinemático"** (ronda 3, 6, 9…): karaoke por palabra (palabra activa
  en blanco, resto en negro) + grade frío/cálido + viñeta más fuerte +
  barras de letterbox.

Añadir un 4º estilo en el futuro: define un nuevo `StylePreset` en
`STYLE_PRESETS` con su propio `build_ass` — no hay más sitios que tocar
(el runner y el renderer iteran sobre el registro, no hardcodean nombres)."""

from __future__ import annotations

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


def _dialogue(start: float, end: float, text: str) -> str:
    return f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{text}"


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
# Estilo B — Reveal (letra a letra + glow)
# ---------------------------------------------------------------------------
def _line_char_timeline(line: dict) -> tuple[str, list[float]]:
    """Reparte los caracteres de cada palabra uniformemente dentro de su
    ventana [start, end] (timings de Whisper). Devuelve (full_text_sin_ultimo_espacio,
    lista de instantes en que cada carácter queda revelado)."""
    chars: list[str] = []
    times: list[float] = []
    for w in line["words"]:
        word = w["word"]
        n = max(1, len(word))
        dur = max(0.0, w["end"] - w["start"])
        for i, ch in enumerate(word):
            t = w["start"] + dur * (i + 1) / n
            chars.append(ch)
            times.append(t)
        chars.append(" ")
        times.append(w["end"])
    # quita el espacio final sobrante
    if chars and chars[-1] == " ":
        chars.pop()
        times.pop()
    return "".join(chars), times


def build_ass_reveal(lines: list[dict], preset: "StylePreset") -> str:
    """UNA palabra en pantalla cada vez, grande y con glow.

    Antes se revelaba letra a letra acumulando la frase entera: con frases
    largas el texto se hacía diminuto y se leía fatal en el móvil. Mostrar
    una sola palabra a la vez obliga a leerla, aguanta cualquier longitud de
    frase y encaja mejor con el ritmo del audio.
    """
    # Tamaño mayor que el resto de estilos: al haber una sola palabra hay
    # sitio de sobra y el impacto es la gracia del estilo.
    font_size = int(config.SUB_FONTSIZE * 1.35)
    style_line = (
        f"Style: Default,{config.SUB_FONT},{font_size},"
        f"&H00FFFFFF&,&H000000FF&,&H00000000&,&H00000000&,-1,0,0,0,100,100,0,0,1,4,0,5,"
        f"{config.SUB_MARGIN_LR},{config.SUB_MARGIN_LR},0,1"
    )
    header = _ass_header(style_line)
    events: list[str] = []
    # Glow blanco suave alrededor de la palabra activa.
    glow_tag = r"{\bord5\blur5\3c&HFFFFFF&\4c&HFFFFFF&}"

    for ln in lines:
        for w in ln.get("words") or []:
            start = float(w["start"])
            end = float(w["end"])
            # Whisper a veces devuelve palabras de duración ~0; sin un mínimo
            # la palabra parpadearía y no daría tiempo a leerla.
            if end - start < 0.12:
                end = start + 0.12
            events.append(_dialogue(start, end, f"{glow_tag}{w['word']}"))

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
# Estilo G — Cuadrado (palabras que se acumulan, tipografía variada)
# ---------------------------------------------------------------------------
# Cómo salen las palabras. Cada una coge un "molde" distinto para que el
# bloque no parezca un subtítulo corrido sino un montaje hecho a mano, que es
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

    for ln in lines:
        palabras = ln.get("words") or []
        for inicio in range(0, len(palabras), _STACK_MAX):
            grupo = palabras[inicio:inicio + _STACK_MAX]
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
                events.append(_dialogue(ev_start, ev_end, "\\N".join(partes)))

    return header + "\n".join(events) + "\n"


# ---------------------------------------------------------------------------
# Barras de cine que se retiran (transición del gancho al paisaje)
# ---------------------------------------------------------------------------
def _retracting_bars(
    alto: int = 77,
    pasos: int = 14,
    dur: float | None = None,
) -> list[str]:
    """Letterbox que arranca completo y se retira durante el gancho.

    Marca visualmente el paso del gancho al b-roll —que es donde el ojo pide
    un corte— y evita que las barras se coman encuadre durante todo el vídeo.

    Va en PASOS con `enable` en vez de una expresión continua porque
    `drawbox` NO evalúa `x/y/w/h` por fotograma: su variable `t` es el GROSOR,
    no el tiempo, así que una expresión con `t` se evalúa mal y el filtro
    acaba pintando el frame entero de negro (comprobado). `enable` sí se
    evalúa por fotograma, así que 14 escalones de ~0,26s dan una retirada que
    se lee como continua.
    """
    if dur is None:
        # Termina justo al entrar el primer paisaje (gancho + su transición).
        dur = config.HOOK_DUR + 0.6
    filtros: list[str] = []
    paso_dur = dur / pasos
    for i in range(pasos):
        h = round(alto * (1 - i / pasos))
        if h <= 0:
            continue
        t0 = i * paso_dur
        # El último escalón cierra en `dur`; los demás encadenan sin hueco.
        t1 = dur if i == pasos - 1 else (i + 1) * paso_dur
        ventana = f":enable='between(t,{t0:.3f},{t1:.3f})'"
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
    # Encaja el vídeo en un CUADRADO con esquinas redondeadas centrado sobre
    # negro (estilo de los vídeos de reflexión que funcionan en TikTok).
    square_frame: bool = False


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
        noise_filter_override="noise=alls=35:allf=t+u:c0s=1",
        # Grano fuerte + rayaduras: el más "sucio" y reconocible.
        film_scratches=3,
    ),
    "cinematic": StylePreset(
        key="cinematic",
        label="C · Cinemático",
        build_ass=build_ass_cinematic,
        vignette_angle="PI/3.5",
        eq_extra={"gamma_r": 1.06, "gamma_b": 0.94},
        post_subtitle_filters=_retracting_bars(),
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
        label="E · Noir",
        build_ass=build_ass_classic,
        vignette_angle="PI/3.2",
        # Contraste alto y color muy lavado (sin llegar a B/N puro).
        eq_extra={"gamma": 0.95},
        pre_subtitle_filters=["colorchannelmixer=.35:.45:.15:0:.35:.45:.15:0:.35:.45:.20:0"],
        noise_filter_override="noise=alls=18:allf=t+u",
        # Fundido a negro corto y seco, muy de cine negro.
        transition_landscape=("fadeblack", 0.45),
        # Sin zoom: quieto, contrastado y rayado — el más sobrio/dramático.
        film_scratches=5,
        vignette_breathe=0.20,
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
    "classic", "reveal", "cinematic", "teal_orange", "noir", "golden", "cuadrado",
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
