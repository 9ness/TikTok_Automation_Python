"""Herramienta: cortador inteligente de silencios + frases sucias.

Combina 3 fuentes para decidir qué cortar:

1) **Auto-trim head/tail** — usa el primer y último `word_start/end` de
   Whisper para recortar silencio antes de hablar y después de terminar.
   Funciona incluso si Silero VAD y OpenAI fallan.

2) **Silero VAD** — detecta tramos de silencio real entre voz. Cortes
   determinísticos basados en amplitud / clasificador VAD.

3) **OpenAI GPT-4o sobre transcript** — recibe palabras con timestamps +
   `total_duration_s` y devuelve cuts para: false-starts, frases sucias,
   self-corrections, gaps mid-phrase (tos / chasquido), etc.

Los 3 conjuntos se fusionan en intervalos no-solapantes y se aplica un
único pase con **FFmpeg directo** (filter_complex `trim+atrim+concat`)
que respeta la rotation metadata del input (clave para .mov de iPhone:
MoviePy ignora `Display Matrix → rotation: -90` y exporta horizontal).

Position_weight = 10 → siempre PRIMERO en el flujo del orchestrator.

Dependencias opcionales:
  - `silero-vad` (PyPI) — si falta, fallback solo IA + auto-trim.
  - `OPENAI_API_KEY` env — si falta, fallback solo VAD + auto-trim.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from src.editor_auto.config import TOOL_POSITION_WEIGHTS, TOOL_SILENCE_CUTTER

from .base import ToolContext


# Constantes — ajustables por config del usuario salvo donde se indique fijo.
# Pads separados: head deja aire al inicio para que el viewer no entre "en
# medio" de la primera palabra. Tail es agresivo (50ms) porque cualquier
# audio post-última-palabra suele ser cola residual o ruido que el viewer
# oye como sílabas sueltas ("e" tras 'surrealista' en el caso real).
_HEAD_PAD_S = 0.15
_TAIL_PAD_S = 0.05
_HEAD_TAIL_PAD_S = 0.15        # legacy alias — usado por algunos callers
_HEAD_TRIM_THRESHOLD_S = 0.5   # silencio inicial mínimo para cortar
_TAIL_TRIM_THRESHOLD_S = 0.5   # silencio final mínimo para cortar
_MIN_KEEP_SEGMENT_S = 0.10     # subclips <100ms generan slivers audibles ("cua")
_MERGE_TOLERANCE_S = 0.08      # cuts separados por <80ms se fusionan → sin slivers
# Pad de seguridad alrededor de cada palabra Whisper cuando hacemos trim de
# cuts acústicos. Más bajo = recuperamos más silencio real (Whisper alarga
# `word.end` más allá del audio audible). Más alto = más conservador. 30ms
# es el sweet spot tras analizar diagnósticos reales — antes 80ms se comía
# silencios ≥1s que Silero sí detectaba.
_SAFETY_PAD_S = 0.03
_MIN_REMAINING_S = 0.10        # sub-cuts más cortos tras trim se descartan
# Margen INTOCABLE alrededor de cada palabra al aplicar CUALQUIER corte. Tras
# fusionar todos los cortes (IA, gap, acústica, silero…), ningún corte puede
# empezar a menos de esto tras el fin de una palabra ni acabar a menos de esto
# antes del inicio de la siguiente. Los timestamps de Whisper marcan el fin de
# palabra un poco PRONTO (se come la consonante final, ej. la "n" de "bien"),
# así que sin este guard los cortes clipan finales de palabra. 150ms es
# imperceptible como pausa pero preserva el audio real de la palabra con
# margen de sobra (objetivo: NUNCA comerse una palabra).
_WORD_GUARD_S = 0.15


class SilenceCutterTool:
    tool_id: str = TOOL_SILENCE_CUTTER
    display_name: str = "Cortador de silencios"
    description: str = (
        "Recorta silencios iniciales/finales, gaps de respiración o ruido "
        "(Silero VAD), y frases dichas a medias o re-empezadas (GPT-4o)."
    )
    position_weight: int = TOOL_POSITION_WEIGHTS[TOOL_SILENCE_CUTTER]

    def default_config(self) -> dict[str, Any]:
        return {
            "vad_enabled": True,
            "min_silence_ms": 500,
            # Margen que se conserva alrededor de cada tramo de voz. 150ms
            # evita comerse el final de las palabras al cortar (antes 100).
            # Súbelo más (180-220) si aún recorta finales.
            "padding_ms": 150,
            # Capa de detección por amplitud (ffmpeg silencedetect) — captura
            # "ejem ejem" con boca cerrada y respiraciones que Silero VAD
            # clasifica falsamente como voz. NO usa modelo, solo dB threshold.
            "amplitude_enabled": True,
            "amplitude_noise_db": -30.0,    # debajo de -30dB se considera silencio
            "amplitude_min_silence_s": 0.4, # gap mínimo en segundos para cortar
            # Cortes determinísticos por gap entre palabras (basado en
            # word_timings de Whisper). NO depende de IA: los gaps son
            # hechos objetivos. Cualquier silencio entre palabras ≥
            # `inter_word_gap_threshold_s` se corta automáticamente.
            # ESTE es el caso principal del usuario: 1-2s entre frases.
            "inter_word_gap_enabled": True,
            # Bajado de 0.6 → 0.5: el caso típico del usuario "1 segundo de
            # pausa entre frases" ahora se corta sin depender de la IA.
            "inter_word_gap_threshold_s": 0.5,
            "inter_word_gap_keep_ms": 200,  # cuánta pausa natural conservar
            "ai_clean_enabled": True,
            "ai_model": "gpt-4o",
            "ai_language": "es",
            # Pasada 2 IA — especialista en false-starts. Cada modelo es
            # toggleable independientemente para balancear coste/fiabilidad:
            #   - Solo Gemini (default, ~$0.015 total/vid): pass1 GPT-4o
            #     + pass2 Gemini 2.5 Pro. Gemini es más agresivo en español
            #     y barato. La heurística n-gram cubre repeticiones literales.
            #   - Solo OpenAI: pass1+2 GPT-4o (~$0.024). Sin red de seguridad
            #     ante non-determinismo (caso real visto en producción).
            #   - Ambos (consenso, ~$0.027): los 2 modelos en pass2. Máxima
            #     fiabilidad, recomendado para vídeos premium.
            "ai_false_starts_pass2": True,
            # Default = consenso PRO: GPT-4o pass2 + Gemini 2.5 Pro pass2.
            # Más caro (~+$0.008/min de vídeo) pero máxima fiabilidad — la
            # pasada 2 cubre false-starts que escapan al pass1 y entre 2
            # modelos hay red de seguridad ante non-determinismo (caso real
            # visto en prod: gpt-4o se atascó en una iteración, gemini lo
            # salvó). Si quieres bajar costes, desactiva uno de los dos
            # toggles en la config UI.
            "ai_pass2_openai_enabled": True,
            "ai_pass2_gemini_enabled": True,
            "gemini_model": "gemini-2.5-pro",
            # `large-v3` por defecto — máxima precisión. ~3-5x más lento
            # que `small` y ~6-8GB RAM (vs ~1GB). El operador puede bajar
            # a `medium` o `small` si el server va justo de recursos.
            "whisper_model_size": "large-v3",
            "output_aspect": "9:16",
            # Auditoría post-render: re-analizar el MP4 final con
            # silencedetect para validar calidad y dar quality score.
            "post_audit_enabled": True,
            # ---- Detección de estilo (monólogo vs conversación) ----
            # Si `auto_detect_style=True` (default), una heurística analiza el
            # output de Silero VAD para decidir si el vídeo es monólogo o
            # conversación y ajusta los thresholds de cortes en consecuencia.
            # Si está OFF, se usa `manual_style` directamente.
            # En conversación, `inter_word_gap_threshold_s` sube de 0.5 → 1.2
            # y `inter_word_gap_keep_ms` sube de 200 → 350: respeta los
            # silencios naturales entre turnos de habla en vez de comerse
            # cada pausa entre frases.
            "auto_detect_style": True,
            "manual_style": "monologue",  # solo usado si auto_detect_style=False
        }

    def config_schema(self) -> list[dict[str, Any]]:
        return [
            {"key": "vad_enabled", "label": "Cortar silencios (Silero VAD — clasificador voz)",
             "type": "bool"},
            {"key": "min_silence_ms", "label": "Silencio mínimo VAD (ms)",
             "type": "int", "min": 200, "max": 3000, "step": 50},
            {"key": "padding_ms", "label": "Padding voz VAD (ms)",
             "type": "int", "min": 0, "max": 500, "step": 25},
            {"key": "amplitude_enabled",
             "label": "Cortar silencios por amplitud (ejem/respiración)",
             "type": "bool"},
            {"key": "amplitude_noise_db",
             "label": "Umbral silencio (dB, más negativo = más estricto)",
             "type": "float", "min": -60.0, "max": -10.0, "step": 1.0},
            {"key": "amplitude_min_silence_s",
             "label": "Duración mínima silencio amplitud (s)",
             "type": "float", "min": 0.2, "max": 3.0, "step": 0.1},
            {"key": "inter_word_gap_enabled",
             "label": "Cortar gaps entre frases (determinístico, recomendado)",
             "type": "bool"},
            {"key": "inter_word_gap_threshold_s",
             "label": "Gap mínimo entre frases para cortar (s)",
             "type": "float", "min": 0.3, "max": 3.0, "step": 0.1},
            {"key": "inter_word_gap_keep_ms",
             "label": "Pausa natural a conservar (ms)",
             "type": "int", "min": 50, "max": 600, "step": 50},
            {"key": "ai_clean_enabled",
             "label": "Limpieza IA general (GPT-4o pasada 1)", "type": "bool"},
            {"key": "ai_false_starts_pass2",
             "label": "Pasada 2 IA: especialista false-starts",
             "type": "bool"},
            # Toggles de modelo en pasada 2 — combinarlos define el preset:
            #   solo Gemini   → modo NORMAL (~$0.010/min de video)
            #   solo OpenAI   → modo legacy (~$0.016/min)
            #   ambos         → modo PRO consenso (~$0.018/min, máx fiabilidad)
            #   ninguno       → solo heurística n-gram (~$0.008/min, sin IA pass2)
            {"key": "ai_pass2_openai_enabled",
             "label": "  · GPT-4o en pasada 2 (~+$0.008/min de video)",
             "type": "bool"},
            {"key": "ai_pass2_gemini_enabled",
             "label": "  · Gemini 2.5 Pro en pasada 2 (~+$0.002/min de video)",
             "type": "bool"},
            {"key": "ai_language", "label": "Idioma audio (ISO 639-1)",
             "type": "string"},
            {"key": "whisper_model_size", "label": "Modelo Whisper",
             "type": "select",
             "options": ["tiny", "base", "small", "medium", "large-v3"]},
            {"key": "output_aspect", "label": "Aspect ratio salida",
             "type": "select", "options": ["9:16", "preserve"]},
            {"key": "post_audit_enabled",
             "label": "Auditoría post-render (quality score)", "type": "bool"},
            {"key": "auto_detect_style",
             "label": "Detección automática de estilo (monólogo vs conversación)",
             "type": "bool"},
            {"key": "manual_style",
             "label": "Estilo del vídeo (si detección auto está OFF)",
             "type": "select",
             "options": ["monologue", "conversation"]},
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

        vad_on = bool(config.get("vad_enabled", True))
        amp_on = bool(config.get("amplitude_enabled", True))
        ai_on = bool(config.get("ai_clean_enabled", True))

        # Estructura `diagnostic` que se persistirá a JSON al final. Cada
        # fase añade su sección con cuts en bruto + decisión final → es la
        # fuente de verdad para iterar sobre por qué algo se cortó o no.
        diagnostic: dict[str, Any] = {
            "job_id": ctx.job_id,
            "user_name": ctx.user_name,
            "input_path": input_path,
            "config_used": {
                k: config.get(k) for k in (
                    "vad_enabled", "min_silence_ms", "padding_ms",
                    "amplitude_enabled", "amplitude_noise_db",
                    "amplitude_min_silence_s",
                    "ai_clean_enabled", "ai_model", "ai_language",
                    "whisper_model_size", "output_aspect",
                )
            },
            "phases": {},
        }

        # 0) MODO MANUAL — el editor manual del operador pasa los tramos a
        # CONSERVAR ya decididos. Saltamos TODA la detección (whisper/silero/
        # amplitud/IA/holístico) y renderizamos directamente esos intervalos.
        # Las tools posteriores (subs/flecha) se re-alinean solas sobre el
        # resultado. Es lo que usa el re-render del retoque manual.
        manual_keep = config.get("manual_keep_intervals")
        if manual_keep:
            video_duration, video_rotation = _ffprobe_meta(input_path)
            keep_intervals = _merge_intervals([
                (float(a), float(b)) for a, b in manual_keep
                if float(b) - float(a) >= _MIN_KEEP_SEGMENT_S
            ])
            if not keep_intervals:
                keep_intervals = [(0.0, video_duration)]
            ctx.on_log(
                f"[silence_cutter] ✋ Modo MANUAL: {len(keep_intervals)} tramo(s) "
                f"dados por el operador (sin detección automática)."
            )
            norm_cfg = config.get("audio_normalize", None)
            if norm_cfg is None:
                try:
                    mv = _measure_mean_volume_db(input_path)
                    normalize_audio = mv is not None and mv < -24.0
                except Exception:  # noqa: BLE001
                    normalize_audio = False
            else:
                normalize_audio = bool(norm_cfg)
            ctx.on_progress(0.4, "✂️ Aplicando cortes manuales…")
            _apply_cuts_ffmpeg(
                input_path=input_path,
                output_path=output_path,
                keep_intervals=keep_intervals,
                rotation=video_rotation,
                output_aspect=config.get("output_aspect", "9:16"),
                log=ctx.on_log,
                on_progress=lambda f: ctx.on_progress(0.4 + f * 0.6, "✂️ Renderizando…"),
                normalize_audio=normalize_audio,
            )
            ctx.on_progress(1.0, "✅ Cortes manuales aplicados")
            return output_path

        # 1) Extraer audio
        ctx.on_progress(0.05, "🔊 Extrayendo audio…")
        tmp_dir = Path(ctx.temp_folder)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_audio = str(tmp_dir / f"editor_silence_{ctx.job_id}_{int(time.time())}.wav")
        extract_audio_from_video(input_path, tmp_audio)

        # 2) Duración + rotation del vídeo
        video_duration, video_rotation = _ffprobe_meta(input_path)
        diagnostic["video_duration_s"] = video_duration
        diagnostic["video_rotation_deg"] = video_rotation
        ctx.on_log(
            f"[silence_cutter] Input · duración={video_duration:.1f}s · "
            f"rotation={video_rotation}°"
        )

        cuts_with_source: list[tuple[float, float, str]] = []  # (s, e, fuente)
        words: list[dict] = []

        # 3) Whisper transcribe (necesario para auto-trim, IA y filtro anti-pisar-voz)
        if vad_on or ai_on or amp_on:
            ctx.on_progress(0.10, "🎙️ Whisper transcribiendo…")
            try:
                words = _transcribe(
                    tmp_audio,
                    model_size=config.get("whisper_model_size", "large-v3"),
                    language=config.get("ai_language", "es"),
                    on_progress=lambda f, m: ctx.on_progress(0.10 + f * 0.18, m),
                    timeout_s=int(config.get("whisper_timeout_s", 1200)),
                    fallback_model=str(config.get("whisper_fallback_model", "small")),
                    primary_threads=int(config.get("whisper_cpu_threads", 1)),
                )
                ctx.on_log(f"[silence_cutter] Whisper · {len(words)} palabras")
            except Exception as e:
                ctx.on_log(f"[silence_cutter] ⚠️ Whisper falló: {e}")
                words = []

            diagnostic["phases"]["whisper"] = {
                "n_words": len(words),
                "first_word": words[0] if words else None,
                "last_word": words[-1] if words else None,
                "preview_first_10": [w.get("word") for w in words[:10]],
                "preview_last_5": [w.get("word") for w in words[-5:]],
            }

        # 3b) FILLERS ESTIRADOS — palabra que dura ANORMALMENTE mucho. A veces
        # es un sonido no-hablado etiquetado como palabra ("la"/risa), PERO a
        # veces es una palabra REAL cuyo final Whisper estiró metiéndole el
        # silencio de después ("adidas" 0.5s + 2.8s de silencio absorbido).
        # Por eso NO las cortamos enteras (borraría la palabra real). En su
        # lugar las DESPROTEGEMOS: la capa de amplitud cortará solo el trozo
        # realmente SILENCIOSO dentro del span (mantiene la palabra, quita el
        # silencio/relleno). Seguro: nunca borra voz audible.
        stretched_spans: list[tuple[float, float]] = []
        if words and bool(config.get("cut_stretched_fillers", True)):
            sf = _detect_stretched_fillers(words)
            stretched_spans = [(s, e) for s, e, _t, _d in sf]
            diagnostic["phases"]["stretched_fillers"] = {
                "n": len(sf),
                "preview": [
                    {"word": t, "dur": round(d, 2), "start": round(s, 2)}
                    for s, e, t, d in sf[:10]
                ],
            }
            if sf:
                ctx.on_log(
                    f"[silence_cutter] 🗣️ {len(sf)} palabra(s) estirada(s) "
                    f"(posible risa/silencio absorbido) → desprotegidas para que "
                    f"la amplitud limpie el silencio: "
                    + ", ".join(f"'{t}'({d:.1f}s)" for _, _, t, d in sf[:6])
                )
            # CORTE DETERMINISTA de la cola de FILLERS alargados — para que esos
            # "aaa"/"laaa"/"eeeh" de relleno NO sobrevivan según el humor de la
            # IA (hacían que el score variara 85↔97). Solo tokens de relleno
            # CONOCIDOS (`_FILLER_TOKENS`) claramente alargados (≥1.2s): jamás
            # toca palabras reales (p.ej. "adidas" 3.3s NO está en la lista).
            # Conserva 0.15s de cabeza (sin clic) y corta el resto.
            if bool(config.get("cut_stretched_filler_tails", True)):
                _KEEP_HEAD = 0.15
                n_tail = 0
                for s, e, tok, dur in sf:
                    if tok in _FILLER_TOKENS and dur >= 1.2:
                        cut_s = s + _KEEP_HEAD
                        if e - cut_s > 0.3:
                            cuts_with_source.append((cut_s, e, "stretched_filler"))
                            n_tail += 1
                if n_tail:
                    ctx.on_log(
                        f"[silence_cutter] ✂️ {n_tail} cola(s) de filler alargado "
                        f"cortada(s) determinísticamente (consistencia de score)."
                    )

        # 4) Silero VAD PRIMERO — es la fuente de verdad para silencios.
        # Va antes de cualquier cálculo basado en palabras porque después
        # necesitamos sus silence_intervals para detectar palabras fantasma.
        silero_cuts: list[tuple[float, float]] = []
        silero_diag: dict[str, Any] = {"enabled": vad_on}
        if vad_on:
            ctx.on_progress(0.30, "🛡️ Silero VAD…")
            try:
                speech_intervals = _run_silero_vad(
                    tmp_audio,
                    min_silence_ms=int(config.get("min_silence_ms", 500)),
                    padding_ms=int(config.get("padding_ms", 100)),
                    log=ctx.on_log,
                )
                inv = _invert_intervals(speech_intervals, video_duration)
                min_silence_s = int(config.get("min_silence_ms", 500)) / 1000.0
                silero_cuts = [(a, b) for (a, b) in inv if (b - a) >= min_silence_s]
                silero_diag.update({
                    "n_speech_intervals": len(speech_intervals),
                    "n_silence_cuts": len(silero_cuts),
                    "preview_speech": speech_intervals[:10],
                    "preview_silence_cuts": silero_cuts[:10],
                })
                ctx.on_log(
                    f"[silence_cutter] Silero · {len(silero_cuts)} silencios "
                    f"≥{min_silence_s:.1f}s (de {len(speech_intervals)} tramos de voz)"
                )
            except ImportError as e:
                silero_diag["error"] = f"ImportError: {e}"
                ctx.on_log(
                    f"[silence_cutter] ⚠️ Silero VAD no instalado ({e})."
                )
            except Exception as e:
                silero_diag["error"] = f"{type(e).__name__}: {e}"
                ctx.on_log(f"[silence_cutter] ⚠️ Silero VAD falló ({e}).")
        diagnostic["phases"]["silero_vad"] = silero_diag

        # 4.5) Detección de estilo (monólogo vs conversación) + overrides.
        # Si `auto_detect_style=True`, la heurística sobre Silero decide.
        # Si está OFF, usa `manual_style` (default 'monologue' = legacy).
        # En 'conversation', sube el threshold de inter-word-gap de 0.5 →
        # 1.2s y el keep_ms de 200 → 350: preserva los gaps naturales de
        # turn-taking en vez de cortarlos.
        auto_detect = bool(config.get("auto_detect_style", True))
        if auto_detect and vad_on:
            try:
                speech_for_detect = speech_intervals  # type: ignore[has-type]
            except NameError:
                speech_for_detect = []
            style_decision, style_metrics = _detect_conversation_style(
                speech_for_detect, video_duration,
            )
            ctx.on_log(
                f"[silence_cutter] 🎬 Estilo auto-detectado: "
                f"{style_decision.upper()} · "
                f"mean_seg={style_metrics.get('mean_segment_s', '?')}s · "
                f"turn_gap_ratio={style_metrics.get('turn_gap_ratio', '?')} · "
                f"motivo: {style_metrics.get('reason')}"
            )
        else:
            style_decision = str(config.get("manual_style", "monologue")).lower()
            if style_decision not in ("monologue", "conversation"):
                style_decision = "monologue"
            style_metrics = {
                "style": style_decision,
                "reason": (
                    "manual (auto-detect OFF)" if not auto_detect
                    else "VAD desactivado — usando manual"
                ),
            }
            ctx.on_log(
                f"[silence_cutter] 🎬 Estilo manual: {style_decision.upper()} "
                f"(auto_detect={auto_detect}, vad_on={vad_on})"
            )
        diagnostic["phases"]["style_detection"] = style_metrics
        # Aplicar overrides: copy local de config con thresholds ajustados.
        config = _apply_style_overrides(config, style_decision)
        if style_decision == "conversation":
            ctx.on_log(
                f"[silence_cutter]   → modo CONVERSACIÓN: "
                f"inter_word_gap_threshold={config['inter_word_gap_threshold_s']}s "
                f"(default 0.5), keep_ms={config['inter_word_gap_keep_ms']}ms "
                f"(default 200) — preserva gaps de turn-taking."
            )

        # 5) Detectar palabras fantasma de Whisper usando Silero como
        # source of truth. Si Whisper transcribe una palabra DENTRO de un
        # silencio real (≥0.7s), es alucinación → la quitamos para que NO
        # bloquee los cuts acústicos ni el cálculo de gaps entre frases.
        # threshold 0.5s (bajado de 0.7s) — captura palabras alucinadas en
        # silencios Silero más cortos. El caso real era silencio Silero
        # [26.6, 27.1] de 0.5s con palabra Whisper inventada dentro que
        # protegía el cut del IWG (gap real 'todas'→'hecho' = 1.28s).
        clean_words, phantom_words = _filter_phantom_words(
            words, silero_cuts, min_silence_for_phantom_s=0.5,
        )
        # NUEVA capa: palabras atrapadas entre 2 silencios Silero cercanos
        # (gap < 1.2s). Caso real "cua" entre Android y "esto costaba":
        # Silero detectó [53.5, 55.1] y [55.9, 56.7]. Whisper alucinó una
        # palabra en ~55.5 que no estaba dentro de ningún silencio pero
        # sí "atrapada" entre los dos → fantasma.
        clean_words, trapped_words = _filter_words_trapped_between_silences(
            clean_words, silero_cuts,
            min_silence_s=0.5, max_gap_between_silences_s=1.2,
        )
        if trapped_words:
            phantom_words.extend(trapped_words)
            ctx.on_log(
                f"[silence_cutter] 🪤 {len(trapped_words)} palabra(s) "
                f"atrapadas entre silencios Silero → fantasmas adicionales"
            )
            for w in trapped_words[:3]:
                ctx.on_log(
                    f"[silence_cutter]   trapped '{w.get('word')}' @ "
                    f"{float(w['start']):.2f}-{float(w['end']):.2f}s"
                )
        diagnostic["phases"]["phantom_words"] = {
            "n_phantoms_detected": len(phantom_words),
            "n_clean_words": len(clean_words),
            "previews": [
                {"idx": w.get("idx"), "word": w.get("word"),
                 "start": float(w["start"]), "end": float(w["end"])}
                for w in phantom_words[:10]
            ],
        }
        if phantom_words:
            ctx.on_log(
                f"[silence_cutter] 👻 {len(phantom_words)} palabra(s) "
                f"fantasma detectadas (Whisper alucinó dentro de silencios "
                f"Silero). Se ignorarán para detección de gaps y cuts."
            )
            for w in phantom_words[:5]:
                ctx.on_log(
                    f"[silence_cutter]   fantasma '{w.get('word')}' "
                    f"[{w.get('idx')}] @ {float(w['start']):.2f}-"
                    f"{float(w['end']):.2f}s"
                )

        # 6) Auto-trim head/tail — usa clean_words (sin fantasmas iniciales)
        head_tail = _compute_head_tail_cuts(clean_words, video_duration)
        for ht in head_tail:
            cuts_with_source.append((ht[0], ht[1], "auto_trim"))
            ctx.on_log(
                f"[silence_cutter] Auto-trim cortar [{ht[0]:.2f}, {ht[1]:.2f}] "
                f"= {ht[1]-ht[0]:.2f}s"
            )
        diagnostic["phases"]["auto_trim"] = {
            "cuts": [{"start": s, "end": e} for s, e in head_tail],
        }

        # 7) DETERMINÍSTICO: cortes por gap entre palabras consecutivas
        # ≥ `inter_word_gap_threshold_s`. Usa `clean_words` para que las
        # fantasmas no "partan" un gap grande entre frases en dos pequeños.
        # Ejemplo: si entre 'momento' (48.0) y 'lo' (49.56) Whisper alucinó
        # una palabra a 48.7s, sin filtro el IWG vería dos gaps pequeños
        # (<0.6s cada uno) y no cortaría. Con fantasma eliminada, ve el
        # gap real de 1.56s y lo corta.
        iwg_diag: dict[str, Any] = {
            "enabled": bool(config.get("inter_word_gap_enabled", True)),
            "threshold_s": float(config.get("inter_word_gap_threshold_s", 0.5)),
            "keep_ms": int(config.get("inter_word_gap_keep_ms", 200)),
        }
        if iwg_diag["enabled"] and clean_words:
            iwg_cuts_detailed = _compute_inter_word_gap_cuts(
                clean_words,
                threshold_s=iwg_diag["threshold_s"],
                keep_ms=iwg_diag["keep_ms"],
            )
            iwg_diag["n_cuts"] = len(iwg_cuts_detailed)
            iwg_diag["cuts"] = iwg_cuts_detailed[:30]
            for c in iwg_cuts_detailed:
                cuts_with_source.append((c["t_start"], c["t_end"], "inter_word_gap"))
            ctx.on_log(
                f"[silence_cutter] Inter-word gaps · {len(iwg_cuts_detailed)} "
                f"silencios ≥{iwg_diag['threshold_s']}s entre frases"
            )
            for c in sorted(iwg_cuts_detailed, key=lambda x: -x["gap_s"])[:3]:
                ctx.on_log(
                    f"[silence_cutter]   gap {c['gap_s']:.2f}s entre "
                    f"'{c.get('after_word')}' [{c['after_word_idx']}] y "
                    f"'{c.get('before_word')}' [{c['before_word_idx']}]"
                )
        diagnostic["phases"]["inter_word_gap"] = iwg_diag

        # 6) Amplitude detector (ffmpeg silencedetect) — captura "ejem ejem",
        # respiraciones cerradas y zonas realmente sin audio que Silero
        # clasificó como voz por error.
        #
        # Auto-calibración: medimos el RMS de la voz real (palabras Whisper)
        # y ponemos el threshold de silencio en `speech_rms - 15dB`. Si la
        # voz va a -22dB, el silencio se detecta a < -37dB. Si hay ruido
        # ambiente a -30dB, ya no lo confundimos con silencio. Fallback a
        # -30dB fijo si la medición falla.
        amp_cuts: list[tuple[float, float]] = []
        amp_diag: dict[str, Any] = {"enabled": amp_on}
        mean_vol_db: float | None = None  # nivel global → decide normalización
        if amp_on:
            ctx.on_progress(0.42, "📉 Calibrando umbral por amplitud…")
            speech_rms_db: float | None = None
            try:
                speech_rms_db = _measure_speech_rms_db(tmp_audio, words)
            except Exception as e:
                ctx.on_log(f"[silence_cutter] ⚠️ RMS speech falló ({e}).")

            user_threshold = float(config.get("amplitude_noise_db", -30.0))
            # Umbral anclado a la MEDIA real de la pista (volumedetect). En
            # grabaciones de mala SNR (voz bajita + ruido de sala) las pausas a
            # cortar quedan SOLO ~10dB por encima de la media: p.ej. media -35dB
            # → pausas ~-27dB, que con un umbral fijo de -30 NO se detectaban
            # (quedaban por encima) y dejaban silencios sin cortar. mean+10
            # sigue al nivel real de cada grabación y coincide con el umbral del
            # auditor (-25 para esta clienta). Se acota para no cortar voz
            # (cap -24) ni inventar silencios en pistas limpias (piso -45).
            try:
                mean_vol_db = _measure_mean_volume_db(tmp_audio)
            except Exception as e:
                ctx.on_log(f"[silence_cutter] ⚠️ volumedetect falló ({e}).")

            if mean_vol_db is not None:
                auto_threshold = mean_vol_db + 10.0
                noise_db = min(max(auto_threshold, -45.0), -24.0)
                amp_diag["mean_volume_db"] = round(mean_vol_db, 2)
                amp_diag["auto_threshold_db"] = round(auto_threshold, 2)
                if speech_rms_db is not None:
                    amp_diag["speech_rms_db"] = round(speech_rms_db, 2)
                ctx.on_log(
                    f"[silence_cutter] Media pista @ {mean_vol_db:.1f}dB "
                    f"→ umbral silencio {noise_db:.1f}dB"
                )
            elif speech_rms_db is not None:
                # Fallback al modelo antiguo si volumedetect falla.
                auto_threshold = speech_rms_db - 15.0
                noise_db = max(auto_threshold, user_threshold)
                amp_diag["speech_rms_db"] = round(speech_rms_db, 2)
                amp_diag["auto_threshold_db"] = round(auto_threshold, 2)
                ctx.on_log(
                    f"[silence_cutter] Voz @ {speech_rms_db:.1f}dB → "
                    f"umbral adaptativo {noise_db:.1f}dB (fallback sin media)"
                )
            else:
                noise_db = user_threshold

            try:
                min_dur = float(config.get("amplitude_min_silence_s", 0.4))
                amp_cuts = _run_silencedetect(
                    tmp_audio, noise_db=noise_db, min_duration_s=min_dur,
                )
                amp_diag.update({
                    "noise_db": noise_db,
                    "min_duration_s": min_dur,
                    "n_cuts_raw": len(amp_cuts),
                    "preview_cuts": amp_cuts[:10],
                })
                ctx.on_log(
                    f"[silence_cutter] Amplitud · {len(amp_cuts)} silencios "
                    f"<{noise_db:.1f}dB durante ≥{min_dur}s"
                )
            except Exception as e:
                amp_diag["error"] = f"{type(e).__name__}: {e}"
                ctx.on_log(f"[silence_cutter] ⚠️ silencedetect falló ({e}).")
        diagnostic["phases"]["amplitude"] = amp_diag

        # Cuts Silero de ALTA CONFIANZA (≥0.8s) → se aplican TAL CUAL sin
        # pasar por el filtro de palabras. Whisper a menudo alucina palabras
        # cortas en silencios largos con ruido ambiente (motor, viento) que
        # protegen los cuts y dejan silencios reales en el output. Si Silero
        # está seguro durante >0.8s, le hacemos caso por encima de Whisper.
        silero_high, silero_normal = _split_silero_cuts_by_confidence(
            silero_cuts, high_confidence_threshold_s=0.8,
        )

        # Palabras-fantasma POR AMPLITUD: Whisper a veces coloca palabras
        # reales (no "uh/um", que Silero sí caza) con timestamps erróneos
        # DENTRO de un silencio acústico medido (voz bajita / mala SNR). Si
        # el span de la palabra está casi todo por debajo del umbral de
        # silencio, es inaudible → la quitamos de las listas de protección
        # para que el corte acústico no se fragmente a su alrededor y deje el
        # silencio sin cortar.
        voiced_words = clean_words
        if amp_cuts and clean_words:
            voiced_words, amp_ghosts = _drop_words_inside_silences(
                clean_words, amp_cuts,
            )
            if amp_ghosts:
                ctx.on_log(
                    f"[silence_cutter] 👻 {len(amp_ghosts)} palabra(s) "
                    f"fantasma por amplitud (dentro de silencio real, "
                    f"inaudibles) — no protegen cortes: "
                    + ", ".join(f"'{w.get('word')}'" for w in amp_ghosts[:8])
                )
        # Palabras ESTIRADAS → fuera de la protección, para que la amplitud
        # corte el silencio absorbido dentro de su span (mantiene la voz real).
        if stretched_spans:
            def _is_stretched(w: dict) -> bool:
                try:
                    ws = float(w["start"]); we = float(w["end"])
                except (KeyError, ValueError, TypeError):
                    return False
                return any(abs(ws - a) < 0.01 and abs(we - b) < 0.01
                           for a, b in stretched_spans)
            voiced_words = [w for w in voiced_words if not _is_stretched(w)]

        # Cuts NORMAL (Silero <0.8s + amplitude) → pasan por el trim de
        # palabras para no cortar voz por error en gaps pequeños.
        acoustic_normal_raw = silero_normal + amp_cuts
        acoustic_filtered = _trim_cuts_to_avoid_words(
            acoustic_normal_raw, words=voiced_words, pad_s=_SAFETY_PAD_S,
            min_remaining_s=_MIN_REMAINING_S,
        )
        # Aplicar AMBOS sets de cuts
        for s, e in acoustic_filtered:
            cuts_with_source.append((s, e, "acoustic"))
        for s, e in silero_high:
            cuts_with_source.append((s, e, "silero_high_conf"))

        diagnostic["phases"]["acoustic_combined"] = {
            "n_silero_high_conf": len(silero_high),
            "n_raw_normal": len(acoustic_normal_raw),
            "n_kept_after_word_filter": len(acoustic_filtered),
            "preview_high_conf": silero_high[:10],
            "preview_filtered": acoustic_filtered[:15],
        }
        if silero_high:
            ctx.on_log(
                f"[silence_cutter] 🔇 Silero high-confidence · "
                f"{len(silero_high)} silencios ≥0.8s aplicados directos "
                f"(saltan filtro de palabras)"
            )
        if acoustic_normal_raw:
            ctx.on_log(
                f"[silence_cutter] Acústicos normales · {len(acoustic_filtered)} "
                f"sub-cuts tras recortar bordes (de {len(acoustic_normal_raw)} brutos)"
            )

        # 6c) LIMPIEZA HOLÍSTICA (Gemini, 1 pasada sobre el guion entero).
        # Es el remover de CONTENIDO autoritativo: ve toda la transcripción y
        # decide qué conservar (una instancia de cada repetición/CTA/precio,
        # sin falsos inicios, frases enteras). Sustituye el pegado frágil de
        # cortes parciales (ngram + pasada 2) que oscilaba entre over-cut y
        # dejar repeticiones. Si funciona, desactivamos ngram y pasada 2.
        holistic_ok = False
        holistic_on = bool(config.get("ai_holistic_clean", True))
        holistic_diag: dict[str, Any] = {"enabled": holistic_on}
        if holistic_on and words:
            ctx.on_progress(0.56, "🧠 Limpieza holística del guion (Gemini)…")
            hol_intervals, hol_diag = _ai_holistic_clean_removes(
                words=words,
                language=config.get("ai_language", "es"),
                model=config.get("gemini_model", "gemini-2.5-pro"),
                log=ctx.on_log,
            )
            holistic_diag.update(hol_diag)
            if hol_intervals:
                holistic_ok = True
                for s, e in hol_intervals:
                    cuts_with_source.append((s, e, "ai_holistic"))
        diagnostic["phases"]["ai_holistic"] = holistic_diag

        # 7) IA — frases sucias, false-starts, gaps mid-phrase
        ai_diag: dict[str, Any] = {"enabled": ai_on}
        ai_cuts: list[tuple[float, float]] = []
        if ai_on and words:
            ctx.on_progress(0.58, "🤖 GPT-4o analizando transcript…")
            try:
                ai_cuts, ai_raw_result = _ai_cleanup_cuts_with_raw(
                    words=words,
                    video_duration=video_duration,
                    language=config.get("ai_language", "es"),
                    model=config.get("ai_model", "gpt-4o"),
                    log=ctx.on_log,
                )
                ai_diag.update({
                    "model": config.get("ai_model", "gpt-4o"),
                    "summary": (ai_raw_result or {}).get("summary"),
                    "raw_cuts": (ai_raw_result or {}).get("cuts", []),
                    "n_cuts_parsed": len(ai_cuts),
                    "cuts_by_reason": _count_by_reason(
                        (ai_raw_result or {}).get("cuts", [])
                    ),
                })
                for s, e in ai_cuts:
                    cuts_with_source.append((s, e, "ai"))
            except Exception as e:
                ai_diag["error"] = f"{type(e).__name__}: {e}"
                ctx.on_log(
                    f"[silence_cutter] ⚠️ Limpieza IA falló: {e}"
                )
        diagnostic["phases"]["ai"] = ai_diag

        # 7a) HEURÍSTICA DETERMINÍSTICA — n-gramas consecutivos repetidos.
        # Cubre el caso "esto costaba esto costaba" que la pasada 2 IA a
        # veces ignora (GPT-4o no es determinístico: mismo input → resultado
        # distinto entre runs). Esto SIEMPRE detecta repeticiones literales.
        ngram_diag: dict[str, Any] = {"enabled": not holistic_ok}
        if clean_words and not holistic_ok:
            ngram_cuts_detailed = _detect_repeated_ngrams(
                clean_words, min_n=2, max_n=6, max_gap_between_grams_s=0.6,
            )
            ngram_diag["n_cuts"] = len(ngram_cuts_detailed)
            ngram_diag["cuts"] = ngram_cuts_detailed[:15]
            for c in ngram_cuts_detailed:
                i0 = int(c["start_word_idx"])
                i1 = int(c["end_word_idx"])
                t0 = float(clean_words[i0]["start"]) if i0 < len(clean_words) else None
                t1 = float(clean_words[i1]["end"]) if i1 < len(clean_words) else None
                if t0 is not None and t1 is not None and t1 - t0 > 0.05:
                    cuts_with_source.append((t0, t1, "ngram_repetition"))
            if ngram_cuts_detailed:
                ctx.on_log(
                    f"[silence_cutter] 🔁 N-gram repetition · "
                    f"{len(ngram_cuts_detailed)} repeticiones literales detectadas "
                    f"(determinístico, sin IA)"
                )
                for c in ngram_cuts_detailed[:3]:
                    ctx.on_log(
                        f"[silence_cutter]   ✂ '{c['first_attempt']}' → "
                        f"mantengo '{c['kept_version']}'"
                    )
        diagnostic["phases"]["ngram_repetition"] = ngram_diag

        # 7b) PASADA 2 IA — especialista en false-starts/repeticiones.
        # Va aparte porque el prompt es muy distinto (precisión > recall).
        #
        # Estrategia de consenso multi-modelo: invocamos GPT-4o + Gemini
        # 2.5 Pro y hacemos UNIÓN de cuts. Los LLMs son no-determinísticos
        # (mismo input → resultado distinto), pero rara vez los DOS fallan
        # a la vez. Coste extra Gemini ~$0.003. Total pass 2 ~$0.015.
        ai_pass2_on = bool(config.get("ai_false_starts_pass2", True)) and not holistic_ok
        ai_pass2_diag: dict[str, Any] = {"enabled": ai_pass2_on}
        if ai_pass2_on and words:
            ctx.on_progress(0.62, "🤖 Pasada 2: GPT-4o + Gemini 2.5 Pro…")
            try:
                fs_intervals, fs_diag = _ai_false_starts_consensus(
                    words=words,
                    language=config.get("ai_language", "es"),
                    openai_model=config.get("ai_model", "gpt-4o"),
                    gemini_model=config.get("gemini_model", "gemini-2.5-pro"),
                    openai_enabled=bool(config.get("ai_pass2_openai_enabled", False)),
                    gemini_enabled=bool(config.get("ai_pass2_gemini_enabled", True)),
                    log=ctx.on_log,
                )
                ai_pass2_diag.update(fs_diag)
                ai_pass2_diag["n_cuts_applied"] = len(fs_intervals)
                for s, e in fs_intervals:
                    cuts_with_source.append((s, e, "ai_pass2"))
            except Exception as e:
                ai_pass2_diag["error"] = f"{type(e).__name__}: {e}"
                ctx.on_log(
                    f"[silence_cutter] ⚠️ Pasada 2 IA falló: {e}"
                )
        diagnostic["phases"]["ai_pass2_false_starts"] = ai_pass2_diag

        # Cleanup audio temporal
        try:
            os.remove(tmp_audio)
        except OSError:
            pass

        # 8) Merge final + invertir → keep_intervals
        if not cuts_with_source:
            diagnostic["final"] = {
                "n_cuts_merged": 0,
                "total_cut_s": 0.0,
                "decision": "passthrough_no_cuts",
            }
            _write_diagnostic(diagnostic, ctx)
            ctx.on_log("[silence_cutter] No hay cortes a aplicar → passthrough.")
            _passthrough_with_format(
                input_path, output_path, video_rotation,
                output_aspect=config.get("output_aspect", "9:16"),
                log=ctx.on_log,
            )
            ctx.on_progress(1.0, "✅ Sin cortes (passthrough)")
            return output_path

        # 7c) PROTECCIÓN DEL CIERRE — el vídeo nunca debe terminar TRUNCADO a
        # media frase. Una capa de palabras (AI/holistic/ngram) puede marcar el
        # cierre real (CTA final) como repetición y comerse las últimas
        # palabras (p.ej. acabar en "...el día 7" y borrar "...la tuya").
        # Quirúrgico: clipamos SOLO los cortes que llegan hasta la última
        # palabra HABLADA — quedan recortando únicamente el silencio posterior.
        # Los dedups INTERNOS (false-starts en mitad del cierre) NO se tocan
        # porque no alcanzan el final.
        if bool(config.get("protect_closing", True)) and voiced_words:
            last_word_end = max(float(w["end"]) for w in voiced_words)
            tail_eps = 0.2  # un corte que acaba a <0.2s del final = se come el cierre
            n_pre_close = len(cuts_with_source)
            protected = False
            new_cws: list[tuple[float, float, str]] = []
            for s, e, src in cuts_with_source:
                if s < last_word_end - 0.05 and e >= last_word_end - tail_eps:
                    # se come voz final → recortar solo el silencio tras ella
                    if e > last_word_end:
                        new_cws.append((last_word_end, e, src))
                    protected = True
                else:
                    new_cws.append((s, e, src))
            cuts_with_source = new_cws
            if protected:
                diagnostic["phases"]["closing_protection"] = {
                    "enabled": True,
                    "last_word_end": round(last_word_end, 3),
                    "cuts_before": n_pre_close,
                    "cuts_after": len(cuts_with_source),
                }
                ctx.on_log(
                    f"[silence_cutter] 🛡️ Cierre protegido: un corte se comía "
                    f"la última frase (fin voz {last_word_end:.1f}s) → "
                    f"restaurada (evita truncar el CTA final)."
                )

        cuts_only = [(s, e) for (s, e, _) in cuts_with_source]
        merged_cuts = _merge_intervals(cuts_only)
        # Protección de palabras: ningún corte clipa el final/inicio de una
        # palabra (guard de _WORD_GUARD_S). Se aplica sobre voiced_words
        # (sin fantasmas Silero NI fantasmas por amplitud) tras fusionar —
        # cubre TODAS las fuentes de corte. Usar voiced_words evita que una
        # palabra inaudible dentro de un silencio real proteja (y deje sin
        # cortar) ese silencio.
        n_before = len(merged_cuts)
        if voiced_words:
            merged_cuts = _protect_word_boundaries(
                merged_cuts, voiced_words, _WORD_GUARD_S,
            )
            merged_cuts = _merge_intervals(merged_cuts)  # re-merge por si encogieron
            ctx.on_log(
                f"[silence_cutter] 🛡️ Protección de palabras (guard "
                f"{int(_WORD_GUARD_S*1000)}ms): {n_before} → {len(merged_cuts)} cortes"
            )
        # Ajuste FINAL al silencio real (amplitud) — el guard por Whisper no
        # basta porque Whisper cierra palabras hasta ~400ms pronto. La
        # amplitud dice dónde hay audio de verdad → ningún corte empieza/acaba
        # dentro de una palabra audible.
        if amp_cuts:
            n_pre_amp = len(merged_cuts)
            merged_cuts = _clamp_cuts_to_silence_edges(merged_cuts, amp_cuts)
            merged_cuts = _merge_intervals(merged_cuts)
            ctx.on_log(
                f"[silence_cutter] 🔊 Bordes ajustados al silencio real "
                f"(amplitud): {n_pre_amp} → {len(merged_cuts)} cortes"
            )
        keep_intervals = _invert_intervals(merged_cuts, video_duration)
        keep_intervals = [
            (a, b) for (a, b) in keep_intervals
            if (b - a) >= _MIN_KEEP_SEGMENT_S
        ]

        # Proyecto editable — para el retoque manual: input original, palabras
        # Whisper y los tramos conservados. run.py lo coloca junto al output.
        _write_edit_project(
            ctx, input_path=input_path, words=words,
            keep_intervals=keep_intervals, video_duration=video_duration,
        )

        total_cut_s = sum(b - a for a, b in merged_cuts)
        diagnostic["final"] = {
            "cuts_by_source": _count_by_source(cuts_with_source),
            "word_guard_ms": int(_WORD_GUARD_S * 1000),
            "n_cuts_merged": len(merged_cuts),
            "n_keep_intervals": len(keep_intervals),
            "total_cut_s": round(total_cut_s, 3),
            "kept_duration_s": round(video_duration - total_cut_s, 3),
            "preview_merged_cuts": [
                {"start": round(s, 3), "end": round(e, 3)} for s, e in merged_cuts[:20]
            ],
            "preview_keep_intervals": [
                {"start": round(s, 3), "end": round(e, 3)} for s, e in keep_intervals[:20]
            ],
        }
        _write_diagnostic(diagnostic, ctx)

        if not keep_intervals:
            raise RuntimeError(
                "Tras aplicar los cortes no queda contenido. "
                f"Revisa el diagnóstico en {ctx.temp_folder}/editor_diagnostic_{ctx.job_id}.json"
            )

        ctx.on_log(
            f"[silence_cutter] Resumen · {len(keep_intervals)} segmentos · "
            f"{total_cut_s:.1f}s eliminados de {video_duration:.1f}s "
            f"({total_cut_s/video_duration*100:.0f}%) · "
            f"fuentes: {diagnostic['final']['cuts_by_source']}"
        )

        # 9) Aplicar cortes con FFmpeg directo (autorotate nativo respeta rotation)
        # Normalización de loudness: SOLO si la pista viene baja (auto). Sube
        # grabaciones flojas a -16 LUFS para que se OIGAN (creadoras que graban
        # bajito). No toca a quien ya graba a buen nivel → general y seguro.
        # Override manual con config `audio_normalize` (None = auto por nivel).
        norm_cfg = config.get("audio_normalize", None)
        if norm_cfg is None:
            normalize_audio = mean_vol_db is not None and mean_vol_db < -24.0
        else:
            normalize_audio = bool(norm_cfg)
        if normalize_audio:
            ctx.on_log(
                f"[silence_cutter] 🔊 Audio bajo (media "
                f"{mean_vol_db if mean_vol_db is not None else float('nan'):.1f}dB) "
                f"→ normalizo a -16 LUFS para que se oiga."
            )
        diagnostic["final"]["audio_normalized"] = normalize_audio
        ctx.on_progress(0.72, "✂️ Aplicando cortes con FFmpeg…")
        _apply_cuts_ffmpeg(
            input_path=input_path,
            output_path=output_path,
            keep_intervals=keep_intervals,
            rotation=video_rotation,
            output_aspect=config.get("output_aspect", "9:16"),
            log=ctx.on_log,
            on_progress=lambda f: ctx.on_progress(0.72 + f * 0.25, "✂️ Renderizando…"),
            normalize_audio=normalize_audio,
        )

        # 10) Auditoría post-render — analizar el MP4 final con silencedetect
        # y mapear cada silencio remanente al INPUT con las palabras vecinas
        # del transcript. Esto da feedback "between 'palabra1' y 'palabra2'"
        # imprescindible para iterar.
        if bool(config.get("post_audit_enabled", True)):
            ctx.on_progress(0.97, "🔬 Auditoría post-render…")
            audit = _post_render_audit(
                output_path,
                keep_intervals=keep_intervals,
                words=words,
                stretched_spans=stretched_spans,
            )
            diagnostic["audit"] = audit
            score = audit.get("quality_score")
            verdict = audit.get("verdict", "?")
            if score is not None:
                ctx.on_log(
                    f"[silence_cutter] 🏆 Quality score: {score}/100 — {verdict}"
                )
                # Aviso de FALLO REAL → conviene reencolar (no es solo estética)
                if audit.get("needs_requeue"):
                    bits = []
                    if not audit.get("transcription_ok", True):
                        bits.append("SIN transcripción")
                    if audit.get("n_loose_words"):
                        lw = ", ".join(
                            f"'{p['text']}'"
                            for p in audit.get("loose_words_preview", [])[:4]
                        )
                        bits.append(f"{audit['n_loose_words']} palabra(s) suelta(s): {lw}")
                    if audit.get("n_surviving_stretched"):
                        bits.append(
                            f"{audit['n_surviving_stretched']} relleno(s) estirado(s) sin cortar"
                        )
                    motivo = " · ".join(bits) if bits else "score bajo"
                    ctx.on_log(
                        f"[silence_cutter] 🚩 REENCOLAR recomendado "
                        f"({score}/100): {motivo}"
                    )
                n_internal = audit.get("n_internal_silences", 0)
                if n_internal > 0:
                    ctx.on_log(
                        f"[silence_cutter] ⚠️ {n_internal} silencio(s) ≥"
                        f"{audit['long_silence_threshold_s']}s SIN cortar. "
                        f"Detalle:"
                    )
                    for p in audit.get("internal_silences_preview", [])[:5]:
                        ctx_words = (p.get("context") or {})
                        before = (ctx_words.get("before_word") or {}).get("word") or "—"
                        after = (ctx_words.get("after_word") or {}).get("word") or "—"
                        input_range = (
                            f"input[{p.get('input_start', '?')}, "
                            f"{p.get('input_end', '?')}]"
                            if p.get("input_start") is not None else ""
                        )
                        ctx.on_log(
                            f"[silence_cutter]   • {p['duration_s']:.2f}s "
                            f"entre '{before}' y '{after}' {input_range}"
                        )
            else:
                ctx.on_log(
                    f"[silence_cutter] ⚠️ Auditoría post-render falló: "
                    f"{audit.get('error', 'desconocido')}"
                )
            # Reescribir el diagnóstico con la sección audit añadida
            _write_diagnostic(diagnostic, ctx)

        ctx.on_progress(1.0, "✅ Cortes aplicados")
        return output_path


def _write_edit_project(
    ctx, *, input_path: str, words: list[dict],
    keep_intervals: list[tuple[float, float]], video_duration: float,
) -> None:
    """Persiste el 'proyecto editable' (retoque manual) en `temp_folder`.

    Contiene lo que el editor manual necesita: el input ORIGINAL, las palabras
    Whisper (idx/word/start/end) y los tramos conservados por el algoritmo.
    `run.py` lo reubica junto al output (`salida/.editproj/<output>.json`).
    Best-effort: nunca rompe el job.
    """
    try:
        proj = {
            "input_path": input_path,
            "video_duration_s": round(float(video_duration), 3),
            "keep_intervals": [
                [round(float(a), 3), round(float(b), 3)] for a, b in keep_intervals
            ],
            "words": [
                {
                    "idx": i,
                    "word": str(w.get("word", "")).strip(),
                    "start": round(float(w["start"]), 3),
                    "end": round(float(w["end"]), 3),
                }
                for i, w in enumerate(words)
                if "start" in w and "end" in w
            ],
        }
        out = Path(ctx.temp_folder) / f"editproject_{ctx.job_id}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(proj, f, ensure_ascii=False)
        ctx.on_log(f"[silence_cutter] 📝 Proyecto editable → {out.name}")
    except Exception as e:  # noqa: BLE001
        ctx.on_log(f"[silence_cutter] ⚠️ No se pudo escribir proyecto editable: {e}")


# ---------------------------------------------------------------------------
# FFprobe — duración + rotation
# ---------------------------------------------------------------------------
def _ffprobe_meta(input_path: str) -> tuple[float, int]:
    """Devuelve `(duration_s, rotation_deg)` del vídeo.

    Rotation se lee de `side_data[Display Matrix].rotation` que es el campo
    real de los .mov de iPhone. MoviePy lo ignora — sin esto, los iPhone
    vídeos salen horizontales tras concat.
    """
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_streams",
                "-of", "json",
                input_path,
            ],
            stderr=subprocess.STDOUT,
            timeout=30,
        )
        data = json.loads(out.decode("utf-8", errors="ignore"))
        stream = (data.get("streams") or [{}])[0]
        duration = float(stream.get("duration") or 0.0)
        # `rotation` puede estar en tags (legacy) o side_data_list (moderno).
        rotation = 0
        for sd in stream.get("side_data_list") or []:
            if sd.get("side_data_type") == "Display Matrix":
                rotation = int(sd.get("rotation") or 0)
                break
        if rotation == 0:
            tags = stream.get("tags") or {}
            rotation = int(tags.get("rotate") or 0)
        # Normalizar a [0, 360)
        rotation = rotation % 360
        if duration <= 0:
            # Fallback: leer el format duration
            duration = float((data.get("format") or {}).get("duration") or 0.0)
        return duration, rotation
    except Exception as e:
        print(f"[silence_cutter] ffprobe falló: {e}")
        # Fallback a moviepy
        from moviepy.editor import VideoFileClip
        with VideoFileClip(input_path) as vc:
            return float(vc.duration), 0


# ---------------------------------------------------------------------------
# Whisper transcribe (faster-whisper local, sin coste)
# ---------------------------------------------------------------------------
def _transcribe_subprocess_worker(
    q, audio_path: str, model_size: str, language: str, cpu_threads: int = 1,
) -> None:
    """Corre en un PROCESO hijo (spawn). Transcribe y devuelve las palabras
    por la Queue. Aislado del proceso api para que un deadlock de
    ctranslate2/OpenMP se pueda MATAR sin envenenar el worker principal.

    `cpu_threads` = hilos de cómputo de ctranslate2 (su propio pool). Multi-hilo
    es más rápido pero el deadlock de ctranslate2/int8 es flaky → el watchdog +
    escalado de hilos (en `_transcribe`) lo cubren. `OMP_NUM_THREADS=1` SIEMPRE
    para evitar el OpenMP anidado (la causa típica del cuelgue)."""
    try:
        import os as _os
        # Fijado ANTES de importar el motor (debe ir antes de faster-whisper).
        _os.environ["OMP_NUM_THREADS"] = "1"
        _os.environ["WHISPER_CPU_THREADS"] = str(max(1, int(cpu_threads)))
        from src.subtitles_only import transcribe_with_reference
        words = transcribe_with_reference(
            audio_path,
            reference_script=None,
            model_size=model_size,
            language=language or None,
            audio_type="speech",
            progress_callback=None,  # no cruza procesos; progreso coarse en el padre
        )
        q.put(("ok", words))
    except Exception as e:  # noqa: BLE001
        q.put(("err", f"{type(e).__name__}: {e}"))


def _transcribe(
    audio_path: str, *, model_size: str, language: str, on_progress,
    timeout_s: int = 1200, fallback_model: str = "small",
    primary_threads: int = 4,
) -> list[dict]:
    """Transcribe con Whisper, robusto a deadlocks de ctranslate2.

    El deadlock de ctranslate2/int8 en CPU es FLAKY (a veces cuelga, a veces
    no, con el MISMO audio) y más probable con MÁS hilos. Estrategia de
    ESCALADO de hilos (rápido→seguro→ligero):
      1) large-v3 a `primary_threads` hilos → RÁPIDO (multi-core).
      2) Si el watchdog lo mata por deadlock, reintenta large-v3 a 1 HILO →
         más lento pero casi nunca se cuelga; conserva la calidad del modelo.
      3) Si aún cuelga, cae a `fallback_model` (small) a 1 hilo → garantizado.
    El watchdog por inactividad de CPU detecta el cuelgue en ~2-3min (no espera
    el timeout entero), así que el escalado no cuesta 20min por intento.
    """
    primary_threads = max(1, int(primary_threads))
    # (modelo, hilos): 2 intentos de large antes del fallback. Si primary>1, el
    # 2º baja a 1 hilo (más seguro); si primary ya es 1, el 2º es un REINTENTO
    # (proceso fresco; el deadlock flaky suele pasar a la 2ª).
    plan: list[tuple[str, int]] = [(model_size, primary_threads), (model_size, 1)]
    last_err: Exception | None = None
    for i, (m, th) in enumerate(plan):
        try:
            if i > 0 and on_progress:
                on_progress(
                    0.1,
                    f"⚠️ Whisper {m} colgado — reintento a {th} hilo(s) (más seguro)…",
                )
            return _run_whisper_once(
                audio_path, model_size=m, language=language,
                on_progress=on_progress, timeout_s=timeout_s, cpu_threads=th,
            )
        except TimeoutError as e:
            last_err = e
            continue
    # Tras agotar large-v3 (multi y 1 hilo) → fallback a modelo ligero, 1 hilo.
    if fallback_model and fallback_model != model_size:
        if on_progress:
            on_progress(
                0.1,
                f"⚠️ Whisper {model_size} colgado — caigo a {fallback_model} (rápido)…",
            )
        return _run_whisper_once(
            audio_path, model_size=fallback_model, language=language,
            on_progress=on_progress, timeout_s=max(300, timeout_s // 2),
            cpu_threads=1,
        )
    raise last_err or TimeoutError("Whisper colgado sin fallback")


def _proc_cpu_ticks(pid: int) -> int | None:
    """utime+stime (jiffies) del proceso vía /proc/<pid>/stat. None si no se
    puede leer (no-Linux). Robusto a espacios en el nombre (comm entre paréntesis)."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as f:
            data = f.read()
        after = data[data.rfind(")") + 2:].split()
        # tras comm, el campo 3 (state) es after[0] → utime=campo14=after[11],
        # stime=campo15=after[12]
        return int(after[11]) + int(after[12])
    except Exception:  # noqa: BLE001
        return None


