"""Montaje del vídeo del Nicho Ropa Con Personas.

Es una capa fina sobre el montador del Nicho POV BOF, que ya resuelve todo lo
que hace falta: normalizar, cuadrar la duración con la voz, quemar el bloque de
texto, superponer la flecha y nivelar el audio. Aquí solo cambian tres cosas:

1. **Solo va el título del producto**, con su emoji. Ni gancho ni CTA quemados:
   el nicho enseña la prenda y el texto encima, y todo lo demás lo dice la voz.
2. **El texto va CENTRADO**, sobre la prenda, no en la franja de arriba.
3. **La voz se sortea** entre las cinco locutoras, sin que el operador elija.

Duplicar el montador para esto sería copiar 1.200 líneas que después habría que
arreglar por duplicado cada vez que aparezca un bug de encuadre o de audio.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Callable

from src.nicho_pov_bof.pipeline.video_editor import build_video
from src.nicho_ropa_personas import config
from src.nicho_ropa_personas.services import audio_bank

OnLog = Callable[[str], None]
OnProgress = Callable[[float, str], None]

_noop: OnLog = lambda _msg: None
_noop_progress: OnProgress = lambda _p, _m: None


def montar(
    *,
    raw_video: Path,
    titulo: str,
    emojis: str = "",
    output_path: Path,
    work_dir: Path,
    semilla: str = "",
    audio_path: Path | None = None,
    rng: random.Random | None = None,
    on_log: OnLog = _noop,
    on_progress: OnProgress = _noop_progress,
) -> Path:
    """Monta el vídeo final de una prenda.

    `audio_path` se puede forzar (pruebas); si no, se sortea una de las cinco.
    """
    if audio_path is None:
        audio_path = audio_bank.pick_random(rng=rng)
    on_log(f"[ropa] voz: {audio_path.stem}")

    # El emoji va pegado al título, que es lo que hace el nicho: el nombre del
    # producto sobre la prenda con un emoji que acompañe.
    texto = titulo.strip()
    emoji = (emojis or "").strip()
    if emoji and texto:
        texto = f"{texto} {emoji}"

    return build_video(
        raw_video=Path(raw_video),
        audio_path=Path(audio_path),
        textos={"titulo": texto},
        output_path=Path(output_path),
        work_dir=Path(work_dir),
        con_gancho=False,
        con_cta=False,
        con_titulo=bool(texto),
        con_flecha=True,
        y_frac=config.TEXTO_CY,
        semilla=semilla or Path(output_path).stem,
        on_log=on_log,
        on_progress=on_progress,
    )
