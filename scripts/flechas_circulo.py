"""Flecha "círculo": una flecha dentro de un círculo que late, con una onda.

Estilo nuevo, dibujado aquí y no teñido de otro: todas las flechas que había
eran variaciones de "flecha que baja", y un botón que late es otro gesto —el
de "toca aquí"— que da variedad sin dejar de apuntar al carrito.

Sale igual que las demás: 360x360, ProRes 4444 con transparencia y borde
negro, un bucle de 1,2 s a 30 fps. Un fichero por color, con el mismo nombre
de color que el resto (`flecha_circulo_<color>.mov`), para que el montaje la
elija igual que a las otras.

Uso (dentro del contenedor de la API):
  docker cp scripts/flechas_circulo.py tiktok-api:/tmp/ && \\
  docker exec tiktok-api python /tmp/flechas_circulo.py
Repetible: sobrescribe.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

DIR = Path(os.getenv(
    "FLECHAS_DIR",
    "/mnt/drive/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_EDITOR/Assets/flechas",
))
LADO = 360
FPS = 30
FRAMES = 36  # 1,2 s, lo mismo que las de bloque y los chevrones
# Se dibuja al doble y se reduce: sin esto el borde del círculo sale dentado.
ESCALA = 2

COLORES = {
    "amarilla": (255, 214, 51),
    "naranja": (255, 138, 30),
    "marron": (153, 97, 51),
    "beige": (230, 207, 163),
    "roja": (230, 41, 41),
    "burdeos": (143, 28, 59),
    "rosa": (255, 125, 179),
    "morada": (161, 107, 255),
    "azul": (61, 122, 255),
    "cyan": (51, 209, 230),
    "verde": (77, 199, 92),
    "blanca": (245, 245, 245),
    "negra": (40, 40, 40),
}


def _flecha(d: ImageDraw.ImageDraw, cx: float, cy: float, alto: float, relleno) -> None:
    """Flecha de bloque hacia abajo, centrada en (cx, cy), con borde negro."""
    ancho_palo = alto * 0.30
    ancho_punta = alto * 0.78
    arriba = cy - alto / 2
    abajo = cy + alto / 2
    cuello = cy + alto * 0.02
    puntos = [
        (cx - ancho_palo / 2, arriba), (cx + ancho_palo / 2, arriba),
        (cx + ancho_palo / 2, cuello), (cx + ancho_punta / 2, cuello),
        (cx, abajo),
        (cx - ancho_punta / 2, cuello), (cx - ancho_palo / 2, cuello),
    ]
    d.polygon(puntos, fill=relleno, outline=(0, 0, 0, 255), width=int(7 * ESCALA))


def fotograma(i: int, color: tuple[int, int, int]) -> Image.Image:
    lado = LADO * ESCALA
    img = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fase = i / FRAMES  # 0 → 1 en el bucle
    c = lado / 2

    # La onda: sale del borde del círculo, crece y se desvanece.
    r_onda = (118 + 52 * fase) * ESCALA
    alfa = int(210 * (1 - fase))
    d.ellipse(
        (c - r_onda, c - r_onda, c + r_onda, c + r_onda),
        outline=(*color, alfa), width=int(8 * ESCALA),
    )

    # El círculo late: sube un 8% a mitad de bucle y vuelve.
    latido = 1 + 0.08 * math.sin(math.pi * fase)
    r = 112 * latido * ESCALA
    d.ellipse(
        (c - r, c - r, c + r, c + r),
        fill=(*color, 255), outline=(0, 0, 0, 255), width=int(8 * ESCALA),
    )

    # Flecha blanca, salvo en los círculos claros, donde se leería mal.
    claro = sum(color) / 3 > 190
    relleno = (40, 40, 40, 255) if claro else (255, 255, 255, 255)
    # Baja y sube un poco dentro del círculo: lo que la hace "flecha".
    dy = 10 * math.sin(2 * math.pi * fase) * ESCALA
    _flecha(d, c, c + dy, 120 * latido * ESCALA, relleno)

    return img.resize((LADO, LADO), Image.LANCZOS)


def main() -> None:
    if not DIR.is_dir():
        raise SystemExit(f"No está la carpeta de flechas: {DIR}")
    for nombre, color in COLORES.items():
        work = Path(tempfile.mkdtemp(prefix=f"circulo_{nombre}_"))
        try:
            for i in range(FRAMES):
                fotograma(i, color).save(work / f"{i:03d}.png")
            salida = work / f"flecha_circulo_{nombre}.mov"
            subprocess.run(
                ["ffmpeg", "-nostdin", "-y", "-v", "error", "-framerate", str(FPS),
                 "-i", str(work / "%03d.png"),
                 "-c:v", "prores_ks", "-profile:v", "4444",
                 "-pix_fmt", "yuva444p10le", "-alpha_bits", "16", str(salida)],
                check=True,
            )
            # Escrito fuera y copiado: un ffmpeg a medias en el Drive montado
            # dejaría una flecha rota a la vista de todos los montajes.
            shutil.copy(salida, DIR / salida.name)
            print(f"✓ {salida.name}")
        finally:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
