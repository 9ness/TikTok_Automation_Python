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

from PIL import Image, ImageDraw, ImageFilter, ImageFont

D = Path(sys.argv[1])
W, H = 1080, 1920
SERIF = "/app/assets/fonts/PTSerif-Bold.ttf"
BLACK = "/app/assets/fonts/Montserrat-Black.ttf"
g = json.loads((D / "guion_paraguas.json").read_text())
NARANJA = (255, 106, 0, 255)
# Al hablar y reír la boca baja hasta el 4 % y la barbilla al 6 %: fuera un 8 %
# (y lo mismo repartido en los lados, para seguir en 9:16).
RECORTE_ARRIBA = 0.08
Y_TITULOS = 0.105
# Zona segura de TikTok: abajo (desde ~78 %) va la descripción y a la derecha
# los botones. El dato, en el centro de la pantalla: apartado de los subtítulos (68 %).
Y_ROTULO = 0.50
# Tramo VÁLIDO de cada clip (revisado fotograma a fotograma): fuera de él el
# generador deforma el paraguas o el rival suelta el suyo y se queda de pie
# solo («flotando»). Lo que no está aquí vale entero.
VENTANA = {
    "t2_idle.mp4": (5.0, 7.9), "i_risa.mp4": (4.5, 7.9), "r_risa2.mp4": (3.0, 7.9),
    "r_idleb2.mp4": (4.5, 7.9), "r_idle2.mp4": (0.5, 3.2), "f_cerrado.mp4": (0.0, 7.9),
    "t_nuestro.mp4": (0.5, 5.5), "t2_nuestro.mp4": (4.5, 6.6), "f_abierto1.mp4": (3.0, 7.9),
    "f_abierto2.mp4": (1.5, 7.9),
}


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


AZUL_BRILLO = (60, 150, 255, 255)
AZUL_CAJA = (8, 28, 70, 150)


