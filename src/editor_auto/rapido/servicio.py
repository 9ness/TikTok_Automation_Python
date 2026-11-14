"""Lógica del Editor rápido: créditos, fichas de vídeo, cortes y runner.

- 1 crédito = 1 minuto de vídeo ORIGINAL (redondeo hacia arriba).
- V1: saldo en el Redis del Editor, SIN pagos reales. Alta = N créditos gratis
  (`EDITOR_RAPIDO_FREE_CREDITS`, 5 por defecto) la primera vez que se ve el email.
- Se cobra al pulsar «Cortar» y se devuelve solo si el trabajo falla (idempotente).
- El retoque «devolver un corte» no cuesta créditos en V1.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from src.editor_auto.repos.redis_base import get_editor_redis

RITMOS = ("natural", "sin_pausas")
FORMATOS = ("9:16", "original")
IDIOMAS = ("auto", "es", "en")

MAX_MINUTOS = int(os.getenv("EDITOR_RAPIDO_MAX_MINUTOS", "30"))
MAX_BYTES = int(os.getenv("EDITOR_RAPIDO_MAX_MB", "1024")) * 1024 * 1024
# Cortes más cortos que esto no se enseñan en la lista de retoque.
MIN_CORTE_S = 0.25

_LOCK = threading.Lock()  # un solo proceso de API: basta para el saldo


def gratis_inicial() -> int:
    try:
        return max(0, int(os.getenv("EDITOR_RAPIDO_FREE_CREDITS", "5")))
    except ValueError:
        return 5


def creditos_de(duracion_s: float) -> int:
    """Minutos del original redondeados hacia arriba (mínimo 1)."""
    return max(1, math.ceil(float(duracion_s) / 60.0 - 1e-9))


def raiz_datos() -> Path:
    explicita = os.getenv("EDITOR_RAPIDO_DIR")
    if explicita:
        p = Path(explicita)
    else:
        from src.api.temp_storage import upload_subdir
        p = upload_subdir("editor_rapido")
    p.mkdir(parents=True, exist_ok=True)
    return p


# ───────────────────────── Redis ─────────────────────────

def _k_saldo(email: str) -> str:
    return f"rapido:saldo:{email}"


def _k_ficha(vid: str) -> str:
    return f"rapido:video:{vid}"


def _k_lista(email: str) -> str:
    return f"rapido:videos:{email}"


def saldo(email: str) -> dict:
    """Saldo del usuario; lo crea con los créditos gratis la primera vez."""
    r = get_editor_redis()
    with _LOCK:
        s = r.get_json(_k_saldo(email))
        if s is None:
            s = {"creditos": gratis_inicial(), "gratis_dados": gratis_inicial(), "creado": time.time()}
            r.set_json(_k_saldo(email), s)
        return s


def _guardar_saldo(email: str, s: dict) -> None:
    get_editor_redis().set_json(_k_saldo(email), s)


def ajustar_creditos(email: str, delta: int) -> int:
    """Suma (o resta) créditos. Devuelve el saldo nuevo (nunca < 0)."""
    saldo(email)
    with _LOCK:
        s = get_editor_redis().get_json(_k_saldo(email)) or {"creditos": 0}
        s["creditos"] = max(0, int(s.get("creditos", 0)) + int(delta))
        _guardar_saldo(email, s)
        return s["creditos"]


def cobrar(email: str, n: int) -> bool:
    """Descuenta `n` créditos si alcanzan. False si no hay saldo."""
    saldo(email)
    with _LOCK:
        s = get_editor_redis().get_json(_k_saldo(email)) or {"creditos": 0}
        if int(s.get("creditos", 0)) < n:
            return False
        s["creditos"] = int(s["creditos"]) - n
        _guardar_saldo(email, s)
        return True


def nueva_ficha(email: str, nombre: str, duracion_s: float, bytes_: int) -> dict:
    vid = uuid.uuid4().hex[:12]
    ficha = {
        "id": vid, "email": email, "nombre": nombre,
        "duracion_s": round(duracion_s, 2), "bytes": bytes_,
        "creditos": creditos_de(duracion_s),
        "estado": "subido",  # subido → cola → listo | error
        "creado": time.time(), "job_id": None, "ajustes": None,
        "cobrado": False, "devuelto": False,
        "duracion_final_s": None, "error": None, "version": 0,
        "devueltos": [],  # ids de cortes que el usuario ha devuelto
    }
    guardar_ficha(ficha)
    get_editor_redis().sadd(_k_lista(email), vid)
    return ficha


def guardar_ficha(ficha: dict) -> None:
    get_editor_redis().set_json(_k_ficha(ficha["id"]), ficha)


def cargar_ficha(vid: str, email: str | None = None) -> dict | None:
    if not vid.isalnum():
        return None
    f = get_editor_redis().get_json(_k_ficha(vid))
    if f is None or (email is not None and f.get("email") != email):
        return None
    return f


def listar_fichas(email: str, limite: int = 20) -> list[dict]:
    ids = get_editor_redis().smembers(_k_lista(email))
    fichas = [f for f in (cargar_ficha(i, email) for i in ids) if f]
    fichas.sort(key=lambda f: f.get("creado", 0), reverse=True)
    return fichas[:limite]


def borrar_ficha(ficha: dict) -> None:
    r = get_editor_redis()
    r.delete(_k_ficha(ficha["id"]))
    r.srem(_k_lista(ficha["email"]), ficha["id"])
    shutil.rmtree(carpeta(ficha["id"]), ignore_errors=True)


def devolver_creditos(ficha: dict) -> None:
    """Reembolsa lo cobrado si el trabajo falló. Idempotente."""
    with _LOCK:
        f = cargar_ficha(ficha["id"]) or ficha
        if not f.get("cobrado") or f.get("devuelto"):
            return
        f["devuelto"] = True
        guardar_ficha(f)
    ajustar_creditos(f["email"], int(f.get("creditos", 0)))


# ───────────────────────── Ficheros ─────────────────────────

def carpeta(vid: str) -> Path:
    p = raiz_datos() / vid
    p.mkdir(parents=True, exist_ok=True)
    return p


def ruta_original(vid: str) -> Path | None:
    for p in carpeta(vid).glob("original.*"):
        return p
    return None


def ruta_resultado(vid: str) -> Path:
    return carpeta(vid) / "resultado.mp4"


def poster(vid: str) -> Path | None:
    """JPG del primer segundo del resultado (iOS lo pide para <video poster>). Se crea al vuelo."""
    res = ruta_resultado(vid)
    if not res.exists():
        return None
    jpg = carpeta(vid) / "poster.jpg"
    if not jpg.exists() or jpg.stat().st_mtime < res.stat().st_mtime:
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-ss", "0.5", "-i", str(res), "-frames:v", "1",
                 "-vf", "scale=-2:720", "-q:v", "4", str(jpg)],
                capture_output=True, timeout=30, check=True,
            )
        except Exception:  # noqa: BLE001
            return None
    return jpg if jpg.exists() else None


def duracion_video(path: str | Path) -> float:
    """Duración en segundos con ffprobe (0.0 si no es un vídeo legible)."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "format=duration", "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip()
        return max(0.0, float(out))
    except Exception:  # noqa: BLE001
        return 0.0


