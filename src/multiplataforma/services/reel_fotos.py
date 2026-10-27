"""Carrusel → reel de fotos con música, para Instagram y Facebook.

La API de Meta no deja poner música a un carrusel de fotos, y sin música los
carruseles se quedaban en el perfil: 0 de alcance en todos (27/10/2026). Así
que en IG y FB el carrusel sale como REEL: las mismas fotos en 9:16 (fondo de
la propia foto desenfocado), `config.REEL_FOTO_S` segundos cada una con un
zoom suave, y de fondo la pista que la réplica ya eligió para Meta
(`doc["musica"]["meta"]["fichero"]`, `src/replicar_viral/musica.py`). Si no la
hay, una del banco rotando por cuenta (`musica.elegir_pista`). Threads y
Pinterest siguen como carrusel.

El MP4 va a `<carpeta del carrusel>/reel.mp4` y se reutiliza si ya existe
(idempotente: un reintento no lo rehace).
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from src.multiplataforma import config
from src.multiplataforma.models import Publicacion
from src.multiplataforma.services import musica

ANCHO, ALTO = 1080, 1920
FPS = 30
NOMBRE = "reel.mp4"


def _noop(_: str) -> None:
    return None


class ErrorReel(RuntimeError):
    pass


def ruta(pub: Publicacion) -> Path:
    """`reel.mp4` en la carpeta del carrusel (la de sus fotos)."""
    return Path(pub.imagenes[0]).parent / NOMBRE


def lienzo(origen: Path, destino: Path) -> Path:
    """La foto entera en 9:16 con el fondo de la propia foto ampliada,
    desenfocada y oscurecida (como `carruseles.lienzo_ig`, pero vertical)."""
    from PIL import Image, ImageEnhance, ImageFilter

    with Image.open(origen) as im:
        im = im.convert("RGB")
        escala = max(ANCHO / im.width, ALTO / im.height)
        fondo = im.resize((round(im.width * escala), round(im.height * escala)), Image.LANCZOS)
        x, y = (fondo.width - ANCHO) // 2, (fondo.height - ALTO) // 2
        fondo = fondo.crop((x, y, x + ANCHO, y + ALTO)).filter(ImageFilter.GaussianBlur(40))
        fondo = ImageEnhance.Brightness(fondo).enhance(0.6)
        k = min(ANCHO / im.width, ALTO / im.height)
        w, h = round(im.width * k), round(im.height * k)
        fondo.paste(im.resize((w, h), Image.LANCZOS), ((ANCHO - w) // 2, (ALTO - h) // 2))
        fondo.save(destino, "JPEG", quality=92)
    return destino


def pista_de(pub: Publicacion, usuario: str) -> Path | None:
    """La pista de Meta de la réplica; si no, una del banco (rotando)."""
    estilo = ""
    if pub.carrusel_id:
        try:
            from src.replicar_viral import carrusel

            meta = ((carrusel.ver(usuario or "ness", pub.carrusel_id).get("musica") or {}).get("meta") or {})
            estilo = meta.get("estilo", "")
            fichero = str(meta.get("fichero") or "")
            if "/" in fichero:
                p = config.musica_dir() / fichero.split("/", 1)[1]
                if p.is_file():
                    return p
        except Exception:  # noqa: BLE001 — sin réplica: banco
            pass
    return musica.elegir_pista(estilo or config.MUSICA_ESTILO_NEUTRO, pub.cuenta)


def montar(fotos: list[Path], pista: Path, destino: Path) -> None:
    """Pase de fotos con zoom suave + música recortada, normalizada y con fundidos."""
    seg = config.REEL_FOTO_S
    dur = seg * len(fotos)
    frames = round(seg * FPS)
    dur_pista = musica.duracion(pista)
    inicio = config.MUSICA_INICIO_S if dur_pista >= dur + config.MUSICA_INICIO_S + 2 else 0.0
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="reel_fotos_") as tmp:
        entradas, fc = [], []
        for i, f in enumerate(fotos):
            lz = lienzo(f, Path(tmp) / f"{i:02d}.jpg")
            entradas += ["-loop", "1", "-framerate", str(FPS), "-t", f"{seg:.3f}", "-i", str(lz)]
            fc.append(f"[{i}:v]"
                      f"zoompan=z='1+{config.REEL_ZOOM - 1:.3f}*on/{frames}':x='iw/2-(iw/zoom/2)':"
                      f"y='ih/2-(ih/zoom/2)':d=1:s={ANCHO}x{ALTO}:fps={FPS},"
                      f"trim=end_frame={frames},setsar=1,format=yuv420p[v{i}]")
        n = len(fotos)
        fc.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[vo]")
        fade_out = min(config.MUSICA_FADE_OUT_S, dur / 4)
        fc.append(f"[{n}:a]atrim=0:{dur:.3f},asetpts=PTS-STARTPTS,"
                  f"loudnorm=I={config.REEL_LUFS}:TP=-2:LRA=11,"
                  f"afade=t=in:st=0:d={min(config.MUSICA_FADE_IN_S, dur / 4):.3f},"
                  f"afade=t=out:st={dur - fade_out:.3f}:d={fade_out:.3f},aresample=48000[ao]")
        parcial = destino.with_name(destino.stem + ".tmp.mp4")
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *entradas,
               "-stream_loop", "-1", "-ss", f"{inicio:.3f}", "-i", str(pista),
               "-filter_complex", ";".join(fc), "-map", "[vo]", "-map", "[ao]",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", "-r", str(FPS),
               "-c:a", "aac", "-b:a", "160k", "-ac", "2", "-t", f"{dur:.3f}",
               "-map_metadata", "-1", "-movflags", "+faststart", str(parcial)]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=True)
            parcial.replace(destino)
        except subprocess.CalledProcessError as e:
            raise ErrorReel(f"ffmpeg: {(e.stderr or '').strip()[-300:]}") from e
        finally:
            parcial.unlink(missing_ok=True)


def reel_de(pub: Publicacion, usuario: str = "", log: Callable[[str], None] = _noop) -> Path:
    """El reel de `pub` (lo monta si no existe). Lanza `ErrorReel` si no puede."""
    if not pub.imagenes:
        raise ErrorReel("carrusel sin fotos")
    destino = ruta(pub)
    if destino.is_file() and destino.stat().st_size > 0:
        return destino
    fotos = [Path(f) for f in pub.imagenes[: config.MAX_FOTOS_CARRUSEL["instagram"]]]
    faltan = [f.name for f in fotos if not f.is_file()]
    if faltan:
        raise ErrorReel(f"faltan fotos del carrusel: {', '.join(faltan)}")
    pista = pista_de(pub, usuario)
    if pista is None:
        raise ErrorReel(f"sin banco de música en {config.musica_dir()}")
    montar(fotos, pista, destino)
    log(f"[multiplataforma] {pub.id}: reel de {len(fotos)} fotos con {pista.parent.name}/{pista.name}")
    return destino
