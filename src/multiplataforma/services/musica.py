"""Música de fondo para los vídeos MUDOS de Mis tandas (IG/FB/Threads).

Los formatos mudos del multimodo (`mm_espejo`, botas, bolsos, zapatos,
maniquí…) se publican en TikTok poniendo una canción a mano. La API de Meta no
deja elegir canción de Instagram, así que aquí se MEZCLA en el fichero: una
pista sin copyright del banco `Multiplataforma/_musica/<estilo>/*.mp3`
(Mixkit, licencia en `_musica/LICENCIA.md`) elegida por la sugerencia que cada
vídeo ya guarda (`fila["musica"]["busqueda"]`, p. ej. «autumn lofi»).

- Solo vídeos SIN pista de audio (o con una muda): los que llevan voz no se tocan.
- Estilo por palabras clave (`busqueda` > `estilo` > `alternativas`), con
  `config.MUSICA_ESTILO_NEUTRO` si nada casa.
- Pista rotando dentro del estilo y por cuenta (Redis `musica_ultima:<cuenta>`),
  para no repetir la misma dos veces seguidas.
- La copia va a `config.musica_trabajo_dir()/<cuenta>/` con vídeo `-c:v copy`
  y un `.json` al lado (estilo, pista, original). Si ya existe y es más nueva
  que el original, se reutiliza (idempotente).
- Defensivo: cualquier fallo → log y `None`, y quien llama usa el original.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Callable

from src.multiplataforma import config
from src.multiplataforma.repos import redis_base


def _noop(_: str) -> None:
    return None


# Estilo (= carpeta del banco) → palabras clave. Se buscan en el texto
# normalizado (minúsculas, sin acentos); una clave de varias palabras pesa más.
# El ORDEN desempata (gana el primero).
ESTILOS: dict[str, tuple[str, ...]] = {
    "lofi_otono": ("lofi", "lo-fi", "lo fi", "autumn", "fall aesthetic", "fall", "otono", "cozy", "study"),
    "jazz_cafe": ("jazz", "coffee", "cafe", "cafeteria", "piano", "chanson", "french", "francesa", "parisian",
                  "paris"),
    "bossa_lounge": ("bossa", "bossa nova", "brazilian", "brazilian jazz", "latin", "lounge", "boutique"),
    "country_western": ("western", "cowboy", "country"),
    "folk_acustico": ("acoustic", "acustico", "folk", "soft guitar", "guitar aesthetic", "soft indie", "vlog",
                      "slow morning", "indie suave"),
    "folk_carretera": ("road trip", "carretera", "folk rock"),
    "blues_vintage": ("blues", "rock ballad", "vintage rock", "guitarra vintage"),
    "retro_vintage": ("60s", "60 s", "los 60", "girl group", "vinyl", "vintage love", "old song", "retro",
                      "oldies", "love song"),
    "soul_funk_70s": ("soul", "funk", "70s", "los 70", "disco", "groove"),
    "pop_outfit": ("outfit", "fit check", "ootd", "catwalk", "pasarela", "confident", "main character",
                   "trending", "tendencia", "girly pop", "pop dance", "pop pegadizo", "pop con actitud"),
    "house_fashion": ("house", "get ready", "grwm", "party", "fashion show", "deep house", "dance"),
    "dream_pop": ("dream", "dreamy", "ethereal", "bedroom pop", "envolvente"),
    "rnb_suave": ("rnb", "r&b", "r and b", "late night"),
    "hiphop_chill": ("hip hop", "hiphop", "boom bap", "chill beat", "sneaker", "urbano", "beat"),
}
# Pesos por campo de la sugerencia.
_PESOS = (("busqueda", 3.0), ("estilo", 2.0), ("alternativas", 1.0))


def _norm(texto: str) -> str:
    plano = unicodedata.normalize("NFKD", str(texto or "").lower())
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9&\- ]+", " ", plano).split())


def _contiene(texto: str, clave: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(clave)}(?![a-z0-9])", texto) is not None


def elegir_estilo(musica: dict | str | None) -> str:
    """Estilo del banco para la sugerencia de música del vídeo."""
    if isinstance(musica, str):
        musica = {"busqueda": musica}
    musica = musica if isinstance(musica, dict) else {}
    puntos: dict[str, float] = {}
    for campo, peso in _PESOS:
        valor = musica.get(campo)
        textos = valor if isinstance(valor, list) else [valor]
        for t in textos:
            t = _norm(t)
            if not t:
                continue
            for estilo, claves in ESTILOS.items():
                for clave in claves:
                    if _contiene(t, clave):
                        puntos[estilo] = puntos.get(estilo, 0.0) + peso * (1 + 0.5 * clave.count(" "))
    if not puntos:
        return config.MUSICA_ESTILO_NEUTRO
    return max(puntos, key=lambda e: (puntos[e], -list(ESTILOS).index(e)))


# ---------------------------------------------------------------------------
# ffprobe / banco
# ---------------------------------------------------------------------------
def duracion(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          str(path)], capture_output=True, text=True, timeout=60, check=True).stdout
    return float(out.strip())


def es_mudo(path: Path) -> bool:
    """True si el vídeo no trae pista de audio o la que trae está en silencio."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                          "stream=index", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, timeout=60, check=True).stdout
    if not out.strip():
        return True
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0",
                          "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True, timeout=120).stderr
    m = re.search(r"max_volume:\s*(-?[\d.]+|-inf) dB", err)
    if not m:
        return False
    return m.group(1) == "-inf" or float(m.group(1)) < -60.0