def _run_whisper_once(
    audio_path: str, *, model_size: str, language: str, on_progress,
    timeout_s: int = 1200, stall_s: int = 150, warmup_s: int = 60,
    cpu_threads: int = 1,
) -> list[dict]:
    """UNA pasada de Whisper en SUBPROCESO `spawn` con watchdog por CPU.

    El subproceso (sin heredar hilos/locks de la api) se puede MATAR → un
    deadlock de ctranslate2 nunca atasca la cola. El watchdog mira el TIEMPO
    DE CPU del hijo: si tras el warm-up deja de avanzar durante `stall_s`,
    es un deadlock (todos los hilos dormidos a ~0% CPU) → mata y lanza
    TimeoutError SIN esperar el `timeout_s` entero. Un trabajo SANO consume
    CPU sin parar, así que nunca se le mata por lento. Fallback a llamada
    directa solo si el entorno no soporta spawn.
    """
    import multiprocessing as mp
    import time

    def _direct() -> list[dict]:
        from src.subtitles_only import transcribe_with_reference
        return transcribe_with_reference(
            audio_path, reference_script=None, model_size=model_size,
            language=language or None, audio_type="speech",
            progress_callback=on_progress,
        )

    try:
        mpctx = mp.get_context("spawn")
        q = mpctx.Queue()
        p = mpctx.Process(
            target=_transcribe_subprocess_worker,
            args=(q, audio_path, model_size, language, cpu_threads),
            daemon=True,
        )
        p.start()
    except Exception:  # noqa: BLE001
        # El entorno no soporta spawn → llamada directa (comportamiento antiguo).
        return _direct()

    if on_progress:
        on_progress(0.1, "🎙️ Whisper transcribiendo…")

    t0 = time.monotonic()
    last_cpu = _proc_cpu_ticks(p.pid) or 0
    last_active = t0
    reason: str | None = None
    while True:
        p.join(5)
        if not p.is_alive():
            break
        now = time.monotonic()
        cpu = _proc_cpu_ticks(p.pid)
        if cpu is not None and cpu > last_cpu + 2:  # avanzó CPU → vivo y trabajando
            last_cpu = cpu
            last_active = now
        elapsed = now - t0
        if elapsed > warmup_s and (now - last_active) > stall_s:
            reason = f"estancado (sin CPU {stall_s}s — deadlock)"
            break
        if elapsed > timeout_s:
            reason = f"superó {timeout_s}s"
            break

    if p.is_alive():
        p.terminate()
        p.join(5)
        if p.is_alive():
            p.kill()
        raise TimeoutError(f"Whisper {model_size} {reason} — abortado")
    try:
        kind, payload = q.get_nowait() if not q.empty() else ("err", "sin resultado")
    except Exception:  # noqa: BLE001
        kind, payload = "err", "queue vacía"
    if kind == "ok":
        return payload
    # El subproceso terminó con error (no timeout) → fallback directo.
    return _direct()


