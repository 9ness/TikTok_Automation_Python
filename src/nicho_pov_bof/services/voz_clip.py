"""De qué sexo es la VOZ que trae el clip original.

Los clips de 8s se generan ya con voz. Esa voz dice el sexo del personaje mucho
mejor que la mano: el tono está o no está, mientras que distinguir una mano de
mujer de una lampiña de hombre falla hasta a ojo (por eso `mano.py` acaba
mirando vello y relojes, que es lo único que se ve seguro).

Cómo: se saca el audio a 16 kHz mono con ffmpeg, Silero VAD dice DÓNDE hay voz
—medir el tono sobre música o silencio da basura— y en esos tramos se estima el
tono fundamental por autocorrelación. La mediana decide.

Nunca lanza: si no hay audio, no hay voz o el tono queda en tierra de nadie,
devuelve sexo vacío y quien llama sigue con la mano, como hasta ahora.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Callable

OnLog = Callable[[str], None]


def _noop(_: str) -> None:
    return None


SR = 16000
# Lo que se mide es el TONO (cada cuántas veces por segundo vibran las cuerdas
# vocales), no el volumen: el volumen no dice nada del sexo de quien habla.
#
# El corte no es una raya. Los dos repartos se solapan —hay hombres agudos y
# mujeres graves—, así que solo se decide con el tono cuando está LEJOS del
# solapamiento. La franja de duda es ancha a propósito: 164 Hz no puede decidir
# con la misma seguridad que 110 Hz, y antes lo hacía.
HZ_HOMBRE = 150.0
HZ_MUJER = 195.0
# Dentro de la franja, hacia dónde se inclina. No decide por sí solo: es el
# último recurso, cuando ni escuchar ni la mano han dicho nada.
HZ_MEDIO = (HZ_HOMBRE + HZ_MUJER) / 2
# Rango donde se busca el tono. Fuera de esto no es voz humana hablando, y
# ampliarlo solo mete octavas falsas.
HZ_MIN = 70.0
HZ_MAX = 320.0
# Trozos de 40 ms: bastan dos ciclos del tono más grave y siguen siendo cortos
# para que el tono no cambie dentro del trozo.
VENTANA = int(SR * 0.040)
SALTO = VENTANA // 2
# Con menos tramos medidos no hay mediana que valga: puede ser una sílaba
# suelta o un ruido con forma de tono.
MIN_TRAMOS = 12


def _audio_16k(video: Path) -> "object | None":
    """El audio del clip como numpy float32 mono, o None si no tiene."""
    import numpy as np

    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", str(video), "-vn", "-ac", "1", "-ar", str(SR),
            "-f", "s16le", "-acodec", "pcm_s16le", "-",
        ],
        capture_output=True, timeout=180,
    )
    if proc.returncode != 0 or not proc.stdout:
        return None
    datos = np.frombuffer(proc.stdout, dtype=np.int16).astype("float32") / 32768.0
    return datos if datos.size else None


def _tramos_de_voz(muestras) -> list[tuple[int, int]]:
    """Dónde habla alguien, en muestras. Vacío si no se puede saber."""
    try:
        import torch
        from silero_vad import get_speech_timestamps, load_silero_vad

        modelo = load_silero_vad(onnx=True)
        marcas = get_speech_timestamps(
            torch.from_numpy(muestras), modelo, sampling_rate=SR,
        )
        return [(int(m["start"]), int(m["end"])) for m in marcas]
    except Exception:  # noqa: BLE001
        # Sin VAD se mide sobre todo el audio: peor, pero mejor que nada.
        return []


def _tono(trozo) -> float:
    """Tono fundamental de un trozo, en Hz. 0 si no lo tiene claro.

    Autocorrelación: la voz es periódica, así que la señal se parece a sí misma
    desplazada un periodo. Se busca el pico más alto dentro del rango de voz.
    """
    import numpy as np

    trozo = trozo - float(np.mean(trozo))
    energia = float(np.sqrt(np.mean(trozo ** 2)))
    # Un trozo callado da picos de autocorrelación por puro ruido.
    if energia < 0.01:
        return 0.0
    corr = np.correlate(trozo, trozo, mode="full")[len(trozo) - 1:]
    if corr[0] <= 0:
        return 0.0
    desde, hasta = int(SR / HZ_MAX), min(int(SR / HZ_MIN), len(corr) - 1)
    if hasta <= desde:
        return 0.0
    tramo = corr[desde:hasta]
    pico = int(np.argmax(tramo)) + desde
    # Un pico bajo comparado con el de desplazamiento cero es señal de que no
    # hay periodicidad de verdad: ruido, música o consonantes.
    if corr[pico] < 0.30 * corr[0]:
        return 0.0
    return SR / float(pico)


def de_un_clip(video: Path, *, on_log: OnLog = _noop) -> dict:
    """`{sexo, hz, tramos}` de UN clip. `sexo` vacío = no se puede decir."""
    import numpy as np

    vacio = {"sexo": "", "hz": 0.0, "tramos": 0, "tendencia": ""}
    try:
        muestras = _audio_16k(Path(video))
        if muestras is None:
            on_log(f"[voz_clip] {Path(video).name}: sin audio")
            return vacio

        trozos = _tramos_de_voz(muestras)
        if not trozos:
            trozos = [(0, len(muestras))]

        tonos = []
        for ini, fin in trozos:
            for p in range(ini, max(ini, fin - VENTANA), SALTO):
                hz = _tono(muestras[p:p + VENTANA])
                if hz:
                    tonos.append(hz)
        if len(tonos) < MIN_TRAMOS:
            on_log(
                f"[voz_clip] {Path(video).name}: solo {len(tonos)} tramos con tono, "
                "no me fío"
            )
            return vacio

        hz = float(np.median(tonos))
        if hz <= HZ_HOMBRE:
            sexo = "hombre"
        elif hz >= HZ_MUJER:
            sexo = "mujer"
        else:
            sexo = ""
        tendencia = "hombre" if hz < HZ_MEDIO else "mujer"
        on_log(
            f"[voz_clip] {Path(video).name}: {hz:.0f} Hz en {len(tonos)} tramos "
            f"→ {sexo or f'en duda (tira a {tendencia})'}"
        )
        return {"sexo": sexo, "hz": hz, "tramos": len(tonos), "tendencia": tendencia}
    except Exception as e:  # noqa: BLE001
        on_log(f"[voz_clip] {Path(video).name}: no se pudo medir ({e})")
        return vacio


def detectar(clips: list[Path], *, on_log: OnLog = _noop) -> dict:
    """El sexo de la voz del producto, mirando todos sus clips.

    Manda el PRIMER clip que se pueda medir. Es lo que pidió el operador y
    tiene sentido: los clips son del mismo personaje, así que si uno dice otra
    cosa es que ese está mal medido —o que el generador cambió de voz—, y el
    primero es el que marca cómo empieza el vídeo.
    """
    lecturas = [de_un_clip(Path(c), on_log=on_log) for c in clips]
    utiles = [x for x in lecturas if x["sexo"]]
    if not utiles:
        # Sin veredicto, pero puede haber tono medido: sirve de desempate al
        # final del todo, cuando ni escuchar ni la mano dicen nada.
        medidos = [x for x in lecturas if x.get("tramos")]
        if medidos:
            return {**medidos[0], "sexo": "", "clips": len(clips)}
        return {"sexo": "", "hz": 0.0, "tramos": 0, "tendencia": "", "clips": len(clips)}
    manda = utiles[0]
    distintos = {x["sexo"] for x in utiles}
    if len(distintos) > 1:
        on_log(
            "[voz_clip] los clips no dicen lo mismo "
            f"({', '.join(x['sexo'] for x in utiles)}); mando el primero: {manda['sexo']}"
        )
    return {**manda, "clips": len(clips), "acuerdo": len(distintos) == 1}


_PROMPT_ESCUCHA = """Audio de un vídeo corto de producto donde alguien habla.

