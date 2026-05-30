"""Herramienta: inserción automática de fotos (B-roll) al mencionar
personas famosas / marcas.

Idea: si en el audio se dice "...esta crema la usa Katy Perry...", el tool
detecta la entidad ("Katy Perry"), busca su foto en internet y la
superpone PEQUEÑA en pantalla justo en ese momento. 100% automático: si
no se menciona ninguna persona/marca reconocible, no inserta nada.

Pipeline:
1) Whisper transcribe el vídeo POST-cortes (timestamps válidos sobre el
   vídeo ya editado).
2) Gemini lee la transcripción con timestamps y devuelve SOLO las
   entidades reales que merecen foto (personas famosas, marcas) con su
   segundo de aparición y una query de búsqueda.
3) Por cada entidad: búsqueda de imagen (DuckDuckGo / Google CSE) →
   descarga la mejor → la coloca en la posición/tamaño que el operador
   configuró, durante `duration_seconds`.
4) FFmpeg encadena un overlay por foto con `enable='between(t,T0,T1)'`.

Si Gemini no está configurado, no hay entidades, o no se descarga ninguna
imagen → no-op (copia el input tal cual). NUNCA aborta el pipeline.

Position_weight = 70: después de cortes (10) y antes de flecha (80) y
subs (90), para que flecha y subtítulos queden ENCIMA de la foto si
colisionan.

⚠️ Copyright: usa imágenes de la web abierta (personas/marcas). Riesgo
asumido por el operador; pensado para contenido TikTok orgánico.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import requests

from src.editor_auto.config import TOOL_PHOTO_INSERT, TOOL_POSITION_WEIGHTS

from .base import ToolContext


_ENTITY_TYPE_OPTIONS = ["personas y marcas", "solo personas", "solo marcas"]

_SYSTEM_PROMPT = (
    "Eres un editor de vídeo viral para TikTok. Te paso la transcripción de "
    "un vídeo como lista de palabras con su segundo de inicio. Detecta las "
    "menciones de ENTIDADES RECONOCIBLES que merezcan mostrar una foto "
    "pequeña en pantalla en ese momento (B-roll): personas famosas (cantantes, "
    "actores, deportistas, influencers) y/o marcas conocidas, según el filtro "
    "`types` que te indico.\n\n"
    "Reglas estrictas:\n"
    "- SOLO entidades realmente mencionadas y reconocibles a nivel mundial o "
    "nacional. NO inventes. NO incluyas nombres comunes, pronombres ni la "
    "propia marca del producto que se vende.\n"
    "- Por cada una devuelve: `label` (nombre tal cual se reconoce), "
    "`search_query` (consulta óptima para buscar su foto en un buscador de "
    "imágenes, p.ej. 'Katy Perry' o 'logo Nike'), `t_start` (el segundo, "
    "tomado de los timestamps que te doy, donde EMPIEZA la mención), `type` "
    "('persona' o 'marca').\n"
    "- Máximo `max` entidades, las más relevantes. Si una entidad se repite, "
    "quédate con la primera mención.\n"
    "- Si no hay ninguna entidad clara, devuelve lista vacía.\n\n"
    "Devuelve SOLO JSON válido: {\"inserts\":[{\"label\":..,\"search_query\":..,"
    "\"t_start\":..,\"type\":..}]}"
)

# Headers de navegador para que los CDN no devuelvan 403 al descargar.
_DL_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
}


class PhotoInsertTool:
    tool_id: str = TOOL_PHOTO_INSERT
    display_name: str = "📸 Fotos automáticas (famosos/marcas)"
    description: str = (
        "Detecta cuando el audio nombra a una persona famosa o marca y "
        "superpone su foto en pantalla en ese momento. Whisper + Gemini "
        "deciden qué y cuándo; la imagen se busca en internet. Si no se "
        "menciona a nadie, no inserta nada."
    )
    position_weight: int = TOOL_POSITION_WEIGHTS.get(TOOL_PHOTO_INSERT, 70)

    def default_config(self) -> dict[str, Any]:
        return {
            # Posición del CENTRO de la foto (% del frame). Default: arriba-centro.
            "position_x_pct": 50.0,
            "position_y_pct": 28.0,
            # Tamaño de la foto como % del ancho del vídeo.
            "scale_width_pct": 38.0,
            # Cuánto se mantiene visible cada foto (s).
            "duration_seconds": 2.5,
            # Aparece N s antes del instante de la mención (da margen).
            "lead_seconds": 0.2,
            # Máximo de fotos a insertar en todo el vídeo.
            "max_photos": 5,
            # Qué entidades detectar.
            "entity_types": "personas y marcas",
            # Buscar en Google CSE si está configurado (mejor precisión).
            "prefer_google": False,
            # Whisper para detectar entidades + sus tiempos.
            "whisper_model_size": "large-v3",
            "ai_language": "es",
        }

    def config_schema(self) -> list[dict[str, Any]]:
        return [
            {"key": "position_x_pct",
             "label": "Posición X (% desde la izquierda)",
             "type": "float", "min": 0.0, "max": 100.0, "step": 1.0},
            {"key": "position_y_pct",
             "label": "Posición Y (% desde arriba)",
             "type": "float", "min": 0.0, "max": 100.0, "step": 1.0},
            {"key": "scale_width_pct",
             "label": "Tamaño de la foto (% del ancho del vídeo)",
             "type": "float", "min": 10.0, "max": 80.0, "step": 1.0},
            {"key": "duration_seconds",
             "label": "Duración visible de cada foto (s)",
             "type": "float", "min": 0.5, "max": 8.0, "step": 0.5},
            {"key": "lead_seconds",
             "label": "Aparece N segundos antes de la mención (si no cabe, arranca en el seg 0)",
             "type": "float", "min": 0.0, "max": 5.0, "step": 0.1},
            {"key": "max_photos",
             "label": "Máximo de fotos en el vídeo",
             "type": "int", "min": 1, "max": 12, "step": 1},
            {"key": "entity_types",
             "label": "Qué detectar",
             "type": "select", "options": _ENTITY_TYPE_OPTIONS},
            {"key": "prefer_google",
             "label": "Usar Google CSE si está configurado (mejor precisión)",
             "type": "bool"},
            {"key": "whisper_model_size", "label": "Modelo Whisper",
             "type": "select",
             "options": ["tiny", "base", "small", "medium", "large-v3"]},
            {"key": "ai_language", "label": "Idioma audio (ISO 639-1)",
             "type": "string"},
        ]

    def descriptor(self):  # type: ignore[override]
        from .base import ToolDescriptor
        return ToolDescriptor(
            tool_id=self.tool_id,
            display_name=self.display_name,
            description=self.description,
            position_weight=self.position_weight,
            default_config=self.default_config(),
            config_schema=self.config_schema(),
        )

    def run(
        self,
        *,
        input_path: str,
        output_path: str,
        config: dict[str, Any],
        ctx: ToolContext,
    ) -> str:
        duration = _probe_duration(input_path)
        ctx.on_log(f"[photo_insert] Duración input: {duration:.1f}s")

        # 1) Transcribir para detectar entidades + tiempos.
        ctx.on_progress(0.05, "🎙️ Whisper transcribiendo…")
        words = _transcribe(input_path, config, ctx)
        if not words:
            ctx.on_log("[photo_insert] Sin transcripción — no inserto fotos.")
            return _noop_copy(input_path, output_path)

        # 2) Gemini → entidades con timestamp.
        ctx.on_progress(0.55, "🧠 Detectando famosos/marcas…")
        try:
            max_photos = int(config.get("max_photos", 5) or 5)
        except (TypeError, ValueError):
            max_photos = 5
        inserts = _extract_entities(
            words=words,
            max_n=max_photos,
            entity_types=str(config.get("entity_types", "personas y marcas")),
            ctx=ctx,
        )
        if not inserts:
            ctx.on_log(
                "[photo_insert] No se detectó ninguna persona/marca — "
                "no inserto fotos (es lo esperado en muchos vídeos)."
            )
            return _noop_copy(input_path, output_path)

        ctx.on_log(
            "[photo_insert] Entidades: "
            + " · ".join(f"{i['label']}@{i['t_start']:.1f}s" for i in inserts)
        )

        # 3) Buscar + descargar imagen de cada entidad.
        ctx.on_progress(0.65, "🔎 Buscando imágenes…")
        tmp_dir = Path(ctx.temp_folder)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        prefer_google = bool(config.get("prefer_google", False))
        lead = max(0.0, float(config.get("lead_seconds", 0.2)))
        dur = max(0.5, float(config.get("duration_seconds", 2.5)))

        items: list[dict[str, Any]] = []
        for idx, ins in enumerate(inserts):
            t_start = max(0.0, min(duration, float(ins["t_start"])))
            ws = max(0.0, t_start - lead)
            if ws >= duration:
                continue
            img_path = _search_and_download(
                query=ins["search_query"],
                dest=str(tmp_dir / f"photo_{ctx.job_id}_{idx}.png"),
                prefer_google=prefer_google,
                log=ctx.on_log,
            )
            if not img_path:
                ctx.on_log(f"[photo_insert] ⚠️ Sin imagen para '{ins['label']}' — la salto.")
                continue
            items.append({"path": img_path, "ws": ws, "we": min(duration, ws + dur),
                          "label": ins["label"]})

        if not items:
            ctx.on_log("[photo_insert] Ninguna imagen descargada — no-op.")
            return _noop_copy(input_path, output_path)

        # Ordenar por inicio y recortar solapes (que no se pisen 2 fotos).
        items.sort(key=lambda x: x["ws"])
        for i in range(len(items) - 1):
            if items[i]["we"] > items[i + 1]["ws"]:
                items[i]["we"] = max(items[i]["ws"] + 0.5, items[i + 1]["ws"] - 0.05)

        # 4) FFmpeg: un overlay por foto.
        ctx.on_progress(0.85, "🎬 Insertando fotos…")
        _apply_photo_overlays_ffmpeg(
            input_path=input_path,
            output_path=output_path,
            items=items,
            position_x_pct=float(config.get("position_x_pct", 50.0)),
            position_y_pct=float(config.get("position_y_pct", 28.0)),
            scale_width_pct=float(config.get("scale_width_pct", 38.0)),
            log=ctx.on_log,
        )
        ctx.on_progress(1.0, f"✅ {len(items)} foto(s) insertada(s)")
        return output_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _noop_copy(input_path: str, output_path: str) -> str:
    """Copia el input al output sin tocar — la tool no aplicó nada."""
    if os.path.abspath(input_path) != os.path.abspath(output_path):
        shutil.copyfile(input_path, output_path)
    return output_path


def _probe_duration(path: str) -> float:
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path], timeout=30,
        )
        return float(out.decode().strip())
    except Exception:
        return 0.0


def _probe_video_size(path: str) -> tuple[int, int]:
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "csv=p=0:s=x", path], timeout=30,
        )
        w, h = out.decode().strip().split("x")
        return int(w), int(h)
    except Exception:
        return 0, 0


def _transcribe(input_path: str, config: dict, ctx: ToolContext) -> list[dict]:
    """Whisper local → lista de palabras con `start`. [] si falla."""
    try:
        from src.subtitles_only import (
            extract_audio_from_video,
            transcribe_with_reference,
        )
        tmp_dir = Path(ctx.temp_folder)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_audio = str(tmp_dir / f"photo_insert_{ctx.job_id}_{int(time.time())}.wav")
        extract_audio_from_video(input_path, tmp_audio)
        words = transcribe_with_reference(
            tmp_audio,
            reference_script=None,
            model_size=config.get("whisper_model_size", "large-v3"),
            language=config.get("ai_language", "es") or None,
            audio_type="speech",
            progress_callback=lambda f, m: ctx.on_progress(0.05 + f * 0.45, m),
        )
        try:
            os.remove(tmp_audio)
        except OSError:
            pass
        return words or []
    except Exception as e:
        ctx.on_log(f"[photo_insert] ⚠️ Whisper falló ({e}).")
        return []


def _extract_entities(
    *, words: list[dict], max_n: int, entity_types: str, ctx: ToolContext,
) -> list[dict]:
    """Llama a Gemini con la transcripción y devuelve las entidades válidas
    [{label, search_query, t_start, type}]. [] si no hay o si Gemini falla."""
    try:
        from src.editor_auto.api import gemini_client
        if not gemini_client.is_configured():
            ctx.on_log("[photo_insert] Gemini no configurado — no detecto entidades.")
            return []
        compact = [
            {"w": str(w.get("word", "")).strip(), "s": round(float(w.get("start", 0.0)), 2)}
            for w in words if str(w.get("word", "")).strip()
        ][:1200]
        types_map = {
            "solo personas": "solo personas famosas",
            "solo marcas": "solo marcas",
            "personas y marcas": "personas famosas y marcas",
        }
        result = gemini_client.analyze_transcript_json(
            system_prompt=_SYSTEM_PROMPT,
            user_payload={
                "types": types_map.get(entity_types, "personas famosas y marcas"),
                "max": max_n,
                "words": compact,
            },
            model="gemini-2.5-flash",
            temperature=0.0,
        )
        raw = result.get("inserts") if isinstance(result, dict) else None
        if not isinstance(raw, list):
            return []
        parsed: list[dict] = []
        seen: set[str] = set()
        for it in raw:
            if not isinstance(it, dict):
                continue
            label = str(it.get("label", "")).strip()
            query = str(it.get("search_query", "")).strip() or label
            if not label or label.lower() in seen:
                continue
            try:
                t_start = float(it.get("t_start", 0.0))
            except (TypeError, ValueError):
                continue
            seen.add(label.lower())
            parsed.append({
                "label": label, "search_query": query,
                "t_start": t_start, "type": str(it.get("type", "")),
            })
        # Ordenar por TIEMPO y capar: con max=1 se queda la PRIMERA mención
        # del vídeo (ej. "Elsa Pataky" al inicio), no una posterior.
        parsed.sort(key=lambda x: x["t_start"])
        return parsed[:max_n]
    except Exception as e:
        ctx.on_log(f"[photo_insert] ⚠️ Detección de entidades falló ({e}).")
        return []


def _search_and_download(
    *, query: str, dest: str, prefer_google: bool, log,
) -> str | None:
    """Busca imágenes para `query` y descarga la primera válida a `dest`
    (re-codificada a PNG con PIL para garantizar compatibilidad ffmpeg).
    Devuelve la ruta o None."""
    try:
        from src.tiktok_shop.utils.image_search import search_product_images
        _provider, results = search_product_images(
            query, num=8, prefer_google=prefer_google,
        )
    except Exception as e:
        log(f"[photo_insert] búsqueda falló para '{query}': {e}")
        return None
    for r in results:
        url = (r or {}).get("link", "")
        if not url:
            continue
        if _download_and_normalize(url, dest):
            log(f"[photo_insert] ✅ imagen de '{query}' descargada.")
            return dest
    return None


def _download_and_normalize(url: str, dest: str) -> bool:
    """Descarga `url` y la guarda como PNG RGBA en `dest`. False si falla."""
    try:
        resp = requests.get(url, headers=_DL_HEADERS, timeout=15, stream=True)
        if resp.status_code != 200:
            return False
        raw = resp.content
        if len(raw) < 1024:   # demasiado pequeña — placeholder/error
            return False
        from io import BytesIO

        from PIL import Image
        img = Image.open(BytesIO(raw))
        img.verify()
        img = Image.open(BytesIO(raw)).convert("RGBA")
        # Cap a 1080 de lado largo para no inflar el filtro.
        w, h = img.size
        if max(w, h) > 1080:
            scale = 1080 / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)))
        img.save(dest, format="PNG")
        return True
    except Exception:
        return False


def _apply_photo_overlays_ffmpeg(
    *, input_path: str, output_path: str, items: list[dict],
    position_x_pct: float, position_y_pct: float, scale_width_pct: float,
    log,
) -> None:
    """Encadena un overlay por foto, cada uno con su ventana temporal."""
    px = max(0.0, min(1.0, position_x_pct / 100.0))
    py = max(0.0, min(1.0, position_y_pct / 100.0))
    sw = max(0.05, min(0.8, scale_width_pct / 100.0))

    main_w_px, _h = _probe_video_size(input_path)
    if main_w_px <= 0:
        main_w_px = 1080
    photo_w_px = max(2, int(round(main_w_px * sw)))
    if photo_w_px % 2 != 0:
        photo_w_px -= 1

    # Inputs: 0 = vídeo; 1..N = fotos (loop infinito, acotado por -shortest).
    cmd: list[str] = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning", "-i", input_path,
    ]
    for it in items:
        cmd += ["-loop", "1", "-i", it["path"]]

    scale_parts: list[str] = []
    overlay_parts: list[str] = []
    prev = "[0:v]"
    for i, it in enumerate(items):
        idx = i + 1
        scale_parts.append(
            f"[{idx}:v]scale={photo_w_px}:-2,format=rgba,setsar=1[s{i}]"
        )
        out_label = "[v]" if i == len(items) - 1 else f"[t{i}]"
        overlay_parts.append(
            f"{prev}[s{i}]overlay="
            f"x=(main_w*{px})-(overlay_w/2):"
            f"y=(main_h*{py})-(overlay_h/2):"
            f"enable='between(t,{it['ws']:.3f},{it['we']:.3f})'{out_label}"
        )
        prev = f"[t{i}]"
    filter_complex = ";".join(scale_parts + overlay_parts)

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-c:a", "copy",
        "-shortest", "-movflags", "+faststart",
        output_path,
    ]
    log(
        f"[photo_insert] FFmpeg · {len(items)} foto(s) · scale={sw*100:.0f}% · "
        f"pos=({px*100:.0f}%,{py*100:.0f}%)"
    )
    proc = subprocess.run(cmd, capture_output=True, timeout=1800)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="ignore")[-500:]
        raise RuntimeError(f"FFmpeg falló (photo_insert): {err}")
