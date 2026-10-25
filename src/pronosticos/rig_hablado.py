"""Rig 2D «hablado» para el vídeo de C1: un muñeco que habla con la voz.

Imita lo que hace «Animate from audio» de Adobe Express (lo que usa
@analisis_yeison), pero en local y sin API:

- **Boca** con la voz: volumen (RMS) para la apertura y timbre (centroide del
  espectro) para elegir entre boca ancha con dientes y boca redonda («o/u»).
- **Parpadeo** aleatorio (a veces doble), y mirada que cambia al empezar frase.
- **Gestos**: al arrancar cada frase (tras una pausa de la voz) el muñeco
  cambia de postura de brazos; con `marcas` se fuerzan gestos en momentos
  concretos (cada pick, el CTA). En las pausas largas vuelve a reposo.
- **Cabeza**: vaivén lento, cabeceo en los acentos y leve inclinación hacia el
  lado del gesto. Cejas arriba en los acentos.

El motor no sabe nada del personaje: cualquier clase con `size`, `poses`,
`gestos`, `reposo` y `frame(estado)` sirve. Hay dos:
`PersonajeViejo` (dibujado aquí, vectorial) y `PersonajeMascota`
(`rig_mascota.py`, a partir de las poses de Flow).

Solo usa numpy + PIL + ffmpeg (nada de MoviePy): los fotogramas van por
tubería a ffmpeg en `video_hablado.py`.
"""

from __future__ import annotations

import math
import random
import subprocess
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

FPS = 30


# ---------------------------------------------------------------------------
# 1. Análisis de la voz
# ---------------------------------------------------------------------------

@dataclass
class Voz:
    """Lo que el rig necesita saber de la voz, una muestra por fotograma."""
    env: np.ndarray          # volumen 0..1 (ya suavizado: ataque rápido, caída lenta)
    timbre: np.ndarray       # 0 = grave/redondo («o», «u») · 1 = brillante («e», «i», «s»)
    frases: list[float]      # inicio de cada frase (s): primera voz tras una pausa
    acentos: list[float]     # picos de volumen (s), separados ≥0,35 s
    dur: float
    fps: int = FPS


def _leer_pcm(audio_path: str, sr: int = 16000) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-v", "quiet", "-i", audio_path, "-ac", "1", "-ar", str(sr),
         "-f", "s16le", "-"],
        capture_output=True, timeout=300,
    ).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0


def analizar_voz(audio_path: str, fps: int = FPS, pausa_min: float = 0.18) -> Voz:
    sr = 16000
    x = _leer_pcm(audio_path, sr)
    dur = len(x) / sr
    hop = sr // fps
    n = max(1, int(math.ceil(len(x) / hop)))
    x = np.pad(x, (0, n * hop + hop - len(x)))
    win = np.hanning(2 * hop).astype(np.float32)
    freqs = np.fft.rfftfreq(2 * hop, 1 / sr)
    rms = np.zeros(n, np.float32)
    cent = np.zeros(n, np.float32)
    for i in range(n):
        seg = x[i * hop:i * hop + 2 * hop]
        rms[i] = float(np.sqrt(np.mean(seg ** 2)))
        mag = np.abs(np.fft.rfft(seg * win))
        band = (freqs > 150) & (freqs < 6000)
        s = mag[band].sum()
        cent[i] = float((mag[band] * freqs[band]).sum() / s) if s > 0 else 0.0

    p = float(np.percentile(rms, 95)) or 1e-6
    raw_env = np.clip(rms / p, 0, 1)
    raw_env = np.where(raw_env < 0.08, 0.0, raw_env)
    # Ataque rápido y caída algo más lenta: la boca no «tirita» entre sílabas.
    env = np.zeros(n, np.float32)
    for i in range(n):
        prev = env[i - 1] if i else 0.0
        a = 0.85 if raw_env[i] > prev else 0.45
        env[i] = prev + a * (raw_env[i] - prev)

    voiced = raw_env > 0.0
    lo, hi = np.percentile(cent[voiced], [10, 90]) if voiced.any() else (500, 3000)
    timbre = np.clip((cent - lo) / max(1.0, hi - lo), 0, 1)
    timbre = np.convolve(timbre, np.ones(3) / 3, mode="same")

    # Frases: la primera voz tras una pausa de al menos `pausa_min`.
    frases: list[float] = []
    silencio = int(pausa_min * fps)
    callado = silencio  # el principio cuenta como pausa
    for i in range(n):
        if raw_env[i] < 0.12:
            callado += 1
        else:
            if callado >= silencio:
                frases.append(i / fps)
            callado = 0

    # Acentos: máximos locales altos del volumen.
    acentos: list[float] = []
    sm = np.convolve(raw_env, np.ones(5) / 5, mode="same")
    ult = -1.0
    for i in range(2, n - 2):
        if sm[i] > 0.72 and sm[i] >= sm[i - 2:i + 3].max() and i / fps - ult >= 0.35:
            acentos.append(i / fps)
            ult = i / fps
    return Voz(env=env, timbre=timbre, frases=frases, acentos=acentos, dur=dur, fps=fps)


