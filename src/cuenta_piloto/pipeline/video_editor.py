"""Montaje del vídeo de la Cuenta Piloto.

Capa fina sobre el montador del Nicho POV BOF: la edición es LA MISMA (gancho,
título, CTA, flecha y voz sorteada del banco), porque lo que cambia en este
nicho es de dónde sale el vídeo bruto —orgánico, no generado con IA— y eso el
montador ni lo mira.

Duplicarlo sería copiar 1.200 líneas y tener que arreglar dos veces cada bug
de encuadre o de audio.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from src.nicho_pov_bof.pipeline.video_editor import build_video, layout_for_producto
from src.nicho_pov_bof.services import audio_bank

OnLog = Callable[[str], None]
OnProgress = Callable[[float, str], None]

_noop: OnLog = lambda _msg: None
_noop_progress: OnProgress = lambda _p, _m: None


def montar(
    *,
    raw_video: Path,
    textos: dict,
    sexo: str,
    output_path: Path,
    work_dir: Path,
    semilla: str = "",
    con_gancho: bool = True,
    con_titulo: bool = True,
    con_cta: bool = True,
    con_flecha: bool = True,
    audio_path: Path | None = None,
    on_log: OnLog = _noop,
    on_progress: OnProgress = _noop_progress,
) -> Path:
    """Monta el vídeo final de un producto.

    `audio_path` se puede forzar (pruebas); si no, se sortea una frase del
    banco para el sexo elegido y se le recortan los silencios.
    """
    if audio_path is None:
        crudo = audio_bank.pick_random(sexo)
        audio_path = audio_bank.prepare(crudo, on_log=on_log)
        on_log(f"[cuenta_piloto] voz: {crudo.name} → {Path(audio_path).name}")

    return build_video(
        raw_video=Path(raw_video),
        audio_path=Path(audio_path),
        textos=textos or {},
        output_path=Path(output_path),
        work_dir=Path(work_dir),
        layout=layout_for_producto(semilla, (textos or {}).get("cta", "")),
        con_gancho=con_gancho,
        con_titulo=con_titulo,
        con_cta=con_cta,
        con_flecha=con_flecha,
        semilla=semilla or Path(output_path).stem,
        on_log=on_log,
        on_progress=on_progress,
    )