def pistas(estilo: str) -> list[Path]:
    base = config.musica_dir()
    for e in (estilo, config.MUSICA_ESTILO_NEUTRO):
        d = base / e
        if d.is_dir():
            lista = sorted(p for p in d.iterdir() if p.is_file() and p.suffix.lower() in (".mp3", ".m4a", ".wav"))
            if lista:
                return lista
    return []


def _key_ultima(cuenta: str) -> str:
    return f"musica_ultima:{cuenta}"


def elegir_pista(estilo: str, cuenta: str) -> Path | None:
    """La siguiente del estilo tras la última usada en esa cuenta (rotación)."""
    lista = pistas(estilo)
    if not lista:
        return None
    try:
        r = redis_base.get_redis()
        ultimas = r.get_json(_key_ultima(cuenta)) or {}
    except Exception:  # noqa: BLE001 — sin Redis, rota igual desde la primera
        r, ultimas = None, {}
    nombres = [p.name for p in lista]
    previa = ultimas.get(estilo)
    i = (nombres.index(previa) + 1) % len(lista) if previa in nombres else 0
    elegida = lista[i]
    if r is not None:
        try:
            ultimas[estilo] = elegida.name
            r.set_json(_key_ultima(cuenta), ultimas)
        except Exception:  # noqa: BLE001
            pass
    return elegida


# ---------------------------------------------------------------------------
# Mezcla
# ---------------------------------------------------------------------------
def ruta_copia(video: Path, cuenta: str) -> Path:
    h = hashlib.sha1(str(video).encode("utf-8")).hexdigest()[:10]
    stem = re.sub(r"[^\w\-]+", "_", video.stem)[:60].strip("_")
    return config.musica_trabajo_dir() / cuenta / f"{stem}__{h}.mp4"


def mezclar(video: Path, pista: Path, destino: Path) -> None:
    """Copia de `video` con `pista` de fondo: vídeo sin recodificar, música
    normalizada, con fundidos y recortada a la duración del vídeo."""
    dur = duracion(video)
    dur_pista = duracion(pista)
    inicio = config.MUSICA_INICIO_S if dur_pista >= dur + config.MUSICA_INICIO_S + 2 else 0.0
    fade_out = min(config.MUSICA_FADE_OUT_S, max(dur / 4, 0.1))
    filtro = (f"loudnorm=I={config.MUSICA_LUFS}:TP=-2:LRA=11,"
              f"afade=t=in:st=0:d={min(config.MUSICA_FADE_IN_S, dur / 4):.3f},"
              f"afade=t=out:st={max(dur - fade_out, 0):.3f}:d={fade_out:.3f},"
              f"aresample=48000")
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.stem + ".tmp.mp4")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-i", str(video), "-stream_loop", "-1", "-ss", f"{inicio:.3f}", "-i", str(pista),
           "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-af", filtro,
           "-c:a", "aac", "-b:a", "160k", "-ac", "2", "-t", f"{dur:.3f}",
           "-map_metadata", "-1", "-movflags", "+faststart", str(tmp)]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=True)
        tmp.replace(destino)
    finally:
        tmp.unlink(missing_ok=True)


def con_musica(video_path: str, musica: dict | str | None, cuenta: str,
               log: Callable[[str], None] = _noop) -> dict | None:
    """Copia con música de un vídeo MUDO. Devuelve `{path, estilo, pista,
    reutilizada}` o None (tiene voz, no hay banco o algo ha fallado: se usa
    el original)."""
    video = Path(video_path)
    try:
        if not video.is_file():
            return None
        destino = ruta_copia(video, cuenta)
        meta_path = destino.with_suffix(".json")
        if destino.is_file() and destino.stat().st_mtime >= video.stat().st_mtime:
            meta = json.loads(meta_path.read_text("utf-8")) if meta_path.is_file() else {}
            return {"path": str(destino), "estilo": meta.get("estilo", ""), "pista": meta.get("pista", ""),
                    "reutilizada": True}
        estilo = elegir_estilo(musica)
        if not pistas(estilo):
            log(f"[multiplataforma] sin banco de música en {config.musica_dir()}: {video.name} va tal cual")
            return None
        if not es_mudo(video):
            return None
        pista = elegir_pista(estilo, cuenta)
        if pista is None:
            return None
        mezclar(video, pista, destino)
        busqueda = musica.get("busqueda") if isinstance(musica, dict) else musica
        meta = {"estilo": estilo, "pista": pista.name, "busqueda": busqueda or "", "original": str(video)}
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), "utf-8")
        log(f"[multiplataforma] música {estilo}/{pista.name} → {destino.name}")
        return {"path": str(destino), "estilo": estilo, "pista": pista.name, "reutilizada": False}
    except Exception as e:  # noqa: BLE001 — nunca bloquea la publicación
        log(f"[multiplataforma] no se pudo poner música a {video.name}: {e}")
        return None