# ───────────────────────── Cortes ─────────────────────────

def calcular_cortes(proyecto: dict) -> list[dict]:
    """Cortes = huecos entre los tramos conservados, con el texto que se fue.

    `proyecto` es el `editproject_<job>.json` del cortador (keep_intervals,
    words, video_duration_s). Cada corte lleva un `id` estable (posición en
    esta lista BASE) para poder devolverlo después.
    """
    dur = float(proyecto.get("video_duration_s") or 0.0)
    keeps = sorted((float(a), float(b)) for a, b in proyecto.get("keep_intervals", []))
    palabras = proyecto.get("words", [])
    huecos: list[tuple[float, float]] = []
    cursor = 0.0
    for a, b in keeps:
        if a - cursor >= MIN_CORTE_S:
            huecos.append((cursor, a))
        cursor = max(cursor, b)
    if dur - cursor >= MIN_CORTE_S:
        huecos.append((cursor, dur))
    cortes = []
    for i, (a, b) in enumerate(huecos):
        txt = " ".join(
            str(w.get("word", "")).strip() for w in palabras
            if a <= (float(w["start"]) + float(w["end"])) / 2 <= b
        ).strip()
        cortes.append({
            "id": i, "inicio": round(a, 2), "fin": round(b, 2),
            "duracion": round(b - a, 2), "texto": txt,
            "tipo": "palabras" if txt else "silencio",
        })
    return cortes


def tramos_a_conservar(duracion: float, cortes: list[dict], devueltos: set[int]) -> list[tuple[float, float]]:
    """Complemento de los cortes que siguen aplicados (los devueltos se quedan)."""
    activos = sorted((c["inicio"], c["fin"]) for c in cortes if c["id"] not in devueltos)
    keeps, cursor = [], 0.0
    for a, b in activos:
        if a > cursor:
            keeps.append((cursor, a))
        cursor = max(cursor, b)
    if duracion > cursor:
        keeps.append((cursor, duracion))
    return keeps


