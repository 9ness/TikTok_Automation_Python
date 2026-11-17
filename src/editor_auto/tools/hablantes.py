"""Quién habla y cuándo (diarización local, sin API de pago) — 17/11/2026.

Para el modo «Conversación» del Editor rápido: saber si en un vídeo hablan una o
varias personas y a quién pertenece cada palabra (subtítulos de un color por persona).

Cómo:
  1. ffmpeg → audio 16 kHz mono.
  2. Silero VAD (el mismo que el cortador) → tramos con voz.
  3. Ventanas de 1,5 s (paso 0,75 s) dentro de cada tramo → huella de voz de 256
     números con WeSpeaker ResNet34 (ONNX, 26 MB, CPU; se baja la primera vez).
  4. Agrupado jerárquico por coseno: se queda con 2-3 grupos solo si están lejos
     entre sí y cada uno habla un mínimo; si no, 1 persona.
  5. Suavizado de etiquetas (una ventana suelta entre dos de otro no cambia de voz).

Todo es CPU local: ~3-6 s por minuto de vídeo. Nunca lanza en `detectar_seguro`.
"""

from __future__ import annotations

import os
import subprocess
import urllib.request
from pathlib import Path
from typing import Any, Callable

SR = 16000
VENTANA_S = 1.5
PASO_S = 0.75
MIN_TRAMO_S = 0.6           # tramos de voz más cortos no dan huella fiable
MAX_VENTANAS = 600          # ~7,5 min de voz; vídeos más largos se muestrean

# Umbrales calibrados con vídeos reales (ver learnings 17/11/2026).
DIST_SEPARAR = float(os.getenv("EDITOR_HABLANTES_DIST", "0.62"))  # 1 - coseno entre centroides
MIN_PARTE = 0.12            # cada persona debe hablar ≥ 12 % de la voz
MAX_PERSONAS = 3

MODELO_URL = ("https://huggingface.co/Wespeaker/wespeaker-voxceleb-resnet34-LM/"
              "resolve/main/voxceleb_resnet34_LM.onnx")
MODELO_BYTES = 26_530_309

_sesion = None


def ruta_modelo() -> Path:
    explicita = os.getenv("EDITOR_HABLANTES_MODELO")
    if explicita:
        return Path(explicita)
    from src.api.temp_storage import upload_subdir
    return upload_subdir("editor_rapido") / "_modelos" / "wespeaker_resnet34.onnx"


def _cargar_modelo(on_log: Callable[[str], None]):
    global _sesion
    if _sesion is not None:
        return _sesion
    import onnxruntime as ort

    ruta = ruta_modelo()
    if not ruta.exists() or ruta.stat().st_size != MODELO_BYTES:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        on_log("[hablantes] Bajando el modelo de huella de voz (26 MB, solo la primera vez)…")
        tmp = ruta.with_suffix(".part")
        urllib.request.urlretrieve(MODELO_URL, tmp)
        if tmp.stat().st_size != MODELO_BYTES:
            tmp.unlink(missing_ok=True)
            raise RuntimeError("el modelo de voz se bajó incompleto")
        os.replace(tmp, ruta)
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = int(os.getenv("EDITOR_HABLANTES_HILOS", "2"))
    _sesion = ort.InferenceSession(str(ruta), sess_options=opts, providers=["CPUExecutionProvider"])
    return _sesion


def _audio(path: str):
    import numpy as np
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
         "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-acodec", "pcm_s16le", "-"],
        capture_output=True, timeout=600,
    )
    if proc.returncode != 0:
        raise RuntimeError("no se pudo leer el audio: " + proc.stderr.decode(errors="ignore")[:200])
    return np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def _voz(wav) -> list[tuple[float, float]]:
    import torch
    from silero_vad import get_speech_timestamps, load_silero_vad
    model = load_silero_vad(onnx=True)
    ts = get_speech_timestamps(torch.from_numpy(wav), model, sampling_rate=SR,
                               min_silence_duration_ms=250, speech_pad_ms=30, return_seconds=True)
    return [(float(s["start"]), float(s["end"])) for s in ts]


