"""Variantes SIN créditos de un vídeo ya montado y en verde (réplicas `rv|`).

De un MP4 terminado (píldora de gancho arriba los primeros segundos, flecha
abajo a la izquierda al final, música dentro) saca hasta tres versiones que
cambian varias cosas a la vez:

  - gancho nuevo: una píldora opaca con otro texto tapa la del original;
  - otro orden de los planos SIN flecha (la cola con flecha no se toca);
  - un movimiento lento de cámara (acercar, alejar o deriva lateral);
  - espejo de los planos sin flecha, solo si quien lo lanza lo pide (el
    producto tiene que ser simétrico y sin texto ni logos: lo decide el
    agente mirando la ficha, nunca el script);
  - otra música libre del banco (`Multiplataforma/_musica`).

Todo con ffmpeg, PIL y numpy: 0 créditos. El texto del gancho lo escribe
Haiku (`ganchos`, céntimos) o lo pasa el agente.

Reglas anti-duplicado (`bloqueadas`, lógica pura): una familia es el vídeo
original más sus variantes; de una familia solo sale UNO al día, con al menos
`DIAS_ENTRE` días desde la última subida de cualquiera de ellos, y ninguna
variante antes que su original. Como mucho `MAX_VARIANTES` por original.

Cada variante pasa el control de cualquier vídeo (`controlar`: comprobador
técnico + movimiento) y se registra SIN semáforo (`registrar_variante`), así
que queda «sin revisar» en Mis tandas hasta que el agente la mire a 2 fps.

CLI: `python3 -m src.replicar_viral.variantes {analizar,crear,hoja,ganchos,registrar,publicables}`.
Guía: `src/agente_mcp/guias/replicar-virales.md` › «Variantes sin créditos».
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import itertools
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

W, H = 1080, 1920
FPS = 30
MAX_VARIANTES = 3
DIAS_ENTRE = 3
GANCHO_MAX_S = 6.0        # la píldora nueva nunca dura más que esto
COLA_FLECHA_S = 4.0       # si no se detecta la flecha: los últimos 4 s
MARGEN_TAPA = 14          # px que la píldora nueva sobresale de la vieja
RAIZ = Path(__file__).resolve().parents[2]
FUENTES = RAIZ / "assets" / "fonts"
PROMPT_GANCHO = Path(__file__).parent / "prompts" / "variantes_gancho.md"

ESTILOS_PILDORA = {
    "negra": ((17, 17, 17), (255, 255, 255)),
    "amarilla": ((255, 221, 51), (0, 0, 0)),
    "blanca": ((255, 255, 255), (0, 0, 0)),
}
# (zoom inicial, zoom final, deriva lateral en px de un extremo al otro)
MOVIMIENTOS = {
    "acercar": (1.03, 1.07, 0),
    "alejar": (1.08, 1.04, 0),
    "deriva": (1.05, 1.07, 12),
}
# Qué cambia cada variante: nunca dos iguales del mismo original.
RECETAS = {
    1: {"pildora": "negra", "movimiento": "acercar", "orden": 0},
    2: {"pildora": "amarilla", "movimiento": "alejar", "orden": 1},
    3: {"pildora": "blanca", "movimiento": "deriva", "orden": 2},
}
ESTILOS_MUSICA = ("pop_outfit", "soul_funk_70s", "retro_vintage", "folk_acustico",
                  "jazz_cafe", "lofi_otono", "house_fashion", "hiphop_chill")

_PRECIO = re.compile(r"\d+(?:[.,]\d+)?\s?(?:€|eur\w*|euros?)|(?:€|\$)\s?\d+|\d+\s?%", re.I)
_PROHIBIDO = re.compile(r"\b(?:cup[oó]n\w*|descuento\w*|rebaja\w*|gratis|el mejor|la mejor|garantizad\w+)\b", re.I)
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿⌚-⏿]")


class ErrorVariante(Exception):
    pass


# ---------------------------------------------------------------------------
# Análisis del vídeo original
# ---------------------------------------------------------------------------
def _run(cmd: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def duracion(video: Path) -> float:
    out = _run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                "format=duration", "-of", "csv=p=0", str(video)]).stdout.strip()
    try:
        return float(out)
    except ValueError as e:
        raise ErrorVariante(f"No se puede leer {video}") from e


def cortes(video: Path, umbral: float = 0.3) -> list[float]:
    """Segundo en que empieza cada plano nuevo (cambio de escena)."""
    err = _run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-an", "-vf",
                f"select='gt(scene,{umbral})',showinfo", "-f", "null", "-"]).stderr
    return [float(x) for x in re.findall(r"pts_time:([\d.]+)", err)]


def _fotogramas(video: Path, fps: int = 4, ancho: int = 270, alto: int = 480):
    import numpy as np

    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video), "-vf",
                        f"fps={fps},scale={ancho}:{alto}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       capture_output=True, timeout=600)
    datos = np.frombuffer(r.stdout, dtype=np.uint8)
    n = datos.size // (ancho * alto * 3)
    if not n:
        raise ErrorVariante(f"ffmpeg no pudo leer {video}")
    return datos[: n * ancho * alto * 3].reshape(n, alto, ancho, 3)


def _tramo_mas_largo(marcas) -> tuple[int, int] | None:
    mejor, ini = None, None
    for i, m in enumerate(list(marcas) + [False]):
        if m and ini is None:
            ini = i
        elif not m and ini is not None:
            if mejor is None or i - ini > mejor[1] - mejor[0]:
                mejor = (ini, i)
            ini = None
    return mejor


def detectar_pildora(fr, fps: int = 4) -> dict | None:
    """La píldora blanca del gancho: rectángulo casi blanco, quieto y centrado
    durante los primeros segundos. Devuelve su caja en píxeles de 1080x1920 y
    hasta qué segundo se ve, o None si no hay.

    Las filas que cruzan el texto tienen poco blanco, pero los márgenes de la
    píldora son blancos de arriba abajo: se busca el tramo más alto de filas
    cuyo blanco empieza y acaba en las mismas dos columnas."""
    import numpy as np

    n, alto, ancho, _ = fr.shape
    esc = W / ancho
    blanco = fr.min(axis=3) > 215
    quieto = blanco[1: max(2, int(2 * fps) + 1)].all(axis=0)
    limite = int(0.62 * alto)
    ext: list[tuple[int, int] | None] = []
    for y in range(limite):
        xs = np.flatnonzero(quieto[y])
        ext.append((int(xs[0]), int(xs[-1])) if xs.size >= 0.12 * ancho else None)
    mejor = None
    y = 0
    while y < limite:
        if ext[y] is None:
            y += 1
            continue
        # la fila de referencia es la más ancha del tramo (las esquinas son redondas)
        y1 = y
        while y1 < limite and ext[y1] is not None:
            y1 += 1
        tramo = ext[y:y1]
        x0 = min(e[0] for e in tramo)
        x1 = max(e[1] for e in tramo)
        dentro = [abs(e[0] - x0) <= 3 and abs(e[1] - x1) <= 3 for e in tramo]
        sub = _tramo_mas_largo(dentro)
        if sub and (mejor is None or sub[1] - sub[0] > mejor[1] - mejor[0]):
            w, h = x1 - x0 + 1, sub[1] - sub[0]
            centrada = abs((x0 + x1) / 2 - ancho / 2) <= 0.08 * ancho
            if 0.30 * ancho <= w <= 0.98 * ancho and 0.025 * alto <= h <= 0.28 * alto and centrada:
                mejor = (y + sub[0], y + sub[1], x0, x1 + 1)
        y = y1
    if mejor is None:
        return None
    y0, y1, x0, x1 = mejor
    # las filas de las esquinas redondas quedan fuera del tramo: 2 filas por lado
    y0, y1 = max(y0 - 2, 0), min(y1 + 2, alto)
    presente = [blanco[i, y0:y1, x0:x1].mean() > 0.45 for i in range(n)]
    fin_ = next((i for i, p in enumerate(presente) if not p and i > 0), n)
    return {"x": int(x0 * esc), "y": int(y0 * esc), "w": int((x1 - x0) * esc),
            "h": int((y1 - y0) * esc), "fin": round(fin_ / fps, 2)}


def _amarillo(fr):
    """Máscara del amarillo de la flecha en la esquina de abajo a la izquierda."""
    alto, ancho = fr.shape[-3], fr.shape[-2]
    zona = fr[..., int(0.70 * alto): int(0.93 * alto), : int(0.48 * ancho), :].astype("int16")
    r, g, b = zona[..., 0], zona[..., 1], zona[..., 2]
    return (r > 190) & (g > 150) & (b < 110) & (r - b > 100)


def detectar_flecha(fr, dur: float, fps: int = 4) -> dict | None:
    """La flecha amarilla de abajo a la izquierda: desde qué segundo se ve
    (hasta el final) y en qué ventana. None si no se distingue. Se mide solo en
    la ventana más amarilla del último segundo y medio: las luces doradas del
    fondo engañan si se mira toda la esquina."""
    import numpy as np

    n = fr.shape[0]
    amarillo = _amarillo(fr)
    ult = max(int(1.5 * fps), 2)
    fija = (amarillo[-ult:].mean(axis=0) >= 0.3).astype("int32")
    vh, vw = min(40, fija.shape[0]), min(28, fija.shape[1])      # flecha de ~110x160 px + su vaivén
    ii = np.pad(fija.cumsum(axis=0).cumsum(axis=1), ((1, 0), (1, 0)))
    sumas = ii[vh:, vw:] - ii[:-vh, vw:] - ii[vh:, :-vw] + ii[:-vh, :-vw]
    y, x = np.unravel_index(int(sumas.argmax()), sumas.shape)
    if sumas[y, x] < 0.12 * vh * vw:
        return None
    frac = amarillo[:, y: y + vh, x: x + vw].reshape(n, -1).mean(axis=1)
    ref = float(np.median(frac[-ult:]))
    hay = frac >= 0.5 * ref
    i = n
    while i > 0 and hay[i - 1]:
        i -= 1
    t = i / fps
    if n - i < fps or t < 0.25 * dur:      # menos de 1 s, o «flecha» casi todo el vídeo: no es la flecha
        return None
    return {"desde": round(t, 2), "ventana": [int(y), int(x), vh, vw], "ref": round(ref, 4)}


def _flecha_en(video: Path, t: float, flecha: dict) -> bool:
    """¿Se ve la flecha en el fotograma del segundo `t`?"""
    import numpy as np

    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{max(t, 0):.3f}", "-i", str(video),
                        "-frames:v", "1", "-vf", "scale=270:480", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       capture_output=True, timeout=120)
    if len(r.stdout) < 270 * 480 * 3:
        return True                        # ante la duda, ese plano no se mueve
    fr = np.frombuffer(r.stdout[: 270 * 480 * 3], dtype=np.uint8).reshape(480, 270, 3)
    y, x, vh, vw = flecha["ventana"]
    return float(_amarillo(fr)[y: y + vh, x: x + vw].mean()) >= 0.5 * flecha["ref"]


def analizar(video: Path) -> dict:
    video = Path(video)
    dur = duracion(video)
    fr = _fotogramas(video)
    pildora = detectar_pildora(fr)
    flecha = detectar_flecha(fr, dur)
    avisos = []
    if pildora is None:
        avisos.append("No se detecta la píldora del gancho: la nueva irá en el sitio habitual; revisa que no queden dos textos.")
    if flecha is None:
        avisos.append(f"No se detecta la flecha: se respetan los últimos {COLA_FLECHA_S:.0f} s.")
    cts = [c for c in cortes(video) if 0.4 < c < dur - 0.4]
    bordes = [0.0] + cts + [dur]
    planos = []
    for a, b in zip(bordes, bordes[1:]):
        if flecha is None:
            con = b > max(dur - COLA_FLECHA_S, 0.0) + 0.15
        else:
            # un plano lleva flecha si la tiene su último fotograma (una vez sale, ya no se va)
            con = b > flecha["desde"] + 0.3 or (b > flecha["desde"] - 0.3 and _flecha_en(video, b - 0.05, flecha))
        planos.append({"ini": round(a, 3), "fin": round(b, 3), "flecha": con})
    # Desde el primer plano con flecha, todo es cola: no se mueve ni se espeja.
    cola = False
    for p in planos:
        cola = cola or p["flecha"]
        p["flecha"] = cola
    return {"duracion": round(dur, 3), "cortes": [round(c, 3) for c in cts], "pildora": pildora,
            "flecha_desde": flecha["desde"] if flecha else None, "planos": planos, "avisos": avisos}


# ---------------------------------------------------------------------------
# Receta: qué cambia en cada variante
# ---------------------------------------------------------------------------
def _fin_gancho(orden: list[int], planos: list[dict], fin_pildora: float) -> float:
    """Hasta qué segundo de la SALIDA hay que tapar: el último instante que
    enseña un fotograma del original con la píldora vieja."""
    t, fin = 0.0, 0.0
    for i in orden:
        p = planos[i]
        if p["ini"] < fin_pildora:
            fin = t + min(p["fin"], fin_pildora) - p["ini"]
        t += p["fin"] - p["ini"]
    return fin


def ordenes(analisis: dict) -> list[list[int]]:
    """Órdenes de planos distintos del original: solo se permutan los planos
    sin flecha, y no valen los que alargan el gancho más de `GANCHO_MAX_S`.
    Primero los que abren con otro plano."""
    planos = analisis["planos"]
    cabeza = [i for i, p in enumerate(planos) if not p["flecha"]]
    cola = [i for i, p in enumerate(planos) if p["flecha"]]
    fin_pildora = (analisis.get("pildora") or {}).get("fin", 4.0)
    salida = []
    for perm in itertools.permutations(cabeza):
        orden = list(perm) + cola
        if list(perm) == cabeza or _fin_gancho(orden, planos, fin_pildora) > GANCHO_MAX_S:
            continue
        salida.append(orden)
    salida.sort(key=lambda o: (o[0] == cabeza[0], o))
    return salida


def receta(analisis: dict, n: int, *, espejo: bool = False, conservar_audio: bool = False) -> dict:
    """La receta de la variante `n` (1..MAX_VARIANTES) de un original."""
    if n not in RECETAS:
        raise ErrorVariante(f"Solo hay variantes 1..{MAX_VARIANTES}; no «{n}».")
    base = RECETAS[n]
    planos = analisis["planos"]
    original = list(range(len(planos)))
    otros = [] if conservar_audio else ordenes(analisis)
    # con un solo orden alternativo, la 2 se queda con el original (cambia en lo
    # demás) para que 1 y 2 no se parezcan entre sí
    ciclo = otros[:MAX_VARIANTES] + ([original] if len(otros) < MAX_VARIANTES else [])
    orden = ciclo[base["orden"] % len(ciclo)]
    z0, z1, deriva = MOVIMIENTOS[base["movimiento"]]
    return {"n": n, "pildora": base["pildora"], "movimiento": base["movimiento"],
            "z0": z0, "z1": z1, "deriva": deriva, "orden": orden, "orden_cambia": orden != original,
            # el espejo solo en las variantes impares: así 1 y 2 no se parecen
            "espejo": bool(espejo and n % 2 == 1 and any(not p["flecha"] for p in planos)),
            "conservar_audio": bool(conservar_audio)}


# ---------------------------------------------------------------------------
# Píldora nueva
# ---------------------------------------------------------------------------
def _trozos(linea: str) -> list[tuple[bool, str]]:
    out: list[tuple[bool, str]] = []
    for ch in linea.replace("️", "").replace("‍", ""):
        emo = bool(_EMOJI.match(ch))
        if out and out[-1][0] == emo and not emo:
            out[-1] = (False, out[-1][1] + ch)
        else:
            out.append((emo, ch))
    return out


def _ancho_linea(d, linea: str, fuente, tam: int) -> float:
    return sum(tam * 1.08 if emo else d.textlength(t, font=fuente) for emo, t in _trozos(linea))


def _partir(palabras: list[str], lineas: int, medir) -> list[str]:
    """Reparte las palabras en `lineas` líneas lo más parejas posible."""
    n = len(palabras)
    lineas = min(lineas, n)
    mejor, mejor_w = None, None
    for cortes_ in itertools.combinations(range(1, n), lineas - 1):
        idx = [0, *cortes_, n]
        ls = [" ".join(palabras[a:b]) for a, b in zip(idx, idx[1:])]
        w = max(medir(l) for l in ls)
        if mejor_w is None or w < mejor_w:
            mejor, mejor_w = ls, w
    return mejor or [" ".join(palabras)]


def pintar_pildora(texto: str, tapa: dict | None, estilo: str, destino: Path) -> dict:
    """PNG 1080x1920 transparente con la píldora nueva. `tapa` es la caja que
    hay que cubrir entera (la píldora vieja ya movida por el zoom); el texto se
    ajusta para llenarla. Devuelve la caja pintada."""
    from PIL import Image, ImageDraw, ImageFont

    fondo, tinta = ESTILOS_PILDORA[estilo]
    texto = " ".join((texto or "").split())
    if not texto:
        raise ErrorVariante("Falta el texto del gancho.")
    if tapa is None:
        tapa = {"x": 190, "y": 250, "w": 700, "h": 150}
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    palabras = texto.split()
    mejor = None
    for tam in range(62, 36, -2):
        fuente = ImageFont.truetype(str(FUENTES / "TikTokSans-Bold.ttf"), tam)
        pad, alto_l = int(tam * 0.56), int(tam * 1.32)
        for nl in (1, 2, 3, 4):
            ls = _partir(palabras, nl, lambda l: _ancho_linea(d, l, fuente, tam))
            bw = max(_ancho_linea(d, l, fuente, tam) for l in ls) + 2 * pad
            bh = alto_l * len(ls) + 2 * pad - int(tam * 0.12)
            if bw > W - 60:
                continue
            fw, fh = max(bw, tapa["w"]), max(bh, tapa["h"])
            sobra = (fw * fh) / (bw * bh)          # 1 = el texto llena la caja
            clave = (round(sobra, 1), -tam)
            if mejor is None or clave < mejor[0]:
                mejor = (clave, tam, fuente, ls, fw, fh, pad, alto_l, bh)
    if mejor is None:
        raise ErrorVariante(f"El gancho no cabe en pantalla: «{texto}»")
    _, tam, fuente, ls, fw, fh, pad, alto_l, bh = mejor
    cx, cy = tapa["x"] + tapa["w"] / 2, tapa["y"] + tapa["h"] / 2
    y0 = int(max(cy - fh / 2, 0))
    if fw >= W - 40:                       # no cabe con esquinas: banda de lado a lado
        x0, fw = 0, W
        d.rectangle((0, y0, W, y0 + fh), fill=(*fondo, 255))
    else:
        x0 = int(min(max(cx - fw / 2, 12), W - 12 - fw))
        d.rounded_rectangle((x0, y0, x0 + fw, y0 + fh), radius=int(tam * 0.44), fill=(*fondo, 255))
    emo = ImageFont.truetype(str(FUENTES / "NotoColorEmoji.ttf"), 109)
    ty = y0 + (fh - bh) / 2 + pad
    for linea in ls:
        tx = x0 + (fw - _ancho_linea(d, linea, fuente, tam)) / 2
        for es_emoji, t in _trozos(linea):
            if es_emoji:
                g = Image.new("RGBA", (140, 140), (0, 0, 0, 0))
                ImageDraw.Draw(g).text((0, 0), t, font=emo, embedded_color=True)
                caja = g.getbbox()
                if caja:
                    g = g.crop(caja).resize((tam, tam), Image.LANCZOS)
                    im.alpha_composite(g, (int(tx + tam * 0.04), int(ty + tam * 0.14)))
                tx += tam * 1.08
            else:
                d.text((tx, ty), t, font=fuente, fill=(*tinta, 255))
                tx += d.textlength(t, font=fuente)
        ty += alto_l
    destino.parent.mkdir(parents=True, exist_ok=True)
    im.save(destino)
    return {"x": x0, "y": y0, "w": int(fw), "h": int(fh), "tam": tam, "lineas": ls}


def caja_tapada(pildora: dict | None, rec: dict, analisis: dict, fin_gancho: float) -> dict | None:
    """Dónde cae la píldora vieja en la salida (con espejo, zoom y deriva),
    unida a lo largo del gancho y con margen: lo que la nueva debe cubrir."""
    if not pildora:
        return None
    dur = analisis["duracion"]
    cajas = [(pildora["x"], pildora["w"])]
    if rec["espejo"]:
        cajas.append((W - pildora["x"] - pildora["w"], pildora["w"]))
    xs, ys = [], []
    pasos = max(2, int(fin_gancho / 0.25) + 2)
    for k in range(pasos):
        t = min(fin_gancho, k * 0.25)
        f = t / dur
        z = rec["z0"] + (rec["z1"] - rec["z0"]) * f
        pan = rec["deriva"] * (f - 0.5)
        for x, w in cajas:
            for px in (x, x + w):
                xs.append((px - W / 2) * z + W / 2 - pan * z)
        for py in (pildora["y"], pildora["y"] + pildora["h"]):
            ys.append((py - H / 2) * z + H / 2)
    x0, x1 = max(min(xs) - MARGEN_TAPA, 0), min(max(xs) + MARGEN_TAPA, W)
    y0, y1 = max(min(ys) - MARGEN_TAPA, 0), min(max(ys) + MARGEN_TAPA, H)
    return {"x": int(x0), "y": int(y0), "w": int(x1 - x0 + 1), "h": int(y1 - y0 + 1)}


# ---------------------------------------------------------------------------
# Música libre
# ---------------------------------------------------------------------------
def musica_dir() -> Path:
    env = os.getenv("VARIANTES_MUSICA_DIR")
    if env:
        return Path(env)
    try:
        from src.multiplataforma import config as mp_config

        d = Path(mp_config.musica_dir())
        if d.is_dir():
            return d
    except Exception:  # noqa: BLE001 — fuera de la app: la ruta del Drive montado
        pass
    return Path.home() / "gdrive/Nebulabs/TikTok/TikTok Shop/Multiplataforma/_musica"


def banco(base: Path | None = None, estilos=ESTILOS_MUSICA) -> list[Path]:
    base = Path(base) if base else musica_dir()
    pistas: list[Path] = []
    for e in estilos:
        d = base / e
        if d.is_dir():
            pistas += sorted(p for p in d.iterdir() if p.suffix.lower() in (".mp3", ".m4a", ".wav"))
    return pistas


def elegir_pista(origen_id: str, n: int, pistas: list[Path]) -> Path:
    """Una pista fija por (original, variante): las tres variantes de un
    original llevan pistas distintas y de estilos distintos."""
    if not pistas:
        raise ErrorVariante("El banco de música libre está vacío o el Drive no está montado.")
    por_estilo: dict[str, list[Path]] = {}
    for p in pistas:
        por_estilo.setdefault(p.parent.name, []).append(p)
    h = int(hashlib.sha1(origen_id.encode()).hexdigest(), 16)
    estilos = sorted(por_estilo)
    lista = por_estilo[estilos[(h + n) % len(estilos)]]
    return lista[(h // 7 + n) % len(lista)]


# ---------------------------------------------------------------------------
# Montaje
# ---------------------------------------------------------------------------
def montar(video: Path, analisis: dict, rec: dict, gancho: str, destino: Path,
           pista: Path | None = None) -> dict:
    """Renderiza la variante. Devuelve lo que ha hecho (para el JSON de la tanda)."""
    video, destino = Path(video), Path(destino)
    planos, dur = analisis["planos"], analisis["duracion"]
    fin_pildora = (analisis.get("pildora") or {}).get("fin", 4.0)
    fin_gancho = round(min(max(_fin_gancho(rec["orden"], planos, fin_pildora), 2.0), GANCHO_MAX_S), 3)
    tapa = caja_tapada(analisis.get("pildora"), rec, analisis, fin_gancho)
    png = destino.with_suffix(".pildora.png")
    caja = pintar_pildora(gancho, tapa, rec["pildora"], png)

    partes = []
    k = len(rec["orden"])
    simple = k == 1 and not rec["espejo"]
    if simple:
        partes.append("[0:v]null[cat]")
    else:
        partes.append(f"[0:v]split={k}" + "".join(f"[s{j}]" for j in range(k)))
        for j, i in enumerate(rec["orden"]):
            p = planos[i]
            fin = "" if i == len(planos) - 1 else f":end={p['fin']}"
            flip = ",hflip" if rec["espejo"] and not p["flecha"] else ""
            partes.append(f"[s{j}]trim=start={p['ini']}{fin},setpts=PTS-STARTPTS{flip}[v{j}]")
        partes.append("".join(f"[v{j}]" for j in range(k)) + f"concat=n={k}:v=1:a=0[cat]")
    nf = max(int(dur * FPS), 1)
    dz = rec["z1"] - rec["z0"]
    # x2 antes del zoompan: sin eso el recorte va a saltos de 1 px y tiembla
    partes.append(
        f"[cat]fps={FPS},scale={2 * W}:{2 * H}:flags=bicubic,"
        f"zoompan=z='{rec['z0']}+({dz:.4f})*on/{nf}'"
        f":x='(iw-iw/zoom)/2+{2 * rec['deriva']}*(on/{nf}-0.5)':y='(ih-ih/zoom)/2'"
        f":d=1:s={W}x{H}:fps={FPS},setsar=1[z]")
    partes.append(f"[z][1:v]overlay=0:0:enable='lt(t,{fin_gancho})',format=yuv420p[v]")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(video), "-i", str(png)]
    if rec["conservar_audio"]:
        audio = ["-map", "0:a:0", "-c:a", "aac", "-b:a", "160k"]
    else:
        if pista is None:
            raise ErrorVariante("Falta la pista de música.")
        cmd += ["-stream_loop", "-1", "-ss", "3", "-i", str(pista)]
        fundido = (f"loudnorm=I=-16:TP=-2:LRA=11,afade=t=in:st=0:d=0.3,"
                   f"afade=t=out:st={max(dur - 0.8, 0):.3f}:d=0.8,aresample=48000")
        audio = ["-map", "2:a:0", "-af", fundido, "-c:a", "aac", "-b:a", "160k", "-ac", "2"]
    tmp = destino.with_name(destino.stem + ".tmp.mp4")
    cmd += ["-filter_complex", ";".join(partes), "-map", "[v]", *audio,
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-r", str(FPS),
            "-t", f"{dur:.3f}", "-map_metadata", "-1", "-map_chapters", "-1",
            "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
            "-movflags", "+faststart", str(tmp)]
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = _run(cmd, timeout=1800)
        if r.returncode != 0 or not tmp.is_file():
            raise ErrorVariante(f"ffmpeg falló: {r.stderr[-600:]}")
        tmp.replace(destino)
    finally:
        tmp.unlink(missing_ok=True)
        png.unlink(missing_ok=True)
    return {"gancho": gancho, "gancho_hasta_s": fin_gancho, "pildora_caja": caja,
            "musica": f"{pista.parent.name}/{pista.name}" if pista and not rec["conservar_audio"] else "original"}


def restos_pildora(video: Path, caja: dict, hasta: float, fps: int = 4) -> bool:
    """True si alrededor de la píldora nueva asoma una franja blanca y quieta
    del ancho de la píldora: la vieja no ha quedado tapada del todo."""
    fr = _fotogramas(Path(video), fps=fps, ancho=540, alto=960)
    k = max(int(hasta * fps) - 1, 2)
    # con los planos cambiados de orden la vieja no se ve seguida: basta la mitad del rato
    quieto = (fr[1:k].min(axis=3) > 215).mean(axis=0) >= 0.5
    x0, x1 = max(caja["x"] // 2 + 12, 0), min((caja["x"] + caja["w"]) // 2 - 12, 540)
    arriba, abajo = caja["y"] // 2, (caja["y"] + caja["h"]) // 2
    for franja in (quieto[max(arriba - 7, 0): max(arriba - 1, 0), x0:x1], quieto[abajo + 1: abajo + 7, x0:x1]):
        if franja.size and franja.mean(axis=1).max() > 0.5:
            return True
    return False


def hoja(video: Path, destino: Path, fps: int = 2) -> Path:
    """Hoja de contacto a `fps` fotogramas por segundo, para revisar a ojo."""
    n = max(int(duracion(Path(video)) * fps), 1)
    cols = 8
    filas = -(-n // cols)
    r = _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(video), "-vf",
              f"fps={fps},scale=270:-2,tile={cols}x{filas}", "-frames:v", "1", "-q:v", "3", str(destino)])
    if r.returncode != 0:
        raise ErrorVariante(f"No se pudo hacer la hoja: {r.stderr[-300:]}")
    return Path(destino)


# ---------------------------------------------------------------------------
# Control: el mismo que un vídeo normal
# ---------------------------------------------------------------------------
def controlar(video: Path, clips: int = 0) -> dict:
    """Comprobador técnico (formato, bandas → 1080:1920, audio, metadatos) y
    movimiento (media ≥ 2 y ninguna mitad < 1,5). `ok` solo si pasan los dos."""
    cmd = [sys.executable, "-m", "src.comprobador_video", str(video), "--json"]
    if clips:
        cmd += ["--clips", str(clips)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=str(RAIZ))
    try:
        tecnico = json.loads(r.stdout)
    except ValueError:
        tecnico = {"error": (r.stderr or r.stdout)[-400:]}
    m = subprocess.run([sys.executable, str(RAIZ / "scripts" / "medir_movimiento.py"), str(video)],
                       capture_output=True, text=True, timeout=600, cwd=str(RAIZ))
    return {"ok": r.returncode == 0 and m.returncode == 0, "tecnico_ok": r.returncode == 0,
            "movimiento_ok": m.returncode == 0, "tecnico": tecnico,
            "movimiento": (m.stdout or m.stderr).strip()[-300:]}


# ---------------------------------------------------------------------------
# Gancho con Haiku
# ---------------------------------------------------------------------------
def gancho_valido(texto: str) -> bool:
    t = " ".join((texto or "").split())
    return 20 <= len(t) <= 95 and not _PRECIO.search(t) and not _PROHIBIDO.search(t)


def ganchos(titulo: str, caption: str = "", actual: str = "", n: int = MAX_VARIANTES) -> list[str]:
    """`n` ganchos nuevos para el producto (Haiku, tarea «texto»; el coste lo
    apunta el cliente de Claude). Los que traen precio, cupón o superlativos se tiran."""
    from src.tiktok_shop.api import claude

    sistema = PROMPT_GANCHO.read_text(encoding="utf-8")
    usuario = (f"Producto: {titulo}\nCaption del vídeo: {caption or '-'}\n"
               f"Gancho que ya lleva el vídeo (no lo repitas): {actual or 'desconocido'}\n"
               f"Escribe {n + 2} ganchos.")
    datos = claude.generate_json(sistema, usuario, tarea="texto")
    lista = datos.get("ganchos") if isinstance(datos, dict) else datos
    vistos: list[str] = []
    for g in lista or []:
        g = " ".join(str(g).split())
        if gancho_valido(g) and g.lower() not in [v.lower() for v in vistos] and g.lower() != actual.lower():
            vistos.append(g)
    if len(vistos) < n:
        raise ErrorVariante(f"Haiku solo dio {len(vistos)} ganchos válidos de {n}: {lista}")
    return vistos[:n]


# ---------------------------------------------------------------------------
# Anti-duplicado (lógica pura sobre los documentos `rv`)
# ---------------------------------------------------------------------------
def _id(x) -> str:
    return str(x or "").split("|")[-1]


def familias(docs: list[dict]) -> dict[str, str]:
    """id → id del original de su familia (solo de los que tienen variantes o lo son)."""
    fam: dict[str, str] = {}
    for d in docs:
        de = _id((d.get("variante") or {}).get("de"))
        if de:
            fam[_id(d.get("id"))] = de
            fam[de] = de
    return fam


def _dia(ts, tz) -> dt.date | None:
    try:
        return dt.datetime.fromtimestamp(float(ts), tz).date() if ts else None
    except (TypeError, ValueError, OSError):
        return None


def bloqueadas(docs: list[dict], hoy: dt.date, tz=None, dias: int = DIAS_ENTRE) -> dict[str, str]:
    """Los vídeos SIN subir de una familia que hoy no se pueden publicar, con el
    motivo. Una variante no sale antes que su original ni con menos de `dias`
    días desde la última subida de su familia (el original incluido)."""
    if tz is None:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("Europe/Madrid")
    fam = familias(docs)
    por_id = {_id(d.get("id")): d for d in docs}
    ultima: dict[str, dt.date] = {}
    for i, raiz in fam.items():
        d = por_id.get(i) or {}
        dia = _dia(d.get("uploaded_at"), tz) if d.get("uploaded") else None
        if dia and (raiz not in ultima or dia > ultima[raiz]):
            ultima[raiz] = dia
    out: dict[str, str] = {}
    for i, raiz in fam.items():
        d = por_id.get(i)
        if not d or d.get("uploaded"):
            continue
        es_variante = i != raiz
        original = por_id.get(raiz) or {}
        if es_variante and not original.get("uploaded"):
            out[i] = "su original aún no se ha subido"
            continue
        u = ultima.get(raiz)
        if u is not None and (hoy - u).days < dias:
            libre = u + dt.timedelta(days=dias)
            out[i] = f"su familia subió el {u:%d/%m}: no antes del {libre:%d/%m}"
    return out


def una_por_familia(ids: list[str], fam: dict[str, str]) -> list[str]:
    """De una lista ya ordenada, deja solo el primero de cada familia (nunca dos
    variantes —ni variante y original— el mismo día)."""
    vistas: set[str] = set()
    out = []
    for i in ids:
        raiz = fam.get(_id(i))
        if raiz and raiz in vistas:
            continue
        if raiz:
            vistas.add(raiz)
        out.append(i)
    return out


def hoy_madrid() -> dt.date:
    from zoneinfo import ZoneInfo

    return dt.datetime.now(ZoneInfo("Europe/Madrid")).date()


def estado_publicacion(usuario: str, hoy: dt.date | None = None) -> dict:
    """Para el plan del día: familias y qué no se puede subir hoy."""
    from src.replicar_viral import video as rv_video

    docs = rv_video.listar(usuario)
    return {"familia": familias(docs), "bloqueadas": bloqueadas(docs, hoy or hoy_madrid())}


# ---------------------------------------------------------------------------
# Registro en Mis tandas (sin semáforo: queda «sin revisar»)
# ---------------------------------------------------------------------------
def registrar_variante(usuario: str, origen_id: str, mp4: Path, *, n: int, gancho: str,
                       receta_: dict | None = None) -> dict:
    """Da de alta la variante como una réplica más, con el producto, el caption
    y los hashtags del original. No le pone semáforo: hay que revisarla."""
    from src.mis_tandas import servicio as mt
    from src.replicar_viral import servicio, video as rv_video

    origen_id = _id(origen_id)
    if n not in RECETAS:
        raise ErrorVariante(f"Solo hay variantes 1..{MAX_VARIANTES}; no «{n}».")
    if not gancho_valido(gancho):
        raise ErrorVariante("Falta el gancho que lleva la variante (o trae precio, cupón o superlativo).")
    original = rv_video.ver(usuario, origen_id)
    if (original.get("variante") or {}).get("de"):
        raise ErrorVariante("Ese vídeo ya es una variante: las variantes se hacen del original.")
    color = ((mt.semaforos(usuario) or {}).get(f"rv|{origen_id}") or {}).get("color")
    if color != "verde":
        raise ErrorVariante(f"El original rv|{origen_id} no está en verde ({color or 'sin semáforo'}).")
    hermanas = [d for d in rv_video.listar(usuario) if _id((d.get("variante") or {}).get("de")) == origen_id]
    if len(hermanas) >= MAX_VARIANTES:
        raise ErrorVariante(f"rv|{origen_id} ya tiene {MAX_VARIANTES} variantes.")
    if any((d.get("variante") or {}).get("n") == n for d in hermanas):
        raise ErrorVariante(f"La variante {n} de rv|{origen_id} ya está registrada.")
    prod = original.get("producto") or {}
    nota = (f"VARIANTE {n} de rv|{origen_id} (sin créditos) · gancho «{gancho}». "
            f"No subir el mismo día que otro de su familia ni con menos de {DIAS_ENTRE} días entre ellos "
            f"(`variantes publicables`).")
    doc = rv_video.registrar(
        usuario, modo=original.get("modo") or "con_ia", origen=Path(mp4), titulo=prod.get("titulo", ""),
        url_viral=original.get("url", ""), product_id=prod.get("product_id", ""),
        product_url=prod.get("product_url", ""), tienda=prod.get("tienda", ""),
        caption=original.get("caption", ""), hashtags=original.get("hashtags") or [], notas=nota)
    doc["variante"] = {"de": origen_id, "n": n, "gancho": gancho, "receta": receta_ or {},
                       "creado_at": time.time()}
    for campo in ("catalogo_ref", "epoca"):
        if original.get(campo) and not doc.get(campo):
            doc[campo] = original[campo]
    servicio.guardar(doc, indexar=False)
    return doc


# ---------------------------------------------------------------------------
# Tanda de variantes de un vídeo
# ---------------------------------------------------------------------------
def crear(video: Path, origen_id: str, textos: list[str], salida: Path, *, numeros=(1, 2, 3),
          espejo: bool = False, conservar_audio: bool = False, base_musica: Path | None = None) -> dict:
    """Hace las variantes pedidas, las controla y deja al lado su hoja a 2 fps
    y un `variantes.json` con todo. No registra nada."""
    video, salida = Path(video), Path(salida)
    numeros = list(numeros)
    if len(textos) < len(numeros):
        raise ErrorVariante(f"Hacen falta {len(numeros)} ganchos y hay {len(textos)}.")
    malos = [t for t in textos[: len(numeros)] if not gancho_valido(t)]
    if malos:
        raise ErrorVariante(f"Ganchos que no valen (precio, cupón, superlativo o largo): {malos}")
    a = analizar(video)
    pistas = [] if conservar_audio else banco(base_musica)
    hechas = []
    for n, texto in zip(numeros, textos):
        rec = receta(a, n, espejo=espejo, conservar_audio=conservar_audio)
        destino = salida / f"{_id(origen_id)}_var{n}.mp4"
        pista = None if conservar_audio else elegir_pista(_id(origen_id), n, pistas)
        info = montar(video, a, rec, texto, destino, pista)
        control = controlar(destino, clips=len(a["planos"]) if len(a["planos"]) > 1 else 0)
        control["restos_pildora"] = restos_pildora(destino, info["pildora_caja"], info["gancho_hasta_s"])
        control["ok"] = control["ok"] and not control["restos_pildora"]
        hoja(destino, destino.with_suffix(".hoja.jpg"))
        hechas.append({"n": n, "mp4": str(destino), "hoja": str(destino.with_suffix(".hoja.jpg")),
                       "receta": rec, **info, "control_ok": control["ok"], "control": control})
    res = {"origen": _id(origen_id), "video": str(video), "analisis": a, "variantes": hechas,
           "ok": all(v["control_ok"] for v in hechas)}
    (salida / f"{_id(origen_id)}_variantes.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="variantes", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("analizar", help="píldora, flecha y planos de un MP4")
    p.add_argument("video")
    p = sub.add_parser("crear", help="hace las variantes de un MP4 en verde (no registra)")
    p.add_argument("video")
    p.add_argument("--id", required=True, help="id del original (rv|…)")
    p.add_argument("--ganchos", required=True, help="textos separados por |, uno por variante")
    p.add_argument("--n", default="1,2,3", help="qué variantes hacer (1,2,3)")
    p.add_argument("--espejo", action="store_true",
                   help="SOLO si el producto es simétrico y no lleva texto ni logos")
    p.add_argument("--conservar-audio", action="store_true", help="vídeo hablado: ni música nueva ni reorden")
    p.add_argument("--musica-dir", default="")
    p.add_argument("--salida", required=True)
    p = sub.add_parser("hoja", help="hoja de contacto a 2 fps")
    p.add_argument("video")
    p.add_argument("destino")
    p = sub.add_parser("ganchos", help="ganchos nuevos con Haiku (dentro de la app)")
    p.add_argument("--titulo", required=True)
    p.add_argument("--caption", default="")
    p.add_argument("--actual", default="")
    p.add_argument("--n", type=int, default=MAX_VARIANTES)
    p = sub.add_parser("registrar", help="alta en Mis tandas, sin semáforo (dentro de la app)")
    p.add_argument("usuario")
    p.add_argument("origen_id")
    p.add_argument("mp4")
    p.add_argument("--n", type=int, required=True)
    p.add_argument("--gancho", required=True)
    p = sub.add_parser("publicables", help="familias y qué no se puede subir hoy (dentro de la app)")
    p.add_argument("usuario")
    p.add_argument("--fecha", default="")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "analizar":
            res = analizar(Path(a.video))
        elif a.cmd == "crear":
            res = crear(Path(a.video), a.id, [t.strip() for t in a.ganchos.split("|") if t.strip()],
                        Path(a.salida), numeros=[int(x) for x in a.n.split(",")], espejo=a.espejo,
                        conservar_audio=a.conservar_audio, base_musica=Path(a.musica_dir) if a.musica_dir else None)
            for v in res["variantes"]:
                v.pop("control", None)
            res.pop("analisis", None)
        elif a.cmd == "hoja":
            res = {"hoja": str(hoja(Path(a.video), Path(a.destino)))}
        elif a.cmd == "ganchos":
            res = {"ganchos": ganchos(a.titulo, a.caption, a.actual, a.n)}
        elif a.cmd == "registrar":
            d = registrar_variante(a.usuario, a.origen_id, Path(a.mp4), n=a.n, gancho=a.gancho)
            res = {"id": f"rv|{d['id']}", "variante": d["variante"], "semaforo": "sin revisar"}
        else:
            hoy = dt.date.fromisoformat(a.fecha) if a.fecha else None
            res = estado_publicacion(a.usuario, hoy)
    except ErrorVariante as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0 if res.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
