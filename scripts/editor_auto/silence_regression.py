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

Banco sin gasto (9/11/2026), ver `replay.py`:
  --modo offline   (def.) nada de pago sale: Deepgram cae a Whisper local y la
                   IA va apagada salvo que esté grabada (--with-ai + replay).
  --modo record    graba Deepgram + IA en --grabaciones (gasta UNA vez).
  --modo replay    reproduce lo grabado: mismo resultado, 0 €.
  --informe X.json guarda el resultado (score, tiempos, perfil de ffmpeg).
  --base X.json    compara con un informe anterior: falla si un vídeo baja.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import tempfile
import subprocess
import time
from collections import defaultdict

# Permite ejecutar como script suelto dentro del contenedor.
sys.path.insert(0, os.environ.get("APP_ROOT", "/app"))

from src.editor_auto.tools.base import ToolContext  # noqa: E402
from src.editor_auto.tools.silence_cutter import SilenceCutterTool  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from replay import Grabadora  # noqa: E402

DEFAULT_CORPUS = "/mnt/drive/Nebulabs/TikTok/TIKTOK_EDITOR/_regression_corpus"
DEFAULT_GRABACIONES = os.path.join(DEFAULT_CORPUS, "_grabaciones")
VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".webm", ".mkv")


def _find_videos(corpus: str, solo: list[str] | None = None) -> list[str]:
    out: list[str] = []
    for name in sorted(os.listdir(corpus)):
        if os.path.splitext(name)[1].lower() not in VIDEO_EXTS:
            continue
        if solo and not any(x in name for x in solo):
            continue
        out.append(os.path.join(corpus, name))
    return out


# -- perfil de procesos externos (ffmpeg, ffprobe, whisper…) ----------------
def _tipo_proceso(cmd) -> str:
    """Etiqueta corta de un comando para sumar su tiempo por tipo."""
    try:
        args = [str(a) for a in (cmd if isinstance(cmd, (list, tuple)) else [cmd])]
    except Exception:  # noqa: BLE001
        return "otro"
    prog = os.path.basename(args[0]) if args else "otro"
    if prog.startswith("ffmpeg"):
        if "-c:v" in args:
            i = args.index("-c:v")
            codec = args[i + 1] if i + 1 < len(args) else "?"
            return "ffmpeg codificar" if codec != "copy" else "ffmpeg copiar"
        if "-vn" in args or any(a.endswith((".wav", ".mp3", ".m4a")) for a in args[-1:]):
            return "ffmpeg audio"
        if any(a in ("-f", "null") for a in args) and "null" in args:
            return "ffmpeg analizar"
        return "ffmpeg otro"
    if prog.startswith("ffprobe"):
        return "ffprobe"
    if prog.startswith("python"):
        return "subproceso python (whisper)"
    return prog


class Perfil:
    """Suma el tiempo de pared de cada subprocess.run/Popen por tipo."""

    def __init__(self):
        self.t: dict[str, float] = defaultdict(float)
        self.n: dict[str, int] = defaultdict(int)
        self._run = subprocess.run

    def __enter__(self):
        perfil = self
        orig_run = self._run

        def run(cmd, *a, **kw):
            t0 = time.time()
            try:
                return orig_run(cmd, *a, **kw)
            finally:
                k = _tipo_proceso(cmd)
                perfil.t[k] += time.time() - t0
                perfil.n[k] += 1

        subprocess.run = run
        return self

    def __exit__(self, *_):
        subprocess.run = self._run

    def resumen(self) -> dict:
        return {k: {"seg": round(v, 1), "n": self.n[k]}
                for k, v in sorted(self.t.items(), key=lambda x: -x[1])}


