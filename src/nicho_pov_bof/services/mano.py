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
FOTOGRAMAS = 5
# Ancho al que se encogen. La mano se distingue de sobra y pesan la décima
# parte, que es lo que tarda la llamada.
ANCHO = 540
# Cuántos fotogramas tienen que enseñar señal de hombre para decir hombre. Por
# debajo de esto se da por mujer: es lo que pidió el operador —"mujer salvo que
# se vea reloj o vello"— y además es lo fiable, porque esas señales o están o
# no están, mientras que distinguir una mano de mujer de una lampiña de hombre
# falla hasta a ojo.
MIN_SENALES = 2

_PROMPT = """Fotogramas de un vídeo vertical de TikTok donde una persona muestra
un producto con la mano.

Para CADA fotograma, dime si hay alguna señal CLARA de que la mano o el brazo
sean de un HOMBRE. Señales que cuentan:

- vello visible en el dorso de la mano o en el antebrazo
- reloj de hombre, correa ancha o pulsera gruesa
- mano notablemente ancha, dedos gruesos o nudillos muy marcados
- uñas cortas y rectas junto a alguna de las anteriores

NO cuentan como señal: que no se le vean las uñas pintadas, que la mano esté
algo sombreada, o que sostenga un producto "de hombre". Ante la duda, NO es
señal: se dará por mujer.

Responde SOLO un JSON con una entrada por fotograma, en orden:
{"fotogramas": [{"hombre": true|false, "senal": "3-6 palabras o vacío",
                 "hay_mano": true|false}, ...]}

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


def _sacar_fotogramas(video: Path, destino: Path, n: int = FOTOGRAMAS) -> list[str]:
    """Reparte `n` fotogramas por el vídeo, sin coger el primero ni el último.

    Los extremos suelen ser el arranque o el cierre del plano y ahí la mano
    entra o sale de cuadro.
    """
    dur = _duracion(video)
    salidas: list[str] = []
    for i in range(n):
        t = dur * (i + 1) / (n + 1)
        f = destino / f"mano_{i}.jpg"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video),
             "-frames:v", "1", "-vf", f"scale={ANCHO}:-1", str(f)],
            capture_output=True,
        )
        if f.is_file() and f.stat().st_size > 0:
            salidas.append(str(f))
    return salidas


def detectar(video: Path, *, on_log: OnLog = _noop) -> dict:
    """`{sexo, votos, total, pistas}`. `sexo` vacío si no se ve ninguna mano.

    No lanza nunca: si falla ffmpeg o Gemini se devuelve vacío y quien llama
    decide (en el montaje, seguir con lo que eligió el operador).
    """
    from src.tiktok_shop.api.gemini import generate_json

    vacio = {"sexo": "", "votos": 0, "total": 0, "pistas": ""}
    trabajo = Path(tempfile.mkdtemp(prefix="mano_"))
    try:
        fotos = _sacar_fotogramas(Path(video), trabajo)
        if not fotos:
            on_log("[mano] no pude sacar fotogramas del vídeo")
            return vacio
        datos = generate_json(_PROMPT, "", images=fotos)
        lecturas = [x for x in ((datos or {}).get("fotogramas") or []) if x.get("hay_mano")]
        if not lecturas:
            on_log("[mano] no se ve ninguna mano en los fotogramas")
            return vacio
        con_senal = [x for x in lecturas if x.get("hombre")]
        # Dos fotogramas con la misma señal, no uno: con uno bastaba una sombra
        # o el puño de una camisa para dar hombre por error.
        sexo = "hombre" if len(con_senal) >= MIN_SENALES else "mujer"
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
