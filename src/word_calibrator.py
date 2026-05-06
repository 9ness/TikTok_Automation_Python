"""Auto-calibrador de palabras por tipo de vídeo (Presidentes Top N).

Persiste en Upstash Redis el target de palabras por tipo de guion para que
cada generación se acerque a la duración objetivo (~60-65s, sweet spot
para monetización TikTok CRP). Tras generar el audio, mide su duración y
ajusta el target proporcionalmente. La siguiente generación arranca con
el valor calibrado.

Schema Redis:
    key:   tiktokCR:words:{type_key}
    value: JSON {"target_words": int, "last_dur_s": float, "samples": int,
                  "updated_at": iso8601}

Las funciones degradan limpiamente si Upstash no está configurado: usan
el default y no lanzan.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.parse
from datetime import datetime, timezone
from typing import Tuple

import requests
from dotenv import load_dotenv

load_dotenv()

UPSTASH_URL = (os.getenv("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
UPSTASH_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN") or ""

PREFIX = "tiktokCR:words:"

# Rango de duración aceptable (segundos)
TARGET_MIN_S = 60.0
TARGET_MAX_S = 65.0
TARGET_MID_S = 62.0  # punto al que apunta el ajuste proporcional

# Límites duros del calibrador (evita explosiones por ruido)
ABS_MIN_WORDS = 120
ABS_MAX_WORDS = 280
MAX_STEP_WORDS = 30  # variación máxima por iteración


def _is_available() -> bool:
    return bool(UPSTASH_URL and UPSTASH_TOKEN)


def _headers() -> dict:
    return {"Authorization": f"Bearer {UPSTASH_TOKEN}"}


def _enc(s: str) -> str:
    return urllib.parse.quote(s, safe="")


def build_type_key(top_count: int, include_hook: bool, creative_mode: bool) -> str:
    """Identificador estable del tipo de guion (combinaciones que afectan a duración)."""
    return (
        f"presidents:t{int(top_count)}"
        f":hook{int(bool(include_hook))}"
        f":cr{int(bool(creative_mode))}"
    )


def get_target_words(type_key: str, default: int = 195) -> int:
    """Lee el target calibrado o devuelve default si no hay registro."""
    if not _is_available() or not type_key:
        return default
    key = PREFIX + type_key
    try:
        r = requests.get(f"{UPSTASH_URL}/get/{_enc(key)}", headers=_headers(), timeout=10)
        if r.status_code != 200:
            return default
        result = r.json().get("result")
        if result is None:
            return default
        data = json.loads(result)
        val = int(data.get("target_words") or default)
        return max(ABS_MIN_WORDS, min(ABS_MAX_WORDS, val))
    except Exception as e:
        print(f"[word_calibrator] get error: {e}")
        return default


def save_target_words(type_key: str, target_words: int, last_dur_s: float) -> bool:
    """Persiste el target con la última duración medida."""
    if not _is_available() or not type_key:
        return False
    key = PREFIX + type_key
    prev_samples = 0
    try:
        r = requests.get(f"{UPSTASH_URL}/get/{_enc(key)}", headers=_headers(), timeout=10)
        if r.status_code == 200:
            res = r.json().get("result")
            if res:
                prev = json.loads(res)
                prev_samples = int(prev.get("samples") or 0)
    except Exception:
        pass

    body = json.dumps({
        "target_words": int(target_words),
        "last_dur_s": round(float(last_dur_s), 2),
        "samples": prev_samples + 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False)
    try:
        r = requests.post(
            f"{UPSTASH_URL}/set/{_enc(key)}",
            headers=_headers(),
            data=body.encode("utf-8"),
            timeout=10,
        )
        return r.status_code == 200 and r.json().get("result") == "OK"
    except Exception as e:
        print(f"[word_calibrator] save error: {e}")
        return False


def adjust_target_words(current: int, dur_s: float) -> int:
    """Devuelve el nuevo target apuntando a TARGET_MID_S, con paso acotado."""
    if dur_s <= 0:
        return current
    raw = int(round(current * (TARGET_MID_S / dur_s)))
    bounded = max(current - MAX_STEP_WORDS, min(current + MAX_STEP_WORDS, raw))
    return max(ABS_MIN_WORDS, min(ABS_MAX_WORDS, bounded))


def is_in_range(dur_s: float) -> bool:
    return TARGET_MIN_S <= dur_s <= TARGET_MAX_S


def measure_audio_folder_duration(folder: str) -> float:
    """Suma duraciones (segundos) de todos los .mp3 de la carpeta vía ffprobe."""
    if not folder or not os.path.isdir(folder):
        return 0.0
    total = 0.0
    try:
        for fn in os.listdir(folder):
            if not fn.lower().endswith(".mp3"):
                continue
            path = os.path.join(folder, fn)
            try:
                out = subprocess.run(
                    [
                        "ffprobe", "-v", "error",
                        "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1",
                        path,
                    ],
                    capture_output=True, text=True, timeout=20,
                )
                d = float((out.stdout or "0").strip() or 0)
                total += d
            except Exception as e:
                print(f"[word_calibrator] ffprobe fail {fn}: {e}")
    except Exception as e:
        print(f"[word_calibrator] measure error: {e}")
    return total


def calibration_decision(
    type_key: str,
    current_target: int,
    dur_s: float,
) -> Tuple[bool, int]:
    """Devuelve (en_rango, siguiente_target). Si en_rango, persiste current_target;
    si no, persiste new_target. Pensado para usarse después de cada intento."""
    if is_in_range(dur_s):
        save_target_words(type_key, current_target, dur_s)
        return True, current_target
    new_target = adjust_target_words(current_target, dur_s)
    save_target_words(type_key, new_target, dur_s)
    return False, new_target
