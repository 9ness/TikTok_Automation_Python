"""Herramienta: cortador de silencios CON GUIÓN de referencia.

Variante del `silence_cutter` para el caso en que el operador entrega
junto al vídeo el guion que el speaker debía decir. El guion actúa como
fuente de verdad: cualquier palabra del transcript Whisper que NO esté
en el guion se considera ruido (filler, repetición, error) y se corta.

Pipeline:

1) **Silero VAD** (gratis) — silencios duros + ruidos no verbales.
2) **Whisper word_timings** — qué se dijo realmente y cuándo.
3) **Diff transcript vs guión** (difflib.SequenceMatcher) — alinea
   palabra a palabra. Regiones del transcript SIN match en el guion
   son candidatas a corte.
4) **(Opcional) 1 pasada GPT-4o** sobre regiones ambiguas
   (`scripted_llm_arbitration`) — decide cut/keep cuando la deriva es
   larga (>2 palabras) y podría ser improvisación legítima.
5) **FFmpeg** — concat de los `keep_intervals` resultantes.

Coste: ~$0.003 por vídeo (solo Whisper + 1 LLM opcional barato). Sin
consenso multi-modelo: el guion ES el ground truth.

Position_weight = 10 (mismo slot que `silence_cutter` — INCOMPATIBLE
con éste en el mismo flujo, validado en `users` router).
"""

from __future__ import annotations

import difflib
import json
import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

from src.editor_auto.config import (
    TOOL_POSITION_WEIGHTS,
    TOOL_SILENCE_CUTTER_SCRIPTED,
)

from .base import ToolContext
from . import silence_cutter as _sc  # reuse helpers


_SAFETY_PAD_S = 0.03
_MIN_KEEP_SEGMENT_S = 0.10
_MIN_REMAINING_S = 0.10
_HEAD_PAD_S = 0.15
_TAIL_PAD_S = 0.05