# ---------------------------------------------------------------------------
# Auto-trim head/tail — barato, no requiere VAD ni IA
# ---------------------------------------------------------------------------
def _compute_head_tail_cuts(
    words: list[dict],
    video_duration: float,
) -> list[tuple[float, float]]:
    """Devuelve hasta 2 intervalos a cortar: silencio inicial antes de
    la primera palabra y silencio final tras la última. Cada uno solo
    se aplica si supera el threshold (no cortar pausas de <0.5s).
    """
    if not words or video_duration <= 0:
        return []
    cuts: list[tuple[float, float]] = []
    first_start = float(words[0]["start"])
    last_end = float(words[-1]["end"])
    if first_start >= _HEAD_TRIM_THRESHOLD_S:
        cuts.append((0.0, max(0.0, first_start - _HEAD_PAD_S)))
    if video_duration - last_end >= _TAIL_TRIM_THRESHOLD_S:
        cuts.append((min(video_duration, last_end + _TAIL_PAD_S), video_duration))
    return cuts


# ---------------------------------------------------------------------------
# Silero VAD
# ---------------------------------------------------------------------------
def _run_silero_vad(
    audio_path: str,
    *,
    min_silence_ms: int,
    padding_ms: int,
    log,
) -> list[tuple[float, float]]:
    """Tramos de VOZ en segundos (caller invierte → silencios).

    Cargamos el WAV manualmente con ffmpeg → numpy s16le → tensor 1D, en
    lugar de `silero_vad.read_audio` que delega en `torchaudio.load`. El
    backend de torchaudio en Windows con torch 2.5.1 no entiende los WAV
    que escribe MoviePy y revienta con `Couldn't find appropriate backend`.
    Esto rompía Silero silenciosamente — la detección de silencios sutiles
    (respiración, "ejem" con boca cerrada) caía a fallback Amplitud que
    no los detecta.
    """
    import numpy as np
    import torch
    from silero_vad import get_speech_timestamps, load_silero_vad

    log("[silence_cutter] Cargando modelo Silero VAD (ONNX)…")
    model = load_silero_vad(onnx=True)

    # Resamplear a 16kHz mono PCM s16le con ffmpeg → bytes raw → np.int16.
    # Esto evita TODA dependencia de torchaudio para el decode.
    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", audio_path,
            "-ac", "1", "-ar", "16000",
            "-f", "s16le", "-acodec", "pcm_s16le", "-",
        ],
        capture_output=True, timeout=600,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg decode falló para Silero: {proc.stderr.decode(errors='ignore')[:300]}"
        )
    audio_int16 = np.frombuffer(proc.stdout, dtype=np.int16)
    audio_f32 = audio_int16.astype(np.float32) / 32768.0
    wav = torch.from_numpy(audio_f32)

    speech = get_speech_timestamps(
        wav, model,
        sampling_rate=16000,
        min_silence_duration_ms=min_silence_ms,
        speech_pad_ms=padding_ms,
        return_seconds=True,
    )
    return [(float(s["start"]), float(s["end"])) for s in speech]


