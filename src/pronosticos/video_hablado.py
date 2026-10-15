"""Vídeo «hablado» de C1: foto del partido + marcador + muñeco que habla.

Formato copiado de @analisis_yeison: foto fija del partido a pantalla
completa, una banda de marcador arriba (escudos redondos, nombres, hora y
«Mañana», sin cuotas) y el muñeco abajo en el centro contando 3-4 partidos en
~35 s. Abre con una tarjeta blanca que lista todos los partidos y luego pasa a
la banda de cada uno («escenas»). Una sola foto en todo el vídeo. Sin subtítulos.

El muñeco lo mueve `rig_hablado` (boca, parpadeo, gestos y cabeza a partir
del audio). Los fotogramas van por tubería a ffmpeg; nada de MoviePy.

Uso (CLI):
    python -m src.pronosticos.video_hablado --voz voz.mp3 --fondo foto.jpg \
        --local Benfica --visitante Celtic --logo-local 211.png --logo-visitante 247.png \
        --hora 21:00 --personaje viejo|mascota [--assets-mascota DIR] \
        [--marcas "13.8:dedo_arriba,16.3:explica_i"] [--musica fondo.mp3] --salida out.mp4
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

import numpy as np

from src.pronosticos.rig_hablado import FPS, Estado, analizar_voz, planificar

ANCHO, ALTO = 1080, 1920
FUENTES = Path(__file__).resolve().parents[2] / "assets" / "fonts"


def _fuente(nombre: str, tam: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FUENTES / nombre), tam)


def _fondo(foto: str) -> Image.Image:
    im = ImageOps.fit(Image.open(foto).convert("RGB"), (ANCHO, ALTO), Image.LANCZOS, centering=(0.5, 0.35))
    im = ImageEnhance.Brightness(im).enhance(0.82)
    # viñeta abajo para que el muñeco destaque
    grad = Image.linear_gradient("L").resize((ANCHO, ALTO)).point(lambda v: int(max(0, v - 110) * 1.4))
    negro = Image.new("RGB", (ANCHO, ALTO), (0, 0, 0))
    return Image.composite(negro, im, grad)


def _escudo_redondo(logo: str, d: int) -> Image.Image:
    circ = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    ImageDraw.Draw(circ).ellipse((0, 0, d - 1, d - 1), fill=(255, 255, 255, 255))
    lg = Image.open(logo).convert("RGBA")
    lg.thumbnail((int(d * 0.72), int(d * 0.72)), Image.LANCZOS)
    circ.alpha_composite(lg, ((d - lg.width) // 2, (d - lg.height) // 2))
    return circ


def _estrella(dr: ImageDraw.ImageDraw, cx, cy, r, color):
    import math
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.42
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    dr.polygon(pts, fill=color)


MARCADOR_Y = 470     # donde la pone Yeison (24 % de la altura)
MARCADOR_ALTO = 190


def _fuente_que_quepa(nombre: str, texto: str, tam: int, ancho_max: int) -> ImageFont.FreeTypeFont:
    f = _fuente(nombre, tam)
    while tam > 18 and f.getlength(texto) > ancho_max:
        tam -= 2
        f = _fuente(nombre, tam)
    return f


def posicion_marcador(fondo: Image.Image, defecto: int = MARCADOR_Y, tope_muneco: int = 1000) -> int:
    """Altura de la banda para que no tape ninguna cara grande del fondo.

    Prueba la posición de Yeison; si pisa una cara, la pone justo debajo de la
    barbilla (si cabe antes del muñeco) o encima de la frente."""
    try:
        import cv2
        import numpy as np
        gris = cv2.cvtColor(np.asarray(fondo.convert("RGB")), cv2.COLOR_RGB2GRAY)
        det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        caras = [tuple(c) for c in det.detectMultiScale(gris, 1.1, 6, minSize=(140, 140))]
    except Exception:
        return defecto

    def pisa(y0, holgura):
        """Píxeles de cara (alto × holgura, para dejar la barbilla) que tapa la banda."""
        return sum(max(0, min(y0 + MARCADOR_ALTO, y + h * holgura) - max(y0, y)) for x, y, w, h in caras)

    if not pisa(defecto, 1.25):
        return defecto
    huecos = sorted(range(160, tope_muneco - MARCADOR_ALTO + 1, 10), key=lambda v: abs(v - defecto))
    # 1) con margen bajo la barbilla; 2) justo bajo la barbilla (caras muy
    # grandes, 14-oct: Modrić); 3) lo que menos tape.
    for holgura in (1.25, 1.0):
        for y0 in huecos:
            if not pisa(y0, holgura):
                return y0
    return min(huecos, key=lambda v: (pisa(v, 1.0), abs(v - defecto)))


def _escudo(logo: str, d: int) -> Image.Image:
    lg = Image.open(logo).convert("RGBA")
    lg.thumbnail((d, d), Image.LANCZOS)
    return lg


def marcador(local: str, visitante: str, logo_l: str, logo_v: str, hora: str, dia: str = "Mañana",
             y0: int = MARCADOR_Y) -> Image.Image:
    """Banda de marcador (capa RGBA 1080×1920) como la de Yeison: oscura y
    translúcida, escudo suelto con el nombre debajo, hora y «Mañana» al centro,
    estrella llena a la izquierda y hueca a la derecha."""
    capa = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    y1 = y0 + MARCADOR_ALTO
    capa.alpha_composite(Image.new("RGBA", (ANCHO, y1 - y0), (34, 26, 22, 205)), (0, y0))
    d = ImageDraw.Draw(capa)
    cy = y0 + 62
    _estrella(d, 66, cy, 26, (255, 255, 255, 240))
    _estrella(d, ANCHO - 66, cy, 26, (255, 255, 255, 240))
    _estrella(d, ANCHO - 66, cy, 17, (34, 26, 22, 255))   # hueca
    diam = 104
    for cx, nombre, logo in ((205, local, logo_l), (ANCHO - 205, visitante, logo_v)):
        esc = _escudo(logo, diam)
        capa.alpha_composite(esc, (cx - esc.width // 2, y0 + 12 + (diam - esc.height) // 2))
        f_nom = _fuente_que_quepa("Poppins-SemiBold.ttf", nombre, 34, 300)
        d.text((cx, y0 + 12 + diam + 32), nombre, font=f_nom, fill="white", anchor="mm")
    d.text((ANCHO // 2, cy - 2), hora, font=_fuente("Poppins-SemiBold.ttf", 54), fill="white", anchor="mm")
    d.text((ANCHO // 2, cy + 56), dia, font=_fuente("Poppins-SemiBold.ttf", 38), fill=(235, 235, 235, 255), anchor="mm")
    return capa


def _es_claro(im: Image.Image) -> bool:
    a = np.asarray(im.convert("RGBA")).astype(float)
    visibles = a[a[..., 3] > 128][:, :3]
    return len(visibles) > 0 and visibles.mean() > 200


LISTA_Y = 240   # tarjeta-resumen de Yeison: x 112-967, y 240-768 con 4 partidos


def _auriculares(d: ImageDraw.ImageDraw, cx: int, cy: int, color) -> None:
    d.arc((cx - 14, cy - 14, cx + 14, cy + 14), 180, 360, fill=color, width=3)
    for x in (cx - 14, cx + 9):
        d.rounded_rectangle((x, cy - 2, x + 5, cy + 12), 2, outline=color, width=3)


def lista_partidos(filas: list[dict], y0: int = LISTA_Y) -> Image.Image:
    """Tarjeta blanca del principio con todos los partidos (como la de Yeison):
    estrella, los dos escudos con su nombre uno encima del otro, «PREVIEW» y la
    hora. `filas`: dicts con local, visitante, logo_l, logo_v y hora_corta."""
    capa = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    x0, x1, fila = 112, 968, 132
    y1 = y0 + fila * len(filas)
    tarjeta = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    dt = ImageDraw.Draw(tarjeta)
    dt.rounded_rectangle((x0, y0, x1, y1), 30, fill=(255, 255, 255, 250))
    capa.alpha_composite(tarjeta.filter(ImageFilter.GaussianBlur(0.6)))
    d = ImageDraw.Draw(capa)
    f_nom = _fuente("Poppins-SemiBold.ttf", 28)
    f_pre = _fuente("Poppins-SemiBold.ttf", 17)
    f_hora = _fuente("Poppins-SemiBold.ttf", 25)
    gris = (120, 120, 120, 255)
    for i, f in enumerate(filas):
        top = y0 + i * fila
        if i:
            d.line((x0, top, x1, top), fill=(228, 228, 228, 255), width=2)
        cy = top + fila // 2
        _estrella(d, x0 + 38, cy, 22, (255, 196, 0, 255))
        for k, (nombre, logo) in enumerate(((f["local"], f["logo_l"]), (f["visitante"], f["logo_v"]))):
            yy = cy - 28 + k * 56
            esc = _escudo(logo, 40)
            if _es_claro(esc):   # p. ej. la Juventus, blanca: no se vería sobre la tarjeta
                d.ellipse((x0 + 100 - 25, yy - 25, x0 + 100 + 25, yy + 25), fill=(45, 45, 45, 255))
                esc = _escudo(logo, 34)
            capa.alpha_composite(esc, (x0 + 100 - esc.width // 2, yy - esc.height // 2))
            d.text((x0 + 140, yy), nombre, font=f_nom, fill=(40, 40, 40, 255), anchor="lm")
        _auriculares(d, x0 + 680, cy - 24, gris)
        d.rounded_rectangle((x0 + 625, cy + 10, x0 + 735, cy + 40), 6, outline=(150, 150, 150, 255), width=2)
        d.text((x0 + 680, cy + 25), "PREVIEW", font=f_pre, fill=gris, anchor="mm")
        d.text((x1 - 22, cy), f["hora_corta"], font=f_hora, fill=gris, anchor="rm")
    return capa


def planificar_reposo(personaje) -> Estado:
    return Estado(t=0.0, boca="pequena", apertura=0.0, parpado=0.0, pose_a=personaje.reposo,
                  pose_b=personaje.reposo, mezcla=1.0, cabeza_rot=0.0, cabeza_dy=0.0, ceja=0.0,
                  mirada=(0.0, 0.0), cuerpo_dy=0.0, habla=0.0)


def _sombra(ancho: int) -> Image.Image:
    s = Image.new("RGBA", (ancho, 80), (0, 0, 0, 0))
    ImageDraw.Draw(s).ellipse((ancho * 0.12, 18, ancho * 0.88, 62), fill=(0, 0, 0, 140))
    return s.filter(ImageFilter.GaussianBlur(14))


def _colocar(personaje, alto_muneco):
    """Tamaño y sitio: la FIGURA (no el lienzo) mide `alto_en_video` y apoya los
    pies en `pies_en_video`, como el muñeco de Yeison."""
    reposo = personaje.frame(planificar_reposo(personaje))
    pw, ph = reposo.size
    filas = np.where((np.asarray(reposo.getchannel("A")) > 20).any(1))[0]
    fig_y0, fig_y1 = int(filas[0]), int(filas[-1])
    alto_fig = alto_muneco or getattr(personaje, "alto_en_video", 860)
    pies = getattr(personaje, "pies_en_video", 1683)
    esc = alto_fig / (fig_y1 - fig_y0)
    tam = (int(pw * esc), int(ph * esc))
    px, py = (ANCHO - tam[0]) // 2, int(pies - fig_y1 * esc)
    return esc, tam, px, py, pies, py + int(fig_y0 * esc)


def renderizar(voz: str, escenas: list[dict], personaje, salida: str, marcas=None, musica: str | None = None,
               alto_muneco: int | None = None, vol_musica: float = 0.10, semilla: int = 7) -> list[int]:
    """Monta el vídeo. `escenas`: lista ordenada de dicts con `t` (segundo en que
    entra) y `fondo`, y además o bien `lista` (filas de `lista_partidos`: la
    tarjeta-resumen del principio) o bien `local`, `visitante`, `logo_l`,
    `logo_v`, `hora` y, opcional, `marcador_y` (banda de un partido).
    Devuelve la altura del marcador de cada escena."""
    v = analizar_voz(voz, fps=FPS)
    plan = planificar(v, personaje, marcas=marcas, semilla=semilla)
    esc, tam, px, py, pies, cabeza_y = _colocar(personaje, alto_muneco)
    sombra = _sombra(int(tam[0] * 0.6))
    bases, alturas = [], []
    for e in escenas:
        base = _fondo(e["fondo"]).convert("RGBA")
        base.alpha_composite(sombra, ((ANCHO - sombra.width) // 2, pies - 40))
        if e.get("lista"):
            y = LISTA_Y
            base.alpha_composite(lista_partidos(e["lista"], y))
        else:
            y = e.get("marcador_y") or posicion_marcador(base, tope_muneco=cabeza_y + 60)
            base.alpha_composite(marcador(e["local"], e["visitante"], e["logo_l"], e["logo_v"], e["hora"],
                                          dia=e.get("dia", "Mañana"), y0=y))
        bases.append(base.convert("RGB"))
        alturas.append(y)
    inicios = [int(round(e.get("t", 0) * FPS)) for e in escenas]

    entradas = ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{ANCHO}x{ALTO}", "-r", str(FPS), "-i", "-",
                "-i", voz]
    filtro = "[1:a]aresample=48000,loudnorm=I=-14:TP=-2.0:LRA=11,apad[a]"
    if musica:
        entradas += ["-stream_loop", "-1", "-i", musica]
        filtro = (f"[1:a]aresample=48000,loudnorm=I=-14:TP=-2.0:LRA=11,apad[v];"
                  f"[2:a]aresample=48000,volume={vol_musica}[m];"
                  f"[v][m]amix=inputs=2:duration=first:normalize=0:dropout_transition=0,alimiter=limit=0.89[a]")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *entradas, "-filter_complex", filtro,
           "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", salida]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    # la voz va con apad (silencio infinito): la duración la marca el vídeo (-shortest)
    n = len(plan.estados) + int(0.6 * FPS)   # medio segundo de cola en reposo
    k = 0
    for i in range(n):
        while k + 1 < len(bases) and i >= inicios[k + 1]:
            k += 1
        est = plan.estados[min(i, len(plan.estados) - 1)]
        im = personaje.frame(est).resize(tam, Image.BILINEAR)
        cuadro = bases[k].copy()
        cuadro.paste(im, (px, py + int(getattr(est, "cuerpo_dy", 0) * esc)), im)
        proc.stdin.write(cuadro.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg falló al montar el vídeo hablado")
    return alturas


def _parse_marcas(txt: str | None):
    if not txt:
        return None
    return [(float(t), p) for t, p in (x.split(":") for x in txt.split(",") if x)]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--voz", required=True)
    ap.add_argument("--fondo", required=True)
    ap.add_argument("--local", required=True)
    ap.add_argument("--visitante", required=True)
    ap.add_argument("--logo-local", required=True)
    ap.add_argument("--logo-visitante", required=True)
    ap.add_argument("--hora", required=True)
    ap.add_argument("--personaje", choices=["viejo", "mascota"], default="viejo")
    ap.add_argument("--assets-mascota")
    ap.add_argument("--marcas")
    ap.add_argument("--musica")
    ap.add_argument("--semilla", type=int, default=7)
    ap.add_argument("--salida", required=True)
    a = ap.parse_args()
    if a.personaje == "mascota":
        from src.pronosticos.rig_mascota import PersonajeMascota
        pj = PersonajeMascota(a.assets_mascota)
    else:
        from src.pronosticos.rig_hablado import PersonajeViejo
        pj = PersonajeViejo()
    escena = {"t": 0, "fondo": a.fondo, "local": a.local, "visitante": a.visitante,
              "logo_l": a.logo_local, "logo_v": a.logo_visitante, "hora": a.hora}
    renderizar(a.voz, [escena], pj, a.salida, marcas=_parse_marcas(a.marcas), musica=a.musica, semilla=a.semilla)


if __name__ == "__main__":
    main()