# ---------------------------------------------------------------------------
# 2. Plan de la animación (qué hace el muñeco en cada fotograma)
# ---------------------------------------------------------------------------

@dataclass
class Estado:
    t: float
    boca: str = "cerrada"        # nombre del estado de boca del personaje
    apertura: float = 0.0        # 0..1 (por si el personaje la usa continua)
    parpado: float = 0.0         # 0 abierto · 1 cerrado
    pose_a: str = "reposo"
    pose_b: str = "reposo"
    mezcla: float = 1.0          # 0 = pose_a · 1 = pose_b (ya suavizado)
    cabeza_rot: float = 0.0      # grados (+ = hacia la izquierda de la pantalla)
    cabeza_dy: float = 0.0       # px (+ = abajo): cabeceo
    ceja: float = 0.0            # 0..1 cejas arriba
    mirada: tuple[float, float] = (0.0, 0.0)   # -1..1
    cuerpo_dy: float = 0.0
    habla: float = 0.0           # volumen actual 0..1


@dataclass
class Plan:
    estados: list[Estado] = field(default_factory=list)
    cambios: list[tuple[float, str]] = field(default_factory=list)


def _ease(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def elegir_boca(env: float, timbre: float) -> str:
    """Cinco estados como en un rig de Adobe: cerrada, pequeña, media, abierta y «o»."""
    if env < 0.10:
        return "cerrada"
    if env < 0.30:
        return "pequena"
    if timbre < 0.30 and env < 0.80:
        return "o"
    if env < 0.62:
        return "media"
    return "abierta"


def planificar(voz: Voz, personaje, marcas: list[tuple[float, str]] | None = None,
               semilla: int = 7, transicion: float = 0.28, min_hold: float = 1.1) -> Plan:
    """Decide parpadeos, gestos y cabeza para toda la duración.

    `marcas` = [(segundo, pose)] fuerza un gesto en ese momento (p. ej. la pose
    «dedo» al decir cada pick). Las frases del audio rellenan el resto.
    """
    rnd = random.Random(semilla)
    fps = voz.fps
    n = len(voz.env)
    dur = n / fps

    # --- gestos -----------------------------------------------------------
    forzadas = sorted(marcas or [], key=lambda m: m[0])
    cambios: list[tuple[float, str]] = [(0.0, personaje.reposo)]
    actual = personaje.reposo
    ult_cambio = -10.0
    eventos = sorted([(t, None) for t in voz.frases] + [(t, p) for t, p in forzadas], key=lambda e: (e[0], e[1] is not None))
    for t, forzada in eventos:
        if forzada is None:
            if t - ult_cambio < min_hold:
                continue
            # no repetir la misma postura dos veces seguidas
            ops = [g for g in personaje.gestos if g != actual]
            pesos = [personaje.peso_gesto.get(g, 1.0) for g in ops]
            nueva = rnd.choices(ops, weights=pesos)[0]
        else:
            nueva = forzada
            if t - ult_cambio < 0.45 and cambios and cambios[-1][0] > 0:
                cambios.pop()  # la forzada manda sobre una de frase muy pegada
        if nueva != actual:
            cambios.append((max(0.0, t - 0.08), nueva))   # el gesto se anticipa un pelín
            actual = nueva
            ult_cambio = t
    # Vuelta a reposo en pausas largas (≥0,9 s sin voz) y al final.
    callado = 0
    reposos: list[float] = []
    for i in range(n):
        if voz.env[i] < 0.05:
            callado += 1
            if callado == int(0.9 * fps):
                reposos.append(i / fps - 0.5)
        else:
            callado = 0
    for t in reposos:
        prev = [c for c in cambios if c[0] <= t]
        sig = [c for c in cambios if c[0] > t]
        if prev and prev[-1][1] != personaje.reposo and (not sig or sig[0][0] - t > 0.8):
            cambios.append((t, personaje.reposo))
    cambios.sort()

    # --- parpadeos --------------------------------------------------------
    parp = np.zeros(n, np.float32)
    t = rnd.uniform(0.6, 1.8)
    while t < dur:
        dobles = 2 if rnd.random() < 0.18 else 1
        for k in range(dobles):
            c = t + k * 0.24
            for i in range(int((c - 0.06) * fps), int((c + 0.14) * fps) + 1):
                if 0 <= i < n:
                    u = (i / fps - c)
                    v = 1.0 - abs(u) / (0.06 if u < 0 else 0.14)
                    parp[i] = max(parp[i], min(1.0, max(0.0, v * 1.4)))
        t += rnd.uniform(2.2, 4.8)

    # --- cabeza -----------------------------------------------------------
    nod = np.zeros(n, np.float32)
    ceja = np.zeros(n, np.float32)
    for a in voz.acentos:
        i0 = int(a * fps)
        for i in range(i0, min(n, i0 + int(0.5 * fps))):
            u = (i - i0) / fps
            nod[i] += 7.0 * math.sin(min(1.0, u / 0.12) * math.pi / 2) * math.exp(-u / 0.18)
            ceja[i] = max(ceja[i], math.exp(-u / 0.30))
    for f in voz.frases:
        i0 = int(f * fps)
        for i in range(i0, min(n, i0 + int(0.6 * fps))):
            ceja[i] = max(ceja[i], 0.7 * math.exp(-(i - i0) / fps / 0.35))

    # inclinación hacia el lado del gesto (lado -1/0/+1 que declara el personaje)
    incl_obj = np.zeros(n, np.float32)
    for (t0, pose), sig in zip(cambios, cambios[1:] + [(dur + 1, None)]):
        lado = personaje.lado_gesto.get(pose, 0)
        incl_obj[int(t0 * fps):int(sig[0] * fps)] = 3.0 * lado
    incl = np.zeros(n, np.float32)
    for i in range(n):
        prev = incl[i - 1] if i else 0.0
        incl[i] = prev + 0.10 * (incl_obj[i] - prev)

    # mirada: cambia a veces al empezar frase
    mir = np.zeros((n, 2), np.float32)
    objetivo = (0.0, 0.0)
    marcas_mirada = {int(f * fps) for f in voz.frases if rnd.random() < 0.55}
    for i in range(n):
        if i in marcas_mirada:
            objetivo = rnd.choice([(0.0, 0.0), (0.0, 0.0), (-0.7, 0.0), (0.7, 0.0), (0.4, -0.3), (-0.4, -0.3)])
        prev = mir[i - 1] if i else np.zeros(2, np.float32)
        mir[i] = prev + 0.35 * (np.array(objetivo, np.float32) - prev)

    # --- estados por fotograma -------------------------------------------
    estados: list[Estado] = []
    ph1, ph2 = rnd.uniform(0, 6.28), rnd.uniform(0, 6.28)
    ci = 0
    for i in range(n):
        ts = i / fps
        while ci + 1 < len(cambios) and cambios[ci + 1][0] <= ts:
            ci += 1
        t0, pose_b = cambios[ci]
        pose_a = cambios[ci - 1][1] if ci > 0 else pose_b
        mezcla = _ease((ts - t0) / transicion) if ci > 0 else 1.0
        e = float(voz.env[i])
        rot = (1.6 * math.sin(2 * math.pi * 0.31 * ts + ph1)
               + 0.9 * math.sin(2 * math.pi * 0.83 * ts + ph2) * (0.4 + e)
               + float(incl[i]))
        estados.append(Estado(
            t=ts, boca=elegir_boca(e, float(voz.timbre[i])), apertura=e,
            parpado=float(parp[i]), pose_a=pose_a, pose_b=pose_b, mezcla=mezcla,
            cabeza_rot=rot, cabeza_dy=float(nod[i]), ceja=float(ceja[i]),
            mirada=(float(mir[i][0]), float(mir[i][1])),
            cuerpo_dy=1.6 * math.sin(2 * math.pi * 0.9 * ts) + 2.0 * e, habla=e,
        ))
    return Plan(estados=estados, cambios=cambios)


# ---------------------------------------------------------------------------
# 3. Personaje A: el viejo «sabio» tipo Einstein (dibujado, vectorial)
# ---------------------------------------------------------------------------
# Coordenadas en un lienzo local de 600×900 px (el muñeco entero, pies abajo).
# Se dibuja a SS× y se reduce: así sale con antialias.

SS = 2
NEGRO = (20, 20, 20, 255)
PIEL = (245, 178, 128, 255)
PIEL_SOMBRA = (226, 150, 104, 255)
BLANCO = (250, 250, 250, 255)
GRIS_CUERPO = (122, 122, 124, 255)
GAFAS = (62, 62, 66, 255)
BOCA_DENTRO = (92, 30, 34, 255)
LENGUA = (214, 92, 96, 255)
TRAZO = 5            # grosor del contorno (px a 1×)


def _s(v):
    return int(round(v * SS))


def _mask(size):
    return Image.new("L", (size[0] * SS, size[1] * SS), 0)


def _dilatar(mask: Image.Image, r: int) -> Image.Image:
    """Dilatación con disco de radio `r`, solo en la caja de la pieza.

    `MaxFilter` de PIL con núcleo grande sobre el lienzo entero tardaba
    segundos por pieza; así son milisegundos y sin depender de scipy/cv2."""
    box = mask.getbbox()
    if not box:
        return mask
    x0, y0 = max(0, box[0] - r), max(0, box[1] - r)
    x1, y1 = min(mask.width, box[2] + r), min(mask.height, box[3] + r)
    a = np.asarray(mask.crop((x0, y0, x1, y1)))
    pad = np.pad(a, r)
    out = np.zeros_like(a)
    h, w = a.shape
    for dy in range(-r, r + 1):
        span = int(math.sqrt(r * r - dy * dy))
        for dx in range(-span, span + 1):
            np.maximum(out, pad[r + dy:r + dy + h, r + dx:r + dx + w], out=out)
    res = Image.new("L", mask.size, 0)
    res.paste(Image.fromarray(out), (x0, y0))
    return res


def _contorno(capa: Image.Image, mask: Image.Image, color, grosor: float = TRAZO):
    """Pinta `mask` con `color` y un contorno negro alrededor (estilo cartoon)."""
    borde = _dilatar(mask, _s(grosor))
    capa.paste(NEGRO, (0, 0), borde)
    capa.paste(color, (0, 0), mask)


def _pelo_nube(m: Image.Image, cx, cy, rx, ry, semilla=3):
    """Pelo alborotado: nube de mechones redondos + algunas puntas sueltas."""
    rnd = random.Random(semilla)
    d = ImageDraw.Draw(m)
    d.ellipse([_s(cx - rx * 0.86), _s(cy - ry * 0.86), _s(cx + rx * 0.86), _s(cy + ry * 0.86)], fill=255)
    n = 22
    for k in range(n):
        a = math.pi * 2 * k / n + rnd.uniform(-0.08, 0.08)
        if math.sin(a) > 0.6:          # debajo de las orejas no hay pelo
            continue
        r = rnd.uniform(24, 38)
        px, py = cx + rx * 0.84 * math.cos(a), cy + ry * 0.84 * math.sin(a)
        d.ellipse([_s(px - r), _s(py - r), _s(px + r), _s(py + r)], fill=255)
    for k in range(9):                 # puntas de pelo disparadas
        a = rnd.uniform(math.pi * 1.05, math.pi * 1.95) if k < 6 else rnd.choice([math.pi * 0.95, 0.15, math.pi * 0.85, 0.05])
        bx, by = cx + rx * 0.95 * math.cos(a), cy + ry * 0.95 * math.sin(a)
        tx, ty = cx + rx * rnd.uniform(1.18, 1.32) * math.cos(a), cy + ry * rnd.uniform(1.18, 1.32) * math.sin(a)
        nx, ny = -math.sin(a) * 13, math.cos(a) * 13
        d.polygon([(_s(bx + nx), _s(by + ny)), (_s(tx), _s(ty)), (_s(bx - nx), _s(by - ny))], fill=255)


class PersonajeViejo:
    """Viejo sabio 2D: pelo blanco alborotado, gafas, bigote, cuerpo gris con
    bata, brazos y piernas de palo. Lo más parecido al de Yeison."""

    size = (600, 900)
    reposo = "reposo"
    gestos = ["explica_d", "explica_i", "abre", "juntas", "dedo_arriba", "pensando", "cadera"]
    peso_gesto = {"explica_d": 2.0, "explica_i": 2.0, "abre": 1.6, "juntas": 1.2,
                  "dedo_arriba": 1.0, "pensando": 0.5, "cadera": 0.7}
    lado_gesto = {"explica_d": -1, "explica_i": 1, "dedo_arriba": -1, "pensando": -1, "senala": -1, "senala_i": 1}
    # pivote del cuello (la cabeza gira alrededor de aquí)
    CUELLO = (300, 318)
    HOMBRO_I = (212, 356)
    HOMBRO_D = (388, 356)
    L1, L2 = 108.0, 102.0         # brazo y antebrazo
    CAJA_CABEZA = (110, 0, 490, 380)   # zona que ocupa la cabeza (con margen para girarla)
    # En el vídeo (1080×1920): medido sobre el de @analisis_yeison (14-jul):
    # del pelo (y≈810) a los zapatos (y≈1683), ~873 px.
    alto_en_video = 873
    pies_en_video = 1683

    # Pose = mano izquierda (x, y, estilo), mano derecha (x, y, estilo).
    # «izquierda» es la de la izquierda de la PANTALLA.
    poses = {
        "reposo":      ((166, 548, "abierta"), (434, 548, "abierta")),
        "juntas":      ((286, 466, "puno"), (314, 466, "puno")),
        "explica_d":   ((166, 548, "abierta"), (548, 404, "abierta")),
        "explica_i":   ((52, 404, "abierta"), (434, 548, "abierta")),
        "abre":        ((62, 372, "abierta"), (538, 372, "abierta")),
        "dedo_arriba": ((286, 466, "puno"), (540, 226, "dedo")),
        "senala":      ((166, 548, "abierta"), (566, 330, "dedo")),
        "senala_i":    ((34, 330, "dedo"), (434, 548, "abierta")),
        "pensando":    ((252, 466, "puno"), (326, 340, "puno")),
        "cadera":      ((214, 500, "puno"), (386, 500, "puno")),
        "cuenta":      ((90, 380, "abierta"), (300, 380, "dedo")),
    }

    def __init__(self):
        self._cuerpo = self._dibujar_cuerpo()
        self._cabezas: dict = {}

    # ---- capas estáticas --------------------------------------------------
    def _dibujar_cuerpo(self) -> Image.Image:
        W, H = self.size
        capa = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
        d = ImageDraw.Draw(capa)
        # piernas de palo y zapatos negros (óvalos hacia fuera); primero un
        # borde blanco para que se vean sobre fotos oscuras (como los brazos)
        for halo, color in ((3.0, BLANCO), (0.0, NEGRO)):
            for x0, x1 in ((276, 270), (324, 330)):
                d.line([(_s(x0), _s(600)), (_s(x1), _s(846))], fill=color, width=_s(9 + 2 * halo))
            d.ellipse([_s(226 - halo), _s(834 - halo), _s(286 + halo), _s(862 + halo)], fill=color)
            d.ellipse([_s(314 - halo), _s(834 - halo), _s(374 + halo), _s(862 + halo)], fill=color)
        # bata blanca (asoma un poco por los lados) + cuerpo gris algo trapezoidal
        m = _mask(self.size)
        ImageDraw.Draw(m).rounded_rectangle([_s(196), _s(334), _s(404), _s(606)], radius=_s(30), fill=255)
        _contorno(capa, m, BLANCO)
        m = _mask(self.size)
        dm = ImageDraw.Draw(m)
        dm.rounded_rectangle([_s(204), _s(318), _s(396), _s(612)], radius=_s(34), fill=255)
        dm.polygon([(_s(200), _s(560)), (_s(400), _s(560)), (_s(402), _s(600)), (_s(198), _s(600))], fill=255)
        _contorno(capa, m, GRIS_CUERPO)
        return capa

    def _capa_fija(self, nombre: str) -> Image.Image:
        """Capas de la cabeza que no cambian nunca (se dibujan una vez)."""
        if nombre in self._cabezas:
            return self._cabezas[nombre]
        capa = Image.new("RGBA", (self.size[0] * SS, self.size[1] * SS), (0, 0, 0, 0))
        if nombre == "_fondo":
            # pelo (detrás de la cara)
            m = _mask(self.size)
            _pelo_nube(m, 300, 190, 140, 122)
            _contorno(capa, m, BLANCO)
            # orejas
            m = _mask(self.size)
            dm = ImageDraw.Draw(m)
            dm.ellipse([_s(196), _s(206), _s(226), _s(246)], fill=255)
            dm.ellipse([_s(374), _s(206), _s(404), _s(246)], fill=255)
            _contorno(capa, m, PIEL)
            # cara
            m = _mask(self.size)
            ImageDraw.Draw(m).ellipse([_s(208), _s(128), _s(392), _s(326)], fill=255)
            _contorno(capa, m, PIEL)
            # flequillo: mechones blancos redondeados por delante de la frente
            m = _mask(self.size)
            dm = ImageDraw.Draw(m)
            for cx, cy, r in ((226, 160, 20), (248, 142, 19), (274, 134, 18), (300, 131, 17), (326, 134, 18),
                              (352, 142, 19), (374, 160, 20), (214, 186, 15), (386, 186, 15)):
                dm.ellipse([_s(cx - r), _s(cy - r), _s(cx + r), _s(cy + r)], fill=255)
            _contorno(capa, m, BLANCO, grosor=4)
        elif nombre == "_bigote":
            # bigote blanco grande con puntas hacia arriba
            m = _mask(self.size)
            dm = ImageDraw.Draw(m)
            dm.ellipse([_s(242), _s(250), _s(302), _s(282)], fill=255)
            dm.ellipse([_s(298), _s(250), _s(358), _s(282)], fill=255)
            dm.ellipse([_s(216), _s(258), _s(256), _s(278)], fill=255)
            dm.ellipse([_s(344), _s(258), _s(384), _s(278)], fill=255)
            dm.polygon([(_s(220), _s(268)), (_s(204), _s(250)), (_s(232), _s(262))], fill=255)
            dm.polygon([(_s(380), _s(268)), (_s(396), _s(250)), (_s(368), _s(262))], fill=255)
            dm.ellipse([_s(286), _s(244), _s(314), _s(262)], fill=255)          # nariz/centro
            _contorno(capa, m, BLANCO, grosor=4)
            ImageDraw.Draw(capa).arc([_s(286), _s(232), _s(314), _s(258)], start=200, end=340,
                                     fill=PIEL_SOMBRA, width=_s(3))
        elif nombre.startswith("_cejas"):
            # cejas blancas y pobladas (suben con `ceja`)
            cy = 182 - float(nombre[6:]) * 7
            m = _mask(self.size)
            dm = ImageDraw.Draw(m)
            for ex in (262, 338):
                for k in range(4):
                    ox = ex - 22 + k * 13
                    dm.ellipse([_s(ox), _s(cy - 8 - (3 if k in (1, 2) else 0)), _s(ox + 18), _s(cy + 6)], fill=255)
            _contorno(capa, m, BLANCO, grosor=3)
        self._cabezas[nombre] = capa
        return capa

    def _cabeza(self, boca: str, parp: int, ceja: float, mir: int) -> Image.Image:
        """Cabeza completa (capas fijas + ojos/cejas/boca del estado). Se cachea."""
        clave = (boca, parp, ceja, mir)
        if clave in self._cabezas:
            return self._cabezas[clave]
        capa = self._capa_fija("_fondo").copy()
        d = ImageDraw.Draw(capa)
        # ojos (detrás de las gafas)
        dx = mir * 4
        for ex in (264, 336):
            if parp == 2:        # cerrado: rayita curva
                d.arc([_s(ex - 12), _s(206), _s(ex + 12), _s(224)], start=20, end=160, fill=NEGRO, width=_s(4))
            elif parp == 1:      # medio cerrado
                d.ellipse([_s(ex - 7 + dx), _s(212), _s(ex + 7 + dx), _s(222)], fill=NEGRO)
                d.line([(_s(ex - 14), _s(212)), (_s(ex + 14), _s(212))], fill=NEGRO, width=_s(3))
            else:
                d.ellipse([_s(ex - 7 + dx), _s(207), _s(ex + 7 + dx), _s(223)], fill=NEGRO)
                d.ellipse([_s(ex - 3 + dx), _s(209), _s(ex + 0 + dx), _s(212)], fill=BLANCO)
        # gafas: dos monturas gruesas redondeadas + puente + patillas
        for ex in (264, 336):
            d.rounded_rectangle([_s(ex - 34), _s(194), _s(ex + 34), _s(238)], radius=_s(12),
                                outline=GAFAS, width=_s(8))
        d.line([(_s(298), _s(206)), (_s(302), _s(206))], fill=GAFAS, width=_s(7))
        d.line([(_s(230), _s(206)), (_s(212), _s(200))], fill=GAFAS, width=_s(6))
        d.line([(_s(370), _s(206)), (_s(388), _s(200))], fill=GAFAS, width=_s(6))
        capa.alpha_composite(self._capa_fija(f"_cejas{ceja}"))
        # boca (debajo del bigote, que la tapa por arriba)
        self._boca(ImageDraw.Draw(capa), boca)
        capa.alpha_composite(self._capa_fija("_bigote"))
        self._cabezas[clave] = capa
        return capa

    def _boca(self, d: ImageDraw.ImageDraw, boca: str):
        cx, cy = 300, 288
        if boca == "cerrada":
            d.arc([_s(cx - 18), _s(cy - 12), _s(cx + 18), _s(cy + 6)], start=20, end=160, fill=NEGRO, width=_s(4))
            return
        w, h = {"pequena": (16, 8), "media": (20, 15), "abierta": (24, 22), "o": (12, 15)}[boca]
        d.ellipse([_s(cx - w - 4), _s(cy - h - 4), _s(cx + w + 4), _s(cy + h + 4)], fill=NEGRO)
        d.ellipse([_s(cx - w), _s(cy - h), _s(cx + w), _s(cy + h)], fill=BOCA_DENTRO)
        if boca in ("media", "abierta"):
            d.ellipse([_s(cx - w * 0.7), _s(cy + h * 0.15), _s(cx + w * 0.7), _s(cy + h)], fill=LENGUA)
        if boca != "o":
            # las dos paletas (como el de Yeison)
            th = min(10, h * 0.9)
            for x0 in (cx - 9, cx + 1):
                d.rounded_rectangle([_s(x0), _s(cy - h + 1), _s(x0 + 8), _s(cy - h + 1 + th)], radius=_s(2),
                                    fill=BLANCO, outline=NEGRO, width=_s(1.5))

    # ---- brazos -----------------------------------------------------------
    def _ik(self, hombro, mano, sentido: int):
        sx, sy = hombro
        hx, hy = mano
        dx, dy = hx - sx, hy - sy
        d = math.hypot(dx, dy)
        d = min(max(d, 20.0), (self.L1 + self.L2) * 0.985)
        a = math.atan2(dy, dx)
        cos_b = (self.L1 ** 2 + d ** 2 - self.L2 ** 2) / (2 * self.L1 * d)
        b = math.acos(max(-1.0, min(1.0, cos_b)))
        ang = a + sentido * b
        codo = (sx + self.L1 * math.cos(ang), sy + self.L1 * math.sin(ang))
        mano_r = (sx + d * math.cos(a), sy + d * math.sin(a))
        return codo, mano_r

    def _mano(self, d, pos, codo, estilo, halo: float = 0.0):
        # halo > 0: misma mano en blanco y más gruesa (borde para que se vea
        # sobre fotos oscuras); se pinta antes que la negra.
        tinta = (255, 255, 255, 255) if halo else NEGRO
        relleno = (255, 255, 255, 255) if halo else PIEL
        x, y = pos
        dirx, diry = x - codo[0], y - codo[1]
        base = math.atan2(diry, dirx)
        if estilo == "puno":
            r = 14 + halo
            d.ellipse([_s(x - r), _s(y - r), _s(x + r), _s(y + r)], fill=relleno, outline=tinta, width=_s(4))
            return
        if estilo == "dedo":
            a = base - 0.15
            d.line([(_s(x + 6 * math.cos(a)), _s(y + 6 * math.sin(a))),
                    (_s(x + (46 + halo) * math.cos(a)), _s(y + (46 + halo) * math.sin(a)))],
                   fill=tinta, width=_s(7 + 2 * halo))
            r = 13 + halo
            d.ellipse([_s(x - r), _s(y - r), _s(x + r), _s(y + r)], fill=relleno, outline=tinta, width=_s(4))
            return
        # abierta: 4 dedos de palo en abanico + pulgar
        for k, off in enumerate((-0.62, -0.2, 0.2, 0.62)):
            a = base + off
            ln = (34 if k in (1, 2) else 28) + halo
            d.line([(_s(x), _s(y)), (_s(x + ln * math.cos(a)), _s(y + ln * math.sin(a)))],
                   fill=tinta, width=_s(5 + 2 * halo))

    def _pose_interp(self, est: Estado, t: float):
        pa, pb = self.poses[est.pose_a], self.poses[est.pose_b]
        u = est.mezcla
        manos = []
        for k in range(2):
            ax, ay, sa = pa[k]
            bx, by, sb = pb[k]
            x = ax + (bx - ax) * u
            y = ay + (by - ay) * u
            # arco: en mitad del gesto la mano sube un poco (no va en línea recta)
            y -= math.sin(u * math.pi) * 18 * (1 if (ax, ay) != (bx, by) else 0)
            # vida: balanceo suave + «golpe» con la voz
            ph = 1.3 if k else 0.0
            x += 3.0 * math.sin(2 * math.pi * 0.7 * t + ph)
            y += 3.0 * math.sin(2 * math.pi * 0.55 * t + ph + 0.8) + 5.0 * est.habla
            manos.append((x, y, sb if u > 0.5 else sa))
        return manos

    # ---- fotograma --------------------------------------------------------
    # Margen a cada lado del lienzo de dibujo: con el brazo estirado la mano y
    # el dedo pasan de los 600 px y se cortaban (14-oct).
    MARGEN = 120

    def frame(self, est: Estado) -> Image.Image:
        W, H = self.size
        M = self.MARGEN
        lienzo = Image.new("RGBA", ((W + 2 * M) * SS, H * SS), (0, 0, 0, 0))
        lienzo.alpha_composite(self._cuerpo, (M * SS, 0))
        d = ImageDraw.Draw(lienzo)
        manos = self._pose_interp(est, est.t)
        # brazos encima del cuerpo
        brazos = []
        for (mx, my, estilo), hombro, sentido in ((manos[0], self.HOMBRO_I, 1), (manos[1], self.HOMBRO_D, -1)):
            hombro = (hombro[0] + M, hombro[1])
            codo, mano = self._ik(hombro, (mx + M, my), sentido)
            brazos.append(([hombro, codo, mano], codo, mano, estilo))
        # primero el borde blanco de los dos brazos, luego el trazo negro
        for halo in (3.0, 0.0):
            for pts, codo, mano, estilo in brazos:
                d.line([(_s(px), _s(py)) for px, py in pts], fill=(255, 255, 255, 255) if halo else NEGRO,
                       width=_s(9 + 2 * halo), joint="curve")
                self._mano(d, mano, codo, estilo, halo)
        # cabeza: estados cuantizados (se cachean) + giro alrededor del cuello.
        # Solo se gira el recorte de la cabeza (girar el lienzo entero era lo lento).
        parp = 2 if est.parpado > 0.75 else (1 if est.parpado > 0.3 else 0)
        mir = -1 if est.mirada[0] < -0.35 else (1 if est.mirada[0] > 0.35 else 0)
        cab = self._cabeza(est.boca, parp, round(est.ceja * 2) / 2, mir)
        x0, y0, x1, y1 = (_s(v) for v in self.CAJA_CABEZA)
        trozo = cab.crop((x0, y0, x1, y1))
        cx, cy = _s(self.CUELLO[0]) - x0, _s(self.CUELLO[1]) - y0
        trozo = trozo.rotate(est.cabeza_rot, resample=Image.BICUBIC, center=(cx, cy),
                             translate=(0, _s(est.cabeza_dy * 0.6)))
        lienzo.alpha_composite(trozo, (x0 + M * SS, y0))
        return lienzo.reduce(SS)
