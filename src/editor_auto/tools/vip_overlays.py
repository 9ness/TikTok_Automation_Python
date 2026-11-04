"""Edición VIP automática: gancho, rótulos, zooms, fotos de apoyo y SFX.

Generaliza la edición VIP hecha a mano del candado (nov 2026) para que salga
sola con el ESTILO de cada cliente:

  - El estilo es la config de la herramienta en el flujo del usuario (colores,
    fuente, densidad de rótulos, fotos sí/no, zooms, SFX, notas libres). Cada
    persona tiene la suya, así que "su estilo" se repite en todos sus vídeos.
  - El plan (qué rótulo, cuándo, qué zoom, qué foto) lo decide la IA
    (`prompts/vip_plan.md`) leyendo el guion con tiempos de ESTE vídeo y los
    sonidos fuertes sin voz (alarmas, pitidos: candidatos a gancho).
  - El render es una pasada de ffmpeg: gancho copiado al principio (opcional,
    con temblor), zooms de golpe, color, píldoras y tarjetas con "pop",
    SFX sintetizados y loudnorm.

Va DESPUÉS del cortador (los tiempos ya son los del vídeo final) y ANTES de
fotos/flecha/subtítulos, que quedan encima. Nunca rompe el flujo: si la IA o
el render fallan, copia la entrada tal cual.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import struct
import subprocess
import time
import wave
from pathlib import Path
from typing import Any

from ..config import TOOL_POSITION_WEIGHTS, TOOL_VIP_OVERLAYS
from .base import ToolContext

_REPO = Path(__file__).resolve().parents[3]
_FONTS = _REPO / "assets" / "fonts"
_BOOM = _REPO / "assets" / "sfx" / "epico" / "boom_grave.wav"
_PROMPT = Path(__file__).resolve().parent.parent / "prompts" / "vip_plan.md"

_DENSIDAD = {"baja": 12.0, "media": 7.0, "alta": 4.5}  # segundos por rótulo
_PRESETS = {
    # Los colores del candado: rojo alerta, amarillo dato, verde ok, negro neutro.
    "impacto": {"color_alerta": "#E61E2D", "color_dato": "#FFD600",
                "color_ok": "#1EB95A", "color_neutro": "#0F0F0F"},
    "limpio": {"color_alerta": "#111111", "color_dato": "#FFFFFF",
               "color_ok": "#111111", "color_neutro": "#111111"},
    "neon": {"color_alerta": "#FF2D95", "color_dato": "#22D3EE",
             "color_ok": "#A3E635", "color_neutro": "#1E1B4B"},
}


class VipOverlaysTool:
    tool_id: str = TOOL_VIP_OVERLAYS
    display_name: str = "✨ Edición VIP (gancho, rótulos, zooms, SFX)"
    description: str = (
        "Edición tipo agencia con el estilo del cliente: la IA lee el guion y "
        "decide gancho, rótulos en píldora, zooms de golpe y fotos de apoyo; "
        "se añaden SFX y color. Va tras el cortador y antes de los subtítulos."
    )
    position_weight: int = TOOL_POSITION_WEIGHTS.get(TOOL_VIP_OVERLAYS, 60)

    def default_config(self) -> dict[str, Any]:
        return {
            "preset": "impacto",
            **_PRESETS["impacto"],
            "font_path": str(_FONTS / "Montserrat-Black.ttf"),
            "densidad_rotulos": "media",
            "gancho": True,
            "gancho_clip": True,
            "fotos": True,
            "max_fotos": 3,
            "zooms": True,
            "sfx": True,
            "sfx_volumen_db": -10.0,
            "color_grade": True,
            "loudnorm": True,
            "rotulo_y_pct": 16.0,
            "notas_estilo": "",
            "whisper_model_size": "large-v3",
            "ai_language": "es",
        }

    def config_schema(self) -> list[dict[str, Any]]:
        return [
            {"key": "preset", "label": "Colores ('personalizado' usa los de abajo)", "type": "select",
             "options": list(_PRESETS) + ["personalizado"]},
            {"key": "color_alerta", "label": "Color alerta/urgencia", "type": "color"},
            {"key": "color_dato", "label": "Color datos/pasos/precio", "type": "color"},
            {"key": "color_ok", "label": "Color beneficio/ok", "type": "color"},
            {"key": "color_neutro", "label": "Color neutro", "type": "color"},
            {"key": "font_path", "label": "Fuente de los rótulos", "type": "font_picker"},
            {"key": "densidad_rotulos", "label": "Cantidad de rótulos", "type": "select",
             "options": list(_DENSIDAD)},
            {"key": "gancho", "label": "Rótulo de gancho al inicio", "type": "bool"},
            {"key": "gancho_clip", "label": "Copiar el momento más llamativo al principio",
             "type": "bool"},
            {"key": "fotos", "label": "Fotos de apoyo (lo que se nombra y no se ve)",
             "type": "bool"},
            {"key": "max_fotos", "label": "Máximo de fotos", "type": "int",
             "min": 0, "max": 8, "step": 1},
            {"key": "zooms", "label": "Zooms de golpe", "type": "bool"},
            {"key": "sfx", "label": "Efectos de sonido", "type": "bool"},
            {"key": "sfx_volumen_db", "label": "Volumen SFX (dB)", "type": "float",
             "min": -30.0, "max": 0.0, "step": 1.0},
            {"key": "color_grade", "label": "Realce de color", "type": "bool"},
            {"key": "loudnorm", "label": "Normalizar volumen (-14 LUFS)", "type": "bool"},
            {"key": "rotulo_y_pct", "label": "Altura de los rótulos (% desde arriba)",
             "type": "float", "min": 5.0, "max": 60.0, "step": 1.0},
            {"key": "notas_estilo", "label": "Cómo le gusta al cliente (lo lee la IA)",
             "type": "text"},
            {"key": "whisper_model_size", "label": "Modelo Whisper", "type": "select",
             "options": ["small", "medium", "large-v3"]},
            {"key": "ai_language", "label": "Idioma audio (ISO 639-1)", "type": "string"},
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
        if cfg.get("preset") in _PRESETS:  # los 4 colores solo cuentan en "personalizado"
            cfg.update(_PRESETS[cfg["preset"]])
        tmp = Path(ctx.temp_folder) / f"vip_{ctx.job_id}_{int(time.time())}"
        tmp.mkdir(parents=True, exist_ok=True)
        try:
            info = _probe(input_path)
            ctx.on_progress(0.05, "🎙️ Transcribiendo para la edición VIP…")
            wav = str(tmp / "audio.wav")
            words = _transcribe(input_path, wav, cfg, ctx) if info["audio"] else []
            if not words:
                ctx.on_log("[vip] Sin voz transcrita — no aplico edición VIP.")
                return _copy(input_path, output_path)
            eventos = _sound_events(wav, words)
            ctx.on_progress(0.5, "🧠 Planificando gancho, rótulos y zooms…")
            plan = _plan(words, info["dur"], eventos, cfg, ctx)
            if not plan:
                return _copy(input_path, output_path)
            g = plan.setdefault("gancho", {}) if isinstance(plan.get("gancho"), dict) else None
            if g is not None and cfg.get("gancho_clip") and not g.get("clip"):
                g["clip"] = _clip_por_sonido(eventos, words)  # la IA a veces no lo propone
            plan = _sanitize(plan, info["dur"], cfg)
            ctx.on_log("[vip] Plan: " + json.dumps(plan, ensure_ascii=False)[:900])
            if plan["correcciones"]:  # para que los subtítulos escriban bien los nombres
                ctx.extras["correcciones"] = plan["correcciones"]
            ctx.on_progress(0.65, "🖼️ Preparando gráficos…")
            _render(input_path, output_path, plan, info, cfg, tmp, ctx)
            ctx.on_progress(1.0, f"✅ VIP: {len(plan['rotulos'])} rótulos, "
                                 f"{len(plan['zooms'])} zooms, {len(plan['fotos'])} fotos")
            return output_path
        except Exception as e:  # noqa: BLE001 — nunca rompe el flujo
            ctx.on_log(f"[vip] ⚠️ Edición VIP falló ({str(e)[-400:]}) — sigo sin ella.")
            return _copy(input_path, output_path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Entrada: probe, transcripción, sonidos sin voz
# ---------------------------------------------------------------------------
def _copy(src: str, dst: str) -> str:
    if os.path.abspath(src) != os.path.abspath(dst):
        shutil.copyfile(src, dst)
    return dst


def _probe(path: str) -> dict:
    out = json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,width,height,r_frame_rate:stream_tags=rotate:stream_side_data=rotation"
         ":format=duration", "-of", "json", path],
        timeout=60))
    sv = next(s for s in out["streams"] if s.get("codec_type") == "video")
    num, _, den = (sv.get("r_frame_rate") or "30/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 30.0
    w, h = int(sv["width"]), int(sv["height"])
    # móvil en vertical: ffmpeg autorrota, así que los filtros ven el lado corto como ancho
    rot = (sv.get("tags") or {}).get("rotate") or next(
        (d.get("rotation") for d in sv.get("side_data_list") or [] if "rotation" in d), 0)
    if abs(int(float(rot or 0))) % 180 == 90:
        w, h = h, w
    return {"dur": float(out["format"]["duration"]), "w": w, "h": h,
            "fps": fps if 10 < fps < 121 else 30.0,
            "audio": any(s.get("codec_type") == "audio" for s in out["streams"])}


def _transcribe(video: str, wav: str, cfg: dict, ctx: ToolContext) -> list[dict]:
    try:
        from src.subtitles_only import extract_audio_from_video, transcribe_with_reference
        extract_audio_from_video(video, wav)
        words = transcribe_with_reference(
            wav, reference_script=None, model_size=cfg.get("whisper_model_size", "large-v3"),
            language=cfg.get("ai_language", "es") or None, audio_type="speech",
            progress_callback=lambda f, m: ctx.on_progress(0.05 + f * 0.4, m),
        )
        return [w for w in (words or []) if str(w.get("word", w.get("text", ""))).strip()]
    except Exception as e:  # noqa: BLE001
        ctx.on_log(f"[vip] ⚠️ Whisper falló ({e}).")
        return []


def _wtext(w: dict) -> str:
    return str(w.get("word", w.get("text", ""))).strip()


def _sound_events(wav: str, words: list[dict], min_db: float = 15.0) -> list[dict]:
    """Tramos ≥0,4 s mucho más fuertes que el fondo y SIN palabras: el producto
    sonando (alarma, pitido, golpe). Son los mejores candidatos a gancho."""
    try:
        import numpy as np
        with wave.open(wav, "rb") as f:
            sr, n, ch, sw = f.getframerate(), f.getnframes(), f.getnchannels(), f.getsampwidth()
            raw = f.readframes(n)
        if sw != 2:
            return []
        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        if ch > 1:
            x = x.reshape(-1, ch).mean(axis=1)
        hop = int(sr * 0.05)
        if len(x) < hop * 10:
            return []
        fr = x[: len(x) // hop * hop].reshape(-1, hop)
        db = 20 * np.log10(np.sqrt((fr ** 2).mean(axis=1)) + 1e-6)
        floor = float(np.percentile(db, 15))
        hot = db > floor + min_db + 10  # bien por encima de la voz normal
        spans = [(float(w.get("start", 0)), float(w.get("end", 0))) for w in words]
        out, i = [], 0
        while i < len(hot):
            if not hot[i]:
                i += 1
                continue
            j = i
            while j < len(hot) and hot[j]:
                j += 1
            a, b = i * 0.05, j * 0.05
            habla = sum(max(0.0, min(b, e) - max(a, s)) for s, e in spans)
            if b - a >= 0.4 and habla < (b - a) * 0.3:
                out.append({"t0": round(a, 2), "t1": round(b, 2),
                            "db_sobre_fondo": round(float(db[i:j].mean()) - floor, 1)})
            i = j
        return out[:8]
    except Exception:  # noqa: BLE001
        return []


def _clip_por_sonido(eventos: list[dict], words: list[dict]) -> dict | None:
    """El sonido fuerte sin voz (después de los 2 primeros s) como clip de gancho:
    1,5-3 s alrededor de él, sin empezar ni acabar a mitad de una palabra."""
    ev = [e for e in eventos if e["t0"] > 2.0]
    if not ev:
        return None
    e = max(ev, key=lambda e: (e["db_sobre_fondo"], e["t1"] - e["t0"]))
    a, b = e["t0"] - 0.3, max(e["t1"] + 0.3, e["t0"] + 1.5)
    for w in words:
        s, t = float(w.get("start", 0)), float(w.get("end", 0))
        if s < a < t:
            a = s
        if s < b < t:
            b = t
    b = min(b, a + 3.0)
    return {"t0": round(a, 2), "t1": round(b, 2)}


# ---------------------------------------------------------------------------
# Plan (IA) y saneado
# ---------------------------------------------------------------------------
def _plan(words: list[dict], dur: float, eventos: list[dict], cfg: dict,
          ctx: ToolContext) -> dict | None:
    from src.editor_auto.api.openai_client import analyze_transcript_json
    payload = {
        "duracion_s": round(dur, 2),
        "palabras": [[round(float(w.get("start", 0)), 2), _wtext(w)] for w in words],
        "sonidos_sin_voz": eventos,
        "estilo_cliente": {
            "max_rotulos": max(2, int(dur / _DENSIDAD.get(cfg.get("densidad_rotulos"), 7.0))),
            "gancho": bool(cfg.get("gancho")),
            "clip_de_gancho": bool(cfg.get("gancho_clip")),
            "fotos": bool(cfg.get("fotos")) and int(cfg.get("max_fotos") or 0) > 0,
            "max_fotos": int(cfg.get("max_fotos") or 0),
            "zooms": bool(cfg.get("zooms")),
            "notas": str(cfg.get("notas_estilo") or "")[:1500],
        },
    }
    try:
        res = analyze_transcript_json(
            system_prompt=_PROMPT.read_text(encoding="utf-8"), user_payload=payload)
        return res if isinstance(res, dict) else None
    except Exception as e:  # noqa: BLE001
        ctx.on_log(f"[vip] ⚠️ La IA no devolvió plan ({str(e)[:200]}).")
        return None


def _num(v, default=0.0) -> float:
    try:
        f = float(v)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def _clean_text(t: str, n: int = 22) -> str:
    t = "".join(ch for ch in str(t or "") if ord(ch) < 0x2000 or ch in "€")
    t = re.sub(r"\s+", " ", t).strip().upper()
    if len(t) > n:  # nunca a mitad de palabra («ELSA PA»)
        t = t[:n + 1].rsplit(" ", 1)[0] if " " in t[:n + 1] else t[:n]
    # unidades que en mayúsculas cambian de sentido o quedan raras
    return re.sub(r"(\d)\s?DB\b", r"\1 dB", t)


_COLORES_STOCK = {
    "rojo": "#E53935", "roja": "#E53935", "naranja": "#FB8C00", "amarillo": "#FDD835",
    "amarilla": "#FDD835", "verde": "#43A047", "azul": "#1E88E5", "morado": "#8E24AA",
    "morada": "#8E24AA", "lila": "#B39DDB", "rosa": "#EC407A", "blanco": "#FAFAFA",
    "blanca": "#FAFAFA", "negro": "#212121", "negra": "#212121", "gris": "#9E9E9E",
    "beige": "#D7C4A3", "marron": "#6D4C41", "marrón": "#6D4C41", "dorado": "#D4AF37",
    "plateado": "#C0C0C0", "plata": "#C0C0C0", "turquesa": "#26C6DA", "granate": "#7B1F2A",
}


def _hex_color(c) -> str:
    """Nombre de color (o #hex) → #hex; '' si no se reconoce."""
    t = str(c or "").strip().lower()
    if re.fullmatch(r"#[0-9a-f]{6}", t):
        return t.upper()
    return _COLORES_STOCK.get(t.split()[0] if t else "", "")


def _sanitize(plan: dict, dur: float, cfg: dict) -> dict:
    """Recorta a la duración, quita solapes y aplica los límites del estilo."""
    def span(d, mn=0.4, mx=6.0):
        a = max(0.0, min(dur, _num(d.get("t0"))))
        b = max(0.0, min(dur, _num(d.get("t1"))))
        if b - a < mn:
            return None
        return a, min(b, a + mx)

    g = plan.get("gancho") or {}
    gancho = {"texto": _clean_text(g.get("texto"), 28) if cfg.get("gancho") else "",
              "dato": _clean_text(g.get("dato"), 10) if cfg.get("gancho") else "", "clip": None,
              "foto": str(g.get("foto") or "").strip()[:80]
              if cfg.get("gancho") and cfg.get("fotos") else ""}
    c = g.get("clip") if cfg.get("gancho_clip") else None
    if isinstance(c, dict):
        s = span(c, 1.2, 3.0)
        if s and s[0] > 2.0:  # si ya está al principio no hace falta copiarlo
            gancho["clip"] = {"t0": s[0], "t1": s[1]}

    top = []  # rótulos y fotos comparten la franja de arriba: nunca a la vez
    max_rot = max(2, int(dur / _DENSIDAD.get(cfg.get("densidad_rotulos"), 7.0)))
    for r in (plan.get("rotulos") or [])[: max_rot + 3]:
        s, txt = span(r, 0.5, 3.5), _clean_text(r.get("texto"), 18)
        if s and txt:
            rol = r.get("rol") if r.get("rol") in ("alerta", "dato", "ok", "neutro") else "neutro"
            top.append({"tipo": "rotulo", "texto": txt, "rol": rol, "t0": s[0], "t1": s[1]})
    st = plan.get("stock")
    if isinstance(st, dict):
        s = span(st, 1.0, 3.5)
        quedan = [_hex_color(c) for c in (st.get("quedan") or [])[:6]]
        quedan = [c for c in quedan if c]
        agot = max(0, min(6 - len(quedan), int(_num(st.get("agotados")))))
        if s and quedan:
            top.append({"tipo": "stock", "quedan": quedan, "agotados": agot,
                        "t0": s[0], "t1": s[1]})
    if cfg.get("fotos"):
        for f in (plan.get("fotos") or [])[: int(cfg.get("max_fotos") or 0)]:
            s, q = span(f, 1.0, 3.5), str(f.get("busqueda") or "").strip()[:80]
            if s and q:
                top.append({"tipo": "foto", "busqueda": q, "t0": s[0], "t1": s[1]})
    stk = next((x for x in top if x["tipo"] == "stock"), None)
    if stk:  # la tarjeta manda: fuera los rótulos que la pisan (suelen decir lo mismo)
        top = [x for x in top if x is stk or x["t1"] <= stk["t0"] - 0.1 or x["t0"] >= stk["t1"] + 0.1]
    top.sort(key=lambda x: x["t0"])
    limpio = []
    for it in top:
        if limpio and it["t0"] < limpio[-1]["t1"] + 0.1:
            if it["t0"] - limpio[-1]["t0"] >= 0.8:
                limpio[-1]["t1"] = it["t0"] - 0.1
            else:
                continue
        limpio.append(it)
    if gancho["texto"]:  # el gancho ocupa la franja los 2 primeros segundos
        limpio = [x for x in limpio if x["t0"] >= 2.1]

    zooms = []
    if cfg.get("zooms"):
        for z in sorted(plan.get("zooms") or [], key=lambda z: _num(z.get("t0"))):
            s = span(z, 0.8, 4.0)
            if not s or (zooms and s[0] < zooms[-1]["t1"] + 0.3):
                continue
            zooms.append({"t0": s[0], "t1": s[1],
                          "nivel": max(1.06, min(1.22, _num(z.get("nivel"), 1.12))),
                          "temblor": bool(z.get("temblor"))})
        tot, kept = 0.0, []
        for z in zooms:  # nunca más de la mitad del vídeo con zoom
            if tot + z["t1"] - z["t0"] <= dur * 0.5:
                kept.append(z)
                tot += z["t1"] - z["t0"]
        zooms = kept
    return {"gancho": gancho, "rotulos": [x for x in limpio if x["tipo"] == "rotulo"],
            "fotos": [x for x in limpio if x["tipo"] == "foto"],
            "stock": next((x for x in limpio if x["tipo"] == "stock"), None), "zooms": zooms,
            "nota": str(plan.get("nota") or "")[:300],
            "correcciones": [{"oido": str(c.get("oido"))[:40], "bien": str(c.get("bien"))[:40]}
                             for c in (plan.get("correcciones") or [])[:8]
                             if isinstance(c, dict) and c.get("oido") and c.get("bien")
                             and str(c["oido"]).lower() != str(c["bien"]).lower()]}


# ---------------------------------------------------------------------------
# Gráficos (PIL)
# ---------------------------------------------------------------------------
def _rgba(hexc: str, a: int = 255) -> tuple:
    h = str(hexc or "#000000").lstrip("#")
    if len(h) != 6:
        h = "000000"
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


def _ink(bg: tuple) -> tuple:
    lum = 0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]
    return (15, 15, 15, 255) if lum > 150 else (255, 255, 255, 255)


