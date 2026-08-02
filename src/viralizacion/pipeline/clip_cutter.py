"""Saca clips de ~1 minuto de un audio largo de YouTube.

El operador encuentra charlas de 3-10 minutos del mismo ponente que empiezan
distinto a las que ya tiene. De ahí no sirve el audio entero: hay que encontrar
**dónde arranca cada idea con gancho y dónde cierra**, que es justo lo que no
se puede hacer con reglas de silencios.

Cómo:
1. Whisper (local, ya cacheado) da la transcripción con timings por palabra.
2. Gemini lee esa transcripción con marcas de tiempo y propone los cortes. Va
   con la key FREE, así que el Programa 4 sigue sin gastar un céntimo.
3. Los cortes se **ajustan a un silencio real** del fichero: Gemini razona
   sobre el texto y clava el punto ±0.5s, pero cortar en mitad de una sílaba
   se oye fatal. `silencedetect` decide el fotograma exacto.

La propuesta se guarda y NO se corta nada hasta que el operador elige: un clip
mal cortado no se detecta hasta que el vídeo está montado y subido.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from src.viralizacion import config

OnLog = Callable[[str], None]


def _noop(_: str) -> None:
    return None


# Duraciones. Lo que retiene es el minuto largo, pero el suelo es 50s: con 55
# se perdió el cierre de una charla ("La vida no es para temerla, es para
# vivirla") porque el tramo daba 54. Se apunta a 60-90 desde el prompt; esto
# es solo el mínimo por debajo del cual no vale la pena. Se valida DESPUÉS de
# ajustar a silencios, porque el ajuste puede recortar unas décimas.
MIN_CLIP_S = 50.0
MAX_CLIP_S = 110.0

# Tope solo para el caso de quedarse con la cola del audio. Se permite pasar de
# 110 porque la alternativa es tirar el remate de la charla, y el operador
# prefiere alargar: cuanto más aguanta el clip, más retención.
MAX_ESTIRADO_S = 125.0

# Margen que se le deja al ajuste a silencio para buscar alrededor del punto
# que dio Gemini. Más de 1.5s y se comería palabras de la idea.
SNAP_VENTANA_S = 1.5

# Separación mínima entre el final de un clip y el arranque del siguiente. Un
# clip que empieza 0.2s después de acabar el anterior no es un clip nuevo: es
# la misma frase partida. Pasó tal cual — uno cerraba en "...sin contemplaciones
# con crudeza" y el siguiente arrancaba en "con crudeza y aceptar lo que venga".
SEPARACION_MIN_S = 2.0

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "clip_cutter.md"


@dataclass
class ClipPropuesto:
    inicio: float
    fin: float
    gancho: str
    tema: str
    porque: str
    # Últimas palabras del clip tal cual se oyen. Igual que `gancho`, sirve
    # para clavar el corte donde de verdad cierra la idea.
    cierre: str = ""

    @property
    def duracion(self) -> float:
        return max(0.0, self.fin - self.inicio)


# ---------------------------------------------------------------------------
# 1. Transcripción → texto con marcas de tiempo
# ---------------------------------------------------------------------------
def transcripcion_marcada(words: list[dict], cada_s: float = 5.0) -> str:
    """Texto corrido con un `[mm:ss.d]` cada `cada_s` segundos.

    Se marca por tiempo y no por palabra porque un timestamp pegado a cada
    palabra multiplica por cinco los tokens y el modelo pierde el hilo de lo
    que se está contando, que es lo único que tiene que juzgar.
    """
    partes: list[str] = []
    siguiente = 0.0
    for w in words:
        inicio = float(w.get("start") or 0.0)
        if inicio >= siguiente:
            partes.append(f"\n[{int(inicio // 60):02d}:{inicio % 60:04.1f}] ")
            siguiente = inicio + cada_s
        partes.append(str(w.get("word") or "").strip())
    return " ".join(p for p in partes if p).replace("\n ", "\n")


# ---------------------------------------------------------------------------
# 2. Gemini propone los cortes
# ---------------------------------------------------------------------------
def _parse_respuesta(raw: str, duracion: float) -> list[ClipPropuesto]:
    """JSON del modelo → clips saneados. Descarta lo que no cuadre.

    El modelo acierta el contenido pero se inventa décimas: hay que recortar a
    la duración real y tirar lo que se salga de rango antes de enseñárselo a
    nadie.
    """
    texto = (raw or "").strip()
    # Por si cuela un ```json ... ``` pese a pedirle que no.
    if texto.startswith("```"):
        texto = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", texto).strip()
    try:
        doc = json.loads(texto)
    except json.JSONDecodeError:
        return []

    salida: list[ClipPropuesto] = []
    for c in (doc.get("clips") or []) if isinstance(doc, dict) else []:
        try:
            inicio = max(0.0, float(c.get("inicio")))
            fin = min(duracion, float(c.get("fin")))
        except (TypeError, ValueError):
            continue
        if fin - inicio < MIN_CLIP_S:
            continue
        if fin - inicio > MAX_CLIP_S:
            fin = inicio + MAX_CLIP_S
        salida.append(ClipPropuesto(
            inicio=round(inicio, 1),
            fin=round(fin, 1),
            gancho=str(c.get("gancho") or "").strip()[:200],
            tema=str(c.get("tema") or "").strip()[:80],
            porque=str(c.get("porque") or "").strip()[:200],
            cierre=str(c.get("cierre") or "").strip()[:200],
        ))

    # Sin solapes NI clips pegados: el modelo a veces devuelve dos que comparten
    # 10s (el mismo trozo saldría en dos vídeos, justo lo que se evita con todo
    # el banco de candidatos) o uno que arranca donde acaba el anterior, que es
    # la misma frase partida en dos.
    salida.sort(key=lambda c: c.inicio)
    return _sin_pegados(salida)


def _sin_pegados(clips: list[ClipPropuesto]) -> list[ClipPropuesto]:
    limpios: list[ClipPropuesto] = []
    for c in sorted(clips, key=lambda x: x.inicio):
        if limpios and c.inicio < limpios[-1].fin + SEPARACION_MIN_S:
            continue
        limpios.append(c)
    return limpios


def _huecos(clips: list[ClipPropuesto], duracion: float) -> list[tuple[float, float]]:
    """Tramos sin usar de al menos `MIN_CLIP_S`, en orden."""
    libres: list[tuple[float, float]] = []
    cursor = 0.0
    for c in sorted(clips, key=lambda x: x.inicio):
        if c.inicio - cursor >= MIN_CLIP_S:
            libres.append((cursor, c.inicio))
        cursor = max(cursor, c.fin)
    if duracion - cursor >= MIN_CLIP_S:
        libres.append((cursor, duracion))
    return libres


def _pedir(system: str, user: str, duracion: float) -> list[ClipPropuesto]:
    from src.tiktok_shop.api import gemini

    raw = gemini.generate_text(system, user, expect_json=True, temperature=0.15)
    return _parse_respuesta(raw, duracion)


def proponer(
    words: list[dict], duracion: float, *, on_log: OnLog | None = None,
) -> list[ClipPropuesto]:
    """Pide a Gemini los cortes. Lista vacía si no hay nada aprovechable.

    Va en DOS pasadas. En la primera el modelo tiende a quedarse con el clip
    más evidente y dar el audio por terminado: en una charla de 3 minutos sacó
    uno de 99s y dejó los 74 finales sin mirar, con dos ganchos buenos dentro.
    Así que si queda un hueco de 50s o más, se le vuelve a preguntar SOLO por
    ese tramo. Sale gratis (key FREE) y es lo que da variedad de arranques,
    que es justo para lo que existe esto.
    """
    log = on_log or _noop
    system = _PROMPT_PATH.read_text(encoding="utf-8")
    marcada = transcripcion_marcada(words)

    log("[clip_cutter] pidiendo cortes a Gemini…")
    clips = _pedir(
        system,
        f"Duración total del audio: {duracion:.1f} segundos.\n\n"
        f"Transcripción:\n{marcada}",
        duracion,
    )
    log(f"[clip_cutter] 1ª pasada: {len(clips)} clip(s)")

    libres = _huecos(clips, duracion)
    if libres:
        tramos = ", ".join(f"{a:.1f}s-{b:.1f}s" for a, b in libres)
        log(f"[clip_cutter] quedan {len(libres)} tramo(s) sin usar ({tramos}) — 2ª pasada")
        extra = _pedir(
            system,
            f"Duración total del audio: {duracion:.1f} segundos.\n\n"
            f"Ya se han elegido estos trozos y NO se pueden repetir:\n"
            + "\n".join(f"- {c.inicio:.1f}s a {c.fin:.1f}s ({c.tema})" for c in clips)
            + f"\n\nBusca AHORA clips solo dentro de estos tramos libres: {tramos}.\n"
            f"Si un tramo libre da para un clip de 50s o más que arranque con "
            f"gancho propio, devuélvelo. Si no da, devuelve la lista vacía.\n"
            f"NO fuerces un clip para rellenar: si el tramo libre empieza a "
            f"mitad de una frase o de una idea ya contada, no vale — devolver "
            f"la lista vacía es la respuesta correcta.\n\n"
            f"Transcripción completa:\n{marcada}",
            duracion,
        )
        # Solo lo que cae de verdad en un hueco: si el modelo se sale, sería
        # un solape con un clip ya aceptado y el mismo trozo saldría dos veces.
        nuevos = [
            c for c in extra
            if any(a - 0.5 <= c.inicio and c.fin <= b + 0.5 for a, b in libres)
        ]
        log(f"[clip_cutter] 2ª pasada: {len(nuevos)} clip(s) más")
        clips = _sin_pegados(clips + nuevos)

    log(f"[clip_cutter] {len(clips)} clip(s) propuestos")
    return clips


# ---------------------------------------------------------------------------
# 3. Alinear el arranque con el gancho que declara el modelo
# ---------------------------------------------------------------------------
def _plano(txt: str) -> list[str]:
    """Palabras en minúsculas, sin signos ni acentos, para comparar."""
    import unicodedata

    sin = unicodedata.normalize("NFKD", txt or "")
    sin = "".join(c for c in sin if not unicodedata.combining(c))
    return [w for w in re.split(r"[^a-z0-9]+", sin.lower()) if w]


# Cuánto se le deja mover el arranque respecto de lo que dijo el modelo. Más
# que esto y ya no estaríamos corrigiendo una entradilla, sino eligiendo otro
# trozo distinto.
VENTANA_GANCHO_S = 25.0

# Aire antes de la primera palabra para no comerse el primer fonema.
COLCHON_GANCHO_S = 0.12

# Y un poco de aire después de la última, para que no se corte en seco.
COLA_CIERRE_S = 0.25

# Despedidas de plató. Estos monólogos SIEMPRE acaban así ("Buenas noches",
# "Hasta mañana") y detrás vienen aplausos: quedarse con la cola del audio
# metía las dos cosas. Se recortan solo si están al FINAL del todo.
_DESPEDIDAS = {
    "buenas", "noches", "tardes", "dias", "buenos", "hasta", "manana",
    "luego", "gracias", "muchas", "adios", "chao", "nos", "vemos",
}


def alinear_con_gancho(
    clips: list[ClipPropuesto], words: list[dict], *, on_log: OnLog | None = None,
) -> tuple[list[ClipPropuesto], set[int]]:
    """Empieza el clip en la primera palabra del `gancho` que declara el modelo.

    El modelo describe bien POR DÓNDE engancha pero luego da un `inicio` unos
    segundos antes, incluyendo la entradilla de programa: decía que el gancho
    era "¿qué fácil es dar consejos…" y arrancaba en "Esta noche va de
    consejos porque…". Como el texto del gancho sí es fiable, se busca en los
    timings de Whisper y manda ese punto.

    Devuelve también qué clips quedaron fijados, para que el ajuste a silencio
    no vuelva a arrastrar el arranque hacia atrás.
    """
    log = on_log or _noop
    planas = [(_plano(str(w.get("word") or "")), float(w.get("start") or 0.0)) for w in words]
    secuencia = [(p[0], t) for p, t in planas if p]  # una palabra por entrada

    salida: list[ClipPropuesto] = []
    fijos: set[int] = set()
    for idx, c in enumerate(clips):
        objetivo = _plano(c.gancho)[:5]
        if len(objetivo) < 3:
            salida.append(c)
            continue

        encontrado: float | None = None
        for i in range(len(secuencia) - len(objetivo) + 1):
            t = secuencia[i][1]
            if abs(t - c.inicio) > VENTANA_GANCHO_S:
                continue
            if [w for w, _ in secuencia[i:i + len(objetivo)]] == objetivo:
                encontrado = t
                break

        if encontrado is None or abs(encontrado - c.inicio) < 0.2:
            salida.append(c)
            continue

        nuevo = round(max(0.0, encontrado - COLCHON_GANCHO_S), 2)
        if c.fin - nuevo < MIN_CLIP_S:
            log(f"[clip_cutter] {c.tema!r}: el gancho real dejaría {c.fin - nuevo:.0f}s, se deja como estaba")
            salida.append(c)
            continue

        log(f"[clip_cutter] {c.tema!r}: arranque {c.inicio:.1f}s → {nuevo:.1f}s (primera palabra del gancho)")
        salida.append(ClipPropuesto(
            inicio=nuevo, fin=c.fin, gancho=c.gancho, tema=c.tema,
            porque=c.porque, cierre=c.cierre,
        ))
        fijos.add(idx)
    return salida, fijos


def alinear_con_cierre(
    clips: list[ClipPropuesto], words: list[dict], *, on_log: OnLog | None = None,
) -> tuple[list[ClipPropuesto], set[int]]:
    """Termina el clip donde acaban las palabras de `cierre` que declara el modelo.

    Simétrico a `alinear_con_gancho`, y por el mismo motivo: el modelo sabe
    dónde cierra la idea pero el número que da se queda corto. Uno acabó en
    "sabes que te estás engañando **y**" — el remate ("...y que la suerte te dio
    una oportunidad") venía dos segundos después. Y el ajuste a silencio no
    salva eso: ahí hay una pausa de verdad, es una respiración a mitad de frase.
    """
    log = on_log or _noop
    secuencia = [
        (_plano(str(w.get("word") or "")), float(w.get("start") or 0.0),
         float(w.get("end") or w.get("start") or 0.0))
        for w in words
    ]
    secuencia = [(p[0], ini, fin) for p, ini, fin in secuencia if p]

    salida: list[ClipPropuesto] = []
    fijos: set[int] = set()
    for idx, c in enumerate(clips):
        objetivo = _plano(c.cierre)[-5:]
        if len(objetivo) < 3:
            salida.append(c)
            continue

        # Se busca en TODO el audio, no alrededor del `fin` declarado: el
        # modelo da los dos datos por separado y no siempre cuadran. En uno
        # decía que cerraba en "…la suerte te dio una oportunidad" (1:04) y
        # ponía `fin` en 1:41, a mitad de otra frase. El texto es el fiable;
        # el número solo desempata si hay varias apariciones.
        candidatos: list[float] = []
        for i in range(len(secuencia) - len(objetivo) + 1):
            if [w for w, _, _ in secuencia[i:i + len(objetivo)]] == objetivo:
                candidatos.append(secuencia[i + len(objetivo) - 1][2])

        validos = [
            t for t in candidatos
            if MIN_CLIP_S <= (t + COLA_CIERRE_S) - c.inicio <= MAX_CLIP_S
        ]
        encontrado = min(validos, key=lambda t: abs(t - c.fin)) if validos else None

        if encontrado is None or abs(encontrado - c.fin) < 0.2:
            salida.append(c)
            continue

        nuevo_fin = round(encontrado + COLA_CIERRE_S, 2)

        log(f"[clip_cutter] {c.tema!r}: final {c.fin:.1f}s → {nuevo_fin:.1f}s (última palabra del cierre)")
        salida.append(ClipPropuesto(
            inicio=c.inicio, fin=nuevo_fin, gancho=c.gancho, tema=c.tema,
            porque=c.porque, cierre=c.cierre,
        ))
        fijos.add(idx)
    return salida, fijos


def _fin_hablado(words: list[dict]) -> float:
    """Fin de la última palabra que NO es despedida.

    Sin esto, quedarse con la cola del audio significaba acabar en "…lo que te
    hace feliz. **Buenas noches**" y nueve segundos de aplausos.
    """
    utiles = [w for w in words if _plano(str(w.get("word") or ""))]
    i = len(utiles) - 1
    # Como mucho seis palabras de despedida: más allá ya sería contenido.
    tope = max(0, len(utiles) - 6)
    while i >= tope and _plano(str(utiles[i].get("word") or ""))[0] in _DESPEDIDAS:
        i -= 1
    if i < 0:
        return 0.0
    w = utiles[i]
    return float(w.get("end") or w.get("start") or 0.0)


def estirar_hasta_el_final(
    clips: list[ClipPropuesto], duracion: float,
    *, words: list[dict] | None = None,
    fines_fijos: set[int] | None = None, on_log: OnLog | None = None,
) -> list[ClipPropuesto]:
    """Si la cola que sobra no da para otro clip, se la queda el último.

    El remate de un monólogo es lo mejor que tiene ("Entre lo que está bien y lo
    que está mal, elige lo que te hace feliz") y se estaba quedando fuera: 41
    segundos sueltos al final, que no llegan al mínimo para ser un clip propio y
    tampoco los recogía nadie. Solo se estira si cabe dentro del máximo.

    NO se estira si el modelo ya dijo dónde cierra ese clip: hacerlo colaba la
    despedida del plató ("…elige lo que te hace feliz. **Buenas noches**").
    """
    if not clips:
        return clips
    log = on_log or _noop
    if (len(clips) - 1) in (fines_fijos or set()):
        return clips
    # No hasta el final del FICHERO, sino hasta la última palabra que importa:
    # detrás hay despedida y aplausos.
    tope = duracion
    if words:
        hablado = _fin_hablado(words)
        if hablado > 0:
            tope = min(duracion, round(hablado + COLA_CIERRE_S, 2))
    ultimo = clips[-1]
    cola = tope - ultimo.fin
    if cola <= 0.5 or cola >= MIN_CLIP_S:
        return clips
    if tope - ultimo.inicio > MAX_ESTIRADO_S:
        return clips
    log(f"[clip_cutter] {ultimo.tema!r}: +{cola:.0f}s hasta el final (la cola sola no daba un clip)")
    return clips[:-1] + [ClipPropuesto(
        inicio=ultimo.inicio, fin=round(tope, 2), gancho=ultimo.gancho,
        tema=ultimo.tema, porque=ultimo.porque, cierre=ultimo.cierre,
    )]


# ---------------------------------------------------------------------------
# 4. Ajuste a silencio real
# ---------------------------------------------------------------------------
def _silencios(path: Path, noise_db: int = -32, min_dur: float = 0.18) -> list[tuple[float, float]]:
    """`[(silence_start, silence_end), ...]` de todo el fichero."""
    out = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(path),
         "-af", f"silencedetect=noise={noise_db}dB:d={min_dur}", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    tramos: list[tuple[float, float]] = []
    abierto: float | None = None
    for linea in out.stderr.splitlines():
        if "silence_start:" in linea:
            try:
                abierto = float(linea.split("silence_start:")[1].split()[0])
            except (IndexError, ValueError):
                abierto = None
        elif "silence_end:" in linea and abierto is not None:
            try:
                fin = float(linea.split("silence_end:")[1].split()[0])
            except (IndexError, ValueError):
                abierto = None
                continue
            tramos.append((abierto, fin))
            abierto = None
    return tramos


def ajustar_a_silencio(
    clips: list[ClipPropuesto], audio_path: Path, duracion: float,
    *, inicios_fijos: set[int] | None = None,
    fines_fijos: set[int] | None = None, on_log: OnLog | None = None,
) -> list[ClipPropuesto]:
    """Mueve inicio/fin al silencio más cercano, dentro de `SNAP_VENTANA_S`.

    El inicio se lleva al FIN del silencio (justo cuando arranca la voz) y el
    fin al PRINCIPIO del siguiente (justo cuando la voz calla): así el clip no
    empieza con aire muerto ni se corta una palabra por la mitad.

    El ajuste es cosmético — quien decide si el trozo vale es el modelo — así
    que cuando mover los bordes deja el clip unas décimas por debajo del
    mínimo, se recupera estirando en vez de tirar el clip.
    """
    log = on_log or _noop
    tramos = _silencios(audio_path)
    if not tramos:
        log("[clip_cutter] sin silencios detectables — se dejan los cortes tal cual")
        return clips

    arranques = sorted(t[1] for t in tramos)          # dónde vuelve a hablar
    # El final del fichero es un sitio perfectamente válido para acabar, y a
    # menudo el único: sin esto, un clip que llega hasta el final del audio se
    # descartaba por no encontrar silencio al que agarrarse.
    paradas = sorted([t[0] for t in tramos] + [duracion])   # dónde calla

    def mas_cerca(valor: float, candidatos: list[float]) -> float:
        dentro = [c for c in candidatos if abs(c - valor) <= SNAP_VENTANA_S]
        return min(dentro, key=lambda c: abs(c - valor)) if dentro else valor

    fijos = inicios_fijos or set()
    fijos_fin = fines_fijos or set()
    ajustados: list[ClipPropuesto] = []
    for idx, c in enumerate(clips):
        # Un arranque ya alineado con la primera palabra del gancho NO se
        # toca: el silencio más cercano suele estar justo ANTES, y moverlo
        # allí volvería a colar la entradilla que se acaba de quitar.
        inicio = c.inicio if idx in fijos else round(mas_cerca(c.inicio, arranques), 2)
        fin = c.fin if idx in fijos_fin else round(mas_cerca(c.fin, paradas), 2)

        if fin - inicio < MIN_CLIP_S:
            # 1º estirar el final al siguiente sitio donde calla.
            posteriores = [s for s in paradas if s >= inicio + MIN_CLIP_S]
            if posteriores:
                fin = round(min(posteriores), 2)
        if fin - inicio < MIN_CLIP_S and idx not in fijos:
            # 2º retroceder el arranque al silencio anterior. Se pierde un
            # poco de gancho pero se salva el clip.
            anteriores = [a for a in arranques if a <= fin - MIN_CLIP_S]
            if anteriores:
                inicio = round(max(anteriores), 2)
        if fin - inicio < MIN_CLIP_S:
            log(f"[clip_cutter] descartado {c.tema!r}: se queda en {fin - inicio:.1f}s")
            continue

        ajustados.append(ClipPropuesto(
            inicio=inicio, fin=round(min(fin, inicio + MAX_CLIP_S), 2),
            gancho=c.gancho, tema=c.tema, porque=c.porque, cierre=c.cierre,
        ))
    return ajustados


# ---------------------------------------------------------------------------
# 4. Analizar de punta a punta
# ---------------------------------------------------------------------------
def analizar(
    ponente: str, audio_path: Path, *, tmp_dir: Path,
    on_log: OnLog | None = None,
    on_paso: Callable[[float, str], None] | None = None,
) -> list[ClipPropuesto]:
    """Transcribe, propone y ajusta. No escribe ningún MP3.

    `on_paso` va por fases y no por porcentaje real: Whisper no informa de su
    avance, y sin ningún aviso la cola se queda clavada en el 10% varios
    minutos y parece colgada.
    """
    log = on_log or _noop
    paso = on_paso or (lambda _p, _m: None)
    from src.viralizacion.pipeline.ffmpeg_utils import ffprobe_duration
    from src.viralizacion.pipeline.transcriber import transcribe_words

    duracion = ffprobe_duration(audio_path)
    log(f"[clip_cutter] {audio_path.name} · {duracion:.1f}s")
    if duracion < MIN_CLIP_S:
        log("[clip_cutter] el audio ya es más corto que el mínimo — nada que cortar")
        return []

    paso(0.15, f"🎧 Transcribiendo {duracion / 60:.1f} min con Whisper…")
    words = transcribe_words(ponente, audio_path, tmp_dir=tmp_dir, on_log=on_log)

    paso(0.65, "🧠 Buscando dónde empieza y acaba cada idea…")
    clips = proponer(words, duracion, on_log=on_log)

    paso(0.9, f"✂️ Afinando {len(clips)} corte(s)…")
    clips, fijos = alinear_con_gancho(clips, words, on_log=on_log)
    clips, fines_fijos = alinear_con_cierre(clips, words, on_log=on_log)
    clips = ajustar_a_silencio(
        clips, audio_path, duracion,
        inicios_fijos=fijos, fines_fijos=fines_fijos, on_log=on_log,
    )
    clips = estirar_hasta_el_final(
        clips, duracion, words=words, fines_fijos=fines_fijos, on_log=on_log,
    )
    return _sin_despedida(clips, words, on_log=on_log)


def _sin_despedida(
    clips: list[ClipPropuesto], words: list[dict], *, on_log: OnLog | None = None,
) -> list[ClipPropuesto]:
    """Recorta la despedida de plató del último clip, venga de donde venga.

    No basta con controlarlo al estirar la cola: el propio modelo la incluye a
    veces en el `cierre` que declara ("…elige lo que te hace feliz. Buenas
    noches"), y entonces el corte se alinea con ella.
    """
    log = on_log or _noop
    tope = _fin_hablado(words)
    if tope <= 0:
        return clips
    tope = round(tope + COLA_CIERRE_S, 2)
    salida: list[ClipPropuesto] = []
    for c in clips:
        if c.fin <= tope or tope - c.inicio < MIN_CLIP_S:
            salida.append(c)
            continue
        log(f"[clip_cutter] {c.tema!r}: final {c.fin:.1f}s → {tope:.1f}s (fuera la despedida)")
        salida.append(ClipPropuesto(
            inicio=c.inicio, fin=tope, gancho=c.gancho, tema=c.tema,
            porque=c.porque, cierre=c.cierre,
        ))
    return salida


# ---------------------------------------------------------------------------
# 5. Cortar de verdad
# ---------------------------------------------------------------------------
# Prefijo de los clips sacados de una charla larga. Los audios "base" son los
# que el operador recortó a mano; estos los ha propuesto la máquina, y quiere
# poder distinguirlos de un vistazo aunque se elijan igual.
PREFIJO_CLIP = "clip_"


def es_clip(nombre: str) -> bool:
    return nombre.lower().startswith(PREFIJO_CLIP)


def _nombre_libre(carpeta: Path, base: str, i: int) -> Path:
    """`clip_<base>_c1.mp3`, saltando los que ya existan."""
    n = i
    while True:
        p = carpeta / f"{PREFIJO_CLIP}{base}_c{n}.mp3"
        if not p.exists():
            return p
        n += 1


def cortar(
    ponente: str, audio_path: Path, clips: list[ClipPropuesto],
    *, on_log: OnLog | None = None,
) -> list[Path]:
    """Escribe un MP3 por clip en la carpeta de audios del ponente.

    Se re-codifica (no `-c copy`) a propósito: copiando el stream el corte cae
    en el frame MP3 más cercano y se cuela un trocito de la palabra anterior.
    """
    log = on_log or _noop
    destino = config.ponente_audios_folder(ponente)
    destino.mkdir(parents=True, exist_ok=True)
    base = re.sub(r"[^a-zA-Z0-9]+", "_", audio_path.stem).strip("_").lower() or "clip"

    salidas: list[Path] = []
    for i, c in enumerate(clips, start=1):
        out = _nombre_libre(destino, base, i)
        cmd = [
            "ffmpeg", "-y", "-ss", f"{c.inicio:.3f}", "-to", f"{c.fin:.3f}",
            "-i", str(audio_path), "-vn", "-ac", "1",
            "-b:a", config.FFMPEG_AUDIO_BITRATE, str(out), "-loglevel", "error",
        ]
        log("+ " + " ".join(cmd))
        subprocess.run(cmd, check=True)
        log(f"[clip_cutter] {out.name} · {c.duracion:.1f}s · {c.tema}")
        salidas.append(out)
    return salidas


def a_dict(clips: list[ClipPropuesto]) -> list[dict]:
    return [{**asdict(c), "duracion": round(c.duracion, 1)} for c in clips]
