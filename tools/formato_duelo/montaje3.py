"""Montaje del «Duelo» en UN plano compartido (los dos en el mismo banco) a
PANTALLA COMPLETA. Las caras no se recortan aquí: la imagen base se genera con
la cámara inclinada hacia abajo (el borde de arriba pasa bajo la barbilla y
abajo queda suelo), así no hay labios que sincronizar ni bandas.
python montaje3.py <dir>  → <dir>/duelo_final3.mp4 (antes: voces.py <dir>;
<dir> con guion_paraguas.json y media/ con los clips; usar /app/temp_work, no /tmp)"""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

D = Path(sys.argv[1])
W, H = 1080, 1920
SERIF = "/app/assets/fonts/PTSerif-Bold.ttf"
BLACK = "/app/assets/fonts/Montserrat-Black.ttf"
g = json.loads((D / "guion_paraguas.json").read_text())
NARANJA = (255, 106, 0, 255)
# Al hablar y reír la boca baja hasta el 4 % y la barbilla al 6 %: fuera un 8 %
# (y lo mismo repartido en los lados, para seguir en 9:16).
RECORTE_ARRIBA = 0.08
Y_ROTULO = 0.83   # rótulos sobre el suelo, por debajo de los subtítulos (68 %)
# Hasta dónde vale cada clip (revisado fotograma a fotograma): a partir de ahí
# el generador deforma el paraguas.
LIMITE = {"t2_nuestro.mp4": 6.6}


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


def encajar(txt: str, sz: int, ancho: float) -> Image.Image:
    """Rótulo naranja que nunca se sale: baja de tamaño hasta caber."""
    im = texto_cursiva(txt, sz, borde=NARANJA)
    while im.width > ancho and sz > 30:
        sz -= 4
        im = texto_cursiva(txt, sz, borde=NARANJA)
    return im


