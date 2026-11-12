"""Edición VIP copiando un vídeo de referencia (12/11/2026).

Un TikTok (o cualquier vídeo) cuya edición gusta → config de `vip_overlays`:
- el ESTILO (colores, letra, subtítulos, flecha) con `estilo_vip.estilo_desde_video`;
- el RITMO: cortes de plano medidos con ffmpeg (sin IA) y zooms, rótulos y
  gancho leídos de dos hojas de fotogramas (inicio + todo el vídeo).

La visión va con Claude (`claude_client.modelo()`, Haiku por defecto) y, si
falla, con Gemini (`MODELO_GEMINI`). Coste ~0,002-0,004 $ por referencia.
El resultado se mezcla en la config del VIP; lo que el usuario pase a mano gana.
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
from pathlib import Path

from src import cost_tracking

from .revision_visual import _fotogramas, _hoja

MODELO_GEMINI = "gemini-2.5-flash"  # reserva si Claude falla
N_TODO = 24
N_GANCHO = 8
DUR_GANCHO = 3.0
UMBRAL_ESCENA = 0.3
_PROMPT = Path(__file__).resolve().parent.parent / "prompts" / "vip_ritmo_referencia.md"
_TIPOS_GANCHO = {"pregunta", "problema", "promesa", "dato", "resultado", "sorpresa", "ninguno"}


def _duracion(video: str) -> float:
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
        timeout=60).decode().strip())


def cortes_de_plano(video: str, umbral: float = UMBRAL_ESCENA) -> list[float]:
    """Segundos donde cambia el plano (filtro `scene` de ffmpeg, a baja resolución)."""
    p = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "info", "-threads", "2", "-i", video, "-an", "-vf",
         f"scale=160:-2,select='gt(scene,{umbral})',showinfo", "-f", "null", "-"],
        capture_output=True, text=True, timeout=300)
    return [round(float(t), 2) for t in re.findall(r"pts_time:([0-9.]+)", p.stderr)]


def _tiempos(dur: float, n: int) -> str:
    return f"{dur:.2f}·(k−0,5)/{n}"


def _vision(jpgs: list[bytes], instr: str) -> dict:
    """Claude (Haiku) y, si falla, Gemini. Lanza si fallan los dos."""
    try:
        return _vision_claude(jpgs, instr)
    except Exception as e_claude:  # noqa: BLE001
        try:
            return _vision_gemini(jpgs, instr)
        except Exception as e_gem:  # noqa: BLE001
            raise RuntimeError(f"referencia: Claude ({str(e_claude)[:150]}) y Gemini "
                               f"({str(e_gem)[:150]}) fallaron") from e_gem


def _json(raw: str) -> dict:
    if "{" not in raw:
        raise RuntimeError("la IA no devolvió JSON")
    return json.loads(raw[raw.find("{"): raw.rfind("}") + 1])


def _vision_claude(jpgs: list[bytes], instr: str) -> dict:
    from src.editor_auto.api import claude_client

    m = claude_client.modelo()
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                            "data": base64.b64encode(j).decode()}} for j in jpgs]
    content.append({"type": "text", "text": instr})
    resp = claude_client._client().messages.create(
        model=m, max_tokens=8000, messages=[{"role": "user", "content": content}])
    try:
        cost_tracking.record_claude(input_tokens=int(resp.usage.input_tokens or 0),
                                    output_tokens=int(resp.usage.output_tokens or 0),
                                    model=m, detail=f"editor_auto.referencia_vip ({m})")
    except Exception:  # noqa: BLE001
        pass
    return _json("".join(b.text for b in resp.content if b.type == "text"))


def _vision_gemini(jpgs: list[bytes], instr: str) -> dict:
    from src.tiktok_shop.api.gemini import generate_text

    raw = generate_text("Responde solo con JSON.", instr, model=MODELO_GEMINI, expect_json=True,
                        images=list(jpgs), temperature=0.2, max_output_tokens=4000)
    try:  # el wrapper no da tokens: ~258 por imagen + 1 cada 3,5 caracteres
        cost_tracking.record_gemini(input_tokens=258 * len(jpgs) + int(len(instr) / 3.5),
                                    output_tokens=int(len(raw) / 3.5), model=MODELO_GEMINI,
                                    detail="editor_auto.referencia_vip (reserva)")
    except Exception:  # noqa: BLE001
        pass
    return _json(raw)


def _num(v, lo: float, hi: float, default: float) -> float:
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return default


def ritmo_desde_video(video: str) -> dict:
    """`ritmo_ref` del vídeo: cortes/min, zooms, rótulos/min y gancho. Lanza si falla."""
    dur = _duracion(video)
    if dur <= 0.5:
        raise RuntimeError("referencia demasiado corta")
    cortes = cortes_de_plano(video)
    cortes_min = round(len(cortes) * 60 / dur, 1)
    dg = min(DUR_GANCHO, dur)
    hoja_g = _hoja(_fotogramas(video, dg, N_GANCHO))
    hoja_t = _hoja(_fotogramas(video, dur, N_TODO))
    instr = (_PROMPT.read_text(encoding="utf-8")
             .replace("{n_gancho}", str(N_GANCHO)).replace("{dur_gancho}", f"{dg:.0f}")
             .replace("{t_gancho}", _tiempos(dg, N_GANCHO)).replace("{n}", str(N_TODO))
             .replace("{dur}", f"{dur:.0f}").replace("{t_todo}", _tiempos(dur, N_TODO))
             .replace("{cortes_min}", str(cortes_min)).replace("{cortes}", str(len(cortes))))
    return ritmo_desde_json(_vision([hoja_g, hoja_t], instr), dur, cortes)


def ritmo_desde_json(d: dict, dur: float, cortes: list[float]) -> dict:
    """Respuesta de la IA + cortes medidos → `ritmo_ref` saneado."""
    zooms = int(_num(d.get("zooms"), 0, 60, 0))
    rot = int(_num(d.get("rotulos"), 0, 80, 0))
    tipo = str(d.get("gancho_tipo") or "").strip().lower()
    return {
        "dur": round(dur, 2),
        "cortes_min": round(len(cortes) * 60 / dur, 1),
        "plano_medio_s": round(dur / (len(cortes) + 1), 2),
        "zooms_min": round(zooms * 60 / dur, 1),
        "zoom_nivel": round(_num(d.get("zoom_nivel"), 1.06, 1.22, 1.12), 2),
        "zoom_pct": round(_num(d.get("zoom_pct"), 0, 0.5, 0.3), 2),
        "temblor": bool(d.get("temblor")),
        "rotulos_min": round(rot * 60 / dur, 1),
        "gancho_texto": str(d.get("gancho_texto") or "").strip()[:80],
        "gancho_tipo": tipo if tipo in _TIPOS_GANCHO else "",
        "gancho_dato": str(d.get("gancho_dato") or "").strip()[:20],
        "gancho_clip": bool(d.get("gancho_clip")),
        "notas": str(d.get("notas") or "").strip()[:400],
    }


def config_desde_ritmo(r: dict) -> dict:
    """Claves de `vip_overlays` que salen del ritmo (densidad, zooms, gancho)."""
    cfg: dict = {"ritmo_ref": r}
    rm = r.get("rotulos_min", 0)
    cfg["densidad_rotulos"] = "alta" if rm >= 10 else "media" if rm >= 6 else "baja"
    cfg["zooms"] = r.get("zooms_min", 0) > 0
    cfg["gancho"] = r.get("gancho_tipo", "") != "ninguno"
    cfg["gancho_clip"] = bool(r.get("gancho_clip"))
    return cfg


def analizar(video: str, log=lambda _m: None) -> dict:
    """Config parcial de `vip_overlays` copiando estilo + ritmo de la referencia.

    Nunca lanza: lo que falle se queda fuera (y se loguea). Incluye `_flujo`
    (subtítulos/flecha para otros pasos) si el estilo lo trae."""
    from .estilo_vip import estilo_desde_video

    cfg: dict = {}
    try:
        cfg.update(estilo_desde_video(video))
    except Exception as e:  # noqa: BLE001
        log(f"[vip] ⚠️ Estilo de la referencia no leído ({str(e)[:200]}).")
    try:
        cfg.update(config_desde_ritmo(ritmo_desde_video(video)))  # el ritmo manda en densidad/zooms
    except Exception as e:  # noqa: BLE001
        log(f"[vip] ⚠️ Ritmo de la referencia no leído ({str(e)[:200]}).")
    return cfg


if __name__ == "__main__":  # python -m src.editor_auto.services.referencia_vip <video>
    import sys
    print(json.dumps(analizar(sys.argv[1], print), ensure_ascii=False, indent=1))
