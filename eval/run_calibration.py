#!/usr/bin/env python3
"""Harness de CALIBRACIÓN del audit de silence_cutter.

Mide la fiabilidad del medidor contra la VERDAD marcada en
`eval/audit_calibration.json`:
  · FALSO FALLO   = la verdad dice "good", el audit lo marca (score<90 / fallos /
                    coherencia<100). Es lo que erosiona la confianza.
  · FALLO NO VISTO = la verdad dice "real_fallo", el audit lo da por bueno.

Correr DENTRO del contenedor (lee los diagnósticos más recientes de cada vídeo):
    docker exec tiktok-api python /app/eval/run_calibration.py

No re-procesa nada: usa el último diagnóstico de cada source (corre el set por
la UI/cola y luego esto para medir). El A/B de ASR (Whisper vs Deepgram) se monta
encima cuando esté `DEEPGRAM_API_KEY` + el flag `asr_provider`.
"""
from __future__ import annotations

import glob
import json
import os

LABELS = "/app/eval/audit_calibration.json"
DIAG_GLOB = "/app/temp_work/editor_diagnostic_*.json"


def _latest_diag_for(source: str) -> dict | None:
    """Diagnóstico más reciente cuyo input_path contiene `source`."""
    best = None
    best_mt = -1.0
    stem = os.path.splitext(os.path.basename(source))[0].lower()
    for p in glob.glob(DIAG_GLOB):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if stem in str(d.get("input_path", "")).lower():
            mt = os.path.getmtime(p)
            if mt > best_mt:
                best_mt, best = mt, d
    return best


def main() -> None:
    spec = json.load(open(LABELS, encoding="utf-8"))
    rows = []
    fp = fn = matched = sin_dato = 0
    for v in spec.get("videos", []):
        truth = v.get("truth")
        d = _latest_diag_for(v["source"])
        if d is None:
            rows.append((v["id"], truth, "—", "SIN DIAGNÓSTICO", "?"))
            sin_dato += 1
            continue
        a = d.get("audit") or {}
        score = a.get("quality_score")
        vd = a.get("verdict_detail") or {}
        overall = vd.get("overall")  # ok | revisar | fallo
        # ¿el audit lo "marca como problemático"? (score bajo, fallos, o overall fallo)
        flags = (
            (isinstance(score, int) and score < 90)
            or bool(a.get("needs_requeue"))
            or overall == "fallo"
        )
        # Veredicto esperado por la verdad:
        truth_is_good = truth in ("good", "source_rough")
        if truth_is_good and flags:
            # Falso fallo SALVO que sea source_rough y el veredicto lo reconozca
            if truth == "source_rough" and overall == "revisar":
                verdict = "OK (fuente bruta reconocida)"
                matched += 1
            else:
                verdict = "★ FALSO FALLO"
                fp += 1
        elif (not truth_is_good) and not flags:
            verdict = "★ FALLO NO DETECTADO"
            fn += 1
        else:
            verdict = "OK"
            matched += 1
        rows.append((v["id"], truth, score, overall or "—", verdict))

    print(f"{'VIDEO':<18}{'VERDAD':<14}{'SCORE':<8}{'OVERALL':<10}RESULTADO")
    print("-" * 70)
    for r in rows:
        print(f"{r[0]:<18}{r[1]:<14}{str(r[2]):<8}{str(r[3]):<10}{r[4]}")
    print("-" * 70)
    total = fp + fn + matched
    print(
        f"OK: {matched}  ·  FALSOS FALLOS: {fp}  ·  FALLOS NO VISTOS: {fn}  ·  "
        f"sin dato: {sin_dato}"
    )
    if total:
        print(f"Fiabilidad: {100*matched//total}% acertado  "
              f"(falsos fallos = {100*fp//total}%)")


if __name__ == "__main__":
    main()
