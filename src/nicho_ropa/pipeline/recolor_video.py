"""Recolorear la prenda EN EL VÍDEO, fotograma a fotograma.

Para los cortes de color del formato Tienda Colores: en vez de tapar el
vídeo con una foto (que es contenido estático dos segundos y se nota), se
cambia el color del pantalón sobre el propio vídeo, así la creadora se
mueve —se lo sube, se coloca— en cada color, como en los virales.

Cómo: se mide el color del pantalón en el fotograma (Lab), se construye una
máscara con los píxeles que se le parecen (ΔE en Lab, con borde suave) y
dentro de la máscara se sustituye el tono (a, b) por el del color destino
conservando la luz (L) escalada, que es lo que mantiene pliegues, costuras y
sombras. Fuera de la máscara no se toca nada.

Solo vale cuando el color puesto es "aislable": saturado y distinto de la
piel, del top blanco y de las mallas. Un rosa, un rojo o un verde vivo sí;
un beige, un gris o un negro se confunden con el fondo y la piel (medido:
el oliva del viral tenía el croma de una pared). `aislable()` lo decide y
quien llama cae a la foto en ese caso.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

import numpy as np

OnLog = Callable[[str], None]
_noop: OnLog = lambda _m: None

# Croma mínimo (en Lab, sqrt(a²+b²)) para fiarse de la máscara por color. Un
# rosa palo mide ~16 y aún se aísla; por debajo de 12 es casi gris.
CROMA_MIN = 12.0
# Tolerancia de la máscara: distancia SOLO en tono (a, b), sin la luz, por
# debajo de la cual el píxel es "pantalón" seguro y por encima seguro que no;
# entre medias, borde suave. Sin la L entran las sombras del pantalón (mismo
# tono, menos luz); y con el tope bajo la piel se queda fuera (misma a que un
# rosa, pero mucha más b, amarillenta).
DE_DENTRO = 6.0
DE_FUERA = 11.0
# Segunda vuelta (histéresis): los píxeles algo más lejos en tono entran SI
# tocan al pantalón ya detectado (bajo quemado por la luz, brillos). La
# distancia es RELATIVA al croma del pantalón (con un rosa pálido de croma
# 16, un tope fijo de 20 metía el suelo y la pared, que están a 16) y el
# crecimiento se limita a unas pocas dilataciones para que no se arrastre
# por el suelo.
DE_CONECTADO_FRACCION = 0.8
HISTERESIS_PASOS = 6
# La máscara se ENCOGE unos píxeles antes de difuminar el borde: los píxeles
# del contorno son mezcla de pantalón y fondo, y al recolorearlos a un color
# oscuro dejaban un reborde negro alrededor de la pierna y sobre las
# zapatillas. Encogida, el borde queda dentro de la tela.
# Se DILATA un poco (no se encoge): encogida dejaba un filo del color
# original —rosa sobre negro, que canta— alrededor de la pierna. Dilatada y
# con el borde difuminado, lo que sobra es un par de píxeles del color nuevo
# sobre el fondo, que se lee como la sombra de la tela.
DILATACION_PX = 0
BLUR_BORDE = 7
# El contorno del pantalón son píxeles MEZCLA (tela + fondo): dejarlos sin
# tocar deja un filo del color viejo (rosa sobre negro, que canta) y
# pintarlos del todo deja un reborde del nuevo sobre el fondo. Se tratan
# aparte: en un anillo alrededor de la prenda, los píxeles cuyo tono aún
# recuerda al original se corrigen A MEDIAS hacia el destino.
ANILLO_PX = 3
# Cuánto se encoge la región para marcar el "dentro seguro": la corona que
# queda es el borde, donde manda el color del píxel.
NUCLEO_PX = 11
DE_ANILLO = 12.0
# Cuánto contraste de luz se conserva al recolorear: 1 = el del vídeo tal
# cual desplazado al destino. Escalar la luz (×0,15 para un negro) aplastaba
# los pliegues y el pantalón salía como un recorte plano.
CONTRASTE_L = 0.75
# Luz mínima del píxel para ser pantalón (fuera las mallas negras y el suelo
# oscuro, que sin croma podrían colarse por tono).
L_MIN = 45.0
# Y máxima: el top blanco (L≈240) llevaba un poco de rosa reflejado en el
# bajo y se teñía; el pantalón, aunque sea claro, no llega a tanto.
L_MAX = 222.0
# Solo se busca el pantalón por debajo de esta fracción de la altura: la cara
# (labios, colorete) también es rosada y está arriba.
Y_MIN = 0.28
# Zona donde se MIDE el color del pantalón: centro-bajo del encuadre.
ZONA_MEDIDA = (0.30, 0.70, 0.42, 0.72)  # x0, x1, y0, y1 (fracciones)


def _lab(bgr: np.ndarray) -> np.ndarray:
    import cv2

    return cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)


def _de_lab(lab: np.ndarray) -> np.ndarray:
    import cv2

    return cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)


def color_prenda(frame_bgr: np.ndarray) -> np.ndarray:
    """El color (Lab) del pantalón: la mediana de la zona centro-baja,
    quedándose con el grupo de píxeles más numeroso y saturado."""
    h, w = frame_bgr.shape[:2]
    x0, x1, y0, y1 = ZONA_MEDIDA
    zona = _lab(frame_bgr[int(h * y0):int(h * y1), int(w * x0):int(w * x1)])
    px = zona.reshape(-1, 3)
    # Fuera lo casi neutro (top blanco, mallas negras, suelo): sin croma no
    # hay pantalón de color.
    croma = np.hypot(px[:, 1] - 128, px[:, 2] - 128)
    con_color = px[croma > CROMA_MIN * 0.6]
    if len(con_color) < 50:
        return np.median(px, axis=0)
    return np.median(con_color, axis=0)


def aislable(lab_color: np.ndarray) -> bool:
    return float(np.hypot(lab_color[1] - 128, lab_color[2] - 128)) >= CROMA_MIN


def hex_a_lab(hexcolor: str) -> np.ndarray:
    h = hexcolor.strip().lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return _lab(np.array([[[b, g, r]]], dtype=np.uint8))[0, 0]


# Zona ESTRECHA para medir en la foto de un color: solo el centro de las
# piernas, donde no entra ni el suelo ni el top aunque la prenda sea negra o
# beige (sin croma, el filtro de "píxeles con color" no sirve para aislarla).
ZONA_FOTO = (0.40, 0.60, 0.48, 0.68)


def color_de_foto(foto: Path) -> np.ndarray | None:
    """El color (Lab) del pantalón en la foto de ese color hecha en Flow: es
    la misma chica y el mismo encuadre que el clip, así que se mide en la
    misma zona. Mejor que el hex de la miniatura de la ficha, que es
    diminuta y sale con el tono que le dé el modelo.

    Aquí NO se filtra por croma: un negro o un beige no lo tienen, y con el
    filtro la mediana caía en el suelo (el "oscuro" salió gris claro). Se
    mide la mediana de una franja estrecha en el centro de las piernas.
    """
    import cv2

    im = cv2.imread(str(foto))
    if im is None:
        return None
    h, w = im.shape[:2]
    x0, x1, y0, y1 = ZONA_FOTO
    zona = _lab(im[int(h * y0):int(h * y1), int(w * x0):int(w * x1)]).reshape(-1, 3)
    if len(zona) == 0:
        return None
    return np.median(zona, axis=0)


def _a_lab(destino) -> np.ndarray:
    return hex_a_lab(destino) if isinstance(destino, str) else np.asarray(destino, dtype=np.float32)


def mascara(lab: np.ndarray, origen: np.ndarray) -> np.ndarray:
    """Máscara 0..1 de los píxeles que son del pantalón.

    Dos capas, porque cada una arregla un defecto de la otra:
      - la REGIÓN (morfología: núcleo + histéresis + componentes grandes)
        dice DÓNDE está la prenda y deja fuera la piel, el fondo y el suelo;
      - el ALFA POR COLOR dice CUÁNTO de cada píxel es tela, y es continuo,
        así el borde sigue la tela de verdad. Con la región sola el contorno
        salía a bloques (los del códec) y se veía el recorte.
    """
    import cv2

    de = np.sqrt(((lab[..., 1:] - origen[1:]) ** 2).sum(axis=2))
    alfa = np.clip((DE_FUERA - de) / (DE_FUERA - DE_DENTRO), 0.0, 1.0)
    h = lab.shape[0]
    validos = (lab[..., 0] >= L_MIN) & (lab[..., 0] <= L_MAX)
    validos[: int(h * Y_MIN), :] = False
    alfa[~validos] = 0.0

    # Histéresis: lo que está algo más lejos en tono pero PEGADO al pantalón
    # (bajo quemado por la luz, brillos) también es pantalón.
    nucleo = (alfa > 0.5).astype(np.uint8)
    croma = float(np.hypot(origen[1] - 128, origen[2] - 128))
    tope = max(DE_FUERA, min(20.0, croma * DE_CONECTADO_FRACCION))
    candidato = ((de < tope) & validos).astype(np.uint8)
    k = np.ones((5, 5), np.uint8)
    region = nucleo & candidato
    for _ in range(HISTERESIS_PASOS):
        siguiente = cv2.dilate(region, k) & candidato
        if np.array_equal(siguiente, region):
            break
        region = siguiente
    # Cerrar agujeros (costuras, brillos) y quitar manchas sueltas.
    region = cv2.morphologyEx(region * 255, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
    region = cv2.medianBlur(region, 7)
    # SOLO lo que es la prenda: las manchas que quedan del mismo tono (la
    # ropa del perchero, el reflejo en el espejo, la pared) están separadas,
    # así que valen las componentes que pisan la zona donde se mide el
    # pantalón —el centro del encuadre— y son grandes. Sin esto, al pintar el
    # interior entero se teñían el perchero y el espejo.
    n, etiquetas, stats, _ = cv2.connectedComponentsWithStats((region > 100).astype(np.uint8), connectivity=8)
    if n > 1:
        hh, ww = region.shape[:2]
        x0, x1, y0, y1 = ZONA_MEDIDA
        caja = etiquetas[int(hh * y0):int(hh * y1), int(ww * x0):int(ww * x1)]
        centrales = {int(e) for e in np.unique(caja) if e}
        areas = stats[1:, cv2.CC_STAT_AREA]
        minimo = max(areas.max() * 0.05, 400)
        buenas = [
            i + 1 for i, ar in enumerate(areas)
            if ar >= minimo and (not centrales or (i + 1) in centrales)
        ]
        region = np.where(np.isin(etiquetas, buenas), region, 0).astype(np.uint8)
    # Dentro de la prenda se pinta SIEMPRE; el color solo decide en el
    # borde. Si el alfa por color mandara también dentro, los pliegues
    # quemados por la luz (tono pálido) se quedaban del color viejo — con el
    # negro se veían manchas rosas en medio de la pierna.
    region = cv2.dilate(region, np.ones((ANILLO_PX, ANILLO_PX), np.uint8))
    dentro = cv2.erode(region, np.ones((NUCLEO_PX, NUCLEO_PX), np.uint8))
    borde = cv2.subtract(region, dentro)
    alfa_borde = np.clip((DE_ANILLO - de) / (DE_ANILLO - DE_DENTRO), 0.0, 1.0)
    alfa_borde[~validos] = 0.0
    m = np.maximum(
        dentro.astype(np.float32) / 255.0,
        (borde.astype(np.float32) / 255.0) * alfa_borde,
    )
    return cv2.GaussianBlur(m, (BLUR_BORDE, BLUR_BORDE), 0)


def recolorear_frame(frame_bgr: np.ndarray, origen: np.ndarray, destino: np.ndarray, m: np.ndarray | None = None) -> np.ndarray:
    lab = _lab(frame_bgr)
    if m is None:
        m = mascara(lab, origen)
    # Luz: la del vídeo DESPLAZADA a la del destino conservando el
    # contraste (pliegues, sombras). Un negro queda oscuro pero con relieve;
    # escalarla lo dejaba plano.
    nuevo = lab.copy()
    nuevo[..., 0] = np.clip(destino[0] + (lab[..., 0] - origen[0]) * CONTRASTE_L, 0, 255)
    nuevo[..., 1] = destino[1] + (lab[..., 1] - origen[1]) * 0.35
    nuevo[..., 2] = destino[2] + (lab[..., 2] - origen[2]) * 0.35
    out = _de_lab(nuevo).astype(np.float32)
    m3 = m[..., None]
    return (out * m3 + frame_bgr.astype(np.float32) * (1.0 - m3)).astype(np.uint8)


def recolorear_tramos(
    clip: Path, tramos: list[tuple[float, float, object]], destino_path: Path,
    on_log: OnLog = _noop, t_medida: float | None = None,
) -> tuple[Path, float]:
    """Escribe `destino_path`: el clip con cada tramo `(t0, t1, destino)`
    recoloreado, donde `destino` es un hex `"#rrggbb"` o un color Lab ya
    medido (`color_de_foto`). Devuelve la ruta y el croma medido del color
    puesto (para que quien llama sepa lo fiable que es). Audio intacto."""
    import cv2

    cap = cv2.VideoCapture(str(clip))
    if not cap.isOpened():
        raise RuntimeError(f"no se pudo abrir {clip}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    # Se mide el color en el fotograma del color puesto (o el primero).
    if t_medida is None:
        t_medida = max(t for _, t, _ in tramos) if tramos else 0.0
    cap.set(cv2.CAP_PROP_POS_MSEC, t_medida * 1000)
    ok, ref = cap.read()
    if not ok:
        raise RuntimeError("no se pudo leer el fotograma de referencia")
    origen = color_prenda(ref)
    croma = float(np.hypot(origen[1] - 128, origen[2] - 128))
    destinos = [(t0, t1, _a_lab(d)) for t0, t1, d in tramos]
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    tmp = destino_path.with_suffix(".video.mp4")
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
         "-s", f"{w}x{h}", "-r", f"{fps:.3f}", "-i", "-",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(tmp)],
        stdin=subprocess.PIPE,
    )
    n = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            t = n / fps
            for t0, t1, dest in destinos:
                if t0 <= t < t1:
                    frame = recolorear_frame(frame, origen, dest)
                    break
            proc.stdin.write(frame.tobytes())
            n += 1
    finally:
        proc.stdin.close()
        proc.wait()
        cap.release()
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg falló escribiendo el vídeo recoloreado")
    # Volver a pegar el audio original.
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(tmp), "-i", str(clip),
         "-map", "0:v", "-map", "1:a?", "-c:v", "copy", "-c:a", "copy", "-shortest",
         "-movflags", "+faststart", str(destino_path)],
        capture_output=True, text=True,
    )
    tmp.unlink(missing_ok=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg falló al mezclar el audio: {r.stderr[-300:]}")
    on_log(f"[recolor-video] {n} fotogramas, color puesto Lab={origen.round(0).tolist()} croma={croma:.0f}")
    return destino_path, croma