Escucha SOLO la voz que habla (ignora música, efectos y ruido de fondo) y dime
si es de HOMBRE o de MUJER.

Si no habla nadie, si no se entiende, o si dudas, responde "" — es preferible a
acertar por casualidad: quien pregunta tiene otra forma de averiguarlo.

Responde solo JSON:
{"sexo": "hombre"|"mujer"|"", "seguridad": "alta"|"media"|"baja"}"""


def _escuchar(clip: Path, *, on_log: OnLog = _noop) -> str:
    """Que Gemini ESCUCHE el clip y diga hombre o mujer. Vacío si no lo tiene claro.

    Es el desempate para la franja donde el tono no decide (165-180 Hz): ahí
    hay hombres agudos y mujeres graves y medir no basta. Un audio de 8s a 16
    kHz mono son ~250 KB, así que va en la propia llamada sin subir nada.
    """
    from src.tiktok_shop.api.gemini import generate_json

    trabajo = Path(tempfile.mkdtemp(prefix="voz_"))
    try:
        wav = trabajo / "voz.wav"
        proc = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(clip), "-vn", "-ac", "1", "-ar", str(SR), str(wav),
            ],
            capture_output=True, timeout=180,
        )
        if proc.returncode != 0 or not wav.is_file():
            return ""
        datos = generate_json(_PROMPT_ESCUCHA, "", audios=[str(wav)]) or {}
        sexo = str(datos.get("sexo") or "").strip().lower()
        if sexo not in ("hombre", "mujer") or datos.get("seguridad") == "baja":
            on_log("[voz_clip] escuchado, pero sin decidirse")
            return ""
        on_log(f"[voz_clip] escuchado: {sexo} (seguridad {datos.get('seguridad')})")
        return sexo
    except Exception as e:  # noqa: BLE001
        on_log(f"[voz_clip] no se pudo escuchar ({e})")
        return ""
    finally:
        import shutil

        shutil.rmtree(trabajo, ignore_errors=True)


def decidir(clips: list[Path], *, on_log: OnLog = _noop) -> dict:
    """El sexo de la voz del vídeo: primero la VOZ del clip, luego la mano.

    Este orden y no el contrario porque la voz es la señal buena. El clip se
    genera hablando, y el tono de quien habla dice el sexo del personaje sin
    lugar a dudas; la mano hay que deducirla de si se ve vello o un reloj, y de
    ahí venían los fallos (una lectura suelta bastaba para poner voz de hombre
    a una mano de mujer).

    Además sale gratis y en local —ffmpeg y numpy—, así que cuando la voz habla
    claro ni siquiera se gasta la llamada a Gemini de la mano.

    Se pregunta por orden, de más fiable a menos, y manda el primero que lo
    tenga claro:

    1. El TONO medido, gratis y en local, pero SOLO fuera de la franja donde
       los dos repartos se solapan (150-195 Hz).
    2. ESCUCHAR el clip con Gemini. Es lo que decide dentro de esa franja.
    3. La MANO, deduciendo por vello o reloj.
    4. Y si nada de eso dice nada, hacia dónde tiraba el tono: 152 Hz no es
       concluyente, pero es más que la voz por defecto.

    Cuando dos fuentes se contradicen gana la de arriba y queda escrito en el
    log — que es justo lo que hay que mirar si un vídeo sale con la voz rara.

    Devuelve lo mismo que `mano.detectar` más `fuente` ("tono", "escucha",
    "mano" o "tono flojo"), para que quien llama trate el error igual.
    """
    voz = detectar(clips, on_log=on_log)
    if voz.get("sexo"):
        return {
            "sexo": voz["sexo"], "votos": 0, "total": 0, "fuente": "tono",
            "pistas": f"voz a {voz.get('hz', 0):.0f} Hz",
        }

    tendencia = str(voz.get("tendencia") or "")
    hz = float(voz.get("hz") or 0)

    # El tono no ha bastado. Antes de mirar la mano —que es deducir el sexo de
    # si hay vello o reloj—, que alguien ESCUCHE: sigue siendo la voz de quien
    # habla, que es la señal buena.
    if clips:
        escuchado = _escuchar(Path(clips[0]), on_log=on_log)
        if escuchado:
            if tendencia and escuchado != tendencia:
                # Se deja escrito: es justo el caso en el que conviene mirar el
                # vídeo si la voz sale rara.
                on_log(
                    f"[voz_clip] el tono ({hz:.0f} Hz) tiraba a {tendencia} pero "
                    f"escuchándolo es {escuchado}; mando lo escuchado"
                )
            return {
                "sexo": escuchado, "votos": 0, "total": 0, "fuente": "escucha",
                "pistas": f"voz escuchada{f' · {hz:.0f} Hz' if hz else ''}",
            }

    from src.nicho_pov_bof.services import mano

    on_log("[voz_clip] la voz del clip no lo aclara; miro la mano")
    det = mano.detectar(clips, on_log=on_log)
    if det.get("sexo"):
        if tendencia and det["sexo"] != tendencia:
            on_log(
                f"[voz_clip] el tono ({hz:.0f} Hz) tiraba a {tendencia} y la mano "
                f"dice {det['sexo']}; mando la mano"
            )
        return {**det, "fuente": "mano"}

    # Nadie lo ha dicho. Si al menos se midió tono, su inclinación es mejor que
    # la voz por defecto: 152 Hz no es concluyente, pero tampoco es nada.
    if tendencia:
        on_log(
            f"[voz_clip] nada concluyente; me quedo con lo que decía el tono "
            f"({hz:.0f} Hz → {tendencia})"
        )
        return {
            "sexo": tendencia, "votos": 0, "total": 0, "fuente": "tono flojo",
            "pistas": f"voz a {hz:.0f} Hz (en la franja de duda)",
        }

    return {**det, "fuente": "mano"}
