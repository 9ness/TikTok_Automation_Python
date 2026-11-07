"""Mide cuánto se mueve un vídeo (diferencia media entre fotogramas, YAVG de tblend).

Uso: python3 scripts/medir_movimiento.py v1.mp4 [v2.mp4 ...]
Imprime la media del vídeo y la de cada mitad (≈ cada clip de un vídeo de 2 clips).
Referencia: sancionados por «contenido estático» 0,85-1,63 (un clip 0,35-1,15);
sin problemas 2-3 o más. Verde: media ≥ 2 y ninguna mitad < 1,5.
"""
import re
import subprocess
import sys
import tempfile


def medir(ruta: str) -> list[float]:
    with tempfile.NamedTemporaryFile(suffix=".txt") as f:
        subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-i", ruta, "-vf",
             f"fps=10,scale=180:-2,tblend=all_mode=difference,signalstats,"
             f"metadata=print:key=lavfi.signalstats.YAVG:file={f.name}",
             "-f", "null", "-"],
            check=True,
        )
        return [float(x) for x in re.findall(r"YAVG=([\d.]+)", open(f.name).read())]


def main() -> None:
    for ruta in sys.argv[1:]:
        v = medir(ruta)
        if not v:
            print(f"sin fotogramas  {ruta}")
            continue
        h = max(1, len(v) // 2)
        media, c1, c2 = sum(v) / len(v), sum(v[:h]) / h, sum(v[h:]) / max(1, len(v) - h)
        if media >= 2 and min(c1, c2) >= 1.5:
            nota = "OK"
        elif media >= 1.5:
            nota = "AL LÍMITE (ámbar)"
        else:
            nota = "ESTÁTICO (rehacer)"
        print(f"{media:.2f}  clip1 {c1:.2f}  clip2 {c2:.2f}  {nota}  {ruta}")


if __name__ == "__main__":
    main()