class SilenceCutterScriptedTool:
    tool_id: str = TOOL_SILENCE_CUTTER_SCRIPTED
    display_name: str = "Cortador de silencios (con guión)"
    description: str = (
        "Igual que el cortador estándar pero usando un guión de referencia "
        "(introducido en el generador) para cortar todo lo que el speaker "
        "diga de más, fillers o repeticiones. Más barato y preciso."
    )
    position_weight: int = TOOL_POSITION_WEIGHTS[TOOL_SILENCE_CUTTER_SCRIPTED]

    def default_config(self) -> dict[str, Any]:
        return {
            "vad_enabled": True,
            "min_silence_ms": 500,
            "padding_ms": 100,
            # Diff transcript ↔ guión: cuántas palabras consecutivas sin
            # match dispara cut. 1 = agresivo (cualquier desvío), mayor =
            # conservador.
            "diff_min_unmatched_words": 1,
            # Pad de seguridad alrededor de palabras en regiones cortadas.
            "diff_safety_pad_s": _SAFETY_PAD_S,
            # LLM arbitrator (opcional) — solo se llama si hay regiones
            # ambiguas (≥`llm_min_region_words` palabras desviadas seguidas).
            # Sin el LLM: cortamos TODA palabra fuera del guion (recomendado
            # por coste: ~$0.003 con solo Whisper).
            "scripted_llm_arbitration": False,
            "llm_min_region_words": 3,
            "ai_model": "gpt-4o",
            "ai_language": "es",
            "whisper_model_size": "small",
            "output_aspect": "9:16",
            "post_audit_enabled": True,
        }

    def config_schema(self) -> list[dict[str, Any]]:
        return [
            {"key": "vad_enabled",
             "label": "Cortar silencios (Silero VAD)", "type": "bool"},
            {"key": "min_silence_ms", "label": "Silencio mínimo VAD (ms)",
             "type": "int", "min": 200, "max": 3000, "step": 50},
            {"key": "padding_ms", "label": "Padding voz VAD (ms)",
             "type": "int", "min": 0, "max": 500, "step": 25},
            {"key": "diff_min_unmatched_words",
             "label": "Palabras consecutivas fuera de guión para cortar",
             "type": "int", "min": 1, "max": 6, "step": 1},
            {"key": "scripted_llm_arbitration",
             "label": "Arbitraje LLM en regiones largas (~+$0.003/video)",
             "type": "bool"},
            {"key": "llm_min_region_words",
             "label": "Tamaño mínimo región para llamar al LLM (palabras)",
             "type": "int", "min": 2, "max": 10, "step": 1},
            {"key": "ai_language", "label": "Idioma audio (ISO 639-1)",
             "type": "string"},
            {"key": "whisper_model_size", "label": "Modelo Whisper",
             "type": "select",
             "options": ["tiny", "base", "small", "medium", "large-v3"]},
            {"key": "output_aspect", "label": "Aspect ratio salida",
             "type": "select", "options": ["9:16", "preserve"]},
            {"key": "post_audit_enabled",
             "label": "Auditoría post-render (quality score)", "type": "bool"},
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
        from src.subtitles_only import extract_audio_from_video

        # El guion lo inyecta el orchestrator desde job.params["script"]. Si
        # no llega, esta tool NO tiene base para alinear → fallback automático
        # a `silence_cutter` normal (mismo recorte de silencios, sin la pasada
        # de diff transcript↔guion). Mantenemos los campos comunes (VAD,
        # idioma, Whisper model, aspect) para que el comportamiento sea lo
        # más parecido posible a lo que el usuario configuró.
        script_raw = (config.get("script") or "").strip()
        if not script_raw:
            ctx.on_log(
                "[silence_cutter_scripted] ⚠️ No se ha encontrado guion para "
                "este vídeo → fallback automático a 'Cortador de silencios' "
                "(modo SIN guion). Los cortes serán por VAD/IA, no por diff "
                "transcript↔guion. Para usar el modo con guion, pega el guion "
                "al encolar el vídeo."
            )
            from src.editor_auto.tools.silence_cutter import SilenceCutterTool
            fallback_tool = SilenceCutterTool()
            fallback_config = fallback_tool.default_config()
            # Pasar los campos comunes que el usuario quizá hubiera tuneado
            # en la config scripted, para respetar sus preferencias.
            _COMMON_KEYS = (
                "vad_enabled", "min_silence_ms", "padding_ms",
                "ai_language", "whisper_model_size", "output_aspect",
                "post_audit_enabled",
            )
            for k in _COMMON_KEYS:
                if k in config:
                    fallback_config[k] = config[k]
            return fallback_tool.run(
                input_path=input_path,
                output_path=output_path,
                config=fallback_config,
                ctx=ctx,
            )

        diagnostic: dict[str, Any] = {
            "job_id": ctx.job_id,
            "user_name": ctx.user_name,
            "input_path": input_path,
            "tool": self.tool_id,
            "config_used": {
                k: config.get(k) for k in (
                    "vad_enabled", "min_silence_ms", "padding_ms",
                    "diff_min_unmatched_words",
                    "scripted_llm_arbitration", "llm_min_region_words",
                    "ai_model", "ai_language",
                    "whisper_model_size", "output_aspect",
                )
            },
            "script_length_chars": len(script_raw),
            "phases": {},
        }

        # 1) Extraer audio
        ctx.on_progress(0.05, "🔊 Extrayendo audio…")
        tmp_dir = Path(ctx.temp_folder)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_audio = str(
            tmp_dir / f"editor_silence_scripted_{ctx.job_id}_{int(time.time())}.wav"
        )
        extract_audio_from_video(input_path, tmp_audio)

        # 2) Duración + rotation
        video_duration, video_rotation = _sc._ffprobe_meta(input_path)
        diagnostic["video_duration_s"] = video_duration
        diagnostic["video_rotation_deg"] = video_rotation
        ctx.on_log(
            f"[silence_cutter_scripted] Input · duración={video_duration:.1f}s "
            f"· rotation={video_rotation}°"
        )

        # 3) Whisper transcribe
        ctx.on_progress(0.10, "🎙️ Whisper transcribiendo…")
        try:
            words = _sc._transcribe(
                tmp_audio,
                model_size=config.get("whisper_model_size", "small"),
                language=config.get("ai_language", "es"),
                on_progress=lambda f, m: ctx.on_progress(0.10 + f * 0.20, m),
            )
            ctx.on_log(f"[silence_cutter_scripted] Whisper · {len(words)} palabras")
        except Exception as e:
            ctx.on_log(f"[silence_cutter_scripted] ⚠️ Whisper falló: {e}")
            words = []
        diagnostic["phases"]["whisper"] = {
            "n_words": len(words),
            "preview_first_10": [w.get("word") for w in words[:10]],
        }

        if not words:
            raise RuntimeError(
                "Whisper no devolvió palabras — no se puede alinear con el guion."
            )

        cuts_with_source: list[tuple[float, float, str]] = []

        # 4) Silero VAD — silencios duros + ruidos no verbales
        vad_on = bool(config.get("vad_enabled", True))
        silero_cuts: list[tuple[float, float]] = []
        silero_diag: dict[str, Any] = {"enabled": vad_on}
        if vad_on:
            ctx.on_progress(0.32, "🛡️ Silero VAD…")
            try:
                speech_intervals = _sc._run_silero_vad(
                    tmp_audio,
                    min_silence_ms=int(config.get("min_silence_ms", 500)),
                    padding_ms=int(config.get("padding_ms", 100)),
                    log=ctx.on_log,
                )
                inv = _sc._invert_intervals(speech_intervals, video_duration)
                min_silence_s = int(config.get("min_silence_ms", 500)) / 1000.0
                silero_cuts = [
                    (a, b) for (a, b) in inv if (b - a) >= min_silence_s
                ]
                silero_diag.update({
                    "n_speech_intervals": len(speech_intervals),
                    "n_silence_cuts": len(silero_cuts),
                })
                ctx.on_log(
                    f"[silence_cutter_scripted] Silero · {len(silero_cuts)} "
                    f"silencios ≥{min_silence_s:.1f}s"
                )
            except ImportError as e:
                silero_diag["error"] = f"ImportError: {e}"
                ctx.on_log(
                    f"[silence_cutter_scripted] ⚠️ Silero VAD no instalado ({e})."
                )
            except Exception as e:
                silero_diag["error"] = f"{type(e).__name__}: {e}"
                ctx.on_log(
                    f"[silence_cutter_scripted] ⚠️ Silero VAD falló ({e})."
                )
        diagnostic["phases"]["silero_vad"] = silero_diag

        # 5) Filtrar palabras fantasma (Whisper alucina en silencios)
        clean_words, phantom_words = _sc._filter_phantom_words(
            words, silero_cuts, min_silence_for_phantom_s=0.5,
        )
        clean_words, trapped_words = _sc._filter_words_trapped_between_silences(
            clean_words, silero_cuts,
            min_silence_s=0.5, max_gap_between_silences_s=1.2,
        )
        if trapped_words:
            phantom_words.extend(trapped_words)
        diagnostic["phases"]["phantom_words"] = {
            "n_phantoms_detected": len(phantom_words),
            "n_clean_words": len(clean_words),
        }

        # 6) Auto-trim head/tail (silencio antes 1ª palabra / tras última)
        head_tail = _sc._compute_head_tail_cuts(clean_words, video_duration)
        for ht in head_tail:
            cuts_with_source.append((ht[0], ht[1], "auto_trim"))
        diagnostic["phases"]["auto_trim"] = {
            "cuts": [{"start": s, "end": e} for s, e in head_tail],
        }

        # 7) **Diff transcript vs guión** — núcleo de esta tool
        ctx.on_progress(0.50, "🔍 Alineando transcript con guión…")
        script_tokens = _tokenize(script_raw)
        transcript_tokens = [_normalize_token(w.get("word", "")) for w in clean_words]
        regions = _diff_regions(
            transcript_tokens=transcript_tokens,
            script_tokens=script_tokens,
            min_unmatched_words=int(config.get("diff_min_unmatched_words", 1)),
        )
        diagnostic["phases"]["script_diff"] = {
            "n_script_tokens": len(script_tokens),
            "n_transcript_tokens": len(transcript_tokens),
            "n_unmatched_regions": len(regions),
            "regions_preview": regions[:15],
        }
        ctx.on_log(
            f"[silence_cutter_scripted] Diff · "
            f"{len(transcript_tokens)} transcript vs {len(script_tokens)} guion "
            f"→ {len(regions)} región(es) fuera de guión"
        )

        # 8) Arbitraje LLM opcional para regiones ambiguas (largas)
        llm_diag: dict[str, Any] = {
            "enabled": bool(config.get("scripted_llm_arbitration", False)),
        }
        decisions_by_region: dict[int, str] = {}
        if llm_diag["enabled"] and regions:
            min_region = int(config.get("llm_min_region_words", 3))
            ambiguous = [
                (i, r) for i, r in enumerate(regions)
                if (r["end_idx"] - r["start_idx"] + 1) >= min_region
            ]
            llm_diag["n_ambiguous"] = len(ambiguous)
            if ambiguous:
                ctx.on_progress(0.58, "🤖 GPT-4o arbitrando regiones largas…")
                try:
                    decisions = _llm_arbitrate(
                        regions=ambiguous,
                        clean_words=clean_words,
                        script=script_raw,
                        model=config.get("ai_model", "gpt-4o"),
                        log=ctx.on_log,
                    )
                    for d in decisions:
                        decisions_by_region[int(d.get("region_id", -1))] = (
                            d.get("action") or "cut"
                        )
                    llm_diag["decisions"] = decisions
                except Exception as e:
                    llm_diag["error"] = f"{type(e).__name__}: {e}"
                    ctx.on_log(
                        f"[silence_cutter_scripted] ⚠️ LLM falló: {e} — "
                        f"cayendo a corte automático de TODAS las regiones."
                    )
        diagnostic["phases"]["llm_arbitration"] = llm_diag

        # 9) Convertir regiones → cuts (start_s, end_s) usando timestamps de
        # `clean_words`. Si una región tiene decisión "keep" del LLM, se
        # respeta (NO se corta).
        pad = float(config.get("diff_safety_pad_s", _SAFETY_PAD_S))
        n_cut_regions = 0
        for i, region in enumerate(regions):
            if decisions_by_region.get(i) == "keep":
                continue
            i0 = region["start_idx"]
            i1 = region["end_idx"]
            if i0 < 0 or i1 >= len(clean_words):
                continue
            t0 = float(clean_words[i0]["start"]) - pad
            t1 = float(clean_words[i1]["end"]) + pad
            t0 = max(0.0, t0)
            t1 = min(video_duration, t1)
            if t1 - t0 < _MIN_REMAINING_S:
                continue
            cuts_with_source.append((t0, t1, "script_diff"))
            n_cut_regions += 1
        diagnostic["phases"]["script_diff"]["n_regions_cut"] = n_cut_regions

        # 10) Añadir silencios Silero (cualquier silencio ≥ threshold)
        # filtrados contra palabras del transcript LIMPIAS — así no cortamos
        # voz por error en gaps pequeños.
        silero_filtered = _sc._trim_cuts_to_avoid_words(
            silero_cuts, words=clean_words, pad_s=pad,
            min_remaining_s=_MIN_REMAINING_S,
        )
        for s, e in silero_filtered:
            cuts_with_source.append((s, e, "silero"))

        # Cleanup audio temporal
        try:
            os.remove(tmp_audio)
        except OSError:
            pass

        # 11) Merge final + invertir → keep_intervals
        if not cuts_with_source:
            diagnostic["final"] = {
                "n_cuts_merged": 0,
                "total_cut_s": 0.0,
                "decision": "passthrough_no_cuts",
            }
            _sc._write_diagnostic(diagnostic, ctx)
            ctx.on_log("[silence_cutter_scripted] Sin cortes → passthrough.")
            _sc._passthrough_with_format(
                input_path, output_path, video_rotation,
                output_aspect=config.get("output_aspect", "9:16"),
                log=ctx.on_log,
            )
            ctx.on_progress(1.0, "✅ Sin cortes (passthrough)")
            return output_path

        cuts_only = [(s, e) for (s, e, _) in cuts_with_source]
        merged_cuts = _sc._merge_intervals(cuts_only)
        keep_intervals = _sc._invert_intervals(merged_cuts, video_duration)
        keep_intervals = [
            (a, b) for (a, b) in keep_intervals
            if (b - a) >= _MIN_KEEP_SEGMENT_S
        ]
        total_cut_s = sum(b - a for a, b in merged_cuts)
        diagnostic["final"] = {
            "cuts_by_source": _sc._count_by_source(cuts_with_source),
            "n_cuts_merged": len(merged_cuts),
            "n_keep_intervals": len(keep_intervals),
            "total_cut_s": round(total_cut_s, 3),
            "kept_duration_s": round(video_duration - total_cut_s, 3),
            "preview_merged_cuts": [
                {"start": round(s, 3), "end": round(e, 3)}
                for s, e in merged_cuts[:20]
            ],
            "preview_keep_intervals": [
                {"start": round(s, 3), "end": round(e, 3)}
                for s, e in keep_intervals[:20]
            ],
        }
        _sc._write_diagnostic(diagnostic, ctx)

        if not keep_intervals:
            raise RuntimeError(
                "Tras aplicar los cortes no queda contenido. Revisa diagnostic."
            )
        ctx.on_log(
            f"[silence_cutter_scripted] Resumen · {len(keep_intervals)} "
            f"segmentos · {total_cut_s:.1f}s eliminados de "
            f"{video_duration:.1f}s "
            f"({total_cut_s/video_duration*100:.0f}%)"
        )

        # 12) Aplicar cortes con FFmpeg
        ctx.on_progress(0.72, "✂️ Aplicando cortes con FFmpeg…")
        _sc._apply_cuts_ffmpeg(
            input_path=input_path,
            output_path=output_path,
            keep_intervals=keep_intervals,
            rotation=video_rotation,
            output_aspect=config.get("output_aspect", "9:16"),
            log=ctx.on_log,
            on_progress=lambda f: ctx.on_progress(0.72 + f * 0.25, "✂️ Renderizando…"),
        )

        # 13) Auditoría post-render
        if bool(config.get("post_audit_enabled", True)):
            ctx.on_progress(0.97, "🔬 Auditoría post-render…")
            audit = _sc._post_render_audit(
                output_path,
                keep_intervals=keep_intervals,
                words=words,
            )
            diagnostic["audit"] = audit
            score = audit.get("quality_score")
            if score is not None:
                ctx.on_log(
                    f"[silence_cutter_scripted] 🏆 Quality {score}/100 — "
                    f"{audit.get('verdict', '?')}"
                )
            _sc._write_diagnostic(diagnostic, ctx)

        ctx.on_progress(1.0, "✅ Cortes aplicados")
        return output_path


# ---------------------------------------------------------------------------
# Tokenizer + diff
# ---------------------------------------------------------------------------
_TOKEN_RE = re.compile(r"[^\w]+", re.UNICODE)


def _strip_accents(s: str) -> str:
    """Quita acentos para comparación robusta — el transcript Whisper
    suele tildar distinto al guion."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _normalize_token(s: str) -> str:
    s = _strip_accents((s or "").lower())
    return _TOKEN_RE.sub("", s)


def _tokenize(text: str) -> list[str]:
    """Texto → lista de tokens normalizados (sin puntuación, sin acentos)."""
    raw = (text or "").split()
    return [t for t in (_normalize_token(w) for w in raw) if t]


def _diff_regions(
    *,
    transcript_tokens: list[str],
    script_tokens: list[str],
    min_unmatched_words: int = 1,
) -> list[dict[str, Any]]:
    """Devuelve los rangos del transcript que NO están en el guion.

    Cada región es `{start_idx, end_idx, transcript_text}` con índices
    INCLUSIVOS dentro de `transcript_tokens` (= índices de `clean_words`).

    Usamos `difflib.SequenceMatcher.get_opcodes()` que devuelve tramos
    de tipo `equal | replace | delete | insert`. Cualquier opcode con
    tag distinto de `equal` que afecte al transcript (`delete` o
    `replace`) es una región fuera de guion.
    """
    if not transcript_tokens:
        return []
    sm = difflib.SequenceMatcher(
        a=transcript_tokens, b=script_tokens, autojunk=False,
    )
    regions: list[dict[str, Any]] = []
    for tag, i1, i2, _j1, _j2 in sm.get_opcodes():
        if tag == "equal" or tag == "insert":
            continue
        # `delete` y `replace` señalan transcript[i1:i2] no presente en script.
        if i2 - i1 < min_unmatched_words:
            continue
        start = i1
        end = i2 - 1
        regions.append({
            "start_idx": start,
            "end_idx": end,
            "n_words": end - start + 1,
            "tag": tag,
            "transcript_text": " ".join(transcript_tokens[i1:i2])[:200],
        })
    return regions


# ---------------------------------------------------------------------------
# LLM arbitrator
# ---------------------------------------------------------------------------
def _load_prompt() -> str:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(base, "prompts", "silence_cutter_scripted.md")
    try:
        with open(p, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _llm_arbitrate(
    *,
    regions: list[tuple[int, dict[str, Any]]],
    clean_words: list[dict],
    script: str,
    model: str,
    log,
) -> list[dict[str, Any]]:
    """1 sola pasada a GPT-4o para decidir cut/keep en regiones largas.

    `regions` viene como lista de `(region_id_original, region_dict)`.
    Devuelve la lista de decisiones que el LLM emite — el caller mapea
    por `region_id` y aplica.
    """
    from src.editor_auto.api.openai_client import analyze_transcript_json

    payload_regions = []
    for rid, r in regions:
        # Snippet con contexto: 3 palabras antes y 3 después
        i0 = max(0, r["start_idx"] - 3)
        i1 = min(len(clean_words) - 1, r["end_idx"] + 3)
        context_words = [w.get("word", "") for w in clean_words[i0 : i1 + 1]]
        region_words = [
            w.get("word", "")
            for w in clean_words[r["start_idx"] : r["end_idx"] + 1]
        ]
        payload_regions.append({
            "region_id": rid,
            "n_words": r["n_words"],
            "region_said": " ".join(region_words),
            "with_context": " ".join(context_words),
        })

    payload = {
        "script": script,
        "regions": payload_regions,
        "language": "es",
    }
    system = _load_prompt()
    log(
        f"[silence_cutter_scripted] LLM arbitrando {len(payload_regions)} "
        f"región(es) ambigua(s) con {model}…"
    )
    result = analyze_transcript_json(
        system_prompt=system,
        user_payload=payload,
        model=model,
        temperature=0.1,
    )
    decisions = result.get("decisions") if isinstance(result, dict) else None
    if not isinstance(decisions, list):
        return []
    out: list[dict[str, Any]] = []
    for d in decisions:
        if not isinstance(d, dict):
            continue
        rid = d.get("region_id")
        action = d.get("action")
        if rid is None or action not in ("cut", "keep"):
            continue
        out.append({
            "region_id": int(rid),
            "action": action,
            "reason": d.get("reason", ""),
        })
    return out
