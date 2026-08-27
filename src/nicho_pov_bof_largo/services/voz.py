"""Locución del guion con Fish Audio + nivelado de volumen.

Dos cosas que no son obvias:

1. **La voz se sortea.** El operador solo elige sexo; cuál de las del banco
   suena lo decide el azar, igual que en el Nicho POV BOF con sus mp3 grabados.

2. **La cadena de nivelado NO es la del POV BOF.** Allí se usa `TP=-1.5` con el
   limitador a 0.9 y funciona porque los audios son grabaciones humanas. Con
   una voz de Fish, esos mismos valores dieron **+0,20 dBTP** — o sea recorte
   audible, justo lo que se quiere evitar. Con `TP=-2.0` y 0.89 queda en
   -13,1/-13,6 LUFS con picos en -1,1/-1,6 dBTP: alto y limpio.

3. **Se recortan silencios** (`config.VOZ_SILENCIO`) para que el vídeo no quede
   más largo de la cuenta: fuera el aire muerto del principio/final y las
   pausas internas largas se capan (~0,3s) sin eliminarlas, para que siga
   sonando orgánico. Va primero en la cadena para que el nivelado mida el audio
   ya ajustado.
"""

from __future__ import annotations

import json
import random
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from src.nicho_pov_bof_largo import config

OnLog = Callable[[str], None]
_noop: OnLog = lambda _m: None

# Tarifa del plan de pago de Fish: $15 por millón de BYTES UTF-8. Con el modelo
# gratuito (`s2.1-pro-free`, el de por defecto) no se cobra, pero el consumo se
# registra igual para poder ver el volumen y para que el día que se cambie a
# pago el coste aparezca solo en el panel.
FISH_USD_PER_MILLON_BYTES = 15.0


# Colchón al descartar voces por velocidad. Las cifras de `velocidad_voz` se
# reajustan solas con cada vídeo, así que una voz que hoy cuadra justo puede
# bajar una décima mañana y colarse sin que quepa. Con medio segundo, la que
# entra cabe de verdad.
MARGEN_VOZ_S = 0.5


def elegir_voz(
    sexo: str,
    rng: random.Random | None = None,
    *,
    caracteres: int = 0,
    segundos_max: float = 0.0,
    margen_s: float = MARGEN_VOZ_S,
    on_log: OnLog = _noop,
) -> dict[str, str]:
    """Una voz al azar del banco del sexo pedido.

    Si se dice cuánto texto hay (`caracteres`) y cuánto vídeo cabe
    (`segundos_max`), se descartan las voces que NO quepan: cada una habla a su
    ritmo y la diferencia es enorme —de 14 a 23,6 caracteres por segundo—, así
    que el mismo guion son 15s con una y 25s con otra. Locutar con una lenta un
    guion medido para una media obliga al montaje a estirar el vídeo, y ahí es
    donde se deforma el gesto de la mano.

    Se puede filtrar porque cuando se locuta los clips YA están subidos: se sabe
    cuánto material hay. Antes se sorteaba a ciegas entre todas.

    Se descarta con un COLCHÓN (`margen_s`): las velocidades se reajustan solas
    con cada vídeo montado, así que una voz que cuadra por una décima hoy puede
    no cuadrar mañana.

    Si con el colchón no cabe ninguna se prueba sin él, y si aún así ninguna se
    sortea entre todas: quedarse sin voz sería peor que estirar un poco. Los
    dos escalones se dicen en el log, porque significan que el vídeo va a pedir
    un clip más de lo previsto.
    """
    sexo = (sexo or "").strip().lower()
    if sexo not in config.VOCES:
        raise ValueError(f"sexo debe ser {' o '.join(config.SEXOS)}, recibido: {sexo!r}")
    candidatas = list(config.VOCES[sexo])
    if caracteres > 0 and segundos_max > 0:
        from src.nicho_pov_bof_largo.services import velocidad_voz

        def _caben(tope: float) -> list[dict[str, str]]:
            return [
                v for v in candidatas
                if caracteres / velocidad_voz.caracteres_por_segundo(v["id"]) <= tope
            ]

        con_colchon = _caben(segundos_max - max(0.0, margen_s))
        if con_colchon:
            candidatas = con_colchon
        else:
            justas = _caben(segundos_max)
            if justas:
                on_log(
                    f"[voz] ninguna voz cabe con {margen_s}s de margen en "
                    f"{segundos_max:.1f}s; se sortea entre las {len(justas)} que "
                    "caben justas"
                )
                candidatas = justas
            else:
                on_log(
                    f"[voz] NINGUNA voz cabe: {caracteres} caracteres no entran "
                    f"en {segundos_max:.1f}s. Se sortea entre todas y el montaje "
                    "tendrá que estirar o pedir otro clip."
                )
    return (rng or random).choice(candidatas)


