"""¿La mano del vídeo es de hombre o de mujer?

El operador elegía la voz abriendo el vídeo y mirando la mano (ancho, vello,
uñas, reloj). Esto lo hace por él: saca varios fotogramas y le pregunta a
Gemini por CADA uno, quedándose con lo que diga la mayoría.

No se le pregunta "¿de quién es esta mano?" sino "¿hay algo que delate a un
hombre?" — reloj, vello marcado, mano muy ancha— y sin eso se da por MUJER. Lo
pidió así el operador y además es lo que funciona: distinguir una mano de mujer
de una de hombre lampiña es difícil hasta mirándolo uno mismo, pero un reloj o
un antebrazo con vello se ven o no se ven.

Tres cosas más que salieron de medirlo, no de suponerlo:

- **Varios fotogramas, no uno.** Con tres juzgados a la vez contestaba "hombre"
  a casi todo: de 12 vídeos de cosmética, once. Mirándolos uno a uno, 6 y 6.
- **Hacen falta DOS fotogramas con la misma señal** para decir hombre. Con uno
  bastaba una sombra o un puño de camisa para equivocarse.
- **La confianza que dice NO sirve de filtro**: daba 95% acertando y 90-95%
  fallando. Lo que se guarda es en cuántos fotogramas se vio la señal, que sí
  distingue el caso claro del dudoso.

Nunca decide sola nada irreversible: el operador ve lo detectado y puede
cambiarlo. Y se guarda para comparar con lo que él elige, que es como sabremos
si algún día se puede quitar el selector.
"""

from __future__ import annotations

import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Callable

OnLog = Callable[[str], None]
_noop: OnLog = lambda _m: None

# Cuántos fotogramas se miran. Con cinco, un plano donde la mano sale movida o
# fuera de cuadro no decide el resultado, y sigue siendo UNA llamada.
FOTOGRAMAS = 8
# Ancho al que se encogen. Estaba en 540 y ahí el VELLO —que es la señal que
# más manda— se perdía: es detalle fino y al encoger queda como ruido. A 960 se
# ve, y sigue siendo una sola llamada.
ANCHO = 960
# Los fotogramas NO se reparten por igual: en estos vídeos la mano entra desde
# abajo y solo está cerca de la cámara en la segunda mitad, así que ahí es
# donde hay que mirar. Repartidos a partes iguales, los primeros salían sin
# mano o con la mano pequeña al fondo, y eso es justo donde no se ve el vello.
# El exponente < 1 empuja los instantes hacia el final.
SESGO_FINAL = 0.75
# Cuando se miran varios clips del mismo producto, cuántos de cada uno.
FOTOGRAMAS_POR_CLIP = 5
# Cuántos fotogramas tienen que enseñar señal de hombre para decir hombre. Por
# debajo de esto se da por mujer: es lo que pidió el operador —"mujer salvo que
# se vea reloj o vello"— y además es lo fiable, porque esas señales o están o
# no están, mientras que distinguir una mano de mujer de una lampiña de hombre
# falla hasta a ojo.
MIN_SENALES = 2
# Cuántos se miran en el segundo intento, cuando en el primero no salió ninguna
# mano. Más y repartidos distinto: la mano entra y sale de plano.
FOTOGRAMAS_REINTENTO = 9

