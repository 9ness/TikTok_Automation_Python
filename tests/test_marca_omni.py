"""Detección de la estrella de Omni (`config.es_clip_omni`) con clips sintéticos."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.nicho_pov_bof import config


def _clip(dest: Path, estrella: bool, comentario: str = "") -> Path:
    """Clip de 3 s 1080x1920 con fondo oscuro que se mueve y, si se pide, la
    estrella de Omni (blanca al 26 %) fija en (900, 1740)."""
    tmp = dest.parent / f"{dest.stem}_f"
    tmp.mkdir()
    y, x = np.mgrid[-60:60, -60:60] + 0.5
    forma = (np.abs(x) / 43) ** 0.6 + (np.abs(y) / 43) ** 0.6 <= 1
    rng = np.random.default_rng(1)
    for i in range(6):
        img = (np.full((1920, 1080), 40.0) + rng.normal(0, 4, (1920, 1080))
               + 30 * np.sin(np.arange(1080) / 40 + i)[None, :])
        if estrella:
            zona = img[1680:1800, 840:960]
            zona[forma] = zona[forma] * 0.74 + 255 * 0.26
        Path(tmp / f"{i}.pgm").write_bytes(
            b"P5 1080 1920 255\n" + np.clip(img, 0, 255).astype(np.uint8).tobytes())
    meta = ["-metadata", f"comment={comentario}"] if comentario else []
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "2", "-i", str(tmp / "%d.pgm"),
                    "-pix_fmt", "yuv420p", *meta, str(dest)], check=True)
    return dest


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "sin ffmpeg")
class TestMarcaOmni(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_con_estrella_es_omni(self):
        self.assertTrue(config.es_clip_omni(_clip(self.dir / "a.mp4", True)))

    def test_sin_estrella_no_es_omni(self):
        self.assertFalse(config.es_clip_omni(_clip(self.dir / "b.mp4", False)))

    def test_comentario_manda(self):
        self.assertTrue(config.es_clip_omni(_clip(self.dir / "c.mp4", False, config.MARCA_OMNI)))
        self.assertFalse(config.es_clip_omni(_clip(self.dir / "d.mp4", True, config.MARCA_NO_OMNI)))

    def test_encuadre(self):
        self.assertEqual(config.encuadre_marca([_clip(self.dir / "e.mp4", True)]),
                         (config.ZOOM_MARCA_OMNI, config.ESQUINA_MARCA_OMNI))
        self.assertEqual(config.encuadre_marca([_clip(self.dir / "f.mp4", False)]), (None, ""))


if __name__ == "__main__":
    unittest.main()