def _run_one(video: str, *, with_ai: bool, tmp_root: str) -> dict:
    job_id = f"reg_{os.path.splitext(os.path.basename(video))[0]}_{int(time.time())}"
    temp_folder = os.path.join(tmp_root, job_id)
    os.makedirs(temp_folder, exist_ok=True)
    out_path = os.path.join(temp_folder, "out.mp4")

    logs: list[tuple[float, str]] = []
    t0 = time.time()
    ctx = ToolContext(
        user_id="regression",
        user_name=os.path.basename(video),
        job_id=job_id,
        temp_folder=temp_folder,
        on_log=lambda m: logs.append((round(time.time() - t0, 2), str(m))),
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
    err = None
    with Perfil() as perfil:
        try:
            SilenceCutterTool().run(
                input_path=video, output_path=out_path, config=config, ctx=ctx,
            )
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"

    diag_path = os.path.join(temp_folder, f"editor_diagnostic_{job_id}.json")
    score = None
    n_rem = None
    amp: dict = {}
    dur_in = dur_out = None
    if os.path.exists(diag_path):
        try:
            d = json.load(open(diag_path, encoding="utf-8"))
            a = d.get("audit", {})
            score = a.get("quality_score")
            n_rem = a.get("n_internal_silences")
            amp = d.get("phases", {}).get("amplitude", {})
            dur_in = d.get("video_duration_s")
            cortado = (d.get("final") or {}).get("total_cut_s")
            if isinstance(dur_in, (int, float)) and isinstance(cortado, (int, float)):
                dur_out = round(dur_in - cortado, 2)
        except Exception:  # noqa: BLE001
            pass
    return {
        "video": os.path.basename(video),
        "score": score,
        "n_remaining": n_rem,
        "noise_db": amp.get("noise_db"),
        "mean_volume_db": amp.get("mean_volume_db"),
        "n_amp_raw": amp.get("n_cuts_raw"),
        "dur_in": dur_in,
        "dur_out": dur_out,
        "secs": round(time.time() - t0, 1),
        "perfil": perfil.resumen(),
        "logs": logs,
        "error": err,
        "diag": diag_path if os.path.exists(diag_path) else None,
    }


def comparar(actual: list[dict], base: list[dict]) -> list[str]:
    """Vídeos que empeoran respecto a un informe base (score o errores)."""
    previo = {r["video"]: r for r in base}
    peores: list[str] = []
    for r in actual:
        b = previo.get(r["video"])
        if not b:
            continue
        sa, sb = r.get("score"), b.get("score")
        if r.get("error") and not b.get("error"):
            peores.append(f"{r['video']}: ahora falla ({r['error']})")
        elif isinstance(sb, int) and (not isinstance(sa, int) or sa < sb):
            peores.append(f"{r['video']}: score {sb} → {sa}")
    return peores


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=DEFAULT_CORPUS)
    ap.add_argument("--min-score", type=int, default=80)
    ap.add_argument("--with-ai", action="store_true",
                    help="incluye pasadas IA (en offline fallan: grábalas antes)")
    ap.add_argument("--modo", choices=("offline", "replay", "record"), default="offline")
    ap.add_argument("--grabaciones", default=DEFAULT_GRABACIONES)
    ap.add_argument("--solo", nargs="*", help="solo los vídeos cuyo nombre contenga esto")
    ap.add_argument("--informe", help="guarda el resultado en este JSON")
    ap.add_argument("--base", help="informe anterior: falla si algún vídeo empeora")
    args = ap.parse_args()

    if args.modo == "offline":
        # Deepgram también es de pago: sin grabaciones, Whisper local.
        os.environ["EDITOR_ASR_PROVIDER"] = "whisper"

    videos = _find_videos(args.corpus, args.solo)
    if not videos:
        print(f"❌ Sin vídeos en {args.corpus}")
        return 2

    print(f"🎬 Corpus: {len(videos)} grabaciones · IA={'on' if args.with_ai else 'off'} "
          f"· modo={args.modo} · min_score={args.min_score}\n")
    tmp_root = tempfile.mkdtemp(prefix="silence_reg_")
    graba = Grabadora(args.modo, None if args.modo == "offline" else args.grabaciones)
    with graba:
        results = [_run_one(v, with_ai=args.with_ai, tmp_root=tmp_root) for v in videos]

    print(f"{'grabación':<28} {'score':>5} {'rem':>3} {'umbral':>7} "
          f"{'media':>7} {'ampRaw':>6} {'seg':>6}")
    print("-" * 72)
    worst = 100
    for r in results:
        sc = r["score"] if r["score"] is not None else -1
        worst = min(worst, sc if sc >= 0 else 0)
        flag = "" if sc >= args.min_score else "  ⚠️"
        nd = f"{r['noise_db']:.1f}" if r["noise_db"] is not None else "-"
        mv = f"{r['mean_volume_db']:.1f}" if r["mean_volume_db"] is not None else "-"
        print(f"{r['video']:<28} {sc:>5} {str(r['n_remaining']):>3} {nd:>7} "
              f"{mv:>7} {str(r['n_amp_raw']):>6} {r['secs']:>6}{flag}")
        if r["error"]:
            print(f"    ERROR: {r['error']}")

    print("-" * 72)
    total = defaultdict(float)
    for r in results:
        for k, v in r["perfil"].items():
            total[k] += v["seg"]
    print("⏱️  procesos externos: " + " · ".join(
        f"{k} {v:.0f}s" for k, v in sorted(total.items(), key=lambda x: -x[1])))
    print(f"💾 grabaciones: {graba.stats}")

    ok = all((r["score"] or 0) >= args.min_score for r in results)
    if args.base:
        peores = comparar(results, json.load(open(args.base, encoding="utf-8"))["resultados"])
        for p in peores:
            print(f"   ↓ {p}")
        ok = ok and not peores
    if args.informe:
        with open(args.informe, "w", encoding="utf-8") as f:
            json.dump({"modo": args.modo, "con_ia": args.with_ai, "fecha": time.time(),
                       "grabaciones": graba.stats, "resultados": results},
                      f, ensure_ascii=False, indent=1, default=str)
        print(f"📝 informe → {args.informe}")
    print(f"\n{'✅ PASS' if ok else '❌ FAIL'} · peor score={worst} "
          f"· objetivo≥{args.min_score}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
