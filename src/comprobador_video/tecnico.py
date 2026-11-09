"""Lo que una máquina puede decir de un MP4 antes de que nadie lo mire.

Transversal (lo usa cualquier nicho) y sin IA: solo ffprobe y ffmpeg. Junta en
una pasada las comprobaciones que hoy se hacen a mano y por separado, cada una
nacida de una sanción o de una tanda tirada:

- **formato**: 1080x1920 vertical, con imagen y duración.
- **bandas**: `cropdetect` — un MP4 de 1080x1920 puede llevar bandas negras
  dentro (Flow dejado en 3:4, 6/11/2026).
- **movimiento**: lo de `scripts/medir_movimiento.py` — TikTok sanciona el
  «contenido estático» (−4, 7/11/2026).
- **audio**: que haya pista y que no esté en silencio.
- **metadatos**: que no lleve la firma del generador (`limpiar_metadatos`).

Veredicto: `pasa`, `dudas` o `falla` (el peor de sus comprobaciones). **Pasar
lo técnico NO es un verde**: falta mirar el producto contra la ficha. Esto solo
ahorra revisar a ojo lo que ya se sabe que está mal.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

PASA, DUDAS, FALLA = "pasa", "dudas", "falla"
_PESO = {PASA: 0, DUDAS: 1, FALLA: 2}

ANCHO, ALTO = 1080, 1920
# Movimiento (YAVG de la diferencia entre fotogramas). Sancionados por
# estáticos: 0,85-1,63 de media, con un clip a 0,35-1,15; sin problemas, 2-3+.
MOV_MEDIA_OK, MOV_PARTE_OK = 2.0, 1.5
# Bandas: cuánto del alto o del ancho puede faltar sin ser una banda.
BANDA_DUDA, BANDA_FALLA = 0.015, 0.04
# Audio: por debajo de esto de pico, la pista está en silencio.
SILENCIO_DB = -50.0
# Tags que deja un fichero ya limpio (contenedor MP4 y pistas).
TAGS_LIMPIOS = frozenset({"major_brand", "minor_version", "compatible_brands",
                          "handler_name", "vendor_id", "language"})


class ErrorComprobador(Exception):
    """No se pudo leer el vídeo (no existe, no es un vídeo, falta ffmpeg)."""


@dataclass
class Comprobacion:
    clave: str
    veredicto: str
    detalle: str
    valor: Any = None


@dataclass
class Informe:
    ruta: str
    veredicto: str = PASA
    comprobaciones: list[Comprobacion] = field(default_factory=list)
    datos: dict = field(default_factory=dict)
    nota: str = "Pasar lo técnico no es un verde: falta revisar el producto contra la ficha."

    def anadir(self, c: Comprobacion) -> None:
        self.comprobaciones.append(c)
        if _PESO[c.veredicto] > _PESO[self.veredicto]:
            self.veredicto = c.veredicto

    def fallos(self) -> list[Comprobacion]:
        return [c for c in self.comprobaciones if c.veredicto != PASA]

    def como_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Juicios (puros: reciben números, devuelven la comprobación)
# ---------------------------------------------------------------------------
def juzgar_formato(ancho: int, alto: int, duracion: float) -> Comprobacion:
    valor = {"ancho": ancho, "alto": alto, "duracion": round(duracion, 2)}
    if not ancho or not alto:
        return Comprobacion("formato", FALLA, "El fichero no tiene pista de vídeo.", valor)
    if duracion <= 0.5:
        return Comprobacion("formato", FALLA, f"Dura {duracion:.1f} s: el montaje está roto.", valor)
    if (ancho, alto) == (ANCHO, ALTO):
        return Comprobacion("formato", PASA, f"{ancho}x{alto}, {duracion:.1f} s.", valor)
    if ancho >= alto:
        return Comprobacion("formato", FALLA, f"{ancho}x{alto}: no es vertical (tiene que ser 9:16).", valor)
    if abs(ancho / alto - ANCHO / ALTO) < 0.01:
        return Comprobacion("formato", DUDAS, f"{ancho}x{alto}: es 9:16 pero no 1080x1920.", valor)
    return Comprobacion("formato", FALLA, f"{ancho}x{alto}: vertical pero no 9:16.", valor)


def juzgar_bandas(crop: tuple[int, int, int, int] | None, ancho: int, alto: int) -> Comprobacion:
    """`crop` = (w, h, x, y) de `cropdetect` acumulado en todo el vídeo."""
    if not crop:
        return Comprobacion("bandas", DUDAS, "cropdetect no dio resultado (¿vídeo entero en negro?).")
    w, h, x, y = crop
    falta_h, falta_w = 1 - h / alto, 1 - w / ancho
    falta = max(falta_h, falta_w)
    valor = {"imagen": f"{w}x{h}", "en": f"{x},{y}", "falta_pct": round(100 * falta, 1)}
    if falta < BANDA_DUDA:
        return Comprobacion("bandas", PASA, f"Sin bandas (la imagen ocupa {w}x{h}).", valor)
    donde = "arriba y abajo" if falta_h >= falta_w else "a los lados"
    texto = f"Bandas negras {donde}: la imagen real es {w}x{h} dentro de {ancho}x{alto} (falta el {100 * falta:.0f} %)."
    if falta >= BANDA_FALLA:
        return Comprobacion("bandas", FALLA, texto + " Suele ser Flow en 3:4: regenerar en 9:16.", valor)
    return Comprobacion("bandas", DUDAS, texto + " Mira un fotograma: puede ser un borde oscuro de la escena.", valor)


def partir(valores: list[float], partes: int) -> list[float]:
    """Media de cada parte (≈ cada clip del montaje)."""
    partes = max(1, min(int(partes or 1), len(valores) or 1))
    n = len(valores)
    cortes = [round(i * n / partes) for i in range(partes + 1)]
    return [sum(valores[a:b]) / max(1, b - a) for a, b in zip(cortes, cortes[1:])]


def juzgar_movimiento(valores: list[float], clips: int = 2) -> Comprobacion:
    if not valores:
        return Comprobacion("movimiento", DUDAS, "No se pudo medir el movimiento (sin fotogramas).")
    media = sum(valores) / len(valores)
    por_clip = partir(valores, clips)
    valor = {"media": round(media, 2), "por_clip": [round(x, 2) for x in por_clip]}
    partes = " · ".join(f"clip {i + 1} {x:.2f}" for i, x in enumerate(por_clip))
    if media >= MOV_MEDIA_OK and min(por_clip) >= MOV_PARTE_OK:
        return Comprobacion("movimiento", PASA, f"Se mueve: media {media:.2f} ({partes}).", valor)
    if media >= MOV_PARTE_OK:
        flojo = min(range(len(por_clip)), key=por_clip.__getitem__) + 1
        return Comprobacion(
            "movimiento", DUDAS,
            f"Movimiento al límite: media {media:.2f} ({partes}). El clip {flojo} es el flojo: ámbar con el motivo "
            "o rehacerlo con cámara y mano en movimiento.", valor)
    return Comprobacion(
        "movimiento", FALLA,
        f"Estático: media {media:.2f} ({partes}). TikTok lo sanciona como «contenido estático»: rehacer.", valor)


def juzgar_audio(hay_pista: bool, pico_db: float | None, media_db: float | None,
                 con_voz: bool = False) -> Comprobacion:
    valor = {"pista": hay_pista, "pico_db": pico_db, "media_db": media_db}
    mal = FALLA if con_voz else DUDAS
    cola = "" if con_voz else " Bien solo si el formato es mudo a propósito."
    if not hay_pista:
        return Comprobacion("audio", mal, "No tiene pista de audio." + cola, valor)
    if pico_db is None:
        return Comprobacion("audio", DUDAS, "No se pudo medir el volumen.", valor)
    if pico_db <= SILENCIO_DB:
        return Comprobacion("audio", mal, f"La pista de audio está en silencio (pico {pico_db:.0f} dB)." + cola, valor)
    if media_db is not None and media_db < -35:
        return Comprobacion("audio", DUDAS, f"Audio muy bajo (media {media_db:.0f} dB): la voz no se va a oír.", valor)
    return Comprobacion("audio", PASA, f"Con audio (media {media_db:.0f} dB, pico {pico_db:.0f} dB).", valor)


def juzgar_metadatos(tags: dict[str, str]) -> Comprobacion:
    sobran = {k: str(v)[:60] for k, v in sorted(tags.items()) if k.lower() not in TAGS_LIMPIOS}
    if not sobran:
        return Comprobacion("metadatos", PASA, "Metadatos limpios.", {})
    lista = ", ".join(f"{k}={v}" for k, v in list(sobran.items())[:4])
    return Comprobacion(
        "metadatos", DUDAS,
        f"Metadatos sin limpiar ({lista}): pasa `limpiar_metadatos` antes de publicar.", sobran)


# ---------------------------------------------------------------------------
# Lectura de lo que escupe ffmpeg (puro)
# ---------------------------------------------------------------------------
def leer_crop(salida: str) -> tuple[int, int, int, int] | None:
    """El último `crop=w:h:x:y` (con `reset=0` es el acumulado del vídeo)."""
    m = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", salida or "")
    return tuple(int(x) for x in m[-1]) if m else None  # type: ignore[return-value]


def leer_volumen(salida: str) -> tuple[float | None, float | None]:
    """(pico, media) en dB de `volumedetect`."""
    pico = re.search(r"max_volume:\s*(-?[\d.]+|-inf) dB", salida or "")
    media = re.search(r"mean_volume:\s*(-?[\d.]+|-inf) dB", salida or "")

    def _n(m: re.Match | None) -> float | None:
        if not m:
            return None
        return -91.0 if m.group(1) == "-inf" else float(m.group(1))

    return _n(pico), _n(media)


def leer_sonda(doc: dict) -> dict:
    """De la salida JSON de ffprobe a lo que hace falta."""
    video = next((s for s in doc.get("streams") or [] if s.get("codec_type") == "video"), {})
    audio = next((s for s in doc.get("streams") or [] if s.get("codec_type") == "audio"), None)
    fmt = doc.get("format") or {}
    ancho, alto = int(video.get("width") or 0), int(video.get("height") or 0)
    # Un vídeo grabado con el móvil va rotado en los metadatos, no en los píxeles.
    giro = 0
    for sd in video.get("side_data_list") or []:
        if "rotation" in sd:
            giro = int(float(sd["rotation"]))
    giro = int(float((video.get("tags") or {}).get("rotate") or giro))
    if abs(giro) % 180 == 90:
        ancho, alto = alto, ancho
    tags = dict(fmt.get("tags") or {})
    for s in doc.get("streams") or []:
        tags.update(s.get("tags") or {})
    tags.pop("rotate", None)
    return {
        "ancho": ancho, "alto": alto,
        "duracion": float(fmt.get("duration") or video.get("duration") or 0),
        "fps": video.get("avg_frame_rate") or "",
        "codec": video.get("codec_name") or "",
        "audio": audio is not None,
        "codec_audio": (audio or {}).get("codec_name") or "",
        "mb": round(int(fmt.get("size") or 0) / 1e6, 2),
        "tags": tags,
    }


# ---------------------------------------------------------------------------
# ffmpeg
# ---------------------------------------------------------------------------
def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except FileNotFoundError as e:
        raise ErrorComprobador(f"Falta {cmd[0]} en este equipo.") from e
    except subprocess.TimeoutExpired as e:
        raise ErrorComprobador(f"{cmd[0]} tardó más de {timeout} s.") from e


def sondear(ruta: Path, timeout: int = 60) -> dict:
    r = _run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(ruta)], timeout)
    if r.returncode != 0:
        raise ErrorComprobador(f"ffprobe no puede leer {ruta.name}: {r.stderr.strip()[:200]}")
    try:
        return leer_sonda(json.loads(r.stdout))
    except (ValueError, TypeError) as e:
        raise ErrorComprobador(f"ffprobe devolvió algo raro para {ruta.name}.") from e


def medir_imagen(ruta: Path, timeout: int = 300) -> tuple[list[float], tuple[int, int, int, int] | None]:
    """Movimiento y bandas en UNA pasada: dos ramas del mismo decodificado."""
    filtro = (
        "split=2[a][b];"
        "[a]fps=10,scale=180:-2,tblend=all_mode=difference,signalstats,"
        "metadata=print:key=lavfi.signalstats.YAVG:file=-[m];"
        "[b]fps=2,cropdetect=limit=24:round=2:reset=0[c]"
    )
    r = _run(["ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-v", "info", "-i", str(ruta),
              "-filter_complex", filtro, "-map", "[m]", "-f", "null", "-", "-map", "[c]", "-f", "null", "-"], timeout)
    if r.returncode != 0:
        raise ErrorComprobador(f"ffmpeg no puede leer {ruta.name}: {r.stderr.strip()[-200:]}")
    valores = [float(x) for x in re.findall(r"YAVG=([\d.]+)", r.stdout)]
    return valores, leer_crop(r.stderr)


def medir_audio(ruta: Path, timeout: int = 120) -> tuple[float | None, float | None]:
    r = _run(["ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-v", "info", "-i", str(ruta),
              "-vn", "-af", "volumedetect", "-f", "null", "-"], timeout)
    return leer_volumen(r.stderr) if r.returncode == 0 else (None, None)


# ---------------------------------------------------------------------------
# Todo junto
# ---------------------------------------------------------------------------
def comprobar(ruta: str | Path, clips: int = 2, con_voz: bool = False) -> Informe:
    """Todas las comprobaciones de un MP4. `clips` = de cuántos clips está
    montado (el movimiento se mide por clip). `con_voz` = el formato lleva
    locución, así que sin audio es un fallo y no una duda."""
    p = Path(ruta)
    if not p.is_file():
        raise ErrorComprobador(f"No existe {p}.")
    sonda = sondear(p)
    inf = Informe(ruta=str(p), datos={k: v for k, v in sonda.items() if k != "tags"})
    formato = juzgar_formato(sonda["ancho"], sonda["alto"], sonda["duracion"])
    inf.anadir(formato)
    if not sonda["ancho"]:
        return inf
    valores, crop = medir_imagen(p)
    inf.anadir(juzgar_bandas(crop, sonda["ancho"], sonda["alto"]))
    inf.anadir(juzgar_movimiento(valores, clips))
    pico, media = medir_audio(p) if sonda["audio"] else (None, None)
    inf.anadir(juzgar_audio(sonda["audio"], pico, media, con_voz))
    inf.anadir(juzgar_metadatos(sonda["tags"]))
    return inf