# ---------------------------------------------------------------------------
# IA cleanup (OpenAI GPT-4o)
# ---------------------------------------------------------------------------
_NGRAM_NORMALIZE_RE = re.compile(r"[^\w]+")


def _normalize_word_for_match(w: str) -> str:
    """Normaliza para comparación de n-gramas: lowercase + sin puntuación."""
    return _NGRAM_NORMALIZE_RE.sub("", (w or "").lower())


def _detect_repeated_ngrams(
    words: list[dict],
    *,
    min_n: int = 2,
    max_n: int = 6,
    max_gap_between_grams_s: float = 0.6,
) -> list[dict]:
    """Detecta n-gramas consecutivos repetidos en el transcript.

    Ejemplo: "esto costaba doce esto costaba doce euros" → n-grama
    "esto costaba doce" aparece duplicado en [0-2] y [3-5]. Marca como
    cut el primer attempt.

    DETERMINÍSTICO — no depende del LLM. Cubre el caso típico "speaker
    se equivocó y volvió a decir la frase" que GPT-4o a veces ignora
    por non-determinismo.

    Args:
        min_n / max_n: tamaño del n-grama a buscar (palabras).
        max_gap_between_grams_s: si entre la primera ocurrencia y la
            segunda hay más de X segundos de gap, NO se considera
            repetición (porque probablemente es referencia legítima
            de la misma palabra más adelante en la conversación).
    """
    if len(words) < 2 * min_n:
        return []

    normalized = [_normalize_word_for_match(w.get("word", "")) for w in words]
    cuts: list[dict] = []
    used: set[int] = set()

    # Más grande primero — preferimos detectar "esto costaba doce" que
    # solo "costaba doce".
    for n in range(max_n, min_n - 1, -1):
        i = 0
        while i <= len(words) - 2 * n:
            if any(j in used for j in range(i, i + 2 * n)):
                i += 1
                continue
            gram_a = normalized[i : i + n]
            gram_b = normalized[i + n : i + 2 * n]
            if not all(g for g in gram_a):  # n-grama con palabra vacía → skip
                i += 1
                continue
            if gram_a != gram_b:
                i += 1
                continue
            # Verifica que el gap entre ambos n-gramas no sea demasiado
            # grande — si son frases distintas separadas por mucho tiempo,
            # no es una repetición sino una mención legítima.
            t_a_end = float(words[i + n - 1]["end"])
            t_b_start = float(words[i + n]["start"])
            if t_b_start - t_a_end > max_gap_between_grams_s:
                i += 1
                continue
            cuts.append({
                "start_word_idx": i,
                "end_word_idx": i + n - 1,
                "kind": "exact_ngram_repetition",
                "first_attempt": " ".join(words[j]["word"] for j in range(i, i + n)),
                "kept_version": " ".join(
                    words[j]["word"] for j in range(i + n, i + 2 * n)
                ),
                "reason": f"N-grama de {n} palabras repetido consecutivamente",
                "n": n,
            })
            for j in range(i, i + 2 * n):
                used.add(j)
            i += n  # avanzar el cursor más allá del par para no detectar overlaps
    return sorted(cuts, key=lambda c: c["start_word_idx"])


def _build_false_starts_payload(words: list[dict], language: str) -> dict:
    """Payload común para pass 2 (OpenAI/Gemini) — separado para reutilizar."""
    transcript_text = " ".join(str(w.get("word", "")) for w in words)
    return {
        "language": language,
        "total_words": len(words),
        "transcript_text": transcript_text,
        "words": [
            {"idx": i, "word": w["word"],
             "start": round(float(w["start"]), 3),
             "end": round(float(w["end"]), 3)}
            for i, w in enumerate(words)
        ],
    }


