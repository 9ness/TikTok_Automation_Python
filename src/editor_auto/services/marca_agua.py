"""Quitar la marca de agua de los vídeos que mandan los agentes (12/11/2026).

Mismo método que el montaje de Tiktok Shop AI Pro (`nicho_pov_bof.config`):
no se tapa con un parche, se AMPLÍA el vídeo y el recorte se la lleva.
- Omni (GenAI Pro): estrella de Gemini abajo a la derecha → zoom 1,14 tirando
  solo de abajo (`ZOOM_MARCA_OMNI`, `ESQUINA_MARCA_OMNI`). Se reconoce mirando
  la imagen o por el comentario `marca:omni` del MP4 (`es_clip_omni`).
- Veo: marca pequeña en la esquina → zoom 1,07 centrado (`ZOOM_MARCA_AGUA`).
Se reutilizan esas funciones (no se copian) para que un ajuste allí valga aquí.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

MODOS = ("auto", "omni", "veo", "no")


def decidir(origen: Path, modo: str) -> tuple[float, str] | None:
    """(zoom, esquina) a aplicar, o None si no hay que tocar el vídeo."""
    from src.nicho_pov_bof import config as pov

    modo = (modo or "auto").strip().lower()
    if modo not in MODOS:
        raise ValueError(f"quitar_marca debe ser uno de {', '.join(MODOS)}.")
    if modo == "no":
        return None
    if modo == "omni" or (modo == "auto" and pov.es_clip_omni(origen)):
        return pov.ZOOM_MARCA_OMNI, pov.ESQUINA_MARCA_OMNI
    if modo == "veo":
        return pov.ZOOM_MARCA_AGUA, pov.ESQUINA_MARCA_AGUA
    return None  # auto sin estrella: el vídeo ya viene limpio (o montado)


def quitar(origen: Path, destino: Path, modo: str = "auto") -> str | None:
    """Escribe en `destino` el vídeo sin marca (1080x1920) y devuelve el modo
    aplicado ("omni"/"veo"), o None si no hacía falta (entonces no escribe)."""
    from src.nicho_pov_bof import config as pov

    enc = decidir(origen, modo)
    if enc is None:
        return None
    zoom, esquina = enc
    vf = pov.filtro_encuadre(zoom=zoom, esquina=esquina, acabado=False)
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-threads", "4", "-i", str(origen),
         "-vf", vf, "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
         "-c:a", "copy", "-movflags", "+faststart", str(destino)],
        check=True, timeout=900)
    return "omni" if zoom == pov.ZOOM_MARCA_OMNI and esquina == pov.ESQUINA_MARCA_OMNI else "veo"
