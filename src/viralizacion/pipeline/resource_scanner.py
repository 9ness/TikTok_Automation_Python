"""Bancos de segmentos candidatos (gancho y paisaje), cacheados en JSON.

Gancho: escanea el vídeo "Video Gancho" de un ponente con detección de cara
(OpenCV Haar cascade, muestreo 1fps) y trocea TODOS los tramos continuos de
cara en primer plano (h_frac > FACE_HEIGHT_FRAC_THRESHOLD) de >=3s en
candidatos NO SOLAPADOS de exactamente 3s.

Paisajes: trocea el vídeo de paisajes (compartido entre ponentes) en
candidatos NO SOLAPADOS de ~4.5s, saltando los primeros/últimos 60s.

Ambos bancos se cachean en JSON (`hook_candidates.json` por ponente,
`paisaje_candidates.json` compartido) para no re-escanear en cada job —
el escaneo de cara tarda minutos en un vídeo largo.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.viralizacion import config
from src.viralizacion.pipeline.ffmpeg_utils import ffprobe_duration


def _face_samples(video_path: Path, step_s: float = config.FACE_SAMPLE_STEP_S) -> list[dict]:
    """Muestrea el vídeo a `step_s` fps y devuelve, por cada frame con cara
    detectada, `{t, h_frac, cx_frac}` (cara más grande del frame)."""
    import cv2

    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    duration = frame_count / fps if fps else 0.0
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))

    samples: list[dict] = []
    t = 0.0
    while t < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            t += step_s
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
        if len(faces) > 0:
            fx, fy, fw, fh = max(faces, key=lambda f: f[2] * f[3])
            samples.append({
                "t": round(t, 2),
                "h_frac": round(fh / height, 4) if height else 0.0,
                "cx_frac": round((fx + fw / 2) / width, 4) if width else 0.5,
            })
        t += step_s
    cap.release()
    return samples


def _find_runs(samples: list[dict], max_gap: float = 1.5) -> list[list[dict]]:
    """Agrupa samples consecutivos (con huecos <= max_gap) en tramos."""
    runs: list[list[dict]] = []
    if not samples:
        return runs
    cur = [samples[0]]
    for s in samples[1:]:
        if s["t"] - cur[-1]["t"] <= max_gap:
            cur.append(s)
        else:
            runs.append(cur)
            cur = [s]
    runs.append(cur)
    return runs


def _chop_hook_run(run: list[dict]) -> list[dict]:
    """Trocea un tramo continuo de cara en candidatos NO SOLAPADOS de
    exactamente HOOK_DUR segundos. `cx_frac` de cada candidato = media de
    los samples que caen dentro de su ventana (fallback: media del tramo)."""
    run_start = run[0]["t"]
    run_end = run[-1]["t"] + config.FACE_SAMPLE_STEP_S  # margen de 1 sample
    run_avg_cx = sum(s["cx_frac"] for s in run) / len(run)

    out = []
    t = run_start
    while t + config.HOOK_DUR <= run_end + 1e-6:
        window = [s for s in run if t <= s["t"] < t + config.HOOK_DUR]
        cx = (sum(s["cx_frac"] for s in window) / len(window)) if window else run_avg_cx
        out.append({"start": round(t, 2), "cx_frac": round(cx, 4)})
        t += config.HOOK_DUR
    return out


def load_hook_candidates_cached(ponente: str) -> list[dict]:
    """Lee SOLO la caché de gancho (sin escanear). Vacío si no existe.

    Para endpoints UI rápidos — el escaneo de cara tarda minutos y NUNCA
    debe bloquear un GET.
    """
    cache_path = config.hook_candidates_cache_path(ponente)
    if not cache_path.exists():
        return []
    try:
        data = json.loads(cache_path.read_text())
        return data.get("candidates", []) or []
    except Exception:
        return []


def load_paisaje_candidates_cached() -> list[dict]:
    """Lee SOLO la caché de paisaje (sin trocear). Vacío si no existe."""
    cache_path = config.paisaje_candidates_cache_path()
    if not cache_path.exists():
        return []
    try:
        data = json.loads(cache_path.read_text())
        return data.get("candidates", []) or []
    except Exception:
        return []


def scan_hook_candidates(ponente: str, *, force: bool = False) -> list[dict]:
    """Devuelve la lista de candidatos de gancho `{index, start, cx_frac}`
    para `ponente`, usando caché en disco salvo `force=True`."""
    cache_path = config.hook_candidates_cache_path(ponente)
    if cache_path.exists() and not force:
        data = json.loads(cache_path.read_text())
        return data.get("candidates", [])

    video = config.ponente_gancho_video(ponente)
    if video is None:
        raise FileNotFoundError(
            f"No se encontró vídeo de gancho para '{ponente}' en "
            f"{config.ponente_gancho_folder(ponente)}"
        )

    samples = _face_samples(video)
    big = [s for s in samples if s["h_frac"] > config.FACE_HEIGHT_FRAC_THRESHOLD]
    runs = _find_runs(big)

    candidates: list[dict] = []
    idx = 0
    for run in runs:
        run_len = run[-1]["t"] - run[0]["t"]
        if run_len < config.HOOK_DUR:
            continue
        for c in _chop_hook_run(run):
            candidates.append({"index": idx, "start": c["start"], "cx_frac": c["cx_frac"]})
            idx += 1

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(
        {"video": str(video), "candidates": candidates}, ensure_ascii=False, indent=2
    ))
    return candidates


def scan_paisaje_candidates(*, force: bool = False) -> list[dict]:
    """Devuelve la lista de candidatos de paisaje `{index, start, dur}`,
    compartida entre ponentes (mismo vídeo fuente), cacheada en disco."""
    cache_path = config.paisaje_candidates_cache_path()
    if cache_path.exists() and not force:
        data = json.loads(cache_path.read_text())
        return data.get("candidates", [])

    video = config.paisajes_video()
    if video is None:
        raise FileNotFoundError(f"No se encontró vídeo de paisajes en {config.paisajes_folder()}")

    duration = ffprobe_duration(video)
    start_range = config.PAISAJES_SKIP_HEAD_S
    end_range = duration - config.PAISAJES_SKIP_TAIL_S

    candidates: list[dict] = []
    idx = 0
    t = start_range
    while t + config.PAISAJE_CLIP_TARGET_S <= end_range:
        candidates.append({"index": idx, "start": round(t, 2), "dur": config.PAISAJE_CLIP_TARGET_S})
        idx += 1
        t += config.PAISAJE_CLIP_TARGET_S

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(
        {"video": str(video), "duration": duration, "candidates": candidates},
        ensure_ascii=False, indent=2,
    ))
    return candidates