def _parse_false_starts_cuts(
    result: Any, words: list[dict], log, *, provider: str,
) -> list[tuple[float, float, dict]]:
    """Parsea el JSON de la pasada 2 y devuelve los cuts como tuplas
    `(t_start, t_end, raw_cut_dict)`. `provider` solo se usa para log.
    """
    if not isinstance(result, dict):
        return []
    cuts_raw = result.get("cuts", []) or []
    if result.get("summary"):
        log(f"[silence_cutter] {provider} pass2: {result['summary']}")
    intervals: list[tuple[float, float, dict]] = []
    for cut in cuts_raw:
        try:
            i0 = int(cut.get("start_word_idx"))
            i1 = int(cut.get("end_word_idx"))
        except (TypeError, ValueError):
            continue
        if not (0 <= i0 <= i1 < len(words)):
            continue
        t0 = float(words[i0]["start"])
        t1 = float(words[i1]["end"])
        if t1 - t0 > 0.05:
            intervals.append((t0, t1, cut))
            kept = cut.get("kept_version") or ""
            first = cut.get("first_attempt") or ""
            kind = cut.get("kind") or "?"
            log(
                f"[silence_cutter]   ✂ {provider} {kind} [{i0}-{i1}] "
                f"'{first}' → mantengo '{kept}'"
            )
    return intervals


# Modelo + seed de la limpieza holística. gpt-5.4 = el más nuevo que acepta
# temperature=0 (modelo estándar, NO razonador) → determinista de verdad:
# mismo vídeo = mismo corte SIEMPRE (estable y afinable). Verificado en server.
_HOLISTIC_MODEL = "gpt-5.4"
_HOLISTIC_SEED = 7


def _holistic_keep_idxset(
    words: list[dict], *, language: str, model: str, log, label: str,
) -> set[int] | None:
    """UNA pasada de Gemini sobre `words`: devuelve el CONJUNTO de índices
    (0..len-1) a CONSERVAR, o None si falla / resultado inválido.

    El modelo ve la transcripción entera y devuelve `keep_spans` (tramos a
    conservar). Aquí solo parseamos/validamos → set de índices. El caller
    decide guardas y conversión a tiempo.
    """
    n = len(words)
    if n < 4:
        return set(range(n))
    from src.editor_auto.api import openai_client, gemini_client
    prompt_path = (
        Path(__file__).resolve().parent.parent
        / "prompts" / "silence_cutter_clean_script.md"
    )
    system_prompt = prompt_path.read_text(encoding="utf-8")
    payload = _build_false_starts_payload(words, language)
    # DETERMINISTA: GPT-4o + `seed` fijo + temp 0 → mismo input = mismo
    # resultado SIEMPRE (estable y AFINABLE). Gemini 2.5 Pro es "thinking" →
    # varía aunque temp=0, por eso solo se usa como fallback si no hay OpenAI.
    if openai_client.is_configured():
        result = openai_client.analyze_transcript_json(
            system_prompt=system_prompt, user_payload=payload,
            model=_HOLISTIC_MODEL, temperature=0.0, seed=_HOLISTIC_SEED,
        )
    elif gemini_client.is_configured():
        result = gemini_client.analyze_transcript_json(
            system_prompt=system_prompt, user_payload=payload,
            model=model, temperature=0.0,
        )
    else:
        return None
    raw_spans = (result or {}).get("keep_spans") or []
    keep: set[int] = set()
    for sp in raw_spans:
        try:
            a, b = int(sp[0]), int(sp[1])
        except (TypeError, ValueError, IndexError):
            continue
        a = max(0, min(a, n - 1)); b = max(0, min(b, n - 1))
        for i in range(a, b + 1):
            keep.add(i)
    if not keep:
        return None
    log(
        f"[silence_cutter]   ↳ {label}: conserva {len(keep)}/{n} palabras "
        f"({(result or {}).get('removed_summary') or ''})"[:160]
    )
    return keep


def _ai_holistic_clean_removes(
    *,
    words: list[dict],
    language: str,
    model: str,
    log,
    double_check: bool = True,
) -> tuple[list[tuple[float, float]], dict]:
    """Limpieza HOLÍSTICA del guion con Gemini, con DOBLE REVISIÓN.

    En vez de pegar cortes parciales (que oscilaban entre over-cut y dejar
    repeticiones por la ambigüedad de los rangos), Gemini ve la transcripción
    ENTERA y devuelve qué CONSERVAR. Como un editor humano:
      · Pasada 1: limpia el guion (una instancia de cada repetición/CTA/precio,
        sin falsos inicios, frases enteras).
      · Pasada 2 (revisión): re-revisa SOLO lo que sobrevivió → caza lo que la
        1ª se dejó (los LLM varían entre ejecuciones). Resultado final = lo que
        AMBAS conservan.

    Devuelve (remove_intervals_tiempo, diag). Si falla o intenta borrar >70%
    (alucinación), devuelve ([], diag) → el caller usa el pipeline antiguo.
    """
    diag: dict[str, Any] = {"model": model, "double_check": double_check}
    n = len(words)
    if n < 4:
        diag["skipped"] = "pocas palabras"
        return [], diag
    try:
        keep1 = _holistic_keep_idxset(
            words, language=language, model=model, log=log, label="revisión 1",
        )
        if keep1 is None:
            diag["rejected"] = "pasada 1 sin resultado → fallback"
            return [], diag
        final_keep = keep1
        diag["kept_pass1"] = len(keep1)
        if double_check and len(keep1) >= 4:
            # 2ª revisión SOLO sobre las palabras supervivientes.
            sub_idx = sorted(keep1)
            sub_words = [words[i] for i in sub_idx]
            try:
                keep2 = _holistic_keep_idxset(
                    sub_words, language=language, model=model, log=log,
                    label="revisión 2",
                )
            except Exception as e:  # noqa: BLE001
                keep2 = None
                log(f"[silence_cutter]   ↳ revisión 2 falló ({e}); uso solo la 1ª")
            if keep2 is not None:
                # keep2 son índices en sub_words → mapear a índices originales
                final_keep = {sub_idx[j] for j in keep2 if 0 <= j < len(sub_idx)}
                diag["kept_pass2"] = len(final_keep)

        kept_words = len(final_keep)
        diag["kept_words"] = kept_words
        diag["total_words"] = n
        if kept_words < n * 0.30:
            diag["rejected"] = f"keep={kept_words}/{n} (<30%) → fallback"
            return [], diag

        # Complemento = tramos a QUITAR (índices contiguos NO conservados).
        intervals: list[tuple[float, float]] = []
        i = 0
        while i < n:
            if i in final_keep:
                i += 1
                continue
            j = i
            while j < n and j not in final_keep:
                j += 1
            # quitar [i, j-1]
            try:
                t0 = float(words[i]["start"]); t1 = float(words[j - 1]["end"])
                if t1 - t0 > 0.05:
                    intervals.append((t0, t1))
            except (KeyError, IndexError, ValueError, TypeError):
                pass
            i = j
        diag["n_remove_intervals"] = len(intervals)
        log(
            f"[silence_cutter] 🧠 Limpieza holística (doble revisión): conserva "
            f"{kept_words}/{n} palabras · {len(intervals)} quitas de contenido"
        )
        return intervals, diag
    except Exception as e:  # noqa: BLE001
        diag["error"] = f"{type(e).__name__}: {e}"
        log(f"[silence_cutter] ⚠️ Limpieza holística falló: {e} → fallback")
        return [], diag


def _ai_false_starts_openai(
    *, words: list[dict], language: str, model: str, log,
) -> tuple[list[tuple[float, float, dict]], dict | None]:
    """Pasada 2 con OpenAI GPT-4o."""
    from src.editor_auto.api.openai_client import analyze_transcript_json

    prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "silence_cutter_false_starts.md"
    system_prompt = prompt_path.read_text(encoding="utf-8")
    payload = _build_false_starts_payload(words, language)
    result = analyze_transcript_json(
        system_prompt=system_prompt,
        user_payload=payload,
        model=model,
        temperature=0.0,
    )
    intervals = _parse_false_starts_cuts(
        result, words, log, provider="OpenAI",
    )
    return intervals, (result if isinstance(result, dict) else None)


def _ai_false_starts_gemini(
    *, words: list[dict], language: str, model: str, log,
) -> tuple[list[tuple[float, float, dict]], dict | None]:
    """Pasada 2 con Gemini 2.5 Pro — segunda voz para consenso. Si GPT-4o
    falla (devuelve 'Clean transcript' por non-determinismo), Gemini suele
    detectar las repeticiones que el otro modelo se traga.
    """
    from src.editor_auto.api.gemini_client import analyze_transcript_json

    prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "silence_cutter_false_starts.md"
    system_prompt = prompt_path.read_text(encoding="utf-8")
    payload = _build_false_starts_payload(words, language)
    result = analyze_transcript_json(
        system_prompt=system_prompt,
        user_payload=payload,
        model=model,
        temperature=0.0,
    )
    intervals = _parse_false_starts_cuts(
        result, words, log, provider="Gemini",
    )
    return intervals, (result if isinstance(result, dict) else None)


def _ai_false_starts_consensus(
    *,
    words: list[dict],
    language: str,
    openai_model: str = "gpt-4o",
    gemini_model: str = "gemini-2.5-pro",
    openai_enabled: bool = False,
    gemini_enabled: bool = True,
    log,
) -> tuple[list[tuple[float, float]], dict]:
    """Pasada 2 con modelos toggleables independientes (OpenAI / Gemini).

    Si los dos están activos hace CONSENSO (unión deduplicada). Si solo
    uno está activo, devuelve sus cuts directamente. Si ninguno → vacío.

    Estrategias (configurables vía toggles):
      - openai_enabled=False, gemini_enabled=True (DEFAULT, ~$0.003 extra):
        Gemini Pro como pass2 solo. Más agresivo en español, no-determinismo
        mitigado por la heurística n-gram que cubre literales.
      - openai_enabled=True, gemini_enabled=True (consenso, ~$0.015 extra):
        máxima fiabilidad — 2 proveedores independientes en pass2.
      - openai_enabled=True, gemini_enabled=False (~$0.012 extra):
        retro-compatibilidad con setup antiguo.
    """
    diag: dict[str, Any] = {
        "openai": {"model": openai_model, "enabled": openai_enabled},
        "gemini": {"model": gemini_model, "enabled": gemini_enabled},
    }

    openai_cuts: list[tuple[float, float, dict]] = []
    if openai_enabled:
        try:
            openai_cuts, openai_raw = _ai_false_starts_openai(
                words=words, language=language, model=openai_model, log=log,
            )
            diag["openai"]["summary"] = (openai_raw or {}).get("summary")
            diag["openai"]["raw_cuts"] = (openai_raw or {}).get("cuts", [])
            diag["openai"]["n_cuts"] = len(openai_cuts)
        except Exception as e:
            diag["openai"]["error"] = f"{type(e).__name__}: {e}"
            log(f"[silence_cutter] ⚠️ OpenAI pass2 falló: {e}")

    gemini_cuts: list[tuple[float, float, dict]] = []
    if gemini_enabled:
        try:
            from src.editor_auto.api.gemini_client import is_configured
            if not is_configured():
                diag["gemini"]["enabled"] = False
                diag["gemini"]["skipped"] = "no API key"
                log("[silence_cutter] ⚠️ Gemini sin API key, saltando pass2 Gemini")
            else:
                gemini_cuts, gemini_raw = _ai_false_starts_gemini(
                    words=words, language=language, model=gemini_model, log=log,
                )
                diag["gemini"]["summary"] = (gemini_raw or {}).get("summary")
                diag["gemini"]["raw_cuts"] = (gemini_raw or {}).get("cuts", [])
                diag["gemini"]["n_cuts"] = len(gemini_cuts)
        except Exception as e:
            diag["gemini"]["error"] = f"{type(e).__name__}: {e}"
            log(f"[silence_cutter] ⚠️ Gemini pass2 falló: {e}")

    # Unión deduplicada — clave (start_word_idx, end_word_idx)
    seen: dict[tuple[int, int], dict] = {}
    for cuts, source in [(openai_cuts, "openai"), (gemini_cuts, "gemini")]:
        for t0, t1, raw in cuts:
            i0 = int(raw.get("start_word_idx", -999))
            i1 = int(raw.get("end_word_idx", -999))
            key = (i0, i1)
            if key in seen:
                # Marcamos como detectado por AMBOS modelos (consenso fuerte)
                seen[key]["detected_by"] = "both"
            else:
                seen[key] = {"t_start": t0, "t_end": t1, "raw": raw,
                             "detected_by": source}

    # Logear consenso
    only_openai = sum(1 for v in seen.values() if v["detected_by"] == "openai")
    only_gemini = sum(1 for v in seen.values() if v["detected_by"] == "gemini")
    both = sum(1 for v in seen.values() if v["detected_by"] == "both")
    log(
        f"[silence_cutter] Consenso pass2: {both} en ambos · "
        f"{only_openai} solo OpenAI · {only_gemini} solo Gemini = "
        f"{len(seen)} cuts totales"
    )
    diag["consensus"] = {
        "both": both,
        "only_openai": only_openai,
        "only_gemini": only_gemini,
        "total_unique": len(seen),
    }

    intervals = [(v["t_start"], v["t_end"]) for v in seen.values()]
    return intervals, diag


def _ai_cleanup_cuts_with_raw(
    *,
    words: list[dict],
    video_duration: float,
    language: str,
    model: str,
    log,
) -> tuple[list[tuple[float, float]], dict | None]:
    """Como `_ai_cleanup_cuts` pero devuelve también el JSON crudo del LLM
    para inspección en el diagnóstico."""
    from src.editor_auto.api.openai_client import analyze_transcript_json

    prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "silence_cutter_analyst.md"
    system_prompt = prompt_path.read_text(encoding="utf-8")

    # `gap_to_next_s` = silencio en segundos entre el final de esta palabra
    # y el inicio de la siguiente. Hace OBVIOS los gaps largos para el LLM,
    # que antes los pasaba por alto porque tenía que calcular él la resta
    # de timestamps mentalmente.
    enriched_words = []
    for i, w in enumerate(words):
        entry = {
            "idx": i,
            "word": w["word"],
            "start": round(float(w["start"]), 3),
            "end": round(float(w["end"]), 3),
        }
        if i < len(words) - 1:
            gap = float(words[i + 1]["start"]) - float(w["end"])
            entry["gap_to_next_s"] = round(max(0.0, gap), 3)
        enriched_words.append(entry)

    # También enviamos un resumen pre-calculado de los gaps >0.8s — la
    # forma más eficaz de que el LLM no se olvide de ninguno.
    long_gaps = []
    for i in range(len(words) - 1):
        gap = float(words[i + 1]["start"]) - float(words[i]["end"])
        if gap >= 0.8:
            long_gaps.append({
                "after_word_idx": i,
                "before_word_idx": i + 1,
                "t_start": round(float(words[i]["end"]), 3),
                "t_end": round(float(words[i + 1]["start"]), 3),
                "gap_s": round(gap, 3),
            })

    payload = {
        "language": language,
        "total_words": len(words),
        "total_duration_s": round(video_duration, 3),
        "long_gaps_precomputed": long_gaps,
        "words": enriched_words,
    }
    result = analyze_transcript_json(
        system_prompt=system_prompt,
        user_payload=payload,
        model=model,
        temperature=0.2,
    )
    cuts_raw = result.get("cuts", []) if isinstance(result, dict) else []
    if isinstance(result, dict) and result.get("summary"):
        log(f"[silence_cutter] IA summary: {result['summary']}")
    log(
        f"[silence_cutter] IA recibió {len(long_gaps)} gaps pre-calculados ≥0.8s"
    )
    intervals = _parse_ai_cuts(cuts_raw, words=words, video_duration=video_duration)
    return intervals, (result if isinstance(result, dict) else None)


def _count_by_reason(cuts_raw: list[dict]) -> dict[str, int]:
    """Agrupa los cuts del LLM por su campo `reason`."""
    return _count_by_field(cuts_raw, field="reason")


def _count_by_field(cuts_raw: list[dict], *, field: str) -> dict[str, int]:
    """Agrupa cuts por un campo arbitrario (`reason` / `kind` / ...).

    Usado en diagnóstico para `ai.cuts_by_reason` y
    `ai_pass2.cuts_by_kind` sin duplicar lógica.
    """
    out: dict[str, int] = {}
    for c in cuts_raw or []:
        v = (c.get(field) if isinstance(c, dict) else None) or "unknown"
        out[v] = out.get(v, 0) + 1
    return out


def _count_by_source(cuts_with_source: list[tuple[float, float, str]]) -> dict[str, int]:
    """Agrupa los cuts finales por fuente (auto_trim / acoustic / ai)."""
    out: dict[str, int] = {}
    for _, _, src in cuts_with_source:
        out[src] = out.get(src, 0) + 1
    return out


