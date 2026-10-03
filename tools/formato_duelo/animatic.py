"""Borrador (animatic) del formato «Duelo»: voces de Fish + pantalla partida +
rótulo VS + callouts + precio + CTA, sobre FOTOS (sin clips generados).
Se ejecuta dentro del contenedor de la API: python animatic.py <dir>."""
import json
import subprocess
import sys
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

D = Path(sys.argv[1])
W, H = 1080, 1920
FONT = "/app/assets/fonts/Montserrat-Black.ttf"
FONT2 = "/app/assets/fonts/Montserrat-ExtraBold.ttf"
g = json.loads((D / "guion.json").read_text())

from src.nicho_pov_bof_largo import config as c  # noqa: E402
from src.nicho_pov_bof_largo.services import voz  # noqa: E402

voces = {v["label"]: v for v in c.VOCES["hombre"]}
VOZ = {"a": voces["Amigo con Humor"], "b": voces["Joven Conversador Relajado"]}


def f(sz, bold=True):
    return ImageFont.truetype(FONT if bold else FONT2, sz)


def cover(img: Image.Image, w: int, h: int, foco=(0.5, 0.5), zoom=1.0) -> Image.Image:
    iw, ih = img.size
    esc = max(w / iw, h / ih) * zoom
    r = img.resize((int(iw * esc), int(ih * esc)), Image.LANCZOS)
    x = int((r.width - w) * foco[0]); y = int((r.height - h) * foco[1])
    return r.crop((x, y, x + w, y + h))


def texto_borde(d, xy, txt, fnt, fill="white", stroke=8, anchor="mm"):
    d.text(xy, txt, font=fnt, fill=fill, stroke_width=stroke, stroke_fill="black", anchor=anchor)


rival = [Image.open(D / "rival_full.jpg").convert("RGB"), Image.open(D / "rival_viento.jpg").convert("RGB")]
nuestro = Image.open(D / "nuestro.jpg").convert("RGB")
fotos_b = {"nuestro": nuestro}
for k in range(1, 6):
    q = D / "fotos" / f"c{k}.jpg"
    if q.exists():
        fotos_b[f"c{k}"] = Image.open(q).convert("RGB")
# Distintos encuadres de la foto real para cada ronda (en el vídeo de verdad,
# un clip distinto por ronda).
encuadres_b = [((0.5, 0.4), 1.0), ((0.15, 0.2), 1.6), ((0.85, 0.7), 1.5), ((0.5, 0.1), 1.8),
               ((0.35, 0.6), 1.3), ((0.5, 0.5), 1.0)]
encuadres_a = [(0, (0.95, 0.5), 2.2), (0, (0.95, 0.35), 2.6), (1, (0.95, 0.5), 2.2)]

PANEL_Y, PANEL_H = 300, 1180


