"""Locuta las líneas del duelo con Fish: python voces.py <dir> (lee guion3.json).
Entusiasmo con la etiqueta [excited] (no se lee) y un 6 % más rápido; las
líneas «ab» son las dos voces a la vez."""
import json
import subprocess
import sys
from pathlib import Path

from src.nicho_pov_bof_largo import config as c
from src.nicho_pov_bof_largo.services import voz

D = Path(sys.argv[1])
g = json.loads((D / "guion_paraguas.json").read_text())
voces = {v["label"]: v for v in c.VOCES["hombre"]}
VOZ = {"a": voces["Amigo con Humor"], "b": voces["Chico"]}  # «b»: elegida por ness (3 oct)
for i, linea in enumerate(g["lineas"]):
    mp3 = D / f"l{i:02d}.mp3"
    if mp3.exists():
        continue
    quienes = ["a", "b"] if linea["q"] == "ab" else [linea["q"]]
    crudos = []
    for qn in quienes:
        cr = D / f"l{i:02d}_{qn}.mp3"
        voz.sintetizar("[excited] " + linea["t"], cr, voz=VOZ[qn])
        crudos.append(cr)
    entradas = sum((["-i", str(x)] for x in crudos), [])
    filtro = (f"amix=inputs={len(crudos)}:duration=longest:normalize=0," if len(crudos) > 1 else "") + "atempo=1.06"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *entradas, "-filter_complex", filtro, str(mp3)], check=True)
    print(i, linea["q"], mp3.name)