def _ventanas(tramos: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for a, b in tramos:
        if b - a < MIN_TRAMO_S:
            continue
        if b - a <= VENTANA_S:
            out.append((a, b))
            continue
        t = a
        while t + VENTANA_S <= b + 1e-6:
            out.append((t, t + VENTANA_S))
            t += PASO_S
        if out and out[-1][1] < b - 0.3:  # cola del tramo
            out.append((max(a, b - VENTANA_S), b))
    if len(out) > MAX_VENTANAS:
        paso = len(out) / MAX_VENTANAS
        out = [out[int(i * paso)] for i in range(MAX_VENTANAS)]
    return out


def _huellas(wav, ventanas, sesion):
    import numpy as np
    import torch
    import torchaudio.compliance.kaldi as kaldi

    embs = []
    for a, b in ventanas:
        trozo = wav[int(a * SR):int(b * SR)]
        if len(trozo) < int(0.4 * SR):
            embs.append(None)
            continue
        x = torch.from_numpy(trozo).unsqueeze(0) * 32768.0  # WeSpeaker espera escala int16
        feats = kaldi.fbank(x, num_mel_bins=80, frame_length=25, frame_shift=10,
                            dither=0.0, sample_frequency=SR, window_type="hamming", use_energy=False)
        feats = feats - feats.mean(dim=0, keepdim=True)  # CMN
        e = sesion.run(None, {"feats": feats.unsqueeze(0).numpy().astype(np.float32)})[0][0]
        n = float(np.linalg.norm(e))
        embs.append(e / n if n > 0 else None)
    return embs


def _agrupar(X, pesos) -> tuple[list[int], dict[str, Any]]:
    """Etiquetas (0..k-1, 0 = quien más habla) y métricas."""
    import numpy as np
    from scipy.cluster.hierarchy import fcluster, linkage

    if len(X) < 4:
        return [0] * len(X), {"motivo": "poca voz"}
    Z = linkage(X, method="average", metric="cosine")
    mejor = [0] * len(X)
    info: dict[str, Any] = {"motivo": "una voz"}
    for k in range(2, MAX_PERSONAS + 1):
        lab = fcluster(Z, t=k, criterion="maxclust") - 1
        grupos = sorted(set(lab.tolist()))
        if len(grupos) < k:
            break
        cents = []
        partes = []
        total = float(sum(pesos))
        for g in grupos:
            m = lab == g
            c = X[m].mean(axis=0)
            cents.append(c / (np.linalg.norm(c) or 1.0))
            partes.append(float(np.sum(np.array(pesos)[m])) / max(total, 1e-6))
        dmin = min(1.0 - float(np.dot(cents[i], cents[j]))
                   for i in range(len(cents)) for j in range(i + 1, len(cents)))
        info_k = {"k": k, "dist_min": round(dmin, 3), "partes": [round(p, 3) for p in partes]}
        if k == 2:
            info["dist_2"] = info_k["dist_min"]
            info["partes_2"] = info_k["partes"]
        if dmin < DIST_SEPARAR or min(partes) < MIN_PARTE:
            break
        orden = sorted(grupos, key=lambda g: -partes[grupos.index(g)])
        mapa = {g: i for i, g in enumerate(orden)}
        mejor = [mapa[int(v)] for v in lab]
        info = {**info, "motivo": f"{k} voces", **info_k}
    return mejor, info


def _suavizar(etq: list[int]) -> list[int]:
    """Una ventana aislada entre dos iguales de otra voz se pega a ellas."""
    out = list(etq)
    for i in range(1, len(out) - 1):
        if out[i - 1] == out[i + 1] != out[i]:
            out[i] = out[i - 1]
    return out


def detectar(path: str, on_log: Callable[[str], None] = lambda _: None) -> dict[str, Any]:
    """{personas, tramos:[[t0,t1,persona]], voz_s, metricas}. Lanza si algo falla."""
    import numpy as np

    wav = _audio(path)
    dur = len(wav) / SR
    tramos_voz = _voz(wav)
    voz_s = round(sum(b - a for a, b in tramos_voz), 2)
    ventanas = _ventanas(tramos_voz)
    if len(ventanas) < 4:
        return {"personas": 1 if voz_s > 0 else 0, "tramos": [[a, b, 0] for a, b in tramos_voz],
                "voz_s": voz_s, "duracion_s": round(dur, 2), "metricas": {"motivo": "poca voz"}}
    sesion = _cargar_modelo(on_log)
    embs = _huellas(wav, ventanas, sesion)
    ok = [i for i, e in enumerate(embs) if e is not None]
    X = np.stack([embs[i] for i in ok])
    pesos = [ventanas[i][1] - ventanas[i][0] for i in ok]
    etq, met = _agrupar(X, pesos)
    etq = _suavizar(etq)
    personas = (max(etq) + 1) if etq else 1
    vent_ok = [ventanas[i] for i in ok]
    tramos = _a_tramos(vent_ok, etq) if personas > 1 else [[a, b, 0] for a, b in tramos_voz]
    met["ventanas"] = len(vent_ok)
    on_log(f"[hablantes] {personas} voz/voces ({met.get('motivo')}, dist={met.get('dist_2')}, "
           f"partes={met.get('partes_2')})")
    return {"personas": personas, "tramos": tramos, "voz_s": voz_s,
            "duracion_s": round(dur, 2), "metricas": met}


def _a_tramos(ventanas, etq) -> list[list]:
    """Ventanas solapadas → tramos sin solape [t0, t1, persona] (corte a mitad del solape)."""
    tramos: list[list] = []
    for i, ((a, b), p) in enumerate(zip(ventanas, etq)):
        ini = a if i == 0 or ventanas[i - 1][1] <= a else (a + ventanas[i - 1][1]) / 2
        fin = b if i + 1 == len(ventanas) or ventanas[i + 1][0] >= b else (b + ventanas[i + 1][0]) / 2
        if tramos and tramos[-1][2] == p and ini - tramos[-1][1] < 0.6:
            tramos[-1][1] = round(fin, 3)
        else:
            tramos.append([round(ini, 3), round(fin, 3), p])
    return tramos


def detectar_seguro(path: str, on_log: Callable[[str], None] = lambda _: None) -> dict[str, Any] | None:
    try:
        return detectar(path, on_log)
    except Exception as e:  # noqa: BLE001 — detectar voces nunca rompe la edición
        on_log(f"[hablantes] ⚠️ No se pudo detectar quién habla: {str(e)[:200]}")
        return None


def persona_en(tramos: list[list], t: float) -> int | None:
    """Persona que habla en el instante t (o la del tramo más cercano a < 0,8 s)."""
    mejor, dist = None, 0.8
    for a, b, p in tramos:
        if a <= t <= b:
            return int(p)
        d = min(abs(t - a), abs(t - b))
        if d < dist:
            mejor, dist = int(p), d
    return mejor


def asignar_palabras(palabras: list[dict], tramos: list[list]) -> list[dict]:
    """Copia de las palabras con `hablante` (0, 1, 2) por el centro de cada palabra.
    Una palabra suelta de otra voz entre dos de la misma se iguala (errores de borde)."""
    out = []
    for w in palabras:
        c = (float(w.get("start", 0)) + float(w.get("end", w.get("start", 0)))) / 2
        p = persona_en(tramos, c)
        out.append({**w, "hablante": p if p is not None else (out[-1]["hablante"] if out else 0)})
    for i in range(1, len(out) - 1):
        if out[i - 1]["hablante"] == out[i + 1]["hablante"] != out[i]["hablante"]:
            out[i]["hablante"] = out[i - 1]["hablante"]
    return out