# ---------------------------------------------------------------------------
# Amplitude-based silence detect (ffmpeg silencedetect)
# ---------------------------------------------------------------------------
def _protect_word_boundaries(
    cuts: list[tuple[float, float]],
    words: list[dict],
    guard_s: float,
) -> list[tuple[float, float]]:
    """Recorta cada cut para que NUNCA clipe una palabra: el cut no empieza
    hasta `guard_s` después del fin de la palabra previa, ni acaba hasta
    `guard_s` antes del inicio de la siguiente. Aplica a la lista YA fusionada
    de todas las fuentes de corte (IA, gap, acústica, silero…), así ninguna
    puede comerse el final/inicio de una palabra por timestamps imprecisos
    de Whisper. Cuts que quedan vacíos tras el guard se descartan."""
    if not cuts or not words or guard_s <= 0:
        return cuts
    ends = sorted(float(w["end"]) for w in words if "end" in w)
    starts = sorted(float(w["start"]) for w in words if "start" in w)
    out: list[tuple[float, float]] = []
    for s, e in cuts:
        # CLAVE: la palabra PREVIA es la que termina antes del INICIO del cut
        # (end <= s), y la SIGUIENTE la que empieza después del FINAL del cut
        # (start >= e). Usar <=e / >=s cogía una palabra de DENTRO del gap y
        # encogía/eliminaba cortes legítimos (bug que dejaba silencios).
        prev_end = max((x for x in ends if x <= s), default=None)
        next_start = min((x for x in starts if x >= e), default=None)
        ns = s if prev_end is None else max(s, prev_end + guard_s)
        ne = e if next_start is None else min(e, next_start - guard_s)
        if ne - ns > 0.05:
            out.append((ns, ne))
    return out