def capa(linea: dict, sub: str) -> Image.Image:
    lado = linea["q"]
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # Títulos fijos arriba, como la referencia.
    # Arriba están los cuerpos y los mangos: títulos lo más arriba posible y la
    # bandera en el hueco entre los dos, encima del VS (no tapa ningún paraguas).
    pegar(img, texto_cursiva(g["titulo_a"].replace(" ", "\n", 1), 62), W * 0.24, 120)
    pegar(img, texto_cursiva("VS", 60), W * 0.5, 175)
    pegar(img, texto_cursiva(g["titulo_b"].replace(" ", "\n", 1), 62), W * 0.76, 120)
    pegar(img, bandera_es(84, 56), W * 0.5, 88)
    d = ImageDraw.Draw(img)
    # Dato de la ronda, en cursiva sobre el lado del nuestro.
    if linea.get("callout"):
        pegar(img, encajar(linea["callout"].replace(" · ", "\n"), 80, W * 0.9), W * 0.5, H * Y_ROTULO)
    if linea.get("centro"):
        pegar(img, encajar(linea["centro"].capitalize(), 84, W * 0.9), W * 0.5, H * Y_ROTULO)
    # Subtítulo pop-up de 3 palabras, a la altura del POV BOF (68 %).
    if sub:
        # Tamaño fijo como el POV BOF; si no cabe, a dos líneas (no encoger).
        t = sub.upper(); tam = 72
        fnt = fuente(BLACK, tam)
        if d.textlength(t, font=fnt) > W * 0.78 and " " in t:
            pal = t.split()
            mitad = min(range(1, len(pal)), key=lambda k: abs(len(" ".join(pal[:k])) - len(" ".join(pal[k:]))))
            t = " ".join(pal[:mitad]) + "\n" + " ".join(pal[mitad:])
        while max(d.textlength(x, font=fnt) for x in t.split("\n")) > W * 0.86 and tam > 50:
            tam -= 4; fnt = fuente(BLACK, tam)
        borde = NARANJA if lado == "b" else ((255, 196, 0, 255) if lado == "ab" else (0, 0, 0, 255))
        d.multiline_text((W / 2, int(0.68 * H)), t, font=fnt, fill="white", anchor="mm", align="center",
                         spacing=6, stroke_width=max(6, tam // 9), stroke_fill=borde)
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
    corte = dur * linea["corte"] if linea.get("clip2") else dur
    # Cada clip sigue por donde iba; si no queda bastante, se coge el último
    # tramo que quepa (los clips empiezan y acaban en el mismo fotograma).
    ini = desde.get(clip.name, linea.get("desde", 0.0))
    largo = min(LIMITE.get(clip.name, 99.0), float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(clip)]).strip()))
    if ini + corte > largo - 0.1:
        ini = max(0.0, largo - 0.1 - corte)
    desde[clip.name] = ini + corte
    capas = []
    for k, (txt, a, b) in enumerate(trozos(linea["t"], mp3, dur)):
        png = D / f"x{i:02d}_{k:02d}.png"
        capa(linea, txt).save(png)
        capas.append((png, a, b))
    # Segundo clip en la misma frase («se abre solo»: corte de cerrado a
    # abierto, sin que el generador tenga que transformar el paraguas).
    args = ["ffmpeg", "-v", "error", "-y", "-ss", f"{ini:.2f}", "-t", f"{corte:.3f}", "-i", str(clip)]
    if linea.get("clip2"):
        clip2 = media / linea["clip2"]
        ini2 = desde.get(clip2.name, 0.0)
        largo2 = LIMITE.get(clip2.name, 7.9)
        if ini2 + dur - corte > largo2 - 0.1:
            ini2 = max(0.0, largo2 - 0.1 - (dur - corte))
        desde[clip2.name] = ini2 + dur - corte
        args += ["-ss", f"{ini2:.2f}", "-t", f"{dur - corte + 0.1:.3f}", "-i", str(clip2)]
    n_v = 2 if linea.get("clip2") else 1
    for png, _, _ in capas:
        args += ["-i", str(png)]
    args += ["-i", str(mp3)]
    fil = []
    if n_v == 2:
        fil.append("[0:v]fps=30,setsar=1,settb=1/30[c0];[1:v]fps=30,setsar=1,settb=1/30[c1];"
                   "[c0][c1]concat=n=2:v=1:a=0[src]")
    else:
        fil.append("[0:v]fps=30,setsar=1[src]")
    fil.append(f"[src]crop=iw*{1 - RECORTE_ARRIBA}:ih*{1 - RECORTE_ARRIBA}:iw*{RECORTE_ARRIBA / 2}:ih*{RECORTE_ARRIBA},"
               f"scale={W}:{H}:flags=lanczos,unsharp=5:5:0.5,setsar=1[v0]")
    ult = "v0"
    for k, (_, a, b) in enumerate(capas):
        fil.append(f"[{ult}][{n_v + k}:v]overlay=0:0:enable='between(t,{a:.3f},{b:.3f})'[v{k + 1}]")
    # (las capas empiezan después de los vídeos de entrada)
        ult = f"v{k + 1}"
    # Limitador: la mezcla de las dos voces a la vez pasaba de 0 dBFS.
    fil.append(f"[{n_v + len(capas)}:a]apad=pad_dur=0.15,aresample=44100,"
               f"alimiter=limit=0.89:level=disabled[a]")
    mp4 = D / f"y{i:02d}.mp4"
    args += ["-filter_complex", ";".join(fil), "-map", f"[{ult}]", "-map", "[a]", "-t", f"{dur:.2f}",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "128k", str(mp4)]
    subprocess.run(args, check=True)
    partes.append(mp4)
    print(i, linea["q"], f"{dur:.1f}s", clip.name, f"desde {ini:.1f}")
(D / "lista3.txt").write_text("".join(f"file '{p}'\n" for p in partes))
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(D / "lista3.txt"),
                "-c", "copy", str(D / "duelo_sin_flecha.mp4")], check=True)
# La flecha al carrito de SIEMPRE (la de los editores del POV BOF: una de sus
# animaciones al azar, en su sitio, cuando la voz dice «carrito»).
from src.nicho_pov_bof.pipeline import video_editor as pov  # noqa: E402

trabajo = D / "flecha"; trabajo.mkdir(exist_ok=True)
con_flecha = pov._overlay_arrow(D / "duelo_sin_flecha.mp4", D / "duelo_sin_flecha.mp4", trabajo,
                                trabajo / "con_flecha.mp4", print, con_audio=True)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(con_flecha), "-c", "copy", "-map_metadata", "-1",
                str(D / "duelo_final3.mp4")], check=True)
pov.limpiar_metadatos(D / "duelo_final3.mp4", print)
print("OK", D / "duelo_final3.mp4")