def _font(cfg: dict, sz: int):
    from PIL import ImageFont
    for p in (cfg.get("font_path"), str(_FONTS / "Montserrat-Black.ttf")):
        if p and os.path.exists(p):
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


def _pill(text: str, bg: tuple, sz: int, maxw: int, cfg: dict, path: str, rot: float = 0) -> str:
    from PIL import Image, ImageDraw, ImageFilter
    f = _font(cfg, sz)
    while sz > 30 and f.getbbox(text)[2] + sz * 1.2 > maxw:
        sz -= 4
        f = _font(cfg, sz)
    pad = (int(sz * 0.55), int(sz * 0.32))
    bb = f.getbbox(text)
    w, h = bb[2] + pad[0] * 2, bb[3] + pad[1] * 2
    im = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((24, 28, w + 24, h + 28), radius=h // 2, fill=(0, 0, 0, 140))
    im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(8)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((20, 20, w + 20, h + 20), radius=h // 2, fill=bg)
    d.text((20 + pad[0], 20 + pad[1] - bb[1] // 2), text, font=f, fill=_ink(bg))
    if rot:
        im = im.rotate(rot, expand=True, resample=Image.BICUBIC)
    im.save(path)
    return path


def _stock(quedan: list[str], agotados: int, k: float, cfg: dict, path: str) -> str:
    """Tarjeta oscura «QUEDAN» con un círculo por color y los agotados tachados."""
    from PIL import Image, ImageDraw
    k *= 1.6  # en la referencia la tarjeta ocupa casi el ancho del vídeo
    r, gap, pad = int(30 * k), int(22 * k), int(30 * k)
    n = len(quedan) + agotados
    f = _font(cfg, int(34 * k))
    bb = f.getbbox("QUEDAN")
    w = max(n * 2 * r + (n - 1) * gap, bb[2]) + pad * 2
    h = pad + bb[3] + int(18 * k) + 2 * r + pad
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=int(26 * k), fill=(25, 25, 25, 225))
    d.text(((w - bb[2]) // 2, pad - bb[1]), "QUEDAN", font=f, fill=(255, 255, 255, 255))
    x0, cy = (w - (n * 2 * r + (n - 1) * gap)) // 2, pad + bb[3] + int(18 * k) + r
    lw = max(3, int(5 * k))
    for i in range(n):
        cx = x0 + i * (2 * r + gap) + r
        box = (cx - r, cy - r, cx + r, cy + r)
        if i < len(quedan):
            d.ellipse(box, fill=_rgba(quedan[i]), outline=(255, 255, 255, 255), width=lw)
        else:
            d.ellipse(box, outline=(200, 200, 200, 255), width=lw)
            o = int(r * 0.7)
            d.line((cx - o, cy - o, cx + o, cy + o), fill=(200, 200, 200, 255), width=lw)
    im.save(path)
    return path


def _card(src: str, path: str, width: int, rot: float) -> str:
    from PIL import Image, ImageDraw, ImageFilter
    im = Image.open(src).convert("RGB")
    im = im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)
    maxh = int(width * 1.2)
    if im.height > maxh:
        top = (im.height - maxh) // 2
        im = im.crop((0, top, width, top + maxh))
    b = max(8, width // 50)
    c = Image.new("RGBA", (im.width + 2 * b, im.height + 2 * b), (0, 0, 0, 0))
    m = Image.new("L", c.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, *c.size), radius=36, fill=255)
    c.paste(Image.new("RGBA", c.size, (255, 255, 255, 255)), (0, 0), m)
    m2 = Image.new("L", im.size, 0)
    ImageDraw.Draw(m2).rounded_rectangle((0, 0, *im.size), radius=26, fill=255)
    c.paste(im, (b, b), m2)
    pad = 40
    out = Image.new("RGBA", (c.width + 2 * pad, c.height + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((pad + 8, pad + 16, pad + c.width + 8, pad + c.height + 16),
                                         radius=36, fill=(0, 0, 0, 150))
    out = Image.alpha_composite(out, sh.filter(ImageFilter.GaussianBlur(14)))
    out.alpha_composite(c, (pad, pad))
    out.rotate(rot, expand=True, resample=Image.BICUBIC).save(path)
    return path


# ---------------------------------------------------------------------------
# SFX sintetizados (sin depender de bancos externos)
# ---------------------------------------------------------------------------
def _write_wav(path: str, samples, sr: int = 48000) -> str:
    with wave.open(path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sr)
        f.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, s)) * 32000)) for s in samples))
    return path