def leer_cortes(vid: str) -> list[dict]:
    p = carpeta(vid) / "cortes.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def config_cortador(ajustes: dict) -> dict[str, Any]:
    idioma = ajustes.get("idioma", "auto")
    return {
        "vad_enabled": True,
        "amplitude_enabled": True,
        "ai_clean_enabled": os.getenv("EDITOR_RAPIDO_AI_CLEAN", "0") == "1",
        "ai_language": None if idioma == "auto" else idioma,
        "output_aspect": ajustes.get("formato", "9:16"),
        "ritmo": ajustes.get("ritmo", "natural"),
    }


# ───────────────────────── Runner (cola) ─────────────────────────

def ejecutar(job, on_log: Callable[[str], None], on_progress: Callable[[float, str], None]) -> str:
    """Corta un vídeo (modo `auto`) o re-renderiza con cortes devueltos (`retoque`).

    Params del job: video_id, modo ("auto"|"retoque"). Si falla, devuelve los
    créditos y relanza el error para que la cola lo marque como fallido.
    """
    from src.editor_auto.tools.base import ToolContext
    from src.editor_auto.tools.silence_cutter import SilenceCutterTool

    vid = job.params["video_id"]
    modo = job.params.get("modo", "auto")
    ficha = cargar_ficha(vid)
    if ficha is None:
        raise RuntimeError(f"Ficha {vid} no encontrada")
    carp = carpeta(vid)
    entrada = ruta_original(vid)
    if entrada is None:
        raise RuntimeError("No está el vídeo original")
    salida = carp / f"render_{job.id}.mp4"
    try:
        ctx = ToolContext(
            user_id=ficha["email"], user_name=ficha["email"], job_id=job.id,
            temp_folder=str(carp), on_log=on_log,
            on_progress=lambda f, m="": on_progress(f, m or "Cortando…"),
        )
        cfg = config_cortador(ficha.get("ajustes") or {})
        if modo == "retoque":
            cortes = leer_cortes(vid)
            keeps = tramos_a_conservar(
                float(ficha["duracion_s"]), cortes, set(job.params.get("devueltos") or []),
            )
            cfg["manual_keep_intervals"] = [[a, b] for a, b in keeps]
        SilenceCutterTool().run(
            input_path=str(entrada), output_path=str(salida), config=cfg, ctx=ctx,
        )
        if not salida.exists() or salida.stat().st_size == 0:
            raise RuntimeError("El cortador no generó el vídeo")
        if modo == "auto":
            proyecto = carp / f"editproject_{job.id}.json"
            cortes = []
            if proyecto.exists():
                cortes = calcular_cortes(json.loads(proyecto.read_text(encoding="utf-8")))
            (carp / "cortes.json").write_text(json.dumps(cortes, ensure_ascii=False), encoding="utf-8")
            proyecto.unlink(missing_ok=True)
        final = ruta_resultado(vid)
        os.replace(salida, final)
        # Coste: todo local (Silero, faster-whisper, ffmpeg) → sin API de pago.
        try:
            from src import cost_tracking
            cost_tracking.record_custom(
                kind="editor_rapido", units=float(ficha["creditos"]),
                unit_label="min", cost_usd=0.0, detail=f"modo={modo}",
            )
        except Exception:  # noqa: BLE001
            pass
        ficha = cargar_ficha(vid) or ficha
        ficha["estado"] = "listo"
        ficha["version"] = int(ficha.get("version", 0)) + 1
        ficha["duracion_final_s"] = round(duracion_video(final), 2)
        ficha["error"] = None
        if modo == "retoque":
            ficha["devueltos"] = sorted(set(job.params.get("devueltos") or []))
        guardar_ficha(ficha)
        on_progress(1.0, "Listo")
        return str(final)
    except Exception as e:  # noqa: BLE001
        salida.unlink(missing_ok=True)
        ficha = cargar_ficha(vid) or ficha
        if modo == "auto":
            ficha["estado"] = "error"
            ficha["error"] = str(e)[:300]
            guardar_ficha(ficha)
            devolver_creditos(ficha)
        else:  # el retoque falla: se mantiene el resultado anterior
            ficha["estado"] = "listo" if ruta_resultado(vid).exists() else "error"
            ficha["error"] = "No se pudo aplicar el retoque: " + str(e)[:200]
            guardar_ficha(ficha)
        raise
