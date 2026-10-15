"""Personaje B del vídeo hablado: la mascota de MasterPicks (3D, de Flow).

La mascota no se dibuja: sale de las poses que se generaron en Google Flow con
Nano Banana 2 (oct-2026, fondo verde #00FF00, 1024×1024). Casi todas son
EDICIONES de la pose base («cambia solo la boca», «solo el brazo»…), así que
la cabeza y el cuerpo coinciden píxel a píxel y se pueden combinar por zonas:

- **Brazos**: de cada pose se toma solo la zona que cambia respecto a la base
  (sin la cara) y se pega sobre la base. Espejando esa zona respecto al centro
  del cuerpo sale el mismo gesto con el otro brazo, y sumando las dos, «abre».
- **Boca**: parches de la zona de la boca de la base (sonrisa), «talk-a»
  (abierta con lengua), «talk-b» («o») y «sleep» (cerrada).
- **Ojos**: parche de la zona de los ojos de la base o de «blink».
- **Saludo**: alterna wave-in / wave / wave-out mientras dura el gesto.

`preparar_assets()` hace todo eso una vez y deja PNGs + `rig.json` en una
carpeta (en Drive: `BIBLIOTECA_PRONOSTICOS_CLIPS/munecos/mascota/`).
`PersonajeMascota` los carga y pinta cada fotograma.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from src.pronosticos.rig_hablado import Estado

# Originales de Flow (nombres de la descarga del 6-oct-2026, /tmp/flow/out).
FUENTES = {
    "base": "g_9",          # pose de reposo (la «mascota-idle»)
    "blink": "c_blink",     # ojos cerrados
    "talk_a": "n_37",       # boca abierta con lengua
    "talk_b": "tb_4",       # boca en «o»
    "sleep": "n_24",        # boca cerrada (y ojos cerrados: solo se usa la boca)
    "senala": "pt_1",       # brazo señalando a un lado
    "rasca": "n_25",        # mano a la cabeza («hmm»)
    "saluda": "r1_2",       # saludo (brazo arriba)
    "saluda_in": "c_wave_in",
    "saluda_out": "c_wave_out",
}

# Zona de la cara en el original 1024² (no se toca al pegar brazos).
CARA = (300, 300, 724, 610)


def _croma(im: Image.Image) -> Image.Image:
    a = np.asarray(im.convert("RGB")).astype(np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    spill = g - np.maximum(r, b)
    alpha = 1.0 - np.clip((spill - 40) / 90, 0, 1)
    g2 = np.where(spill > 0, np.maximum(r, b), g)
    return Image.fromarray(np.dstack([r, np.minimum(g, g2), b, alpha * 255]).clip(0, 255).astype(np.uint8), "RGBA")


def _cambio(base: Image.Image, otra: Image.Image, thr=22, grow=21, feather=9) -> np.ndarray:
    a = np.asarray(base).astype(np.float32)
    b = np.asarray(otra).astype(np.float32)
    d = Image.fromarray(np.abs(a - b).mean(2).clip(0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(3))
    m = Image.fromarray(((np.asarray(d) > thr) * 255).astype(np.uint8))
    m = m.filter(ImageFilter.MaxFilter(grow)).filter(ImageFilter.GaussianBlur(feather))
    return np.asarray(m).astype(np.float32) / 255.0


def _sin_cara(m: np.ndarray, margen: int = 12) -> np.ndarray:
    m = m.copy()
    x0, y0, x1, y1 = CARA
    m[y0 - margen:y1 + margen, x0 - margen:x1 + margen] = 0
    return np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(4))) / 255.0


def _mezclar(a: np.ndarray, b: np.ndarray, m: np.ndarray) -> np.ndarray:
    return a * (1 - m[..., None]) + b * m[..., None]


def brazo_diagonal(im: Image.Image, ang: float = 45.0) -> Image.Image:
    """Sube en diagonal el brazo DERECHO (de la pantalla) que apunta en horizontal.

    Flow solo dio la pose de señalar en horizontal y el usuario quiere que la
    mascota señale arriba, hacia los escudos del marcador. Se recorta el brazo
    (las filas que salen mucho más allá del cuerpo), se gira `ang` grados
    alrededor del hombro y se deja un disco del brazo original como hombro
    para tapar la junta. Para el brazo izquierdo: espejar, llamar y espejar.
    """
    a = np.asarray(im.convert("RGBA")).copy()
    al = a[..., 3] > 128
    H, W = al.shape
    der = np.array([np.where(r)[0].max() if r.any() else 0 for r in al])
    ref = np.median(der[int(H * .3):int(H * .75)])
    filas = np.where(der > ref + 40)[0]
    if not len(filas):
        return im
    y0, y1 = filas.min(), filas.max()
    borde = int(np.median(der[[max(0, y0 - 15), min(H - 1, y1 + 15)]]))
    piv = (borde - 14, (y0 + y1) / 2)
    radio = (y1 - y0) / 2 + 4
    zona = np.zeros(al.shape, bool)
    zona[y0 - 6:y1 + 7, borde - 14:] = True
    brazo = np.zeros_like(a)
    brazo[zona] = a[zona]
    yy, xx = np.mgrid[:H, :W]
    hombro = ((xx - piv[0]) ** 2 + (yy - piv[1]) ** 2 < radio ** 2) & zona
    corte = np.zeros(al.shape, bool)
    corte[y0 - 6:y1 + 7, borde - 2:] = True
    cuerpo = a.copy()
    cuerpo[corte & ~hombro, 3] = 0
    res = Image.fromarray(cuerpo, "RGBA")
    res.alpha_composite(Image.fromarray(brazo, "RGBA").rotate(ang, resample=Image.BICUBIC, center=piv))
    return res


def diagonalizar(assets_dir: str, ang: float = 45.0) -> None:
    """`pose_senala_lado_{d,i}` (horizontal) → `pose_senala_{d,i}` (diagonal arriba)."""
    d = Path(assets_dir)
    for lado in ("d", "i"):
        lado_png = d / f"pose_senala_lado_{lado}.png"
        if not lado_png.exists():
            (d / f"pose_senala_{lado}.png").rename(lado_png)
        im = Image.open(lado_png)
        if lado == "i":
            im = brazo_diagonal(im.transpose(Image.FLIP_LEFT_RIGHT), ang).transpose(Image.FLIP_LEFT_RIGHT)
        else:
            im = brazo_diagonal(im, ang)
        im.save(d / f"pose_senala_{lado}.png")


def preparar_assets(raw_dir: str, out_dir: str, alto: int = 720) -> None:
    """Genera las capas del rig a partir de los originales de Flow."""
    raw = Path(raw_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    src = {k: Image.open(raw / f"{v}.jpg").convert("RGB") for k, v in FUENTES.items()}
    base = src["base"]
    B = np.asarray(base).astype(np.float32)
    W = base.width

    # Eje de simetría del cuerpo (centro de la barriga en la base).
    al = np.asarray(_croma(base).getchannel("A")) > 128
    filas = np.where(al.any(1))[0]
    y_barriga = int(filas[0] + (filas[-1] - filas[0]) * 0.62)
    xs = np.where(al[y_barriga])[0]
    eje = (xs[0] + xs[-1]) / 2.0

    def espejo(arr: np.ndarray) -> np.ndarray:
        # refleja respecto a `eje` (no al centro de la imagen)
        flip = arr[:, ::-1]
        desp = int(round(2 * eje - (W - 1)))
        return np.roll(flip, desp, axis=1)

    poses: dict[str, np.ndarray] = {"reposo": B}
    deltas = {}
    for k in ("senala", "rasca", "saluda", "saluda_in", "saluda_out"):
        P = np.asarray(src[k]).astype(np.float32)
        m = _sin_cara(_cambio(base, src[k]))
        deltas[k] = (P, m)
        poses[f"{k}_d"] = _mezclar(B, P, m)
        poses[f"{k}_i"] = _mezclar(B, espejo(P), espejo(m))
    P, m = deltas["senala"]
    poses["abre"] = _mezclar(poses["senala_d"], espejo(P), espejo(m))

    # Encuadre común: la caja que cubre todas las poses, con margen.
    keyed = {k: _croma(Image.fromarray(v.clip(0, 255).astype(np.uint8))) for k, v in poses.items()}
    cajas = [im.getchannel("A").point(lambda v: 255 if v > 10 else 0).getbbox() for im in keyed.values()]
    x0 = min(c[0] for c in cajas) - 8
    y0 = min(c[1] for c in cajas) - 8
    x1 = max(c[2] for c in cajas) + 8
    y1 = max(c[3] for c in cajas) + 4
    esc = alto / (y1 - y0)
    tam = (int(round((x1 - x0) * esc)), alto)

    def guardar(im: Image.Image, nombre: str) -> None:
        im.crop((x0, y0, x1, y1)).resize(tam, Image.LANCZOS).save(out / f"{nombre}.png")

    for k, im in keyed.items():
        guardar(im, f"pose_{'senala_lado_' + k[-1] if k.startswith('senala_') else k}")

    # Parches de cara: imagen completa recortada + máscara de su zona.
    zona_boca = np.maximum(_cambio(base, src["talk_a"], grow=31), _cambio(base, src["talk_b"], grow=31))
    zona_ojos = _cambio(base, src["blink"], grow=25)
    zona_ojos[int(CARA[1] + 210):] = 0   # «blink» también tocó un poco la boca: solo ojos

    def parche(rgb: Image.Image, zona: np.ndarray, nombre: str) -> None:
        k = _croma(rgb)
        a = np.asarray(k).copy()
        a[..., 3] = (a[..., 3].astype(np.float32) * zona).astype(np.uint8)
        guardar(Image.fromarray(a, "RGBA"), nombre)

    parche(base, zona_boca, "boca_pequena")
    parche(src["talk_a"], zona_boca, "boca_abierta")
    parche(src["talk_b"], zona_boca, "boca_o")
    parche(src["sleep"], zona_boca, "boca_cerrada")
    media = Image.fromarray(((np.asarray(base).astype(np.float32) + np.asarray(src["talk_a"])) / 2).astype(np.uint8))
    parche(media, zona_boca, "boca_media")
    parche(base, zona_ojos, "ojos_abiertos")
    parche(src["blink"], zona_ojos, "ojos_cerrados")
    (out / "rig.json").write_text(json.dumps({
        "tam": tam, "eje_x": (eje - x0) * esc,
        "poses": sorted(keyed), "fuentes": FUENTES,
    }, indent=1), encoding="utf-8")
    diagonalizar(str(out))


class PersonajeMascota:
    """La mascota de MasterPicks como personaje del rig hablado."""

    reposo = "reposo"
    # senala_d/i = brazo en diagonal hacia el escudo de ese lado del marcador
    gestos = ["senala_d", "senala_i", "abre", "saluda_d", "saluda_i"]
    peso_gesto = {"senala_d": 2.2, "senala_i": 2.2, "abre": 1.2, "saluda_d": 0.8,
                  "saluda_i": 0.6}
    # En el vídeo: de la punta de la antena a los pies, y dónde caen los pies
    # (1080×1920). Más pequeña que el viejo (es ancha) y con los pies donde
    # Yeison pone los zapatos de su muñeco.
    alto_en_video = 640
    pies_en_video = 1683
    lado_gesto = {"senala_d": -1, "senala_i": 1, "saluda_d": -1, "saluda_i": 1}

    def __init__(self, assets_dir: str):
        d = Path(assets_dir)
        meta = json.loads((d / "rig.json").read_text(encoding="utf-8"))
        self.size = tuple(meta["tam"])
        self._img = {p.stem: Image.open(p).convert("RGBA") for p in d.glob("*.png")}
        # el gesto «dedo»/«senala» del motor genérico cae en señalar
        self.alias = {"dedo_arriba": "senala_d", "senala": "senala_d", "dedo": "senala_d"}

    def _pose(self, nombre: str, t: float) -> Image.Image:
        nombre = self.alias.get(nombre, nombre)
        if nombre.startswith("saluda"):
            lado = nombre[-1]
            ciclo = ["saluda_in", "saluda", "saluda_out", "saluda"]
            nombre = f"{ciclo[int(t * 7) % 4]}_{lado}"
        return self._img.get(f"pose_{nombre}", self._img["pose_reposo"])

    def frame(self, est: Estado) -> Image.Image:
        a = self._pose(est.pose_a, est.t)
        b = self._pose(est.pose_b, est.t)
        u = est.mezcla
        if a is b or u >= 1.0:
            im = b.copy()
        elif u <= 0.0:
            im = a.copy()
        else:
            # cambio rápido: el «pop» de escala de abajo disimula el fundido
            im = Image.blend(a, b, 0.0 if u < 0.35 else (1.0 if u > 0.65 else (u - 0.35) / 0.3))
        boca = {"cerrada": "boca_cerrada", "pequena": "boca_pequena", "media": "boca_media",
                "abierta": "boca_abierta", "o": "boca_o"}[est.boca]
        im.alpha_composite(self._img[boca])
        if est.parpado > 0.5:
            im.alpha_composite(self._img["ojos_cerrados"])
        # Vida: estirar/aplastar con la voz, «pop» en los cambios de gesto,
        # vaivén e inclinación (la cabeza es todo el cuerpo).
        W, H = self.size
        pop = math.sin(min(1.0, max(0.0, u)) * math.pi) * 0.05 if est.pose_a != est.pose_b else 0.0
        sy = 1.0 + 0.025 * est.habla + pop + 0.012 * math.sin(est.t * 2 * math.pi * 0.8)
        sx = 1.0 - 0.6 * (sy - 1.0)
        nw, nh = int(W * sx), int(H * sy)
        im = im.resize((nw, nh), Image.BILINEAR)
        lienzo = Image.new("RGBA", (int(W * 1.12), int(H * 1.10)), (0, 0, 0, 0))
        lienzo.alpha_composite(im, ((lienzo.width - nw) // 2, lienzo.height - nh))
        ang = 0.6 * est.cabeza_rot - 0.25 * est.cabeza_dy
        return lienzo.rotate(ang, resample=Image.BICUBIC, center=(lienzo.width / 2, lienzo.height))

    @property
    def size_out(self):
        W, H = self.size
        return (int(W * 1.12), int(H * 1.10))