def _clamp_cuts_to_silence_edges(
    cuts: list[tuple[float, float]],
    silences: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Ajusta los BORDES de cada corte al silencio REAL medido por amplitud.

    Los timestamps de Whisper marcan el fin de palabra hasta ~400ms PRONTO
    (ej. 'resultado' que Whisper cierra en 34.44 pero el audio suena hasta
    34.88). Por eso el word-guard basado en Whisper no basta. La amplitud
    (RMS por debajo de umbral) sí dice dónde HAY audio de verdad. Para cada
    corte que solapa una zona de silencio real, lo recortamos para que NO
    empiece antes de que el audio sea silencio ni acabe después. Si la
    amplitud no detectó silencio en esa zona, dejamos el corte como estaba
    (ya pasó por el word-guard)."""
    if not cuts or not silences:
        return cuts
    # Recorte MÁXIMO permitido por borde. Solo ajustamos el borde si es un
    # recorte PEQUEÑO (proteger la cola/inicio de una palabra por imprecisión
    # de Whisper, ~<500ms). Si la amplitud diría que hay que encoger MUCHO,
    # es que está infra-detectando (audio bajito / ruido de sala por encima
    # del umbral) → NO nos fiamos y mantenemos el corte completo, para no
    # dejar silencios grandes sin cortar.
    _MAX_EDGE_SHRINK_S = 0.5
    sil = _merge_intervals(list(silences))
    out: list[tuple[float, float]] = []
    for s, e in cuts:
        overlapping = [(a, b) for (a, b) in sil if b > s and a < e]
        if overlapping:
            sil_lo = min(a for a, _ in overlapping)
            sil_hi = max(b for _, b in overlapping)
            ns = s
            if sil_lo > s and (sil_lo - s) <= _MAX_EDGE_SHRINK_S:
                ns = sil_lo   # empezar donde el audio se calla de verdad
            ne = e
            if sil_hi < e and (e - sil_hi) <= _MAX_EDGE_SHRINK_S:
                ne = sil_hi   # acabar donde el audio vuelve de verdad
            if ne - ns > 0.05:
                out.append((ns, ne))
        else:
            out.append((s, e))
    return out


def _compute_inter_word_gap_cuts(
    words: list[dict],
    *,
    threshold_s: float,
    keep_ms: int,
) -> list[dict]:
    """Cortes determinísticos basados en los huecos entre palabras Whisper.

    Para cada gap `> threshold_s` entre el final de una palabra y el inicio
    de la siguiente, genera un cut que conserva `keep_ms` de pausa
    natural (no pegamos las dos palabras sin aire). Esta capa NO depende
    de IA: los gaps son hechos objetivos del transcript.

    Returns: lista de dicts con `t_start`, `t_end`, `gap_s`,
    `after_word_idx`, `before_word_idx` para diagnóstico.
    """
    if not words or threshold_s <= 0:
        return []
    keep_s = max(0.0, keep_ms / 1000.0)
    cuts: list[dict] = []
    for i in range(len(words) - 1):
        prev_end = float(words[i]["end"])
        next_start = float(words[i + 1]["start"])
        gap = next_start - prev_end
        if gap < threshold_s:
            continue
        # Repartimos `keep_s` mitad y mitad (algo de aire al final de la
        # frase anterior + algo de aire antes de la nueva). El cut elimina
        # la "tripa" del gap.
        half = keep_s / 2.0
        cut_start = prev_end + half
        cut_end = next_start - half
        if cut_end - cut_start <= 0.05:
            continue
        cuts.append({
            "t_start": round(cut_start, 3),
            "t_end": round(cut_end, 3),
            "gap_s": round(gap, 3),
            "after_word_idx": i,
            "before_word_idx": i + 1,
            "after_word": words[i].get("word"),
            "before_word": words[i + 1].get("word"),
        })
    return cuts


def _map_output_to_input(
    t_output: float,
    keep_intervals: list[tuple[float, float]],
) -> float | None:
    """Convierte un timestamp del MP4 final al timestamp del input original.

    El output es la concatenación de `keep_intervals[0]`, `keep_intervals[1]`,
    etc. Esto reconstruye el offset del input para un instante del output —
    útil para que el audit muestre qué zona del input corresponde a un
    silencio remanente.
    """
    cursor = 0.0
    for start, end in keep_intervals:
        seg_dur = end - start
        if cursor + seg_dur >= t_output:
            return start + (t_output - cursor)
        cursor += seg_dur
    return None


def _nearest_words(
    input_time: float,
    words: list[dict],
) -> dict:
    """Devuelve la palabra anterior + siguiente al `input_time`. Sirve para
    contextualizar en logs por qué un silencio quedó (ej. entre qué frases)."""
    if not words:
        return {}
    before: dict | None = None
    after: dict | None = None
    for i, w in enumerate(words):
        if float(w["end"]) <= input_time:
            before = {"idx": i, "word": w.get("word"),
                      "start": float(w["start"]), "end": float(w["end"])}
        elif float(w["start"]) >= input_time and after is None:
            after = {"idx": i, "word": w.get("word"),
                     "start": float(w["start"]), "end": float(w["end"])}
            break
    return {
        "before_word": before,
        "after_word": after,
        "gap_in_input_s": (
            round(after["start"] - before["end"], 3)
            if before and after else None
        ),
    }


def _post_render_audit(
    output_path: str,
    *,
    long_silence_threshold_s: float = 0.8,
    noise_db: float = -25.0,
    keep_intervals: list[tuple[float, float]] | None = None,
    words: list[dict] | None = None,
    stretched_spans: list[tuple[float, float]] | None = None,
) -> dict:
    """Re-analiza el MP4 final y puntúa la CALIDAD REAL del vídeo (0-100).

    Si se pasan `keep_intervals` y `words`, cada silencio remanente se
    enriquece con su posición en el INPUT y las palabras vecinas en el
    transcript — así sabemos exactamente entre qué frases falló.

    Quality score (0-100) — pondera FALLOS REALES que se notan en el vídeo
    por encima de silencios imperfectos:
      - Transcripción FALLIDA (0 palabras con vídeo largo) → cap 30 + reencolar:
        sin transcripción el corte es solo-acústico y el score es ciego.
      - Palabra suelta (clip diminuto que es solo un relleno tipo 'y'/'la')
        → −12 c/u: artefacto audible/visible.
      - Relleno estirado superviviente (un 'la'/risa de 2s que NO se cortó)
        → −12 c/u.
      - Silencio interno sin cortar exacto → −3 c/u (menor; "no pasa nada").
    `needs_requeue` = True si la transcripción falló o el score < 90 → aviso
    al operador de que hubo un fallo REAL y conviene reencolar.
    """
    audit: dict[str, Any] = {
        "long_silence_threshold_s": long_silence_threshold_s,
        "noise_db": noise_db,
    }
    try:
        # Extraer audio del output a WAV temporal para silencedetect
        import tempfile
        tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        try:
            extract = subprocess.run(
                [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", output_path,
                    "-ac", "1", "-ar", "16000",
                    "-vn", tmp_wav,
                ],
                capture_output=True, timeout=120,
            )
            if extract.returncode != 0:
                audit["error"] = "ffmpeg extract failed"
                return audit
            remaining = _run_silencedetect(
                tmp_wav,
                noise_db=noise_db,
                min_duration_s=long_silence_threshold_s,
            )
        finally:
            try:
                os.remove(tmp_wav)
            except OSError:
                pass

        # Output duration vía ffprobe
        try:
            dur_out = subprocess.check_output(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=nw=1:nk=1", output_path],
                timeout=30,
            )
            output_duration = float(dur_out.decode().strip() or 0.0)
        except Exception:
            output_duration = 0.0

        # Filtrar silencios al inicio/final que podrían ser por encoding
        # (algunos codecs añaden 50-100ms de silencio al arranque/cierre).
        # Solo contamos como problema los silencios netamente internos.
        internal_silences = [
            (s, e) for (s, e) in remaining
            if s > 0.5 and (output_duration == 0 or e < output_duration - 0.5)
        ]
        n_internal = len(internal_silences)

        # --- Señales de FALLO REAL (lo que se nota en el vídeo) ---------------
        n_words = len(words or [])
        # Transcripción fallida: 0 palabras con vídeo de duración real → el
        # corte fue solo-acústico (ciego a palabras) → el score sería engañoso.
        degraded = n_words == 0 and output_duration > 12.0
        # Palabras sueltas: clips diminutos que son solo relleno (un 'y'/'la'
        # colgado entre dos cortes) — artefacto audible.
        loose_words = _detect_loose_words(words or [], keep_intervals or [])
        # Rellenos estirados que NO se cortaron (siguen audibles en el corte).
        surviving_stretched = _surviving_stretched_spans(
            stretched_spans or [], keep_intervals or [],
        )

        n_loose = len(loose_words)
        n_surv = len(surviving_stretched)
        # Penalización del estirado superviviente PROPORCIONAL a cuánto sobrevive:
        # un residuo corto (<1s, apenas perceptible) penaliza poco (−6); uno
        # largo (≥1s, claramente audible) penaliza fuerte (−12). Refleja la
        # severidad real (un "aaa" de 0.6s no es un fallo gordo).
        surv_penalty = sum(
            12 if float(s.get("overlap_s", 0)) >= 1.0 else 6
            for s in surviving_stretched
        )
        score = 100
        score -= 12 * n_loose
        score -= surv_penalty
        score -= 3 * n_internal          # silencios = menor
        score = max(0, min(100, score))
        if degraded:
            score = min(score, 30)
        needs_requeue = bool(degraded or score < 90)

        # Enriquecer cada silencio remanente con su posición en el INPUT
        # y las palabras vecinas — así el operador ve EXACTAMENTE entre qué
        # frases del transcript quedó el silencio. Sin esto, los timestamps
        # del output no informan de nada porque el vídeo está concatenado.
        enriched: list[dict] = []
        for s, e in internal_silences[:15]:
            entry: dict[str, Any] = {
                "output_start": round(s, 3),
                "output_end": round(e, 3),
                "duration_s": round(e - s, 3),
            }
            if keep_intervals:
                input_start = _map_output_to_input(s, keep_intervals)
                input_end = _map_output_to_input(e, keep_intervals)
                if input_start is not None and input_end is not None:
                    entry["input_start"] = round(input_start, 3)
                    entry["input_end"] = round(input_end, 3)
                    if words:
                        # Contexto: palabras antes y después del silencio
                        # en el input. La "before" tiene su end < input_start,
                        # la "after" tiene su start > input_end.
                        mid = (input_start + input_end) / 2.0
                        entry["context"] = _nearest_words(mid, words)
            enriched.append(entry)

        audit.update({
            "output_duration_s": round(output_duration, 3),
            "n_words": n_words,
            "transcription_ok": not degraded,
            "n_silences_remaining": len(remaining),
            "n_internal_silences": n_internal,
            "internal_silences_preview": enriched,
            "n_loose_words": n_loose,
            "loose_words_preview": loose_words[:10],
            "n_surviving_stretched": n_surv,
            "surviving_stretched_preview": surviving_stretched[:10],
            "quality_score": score,
            "needs_requeue": needs_requeue,
            "verdict": _verdict_for_score(score, degraded=degraded),
        })
    except Exception as e:
        audit["error"] = f"{type(e).__name__}: {e}"
    return audit


def _verdict_for_score(score: int, *, degraded: bool = False) -> str:
    if degraded:
        return "FALLO — sin transcripción (corte ciego). REENCOLAR"
    if score >= 90:
        return "EXCELENTE — sin fallos reales detectados"
    if score >= 70:
        return "BIEN — algún detalle menor"
    if score >= 50:
        return "REGULAR — hay fallos visibles. Mejor REENCOLAR"
    return "MAL — varios fallos reales. REENCOLAR"


def _detect_loose_words(
    words: list[dict],
    keep_intervals: list[tuple[float, float]],
    *,
    max_seg_s: float = 0.85,
    pad_s: float = 0.08,
) -> list[dict]:
    """Detecta 'palabras sueltas': un clip diminuto que quedó en el corte
    final cuyo ÚNICO contenido es 1-2 rellenos cortos ('y', 'la', 'eh'...).

    Es el artefacto que más se nota: una palabra colgada entre dos cortes,
    sin frase alrededor. Un segmento normal (una frase) dura >0.85s y trae
    palabras de contenido → no dispara. Solo penaliza fragmentos-basura.
    """
    if not words or not keep_intervals:
        return []
    loose: list[dict] = []
    for s, e in keep_intervals:
        if (e - s) > max_seg_s:
            continue
        seg = [
            w for w in words
            if float(w.get("start", 0)) >= s - pad_s
            and float(w.get("end", 0)) <= e + pad_s
        ]
        if not seg or len(seg) > 2:
            continue
        toks = [
            re.sub(r"[^\wáéíóúñü]", "", str(w.get("word", "")).lower())
            for w in seg
        ]
        if all((t in _FILLER_TOKENS or len(t) <= 2) for t in toks if t):
            loose.append({
                "start": round(s, 2), "end": round(e, 2),
                "text": " ".join(t for t in toks if t) or "·",
            })
    return loose


def _surviving_stretched_spans(
    stretched_spans: list[tuple[float, float]],
    keep_intervals: list[tuple[float, float]],
    *,
    min_overlap_s: float = 0.4,
) -> list[dict]:
    """Rellenos estirados (un 'la'/risa de ~2s) que NO se cortaron: siguen
    solapando una zona conservada ≥ `min_overlap_s` → audibles en el corte."""
    if not stretched_spans or not keep_intervals:
        return []
    surv: list[dict] = []
    for a, b in stretched_spans:
        ov = sum(
            max(0.0, min(b, e) - max(a, s)) for s, e in keep_intervals
        )
        if ov >= min_overlap_s:
            surv.append({
                "start": round(a, 2), "end": round(b, 2),
                "dur": round(b - a, 2), "overlap_s": round(ov, 2),
            })
    return surv


def _measure_speech_rms_db(
    audio_path: str,
    words: list[dict],
    *,
    max_words_sampled: int = 20,
) -> float | None:
    """Mide el volumen RMS del audio en las ZONAS donde Whisper detectó
    palabras. Esto nos da el "volumen base de la voz" — la base para
    calibrar el threshold de silencio relativo al speaker.

    Devuelve dB o None si no se puede medir.
    """
    if not words:
        return None
    # Muestreamos N palabras distribuidas uniformemente para no procesar
    # cien rangos en vídeos largos.
    step = max(1, len(words) // max_words_sampled)
    sampled = words[::step][:max_words_sampled]
    selects = [
        f"between(t,{float(w['start']):.3f},{float(w['end']):.3f})"
        for w in sampled
    ]
    select_expr = "+".join(selects)
    # `astats=measure_overall=RMS_level:reset=1` mide RMS de TODO lo que
    # pasa por el filtro `aselect` — solo las zonas de voz seleccionadas.
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats",
        "-i", audio_path,
        "-af",
        f"aselect='{select_expr}',astats=metadata=1:reset=1,"
        f"ametadata=mode=print:key=lavfi.astats.Overall.RMS_level",
        "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, timeout=180, text=True,
            encoding="utf-8", errors="ignore",
        )
    except subprocess.TimeoutExpired:
        return None
    # Output llega por stderr en líneas tipo:
    #   lavfi.astats.Overall.RMS_level=-22.305614
    values: list[float] = []
    for line in (proc.stderr or "").splitlines() + (proc.stdout or "").splitlines():
        if "RMS_level=" in line:
            try:
                v = float(line.split("RMS_level=")[1].strip().split()[0])
                if v > -200:  # filtra -inf
                    values.append(v)
            except (IndexError, ValueError):
                continue
    if not values:
        return None
    # Mediana es robusta a outliers
    values.sort()
    return values[len(values) // 2]


def _measure_mean_volume_db(audio_path: str) -> float | None:
    """Mide la media RMS global de la pista con `volumedetect` (1 pasada).

    Es la referencia para calibrar el umbral de silencio adaptativo: las
    pausas a cortar quedan ~10dB por encima de la media en grabaciones de
    mala SNR. Devuelve dB o None si no se puede medir.
    """
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats",
        "-i", audio_path,
        "-ac", "1", "-ar", "16000",
        "-af", "volumedetect",
        "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, timeout=180, text=True,
            encoding="utf-8", errors="ignore",
        )
    except subprocess.TimeoutExpired:
        return None
    for line in (proc.stderr or "").splitlines() + (proc.stdout or "").splitlines():
        if "mean_volume:" in line:
            try:
                return float(line.split("mean_volume:")[1].strip().split()[0])
            except (IndexError, ValueError):
                return None
    return None


def _run_silencedetect(
    audio_path: str,
    *,
    noise_db: float,
    min_duration_s: float,
) -> list[tuple[float, float]]:
    """Ejecuta `ffmpeg -af silencedetect=...` y parsea los pares
    `silence_start` / `silence_end` del stderr.

    Detecta silencio físico real (audio por debajo de `noise_db` durante
    `min_duration_s`). Independiente de si es "voz" o ruido — perfecto para
    "ejem ejem con boca cerrada", respiraciones, o pauses sostenidas que
    Silero clasifica como voz por error.
    """
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats",
        "-i", audio_path,
        "-af", f"silencedetect=noise={noise_db}dB:d={min_duration_s}",
        "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, timeout=300, text=True,
            encoding="utf-8", errors="ignore",
        )
    except subprocess.TimeoutExpired:
        return []

    # silencedetect emite a stderr líneas tipo:
    #   [silencedetect @ ...] silence_start: 12.345
    #   [silencedetect @ ...] silence_end: 14.567 | silence_duration: 2.222
    intervals: list[tuple[float, float]] = []
    cur_start: float | None = None
    for line in (proc.stderr or "").splitlines():
        if "silence_start:" in line:
            try:
                cur_start = float(line.split("silence_start:")[1].strip().split()[0])
            except (IndexError, ValueError):
                cur_start = None
        elif "silence_end:" in line and cur_start is not None:
            try:
                end = float(line.split("silence_end:")[1].strip().split()[0])
            except (IndexError, ValueError):
                cur_start = None
                continue
            intervals.append((cur_start, end))
            cur_start = None
    return intervals


# ---------------------------------------------------------------------------
# Filtro: no cortar intervalos que contengan palabras de Whisper
# ---------------------------------------------------------------------------
def _filter_cuts_outside_words(
    cuts: list[tuple[float, float]],
    *,
    words: list[dict],
    pad_s: float = 0.08,
) -> list[tuple[float, float]]:
    """Versión legacy — descarta cuts que solapen con palabras. Sigue
    aquí por compatibilidad con los tests existentes; el flujo principal
    usa ahora `_trim_cuts_to_avoid_words` que es mucho menos destructivo.
    """
    if not words:
        return list(cuts)
    word_ranges = [
        (max(0.0, float(w["start"]) - pad_s), float(w["end"]) + pad_s)
        for w in words
    ]
    out: list[tuple[float, float]] = []
    for cs, ce in cuts:
        overlaps = any(ws < ce and we > cs for (ws, we) in word_ranges)
        if not overlaps:
            out.append((cs, ce))
    return out


def _filter_phantom_words(
    words: list[dict],
    silero_silence_intervals: list[tuple[float, float]],
    *,
    min_silence_for_phantom_s: float = 0.7,
    min_overlap_pct: float = 0.6,
) -> tuple[list[dict], list[dict]]:
    """Detecta palabras "fantasma" de Whisper: tokens que solapan con un
    silencio Silero ≥ `min_silence_for_phantom_s`.

    Una palabra es fantasma si CUALQUIERA:
      (a) Está completamente dentro de un silencio largo.
      (b) Su punto medio cae dentro + dura < 0.6s.
      (c) **>50% de su duración solapa con el silencio** (regla nueva —
          captura alucinaciones que Whisper extendió levemente fuera del
          rango Silero por imprecisión de bordes).

    Returns: `(clean_words, phantoms)`. Antes la regla solo cogía (a)+(b)
    y se nos escapaban palabras cuya "cola" tras la pronunciación caía
    fuera del silencio Silero — protegían los cuts y los silencios reales
    sobrevivían en el output.
    """
    if not silero_silence_intervals:
        return list(words), []
    long_silences = [
        (ss, se) for (ss, se) in silero_silence_intervals
        if (se - ss) >= min_silence_for_phantom_s
    ]
    if not long_silences:
        return list(words), []

    phantoms: list[dict] = []
    clean: list[dict] = []
    for w in words:
        ws = float(w["start"])
        we = float(w["end"])
        word_dur = we - ws
        word_mid = (ws + we) / 2.0
        is_phantom = False
        for ss, se in long_silences:
            # (a) Palabra totalmente dentro
            if ss <= ws and we <= se:
                is_phantom = True
                break
            # (b) Mid dentro + palabra corta
            if ss <= word_mid <= se and word_dur < 0.6:
                is_phantom = True
                break
            # (c) Overlap > min_overlap_pct de la duración de la palabra
            if word_dur > 0:
                overlap = max(0.0, min(we, se) - max(ws, ss))
                if overlap / word_dur >= min_overlap_pct:
                    is_phantom = True
                    break
        if is_phantom:
            phantoms.append(w)
        else:
            clean.append(w)
    return clean, phantoms


def _filter_words_trapped_between_silences(
    words: list[dict],
    silero_silence_intervals: list[tuple[float, float]],
    *,
    min_silence_s: float = 0.5,
    max_gap_between_silences_s: float = 1.2,
) -> tuple[list[dict], list[dict]]:
    """Palabras "atrapadas" entre dos silencios Silero cercanos (gap entre
    silencios < `max_gap_between_silences_s`) → casi seguro alucinaciones.

    Caso real: el operador oía "cua" entre "Android" y "esto costaba". Silero
    detectó silencios `[53.5, 55.1]` y `[55.9, 56.7]` (gap=0.8s). Whisper
    transcribió una palabra entre ellos (~55.4-55.7) que NO estaba dentro
    de ningún silencio individual → `_filter_phantom_words` la dejaba pasar.
    Esta función la detecta porque queda "encajonada" entre 2 silencios.

    Returns: `(clean_words, trapped)`.
    """
    if not silero_silence_intervals or len(silero_silence_intervals) < 2:
        return list(words), []
    sils = sorted(
        [(s, e) for s, e in silero_silence_intervals if (e - s) >= min_silence_s],
        key=lambda x: x[0],
    )
    # Construir pares (silence_i.end, silence_{i+1}.start) donde el gap entre
    # silencios es corto. Cualquier palabra dentro de ese gap es sospechosa.
    suspect_ranges: list[tuple[float, float]] = []
    for i in range(len(sils) - 1):
        gap_start = sils[i][1]
        gap_end = sils[i + 1][0]
        if gap_end - gap_start <= max_gap_between_silences_s:
            suspect_ranges.append((gap_start, gap_end))
    if not suspect_ranges:
        return list(words), []

    trapped: list[dict] = []
    clean: list[dict] = []
    for w in words:
        ws = float(w["start"])
        we = float(w["end"])
        is_trapped = False
        for gs, ge in suspect_ranges:
            # Palabra completamente dentro del gap entre 2 silencios
            if gs - 0.05 <= ws and we <= ge + 0.05:
                is_trapped = True
                break
        if is_trapped:
            trapped.append(w)
        else:
            clean.append(w)
    return clean, trapped


def _split_silero_cuts_by_confidence(
    silero_cuts: list[tuple[float, float]],
    *,
    high_confidence_threshold_s: float = 0.8,
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Separa cuts Silero en "alta confianza" (silencio largo, confiamos
    100%) vs "normal" (pasa por filtro de palabras).

    Silero VAD es muy fiable para silencios ≥0.8s — esos cuts se aplican
    SIN trim de palabras (porque Whisper a menudo alucina palabras en
    medio de silencios largos con ruido ambiente). Para cuts más cortos
    sí pasamos por el filtro de seguridad para no cortar voz por error.
    """
    high: list[tuple[float, float]] = []
    normal: list[tuple[float, float]] = []
    for s, e in silero_cuts:
        if (e - s) >= high_confidence_threshold_s:
            high.append((s, e))
        else:
            normal.append((s, e))
    return high, normal


_FILLER_TOKENS = {
    "la", "le", "lo", "el", "y", "o", "e", "a", "eh", "ah", "oh", "uh", "um",
    "mm", "mmm", "hmm", "ya", "ja", "je", "ji", "jo", "ju", "jaja", "jeje",
    "uy", "ay", "aja", "eeh", "aah", "ehh", "este", "esto", "pues",
}


def _detect_stretched_fillers(
    words: list[dict],
    *,
    hard_s: float = 1.8,
    soft_s: float = 1.0,
    soft_max_chars: int = 3,
) -> list[tuple[float, float, str, float]]:
    """Detecta 'rellenos estirados': una palabra que dura ANORMALMENTE mucho.

    Ninguna palabra real dura >1.5s; cuando Whisper marca un token corto
    ("la"/"y"/"eh"/risa) durante 1.5-2s+ es porque está etiquetando un sonido
    NO hablado (risa, "ehh", micro lejos, ruido). Cortarlas es determinista y
    seguro: una palabra normal (0.1-0.6s) jamás dispara.

    Returns: lista (start, end, token, dur).
    """
    out: list[tuple[float, float, str, float]] = []
    for w in words:
        try:
            s = float(w["start"]); e = float(w["end"])
        except (KeyError, ValueError, TypeError):
            continue
        dur = e - s
        if dur < soft_s:
            continue
        tok = re.sub(r"[^\wáéíóúñü]", "", str(w.get("word", "")).lower())
        if dur >= hard_s:
            out.append((s, e, tok or "·", dur))
        elif len(tok) <= soft_max_chars or tok in _FILLER_TOKENS:
            out.append((s, e, tok or "·", dur))
    return out


def _drop_words_inside_silences(
    words: list[dict],
    silences: list[tuple[float, float]],
    *,
    flank_s: float = 0.05,
) -> tuple[list[dict], list[dict]]:
    """Separa palabras AUDIBLES de palabras FANTASMA por amplitud.

    Una palabra es FANTASMA solo si está ENTERAMENTE dentro de un silencio
    medido por amplitud Y ese silencio la rodea por AMBOS lados con margen
    `flank_s` (queda "varada" en mitad de un silencio largo → Whisper la
    alucinó o le puso timestamp erróneo en un hueco real, es inaudible).

    El flanqueo por ambos lados es CLAVE: una palabra real dicha muy bajo al
    final de una frase (voz floja) tiene silencio SOLO después, no antes —
    NO debe contar como fantasma o claparíamos el cierre real (p.ej. el
    precio "8 euros" final de una creadora que habla bajito). Las fantasma
    de verdad (palabras sueltas en mitad de una pausa) sí tienen silencio a
    ambos lados.

    Returns: (voiced_words, ghost_words).
    """
    if not words or not silences:
        return list(words), []
    sil = _merge_intervals(list(silences))
    voiced: list[dict] = []
    ghosts: list[dict] = []
    for w in words:
        try:
            ws = float(w["start"]); we = float(w["end"])
        except (KeyError, ValueError, TypeError):
            voiced.append(w)
            continue
        # ¿Hay un silencio que contenga la palabra con margen a ambos lados?
        flanked = any(
            a <= ws - flank_s and b >= we + flank_s
            for a, b in sil
        )
        if flanked:
            ghosts.append(w)
        else:
            voiced.append(w)
    return voiced, ghosts


def _trim_cuts_to_avoid_words(
    cuts: list[tuple[float, float]],
    *,
    words: list[dict],
    pad_s: float = 0.05,
    min_remaining_s: float = 0.15,
) -> list[tuple[float, float]]:
    """Recorta los cuts para que NO solapen con palabras transcritas, en
    vez de descartarlos enteros.

    Casos:
      - Cut totalmente fuera de cualquier palabra → keep tal cual.
      - Cut con palabra(s) dentro → partir en sub-cuts a izquierda/derecha.
      - Cada sub-cut resultante debe medir ≥ `min_remaining_s`, si no, drop.

    `pad_s` añade margen a cada palabra (no cortar pegado a la "s" final).
    Mucho menos destructivo que `_filter_cuts_outside_words` (que tiraba
    el cut entero si rozaba una palabra). Antes perdíamos 65% de cuts
    de amplitud que eran silencios reales rozando los bordes de palabras.
    """
    if not words:
        return list(cuts)
    # Word ranges con padding, ordenados por start
    word_ranges = sorted(
        (max(0.0, float(w["start"]) - pad_s), float(w["end"]) + pad_s)
        for w in words
    )

    out: list[tuple[float, float]] = []
    for cs, ce in cuts:
        # Palabras que solapan con este cut
        overlapping = [(ws, we) for (ws, we) in word_ranges if ws < ce and we > cs]
        if not overlapping:
            out.append((cs, ce))
            continue
        # Construir sub-intervalos: parte de [cs] y va saltando cada palabra
        cursor = cs
        for ws, we in overlapping:
            # Hueco entre cursor y el inicio de la palabra
            if ws > cursor:
                sub = (cursor, min(ws, ce))
                if sub[1] - sub[0] >= min_remaining_s:
                    out.append(sub)
            cursor = max(cursor, we)
            if cursor >= ce:
                break
        # Hueco final tras la última palabra
        if cursor < ce:
            sub = (cursor, ce)
            if sub[1] - sub[0] >= min_remaining_s:
                out.append(sub)
    return out


# ---------------------------------------------------------------------------
# Diagnóstico — dump JSON al temp_folder para iteración
# ---------------------------------------------------------------------------
def _write_diagnostic(diagnostic: dict, ctx) -> None:
    """Escribe `editor_diagnostic_<job_id>.json` en `ctx.temp_folder`.

    NO falla si la escritura tira (sería injusto que un bug del diag
    rompa el job). Solo loguea. El path se incluye en logs UI para que
    el operador pueda abrirlo desde el explorer.
    """
    try:
        out_path = Path(ctx.temp_folder) / f"editor_diagnostic_{ctx.job_id}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(diagnostic, f, ensure_ascii=False, indent=2, default=str)
        ctx.on_log(f"[silence_cutter] 🔬 Diagnóstico → {out_path}")
    except Exception as e:
        ctx.on_log(f"[silence_cutter] ⚠️ No se pudo escribir diagnóstico: {e}")


def _ai_cleanup_cuts(
    *,
    words: list[dict],
    video_duration: float,
    language: str,
    model: str,
    log,
) -> list[tuple[float, float]]:
    """Recibe transcript Whisper + duración total → cuts en segundos.

    El prompt del analyst está optimizado para devolver también
    head_silence / tail_silence con índices especiales (-1, -2) y
    `t_start`/`t_end` explícitos. Esto cubre el caso "10 segundos sin
    hablar al principio" incluso sin Silero VAD.
    """
    from src.editor_auto.api.openai_client import analyze_transcript_json

    prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "silence_cutter_analyst.md"
    system_prompt = prompt_path.read_text(encoding="utf-8")

    payload = {
        "language": language,
        "total_words": len(words),
        "total_duration_s": round(video_duration, 3),
        "words": [
            {"idx": i, "word": w["word"], "start": round(w["start"], 3),
             "end": round(w["end"], 3)}
            for i, w in enumerate(words)
        ],
    }
    result = analyze_transcript_json(
        system_prompt=system_prompt,
        user_payload=payload,
        model=model,
        temperature=0.2,
    )
    cuts_raw = result.get("cuts", []) if isinstance(result, dict) else []
    if isinstance(result, dict) and result.get("summary"):
        log(f"[silence_cutter] IA summary: {result['summary']}")

    return _parse_ai_cuts(cuts_raw, words=words, video_duration=video_duration)


def _parse_ai_cuts(
    cuts_raw: list[dict],
    *,
    words: list[dict],
    video_duration: float,
) -> list[tuple[float, float]]:
    """Convierte los cuts del prompt en intervalos temporales (s, e).

    Soporta:
      - `start_word_idx >= 0`: usa `words[i].start` / `words[j].end`.
        Si el cut trae `t_start`/`t_end` explícitos, prevalecen (esto
        permite cortar ENTRE 2 palabras — caso noise_gap).
      - `start_word_idx == -1`: head_silence → `t_start`/`t_end` explícitos.
      - `start_word_idx == -2`: tail_silence → `t_start`/`t_end` explícitos.
    """
    intervals: list[tuple[float, float]] = []
    n = len(words)
    for cut in cuts_raw:
        try:
            i0 = int(cut.get("start_word_idx"))
            i1 = int(cut.get("end_word_idx"))
        except (TypeError, ValueError):
            continue

        t_start_explicit = cut.get("t_start")
        t_end_explicit = cut.get("t_end")

        if i0 in (-1, -2):
            # head/tail silence: el modelo debe enviar t_start/t_end explícitos.
            if t_start_explicit is None or t_end_explicit is None:
                continue
            t0 = float(t_start_explicit)
            t1 = float(t_end_explicit)
        else:
            if not (0 <= i0 <= i1 < n):
                continue
            t0 = float(t_start_explicit) if t_start_explicit is not None else float(words[i0]["start"])
            t1 = float(t_end_explicit) if t_end_explicit is not None else float(words[i1]["end"])

        # Clamp a [0, duration]
        t0 = max(0.0, min(video_duration, t0))
        t1 = max(0.0, min(video_duration, t1))
        if t1 - t0 > 0.05:
            intervals.append((t0, t1))
    return intervals


# ---------------------------------------------------------------------------
# Helpers de intervalos (puros — fácilmente testables)
# ---------------------------------------------------------------------------
def _merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not intervals:
        return []
    sorted_iv = sorted(intervals, key=lambda x: x[0])
    merged: list[tuple[float, float]] = [sorted_iv[0]]
    for s, e in sorted_iv[1:]:
        last_s, last_e = merged[-1]
        # Tolerancia 80ms — cuts contiguos con micro-gaps de <80ms se fusionan
        # para evitar slivers audibles tipo "cua" entre dos cuts grandes.
        if s <= last_e + _MERGE_TOLERANCE_S:
            merged[-1] = (last_s, max(last_e, e))
        else:
            merged.append((s, e))
    return merged


def _invert_intervals(
    intervals: list[tuple[float, float]],
    total_duration: float,
) -> list[tuple[float, float]]:
    if total_duration <= 0:
        return []
    if not intervals:
        return [(0.0, total_duration)]
    sorted_iv = sorted(intervals, key=lambda x: x[0])
    gaps: list[tuple[float, float]] = []
    cursor = 0.0
    for s, e in sorted_iv:
        s = max(0.0, s)
        e = min(total_duration, e)
        if s > cursor:
            gaps.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < total_duration:
        gaps.append((cursor, total_duration))
    return gaps


# ---------------------------------------------------------------------------
# FFmpeg apply cuts — respeta rotation + fuerza 1080x1920 si 9:16
# ---------------------------------------------------------------------------
# Rotation: FFmpeg autorrota nativo leyendo `Display Matrix` antes de meter
# el frame al filter graph. Antes hacíamos `-noautorotate + transpose=N`
# manual y se rotaba al revés (resultado 180° volteado) porque autorotate
# y transpose se aplicaban en cascada. La fix es CONFIAR en autorotate.


# Detección NVENC cacheada — la 1050 Ti / cualquier GPU NVIDIA reciente
# acelera ~8-10x el encode H.264 vs libx264 preset medium. Sin GPU caemos
# a libx264 veryfast (vs medium que era el cuello de botella antes).
_NVENC_CACHE: bool | None = None


def _has_nvenc() -> bool:
    """¿Podemos USAR h264_nvenc en este host?

    No basta con ver "h264_nvenc" en `-encoders` (el FFmpeg de Debian
    viene compilado con NVENC aunque el host no tenga GPU NVIDIA). Hace
    falta abrir realmente el encoder — si `libcuda.so.1` falta o el
    driver NVIDIA no está, falla y caemos a libx264 (CPU).

    Cache por proceso: una vez detectado, no re-probamos.
    """
    global _NVENC_CACHE
    if _NVENC_CACHE is not None:
        return _NVENC_CACHE
    try:
        out = subprocess.check_output(
            ["ffmpeg", "-hide_banner", "-encoders"],
            stderr=subprocess.DEVNULL, timeout=10,
        )
        if b"h264_nvenc" not in out:
            _NVENC_CACHE = False
            return False
    except Exception:
        _NVENC_CACHE = False
        return False

    # Smoke test real: encode 1 frame negro 64x64 a /dev/null. Si falta
    # libcuda o driver, esto sale con código ≠ 0 en ~1s.
    try:
        rc = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.05:r=10",
                "-c:v", "h264_nvenc", "-frames:v", "1",
                "-f", "null", "-",
            ],
            capture_output=True, timeout=15,
        ).returncode
        _NVENC_CACHE = rc == 0
    except Exception:
        _NVENC_CACHE = False
    return _NVENC_CACHE


