"""Montaje del «Duelo» en UN plano compartido (los dos en el mismo banco), como
el creador de referencia: vídeo a pantalla completa y los textos encima.
python montaje2.py <dir>  → <dir>/duelo_final2.mp4"""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

D = Path(sys.argv[1])
W, H = 1080, 1920
SERIF = "/app/assets/fonts/PTSerif-Bold.ttf"
BLACK = "/app/assets/fonts/Montserrat-Black.ttf"
g = json.loads((D / "guion.json").read_text())
NARANJA = (255, 106, 0, 255)
# Recorte del clip: se quita la franja de arriba (bocas) y se rellena la
# pantalla entera sin bandas.
RECORTE_ARRIBA = 0.11


def fuente(ruta, sz):
    return ImageFont.truetype(ruta, sz)


def cursiva(img: Image.Image) -> Image.Image:
    """Inclina un texto ya pintado (PT Serif no trae cursiva)."""
    k = 0.2
    w, h = img.size
    return img.transform((w + int(h * k), h), Image.AFFINE, (1, k, -h * k, 0, 1, 0), Image.BICUBIC)


def texto_cursiva(txt: str, sz: int, borde=(0, 0, 0, 255), relleno=(255, 255, 255, 255)) -> Image.Image:
    fnt = fuente(SERIF, sz)
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lineas = txt.split("\n")
    anchos = [tmp.textlength(l, font=fnt) for l in lineas]
    w, h = int(max(anchos)) + 40, int(len(lineas) * sz * 1.15) + 30
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for j, l in enumerate(lineas):
        d.text((w / 2, 15 + j * sz * 1.15 + sz / 2), l, font=fnt, fill=relleno, anchor="mm",
               stroke_width=max(3, sz // 12), stroke_fill=borde)
    return cursiva(im)


def bandera_es(w=150, h=100) -> Image.Image:
    im = Image.new("RGBA", (w, h), (198, 11, 30, 255))
    ImageDraw.Draw(im).rectangle([0, h // 4, w, 3 * h // 4], fill=(255, 196, 0, 255))
    return im


def pegar(base, pieza, cx, cy):
    base.alpha_composite(pieza, (int(cx - pieza.width / 2), int(cy - pieza.height / 2)))


def capa(linea: dict, sub: str) -> Image.Image:
    lado = linea["q"]
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # Títulos fijos arriba, como la referencia.
    pegar(img, texto_cursiva(g["titulo_a"].replace(" ", "\n", 1), 66), W * 0.25, 175)
    pegar(img, texto_cursiva("VS", 60), W * 0.5, 175)
    pegar(img, texto_cursiva(g["titulo_b"].replace(" ", "\n", 1), 66), W * 0.75, 175)
    pegar(img, bandera_es(), W * 0.25, 320)
    d = ImageDraw.Draw(img)
    # Dato de la ronda, en cursiva sobre el lado del nuestro.
    if linea.get("callout"):
        pegar(img, texto_cursiva(linea["callout"].replace(" · ", "\n"), 76, borde=NARANJA), W * 0.73, 600)
    if linea.get("centro"):
        pegar(img, texto_cursiva(linea["centro"].title(), 84, borde=NARANJA), W * 0.5, 980)
    # Subtítulo pop-up de 3 palabras, a la altura del POV BOF (68 %).
    if sub:
        t = sub.upper(); tam = 72
        fnt = fuente(BLACK, tam)
        while d.textlength(t, font=fnt) > W * 0.70 and tam > 44:
            tam -= 4; fnt = fuente(BLACK, tam)
        borde = NARANJA if lado == "b" else ((255, 196, 0, 255) if lado == "ab" else (0, 0, 0, 255))
        d.text((W / 2, int(0.68 * H)), t, font=fnt, fill="white", anchor="mm",
               stroke_width=max(6, tam // 9), stroke_fill=borde)
    return img


def trozos(texto: str, mp3: Path, dur: float):
    from src.subtitles import transcribe

    pal = texto.split()
    try:
        ws = transcribe(str(mp3), model_size="small", language="es")
    except Exception:  # noqa: BLE001
        ws = []
    if len(ws) == len(pal):
        ini = [ws[k]["start"] for k in range(0, len(pal), 3)]
    else:
        total = sum(len(p) + 1 for p in pal); acum = 0; ini = []
        for k in range(0, len(pal), 3):
            ini.append(dur * acum / total); acum += sum(len(p) + 1 for p in pal[k:k + 3])
    ini[0] = 0.0
    return [(" ".join(pal[k * 3:k * 3 + 3]), ini[k], ini[k + 1] if k + 1 < len(ini) else dur) for k in range(len(ini))]


media = D / "media"
desde: dict[str, float] = {}
partes = []
for i, linea in enumerate(g["lineas"]):
    mp3 = D / f"l{i:02d}.mp3"
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                         "-of", "csv=p=0", str(mp3)]).strip()) + 0.15
    clip = media / linea["clip"]
    # Cada clip sigue por donde iba; si se acaba, vuelve a empezar.
    ini = desde.get(clip.name, linea.get("desde", 0.0))
    largo = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                           "-of", "csv=p=0", str(clip)]).strip())
    if ini + dur > largo - 0.3:
        ini = max(0.0, largo - 0.3 - dur) if linea.get("desde") is None else 0.0
    desde[clip.name] = ini + dur
    capas = []
    for k, (txt, a, b) in enumerate(trozos(linea["t"], mp3, dur)):
        png = D / f"z{i:02d}_{k:02d}.png"
        capa(linea, txt).save(png)
        capas.append((png, a, b))
    args = ["ffmpeg", "-v", "error", "-y", "-ss", f"{ini:.2f}", "-i", str(clip)]
    for png, _, _ in capas:
        args += ["-i", str(png)]
    args += ["-i", str(mp3)]
    fil = [f"[0:v]fps=30,crop=iw*{1 - RECORTE_ARRIBA}*9/16*16/9:ih*{1 - RECORTE_ARRIBA}:(iw-ow)/2:ih*{RECORTE_ARRIBA},"
           f"scale={W}:{H},setsar=1[v0]"]
    ult = "v0"
    for k, (_, a, b) in enumerate(capas):
        fil.append(f"[{ult}][{1 + k}:v]overlay=0:0:enable='between(t,{a:.3f},{b:.3f})'[v{k + 1}]")
        ult = f"v{k + 1}"
    fil.append(f"[{1 + len(capas)}:a]apad=pad_dur=0.15,aresample=44100[a]")
    mp4 = D / f"w{i:02d}.mp4"
    args += ["-filter_complex", ";".join(fil), "-map", f"[{ult}]", "-map", "[a]", "-t", f"{dur:.2f}",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "128k", str(mp4)]
    subprocess.run(args, check=True)
    partes.append(mp4)
    print(i, linea["q"], f"{dur:.1f}s", clip.name, f"desde {ini:.1f}")
(D / "lista2.txt").write_text("".join(f"file '{p}'\n" for p in partes))
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(D / "lista2.txt"),
                "-c", "copy", str(D / "duelo_sin_flecha.mp4")], check=True)
# La flecha al carrito de SIEMPRE (la de los editores del POV BOF: una de sus
# animaciones al azar, en su sitio, cuando la voz dice «carrito»).
from src.nicho_pov_bof.pipeline import video_editor as pov  # noqa: E402

trabajo = D / "flecha"; trabajo.mkdir(exist_ok=True)
con_flecha = pov._overlay_arrow(D / "duelo_sin_flecha.mp4", D / "duelo_sin_flecha.mp4", trabajo,
                                trabajo / "con_flecha.mp4", print, con_audio=True)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(con_flecha), "-c", "copy", "-map_metadata", "-1",
                str(D / "duelo_final2.mp4")], check=True)
pov.limpiar_metadatos(D / "duelo_final2.mp4", print)
print("OK", D / "duelo_final2.mp4")
