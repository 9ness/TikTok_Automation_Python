"""Herramienta: «Mejorar voz» — limpia y nivela el audio del vídeo ya cortado.

Para vídeos que se oyen poco o con ruido de fondo (ventilador, calle, motor,
soplido del micro). Va DESPUÉS del cortador (peso 20) para no cambiar la señal
con la que el cortador decide los silencios, y antes de todo lo demás.

Qué hace, en este orden (cada parte se puede apagar):
  1. `quitar_graves`: highpass a 80 Hz (golpes, viento grave, zumbido).
  2. `quitar_clics`: adeclick (chasquidos).
  3. `motor`: reducción de ruido. "rnnoise" = filtro `arnndn` de ffmpeg con un
     modelo `.rnnn`; si el fichero del modelo no está, NO reduce ruido (solo
     nivela) y lo avisa en el log: medido el 10/11/2026, `afftdn` apaga la voz
     en 4-8 kHz y empeora música, clics y voz baja, así que solo se usa si se
     pide a propósito con motor "afftdn". "ninguno" = sin reducción de ruido.
  4. `compresor`: acompressor suave (iguala frases flojas y fuertes).
  5. `nivelar`: loudnorm a `lufs` (−16 por defecto) en DOS pasadas: primero mide
     y luego aplica con los valores medidos (ganancia lineal siempre que cabe).

El vídeo NO se recodifica (`-c:v copy`); solo el audio (AAC 192k, 48 kHz).
Nunca rompe el flujo: sin pista de audio, audio en silencio o fallo de ffmpeg →
copia la entrada tal cual y avisa por `ctx.on_log`.

Sin APIs de pago (solo ffmpeg local) → no lleva `record_*` de cost_tracking.

No está en el flujo de nadie: `build_tool_flow` no la añade; la pone el equipo a
mano en el flujo de un usuario (y `conservar_pasos_del_equipo` la mantiene).
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from src.editor_auto.config import TOOL_AUDIO_CLEAN, TOOL_POSITION_WEIGHTS

from .base import ToolContext


_REPO = Path(__file__).resolve().parents[3]
MODELO_POR_DEFECTO = "assets/rnnoise/sh.rnnn"
MOTORES = ("rnnoise", "afftdn", "ninguno")
# Mismos valores que `subs_auto.audio_denoise` (ya probados con clientes).
_AFFTDN = "afftdn=nr=12:nf=-25"
_TP = -1.5
_LRA = 11
# Por debajo de esto loudnorm mide «silencio»: no hay voz que nivelar.
_LUFS_SILENCIO = -70.0


class AudioCleanTool:
    tool_id: str = TOOL_AUDIO_CLEAN
    display_name: str = "🔊 Mejorar voz (ruido y volumen)"
    description: str = (
        "Para vídeos que se oyen poco o con ruido de fondo: quita graves y "
        "ruido, y deja la voz al volumen estándar. No recodifica el vídeo. "
        "Va justo después del cortador."
    )
    position_weight: int = TOOL_POSITION_WEIGHTS.get(TOOL_AUDIO_CLEAN, 20)

    def default_config(self) -> dict[str, Any]:
        return {
            "motor": "rnnoise",
            "modelo_rnnoise": MODELO_POR_DEFECTO,
            "mezcla": 1.0,
            "quitar_graves": True,
            "quitar_clics": False,
            "compresor": False,
            "nivelar": True,
            "lufs": -16.0,
        }

    def config_schema(self) -> list[dict[str, Any]]:
        return [
            {"key": "motor", "label": "Reducción de ruido", "type": "select",
             "options": list(MOTORES)},
            {"key": "modelo_rnnoise", "label": "Modelo de rnnoise (.rnnn)", "type": "string"},
            {"key": "mezcla", "label": "Cuánta señal limpia (1 = toda)", "type": "float",
             "min": 0.0, "max": 1.0, "step": 0.05},
            {"key": "quitar_graves", "label": "Quitar graves (golpes, viento)", "type": "bool"},
            {"key": "quitar_clics", "label": "Quitar clics y chasquidos", "type": "bool"},
            {"key": "compresor", "label": "Igualar frases flojas y fuertes", "type": "bool"},
            {"key": "nivelar", "label": "Nivelar el volumen", "type": "bool"},
            {"key": "lufs", "label": "Volumen objetivo (LUFS)", "type": "float",
             "min": -24.0, "max": -10.0, "step": 0.5},
        ]

    def descriptor(self):  # type: ignore[override]
        from .base import ToolDescriptor
        return ToolDescriptor(
            tool_id=self.tool_id, display_name=self.display_name,
            description=self.description, position_weight=self.position_weight,
            default_config=self.default_config(), config_schema=self.config_schema(),
        )

    def run(self, *, input_path: str, output_path: str, config: dict[str, Any],
            ctx: ToolContext) -> str:
        cfg = {**self.default_config(), **(config or {})}
        tmp = Path(ctx.temp_folder) / f"audio_clean_{ctx.job_id}_{int(time.time())}"
        try:
            info = _probe(input_path)
            if not info["audio"]:
                ctx.on_log("[audio_clean] El vídeo no tiene pista de audio — lo dejo como está.")
                return _copy(input_path, output_path)

            # El modelo se copia a la carpeta temporal y ffmpeg corre desde ella:
            # así la ruta dentro del filtro es un nombre simple (sin «:», comas ni
            # espacios que haya que escapar).
            modelo = resolver_modelo(cfg.get("modelo_rnnoise"))
            quiere_rnn = _motor(cfg) == "rnnoise"
            if quiere_rnn and modelo is None:
                ctx.on_log("[audio_clean] No encuentro el modelo de rnnoise "
                           f"({cfg.get('modelo_rnnoise')}) — solo nivelo, sin quitar ruido.")
            tmp.mkdir(parents=True, exist_ok=True)
            if quiere_rnn and modelo is not None:
                shutil.copyfile(modelo, tmp / "m.rnnn")
                cfg["_modelo_filtro"] = "m.rnnn"
            hay_modelo = quiere_rnn and modelo is not None

            if not construir_filtros({**cfg, "nivelar": False}, hay_modelo, None) \
                    and not cfg.get("nivelar"):
                ctx.on_log("[audio_clean] Todo apagado en la config — no toco el audio.")
                return _copy(input_path, output_path)

            medida = None
            if cfg.get("nivelar"):
                ctx.on_progress(0.1, "🔊 Midiendo el volumen…")
                medida = _medir(input_path, construir_filtros(cfg, hay_modelo, None),
                                str(tmp), info["dur"])
                if medida is None:
                    ctx.on_log("[audio_clean] No pude medir el volumen — nivelo en una pasada.")
                elif medida["input_i"] < _LUFS_SILENCIO:
                    ctx.on_log("[audio_clean] El audio está en silencio — lo dejo como está.")
                    return _copy(input_path, output_path)

            ctx.on_progress(0.5, "🔊 Limpiando y nivelando la voz…")
            af = construir_filtros(cfg, hay_modelo, medida)
            parcial = str(tmp / ("salida" + (Path(output_path).suffix or ".mp4")))
            _ffmpeg(["-i", os.path.abspath(input_path), "-map", "0:v?", "-map", "0:a:0",
                     "-af", af, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                     "-movflags", "+faststart", parcial], str(tmp), info["dur"])
            fin = _probe(parcial)
            if not fin["audio"] or abs(fin["dur"] - info["dur"]) > 0.5:
                raise RuntimeError(f"salida rara (audio={fin['audio']}, "
                                   f"dur {fin['dur']:.2f} vs {info['dur']:.2f})")
            shutil.move(parcial, output_path)
            antes = f"{medida['input_i']:.1f}" if medida else "?"
            motor = "rnnoise" if hay_modelo else ("afftdn" if _motor(cfg) == "afftdn" else "sin filtro de ruido")
            if cfg.get("nivelar"):
                lufs = _f(cfg.get("lufs"), -16.0, -24.0, -10.0)
                ctx.on_log(f"[audio_clean] Voz mejorada ({motor}); volumen {antes} → {lufs:.1f} LUFS.")
            else:
                ctx.on_log(f"[audio_clean] Voz mejorada ({motor}), sin nivelar.")
            ctx.on_progress(1.0, "✅ Voz mejorada")
            return output_path
        except Exception as e:  # noqa: BLE001 — nunca rompe el flujo
            ctx.on_log(f"[audio_clean] ⚠️ No pude mejorar el audio ({str(e)[-300:]}) — "
                       "sigo con el original.")
            return _copy(input_path, output_path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Cadena de filtros (pura: se prueba sin ffmpeg)
# ---------------------------------------------------------------------------
def _motor(cfg: dict) -> str:
    m = str(cfg.get("motor") or "ninguno").strip().lower()
    return m if m in MOTORES else "ninguno"


def _f(v, default: float, lo: float, hi: float) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(x):
        return default
    return min(hi, max(lo, x))


def construir_filtros(cfg: dict, modelo_existe: bool, medida: dict | None) -> str:
    """Cadena `-af` de ffmpeg para esta config ("" si no hay nada que hacer).

    - `modelo_existe`: si el `.rnnn` está en disco. Con motor "rnnoise" y sin
      modelo no se reduce ruido (afftdn solo con motor "afftdn").
    - `medida`: lo que midió la primera pasada de loudnorm (`input_i`,
      `input_tp`, `input_lra`, `input_thresh`, `target_offset`). Con ella
      loudnorm aplica la segunda pasada; sin ella (None) va en una pasada y
      pide `print_format=json`, que es justo lo que usa la pasada de medir.
    """
    partes: list[str] = []
    if cfg.get("quitar_graves"):
        partes.append("highpass=f=80")
    if cfg.get("quitar_clics"):
        partes.append("adeclick=w=55:o=75:t=3")
    motor = _motor(cfg)
    if motor == "rnnoise" and modelo_existe:
        # rnnoise trabaja a 48 kHz; ffmpeg no remuestrea solo.
        ruta = cfg.get("_modelo_filtro") or cfg.get("modelo_rnnoise") or MODELO_POR_DEFECTO
        mezcla = _f(cfg.get("mezcla"), 1.0, 0.0, 1.0)
        partes.append("aresample=48000")
        partes.append(f"arnndn=m={_esc(str(ruta))}:mix={mezcla:g}")
    elif motor == "afftdn":
        partes.append(_AFFTDN)
    if cfg.get("compresor"):
        partes.append("acompressor=threshold=-22dB:ratio=3:attack=5:release=150:makeup=2")
    if cfg.get("nivelar"):
        lufs = _f(cfg.get("lufs"), -16.0, -24.0, -10.0)
        ln = f"loudnorm=I={lufs:g}:TP={_TP}:LRA={_LRA}"
        if medida:
            ln += (f":measured_I={medida['input_i']:.2f}:measured_TP={medida['input_tp']:.2f}"
                   f":measured_LRA={medida['input_lra']:.2f}"
                   f":measured_thresh={medida['input_thresh']:.2f}"
                   f":offset={medida.get('target_offset', 0.0):.2f}:linear=true")
        else:
            ln += ":print_format=json"
        partes.append(ln)
    return ",".join(partes)


def _esc(ruta: str) -> str:
    """Escapa una ruta para usarla como valor de una opción de filtro."""
    for ch in ("\\", "'", ":", ",", ";", "[", "]", " "):
        ruta = ruta.replace(ch, "\\" + ch)
    return ruta


def resolver_modelo(ruta) -> str | None:
    """Ruta real del `.rnnn` (absoluta, o relativa a la raíz del repo o a /app)."""
    ruta = str(ruta or MODELO_POR_DEFECTO).strip()
    p = Path(ruta)
    candidatos = [p] if p.is_absolute() else [_REPO / p, Path("/app") / p]
    for c in candidatos:
        if c.is_file() and c.stat().st_size > 0:
            return str(c)
    return None


# ---------------------------------------------------------------------------
# ffmpeg
# ---------------------------------------------------------------------------
def _copy(src: str, dst: str) -> str:
    if os.path.abspath(src) != os.path.abspath(dst):
        shutil.copyfile(src, dst)
    return dst


def _probe(path: str) -> dict:
    out = json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type:format=duration",
         "-of", "json", path], timeout=60))
    return {"dur": float((out.get("format") or {}).get("duration") or 0.0),
            "audio": any(s.get("codec_type") == "audio" for s in out.get("streams") or [])}


def _ffmpeg(args: list[str], cwd: str, dur: float) -> str:
    """Lanza ffmpeg desde `cwd` y devuelve su stderr. Lanza si falla."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", *args], cwd=cwd,
                       capture_output=True, text=True, timeout=max(120, int(dur * 4) + 60))
    if r.returncode != 0:
        raise RuntimeError("ffmpeg: " + (r.stderr or "")[-300:])
    return r.stderr or ""


def _medir(video: str, af: str, cwd: str, dur: float) -> dict | None:
    """Primera pasada de loudnorm sobre la cadena ya filtrada. None si no se pudo leer."""
    try:
        err = _ffmpeg(["-i", os.path.abspath(video), "-map", "0:a:0", "-af", af,
                       "-f", "null", "-"], cwd, dur)
        j = json.loads(err[err.rindex("{"):err.rindex("}") + 1])
        m = {k: float(j[k]) for k in ("input_i", "input_tp", "input_lra", "input_thresh",
                                      "target_offset")}
    except Exception:  # noqa: BLE001 — sin medida se nivela en una pasada
        return None
    if not math.isfinite(m["input_i"]):  # «-inf» = silencio total
        m["input_i"] = -99.0
        return m
    return m if all(math.isfinite(v) for v in m.values()) else None