def sintetizar(
    texto: str,
    destino: Path,
    *,
    sexo: str = "hombre",
    voz: dict[str, str] | None = None,
    rng: random.Random | None = None,
    # Cuánto vídeo hay para esta voz. Sirve para no sortear una voz lenta que
    # no quepa (ver `elegir_voz`). 0 = no se sabe, se sortea entre todas.
    segundos_max: float = 0.0,
    on_log: OnLog = _noop,
) -> dict:
    """Genera el mp3 crudo y lo deja nivelado en `destino`.

    Devuelve `{voz_id, voz_label, caracteres, duracion, lufs, pico}`.
    """
    clave = config.fish_api_key()
    if not clave:
        raise RuntimeError(
            "Falta FISH_API_KEY en el entorno — no se puede locutar el guion."
        )
    texto = " ".join((texto or "").split())
    if not texto:
        raise ValueError("no hay texto que locutar")

    elegida = voz or elegir_voz(
        sexo, rng, caracteres=len(texto), segundos_max=segundos_max,
    )
    on_log(f"[nicho_pov_bof_largo] voz: {elegida['label']} ({sexo})")

    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    crudo = destino.with_name(destino.stem + "_crudo.mp3")

    cuerpo = json.dumps({
        "text": texto, "reference_id": elegida["id"], "format": "mp3",
    }).encode("utf-8")
    peticion = urllib.request.Request(config.FISH_TTS_URL, data=cuerpo, headers={
        "Authorization": f"Bearer {clave}",
        "Content-Type": "application/json",
        "model": config.FISH_MODEL,
    })
    try:
        with urllib.request.urlopen(peticion, timeout=180) as r:
            crudo.write_bytes(r.read())
    except urllib.error.HTTPError as e:
        detalle = ""
        try:
            detalle = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        raise RuntimeError(f"Fish Audio devolvió {e.code}: {detalle}") from e

    _registrar_coste(texto, elegida)
    medidas = _nivelar(crudo, destino, on_log=on_log)
    try:
        crudo.unlink()
    except OSError:
        pass

    return {
        "voz_id": elegida["id"],
        "voz_label": elegida["label"],
        "caracteres": len(texto),
        **medidas,
    }


def _registrar_coste(texto: str, voz: dict) -> None:
    """Consumo de Fish. Con el modelo gratuito el coste es 0, pero el volumen
    se registra igual (ver la constante de tarifa)."""
    from src import cost_tracking

    bytes_utf8 = len(texto.encode("utf-8"))
    gratis = config.FISH_MODEL.endswith("-free")
    coste = 0.0 if gratis else bytes_utf8 / 1_000_000 * FISH_USD_PER_MILLON_BYTES
    try:
        cost_tracking.record_custom(
            kind="fish_tts",
            units=bytes_utf8,
            unit_label="bytes",
            cost_usd=coste,
            detail=f"{config.FISH_MODEL} · {voz['label']}",
        )
    except Exception:
        # Sin tracker activo (pruebas, scripts sueltos) no es motivo para
        # tirar abajo la locución.
        pass


def _medir(audio: Path, extra: str = "") -> dict[str, str]:
    """Primera pasada de `loudnorm`: mide para poder clavar el objetivo."""
    cadena = (f"{extra}," if extra else "") + (
        f"loudnorm=I={config.VOZ_LUFS}:TP={config.VOZ_TP}:LRA=7:print_format=json"
    )
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(audio), "-af", cadena, "-f", "null", "-"],
        capture_output=True, text=True,
    )
    medidas: dict[str, str] = {}
    for clave in ("input_i", "input_tp", "input_lra", "input_thresh"):
        m = re.search(rf'"{clave}"\s*:\s*"?(-?[\d.]+)"?', r.stderr)
        if m:
            medidas[clave] = m.group(1)
    return medidas


def _nivelar(crudo: Path, destino: Path, *, on_log: OnLog = _noop) -> dict:
    # El recorte de silencios va PRIMERO y forma parte de la cadena, para que la
    # medición de sonoridad y el render final vean el mismo audio ya ajustado.
    pre = f"{config.VOZ_SILENCIO},{config.VOZ_CADENA}"
    med = _medir(crudo, pre)
    norm = f"loudnorm=I={config.VOZ_LUFS}:TP={config.VOZ_TP}:LRA=7"
    if len(med) == 4:
        norm += (
            f":measured_I={med['input_i']}:measured_TP={med['input_tp']}"
            f":measured_LRA={med['input_lra']}:measured_thresh={med['input_thresh']}"
        )
    else:
        on_log("[nicho_pov_bof_largo] ⚠️ no pude medir la sonoridad — se normaliza en una pasada")
    # `level=disabled` es IMPRESCINDIBLE: por defecto `alimiter` RE-NIVELA la
    # salida hacia el límite, así que bajar el límite SUBE el volumen.
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(crudo), "-af",
         f"{pre},{norm},alimiter=limit={config.VOZ_LIMITER}:level=disabled",
         str(destino)],
        check=True, capture_output=True,
    )
    final = _medir(destino)
    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(destino)],
        capture_output=True, text=True,
    ).stdout.strip()
    salida = {
        "duracion": float(dur or 0),
        "lufs": float(final.get("input_i", 0) or 0),
        "pico": float(final.get("input_tp", 0) or 0),
    }
    on_log(
        f"[nicho_pov_bof_largo] voz {salida['duracion']:.1f}s · {salida['lufs']:.1f} LUFS · "
        f"pico {salida['pico']:.2f} dBTP"
    )
    return salida
