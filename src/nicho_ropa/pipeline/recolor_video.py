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


def mascara(lab: np.ndarray, origen: np.ndarray) -> np.ndarray:
    """Máscara 0..1 de los píxeles que son del pantalón, con borde suave."""
    import cv2

    de = np.sqrt(((lab[..., 1:] - origen[1:]) ** 2).sum(axis=2))
    m = np.clip((DE_FUERA - de) / (DE_FUERA - DE_DENTRO), 0.0, 1.0)
    m[(lab[..., 0] < L_MIN) | (lab[..., 0] > L_MAX)] = 0.0
    h = lab.shape[0]
    m[: int(h * Y_MIN), :] = 0.0
    # Cerrar agujeritos (costuras, brillos) y suavizar el borde.
    m8 = (m * 255).astype(np.uint8)
    m8 = cv2.morphologyEx(m8, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    m8 = cv2.medianBlur(m8, 7)
    # Solo las manchas grandes: el pantalón es una (o dos, una por pierna).
    # Las pequeñas son reflejos del color en el bajo del top o en la piel.
    n, etiquetas, stats, _ = cv2.connectedComponentsWithStats((m8 > 100).astype(np.uint8), connectivity=8)
    if n > 1:
        areas = stats[1:, cv2.CC_STAT_AREA]
        tope = max(areas.max() * 0.08, 400)
        grandes = np.isin(etiquetas, [i + 1 for i, a in enumerate(areas) if a >= tope])
        m8 = np.where(grandes, m8, 0).astype(np.uint8)
    return cv2.GaussianBlur(m8, (9, 9), 0).astype(np.float32) / 255.0


def recolorear_frame(frame_bgr: np.ndarray, origen: np.ndarray, destino: np.ndarray, m: np.ndarray | None = None) -> np.ndarray:
    lab = _lab(frame_bgr)
    if m is None:
        m = mascara(lab, origen)
    # Luz: se conserva la del vídeo, escalada a la del destino (un negro
    # baja mucho, un beige claro sube un poco). Tono: el del destino.
    escala = float(np.clip((destino[0] + 1.0) / (origen[0] + 1.0), 0.15, 1.6))
    nuevo = lab.copy()
    nuevo[..., 0] = np.clip(lab[..., 0] * escala, 0, 255)
    nuevo[..., 1] = destino[1] + (lab[..., 1] - origen[1]) * 0.35
    nuevo[..., 2] = destino[2] + (lab[..., 2] - origen[2]) * 0.35
    out = _de_lab(nuevo).astype(np.float32)
    m3 = m[..., None]
    return (out * m3 + frame_bgr.astype(np.float32) * (1.0 - m3)).astype(np.uint8)


def recolorear_tramos(
    clip: Path, tramos: list[tuple[float, float, str]], destino_path: Path,
    on_log: OnLog = _noop, t_medida: float | None = None,
) -> tuple[Path, float]:
    """Escribe `destino_path`: el clip con cada tramo `(t0, t1, "#rrggbb")`
    recoloreado. Devuelve la ruta y el croma medido del color puesto (para que
    quien llama sepa lo fiable que es). Audio intacto."""
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
    destinos = [(t0, t1, hex_a_lab(hx)) for t0, t1, hx in tramos]
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