_PROMPT = """Fotogramas de un vídeo vertical de TikTok donde una persona muestra
un producto con la mano.

Mira con atención el DORSO DE LA MANO y el ANTEBRAZO, que es donde está la
señal que importa. Amplía mentalmente esa zona antes de responder: el vello
puede ser fino o claro y aun así estar ahí.

Para CADA fotograma, dime si hay alguna señal CLARA de que la mano o el brazo
sean de un HOMBRE. Señales que cuentan:

- vello visible en el dorso de la mano, en los dedos o en el antebrazo
  (cuenta aunque sea poco denso, mientras se vea que hay pelo)
- reloj de hombre, correa ancha o pulsera gruesa
- mano notablemente ancha, dedos gruesos o nudillos muy marcados
- venas marcadas en el dorso junto a alguna de las anteriores
- uñas cortas y rectas junto a alguna de las anteriores

NO cuentan como señal: que no se le vean las uñas pintadas, que la mano esté
algo sombreada, o que sostenga un producto "de hombre". Ante la duda, NO es
señal: se dará por mujer.

Marca `fuerte` cuando la señal sea de las que no admiten discusión —vello
visible o un reloj/pulsera de hombre—, y déjalo en false cuando sea solo de
proporciones (mano ancha, dedos gruesos), que es opinable.

Los fotogramas pueden ser del MISMO vídeo o de dos clips del mismo producto:
juzga cada uno por separado, sin arrastrar lo que viste en el anterior. En
varios la mano saldrá pequeña o de lejos — ahí pon `hay_mano` en true solo si
puedes ver de verdad la piel del dorso o del antebrazo.

Responde SOLO un JSON con una entrada por fotograma, en orden:
{"fotogramas": [{"hombre": true|false, "fuerte": true|false,
                 "senal": "3-6 palabras o vacío", "hay_mano": true|false}, ...]}

`hay_mano` en false si en ese fotograma no se ve mano ni brazo."""


def _duracion(video: Path) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
            capture_output=True, text=True, check=True,
        )
        return float(out.stdout.strip())
    except Exception:
        return 10.0


def _instantes(n: int, *, sesgo: bool = True) -> list[float]:
    """`n` fracciones del vídeo donde sacar fotograma.

    Con `sesgo` (lo normal) van cargadas hacia el final, que es donde la mano
    está cerca. Sin él se reparten por igual: eso es para el segundo intento,
    cuando no se vio ninguna mano y lo que toca es barrer el vídeo entero.
    """
    return [
        0.12 + 0.85 * (((i + 1) / (n + 1)) ** (SESGO_FINAL if sesgo else 1.0))
        for i in range(n)
    ]


def _sacar_fotogramas(
    video: Path, destino: Path, n: int = FOTOGRAMAS, *, etiqueta: str = "0",
    sesgo: bool = True,
) -> list[str]:
    """Saca `n` fotogramas del vídeo en los instantes de `_instantes`.

    Nunca el primero ni el último: son el arranque y el cierre del plano, y ahí
    la mano entra o sale de cuadro.
    """
    dur = _duracion(video)
    salidas: list[str] = []
    for i, frac in enumerate(_instantes(n, sesgo=sesgo)):
        t = dur * frac
        f = destino / f"mano_{etiqueta}_{i}.jpg"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video),
             "-frames:v", "1", "-vf", f"scale={ANCHO}:-1", str(f)],
            capture_output=True,
        )
        if f.is_file() and f.stat().st_size > 0:
            salidas.append(str(f))
    return salidas


def _fotogramas_de(
    videos: list[Path], destino: Path, *, n_uno: int, n_varios: int,
    sesgo: bool = True,
) -> list[str]:
    """Fotogramas de uno o de varios clips del mismo producto.

    En plazos y en el POV BOF Largo el vídeo son dos clips: mirar solo el
    primero deja fuera la mitad del material, y a veces es en el segundo donde
    la mano se ve de cerca.
    """
    if len(videos) == 1:
        return _sacar_fotogramas(videos[0], destino, n=n_uno, sesgo=sesgo)
    fotos: list[str] = []
    for i, v in enumerate(videos):
        fotos.extend(
            _sacar_fotogramas(v, destino, n=n_varios, etiqueta=str(i), sesgo=sesgo)
        )
    return fotos


