#!/usr/bin/env python3
"""Harness de regresión del Cortador de Silencios.

Corre la detección de silencios sobre un CORPUS de grabaciones reales y
diversas (voz alta/baja, mala/buena SNR, distintas formas de hablar) y
reporta el quality_score del auditor de cada una. Sirve para validar que
CUALQUIER cambio en la detección generaliza — mejora o mantiene TODAS las
grabaciones, sin mejorar una y empeorar otra.

Por defecto corre con las pasadas de IA DESACTIVADAS → determinista y gratis
(aísla justo la capa acústica/Silero/gaps que es donde vive la lógica de
silencios). Úsalo antes de cada deploy:

    docker exec tiktok-api python3 /app/scripts/editor_auto/silence_regression.py

Sale con código !=0 si alguna grabación baja del umbral (--min-score, def 80),
para poder enchufarlo a CI/pre-deploy.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import tempfile
import time

# Permite ejecutar como script suelto dentro del contenedor.
sys.path.insert(0, os.environ.get("APP_ROOT", "/app"))

from src.editor_auto.tools.base import ToolContext  # noqa: E402
from src.editor_auto.tools.silence_cutter import SilenceCutterTool  # noqa: E402

DEFAULT_CORPUS = (
    "/mnt/drive/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_EDITOR/_regression_corpus"
)
VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".webm", ".mkv")


def _find_videos(corpus: str) -> list[str]:
    out: list[str] = []
    for name in sorted(os.listdir(corpus)):
        if os.path.splitext(name)[1].lower() in VIDEO_EXTS:
            out.append(os.path.join(corpus, name))
    return out


def _run_one(video: str, *, with_ai: bool, tmp_root: str) -> dict:
    job_id = f"reg_{os.path.splitext(os.path.basename(video))[0]}_{int(time.time())}"
    temp_folder = os.path.join(tmp_root, job_id)
    os.makedirs(temp_folder, exist_ok=True)
    out_path = os.path.join(temp_folder, "out.mp4")

    logs: list[str] = []
    ctx = ToolContext(
        user_id="regression",
        user_name=os.path.basename(video),
        job_id=job_id,
        temp_folder=temp_folder,
        on_log=lambda m: logs.append(m),
        on_progress=lambda f, m: None,
    )
    config = {
        "vad_enabled": True,
        "amplitude_enabled": True,
        "ai_clean_enabled": with_ai,
        "ai_false_starts_pass2": with_ai,
        "ai_pass2_openai_enabled": with_ai,
        "ai_pass2_gemini_enabled": with_ai,
        "whisper_model_size": os.environ.get("REG_WHISPER", "large-v3"),
        "ai_language": "es",
        "output_aspect": "9:16",
    }
    t0 = time.time()
    err = None
    try:
        SilenceCutterTool().run(
            input_path=video, output_path=out_path, config=config, ctx=ctx,
        )
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"

    diag_path = os.path.join(temp_folder, f"editor_diagnostic_{job_id}.json")
    # El tool escribe el diagnóstico en su temp_folder (== ctx.temp_folder).
    score = None
    n_rem = None
    amp = {}
    if os.path.exists(diag_path):
        try:
            d = json.load(open(diag_path, encoding="utf-8"))
            a = d.get("audit", {})
            score = a.get("quality_score")
            n_rem = a.get("n_internal_silences")
            amp = d.get("phases", {}).get("amplitude", {})
        except Exception:  # noqa: BLE001
            pass
    return {
        "video": os.path.basename(video),
        "score": score,
        "n_remaining": n_rem,
        "noise_db": amp.get("noise_db"),
        "mean_volume_db": amp.get("mean_volume_db"),
        "n_amp_raw": amp.get("n_cuts_raw"),
        "secs": round(time.time() - t0, 1),
        "error": err,
        "diag": diag_path if os.path.exists(diag_path) else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=DEFAULT_CORPUS)
    ap.add_argument("--min-score", type=int, default=80)
    ap.add_argument("--with-ai", action="store_true",
                    help="incluye pasadas IA (no determinista, con coste)")
    args = ap.parse_args()

    videos = _find_videos(args.corpus)
    if not videos:
        print(f"❌ Sin vídeos en {args.corpus}")
        return 2

    print(f"🎬 Corpus: {len(videos)} grabaciones · IA={'on' if args.with_ai else 'off'} "
          f"· min_score={args.min_score}\n")
    tmp_root = tempfile.mkdtemp(prefix="silence_reg_")
    results = [_run_one(v, with_ai=args.with_ai, tmp_root=tmp_root) for v in videos]

    print(f"{'grabación':<28} {'score':>5} {'rem':>3} {'umbral':>7} "
          f"{'media':>7} {'ampRaw':>6} {'seg':>5}")
    print("-" * 72)
    worst = 100
    for r in results:
        sc = r["score"] if r["score"] is not None else -1
        worst = min(worst, sc if sc >= 0 else 0)
        flag = "" if sc >= args.min_score else "  ⚠️"
        nd = f"{r['noise_db']:.1f}" if r["noise_db"] is not None else "-"
        mv = f"{r['mean_volume_db']:.1f}" if r["mean_volume_db"] is not None else "-"
        print(f"{r['video']:<28} {sc:>5} {str(r['n_remaining']):>3} {nd:>7} "
              f"{mv:>7} {str(r['n_amp_raw']):>6} {r['secs']:>5}{flag}")
        if r["error"]:
            print(f"    ERROR: {r['error']}")

    print("-" * 72)
    ok = all((r["score"] or 0) >= args.min_score for r in results)
    print(f"\n{'✅ PASS' if ok else '❌ FAIL'} · peor score={worst} "
          f"· objetivo≥{args.min_score}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