def rotulo_azul(txt: str, sz: int) -> Image.Image:
    """Dato de la ronda: blanco en cursiva con BRILLO AZUL (el color del
    paraguas) sobre una caja azul marino translúcida. Distinto a propósito de
    los subtítulos (Montserrat con borde), para que se lea como «dato»."""
    fnt = fuente(SERIF, sz)
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lineas = txt.split("\n")
    alto_l = int(sz * 1.18)
    w = int(max(tmp.textlength(l, font=fnt) for l in lineas)) + 2 * int(sz * 0.55)
    h = alto_l * len(lineas) + int(sz * 0.6)
    pad = 30  # sitio para el brillo
    im = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([pad, pad, pad + w, pad + h], radius=int(sz * 0.35), fill=AZUL_CAJA,
                                         outline=(120, 190, 255, 200), width=3)

    def pintar(capa_: Image.Image, color, trazo: int) -> None:
        d = ImageDraw.Draw(capa_)
        for j, l in enumerate(lineas):
            d.text((pad + w / 2, pad + int(sz * 0.3) + j * alto_l + alto_l / 2), l, font=fnt, fill=color,
                   anchor="mm", stroke_width=trazo, stroke_fill=color)

    brillo = Image.new("RGBA", im.size, (0, 0, 0, 0))
    pintar(brillo, AZUL_BRILLO, max(4, sz // 10))
    brillo = brillo.filter(ImageFilter.GaussianBlur(sz / 6))
    im.alpha_composite(brillo)
    im.alpha_composite(brillo)
    letras = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(letras)
    for j, l in enumerate(lineas):
        d.text((pad + w / 2, pad + int(sz * 0.3) + j * alto_l + alto_l / 2), l, font=fnt, fill=(255, 255, 255, 255),
               anchor="mm", stroke_width=2, stroke_fill=(10, 40, 110, 255))
    im.alpha_composite(letras)
    return cursiva(im)


def encajar(txt: str, sz: int, ancho: float) -> Image.Image:
    """Rótulo de dato que nunca se sale: baja de tamaño hasta caber."""
    im = rotulo_azul(txt, sz)
    while im.width > ancho and sz > 30:
        sz -= 4
        im = rotulo_azul(txt, sz)
    return im


def capa(linea: dict, sub: str) -> Image.Image:
    lado = linea["q"]
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # Títulos fijos arriba, como la referencia.
    # Posiciones medidas en los virales de referencia: títulos centrados al
    # ~10 % (más arriba los tapa el buscador de TikTok). Sin bandera: aquí se
    # comparan TIPOS de paraguas, no países (la bandera solo si el título es
    # «Paraguas español / coreano…»).
    pegar(img, texto_cursiva(g["titulo_a"].replace(" ", "\n", 1), 60), W * 0.25, H * Y_TITULOS)
    pegar(img, texto_cursiva("VS", 56), W * 0.5, H * Y_TITULOS)
    pegar(img, texto_cursiva(g["titulo_b"].replace(" ", "\n", 1), 60), W * 0.75, H * Y_TITULOS)
    d = ImageDraw.Draw(img)
    # Dato de la ronda, en cursiva sobre el lado del nuestro.
    if linea.get("callout"):
        # Una línea; si es un dato doble («105 cm abierto · 38 cm plegado»),
        # dos líneas un poco más arriba para no pisar los subtítulos.
        dos = " · " in linea["callout"]
        pegar(img, encajar(linea["callout"].replace(" · ", "\n"), 58 if dos else 64, W * 0.8),
              W * 0.5, H * Y_ROTULO)
    if linea.get("centro"):
        pegar(img, encajar(linea["centro"].capitalize(), 84, W * 0.9), W * 0.5, H * Y_ROTULO)
    # Subtítulo pop-up de 3 palabras, a la altura del POV BOF (68 %).
    if sub:
        # Tamaño fijo como el POV BOF; si no cabe, a dos líneas (no encoger).
        t = sub.upper(); tam = 72
        fnt = fuente(BLACK, tam)
        if d.textlength(t, font=fnt) > W * 0.70 and " " in t:
            pal = t.split()
            mitad = min(range(1, len(pal)), key=lambda k: abs(len(" ".join(pal[:k])) - len(" ".join(pal[k:]))))
            t = " ".join(pal[:mitad]) + "\n" + " ".join(pal[mitad:])
        while max(d.textlength(x, font=fnt) for x in t.split("\n")) > W * 0.76 and tam > 50:
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
    # Tramos de vídeo de la frase: [(clip, fracción en que acaba)]. «clip2» +
    # «corte» es el atajo de dos; «tramos» deja meter un inserto en medio.
    if linea.get("tramos"):
        tramos = [(media / c, float(h)) for c, h in linea["tramos"]]
    elif linea.get("clip2"):
        tramos = [(media / linea["clip"], linea["corte"]), (media / linea["clip2"], 1.0)]
    else:
        tramos = [(media / linea["clip"], 1.0)]
    entradas_v: list[tuple[Path, float, float]] = []  # (clip, inicio, duración)
    previo = 0.0
    for k, (clip, hasta) in enumerate(tramos):
        trozo = dur * hasta - previo + (0.1 if k == len(tramos) - 1 else 0.0)
        previo = dur * hasta
        v_ini, v_fin = VENTANA.get(clip.name, (0.0, float(subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(clip)]).strip())))
        ini = desde.get(clip.name, max(v_ini, linea.get("desde", 0.0) if k == 0 else 0.0))
        if ini + trozo > v_fin - 0.1:
            ini = max(v_ini, v_fin - 0.1 - trozo)
        desde[clip.name] = ini + trozo
        entradas_v.append((clip, ini, trozo))
    capas = []
    for k, (txt, a, b) in enumerate(trozos(linea["t"], mp3, dur)):
        png = D / f"x{i:02d}_{k:02d}.png"
        capa(linea, txt).save(png)
        capas.append((png, a, b))
    args = ["ffmpeg", "-v", "error", "-y"]
    for clip, ini, trozo in entradas_v:
        args += ["-ss", f"{ini:.2f}", "-t", f"{trozo:.3f}", "-i", str(clip)]
    n_v = len(entradas_v)
    for png, _, _ in capas:
        args += ["-i", str(png)]
    args += ["-i", str(mp3)]
    fil = [f"[{k}:v]fps=30,scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1,settb=1/30[c{k}]"
           for k in range(n_v)]
    fil.append("".join(f"[c{k}]" for k in range(n_v)) + f"concat=n={n_v}:v=1:a=0[src]")
    fil.append(f"[src]crop=iw*{1 - RECORTE_ARRIBA}:ih*{1 - RECORTE_ARRIBA}:iw*{RECORTE_ARRIBA / 2}:ih*{RECORTE_ARRIBA},"
               f"scale={W}:{H}:flags=lanczos,unsharp=5:5:0.5,setsar=1[v0]")
    ult = "v0"
    for k, (_, a, b) in enumerate(capas):  # las capas van detrás de los vídeos
        fil.append(f"[{ult}][{n_v + k}:v]overlay=0:0:enable='between(t,{a:.3f},{b:.3f})'[v{k + 1}]")
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
    print(i, linea["q"], f"{dur:.1f}s", " + ".join(f"{c.name}@{a:.1f}" for c, a, _ in entradas_v))
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