def detectar(video: Path | list[Path], *, on_log: OnLog = _noop) -> dict:
    """`{sexo, votos, total, pistas}`. `sexo` vacío si no se ve ninguna mano.

    Acepta UN vídeo o la lista de clips de un mismo producto (plazos y POV BOF
    Largo van en dos clips): se mira material de todos en una sola llamada.

    Si en los primeros fotogramas no sale ninguna mano se reintenta con más,
    repartidos por otros sitios: la mano entra y sale de plano, y quedarse sin
    verla manda el vídeo a la voz por defecto sin haberlo mirado bien. Pasó en
    1 de 17 vídeos con mano de hombre.

    No lanza nunca: si falla ffmpeg o Gemini se devuelve vacío y quien llama
    decide (en el montaje, la voz de mujer, que es la de por defecto).
    """
    from src.tiktok_shop.api.gemini import generate_json

    vacio = {"sexo": "", "votos": 0, "total": 0, "pistas": ""}
    videos = [Path(v) for v in (video if isinstance(video, (list, tuple)) else [video])]
    trabajo = Path(tempfile.mkdtemp(prefix="mano_"))
    try:
        fotos = _fotogramas_de(
            videos, trabajo, n_uno=FOTOGRAMAS, n_varios=FOTOGRAMAS_POR_CLIP,
        )
        if not fotos:
            on_log("[mano] no pude sacar fotogramas del vídeo")
            return vacio
        datos = generate_json(_PROMPT, "", images=fotos)
        lecturas = [x for x in ((datos or {}).get("fotogramas") or []) if x.get("hay_mano")]
        if not lecturas:
            on_log(f"[mano] ninguna mano en {len(fotos)} fotogramas; miro más")
            fotos = _fotogramas_de(
                videos, trabajo,
                n_uno=FOTOGRAMAS_REINTENTO,
                # Por clip, menos: con dos serían 18 imágenes en una llamada.
                n_varios=6,
                # Barrido de todo el vídeo: si no se vio mano donde suele
                # estar, hay que mirar donde no suele.
                sesgo=False,
            )
            datos = generate_json(_PROMPT, "", images=fotos) if fotos else {}
            lecturas = [
                x for x in ((datos or {}).get("fotogramas") or []) if x.get("hay_mano")
            ]
        if not lecturas:
            on_log("[mano] no se ve ninguna mano en el vídeo")
            return vacio
        con_senal = [x for x in lecturas if x.get("hombre")]
        fuertes = [x for x in con_senal if x.get("fuerte")]
        # Dos fotogramas con señal, o UNO si es de las que no admiten discusión
        # (vello o reloj de hombre). El equilibrio no es simétrico a propósito:
        # colar voz de mujer en un vídeo con mano de hombre es el fallo que de
        # verdad se nota, así que ante una señal clara se va a hombre aunque
        # aparezca en un único fotograma; en cambio "mano ancha" —que es
        # opinable— necesita repetirse.
        sexo = (
            "hombre"
            if len(con_senal) >= MIN_SENALES or fuertes
            else "mujer"
        )
        pistas = "; ".join(
            str(x.get("senal") or "") for x in con_senal[:2] if x.get("senal")
        )
        on_log(
            f"[mano] {sexo} · señales de hombre en {len(con_senal)}/{len(lecturas)} "
            f"fotogramas{' · ' + pistas[:50] if pistas else ''}"
        )
        return {
            "sexo": sexo, "votos": len(con_senal), "total": len(lecturas),
            "pistas": pistas[:120],
        }
    except Exception as e:  # noqa: BLE001
        on_log(f"[mano] no se pudo detectar ({e}); sigo con lo que eligió el operador")
        return vacio
    finally:
        import shutil

        shutil.rmtree(trabajo, ignore_errors=True)


def resumen(det: dict) -> str:
    """Una línea para el log y para guardar junto al producto."""
    if not det.get("sexo"):
        return "sin mano detectada"
    return f"{det['sexo']} (señales de hombre en {det.get('votos')}/{det.get('total')})"


__all__ = ["detectar", "resumen", "FOTOGRAMAS"]