def _sfx(tipo: str, path: str) -> str:
    import numpy as np
    sr = 48000
    if tipo == "pop":
        t = np.arange(int(sr * 0.09)) / sr
        f = 950 - 5000 * t
        s = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t * 45) * 0.9
    else:  # whoosh: ruido filtrado con barrido
        rng = np.random.default_rng(7)
        n = int(sr * 0.32)
        x = rng.standard_normal(n)
        y = np.zeros(n)
        a = np.linspace(0.02, 0.35, n)
        for i in range(1, n):
            y[i] = y[i - 1] + a[i] * (x[i] - y[i - 1])
        env = np.sin(np.linspace(0, np.pi, n)) ** 2
        s = y / (np.abs(y).max() + 1e-6) * env * 0.7
    return _write_wav(path, s.tolist(), sr)


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------
def _render(src: str, dst: str, plan: dict, info: dict, cfg: dict, tmp: Path,
            ctx: ToolContext) -> None:
    W, H, fps, dur = info["w"], info["h"], info["fps"], info["dur"]
    k = W / 1080.0
    g = plan["gancho"]
    clip = g.get("clip")
    off = (clip["t1"] - clip["t0"]) if clip else 0.0
    total = dur + off
    y_rot = int(H * float(cfg.get("rotulo_y_pct", 16.0)) / 100)
    col = {r: _rgba(cfg.get(f"color_{r}")) for r in ("alerta", "dato", "ok", "neutro")}

    # (png, t0, t1, y) en tiempos de SALIDA
    ovl: list[tuple[str, float, float, int]] = []
    sfx_at: list[tuple[str, float]] = []
    gl = clip["t1"] - clip["t0"] if clip else 2.0
    if g.get("texto"):
        ovl.append((_pill(g["texto"], col["alerta"], int(82 * k), int(W * 0.9), cfg,
                          str(tmp / "g0.png"), -3), 0.0, gl, int(H * 0.135)))
    if g.get("foto"):  # la persona/marca que nombra el gancho: lo que más engancha
        from .photo_insert import _search_and_download
        img = _search_and_download(query=g["foto"], dest=str(tmp / "gf.png"),
                                   prefer_google=False, log=ctx.on_log)
        if img:
            ovl.append((_card(img, str(tmp / "gfc.png"), int(W * 0.55), 3), 0.15, gl,
                        int(H * 0.21)))
            sfx_at.append(("whoosh", 0.15))
    if g.get("dato"):
        ovl.append((_pill(g["dato"], col["dato"], int(150 * k), int(W * 0.8), cfg,
                          str(tmp / "g1.png"), 4), 0.35, gl, int(H * 0.47)))
    rots = [-3, 3, -2, 0, 2]
    for i, r in enumerate(plan["rotulos"]):
        p = _pill(r["texto"], col[r["rol"]], int(84 * k), int(W * 0.86), cfg,
                  str(tmp / f"r{i}.png"), rots[i % len(rots)])
        ovl.append((p, r["t0"] + off, r["t1"] + off, y_rot))
        sfx_at.append(("pop", r["t0"] + off))
    st = plan.get("stock")
    if st:
        ovl.append((_stock(st["quedan"], st["agotados"], k, cfg, str(tmp / "stock.png")),
                    st["t0"] + off, st["t1"] + off, y_rot))
        sfx_at.append(("pop", st["t0"] + off))
    if plan["fotos"]:
        from .photo_insert import _search_and_download
        for i, f in enumerate(plan["fotos"]):
            img = _search_and_download(query=f["busqueda"], dest=str(tmp / f"f{i}.png"),
                                       prefer_google=False, log=ctx.on_log)
            if not img:
                continue
            ovl.append((_card(img, str(tmp / f"c{i}.png"), int(W * 0.62), [-4, 3][i % 2]),
                        f["t0"] + off, f["t1"] + off, int(H * 0.12)))
            sfx_at.append(("whoosh", f["t0"] + off))

    # --- vídeo: (gancho +) original → zoom → color → overlays
    fc: list[str] = []
    has_a = info["audio"]
    if clip:
        fc.append("[0:v]split[va][vb]")
        fc.append(f"[va]trim={clip['t0']:.3f}:{clip['t1']:.3f},setpts=PTS-STARTPTS[hv]")
        fc.append("[vb]setpts=PTS-STARTPTS[mv]")
        if has_a:
            fc.append("[0:a]asplit[aa][ab]")
            fc.append(f"[aa]atrim={clip['t0']:.3f}:{clip['t1']:.3f},asetpts=PTS-STARTPTS,"
                      f"afade=t=out:st={off - 0.04:.3f}:d=0.04[ha]")
            fc.append("[ab]asetpts=PTS-STARTPTS[ma]")
            fc.append("[hv][ha][mv][ma]concat=n=2:v=1:a=1[bv][ba]")
        else:
            fc.append("[hv][mv]concat=n=2:v=1:a=0[bv]")
    else:
        fc.append("[0:v]setpts=PTS-STARTPTS[bv]")
        if has_a:
            fc.append("[0:a]asetpts=PTS-STARTPTS[ba]")

    zs = list(plan["zooms"])
    if clip:  # el gancho entra con zoom y temblor
        zs = [{"t0": -off, "t1": 0.0, "nivel": 1.10, "temblor": True}] + zs
    last = "[bv]"
    if zs:
        zexpr = "1" + "".join(
            f"+{z['nivel'] - 1:.3f}*between(t,{z['t0'] + off:.3f},{z['t1'] + off:.3f})" for z in zs)
        sh = "+".join(f"between(t,{z['t0'] + off:.3f},{z['t1'] + off:.3f})" for z in zs if z["temblor"]) or "0"
        fc.append(f"{last}scale=w='trunc(iw*({zexpr})/2)*2':h='trunc(ih*({zexpr})/2)*2':"
                  f"eval=frame:flags=bicubic,"
                  f"crop={W}:{H}:x='(in_w-{W})/2+({sh})*{12 * k:.1f}*sin(t*47)':"
                  f"y='(in_h-{H})/2+({sh})*{10 * k:.1f}*cos(t*53)',setsar=1[zv]")
        last = "[zv]"
    if cfg.get("color_grade"):
        fc.append(f"{last}eq=saturation=1.15:contrast=1.05,unsharp=5:5:0.5[cv]")
        last = "[cv]"

    inputs = ["-i", src]
    for i, (p, a, b, y) in enumerate(ovl, start=1):
        inputs += ["-loop", "1", "-framerate", f"{fps:.3f}", "-i", p]
        d = b - a
        fc.append(f"[{i}:v]format=rgba,trim=0:{d + 0.05:.3f},setpts=PTS-STARTPTS+{a:.3f}/TB,"
                  f"scale=w='iw*min(1,0.6+0.4*(t-{a:.3f})/0.15)':h=-1:eval=frame,"
                  f"fade=t=out:st={a + d - 0.12:.3f}:d=0.12:alpha=1[o{i}]")
        fc.append(f"{last}[o{i}]overlay=x='(W-w)/2':y='{y}':eof_action=pass:"
                  f"enable='between(t,{a:.3f},{b:.3f})'[x{i}]")
        last = f"[x{i}]"
    fc.append(f"{last}format=yuv420p[vout]")

    # --- audio: SFX + loudnorm
    amap = []
    if has_a:
        alast = "[ba]"
        sfx_in = []
        if cfg.get("sfx"):
            if clip and _BOOM.exists():
                sfx_in.append((str(_BOOM), 0.0, -4.0))
            files = {}
            for tipo, t in sfx_at:
                if tipo not in files:
                    files[tipo] = _sfx(tipo, str(tmp / f"sfx_{tipo}.wav"))
                sfx_in.append((files[tipo], t, 0.0))
        base_idx = 1 + len(ovl)
        vol = float(cfg.get("sfx_volumen_db", -10.0))
        labels = []
        for j, (p, t, extra) in enumerate(sfx_in):
            inputs += ["-i", p]
            ms = int(max(0.0, t) * 1000)
            fc.append(f"[{base_idx + j}:a]aresample=48000,volume={vol + extra:.1f}dB,"
                      f"adelay={ms}:all=1[s{j}]")
            labels.append(f"[s{j}]")
        if labels:
            fc.append(f"{alast}aresample=48000[bm]")
            fc.append(f"[bm]{''.join(labels)}amix=inputs={1 + len(labels)}:"
                      f"duration=first:normalize=0[am]")
            alast = "[am]"
        if cfg.get("loudnorm"):
            fc.append(f"{alast}loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")
        else:
            fc.append(f"{alast}anull[aout]")
        amap = ["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"]

    ctx.on_progress(0.8, "🎬 Renderizando edición VIP…")
    cmd = ["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(fc),
           "-map", "[vout]", *amap, "-t", f"{total:.3f}", "-r", f"{fps:.3f}",
           "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-threads", "2",
           "-map_metadata", "-1", "-movflags", "+faststart", dst]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg VIP: {proc.stderr[-600:]}")
    if clip:  # el gancho es un trozo repetido: sin subtítulos encima
        ctx.extras.setdefault("sin_subs", []).append((0.0, round(off, 3)))
    ctx.on_log(f"[vip] ✅ {len(ovl)} gráficos · {len(zs)} zooms · gancho "
               f"{'copiado ' + format(off, '.1f') + 's' if clip else 'solo rótulo'} · {plan.get('nota', '')}")