def cuadro(i: int, linea: dict) -> Image.Image:
    lado = linea["q"]
    ronda = i // 2
    img = Image.new("RGB", (W, H), (18, 18, 22))
    # Paneles
    ia, fa, za = encuadres_a[min(ronda, len(encuadres_a) - 1)]
    pa = cover(rival[ia], W // 2, PANEL_H, fa, za)
    if linea.get("img") and linea["img"] in fotos_b and linea["img"] != "nuestro":
        pb = cover(fotos_b[linea["img"]], W // 2, PANEL_H, (0.5, 0.5), 1.0)
    else:
        fb, zb = encuadres_b[min(ronda, len(encuadres_b) - 1)]
        pb = cover(nuestro, W // 2, PANEL_H, fb, zb)
    if lado == "a":
        pb = ImageEnhance.Brightness(pb).enhance(0.45)
    elif lado == "b":
        pa = ImageEnhance.Brightness(pa).enhance(0.45)
    img.paste(pa, (0, PANEL_Y)); img.paste(pb, (W // 2, PANEL_Y))
    d = ImageDraw.Draw(img)
    for x0 in ([0, W // 2] if lado == "ab" else [0 if lado == "a" else W // 2]):
        d.rectangle([x0 + 4, PANEL_Y + 4, x0 + W // 2 - 4, PANEL_Y + PANEL_H - 4], outline=(255, 214, 0), width=8)
    # Rótulo VS
    for k, (txt, x) in enumerate(((g["titulo_a"], W // 4), (g["titulo_b"], 3 * W // 4))):
        activo = lado == "ab" or (k == 0) == (lado == "a")
        caja = [x - 250, 70, x + 250, 250]
        d.rounded_rectangle(caja, 28, fill=(255, 214, 0) if activo else (60, 60, 66))
        for j, trozo in enumerate(textwrap.wrap(txt.upper(), 12)):
            d.text((x, 125 + j * 62), trozo, font=f(52), fill="black" if activo else "white", anchor="mm")
    d.ellipse([W // 2 - 62, 98, W // 2 + 62, 222], fill=(230, 30, 40))
    d.text((W // 2, 160), "VS", font=f(64), fill="white", anchor="mm")
    # Callout del dato
    if linea.get("callout"):
        t = "✓ " + linea["callout"] if False else linea["callout"]
        tam = 46
        while d.textlength(t, font=f(tam)) > W // 2 - 90 and tam > 26:
            tam -= 2
        fnt = f(tam)
        tw = d.textlength(t, font=fnt)
        cx = 3 * W // 4
        d.rounded_rectangle([cx - tw / 2 - 30, PANEL_Y + PANEL_H - 170, cx + tw / 2 + 30, PANEL_Y + PANEL_H - 70],
                            24, fill=(255, 214, 0))
        d.text((cx, PANEL_Y + PANEL_H - 120), t, font=fnt, fill="black", anchor="mm")
    # Precio
    if linea.get("centro"):
        fnt = f(66)
        tw = d.textlength(linea["centro"], font=fnt)
        d.rounded_rectangle([W // 2 - tw / 2 - 40, 800, W // 2 + tw / 2 + 40, 950], 36, fill=(230, 30, 40))
        d.text((W // 2, 875), linea["centro"], font=fnt, fill="white", anchor="mm")
    # CTA
    if linea.get("cta"):
        d.rounded_rectangle([W // 2 - 360, 1150, W // 2 + 360, 1290], 36, fill=(255, 106, 0))
        d.text((W // 2, 1220), "CARRITO NARANJA", font=f(64), fill="white", anchor="mm")
        d.polygon([(W // 2 - 90, 1320), (W // 2 + 90, 1320), (W // 2, 1460)], fill=(230, 30, 40))
    return img


def con_subtitulo(base: Image.Image, trozo: str) -> Image.Image:
    """Subtítulo «pop-up» de tres palabras, como el POV BOF."""
    img = base.copy()
    d = ImageDraw.Draw(img)
    t = trozo.upper()
    tam = 92
    while d.textlength(t, font=f(tam)) > W - 120 and tam > 50:
        tam -= 4
    texto_borde(d, (W // 2, 1660), t, f(tam), fill="white", stroke=10)
    return img


def trozos_con_tiempo(texto: str, mp3: Path, dur: float) -> list[tuple[str, float]]:
    """[(3 palabras, segundos)] con los tiempos de Whisper; si no casan las
    palabras, se reparten por longitud de texto."""
    from src.subtitles import transcribe

    palabras = texto.split()
    try:
        ws = transcribe(str(mp3), model_size="small", language="es")
    except Exception:  # noqa: BLE001
        ws = []
    grupos = [palabras[k:k + 3] for k in range(0, len(palabras), 3)]
    if len(ws) == len(palabras):
        inicios = [ws[k]["start"] for k in range(0, len(palabras), 3)]
    else:
        total = sum(len(p) + 1 for p in palabras)
        acum, inicios = 0, []
        for k in range(0, len(palabras), 3):
            inicios.append(dur * acum / total)
            acum += sum(len(p) + 1 for p in palabras[k:k + 3])
    inicios[0] = 0.0
    salida = []
    for k, grupo in enumerate(grupos):
        fin = inicios[k + 1] if k + 1 < len(inicios) else dur
        salida.append((" ".join(grupo), max(0.05, fin - inicios[k])))
    return salida


partes = []
for i, linea in enumerate(g["lineas"]):
    mp3 = D / f"l{i:02d}.mp3"
    if not mp3.exists():
        # Entusiasmo: la etiqueta de emoción de Fish (no se lee en voz alta)
        # y un 6 % más rápido.
        quienes = ["a", "b"] if linea["q"] == "ab" else [linea["q"]]
        crudos = []
        for qn in quienes:
            cr = D / f"l{i:02d}_{qn}.mp3"
            voz.sintetizar("[excited] " + linea["t"], cr, voz=VOZ[qn])
            crudos.append(cr)
        entradas = sum((["-i", str(x)] for x in crudos), [])
        filtro = (f"amix=inputs={len(crudos)}:duration=longest:normalize=0," if len(crudos) > 1 else "") + "atempo=1.06"
        subprocess.run(["ffmpeg", "-v", "error", "-y", *entradas, "-filter_complex", filtro, str(mp3)], check=True)
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                         "-of", "csv=p=0", str(mp3)]).strip()) + 0.15
    base = cuadro(i, linea)
    base.save(D / f"c{i:02d}.png")
    lst = D / f"s{i:02d}.txt"
    filas = []
    for k, (trozo, seg) in enumerate(trozos_con_tiempo(linea["t"], mp3, dur)):
        png = D / f"c{i:02d}_{k:02d}.png"
        con_subtitulo(base, trozo).save(png)
        filas.append(f"file '{png}'\nduration {seg:.3f}\n")
    filas.append(f"file '{png}'\n")
    lst.write_text("".join(filas))
    mp4 = D / f"p{i:02d}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(mp3),
                    "-filter_complex", "[0:v]fps=30,format=yuv420p[v];[1:a]apad=pad_dur=0.15,aresample=44100[a]",
                    "-map", "[v]", "-map", "[a]", "-t", f"{dur:.2f}", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "22", "-c:a", "aac", "-b:a", "128k", str(mp4)], check=True)
    partes.append(mp4)
    print(i, linea["q"], f"{dur:.1f}s")
lista = D / "lista.txt"
lista.write_text("".join(f"file '{p}'\n" for p in partes))
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lista),
                "-c", "copy", str(D / "duelo_borrador.mp4")], check=True)
print("OK", D / "duelo_borrador.mp4")