def _video_encoder_args() -> list[str]:
    """Args ffmpeg de codificación H.264 — NVENC si está, fallback CPU."""
    if _has_nvenc():
        # NVENC preset p4 = balanced (calidad/velocidad). cq 22 ≈ crf 20
        # de libx264 visualmente. Para 1080p hace ~150-300fps en una 1050 Ti.
        return [
            "-c:v", "h264_nvenc",
            "-preset", "p4",
            "-tune", "hq",
            "-rc", "vbr",
            # cq 19 ≈ crf 18 libx264: prioriza calidad (el cliente no quiere
            # perder nitidez). Sube algo el peso del archivo, asumido.
            "-cq", "19",
            "-b:v", "0",
            "-pix_fmt", "yuv420p",
        ]
    # CPU fallback. crf 18 = calidad alta (casi sin pérdida visible) para no
    # degradar el vídeo del cliente. `medium` da mejor compresión que veryfast
    # a igual crf, manteniendo la calidad sin disparar demasiado el tiempo.
    return [
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
    ]


def _aspect_filter(output_aspect: str) -> str | None:
    """Filtro de escalado/pad para forzar 1080x1920 si output_aspect=9:16.

    `preserve` deja el aspect del input. Para `9:16`:
      - scale al fit dentro de 1080x1920 (preserva aspect)
      - pad negro hasta 1080x1920 con centrado.

    Se aplica DESPUÉS del transpose, así que opera sobre el frame ya
    rotado (vertical real).
    """
    if output_aspect != "9:16":
        return None
    return (
        "scale=w=1080:h=1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
        "setsar=1"
    )


def _apply_cuts_ffmpeg(
    *,
    input_path: str,
    output_path: str,
    keep_intervals: list[tuple[float, float]],
    rotation: int,
    output_aspect: str,
    log,
    on_progress,
    normalize_audio: bool = False,
) -> None:
    """Concatena los `keep_intervals` con un filter_complex de FFmpeg.

    Cada segmento se procesa con `trim`/`atrim` + `setpts`/`asetpts`, se
    le aplica la rotación detectada (transpose) y opcionalmente el
    aspect ratio 9:16 con padding. Luego `concat=n=N:v=1:a=1`. Esto
    preserva la sincronía A/V y respeta la rotation metadata del input
    (cosa que MoviePy hace mal con .mov de iPhone).
    """
    n = len(keep_intervals)
    if n == 0:
        raise RuntimeError("No hay intervalos a conservar.")

    # Rotation: confiamos en autorotate nativo de ffmpeg que lee el
    # `Display Matrix` ANTES de entrar al filter graph. El trim+concat
    # opera ya sobre el frame correctamente orientado.
    aspect_vf = _aspect_filter(output_aspect)
    extra_vf = "," + aspect_vf if aspect_vf else ""

    # Micro fade in/out de 20ms en cada segmento de audio — elimina los
    # "clicks" o sub-frames residuales típicos al concatenar cortes
    # sub-segundo (el caso "cua" tras Android del operador). 20ms es
    # imperceptible para voz humana pero suaviza la transición y limpia
    # cualquier cola de audio que FFmpeg no recorta limpio.
    _FADE_S = 0.02
    _FADE_TAIL_S = 0.15  # fade-out del cierre — mata el residuo tras la última palabra

    filter_parts: list[str] = []
    concat_inputs: list[str] = []
    for i, (start, end) in enumerate(keep_intervals):
        filter_parts.append(
            f"[0:v]trim=start={start:.3f}:end={end:.3f},"
            f"setpts=PTS-STARTPTS{extra_vf}[v{i}]"
        )
        seg_dur = end - start
        # Fade-out del ÚLTIMO segmento más largo (~150ms): desvanece la cola
        # tras la última palabra → mata cualquier residuo/clic/"du" del cierre
        # (cola de boca, artefacto del corte, lookahead de loudnorm) sin clipar
        # la palabra. El resto de segmentos usan el micro-fade de 20ms.
        is_last = (i == len(keep_intervals) - 1)
        fade_out_d = _FADE_TAIL_S if (is_last and seg_dur >= 0.35) else _FADE_S
        # Solo aplicamos fades si el segmento es lo suficientemente largo
        # para no comerse contenido (mínimo 100ms para 20+20ms de fades).
        if seg_dur >= 0.10:
            fade_out_start = seg_dur - fade_out_d
            audio_filter = (
                f"[0:a]atrim=start={start:.3f}:end={end:.3f},"
                f"asetpts=PTS-STARTPTS,"
                f"afade=t=in:st=0:d={_FADE_S},"
                f"afade=t=out:st={fade_out_start:.3f}:d={fade_out_d}[a{i}]"
            )
        else:
            audio_filter = (
                f"[0:a]atrim=start={start:.3f}:end={end:.3f},"
                f"asetpts=PTS-STARTPTS[a{i}]"
            )
        filter_parts.append(audio_filter)
        concat_inputs.append(f"[v{i}][a{i}]")

    # Etiqueta de salida de audio: si normalizamos, encadenamos loudnorm
    # (EBU R128 → -16 LUFS) DESPUÉS del concat para que TODA la pista quede a
    # loudness estándar y se oiga (grabaciones bajitas que antes "no se oían").
    # Se aplica al output final, una sola vez, tras unir los segmentos.
    a_out = "[outa]"
    norm_part = ""
    if normalize_audio:
        norm_part = ";[outa]loudnorm=I=-16:TP=-1.5:LRA=11[outa_norm]"
        a_out = "[outa_norm]"

    concat_filter = (
        "".join(concat_inputs) + f"concat=n={n}:v=1:a=1[outv][outa]"
    )
    filter_complex = ";".join(filter_parts) + ";" + concat_filter + norm_part

    # Duración esperada del output (suma de keep_intervals) → ms para que el
    # progress callback sepa contra qué comparar `out_time_ms` y dar % real.
    total_output_ms = int(sum(end - start for start, end in keep_intervals) * 1000)

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", a_out,
        *_video_encoder_args(),
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        # Limpiar metadata de rotación residual del input — el frame ya
        # está rotado físicamente, no queremos que el player lo rote otra vez.
        "-metadata:s:v:0", "rotate=0",
        output_path,
    ]
    encoder_label = "h264_nvenc (GPU)" if _has_nvenc() else "libx264 veryfast (CPU)"
    log(f"[silence_cutter] FFmpeg concat de {n} segmentos · "
        f"rotation={rotation}° · aspect={output_aspect} · enc={encoder_label} · "
        f"target_ms={total_output_ms}")
    _run_ffmpeg_with_progress(
        cmd,
        total_ms=total_output_ms,
        on_progress=on_progress,
    )


def _passthrough_with_format(
    input_path: str,
    output_path: str,
    rotation: int,
    *,
    output_aspect: str,
    log,
) -> None:
    """Sin cortes pero aún normalizamos formato (rotation + aspect).
    Útil porque el resultado siempre debe pasar a la siguiente herramienta
    en un formato consistente.
    """
    aspect_vf = _aspect_filter(output_aspect)
    if not aspect_vf and rotation == 0:
        # Nada que normalizar — copy puro
        import shutil
        shutil.copyfile(input_path, output_path)
        return
    # Si solo hay aspect (rotation ya la hace autorotate), usamos `-vf`.
    # Si rotation != 0 también dejamos que autorotate de ffmpeg actúe y
    # añadimos el aspect después.
    vf = aspect_vf or "null"
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", vf,
        *_video_encoder_args(),
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        "-metadata:s:v:0", "rotate=0",
        output_path,
    ]
    encoder_label = "h264_nvenc (GPU)" if _has_nvenc() else "libx264 veryfast (CPU)"
    log(f"[silence_cutter] Passthrough con normalización · vf={vf} · enc={encoder_label}")
    _run_ffmpeg_with_progress(cmd, on_progress=lambda f: None)


def _run_ffmpeg_with_progress(
    cmd: list[str],
    *,
    on_progress,
    total_ms: int | None = None,
) -> None:
    """Ejecuta ffmpeg con `-progress pipe:1` para emitir progreso periódico.

    `total_ms` es la duración esperada del output (sumando keep_intervals)
    para calcular el % real. Si es None / 0 nos limitamos a emitir el 1.0
    final — sin él el ETA del job se congela en el % inicial del slot.

    CRÍTICO: drenamos stderr en un thread daemon para evitar deadlock. Con
    filter_complex complejos ffmpeg escribe muchos warnings a stderr; si
    nadie los lee, el pipe del kernel se llena (~64KB), ffmpeg se bloquea
    esperando que se vacíe, NO escribe progress a stdout, y nuestro
    `readline()` espera indefinidamente. Hemos visto este síntoma: proceso
    ffmpeg vivo con 0% CPU durante 5+ minutos. La fix es leer ambos pipes
    en paralelo.
    """
    import collections
    import threading

    proc = subprocess.Popen(
        cmd + ["-progress", "pipe:1", "-nostats"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )

    # Buffer rotativo con las últimas N líneas de stderr (para mensaje de
    # error si falla). Usar deque(maxlen=N) es O(1) y limita memoria.
    stderr_tail: collections.deque[str] = collections.deque(maxlen=200)

    def _drain_stderr() -> None:
        if proc.stderr is None:
            return
        for line in proc.stderr:
            stderr_tail.append(line.rstrip("\n"))

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    try:
        while True:
            if proc.stdout is None:
                break
            line = proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            if line.startswith("out_time_ms="):
                try:
                    cur_us = int(line.split("=", 1)[1])
                except ValueError:
                    continue
                cur_ms = cur_us // 1000
                if total_ms and total_ms > 0:
                    on_progress(min(0.99, cur_ms / total_ms))
            elif line.startswith("progress=") and line.endswith("end"):
                on_progress(1.0)
        code = proc.wait()
    finally:
        # Asegurar que el thread drenador termina (proceso ya cerró stderr).
        stderr_thread.join(timeout=5.0)

    if code != 0:
        err_text = "\n".join(stderr_tail)
        raise RuntimeError(
            f"FFmpeg salió con código {code}. Stderr (últimas {len(stderr_tail)} líneas):\n"
            + err_text
        )


# ---------------------------------------------------------------------------
# Detección de estilo: monólogo vs conversación
# ---------------------------------------------------------------------------
def _detect_conversation_style(
    speech_intervals: list[tuple[float, float]],
    video_duration: float,
) -> tuple[str, dict]:
    """Decide si el vídeo es 'monologue' o 'conversation' a partir del
    output de Silero VAD.

    Heurística sin coste (los datos ya los tenemos):

      - `mean_segment_s`  = duración media de tramos de voz. Monólogos
        suelen tener segmentos largos (≥5s); conversaciones cortos (1-4s)
        por turnos de habla.
      - `turn_gap_ratio`  = fracción de la duración total ocupada por
        pausas cortas (0.4-1.5s) — patrón típico de turn-taking. Alto
        ratio = muchas pausas cortas = conversación.

    Reglas (en orden):
      1. < 3 segmentos de voz → datos insuficientes → 'monologue'.
      2. `mean_segment_s < 4.0` Y `turn_gap_ratio > 0.05` → conversación clara.
      3. `mean_segment_s ≥ 6.0` → monólogo claro.
      4. Caso intermedio: si `turn_gap_ratio > 0.08` → conversación;
         si no → monólogo (default conservador, preserva legacy).

    Devuelve `(style, metrics_dict)` para logging.
    """
    n = len(speech_intervals)
    if n < 3 or video_duration <= 0:
        return "monologue", {
            "style": "monologue",
            "reason": "datos insuficientes",
            "n_speech_intervals": n,
        }
    seg_durs = [b - a for a, b in speech_intervals if b > a]
    mean_seg = sum(seg_durs) / len(seg_durs) if seg_durs else 0.0
    # Gaps cortos entre tramos de voz (típicos de turnos).
    short_gap_total = 0.0
    for i in range(1, n):
        gap = speech_intervals[i][0] - speech_intervals[i - 1][1]
        if 0.4 <= gap <= 1.5:
            short_gap_total += gap
    turn_gap_ratio = short_gap_total / max(video_duration, 0.001)

    if mean_seg < 4.0 and turn_gap_ratio > 0.05:
        decision = "conversation"
        reason = "segmentos cortos + muchos gaps cortos (turn-taking)"
    elif mean_seg >= 6.0:
        decision = "monologue"
        reason = "segmentos largos (monólogo claro)"
    elif turn_gap_ratio > 0.08:
        decision = "conversation"
        reason = "muchos gaps cortos (turn-taking)"
    else:
        decision = "monologue"
        reason = "default conservador (caso intermedio)"

    return decision, {
        "style": decision,
        "reason": reason,
        "n_speech_intervals": n,
        "mean_segment_s": round(mean_seg, 2),
        "turn_gap_ratio": round(turn_gap_ratio, 4),
    }


def _apply_style_overrides(
    config: dict[str, Any],
    style: str,
) -> dict[str, Any]:
    """Devuelve una copia de config con thresholds ajustados según el estilo.

    Solo 'conversation' modifica defaults. 'monologue' devuelve la copia
    tal cual (= comportamiento legacy/agresivo intacto)."""
    new_config = dict(config)
    if style == "conversation":
        # Sube el umbral inter-frase de 0.5s → 1.2s: solo silencios MUY
        # largos se cortan, los gaps de turnos se preservan.
        new_config["inter_word_gap_threshold_s"] = max(
            1.2, float(config.get("inter_word_gap_threshold_s", 0.5))
        )
        # Aumenta el padding natural que se conserva (200ms → 350ms).
        # Hace que los cortes que SÍ ocurren no suenen secos.
        new_config["inter_word_gap_keep_ms"] = max(
            350, int(config.get("inter_word_gap_keep_ms", 200))
        )
    return new_config
