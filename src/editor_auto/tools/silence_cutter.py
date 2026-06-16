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
import unicodedata
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

# Self-heal SALVAGE (drop-offender): si un lote de cortes de limpieza sube el
# score pero UN corte roza una palabra (introduce 1 fallo de palabra), en vez de
# tirar TODO el lote, localizamos el/los corte(s) culpables (los que solapan la
# palabra perdida) y re-renderizamos sin ellos. Solo se intenta si hay ≥ esta
# ganancia en juego (no merece un re-render por <10 pts). El resultado solo
# reemplaza al output si queda ESTRICTAMENTE mejor por la misma clave _qkey →
# nunca empeora un vídeo.
_SALVAGE_MIN_GAIN = 10

# Re-alineación de spans INFLADOS de Whisper (palabra real + pausa absorbida,
# p.ej. 'asegúrate' 2.6s, 'muchísimo' 2.78s). Encoge SOLO el span a su voz
# dominante para liberar el silencio absorbido. Umbrales relativos al suelo
# LOCAL del propio span (la voz floja a −25dB lee como voz) — clave para no
# tocar voz floja real (lección de regresiones por umbral absoluto).
_REALIGN_INFLATE_HARD_S = 1.6   # cualquier token >= esto = candidato
_REALIGN_INFLATE_SOFT_S = 0.9   # token corto/filler/stopword >= esto = candidato
_REALIGN_VOICE_DB = 12.0        # voz = energía >= suelo_local_del_span + esto
_REALIGN_MIN_DEAD_S = 0.35      # prueba de INFLACIÓN: hueco mudo contiguo mínimo
_REALIGN_MIN_RUN_S = 0.12       # run de voz mínimo (nunca dejar palabra < esto)
_REALIGN_BRIDGE_S = 0.10        # puentea micro-dips dentro de una palabra
_REALIGN_PAD_S = 0.06           # margen alrededor del run de voz


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
            # gpt-5.4 (no-razonador, acepta temp 0 + seed) en TODAS las pasadas
            # → análisis DETERMINISTA: mismo vídeo = mismo corte siempre. Mejor
            # que gpt-4o y casi mismo precio. Gemini queda fuera por ser
            # "thinking" (varía aunque temp=0 → rompe la consistencia).
            "ai_model": "gpt-5.4",
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
            # Gemini DESACTIVADO (determinismo): la pasada 2 corre solo con gpt
            # (temp 0 + seed) = mismo resultado siempre. Probado en el caso
            # borderline "y esto empezó esto costaba": ni Gemini ni el transcript
            # limpio lo cazan en el pipeline real (sí en una re-transcripción
            # aislada del output, pero ese input no existe en pass2) → no merece
            # romper el determinismo. Reactivar solo para A/B de recall.
            "ai_pass2_gemini_enabled": False,
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

        # 0a) REPARAR ENTRADA si el stream de vídeo viene dañado. Un .mov/.mp4
        # con NAL inválidos hace el decode NO determinista → Whisper saca
        # timings ligeramente distintos y el render concela errores distinto en
        # cada run, así que el MISMO vídeo daba scores base diferentes (84/89/92
        # /94) y cortes inconsistentes. Re-encodear a H264 limpio lo estabiliza.
        # Solo afecta a vídeos corruptos; los sanos pasan intactos.
        repaired = _repair_corrupt_input(
            input_path, ctx.temp_folder, ctx.job_id, ctx.on_log,
        )
        if repaired != input_path:
            diagnostic["input_repaired"] = True
            input_path = repaired

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

        # 1b) Audio NIVELADO para detección de palabras (Whisper + Silero VAD).
        # En grabaciones con voz BAJA (mala SNR), Silero marca silencio donde hay
        # habla floja y Whisper la transcribe con timestamps malos → palabras
        # como 'proteína' se pierden (se filtran como fantasma). loudnorm sube
        # TODA la pista al nivel que esperan VAD/Whisper sin degradar la SNR.
        # La amplitud (detección de silencios) sigue sobre el ORIGINAL → no
        # alarga el vídeo ni infla silencios. Es el mismo filtro del output.
        tmp_audio_vad = tmp_audio
        if bool(config.get("level_audio_for_vad", True)):
            leveled = str(tmp_dir / f"editor_silence_{ctx.job_id}_lvl.wav")
            if _level_audio(tmp_audio, leveled, log=ctx.on_log):
                tmp_audio_vad = leveled
                diagnostic["phases"]["audio_leveling"] = {
                    "enabled": True, "for": "whisper+silero", "filter": "loudnorm",
                }
                ctx.on_log(
                    "[silence_cutter] 🔊 Audio nivelado (loudnorm) para Whisper+"
                    "Silero — capta voz baja sin tocar la detección de silencios"
                )

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
                    tmp_audio_vad,
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

            # 3a) RE-ALINEAR SPANS INFLADOS: Whisper a veces marca una palabra
            # mucho más larga de lo que suena (palabra + pausa absorbida:
            # 'asegúrate' 2.6s, 'muchísimo' 2.78s). Encogemos SOLO el span a su
            # voz dominante — nunca movemos/insertamos/borramos/reordenamos una
            # palabra → seguro por construcción (no puede perder una palabra,
            # resucitar un tartamudeo, ni cortar voz floja). Así el silencio
            # absorbido queda LIBRE y el cortador de pausas lo quita normalmente.
            # Corre ANTES de todo (fillers/fantasmas/auto-trim/IA) para que TODAS
            # las fases vean spans consistentes. Lee el audio nivelado (el que
            # Whisper transcribió). Con kill-switch.
            if words and bool(config.get("realign_inflated_spans", True)):
                try:
                    n_re = _shrink_inflated_word_spans(words, tmp_audio_vad)
                    diagnostic["phases"]["span_realign"] = {
                        "n_shrunk": n_re,
                        "preview": [
                            {"w": w.get("word"),
                             "start": w.get("start"), "end": w.get("end")}
                            for w in words if w.get("_realigned")
                        ][:10],
                    }
                    if n_re:
                        ctx.on_log(
                            f"[silence_cutter] 📐 {n_re} span(s) inflado(s) "
                            f"encogido(s) a su voz (silencio liberado para cortar)"
                        )
                except Exception as e:  # noqa: BLE001
                    ctx.on_log(f"[silence_cutter] ⚠️ Re-alineación de spans falló: {e}")

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
                    tmp_audio_vad,
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
                # Etiqueta los 'noise_gap' aparte ("ai_noise_gap"): la IA marcó
                # una PAUSA ahí, no un borrado deliberado de contenido. Si en ese
                # hueco había una palabra de contenido (caso real 'proteína'),
                # word-protection la re-anexa. Fallback seguro al "ai" de siempre
                # si el conteo no cuadra.
                _ai_tagged = _parse_ai_cuts_tagged(
                    (ai_raw_result or {}).get("cuts", []),
                    words=words, video_duration=video_duration,
                )
                if len(_ai_tagged) == len(ai_cuts):
                    for s, e, _rsn in _ai_tagged:
                        cuts_with_source.append(
                            (s, e, "ai_noise_gap" if _rsn == "noise_gap" else "ai")
                        )
                else:
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
        # N-gram SIEMPRE (determinista + gratis): red de seguridad para
        # repeticiones LITERALES que el holistic IA se deje (p.ej. "aprovecha
        # que ahora… aprovecha que ahora"). Antes solo corría si el holistic
        # fallaba, y por eso se colaban restarts literales. gap 1.0s capta el
        # restart aunque haya un micro-relleno entre las dos copias.
        ngram_diag: dict[str, Any] = {"enabled": True}
        if clean_words:
            ngram_cuts_detailed = _detect_repeated_ngrams(
                clean_words, min_n=2, max_n=6, max_gap_between_grams_s=1.0,
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
        # NOTA: antes esto llevaba `and not holistic_ok`, que APAGABA la pasada 2
        # cuando el holístico devolvía cortes (lo normal). Eso dejaba pasar
        # false-starts/auto-correcciones (regresión: "estocost"). El holístico
        # NO garantiza pillar false-starts, así que la pasada 2 corre SIEMPRE
        # (igual que ya se hizo con el n-gram). El sobre-corte queda contenido
        # por el guardarraíl anti-huérfano del holístico + word-guard + cierre.
        ai_pass2_on = bool(config.get("ai_false_starts_pass2", True))
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

        # NOTA: tmp_audio se borra MÁS ABAJO — el refinado de bordes al valle
        # de energía real (_refine_cut_edges_to_valley) aún lo necesita.

        # 8) Merge final + invertir → keep_intervals
        if not cuts_with_source:
            diagnostic["final"] = {
                "n_cuts_merged": 0,
                "total_cut_s": 0.0,
                "decision": "passthrough_no_cuts",
            }
            _write_diagnostic(diagnostic, ctx)
            ctx.on_log("[silence_cutter] No hay cortes a aplicar → passthrough.")
            for _p in (tmp_audio, tmp_audio_vad):
                try:
                    if _p and _p != input_path:
                        os.remove(_p)
                except OSError:
                    pass
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

        # 7c) PROTEGER LA FRASE DE CIERRE ENTERA (no solo la última palabra). Una
        # capa IA (pass2/holístico) marca a veces el CTA final ("te lo dejo aquí
        # anclado") como frase abandonada y lo corta a MITAD de palabra → deja un
        # fragmento roto ("clado"). Aquí protegemos el último BLOQUE CONTIGUO de
        # habla (la CTA + despedida): cualquier corte que ACABE dentro de ese
        # bloque (sin llegar al final) se recorta para terminar ANTES → la frase
        # de cierre queda ENTERA. El cliente quiere conservar el CTA de cierre.
        if bool(config.get("protect_closing_phrase", True)) and voiced_words:
            vw = sorted(
                (w for w in voiced_words if "start" in w and "end" in w),
                key=lambda w: float(w["start"]),
            )
            if vw:
                closing_gap_s = 0.6
                run_start = float(vw[-1]["start"])
                for i in range(len(vw) - 1, 0, -1):
                    if float(vw[i]["start"]) - float(vw[i - 1]["end"]) <= closing_gap_s:
                        run_start = float(vw[i - 1]["start"])
                    else:
                        break
                last_we = max(float(w["end"]) for w in vw)
                n_clip = 0
                new_cws3: list[tuple[float, float, str]] = []
                for s, e, src in cuts_with_source:
                    # corte que empieza ANTES del cierre y acaba DENTRO de él
                    # (comería parte del CTA) → recortar a `run_start`.
                    if s < run_start - 0.02 and run_start - 0.02 < e <= last_we + 0.05:
                        if run_start - s > 0.05:
                            new_cws3.append((s, run_start, src))
                        n_clip += 1
                    else:
                        new_cws3.append((s, e, src))
                cuts_with_source = new_cws3
                if n_clip:
                    diagnostic["phases"]["closing_phrase_protection"] = {
                        "run_start": round(run_start, 3), "n_clipped": n_clip,
                    }
                    ctx.on_log(
                        f"[silence_cutter] 🛡️ Frase de cierre protegida: {n_clip} "
                        f"corte(s) recortado(s) para no partir el CTA final "
                        f"(cierre desde {run_start:.1f}s)"
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
        n_refined_edges = 0
        if voiced_words:
            merged_cuts = _protect_word_boundaries(
                merged_cuts, voiced_words, _WORD_GUARD_S,
            )
            merged_cuts = _merge_intervals(merged_cuts)  # re-merge por si encogieron
            ctx.on_log(
                f"[silence_cutter] 🛡️ Protección de palabras (guard "
                f"{int(_WORD_GUARD_S*1000)}ms): {n_before} → {len(merged_cuts)} cortes"
            )
            # Refinado de bordes en HABLA CONTIGUA (palabra eliminada pegada a
            # la buena, sin silencio entre medias): Whisper marca los límites
            # ~100-300ms ANTES del audio real, así que cortar exactamente en
            # next_start deja la COLA de la palabra mala ("...zó" antes de
            # "esto costaba"). Aquí movemos ese borde al VALLE de energía real
            # (mínimo RMS) entre ambas palabras → corte limpio sin residuo.
            try:
                merged_cuts, n_refined = _refine_cut_edges_to_valley(
                    merged_cuts, voiced_words or words, tmp_audio,
                )
                n_refined_edges = n_refined
                if n_refined:
                    ctx.on_log(
                        f"[silence_cutter] 🎯 {n_refined} borde(s) afinados al "
                        f"valle de energía real (habla contigua)"
                    )
            except Exception as e:  # noqa: BLE001
                ctx.on_log(f"[silence_cutter] ⚠️ Refinado de bordes falló: {e}")
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
        # ANTI-CORTE-DE-VOZ: un corte de "silencio" largo a veces engulle una
        # palabra que Whisper MAL-ALINEÓ fuera de él (le puso timestamp en una
        # zona muda contigua — p.ej. 'proteína', cuyo audio real está a ~3.8s del
        # slot donde Whisper la etiquetó; el hueco entre medias se cortaba entero
        # llevándose la voz). Esa palabra es AUDIBLE: su energía está MUY por
        # encima del silencio real del propio corte. Partimos el corte para
        # CONSERVAR esas islas de voz. Solo deja de cortar → nunca sobre-corta.
        try:
            # Cortes AUTORITATIVOS (cabecera/cola + contenido IA): el rescate de
            # islas NO debe resucitar tos/falsos arranques dentro de ellos. Solo
            # rescata dentro de cortes acústicos (palabra real mal-alineada).
            _island_protected = [
                (s, e) for (s, e, src) in cuts_with_source
                if src in _CONTENT_CUT_SOURCES or src == "auto_trim" or src == "ai_noise_gap"
            ]
            merged_cuts, n_islands = _preserve_speech_islands_in_cuts(
                merged_cuts, tmp_audio, protected_cuts=_island_protected,
            )
            if n_islands:
                merged_cuts = _merge_intervals(merged_cuts)
                ctx.on_log(
                    f"[silence_cutter] 🗣️ {n_islands} isla(s) de VOZ rescatada(s) de "
                    f"dentro de un corte (palabra mal-alineada por Whisper, no se pierde)"
                )
                diagnostic["phases"]["speech_islands_preserved"] = {"n": n_islands}
        except Exception as e:  # noqa: BLE001
            ctx.on_log(f"[silence_cutter] ⚠️ Rescate de islas de voz falló: {e}")

        # NOTA: tmp_audio se conserva hasta el final de run() — el refinado de
        # bordes de KEEP al valle de energía (y el del self-heal) lo necesitan.

        keep_intervals = _invert_intervals(merged_cuts, video_duration)
        # INVARIANTE ANTI-OVER-CUT (robustez pública): una palabra hablada solo
        # puede eliminarse si una fase de CONTENIDO (holístico/IA/ngram/false-
        # start/filler estirado) la quitó a propósito. Las fases ACÚSTICAS
        # (VAD/energía/gap/auto-trim) cortan SILENCIO, jamás una palabra. Si una
        # palabra real (Whisper, sin fantasmas) la engulló solo un corte acústico
        # → se re-anexa. Resuelve el caso de bugallo ('proteína', 'un ojo', 'te
        # lo dejo aquí' comidos por acoustic/silero/gap). Solo AÑADE keep.
        keep_intervals, n_word_protected = _protect_words_from_acoustic_cuts(
            keep_intervals, cuts_with_source, voiced_words or words,
            video_duration=video_duration,
        )
        if n_word_protected:
            diagnostic["phases"]["word_protection_from_acoustic"] = {
                "words_reanexed": n_word_protected,
            }
            ctx.on_log(
                f"[silence_cutter] 🛟 {n_word_protected} palabra(s) hablada(s) "
                f"re-anexada(s) (las comía un corte acústico, no de contenido)"
            )
        # Absorbe micro-islas de keep (fragmentos de palabra / cabezas de
        # relleno) que el merge de cortes deja entre dos cortes y suenan como
        # media palabra o mini-corte raro. Conservador: una palabra de
        # contenido dentro la protege (respuestas cortas legítimas).
        min_keep_island_s = float(config.get("min_keep_island_s", 0.28))
        keep_intervals, absorbed_islands = _absorb_keep_islands(
            keep_intervals, voiced_words or words, min_keep_s=min_keep_island_s,
        )
        if absorbed_islands:
            ctx.on_log(
                f"[silence_cutter] 🧹 {len(absorbed_islands)} micro-isla(s) de keep "
                f"(<{int(min_keep_island_s*1000)}ms, sin contenido) absorbidas"
            )
        keep_intervals = [
            (a, b) for (a, b) in keep_intervals
            if (b - a) >= _MIN_KEEP_SEGMENT_S
        ]
        # Ajuste FINAL a palabras completas: elimina slivers del arranque de la
        # palabra cortada siguiente ('to'/'queto') y evita partir la última
        # palabra (final 'montó'). Es la última autoridad sobre los bordes.
        keep_intervals = _snap_keeps_to_words(keep_intervals, voiced_words or words)

        # Revisión IA de COMPLETITUD: caza finales colgados a mitad de idea
        # ('...y están solo por ocho' y salta) que el holístico conservó.
        # Determinista (temp 0 + seed); solo recorta palabras finales.
        n_completeness = 0
        if ai_on and bool(config.get("ai_completeness_enabled", True)):
            try:
                keep_intervals, comp_diag = _ai_completeness_review(
                    keep_intervals, voiced_words or words,
                    language=config.get("ai_language", "es"), log=ctx.on_log,
                )
                n_completeness = int(comp_diag.get("applied", 0) or 0)
                diagnostic["completeness_review"] = comp_diag
            except Exception as e:  # noqa: BLE001
                ctx.on_log(f"[silence_cutter] ⚠️ Revisión completitud falló: {e}")

        # CIERRE del vídeo: la última frase debe terminar en una pausa REAL
        # del hablante. Si quedó a medias (habla cortada pegada después),
        # extender hasta la pausa; si no hay pausa alcanzable, cerrar en la
        # frase anterior. El final es lo que más se nota.
        keep_intervals, final_fix = _complete_final_phrase(
            keep_intervals, voiced_words or words,
        )
        if final_fix:
            diagnostic["final_phrase_fix"] = list(final_fix)
            ctx.on_log(
                f"[silence_cutter] 🏁 Cierre del vídeo corregido: "
                f"{final_fix[0]} ({final_fix[1]} palabra(s))"
            )

        # Recorte de palabras funcionales COLGADAS al final de cada segmento
        # (que/y/bueno/...): una frase no puede terminar en conjunción antes
        # de un salto, ni el vídeo acabar en 'bueno'.
        keep_intervals, n_dangling = _trim_dangling_tail_words(
            keep_intervals, voiced_words or words,
        )
        if n_dangling:
            ctx.on_log(
                f"[silence_cutter] ✂️ {n_dangling} palabra(s) colgada(s) "
                f"recortadas del final de segmento (que/y/bueno/…)"
            )

        # Afinado de los DOS bordes de cada keep al VALLE de energía real:
        # mata las colas sub-palabra de la palabra cortada vecina ('o'/'as'/
        # 'os' de sedosit-O/florecit-AS/rayadit-O) que Whisper no puede ver
        # (marca límites ~100-300ms antes del audio real) y evita clipar la
        # última palabra buena. Solo actúa en habla contigua.
        n_keep_valley = 0
        try:
            keep_intervals, n_keep_valley = _refine_keep_edges_to_valley(
                keep_intervals, voiced_words or words, tmp_audio,
            )
            if n_keep_valley:
                ctx.on_log(
                    f"[silence_cutter] 🎯 {n_keep_valley} borde(s) de keep "
                    f"afinados al valle de energía (anti-cola de palabra)"
                )
        except Exception as e:  # noqa: BLE001
            ctx.on_log(f"[silence_cutter] ⚠️ Valle en bordes de keep falló: {e}")

        # RESCATE DE VOZ EN BORDES: si un corte acústico + el snap a palabras
        # clipó voz real pegada al borde de un keep (Whisper mal-alineó/infló el
        # span o se saltó una palabra: 'naranja' a medias, 'asegúrate' comido),
        # extendemos el borde hacia esa voz hasta el silencio real — sin entrar
        # en cortes de CONTENIDO (dedup/falso inicio). Puro audio, agnóstico a
        # los timings de Whisper. Solo añade keep.
        try:
            # +auto_trim: tampoco extender un keep hacia la cabecera/cola que el
            # auto-trim eliminó (re-metería el dead-air inicial/final — fallo s1/s6
            # de buga_1). El head/tail es tan autoritativo como un corte de la IA.
            _content_cuts = [
                (s, e) for (s, e, src) in cuts_with_source
                if src in _CONTENT_CUT_SOURCES or src == "auto_trim" or src == "ai_noise_gap"
            ]
            keep_intervals, n_voiced_ext = _extend_keeps_to_voiced_edges(
                keep_intervals, tmp_audio, _content_cuts,
            )
            if n_voiced_ext:
                ctx.on_log(
                    f"[silence_cutter] 🗣️ {n_voiced_ext} borde(s) de keep "
                    f"extendido(s) para rescatar voz clipada por el corte"
                )
                diagnostic["phases"]["voiced_edge_rescue"] = {"n": n_voiced_ext}
        except Exception as e:  # noqa: BLE001
            ctx.on_log(f"[silence_cutter] ⚠️ Rescate de voz en bordes falló: {e}")

        # Limpieza de palabras sueltas: un editor humano, al revisar su corte,
        # tira los clips diminutos aislados cuyo ÚNICO contenido es relleno
        # ('os', 'la', 'y'…) — el artefacto que más se nota (palabra colgada
        # entre dos cortes, sin frase). `_detect_loose_words` solo marca basura
        # por construcción (keep ≤0.85s, 1-2 tokens funcionales/≤2 chars), así
        # que descartarlos NUNCA se lleva contenido. Es no-regresión por diseño:
        # un vídeo sin sueltas no tiene nada que filtrar → no-op.
        if bool(config.get("drop_loose_filler_keeps", True)) and len(keep_intervals) > 1:
            try:
                _loose = _detect_loose_words(words, keep_intervals)
                if _loose:
                    _loose_spans = {(l["start"], l["end"]) for l in _loose}
                    _before_n = len(keep_intervals)
                    keep_intervals = [
                        (s, e) for (s, e) in keep_intervals
                        if (round(s, 2), round(e, 2)) not in _loose_spans
                    ] or keep_intervals  # nunca vaciar
                    _dropped = _before_n - len(keep_intervals)
                    if _dropped:
                        ctx.on_log(
                            f"[silence_cutter] 🧹 {_dropped} clip(s) suelto(s) de "
                            f"relleno descartado(s): "
                            f"{', '.join(repr(l['text']) for l in _loose[:4])}"
                        )
                        diagnostic["phases"]["loose_filler_cleanup"] = {
                            "n": _dropped, "preview": _loose[:6],
                        }
            except Exception as e:  # noqa: BLE001
                ctx.on_log(f"[silence_cutter] ⚠️ Limpieza de sueltas falló: {e}")

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
            "keep_islands_absorbed": len(absorbed_islands),
            "boundary_edges_refined": n_refined_edges,
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
        # Extender el último keep a la cola fricativa real de la última palabra
        # (anti "cuentas"→"cuento"): el detector de tail_silence corta antes de
        # que la "-s" se apague. Energía con suelo absoluto.
        if bool(config.get("extend_last_word_tail", True)):
            _ext_keeps = _extend_last_keep_to_word_tail(
                keep_intervals, tmp_audio, video_duration
            )
            if _ext_keeps and _ext_keeps[-1][1] > keep_intervals[-1][1] + 0.02:
                ctx.on_log(
                    f"[silence_cutter] 🗣️ Cola última palabra: extiendo keep "
                    f"{keep_intervals[-1][1]:.2f}s → {_ext_keeps[-1][1]:.2f}s "
                    f"(no clipar la fricativa final)."
                )
                keep_intervals = _ext_keeps
        _content_end_out = _content_end_output_s(keep_intervals, tmp_audio)
        _apply_cuts_ffmpeg(
            input_path=input_path,
            output_path=output_path,
            keep_intervals=keep_intervals,
            rotation=video_rotation,
            output_aspect=config.get("output_aspect", "9:16"),
            log=ctx.on_log,
            on_progress=lambda f: ctx.on_progress(0.72 + f * 0.25, "✂️ Renderizando…"),
            normalize_audio=normalize_audio,
            content_end_s=_content_end_out,
        )

        # 10) Auditoría post-render — analizar el MP4 final con silencedetect
        # y mapear cada silencio remanente al INPUT con las palabras vecinas
        # del transcript. Esto da feedback "between 'palabra1' y 'palabra2'"
        # imprescindible para iterar.
        if bool(config.get("post_audit_enabled", True)):
            ctx.on_progress(0.97, "🔬 Auditoría post-render…")

            def _full_audit(
                kints: list[tuple[float, float]],
                audit_path: str | None = None,
            ) -> dict:
                """Audit acústico + AUDIT PROFUNDO (re-transcribe el RESULTADO
                y lo compara token a token contra lo esperado). Devuelve el
                dict de audit con el score ya ajustado.

                `audit_path` permite auditar un render CANDIDATO (p. ej. el tmp
                de una auto-corrección) sin haberlo movido aún a `output_path`,
                para decidir si mejora ANTES de reemplazar el render bueno."""
                ap = audit_path or output_path
                audit = _post_render_audit(
                    ap,
                    keep_intervals=kints,
                    words=words,
                    stretched_spans=stretched_spans,
                )
                # RESIDUO SIN VOZ: tramos conservados que no contienen palabra
                # hablada (dead-air/tos/chasquido que sobrevivió). El juez no lo
                # medía → un 100 podía traer basura visible ('empieza tarde sin
                # nada' / '1s al final'). Baja el score (borde pesa más); el gate
                # <90 decide retención si suman. NO retiene por sí solo un caso
                # leve interior.
                try:
                    n_res, res_edge, res_prev = _count_residue_islands(
                        kints, voiced_words or words,
                    )
                    audit["n_residue_islands"] = n_res
                    audit["residue_head_tail"] = res_edge
                    audit["residue_preview"] = res_prev[:5]
                    if n_res and isinstance(audit.get("quality_score"), int):
                        penalty = 5 * n_res + (5 if res_edge else 0)
                        audit["quality_score"] = max(0, audit["quality_score"] - penalty)
                        audit["verdict"] = _verdict_for_score(audit["quality_score"])
                        for r in res_prev[:3]:
                            ctx.on_log(
                                f"[silence_cutter] 🚮 residuo sin voz conservado "
                                f"[{r['start']:.2f}-{r['end']:.2f}]s "
                                f"({'borde' if r['edge'] else 'interior'})"
                            )
                except Exception:  # noqa: BLE001
                    pass
                if (
                    bool(config.get("deep_audit_enabled", True))
                    and words and kints
                    and audit.get("transcription_ok", True)
                ):
                    ctx.on_progress(0.985, "🔬 Audit profundo: re-transcribiendo el resultado…")
                    try:
                        deep = _deep_audit_compare(
                            ap,
                            words=words,
                            keep_intervals=kints,
                            language=config.get("ai_language", "es"),
                            model_size=config.get("whisper_model_size", "large-v3"),
                            cpu_threads=int(config.get("whisper_cpu_threads", 1)),
                            log=ctx.on_log,
                        )
                        audit["deep"] = deep
                        n_ins = len(deep.get("inserted_blocks", []) or [])
                        n_mis = len(deep.get("missing_blocks", []) or [])
                        nfallos = n_ins + n_mis
                        audit["n_word_fallos"] = nfallos
                        if audit.get("quality_score") is not None:
                            new_score = max(0, int(audit["quality_score"]) - 8 * nfallos)
                            audit["quality_score"] = new_score
                            # CLAVE: cualquier fallo de PALABRA (sobrante/perdida)
                            # marca needs_requeue → NO se entrega aunque el score
                            # quede ≥90 (un solo fallo deja 92 y antes pasaba el
                            # filtro). Los silencios NO marcan esto: son tolerables.
                            audit["needs_requeue"] = (
                                bool(audit.get("needs_requeue")) or nfallos > 0
                            )
                            audit["verdict"] = _verdict_for_score(new_score)
                        if nfallos:
                            for b in (deep.get("inserted_blocks") or [])[:3]:
                                ctx.on_log(
                                    f"[silence_cutter] 🚩 audit profundo: audio SOBRANTE "
                                    f"'{b.get('text')}' (~{b.get('output_t')}s del output)"
                                )
                            for b in (deep.get("missing_blocks") or [])[:3]:
                                ctx.on_log(
                                    f"[silence_cutter] 🚩 audit profundo: palabra PERDIDA "
                                    f"'{b.get('text')}'"
                                )
                        else:
                            ctx.on_log(
                                "[silence_cutter] 🔬 Audit profundo: el resultado dice "
                                "exactamente lo que debía — sin residuos ni pérdidas."
                            )
                    except Exception as e:  # noqa: BLE001
                        audit["deep"] = {"error": f"{type(e).__name__}: {e}"}
                        ctx.on_log(f"[silence_cutter] ⚠️ Audit profundo falló (no bloquea): {e}")

                # 10b-bis) JUEZ DE COHERENCIA — ¿el render SIGUE teniendo sentido?
                # Compara el ORIGINAL con la transcripción real del render (la del
                # audit profundo, coste Whisper 0). El score se pliega con min():
                # solo puede BAJAR → un 100 significa que pasó acústico + palabras
                # + SENTIDO. Es la pasada que convierte el 100 en una nota fiable.
                if (
                    bool(config.get("ai_coherence_judge_enabled", True))
                    and isinstance(audit.get("deep"), dict)
                    and audit["deep"].get("out_text")
                ):
                    ctx.on_progress(0.986, "🧠 Coherencia IA: ¿sigue teniendo sentido?…")
                    try:
                        coh = _ai_coherence_judge(
                            words=words, deep=audit["deep"], keep_intervals=kints,
                            language=config.get("ai_language", "es"), log=ctx.on_log,
                            call_budget=coherence_budget, config=config,
                        )
                    except Exception as e:  # noqa: BLE001
                        coh = {"error": f"{type(e).__name__}: {e}"}
                        ctx.on_log(f"[silence_cutter] ⚠️ Coherencia falló (no bloquea): {e}")
                    if isinstance(coh.get("coherence_score"), int):
                        cs = int(coh["coherence_score"])
                        audit["coherence_score"] = cs
                        audit["coherence_issues"] = coh.get("defects", [])
                        audit["coherence_needs_requeue"] = bool(coh.get("coherence_needs_requeue"))
                        audit["coherence_fallos"] = int(coh.get("coherence_fallos", 0) or 0)
                        if isinstance(audit.get("quality_score"), int):
                            audit["quality_score"] = min(audit["quality_score"], cs)
                            audit["needs_requeue"] = (
                                bool(audit.get("needs_requeue"))
                                or bool(coh.get("coherence_needs_requeue"))
                            )
                            audit["verdict"] = _verdict_for_score(audit["quality_score"])
                        for d in (coh.get("defects") or [])[:3]:
                            ctx.on_log(
                                f"[silence_cutter] 🚩 coherencia ({d.get('type')}): "
                                f"falta '{d.get('missing_text')}' — {d.get('why')}"
                            )
                # VEREDICTO EXPLICABLE — el operador ve QUÉ puntuó, no un número:
                # separa fallo real del motor (Contenido) de fuente bruta (Ritmo)
                # y de avisos de baja confianza (probables falsos positivos).
                try:
                    vd = _build_verdict_detail(audit)
                    audit["verdict_detail"] = vd
                    ctx.on_log(f"[silence_cutter] 📋 VEREDICTO: {vd['label']}")
                    ctx.on_log(
                        "[silence_cutter]    "
                        + "  ·  ".join(
                            f"{d['dim']}: {'✓' if d['ok'] else '⚠ ' + d['detail']}"
                            for d in vd["dimensions"]
                        )
                    )
                    for lc in vd["low_confidence"][:3]:
                        ctx.on_log(f"[silence_cutter]    ℹ️ {lc}")
                except Exception:  # noqa: BLE001
                    pass
                return audit

            # Presupuesto COMPARTIDO de llamadas al juez de coherencia (lista
            # mutable → visible en cada candidato del self-heal). Acota el coste.
            # Default con MARGEN: 1 (audit inicial) + N intentos de self-heal + 1,
            # para que el juez evalúe TODOS los candidatos (si se agota, un
            # candidato sin coherencia parecería 0 fallos y podría aceptarse mal).
            _heal_n = int(config.get("self_heal_max_attempts", 3))
            coherence_budget = [int(config.get("coherence_max_calls", _heal_n + 2))]
            audit = _full_audit(keep_intervals)
            diagnostic["audit"] = audit

            # 10c) AUTO-CORRECCIÓN — si el score no llega al objetivo, el
            # corrector convierte los hallazgos del audit en acciones
            # quirúrgicas (cortar el sobrante exacto / RESTAURAR lo perdido),
            # re-renderiza SOLO con ffmpeg (sin re-analizar, sin coste de API)
            # y re-audita. Máx N intentos; si no llega, queda retenido para
            # revisión humana (needs_requeue) — nunca se entrega algo malo.
            heal_target = int(config.get("self_heal_target_score", 95))
            heal_max = int(config.get("self_heal_max_attempts", 3))
            heal_hist: list[dict] = []
            # MEJOR render hasta ahora. `output_path` SIEMPRE contiene el mejor
            # render; cada candidato se renderiza a un tmp y se AUDITA ahí, y solo
            # se mueve a output_path si MEJORA el score. Así el self-heal nunca
            # entrega algo peor que el render original (antes encadenaba sobre la
            # versión dañada y podía bajar 89→59→68).
            best_keeps = list(keep_intervals)
            best_audit = audit
            best_score = (
                audit.get("quality_score")
                if isinstance(audit.get("quality_score"), int) else None
            )
            if (
                bool(config.get("self_heal_enabled", True)) and words
                and best_score is not None
            ):
                tried_kinds: set[str] = set()
                while (
                    len(heal_hist) < heal_max
                    and (
                        best_score < heal_target
                        or _count_word_fallos(best_audit) > 0
                        or _count_coherence_fallos(best_audit) > 0
                    )
                    and best_audit.get("transcription_ok", True)
                ):
                    residue_cuts, guarded_cuts, restores = _derive_self_heal_actions(
                        best_audit, keep_intervals=best_keeps,
                    )
                    cut_actions = guarded_cuts + residue_cuts
                    # Escalado por seguridad: 1º solo CORTES (quitan sobrante /
                    # silencio — casi nunca dañan), luego RESTAURACIONES (devolver
                    # sobre-corte — arriesgado: puede reintroducir silencio), y al
                    # final ambos. Cada set se prueba como mucho una vez.
                    cand = None
                    if cut_actions and "cortes" not in tried_kinds:
                        cand = ("cortes", "cortes", residue_cuts, guarded_cuts, [])
                    elif restores and "restauracion" not in tried_kinds:
                        cand = ("restauracion", "restauración", [], [], restores)
                    elif cut_actions and restores and "ambos" not in tried_kinds:
                        cand = ("ambos", "cortes+restauración", residue_cuts, guarded_cuts, restores)
                    if cand is None:
                        ctx.on_log(
                            "[silence_cutter] 🩹 Auto-corrección: sin más acciones "
                            "que probar → queda para revisión humana."
                        )
                        break
                    key, kind, r_cuts_a, g_cuts_a, restores_a = cand
                    tried_kinds.add(key)
                    attempt = len(heal_hist) + 1
                    ctx.on_progress(0.985, f"🩹 Auto-corrección {attempt}/{heal_max} ({kind})…")
                    for s, e, why in (r_cuts_a + g_cuts_a + restores_a)[:6]:
                        ctx.on_log(f"[silence_cutter] 🩹 {why} → input[{s:.2f}, {e:.2f}]")
                    new_keeps = _union_intervals(
                        best_keeps, [(s, e) for s, e, _ in restores_a],
                    )
                    gcuts = [(s, e) for s, e, _ in g_cuts_a]
                    if gcuts and voiced_words:
                        gcuts = _protect_word_boundaries(gcuts, voiced_words, _WORD_GUARD_S)
                    rcuts = [(s, e) for s, e, _ in r_cuts_a]
                    new_keeps = _subtract_intervals(new_keeps, gcuts + rcuts)
                    new_keeps, _ab = _absorb_keep_islands(
                        new_keeps, voiced_words or words, min_keep_s=min_keep_island_s,
                    )
                    new_keeps = [
                        (a, b) for a, b in new_keeps if (b - a) >= _MIN_KEEP_SEGMENT_S
                    ]
                    new_keeps = _snap_keeps_to_words(new_keeps, voiced_words or words)
                    # Misma higiene de bordes que el flujo principal: sin
                    # palabras colgadas ni colas sub-palabra en los re-cortes,
                    # y el cierre del vídeo siempre en pausa real.
                    new_keeps, _ff = _complete_final_phrase(
                        new_keeps, voiced_words or words,
                    )
                    new_keeps, _nd = _trim_dangling_tail_words(
                        new_keeps, voiced_words or words,
                    )
                    try:
                        if os.path.exists(tmp_audio):
                            new_keeps, _nv = _refine_keep_edges_to_valley(
                                new_keeps, voiced_words or words, tmp_audio,
                            )
                    except Exception:  # noqa: BLE001
                        pass
                    # Re-extender la cola de la última palabra: _snap_keeps_to_words
                    # (arriba) la recorta al fin de palabra de Whisper, que sub-
                    # reporta la fricativa final. Igual que el render principal, la
                    # recuperamos por energía — si no, el render del self-heal (que
                    # PISA al principal cuando mejora el score) clipa "cuentas"→
                    # "cuento". Esta era la pieza que faltaba.
                    if bool(config.get("extend_last_word_tail", True)):
                        new_keeps = _extend_last_keep_to_word_tail(
                            new_keeps, tmp_audio, video_duration
                        )
                    kept_now = sum(b - a for a, b in new_keeps)
                    kept_before = sum(b - a for a, b in best_keeps)
                    if not new_keeps or kept_now < max(3.0, 0.25 * kept_before):
                        ctx.on_log(
                            "[silence_cutter] 🩹 Auto-corrección: este set recortaría "
                            "demasiado → lo descarto y pruebo otro."
                        )
                        heal_hist.append({
                            "attempt": attempt, "kind": kind, "accepted": False,
                            "score_before": best_score, "score_after": None,
                            "reason": "abort_recorte",
                            "n_residue_cuts": len(rcuts), "n_guarded_cuts": len(gcuts),
                            "n_restores": len(restores_a),
                            "actions": [w for _, _, w in (r_cuts_a + g_cuts_a + restores_a)][:8],
                        })
                        continue
                    # Render del CANDIDATO a tmp — NO toca el mejor render todavía.
                    tmp_out = output_path + ".heal.mp4"
                    try:
                        _apply_cuts_ffmpeg(
                            input_path=input_path,
                            output_path=tmp_out,
                            keep_intervals=new_keeps,
                            rotation=video_rotation,
                            output_aspect=config.get("output_aspect", "9:16"),
                            log=ctx.on_log,
                            on_progress=lambda f: ctx.on_progress(
                                0.985, f"🩹 Re-render corrección {attempt}…",
                            ),
                            normalize_audio=normalize_audio,
                            content_end_s=_content_end_output_s(new_keeps, tmp_audio),
                        )
                    except Exception as e:  # noqa: BLE001
                        try:
                            os.remove(tmp_out)
                        except OSError:
                            pass
                        ctx.on_log(
                            f"[silence_cutter] ⚠️ Auto-corrección: re-render falló "
                            f"({e}); conservo el mejor render."
                        )
                        break
                    # Audita el candidato (tmp). PRIORIDAD: eliminar fallos de
                    # PALABRA (sobrantes/perdidas) — es lo GRAVE. Un silencio de
                    # más es tolerable. Por eso aceptamos el candidato si REDUCE
                    # los fallos de palabra AUNQUE el score total baje un poco
                    # (restaurar una palabra perdida puede dejar un mini-silencio);
                    # a igualdad de fallos de palabra, preferimos mayor score.
                    prev_best = best_score
                    prev_fallos = _count_word_fallos(best_audit)
                    cand_audit = _full_audit(new_keeps, audit_path=tmp_out)
                    cand_score = cand_audit.get("quality_score")
                    cand_fallos = _count_word_fallos(cand_audit)
                    # Clave LEXICOGRÁFICA (menor = mejor): 1º fallos de SENTIDO,
                    # 2º fallos de PALABRA, 3º score. Restaurar una promesa rota
                    # (coherencia) manda sobre todo; a igualdad, menos fallos de
                    # palabra; a igualdad, mayor score. Sigue siendo monótono.
                    def _qkey(a: dict) -> tuple:
                        return (
                            _count_coherence_fallos(a),
                            _count_word_fallos(a),
                            -(a.get("quality_score") or 0),
                        )
                    accepted = isinstance(cand_score, int) and _qkey(cand_audit) < _qkey(best_audit)
                    salvaged = False
                    # SALVAGE (restaurar-palabra): el lote de limpieza SUBIÓ el
                    # score pero clipó UNA palabra de contenido (la perdió en un
                    # borde de keep — sea por el corte o por la higiene snap/valle).
                    # En vez de tirar TODO el lote, RESTAURA el span exacto de las
                    # palabras perdidas a los keeps del candidato (mantiene los N
                    # silencios cortados; sólo des-clipa la palabra). Re-renderiza
                    # y sólo reemplaza si queda estrictamente mejor (misma clave
                    # _qkey) → nunca empeora, sólo cuesta un render extra.
                    if (
                        not accepted and isinstance(cand_score, int)
                        and (cand_score - best_score) >= _SALVAGE_MIN_GAIN
                        and (
                            _count_word_fallos(cand_audit) > _count_word_fallos(best_audit)
                            or _count_coherence_fallos(cand_audit) > _count_coherence_fallos(best_audit)
                        )
                    ):
                        # Spans a RESTAURAR (input time): palabras perdidas del audit
                        # profundo + promesas rotas del juez de coherencia (restore_span).
                        miss_spans = [
                            (float(m["input_start"]), float(m["input_end"]))
                            for m in ((cand_audit.get("deep") or {}).get("missing_blocks") or [])
                            if m.get("input_start") is not None and m.get("input_end") is not None
                        ]
                        for _d in (cand_audit.get("coherence_issues") or []):
                            _rs = _d.get("restore_span")
                            if isinstance(_rs, (list, tuple)) and len(_rs) == 2:
                                try:
                                    miss_spans.append((float(_rs[0]), float(_rs[1])))
                                except (TypeError, ValueError):
                                    pass
                        # Spans de RESIDUO a cortar (audio sobrante): inserted_blocks
                        # del audit profundo, mapeados de tiempo de OUTPUT a INPUT.
                        ins_cut_spans: list[tuple[float, float]] = []
                        for _b in ((cand_audit.get("deep") or {}).get("inserted_blocks") or []):
                            _ot, _oe = _b.get("output_t"), _b.get("output_t_end")
                            if _ot is None or _oe is None:
                                continue
                            try:
                                _is = _map_output_to_input(float(_ot), new_keeps)
                                _ie = _map_output_to_input(float(_oe), new_keeps)
                            except (TypeError, ValueError):
                                _is = _ie = None
                            if _is is not None and _ie is not None and _ie > _is:
                                ins_cut_spans.append((_is, _ie))
                        ctx.on_log(
                            f"[silence_cutter] 🩹 Salvage: candidato {best_score}→{cand_score} · "
                            f"{len(miss_spans)} span(s) a restaurar · {len(ins_cut_spans)} residuo(s) "
                            f"a cortar. Intento conservar la limpieza…"
                        )
                        if miss_spans or ins_cut_spans:
                            # Restaura lo perdido + corta el residuo sobre los keeps del
                            # CANDIDATO — no re-aplico snap/valle (es lo que clipa); sólo
                            # merge/resta + re-extiendo la cola final.
                            pad = _WORD_GUARD_S
                            salv_keeps = _union_intervals(
                                new_keeps, [(ms - pad, me + pad) for ms, me in miss_spans],
                            )
                            if ins_cut_spans:
                                _safe_cuts = ins_cut_spans
                                if voiced_words:
                                    _safe_cuts = _protect_word_boundaries(
                                        _safe_cuts, voiced_words, _WORD_GUARD_S,
                                    )
                                salv_keeps = _subtract_intervals(salv_keeps, _safe_cuts)
                            salv_keeps = [
                                (a, b) for a, b in salv_keeps if (b - a) >= _MIN_KEEP_SEGMENT_S
                            ]
                            if bool(config.get("extend_last_word_tail", True)):
                                salv_keeps = _extend_last_keep_to_word_tail(
                                    salv_keeps, tmp_audio, video_duration,
                                )
                            kept_salv = sum(b - a for a, b in salv_keeps)
                            if salv_keeps and kept_salv >= max(3.0, 0.25 * kept_before):
                                tmp_out2 = output_path + ".salv.mp4"
                                try:
                                    _apply_cuts_ffmpeg(
                                        input_path=input_path,
                                        output_path=tmp_out2,
                                        keep_intervals=salv_keeps,
                                        rotation=video_rotation,
                                        output_aspect=config.get("output_aspect", "9:16"),
                                        log=ctx.on_log,
                                        on_progress=lambda f: ctx.on_progress(
                                            0.985, f"🩹 Salvage corrección {attempt}…",
                                        ),
                                        normalize_audio=normalize_audio,
                                        content_end_s=_content_end_output_s(salv_keeps, tmp_audio),
                                    )
                                    salv_audit = _full_audit(salv_keeps, audit_path=tmp_out2)
                                    salv_score = salv_audit.get("quality_score")
                                    if (
                                        isinstance(salv_score, int)
                                        and _qkey(salv_audit) < _qkey(best_audit)
                                    ):
                                        try:
                                            os.remove(tmp_out)
                                        except OSError:
                                            pass
                                        tmp_out = tmp_out2
                                        new_keeps = salv_keeps
                                        cand_audit = salv_audit
                                        cand_score = salv_score
                                        cand_fallos = _count_word_fallos(salv_audit)
                                        accepted = True
                                        salvaged = True
                                        ctx.on_log(
                                            f"[silence_cutter] 🩹✅ Salvage: restauré "
                                            f"{len(miss_spans)} palabra(s) y conservé la limpieza "
                                            f"→ score {best_score}→{cand_score}/100, "
                                            f"fallos_palabra {cand_fallos}."
                                        )
                                    else:
                                        try:
                                            os.remove(tmp_out2)
                                        except OSError:
                                            pass
                                        ctx.on_log(
                                            f"[silence_cutter] 🩹 Salvage sin éxito "
                                            f"(quedó {salv_score}); conservo el mejor."
                                        )
                                except Exception as e:  # noqa: BLE001
                                    try:
                                        os.remove(tmp_out2)
                                    except OSError:
                                        pass
                                    ctx.on_log(
                                        f"[silence_cutter] ⚠️ Salvage: re-render falló "
                                        f"({e}); conservo el mejor render."
                                    )
                    if accepted:
                        os.replace(tmp_out, output_path)
                        best_keeps, best_audit, best_score = new_keeps, cand_audit, cand_score
                        diagnostic["audit"] = best_audit
                        # La pasada hizo progreso → el audit cambió y quedan
                        # hallazgos NUEVOS (p. ej. silencios que antes no eran los
                        # findings top). Re-habilita CORTES para que una pasada más
                        # (acotada por heal_max) los limpie. Solo tras ACEPTAR →
                        # best_audit ya es distinto, así que no se re-deriva idéntico
                        # y no hay bucle. Si se rechaza, 'cortes' sigue marcado.
                        tried_kinds.discard("cortes")
                        tried_kinds.discard("ambos")
                        ctx.on_log(
                            f"[silence_cutter] 🩹 Corrección ACEPTADA ({kind}): "
                            f"fallos_palabra {prev_fallos}→{cand_fallos} · "
                            f"score {prev_best}→{cand_score}/100"
                        )
                    else:
                        try:
                            os.remove(tmp_out)
                        except OSError:
                            pass
                        ctx.on_log(
                            f"[silence_cutter] 🩹 Corrección DESCARTADA ({kind}): "
                            f"fallos_palabra {prev_fallos}→{cand_fallos} · "
                            f"score {prev_best}→{cand_score} — conservo el mejor."
                        )
                    heal_hist.append({
                        "attempt": attempt, "kind": kind + ("+salvage" if salvaged else ""),
                        "accepted": accepted, "salvaged": salvaged,
                        "score_before": prev_best, "score_after": cand_score,
                        "word_fallos_before": prev_fallos, "word_fallos_after": cand_fallos,
                        "n_residue_cuts": len(rcuts), "n_guarded_cuts": len(gcuts),
                        "n_restores": len(restores_a),
                        "actions": [w for _, _, w in (r_cuts_a + g_cuts_a + restores_a)][:8],
                    })
            # 10d) BARRIDO FINAL de FALSOS ARRANQUES sobre la transcripción del
            # OUTPUT. La pasada 2 corre sobre el input BRUTO y se le escapan
            # restarts borderline (caso "y esto empezó"); aquí re-usamos las
            # `out_words` que el audit profundo YA re-transcribió del RESULTADO —
            # donde el detector SÍ los caza — mapeamos a tiempo de INPUT con
            # _map_output_to_input, re-cortamos y re-auditamos. MONÓTONO: solo se
            # acepta si NO sube fallos de palabra ni de coherencia (quitar un
            # restart redundante no debe perder contenido ni romper el sentido;
            # si los sube, era contenido real → se descarta solo). Determinista
            # (gpt temp 0+seed). Generaliza: caza cualquier restart que escape.
            if (
                bool(config.get("false_start_output_sweep", True))
                and words and best_audit.get("transcription_ok", True)
            ):
                try:
                    _ow = ((best_audit.get("deep") or {}).get("out_words")) or []
                    _ow_words = [
                        {"idx": i, "word": w.get("word", ""),
                         "start": float(w.get("start", 0) or 0),
                         "end": float(w.get("end", 0) or 0)}
                        for i, w in enumerate(_ow)
                    ]
                    _fs_out, _ = (
                        _ai_false_starts_openai(
                            words=_ow_words, language=config.get("ai_language", "es"),
                            model=config.get("ai_model", "gpt-4o"), log=ctx.on_log,
                        ) if len(_ow_words) >= 4 else ([], None)
                    )
                    _in_cuts: list[tuple[float, float, str]] = []
                    for _o0, _o1, _raw in _fs_out:
                        _i0 = _map_output_to_input(float(_o0), best_keeps)
                        _i1 = _map_output_to_input(float(_o1), best_keeps)
                        if _i0 is not None and _i1 is not None and _i1 > _i0:
                            _in_cuts.append((_i0, _i1, (_raw or {}).get("first_attempt", "restart")))
                    if _in_cuts:
                        ctx.on_log(
                            f"[silence_cutter] 🧹 Barrido final: {len(_in_cuts)} falso(s) "
                            f"arranque(s) en el OUTPUT → recorto "
                            + " · ".join(f"'{w}'" for *_, w in _in_cuts)
                        )
                        _cuts = [(s, e) for s, e, _ in _in_cuts]
                        if voiced_words:
                            _cuts = _protect_word_boundaries(_cuts, voiced_words, _WORD_GUARD_S)
                        _sw_keeps = _subtract_intervals(list(best_keeps), _cuts)
                        _sw_keeps = [(a, b) for a, b in _sw_keeps if (b - a) >= _MIN_KEEP_SEGMENT_S]
                        _sw_keeps = _snap_keeps_to_words(_sw_keeps, voiced_words or words)
                        _sw_keeps, _ = _complete_final_phrase(_sw_keeps, voiced_words or words)
                        if bool(config.get("extend_last_word_tail", True)):
                            _sw_keeps = _extend_last_keep_to_word_tail(
                                _sw_keeps, tmp_audio, video_duration,
                            )
                        _kept_sw = sum(b - a for a, b in _sw_keeps)
                        _kept_bf = sum(b - a for a, b in best_keeps)
                        if _sw_keeps and _kept_sw >= max(3.0, 0.5 * _kept_bf):
                            _tmp_sw = output_path + ".fsweep.mp4"
                            try:
                                _apply_cuts_ffmpeg(
                                    input_path=input_path, output_path=_tmp_sw,
                                    keep_intervals=_sw_keeps, rotation=video_rotation,
                                    output_aspect=config.get("output_aspect", "9:16"),
                                    log=ctx.on_log,
                                    on_progress=lambda f: ctx.on_progress(
                                        0.99, "🧹 Barrido falsos arranques…"),
                                    normalize_audio=normalize_audio,
                                    content_end_s=_content_end_output_s(_sw_keeps, tmp_audio),
                                )
                                _sw_audit = _full_audit(_sw_keeps, audit_path=_tmp_sw)
                                # Cortar un restart "rephrase" deja sus palabras
                                # como "missing" en el audit profundo (no recurren).
                                # NO es pérdida real → no debe vetar el corte. La
                                # seguridad real es: (1) coherencia (sentido) no
                                # empeora, y (2) las palabras que ahora "faltan"
                                # caen DENTRO del trozo que quité (el restart). Si
                                # faltara algo FUERA del corte = pérdida real →
                                # rechazo.
                                def _missing_key(_m: dict) -> tuple:
                                    return (round(float(_m.get("input_start", 0) or 0), 1),
                                            round(float(_m.get("input_end", 0) or 0), 1))
                                _best_miss = {
                                    _missing_key(_m)
                                    for _m in ((best_audit.get("deep") or {}).get("missing_blocks") or [])
                                }

                                def _within_sweep(_m: dict) -> bool:
                                    _s0, _e0 = _m.get("input_start"), _m.get("input_end")
                                    if _s0 is None or _e0 is None:
                                        return False
                                    return any(
                                        cs - 0.35 <= float(_s0) and float(_e0) <= ce + 0.35
                                        for cs, ce, _ in _in_cuts
                                    )
                                _unexpected = [
                                    _m for _m in ((_sw_audit.get("deep") or {}).get("missing_blocks") or [])
                                    if _missing_key(_m) not in _best_miss and not _within_sweep(_m)
                                ]
                                _safe = (
                                    isinstance(_sw_audit.get("quality_score"), int)
                                    and not _unexpected
                                    and _count_coherence_fallos(_sw_audit) <= _count_coherence_fallos(best_audit)
                                    and bool(_sw_audit.get("transcription_ok", True))
                                )
                                if _safe:
                                    # El "missing" del restart es INTENCIONADO →
                                    # limpia el needs_requeue/score espurio que vino
                                    # solo de quitarlo (mantén coherencia como gate).
                                    _sw_audit["needs_requeue"] = bool(
                                        _sw_audit.get("coherence_needs_requeue")
                                    )
                                    _sw_audit["quality_score"] = max(
                                        int(_sw_audit.get("quality_score") or 0),
                                        int(best_score or 0),
                                    )
                                    _sw_audit["verdict"] = _verdict_for_score(_sw_audit["quality_score"])
                                    os.replace(_tmp_sw, output_path)
                                    best_keeps, best_audit = _sw_keeps, _sw_audit
                                    best_score = best_audit.get("quality_score")
                                    diagnostic["false_start_sweep"] = {
                                        "cut": [w for *_, w in _in_cuts],
                                    }
                                    ctx.on_log(
                                        "[silence_cutter] 🧹✅ Barrido: falso(s) arranque(s) "
                                        f"eliminado(s) del output ({', '.join(w for *_, w in _in_cuts)}) "
                                        "— sentido intacto, sin pérdida real."
                                    )
                                else:
                                    os.remove(_tmp_sw)
                                    ctx.on_log(
                                        "[silence_cutter] 🧹 Barrido DESCARTADO (rompería "
                                        "coherencia o perdería contenido fuera del restart)."
                                    )
                            except Exception as _e:  # noqa: BLE001
                                try:
                                    os.remove(_tmp_sw)
                                except OSError:
                                    pass
                                ctx.on_log(f"[silence_cutter] ⚠️ Barrido re-render falló: {_e}")
                except Exception as _e:  # noqa: BLE001
                    ctx.on_log(f"[silence_cutter] ⚠️ Barrido falsos arranques falló: {_e}")

            # El mejor render manda: refleja sus keeps/audit aguas abajo.
            keep_intervals = best_keeps
            audit = best_audit
            diagnostic["audit"] = audit

            # APRENDIZAJE: si tras todo quedó un defecto de SENTIDO confirmado y
            # grave, escríbelo como lección → el motor no lo repetirá en los
            # próximos vídeos (idempotente por fingerprint). Solo el 1º (anti-spam).
            for d in (audit.get("coherence_issues") or [])[:1]:
                if d.get("confirmed") and int(d.get("severity", 0) or 0) >= 2:
                    import hashlib
                    fp = hashlib.sha1(
                        (str(d.get("type", "")) + str(d.get("why", ""))[:60]).encode("utf-8")
                    ).hexdigest()[:12]
                    if _append_editor_lesson(
                        {"coherence", "clean_script", "completeness"},
                        f"No partir promesas tipo {d.get('type')}",
                        (
                            f"- El render decía «{d.get('rendered_quote')}» pero el original "
                            f"incluía «{d.get('missing_text') or d.get('original_quote')}» → "
                            f"rompe el sentido ({d.get('why')}). Regla: si una frase ANUNCIA "
                            f"una cantidad o lista (dos ingredientes, 3 trucos), conserva TODOS "
                            f"sus ítems o también el número; nunca dejes una promesa sin su "
                            f"contenido."
                        ),
                        fingerprint=fp,
                    ):
                        ctx.on_log(
                            f"[silence_cutter] 📚 Lección aprendida ({d.get('type')}) "
                            f"→ editor_lessons.md"
                        )
            if heal_hist:
                diagnostic["self_heal"] = {
                    "target": heal_target,
                    "attempts": len(heal_hist),
                    "history": heal_hist,
                }
                # Reflejar los keeps corregidos en final + proyecto editable
                diagnostic["final"]["n_keep_intervals"] = len(keep_intervals)
                diagnostic["final"]["kept_duration_s"] = round(
                    sum(b - a for a, b in keep_intervals), 3,
                )
                diagnostic["final"]["preview_keep_intervals"] = [
                    {"start": round(s, 3), "end": round(e, 3)}
                    for s, e in keep_intervals[:20]
                ]
                _write_edit_project(
                    ctx, input_path=input_path, words=words,
                    keep_intervals=keep_intervals, video_duration=video_duration,
                )
                ctx.on_log(
                    f"[silence_cutter] 🩹 Auto-corrección: {len(heal_hist)} intento(s) "
                    f"→ score final {audit.get('quality_score')}/100"
                )

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

        # Cleanup del audio temporal (se mantuvo vivo para el valle de bordes
        # del flujo principal y del self-heal).
        for _p in (tmp_audio, tmp_audio_vad):
            try:
                if _p and _p != input_path:
                    os.remove(_p)
            except OSError:
                pass

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
# Reparación de entrada — re-encode si el stream viene dañado
# ---------------------------------------------------------------------------
# Nº de errores de decode en una muestra que dispara el re-encode. Un vídeo
# sano da 0; uno con stream H264 roto (NAL inválidos) da decenas/cientos.
_CORRUPT_ERR_THRESHOLD = 8


def _count_decode_errors(input_path: str, *, sample_s: int = 30) -> int:
    """Decodifica los primeros `sample_s` s del vídeo (sin re-encodear, muxer
    null → rápido) y cuenta líneas de error de decode (NAL inválidos, frames
    corruptos). Sirve para detectar un stream dañado que haría el decode NO
    determinista (cortes/score distintos entre runs del MISMO vídeo)."""
    try:
        proc = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-v", "error",
                "-i", input_path, "-map", "0:v:0", "-t", str(sample_s),
                "-f", "null", "-",
            ],
            capture_output=True, text=True, timeout=180,
        )
    except Exception:  # noqa: BLE001
        return 0
    err = proc.stderr or ""
    keys = (
        "NAL", "Error splitting", "corrupt", "missing picture",
        "Invalid data", "decode_slice", "concealing",
    )
    return sum(1 for ln in err.splitlines() if any(k in ln for k in keys))


def _repair_corrupt_input(
    input_path: str, temp_folder: str, job_id: str, log,
) -> str:
    """Si la entrada trae el stream de vídeo dañado, la re-encodea a un H264
    LIMPIO para que Whisper, los cortes y el audit sean fiables y
    REPRODUCIBLES. Los vídeos sanos NO se tocan (devuelve el path original) →
    cero impacto en los casos que ya funcionan.

    Orientación: re-encodea con el autorotate por defecto de ffmpeg (hornea la
    rotación → vídeo ya derecho) y limpia la metadata `rotate`. Aguas abajo
    `_ffprobe_meta` leerá rotation=0 y lo tratará como derecho → MISMA
    orientación final que el flujo original (que también deja el frame
    físicamente rotado)."""
    n_err = _count_decode_errors(input_path)
    if n_err <= _CORRUPT_ERR_THRESHOLD:
        return input_path
    log(
        f"[silence_cutter] 🩺 Entrada con stream dañado (~{n_err} errores de "
        f"decode en 30s) → re-encode a H264 limpio para edición fiable."
    )
    clean = os.path.join(temp_folder, f"editor_clean_{job_id}.mp4")
    cmd = [
        "ffmpeg", "-y", "-hide_banner",
        "-fflags", "+genpts", "-err_detect", "ignore_err",
        "-i", input_path,
        *_video_encoder_args(),
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-metadata:s:v:0", "rotate=0",
        clean,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        ok = (
            proc.returncode == 0
            and os.path.exists(clean)
            and os.path.getsize(clean) > 10_000
        )
        if not ok:
            log(
                f"[silence_cutter] ⚠️ Reparación de entrada falló "
                f"(rc={proc.returncode}) → uso el original."
            )
            try:
                if os.path.exists(clean):
                    os.remove(clean)
            except OSError:
                pass
            return input_path
        log("[silence_cutter] 🩺 Entrada reparada → editando sobre versión limpia.")
        return clean
    except Exception as e:  # noqa: BLE001
        log(f"[silence_cutter] ⚠️ Reparación de entrada lanzó {e} → uso el original.")
        return input_path


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


def _level_audio(src: str, dst: str, *, log=None) -> bool:
    """Normaliza la loudness (EBU R128 `loudnorm`) para que la voz BAJA llegue
    al nivel que esperan Silero VAD y Whisper.

    En grabaciones de mala SNR (creadora hablando flojo + ruido de sala) Silero
    marca SILENCIO donde hay habla y Whisper le pone timestamps malos → palabras
    reales ('proteína') se pierden. loudnorm sube TODA la pista por igual: la voz
    floja se vuelve audible para los modelos SIN degradar la relación señal/ruido
    ni inflar los silencios (la detección de silencios sigue sobre el original).
    Devuelve True si generó `dst` válido."""
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src,
                "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                "-ar", "16000", "-ac", "1", dst,
            ],
            check=True, timeout=300,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return os.path.exists(dst) and os.path.getsize(dst) > 1024
    except Exception as e:  # noqa: BLE001
        if log:
            log(f"[silence_cutter] ⚠️ Nivelado de audio falló ({e}) → uso original")
        return False


def _transcribe_deepgram(
    audio_path: str, *, language: str = "es", model: str = "nova-2",
) -> list[dict]:
    """Transcribe con Deepgram (timestamps por palabra más precisos que Whisper
    en audio ruidoso). Devuelve el MISMO formato que `_transcribe`:
    [{word, start, end}]. Requiere `DEEPGRAM_API_KEY`. Lanza si falla → el
    caller cae a Whisper. Audio nivelado 16k mono (mismo pre-proceso)."""
    import json
    import tempfile
    import urllib.request
    key = os.getenv("DEEPGRAM_API_KEY", "").strip()
    if not key:
        raise RuntimeError("DEEPGRAM_API_KEY no configurada")
    wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", audio_path,
             "-ac", "1", "-ar", "16000", "-vn", wav],
            check=True, timeout=180,
        )
        payload = open(wav, "rb").read()
    finally:
        try:
            os.remove(wav)
        except OSError:
            pass
    url = (
        f"https://api.deepgram.com/v1/listen?model={model}&language={language}"
        "&punctuate=true&smart_format=true"
    )
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Authorization": f"Token {key}", "Content-Type": "audio/wav"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        resp = json.load(r)
    words = (
        resp.get("results", {}).get("channels", [{}])[0]
        .get("alternatives", [{}])[0].get("words", [])
    )
    out: list[dict] = []
    for w in words:
        out.append({
            "word": str(w.get("punctuated_word") or w.get("word", "")),
            "start": float(w.get("start", 0.0)),
            "end": float(w.get("end", 0.0)),
        })
    return out


def _transcribe(
    audio_path: str, *, model_size: str, language: str, on_progress,
    timeout_s: int = 1200, fallback_model: str = "small",
    primary_threads: int = 4,
) -> list[dict]:
    """Transcribe con Whisper, robusto a deadlocks de ctranslate2.

    A/B de ASR: si `EDITOR_ASR_PROVIDER=deepgram` (+ `DEEPGRAM_API_KEY`), usa
    Deepgram (timestamps más limpios). Por defecto 'whisper' → producción intacta.
    Si Deepgram falla, cae a Whisper (nunca rompe el job).

    El deadlock de ctranslate2/int8 en CPU es FLAKY (a veces cuelga, a veces
    no, con el MISMO audio) y más probable con MÁS hilos. Estrategia de
    ESCALADO de hilos (rápido->seguro->ligero):
      1) large-v3 a `primary_threads` hilos -> RÁPIDO (multi-core).
      2) Si el watchdog lo mata por deadlock, reintenta large-v3 a 1 HILO ->
         más lento pero casi nunca se cuelga; conserva la calidad del modelo.
      3) Si aún cuelga, cae a `fallback_model` (small) a 1 hilo -> garantizado.
    El watchdog por inactividad de CPU detecta el cuelgue en ~2-3min (no espera
    el timeout entero), así que el escalado no cuesta 20min por intento.
    """
    if os.getenv("EDITOR_ASR_PROVIDER", "whisper").strip().lower() == "deepgram":
        try:
            dg = _transcribe_deepgram(audio_path, language=language)
            if dg:
                return dg
        except Exception:  # noqa: BLE001 — cualquier fallo → fallback a Whisper
            pass

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
    # `max_interrupt`: nº de palabras que pueden ir ENTRE las dos copias del
    # n-grama y aun así contar como restart. Cubre el caso "aprovecha que ahora
    # ESTÁN aprovecha que ahora estamos" (1 palabra interpuesta) — un re-take
    # típico que el ngram inmediato (0 interpuestas) se dejaba.
    max_interrupt = 2
    for n in range(max_n, min_n - 1, -1):
        i = 0
        while i <= len(words) - 2 * n:
            if any(j in used for j in range(i, i + n)):
                i += 1
                continue
            gram_a = normalized[i : i + n]
            if not all(g for g in gram_a):  # n-grama con palabra vacía → skip
                i += 1
                continue
            matched = False
            for k in range(0, max_interrupt + 1):  # k palabras interpuestas
                b0 = i + n + k
                if b0 + n > len(words):
                    break
                if any(j in used for j in range(i, b0 + n)):
                    continue
                if normalized[b0 : b0 + n] != gram_a:
                    continue
                # Gap temporal entre fin de la 1ª copia y arranque de la 2ª
                # (incluye las palabras interpuestas) — pequeño = re-take real.
                t_a_end = float(words[i + n - 1]["end"])
                t_b_start = float(words[b0]["start"])
                if t_b_start - t_a_end > max_gap_between_grams_s:
                    continue
                # Cortar el PRIMER intento + las palabras interpuestas [i .. b0-1];
                # conservar la 2ª copia (la buena).
                cuts.append({
                    "start_word_idx": i,
                    "end_word_idx": b0 - 1,
                    "kind": "ngram_restart",
                    "first_attempt": " ".join(words[j]["word"] for j in range(i, b0)),
                    "kept_version": " ".join(
                        words[j]["word"] for j in range(b0, b0 + n)
                    ),
                    "reason": f"N-grama de {n} repetido (restart, {k} interpuestas)",
                    "n": n,
                })
                for j in range(i, b0 + n):
                    used.add(j)
                i = b0 + n
                matched = True
                break
            if not matched:
                i += 1
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
_HOLISTIC_MODEL = "gpt-5.4"  # ganador A/B: corta mejor los restarts que gpt-4o, y mas barato
_HOLISTIC_SEED = 7

# Juez de COHERENCIA (pasada final de sentido): mismo modelo/seed deterministas.
_COHERENCE_MODEL = _HOLISTIC_MODEL
_COHERENCE_SEED = _HOLISTIC_SEED
# Penalización del score por severidad del defecto de sentido (1=leve … 3=grave).
_COH_SEV_PENALTY = {1: 4, 2: 12, 3: 25}
# Pistas de ENUMERACIÓN/cantidad: si una de estas queda pegada a un corte, puede
# haberse roto una "promesa" (dice 'dos ingredientes' y nombra uno) → activa juez.
_COH_LIST_HINTS = frozenset({
    "dos", "tres", "cuatro", "cinco", "primero", "segundo", "tercero", "razones",
    "trucos", "ingredientes", "pasos", "motivos", "cosas", "tipos", "formas",
    "claves", "consejos", "ventajas", "beneficios", "errores", "secretos",
})

# ---------------------------------------------------------------------------
# Memoria de LECCIONES del motor de edición
# ---------------------------------------------------------------------------
# `prompts/editor_lessons.md` es la memoria VIVA del motor: errores reales
# observados en vídeos de clientes, escritos como reglas para la IA. Cada
# sección `##` lleva etiquetas `[pasada1|pasada2]` y SOLO se inyecta en esas
# pasadas (clean_script / analyst / false_starts / completeness) — así el
# coste y el ruido no crecen linealmente con la memoria: cada pasada recibe
# únicamente sus lecciones, con un CAP duro. El preámbulo (antes de la
# primera `##`) es para humanos y NUNCA se envía. Además, como las lecciones
# van pegadas al system prompt (prefijo estable, payload variable en el user
# message), el prompt-caching automático de OpenAI descuenta ~50% de esos
# tokens en llamadas repetidas. Al descubrir un fallo nuevo: (1) si es
# codificable, regla determinista en este .py; (2) SIEMPRE, lección corta en
# editor_lessons.md; (3) consolidar lecciones parecidas cuando el cap avise.
_LESSONS_CACHE: tuple[float, list[tuple[set, str]]] | None = None
_LESSONS_MAX_CHARS = 6000  # cap por pasada (~1500 tokens) — avisa si se supera


def _load_editor_lessons(pass_id: str) -> str:
    """Lecciones relevantes para la pasada `pass_id`, cap aplicado."""
    global _LESSONS_CACHE
    p = Path(__file__).resolve().parent.parent / "prompts" / "editor_lessons.md"
    try:
        mt = p.stat().st_mtime
    except OSError:
        return ""
    if _LESSONS_CACHE is None or _LESSONS_CACHE[0] != mt:
        try:
            txt = p.read_text(encoding="utf-8")
        except OSError:
            return ""
        sections: list[tuple[set, str]] = []
        cur_tags: set | None = None
        cur_lines: list[str] = []
        for line in txt.splitlines():
            if line.startswith("## "):
                if cur_tags is not None:
                    sections.append((cur_tags, "\n".join(cur_lines).strip()))
                m = re.search(r"\[([a-z_|]+)\]\s*$", line)
                cur_tags = set(m.group(1).split("|")) if m else set()
                cur_lines = [re.sub(r"\s*\[[a-z_|]+\]\s*$", "", line)]
            elif cur_tags is not None:
                cur_lines.append(line)
            # líneas antes de la primera `##` = preámbulo humano → no se envía
        if cur_tags is not None:
            sections.append((cur_tags, "\n".join(cur_lines).strip()))
        _LESSONS_CACHE = (mt, sections)
    out: list[str] = []
    total = 0
    skipped = 0
    for tags, body in _LESSONS_CACHE[1]:
        if tags and pass_id not in tags:
            continue
        if total + len(body) > _LESSONS_MAX_CHARS:
            skipped += 1
            continue
        out.append(body)
        total += len(body)
    if skipped:
        print(
            f"[silence_cutter] ⚠️ editor_lessons.md supera el cap para "
            f"'{pass_id}' ({skipped} sección(es) fuera) — CONSOLIDAR lecciones."
        )
    if not out:
        return ""
    return (
        "# LECCIONES APRENDIDAS (errores reales en vídeos de clientes — "
        "cúmplelas siempre)\n\n" + "\n\n".join(out)
    )


def _with_lessons(system_prompt: str, pass_id: str) -> str:
    """Añade al system prompt SOLO las lecciones de la pasada `pass_id`."""
    lessons = _load_editor_lessons(pass_id)
    if not lessons:
        return system_prompt
    return system_prompt.rstrip() + "\n\n---\n\n" + lessons


def _append_editor_lesson(
    pass_ids: set[str], title: str, content: str, *, fingerprint: str,
) -> bool:
    """APRENDIZAJE: añade una lección nueva a `editor_lessons.md` para que el
    motor NO repita el fallo en los próximos vídeos. Idempotente por
    `fingerprint` (un marcador HTML al final) → nunca duplica ni infla el cap.

    Escritura ATÓMICA (temp + os.replace; NTFS no tiene rename atómico a mitad
    de escritura), utf-8 explícito, lock best-effort. Invalida la caché de
    lecciones tras escribir. Best-effort: nunca rompe el job. Devuelve True si
    escribió una lección nueva."""
    global _LESSONS_CACHE
    import hashlib  # noqa: F401  (usado por el caller para el fingerprint)
    p = Path(__file__).resolve().parent.parent / "prompts" / "editor_lessons.md"
    marker = f"<!-- coh:fp:{fingerprint} -->"
    lock = p.with_suffix(".md.lock")
    fd = None
    try:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False  # otro proceso está escribiendo → no insistir
        try:
            txt = p.read_text(encoding="utf-8")
        except OSError:
            return False
        if marker in txt:
            return False  # ya aprendida → dedup
        tags = "|".join(sorted(pass_ids))
        block = (
            f"\n\n## Coherencia: {title} [{tags}]\n\n{content.strip()}\n{marker}\n"
        )
        new_txt = txt.rstrip() + block
        tmp = p.with_suffix(".md.tmp")
        tmp.write_text(new_txt, encoding="utf-8")
        os.replace(str(tmp), str(p))
        _LESSONS_CACHE = None  # fuerza recarga en el próximo job
        return True
    except Exception:  # noqa: BLE001
        return False
    finally:
        if fd is not None:
            try:
                os.close(fd)
                os.remove(str(lock))
            except OSError:
                pass


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
    system_prompt = _with_lessons(prompt_path.read_text(encoding="utf-8"), "clean_script")
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


def _reanex_orphan_phrases(
    words: list[dict],
    keep: set[int],
    *,
    max_gap_s: float = 0.7,
    max_reanex_words: int = 6,
) -> tuple[set[int], int]:
    """Evita que el holístico deje una palabra de CONTENIDO suelta separada de
    su frase. Si una 'isla' conservada es UNA sola palabra de contenido y viene
    inmediatamente precedida por un tramo BORRADO de la MISMA frase (sin
    puntuación fuerte ni pausa real entre medias), re-anexa ese tramo al keep
    → reconstruye la frase ("no lo dejes" [borrado] + "pasar" [isla] → entera).

    Solo AÑADE índices al keep (nunca corta más) → imposible que sobre-corte.
    Muy targeted (1 sola palabra de contenido huérfana) para no deshacer
    false-starts legítimos (esos dejan una FRASE entera, no 1 palabra)."""
    n = len(words)
    if not keep or n == 0:
        return keep, 0

    def _tok(i: int) -> str:
        return re.sub(r"[^\wáéíóúñü]", "", str(words[i].get("word", "")).lower())

    def _is_content(i: int) -> bool:
        t = _tok(i)
        return bool(t) and t not in _FILLER_TOKENS and len(t) > 2

    keep = set(keep)
    reverts = 0
    i = 0
    while i < n:
        if i not in keep:
            i += 1
            continue
        a = i
        while i < n and i in keep:
            i += 1
        b = i - 1  # isla conservada [a, b]
        n_content = sum(1 for k in range(a, b + 1) if _is_content(k))
        if n_content != 1 or (b - a) > 1:
            continue  # solo islas de 1 palabra de contenido (huérfana real)
        if a - 1 < 0 or (a - 1) in keep:
            continue  # no hay tramo borrado justo antes
        la = a - 1
        while la - 1 >= 0 and (la - 1) not in keep:
            la -= 1
        if (a - la) > max_reanex_words:
            continue  # tramo borrado largo = corte legítimo, no una frase partida
        gap = float(words[a].get("start", 0.0)) - float(words[a - 1].get("end", 0.0))
        last_removed = str(words[a - 1].get("word", ""))
        if gap < max_gap_s and not re.search(r"[.!?;]\s*$", last_removed):
            for k in range(la, a):
                keep.add(k)
            reverts += 1
    return keep, reverts


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
    # El modelo REAL del holístico es `_HOLISTIC_MODEL` (gpt-5.4) cuando OpenAI
    # está configurado; `model` (gemini) solo es fallback si no hay OpenAI. Antes
    # el diag etiquetaba 'gemini-2.5-pro' aunque corriera gpt-5.4 → confuso.
    from src.editor_auto.api import openai_client
    diag: dict[str, Any] = {
        "model": _HOLISTIC_MODEL if openai_client.is_configured() else model,
        "double_check": double_check,
    }
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

        # Guardarraíl anti-huérfano: si el holístico dejó una palabra de
        # contenido suelta separada de su frase (borró "no lo dejes" y conservó
        # "pasar"), re-anexa el tramo borrado contiguo de la misma frase. Solo
        # añade al keep → nunca sobre-corta.
        final_keep, n_orphan_reverts = _reanex_orphan_phrases(words, final_keep)
        if n_orphan_reverts:
            diag["orphan_reverts"] = n_orphan_reverts
            diag["kept_words"] = len(final_keep)
            log(
                f"[silence_cutter]   ↳ {n_orphan_reverts} frase(s) re-anexada(s) "
                f"(evita dejar 1 palabra suelta sin su frase)"
            )

        # Guardarraíl de TARTAMUDEO: un corte de repetición debe alinearse a la
        # repetición. Si el holístico borró ['es','muy','muy'] y la siguiente
        # palabra conservada es 'muy', el 'es' NO era parte del tartamudeo →
        # re-anexarlo (si no, queda "la cintura | muy elástica" sin el 'es').
        final_keep, n_stutter_fixes = _reanex_stutter_lead_words(words, final_keep)
        if n_stutter_fixes:
            diag["stutter_lead_reverts"] = n_stutter_fixes
            diag["kept_words"] = len(final_keep)
            log(
                f"[silence_cutter]   ↳ {n_stutter_fixes} palabra(s) funcional(es) "
                f"re-anexada(s) antes de un corte de tartamudeo"
            )

        # Red de seguridad: nunca perder contenido ÚNICO (ingredientes, datos,
        # nombres) que el holístico haya decidido cortar por error.
        final_keep, n_unique = _protect_unique_content(words, final_keep)
        if n_unique:
            diag["unique_content_protected"] = n_unique
            diag["kept_words"] = len(final_keep)
            log(
                f"[silence_cutter]   ↳ {n_unique} tramo(s) re-anexado(s) por "
                f"contenido ÚNICO (anti over-cut del holístico)"
            )

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
    system_prompt = _with_lessons(prompt_path.read_text(encoding="utf-8"), "false_starts")
    payload = _build_false_starts_payload(words, language)
    result = analyze_transcript_json(
        system_prompt=system_prompt,
        user_payload=payload,
        model=model,
        temperature=0.0,
        seed=_HOLISTIC_SEED,  # determinista: mismo input = mismos cortes
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
    system_prompt = _with_lessons(prompt_path.read_text(encoding="utf-8"), "false_starts")
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
    system_prompt = _with_lessons(prompt_path.read_text(encoding="utf-8"), "analyst")

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
        temperature=0.0,           # determinista (antes 0.2)
        seed=_HOLISTIC_SEED,       # mismo input = mismos cortes siempre
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
    word_spans = [
        (float(w["start"]), float(w["end"]))
        for w in words if "start" in w and "end" in w
    ]
    out: list[tuple[float, float]] = []
    for s, e in cuts:
        # CLAVE: la palabra PREVIA es la que termina antes del INICIO del cut
        # (end <= s), y la SIGUIENTE la que empieza después del FINAL del cut
        # (start >= e). Usar <=e / >=s cogía una palabra de DENTRO del gap y
        # encogía/eliminaba cortes legítimos (bug que dejaba silencios).
        prev_end = max((x for x in ends if x <= s), default=None)
        next_start = min((x for x in starts if x >= e), default=None)
        ns = s if prev_end is None else max(s, prev_end + guard_s)
        # Backoff del borde final: normalmente retrocede `guard_s` antes del
        # inicio de la palabra siguiente (Whisper marca el inicio bien, así que
        # protege su onset). PERO si una palabra ELIMINADA (dentro del cut)
        # termina justo en `e` y la palabra buena empieza pegada (habla contigua,
        # sin silencio), ese backoff solo conserva la COLA de la palabra mala
        # (residuo tipo "...empezó" antes de "esto costaba"). En ese caso el
        # corte acaba en el inicio de la palabra buena (no la clipa) y se elimina
        # la cola mala. Los cortes de SILENCIO no cumplen la condición → intactos.
        if next_start is None:
            ne = e
        else:
            removed_word_ends_at_e = any(
                ws >= s - 0.01 and abs(we - e) <= 0.06 for ws, we in word_spans
            )
            ne = min(e, next_start) if removed_word_ends_at_e else min(e, next_start - guard_s)
        if ne - ns > 0.05:
            out.append((ns, ne))
    return out


def _preserve_speech_islands_in_cuts(
    cuts: list[tuple[float, float]],
    audio_path: str,
    *,
    min_cut_s: float = 1.0,
    min_island_s: float = 0.22,
    db_above_floor: float = 14.0,
    edge_guard_s: float = 0.18,
    pad_s: float = 0.08,
    protected_cuts: list[tuple[float, float]] | None = None,
) -> tuple[list[tuple[float, float]], int]:
    """Rescata ISLAS de voz atrapadas dentro de un corte largo de 'silencio'.

    Whisper a veces MAL-ALINEA una palabra: le pone el timestamp en una zona muda
    contigua y deja su audio real dentro de un hueco SIN palabras que el cortador
    elimina entero (caso real: 'proteína', cuyo audio está a ~3.8s del slot donde
    Whisper la marcó). Esa palabra es AUDIBLE: su energía está MUY por encima del
    silencio real de su alrededor. Para cada corte ≥`min_cut_s` medimos RMS por
    ventanas de 20ms y detectamos tramos ≥`min_island_s` con energía
    ≥`db_above_floor` dB sobre el SUELO de ruido del PROPIO corte (percentil 10).
    Esas islas se SACAN del corte (se conservan, con `pad_s` de margen). Se
    ignoran islas pegadas a los bordes (`edge_guard_s`: colas/onsets de las
    palabras vecinas, ya cubiertas por el word-guard). Solo REDUCE el corte —
    nunca corta más. Devuelve (cuts_nuevos, n_islas).

    `protected_cuts`: regiones que un corte AUTORITATIVO eliminó a propósito —
    cabecera/cola (auto_trim) y contenido (IA/holístico/ngram/false-start/filler).
    Una isla con energía dentro de una de estas NO es una palabra mal-alineada:
    es una TOS, un FALSO ARRANQUE o RUIDO que la IA mandó cortar. NUNCA se
    rescata (era el bug de buga_1: tos/arranques resucitados como 'islas de voz'
    dentro de la cabecera y de cortes de la IA). El rescate solo aplica dentro de
    cortes puramente ACÚSTICOS (VAD/energía/gap), que es donde Whisper esconde la
    palabra real."""
    protected_cuts = protected_cuts or []
    if not cuts or not audio_path or not os.path.exists(audio_path):
        return cuts, 0
    if not any((e - s) >= min_cut_s for s, e in cuts):
        return cuts, 0
    import wave
    try:
        with wave.open(audio_path, "rb") as wf:
            sr = wf.getframerate(); n_ch = wf.getnchannels()
            sampwidth = wf.getsampwidth(); raw = wf.readframes(wf.getnframes())
    except Exception:
        return cuts, 0
    if sampwidth != 2:
        return cuts, 0
    import numpy as np
    audio = np.frombuffer(raw, dtype=np.int16)
    if n_ch > 1:
        audio = audio.reshape(-1, n_ch).mean(axis=1)
    audio = audio.astype(np.float64)
    win = max(1, int(0.020 * sr)); hop = max(1, int(0.010 * sr))

    def _db_windows(s: float, e: float) -> tuple[list[float], list[float]]:
        i0 = max(0, int(s * sr)); i1 = min(len(audio), int(e * sr))
        ts: list[float] = []; dbs: list[float] = []
        pos = i0
        while pos + win <= i1:
            seg = audio[pos:pos + win]
            rms = float(np.sqrt(np.mean(seg * seg))) + 1e-9
            ts.append((pos + win / 2) / sr)
            dbs.append(20.0 * float(np.log10(rms / 32768.0)))
            pos += hop
        return ts, dbs

    new_cuts: list[tuple[float, float]] = []
    n_islands = 0
    for s, e in cuts:
        if (e - s) < min_cut_s:
            new_cuts.append((s, e)); continue
        ts, dbs = _db_windows(s, e)
        if len(dbs) < 4:
            new_cuts.append((s, e)); continue
        floor = float(np.percentile(dbs, 10))
        thr = floor + db_above_floor
        islands: list[tuple[float, float]] = []
        run_start = None
        for k, db in enumerate(dbs):
            if db >= thr:
                if run_start is None:
                    run_start = k
            elif run_start is not None:
                islands.append((ts[run_start], ts[k - 1])); run_start = None
        if run_start is not None:
            islands.append((ts[run_start], ts[-1]))
        good = [
            (a, b) for a, b in islands
            if (b - a) >= min_island_s and a > s + edge_guard_s and b < e - edge_guard_s
        ]
        # No resucitar islas dentro de un corte AUTORITATIVO (cabecera/cola o
        # contenido de la IA): ahí la energía es tos/falso arranque/ruido que se
        # mandó cortar, no una palabra mal-alineada. Solap = [a,b]∩[ps,pe]≠∅.
        if protected_cuts and good:
            good = [
                (a, b) for a, b in good
                if not any(a < pe and b > ps for ps, pe in protected_cuts)
            ]
        if not good:
            new_cuts.append((s, e)); continue
        cursor = s
        for a, b in good:
            a = max(s, a - pad_s); b = min(e, b + pad_s)
            if a - cursor >= 0.12:
                new_cuts.append((cursor, a))
            cursor = max(cursor, b)
            n_islands += 1
        if e - cursor >= 0.12:
            new_cuts.append((cursor, e))
    return new_cuts, n_islands


def _extend_keeps_to_voiced_edges(
    keep_intervals: list[tuple[float, float]],
    audio_path: str,
    content_cuts: list[tuple[float, float]],
    *,
    max_ext_s: float = 0.6,
    step_s: float = 0.03,
    drop_db: float = 22.0,
) -> tuple[list[tuple[float, float]], int]:
    """Extiende los bordes de cada keep para CAPTURAR la voz adyacente que un
    corte acústico + el snap a palabras dejó fuera.

    Whisper a veces infla el span de una palabra o se salta una (p.ej. se come
    'naranja' y mete 'asegúrate' con un span [29.8-32.4] que engloba naranja +
    pausa + asegúrate). El snap a límites de palabra usa el CENTRO Whisper —que
    cae en el silencio— y descarta la voz real pegada al borde del keep (la cola
    de 'naranja', el 'asegúrate' real). Aquí, en cada borde, medimos la energía
    hacia fuera: mientras siga siendo VOZ (no cae > `drop_db` dB bajo el nivel
    del propio keep en ese borde) y NO entre en un corte de CONTENIDO (dedup/
    falso inicio del holístico), extendemos hasta el silencio real (máx
    `max_ext_s`). Solo AÑADE keep → nunca clipa más. Es agnóstico a los timings
    de Whisper (puro audio), así que arregla cualquier palabra mal-alineada en un
    borde. Devuelve (keeps, n_bordes_extendidos)."""
    if not keep_intervals or not audio_path or not os.path.exists(audio_path):
        return keep_intervals, 0
    import wave
    try:
        with wave.open(audio_path, "rb") as wf:
            sr = wf.getframerate(); n_ch = wf.getnchannels()
            sampwidth = wf.getsampwidth(); raw = wf.readframes(wf.getnframes())
    except Exception:
        return keep_intervals, 0
    if sampwidth != 2:
        return keep_intervals, 0
    import numpy as np
    audio = np.frombuffer(raw, dtype=np.int16)
    if n_ch > 1:
        audio = audio.reshape(-1, n_ch).mean(axis=1)
    audio = audio.astype(np.float64)
    total_s = len(audio) / sr
    win = max(1, int(0.025 * sr))
    hop = max(1, int(0.020 * sr))

    def _db_at(t: float) -> float:
        i0 = int(max(0.0, t) * sr); i1 = min(len(audio), i0 + win)
        if i1 - i0 < 1:
            return -120.0
        seg = audio[i0:i1]
        rms = float(np.sqrt(np.mean(seg * seg))) + 1e-9
        return 20.0 * float(np.log10(rms / 32768.0))

    # Suelo de SILENCIO global del propio audio (percentil 15 de la energía por
    # ventanas): NUNCA extender por debajo de `floor + 12 dB` → no metemos
    # dead-air aunque el borde del keep esté en zona ya quieta.
    all_db = []
    pos = 0
    while pos + win <= len(audio):
        seg = audio[pos:pos + win]
        rms = float(np.sqrt(np.mean(seg * seg))) + 1e-9
        all_db.append(20.0 * float(np.log10(rms / 32768.0)))
        pos += hop
    floor = float(np.percentile(all_db, 15)) if all_db else -60.0
    voice_min = floor + 12.0

    def _in_content_cut(t: float) -> bool:
        return any(s - 1e-3 <= t <= e + 1e-3 for s, e in content_cuts)

    def _voiced(t: float, thr_rel: float) -> bool:
        db = _db_at(t)
        return db >= thr_rel and db >= voice_min

    kept = [(float(a), float(b)) for a, b in keep_intervals]
    n_ext = 0
    out: list[tuple[float, float]] = []
    for a, b in kept:
        # nivel de referencia = voz cerca del propio borde del keep
        ref_a = max(_db_at(a + 0.01), _db_at(a + 0.04), _db_at(a + 0.08))
        ref_b = max(_db_at(b - 0.08), _db_at(b - 0.04), _db_at(b - 0.01))
        thr_a = ref_a - drop_db
        thr_b = ref_b - drop_db
        na, nb = a, b
        # Extender TODOS los bordes a su voz contigua (incluido el FINAL del último
        # keep): así NO se clipa la cola fricativa de la última palabra ("-s"/"-tas"
        # de "cuentas") que Whisper sub-reporta. El "ruido del último frame" NO
        # venía de aquí (era moviepy re-encodeando el audio → resuelto muxeando con
        # ffmpeg) y el fade de cierre va anclado a la energía, así que extender es
        # seguro: completa la palabra sin dejar residuo audible.
        t = a - step_s
        moved = a
        while (a - t) <= max_ext_s and t > 0.0 and not _in_content_cut(t):
            if _voiced(t, thr_a):
                moved = t
            else:
                break
            t -= step_s
        if moved < a - 0.02:
            na = moved; n_ext += 1
        t = b + step_s
        moved = b
        while (t - b) <= max_ext_s and t < total_s and not _in_content_cut(t):
            if _voiced(t, thr_b):
                moved = t
            else:
                break
            t += step_s
        if moved > b + 0.02:
            nb = moved; n_ext += 1
        out.append((max(0.0, na), min(total_s, nb)))
    return _merge_intervals(out), n_ext


def _refine_cut_edges_to_valley(
    cuts: list[tuple[float, float]],
    words: list[dict],
    audio_path: str,
    *,
    search_back_s: float = 0.12,
    search_fwd_max_s: float = 0.28,
) -> tuple[list[tuple[float, float]], int]:
    """Afinado del borde FINAL de cortes en habla CONTIGUA (una palabra
    eliminada pegada a la palabra buena siguiente, sin silencio entre medias).

    Whisper marca los límites de palabra ~100-300ms ANTES del audio real, así
    que un corte que acaba exactamente en `next_start` conserva la COLA de la
    palabra eliminada (residuo tipo "...zó" antes de "esto costaba"). Aquí
    medimos la energía real (RMS por ventanas de 20ms) alrededor del borde y
    movemos el final del corte al MÍNIMO de energía (el valle entre palabras).

    Solo actúa cuando: (a) una palabra eliminada termina justo en el borde, y
    (b) una palabra conservada empieza justo ahí (caso contiguo). La búsqueda
    hacia delante se limita al 40% de la duración de la palabra buena → nunca
    se come su onset. Devuelve (cuts_refinados, n_refinados)."""
    if not cuts or not words or not audio_path or not os.path.exists(audio_path):
        return cuts, 0
    spans = [
        (float(w["start"]), float(w["end"]))
        for w in words if "start" in w and "end" in w
    ]
    # Candidatos: borde final del corte = inicio de palabra conservada Y hay
    # palabra eliminada (dentro del corte) terminando pegada a ese borde.
    candidates: list[int] = []
    for i, (s, e) in enumerate(cuts):
        nxt = next((sp for sp in spans if abs(sp[0] - e) <= 0.03), None)
        if nxt is None:
            continue
        removed_at_edge = any(
            ws >= s - 0.01 and abs(we - e) <= 0.10 for ws, we in spans
        )
        if removed_at_edge:
            candidates.append(i)
    if not candidates:
        return cuts, 0

    import wave
    try:
        with wave.open(audio_path, "rb") as wf:
            sr = wf.getframerate()
            n_ch = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)
    except Exception:
        return cuts, 0
    if sampwidth != 2:
        return cuts, 0  # solo PCM 16-bit (lo que escribe moviepy)
    import numpy as np
    audio = np.frombuffer(raw, dtype=np.int16)
    if n_ch > 1:
        audio = audio.reshape(-1, n_ch).mean(axis=1)
    audio = audio.astype(np.float64)

    win = max(1, int(0.020 * sr))   # ventana RMS 20ms
    hop = max(1, int(0.005 * sr))   # paso 5ms
    out = list(cuts)
    n_ref = 0
    for i in candidates:
        s, e = out[i]
        nxt = next((sp for sp in spans if abs(sp[0] - e) <= 0.03), None)
        if nxt is None:
            continue
        # Hasta el 60% del span Whisper de la palabra buena: como Whisper marca
        # el inicio PRONTO (incluye cola de la palabra previa), esto no llega
        # a su onset real, pero da ventana suficiente para encontrar el valle.
        fwd = min(search_fwd_max_s, 0.6 * max(0.0, nxt[1] - nxt[0]))
        lo = max(0.0, e - search_back_s)
        hi = e + fwd
        i0 = int(lo * sr); i1 = min(len(audio), int(hi * sr))
        if i1 - i0 < win * 2:
            continue
        best_t = None
        best_rms = None
        pos = i0
        while pos + win <= i1:
            seg = audio[pos:pos + win]
            rms = float(np.sqrt(np.mean(seg * seg)))
            if best_rms is None or rms < best_rms:
                best_rms = rms
                best_t = (pos + win / 2) / sr
            pos += hop
        if best_t is not None and best_t > s + 0.05 and abs(best_t - e) > 0.01:
            out[i] = (s, best_t)
            n_ref += 1
    return out, n_ref


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
            stretched_spans or [], keep_intervals or [], words=words,
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


def _deep_audit_compare(
    output_path: str,
    *,
    words: list[dict],
    keep_intervals: list[tuple[float, float]],
    language: str,
    model_size: str,
    cpu_threads: int = 1,
    log=None,
) -> dict:
    """AUDIT PROFUNDO: re-transcribe el OUTPUT final con el mismo Whisper del
    pipeline y lo alinea token a token contra la secuencia ESPERADA (las
    palabras del input cuyo span cae dentro de los keeps).

    Detecta lo que el audit acústico no puede ver:
      · `inserted_blocks` — audio que NO debía estar (residuo de false-start
        tipo "estocost", palabra duplicada que sobrevivió a medias).
      · `missing_blocks` — palabras de contenido que DEBÍAN quedar y no suenan
        (sobre-corte).

    Tolerancias anti-falso-positivo:
      · Palabras con solape parcial (8-60% del span en keeps) son INCIERTAS:
        alinean si aparecen pero no penalizan si faltan (los timestamps de
        Whisper en bordes no son fiables).
      · Variantes de transcripción ("aprovecha"/"aprovecho", splits tipo
        "porque"/"por que") se aceptan por similitud difusa (ratio ≥ 0.7).
      · Solo penalizan faltas de palabras FUERTES de contenido (no fillers).
    """
    import difflib
    import tempfile

    def _norm(s: str) -> str:
        return re.sub(r"[^\wáéíóúñü]", "", str(s).lower())

    # 1) Secuencia esperada con tiers por solape del span en los keeps.
    expected: list[dict] = []  # {tok, strong}
    for w in words:
        try:
            ws, we = float(w["start"]), float(w["end"])
        except (KeyError, TypeError, ValueError):
            continue
        dur = max(1e-6, we - ws)
        ov = sum(max(0.0, min(we, e) - max(ws, s)) for s, e in keep_intervals)
        frac = ov / dur
        tok = _norm(w.get("word", ""))
        if not tok:
            continue
        if frac >= 0.6:
            expected.append({"tok": tok, "strong": True, "ws": ws, "we": we})
        elif frac >= 0.08:
            expected.append({"tok": tok, "strong": False, "ws": ws, "we": we})
    if not expected:
        return {"skipped": "sin palabras esperadas"}

    # 2) Transcribir el OUTPUT (mismo motor/modelo que el input → mismo
    # vocabulario y formato de números; comparación estable).
    tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    try:
        ext = subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-i", output_path, "-ac", "1", "-ar", "16000", "-vn", tmp_wav],
            capture_output=True, timeout=180,
        )
        if ext.returncode != 0:
            return {"error": "ffmpeg extract failed"}
        out_words = _transcribe(
            tmp_wav, model_size=model_size, language=language,
            on_progress=None, timeout_s=900, fallback_model="small",
            primary_threads=max(1, int(cpu_threads)),
        )
    finally:
        try:
            os.remove(tmp_wav)
        except OSError:
            pass
    if not out_words:
        return {"error": "transcripción del output vacía"}

    out_toks = []
    out_times = []
    out_ends = []
    for w in out_words:
        tok = _norm(w.get("word", ""))
        if tok:
            out_toks.append(tok)
            out_times.append(float(w.get("start", 0.0)))
            out_ends.append(float(w.get("end", 0.0)))

    exp_toks = [e["tok"] for e in expected]
    sm = difflib.SequenceMatcher(None, exp_toks, out_toks, autojunk=False)
    inserted: list[dict] = []
    missing: list[dict] = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        if op == "replace":
            # ¿Variante de transcripción del mismo audio? ("aprovecha" vs
            # "aprovecho", "porque" vs "por que"). Compara los bloques unidos.
            a = " ".join(exp_toks[i1:i2])
            b = " ".join(out_toks[j1:j2])
            if difflib.SequenceMatcher(None, a, b).ratio() >= 0.7:
                continue
        if op in ("replace", "delete"):
            toks = [expected[k]["tok"] for k in range(i1, i2)]
            n_strong_content = sum(
                1 for k in range(i1, i2)
                if expected[k]["strong"]
                and expected[k]["tok"] not in _FILLER_TOKENS
                and expected[k]["tok"] not in _AUDIT_STOPWORDS
                and len(expected[k]["tok"]) > 2
            )
            missing.append({
                "text": " ".join(toks),
                "n_toks": len(toks),
                "n_strong_content": n_strong_content,
                # Span en TIEMPO DE INPUT (para que el corrector pueda
                # RESTAURAR la frase perdida a los keeps).
                "input_start": round(min(expected[k]["ws"] for k in range(i1, i2)), 3),
                "input_end": round(max(expected[k]["we"] for k in range(i1, i2)), 3),
            })
        if op in ("replace", "insert"):
            extra = [out_toks[k] for k in range(j1, j2)]
            inserted.append({
                "text": " ".join(extra),
                "n_toks": len(extra),
                "output_t": round(out_times[j1], 2) if j1 < len(out_times) else None,
                # Fin del bloque (para que el corrector corte el span entero).
                "output_t_end": round(out_ends[j2 - 1], 2) if 0 < j2 <= len(out_ends) else None,
            })

    # ── Filtros anti-falso-positivo ─────────────────────────────────────────
    # 1) Emparejar VARIANTES: Whisper re-interpreta palabras cerca de los
    #    bordes de corte (contexto distinto) → "bebida" puede salir como
    #    "beber"/"vida". Un missing y un inserted con similitud ≥0.6 se
    #    cancelan mutuamente (es la misma palabra oída distinto, no un fallo).
    import difflib as _dl
    for m in list(missing):
        for ins in list(inserted):
            if _dl.SequenceMatcher(None, m["text"], ins["text"]).ratio() >= 0.6:
                missing.remove(m)
                inserted.remove(ins)
                break
    # 1-bis) FIABILIDAD — anti-recall-de-Whisper. Una palabra "missing" cuyo span
    #   de INPUT cae ENTERO dentro de un keep (con margen) tiene su audio presente
    #   SÍ O SÍ en el output: el render copia ese tramo TAL CUAL. Si Whisper no la
    #   oyó al re-transcribir, es un fallo de RECALL del modelo, NO una pérdida
    #   real. Esto eliminaba el grueso de los FALSOS FALLOS ("euros" en buga_2,
    #   "cuentas"...). Es seguro por construcción: NO puede ocultar un sobre-corte
    #   (una palabra cortada de verdad NO está dentro de ningún keep, así que no la
    #   filtra). Un clip de borde (cuentas→cuento) sí sobrevive: su span toca el
    #   borde del keep → no cae "entero con margen" → se sigue penalizando.
    _RECALL_MARGIN_S = 0.12
    def _span_fully_in_keep(s: float, e: float) -> bool:
        return any(
            (a + _RECALL_MARGIN_S) <= s and e <= (b - _RECALL_MARGIN_S)
            for a, b in keep_intervals
        )
    missing = [
        m for m in missing
        if not _span_fully_in_keep(
            float(m.get("input_start", 0.0)), float(m.get("input_end", 0.0))
        )
    ]
    # 2) Evidencia FUERTE para penalizar (la varianza típica es de 1 palabra):
    #    · sobrante: ≥2 tokens (frase residual/duplicado) o 1 token ≥6 chars
    #      ("estocost"); 1 palabra corta suelta = varianza → ignorar. ADEMÁS
    #      debe tocar ≥1 palabra de CONTENIDO real — un bloque de solo
    #      funcionales/tartamudeo ("está aquí aquí", "que que") es varianza de
    #      Whisper en habla repetida, NO un residuo real.
    #    · pérdida: bloque ≥3 tokens con ≥1 palabra de contenido ("no lo
    #      dejes"), o ≥2 palabras de contenido; 1 palabra suelta = varianza.
    def _has_content(text: str) -> bool:
        return any(
            len(t) > 2 and t not in _FILLER_TOKENS and t not in _AUDIT_STOPWORDS
            for t in text.split()
        )
    inserted = [
        b for b in inserted
        if (b["n_toks"] >= 2 or len(b["text"].replace(" ", "")) >= 6)
        and _has_content(b["text"])
    ]
    # Anti-ALUCINACIÓN de costura (POSICIONAL): Whisper INVENTA palabras en la
    # junta de un corte (un clic/glitch oído como "aprende a" / "carito naranja").
    # El residuo REAL es la cola/cabeza de la palabra CORTADA en ESA junta
    # ("estocost" de "esto costaba"), así que sus tokens de contenido deben
    # parecerse a lo que se cortó CERCA de esa posición — no a cualquier palabra
    # del vídeo (si comparamos contra todo el guion, un "carito"≈"carrito" dicho
    # en OTRO punto cuela la alucinación). Mapeamos el residuo a tiempo de input y
    # exigimos parecido con las palabras cortadas en ±0.9s. Si no hay nada cortado
    # cerca, o no se parece → alucinación → se descarta. Solo evita un FALSO fallo
    # (retención indebida); nunca corta más.
    def _cut_words_near(t_in: float, window: float = 0.9) -> list[str]:
        near: list[str] = []
        for w in words:
            try:
                ws, we = float(w["start"]), float(w["end"])
            except (KeyError, ValueError, TypeError):
                continue
            c = (ws + we) / 2.0
            if any(a - 1e-3 <= c <= b + 1e-3 for a, b in keep_intervals):
                continue  # conservada → no es material cortado
            if abs(c - t_in) <= window:
                tok = _norm(w.get("word", ""))
                if tok:
                    near.append(tok)
        return near

    def _is_real_residue_block(b: dict) -> bool:
        content = [
            t for t in str(b.get("text", "")).split()
            if len(t) > 2 and t not in _FILLER_TOKENS and t not in _AUDIT_STOPWORDS
        ]
        if not content:
            return False
        t0 = b.get("output_t")
        if t0 is None:
            return True  # sin posición → no podemos verificar → conservador
        t_in = _map_output_to_input(float(t0), keep_intervals)
        if t_in is None:
            return True
        near = _cut_words_near(t_in)
        if not near:
            return False  # nada cortado cerca → no puede ser residuo → alucinación
        for ct in content:
            for ot in near:
                if difflib.SequenceMatcher(None, ct, ot).ratio() >= 0.6:
                    return True
                if len(ot) >= 4 and (ot in ct or ct in ot):  # residuo pegado
                    return True
        return False

    inserted = [b for b in inserted if _is_real_residue_block(b)]
    missing = [
        b for b in missing
        if (b["n_toks"] >= 3 and b["n_strong_content"] >= 1)
        or b["n_strong_content"] >= 2
    ]

    return {
        "model": model_size,
        "n_expected": len(exp_toks),
        "n_output_words": len(out_toks),
        "match_ratio": round(sm.ratio(), 3),
        "inserted_blocks": inserted[:10],
        "missing_blocks": missing[:10],
        # Transcripción REAL del render (lo que el espectador OYE) — la reusa el
        # juez de coherencia SIN coste Whisper extra (ya está transcrito aquí).
        "out_text": " ".join(out_toks),
        "out_words": [
            {"word": t, "start": s, "end": e}
            for t, s, e in zip(out_toks, out_times, out_ends)
        ],
    }


def _removed_spans_text(
    words: list[dict], keep_intervals: list[tuple[float, float]],
) -> str:
    """Texto de las palabras ELIMINADAS a propósito (centro fuera de los keeps).

    Se lo damos al juez como `cuts_summary` → sabe qué se quitó deliberadamente
    (dedup/muletillas/falsos inicios) y NO lo re-marca como fallo. Clave para no
    rechazar ediciones legítimas."""
    out: list[str] = []
    for w in words:
        try:
            ws, we = float(w["start"]), float(w["end"])
        except (KeyError, ValueError, TypeError):
            continue
        mid = (ws + we) / 2.0
        if not any(a - 1e-3 <= mid <= b + 1e-3 for a, b in keep_intervals):
            out.append(str(w.get("word", "")))
    return " ".join(out).strip()


def _has_list_or_number_near_cut(
    words: list[dict], keep_intervals: list[tuple[float, float]],
) -> bool:
    """Pre-screen barato: ¿hay una palabra CONSERVADA de enumeración/número
    (`_COH_LIST_HINTS` o dígito) pegada a un borde de corte? Si la hay, puede
    haberse roto una 'promesa' → vale la pena llamar al juez. Si NO, y el render
    coincide casi 1:1 con lo esperado, nos saltamos el LLM (coste ~$0)."""
    kept_idx = set()
    for i, w in enumerate(words):
        try:
            mid = (float(w["start"]) + float(w["end"])) / 2.0
        except (KeyError, ValueError, TypeError):
            continue
        if any(a - 1e-3 <= mid <= b + 1e-3 for a, b in keep_intervals):
            kept_idx.add(i)
    n = len(words)
    for i in kept_idx:
        tok = re.sub(r"[^\wáéíóúñü]", "", str(words[i].get("word", "")).lower())
        if tok in _COH_LIST_HINTS or tok.isdigit():
            # Junto a un hueco REAL: un vecino que EXISTE pero fue CORTADO. El
            # borde del array (i=0 / i=n-1) no cuenta como hueco — si no se
            # comprueba, i=0 dispara siempre y gasta presupuesto del LLM.
            prev_cut = i > 0 and (i - 1) not in kept_idx
            next_cut = i + 1 < n and (i + 1) not in kept_idx
            if prev_cut or next_cut:
                return True
    return False


def _locate_text_in_words(
    target: str, words: list[dict],
) -> tuple[float, float] | None:
    """Localiza (difuso) una secuencia de tokens en `words` → (start, end) en
    tiempo de INPUT, o None. Para convertir el `missing_text` del juez en un
    span restaurable. Nunca se fía de timestamps del modelo: mapea por palabras
    reales."""
    import difflib

    def _n(s: str) -> str:
        return re.sub(r"[^\wáéíóúñü]", "", str(s).lower())

    tgt = [_n(t) for t in str(target).split() if _n(t)]
    if not tgt or not words:
        return None
    L = len(tgt)
    toks = [_n(w.get("word", "")) for w in words]
    best = None
    bestr = 0.0
    for i in range(0, max(1, len(words) - L + 1)):
        cand = toks[i:i + L]
        r = difflib.SequenceMatcher(None, tgt, cand).ratio()
        if r > bestr:
            bestr = r
            best = (i, min(len(words) - 1, i + L - 1))
    if best and bestr >= 0.8:
        try:
            return (float(words[best[0]]["start"]), float(words[best[1]]["end"]))
        except (KeyError, ValueError, TypeError):
            return None
    return None


def _ai_coherence_judge(
    *, words: list[dict], deep: dict, keep_intervals: list[tuple[float, float]],
    language: str, log, call_budget: list[int] | None, config: dict,
) -> dict:
    """PASADA FINAL DE SENTIDO. Compara el ORIGINAL con la transcripción REAL del
    render (`deep['out_text']`, coste Whisper cero) y deja que gpt-5.4 juzgue si
    el vídeo editado sigue teniendo sentido (caso 'dos ingredientes → arroz' sin
    proteína). Determinista (temp 0 + seed). Verifica las citas/tokens del modelo
    contra los textos reales (anti-alucinación). Devuelve dict con
    `coherence_score`, `defects` (con `restore_span`), `coherence_needs_requeue`
    y `coherence_fallos` (defectos graves y ARREGLABLES)."""
    from src.editor_auto.api import openai_client
    if not openai_client.is_configured():
        return {"skipped": "openai no configurado"}
    if call_budget is not None and call_budget and call_budget[0] <= 0:
        return {"skipped": "presupuesto de llamadas agotado"}
    if len(words) < 8:
        return {"skipped": "pocas palabras"}
    orig_text = " ".join(str(w.get("word", "")) for w in words).strip()
    # Texto EDITADO = palabras CONSERVADAS (centro dentro de un keep), en orden.
    # Representa la DECISIÓN DEL EDITOR (lo que de verdad queda en el vídeo), NO
    # la re-transcripción del render: Whisper a veces NO re-transcribe una palabra
    # que SÍ está conservada (fallo de recall en audio cortado), y comparar contra
    # eso marcaba como "perdidas" palabras presentes (proteína/euros) → falsos
    # positivos. El juez evalúa lo que el editor decidió dejar (su intención).

    # Conservada = su span SOLAPA un keep (≥40% de su duración), NO solo el
    # centro: Whisper coloca mal el tiempo de algunas palabras (deja el centro
    # justo fuera del keep aunque su AUDIO esté dentro) → con el criterio de
    # centro se marcaban como "perdidas" palabras presentes (euros). El solape es
    # robusto a ese error de timing y sigue siendo seguro (una palabra cortada de
    # verdad no solapa ningún keep).
    def _kept_overlap(ws: float, we: float) -> bool:
        dur = max(1e-6, we - ws)
        ov = sum(
            max(0.0, min(we, b) - max(ws, a)) for a, b in keep_intervals
        )
        return (ov / dur) >= 0.4

    kept_words = []
    for w in words:
        try:
            ws, we = float(w["start"]), float(w["end"])
        except (KeyError, ValueError, TypeError):
            continue
        if _kept_overlap(ws, we):
            kept_words.append(w)
    out_text = " ".join(str(w.get("word", "")) for w in kept_words).strip()
    if not out_text:
        return {"skipped": "sin contenido conservado"}

    def _flat(s: str) -> str:
        # Sin acentos NI puntuación: Whisper a veces transcribe sin tilde
        # ('estan' vs 'están'); si no normalizamos, una cita válida del juez no
        # casa y se perdería un defecto REAL. Robustez > exactitud ortográfica.
        s = unicodedata.normalize("NFKD", str(s).lower()).encode("ascii", "ignore").decode()
        return re.sub(r"[^\w ]", "", s)

    def _ntok(s: str) -> str:
        s = unicodedata.normalize("NFKD", str(s).lower()).encode("ascii", "ignore").decode()
        return re.sub(r"[^\w]", "", s)

    # PRE-SCREEN: en vídeos claramente limpios (render ≈ esperado, sin fallos de
    # palabra y sin enumeración/número junto a un corte) NO llamamos al LLM →
    # coherence_score=100 y el coste medio se queda como hoy (~$0.04).
    if (
        float((deep or {}).get("match_ratio", 0) or 0) >= 0.97
        and not (deep or {}).get("missing_blocks")
        and not (deep or {}).get("inserted_blocks")
        and not _has_list_or_number_near_cut(words, keep_intervals)
    ):
        return {"coherence_score": 100, "defects": [], "skipped_clean": True}

    cuts_summary = _removed_spans_text(words, keep_intervals)
    try:
        prompt_path = (
            Path(__file__).resolve().parent.parent
            / "prompts" / "silence_cutter_coherence.md"
        )
        system = _with_lessons(prompt_path.read_text(encoding="utf-8"), "coherence")
    except OSError as e:
        return {"error": f"prompt no leíble: {e}"}
    try:
        data = openai_client.analyze_transcript_json(
            system_prompt=system,
            user_payload={
                "language": language, "original": orig_text,
                "rendered": out_text, "cuts_summary": cuts_summary,
            },
            model=_COHERENCE_MODEL, temperature=0.0, seed=_COHERENCE_SEED,
        )
        if call_budget is not None and call_budget:
            call_budget[0] -= 1
    except Exception as e:  # noqa: BLE001
        log(f"[silence_cutter] ⚠️ Juez de coherencia falló (no bloquea): {e}")
        return {"error": str(e)[:200]}

    flat_orig = _flat(orig_text)
    flat_out = _flat(out_text)
    out_tokset = set(_ntok(t) for t in out_text.split())
    out_tokset.discard("")
    defects: list[dict] = []
    for d in (data or {}).get("defects", []) or []:
        if not d.get("confirmed"):
            continue
        oq = _flat(d.get("original_quote", ""))
        rq = _flat(d.get("rendered_quote", ""))
        # Anti-alucinación: las citas deben EXISTIR de verdad en los textos.
        if oq and oq not in flat_orig:
            continue
        if rq and rq not in flat_out:
            continue
        mt = str(d.get("missing_text", "") or "")
        lost = [_ntok(t) for t in mt.split()]
        lost = [t for t in lost if t]
        # PRECISIÓN ANTI-FALSO-POSITIVO (clave): un defecto SOLO cuenta si señala
        # una palabra de CONTENIDO concreta que de verdad FALTA del render. Esto:
        #   · descarta defectos sin `missing_text` (nonsense_join/dangling_ref =
        #     juicios subjetivos del juez, fuente principal de FP),
        #   · descarta defectos cuya palabra "perdida" SÍ está en el render
        #     (euros/%/proteína presentes → el juez se equivocó comparando con el
        #     original y viendo lo que se cortó a propósito).
        # Solo sobreviven cortes REALES de contenido (el caso 'proteína' cortada).
        if not lost:
            continue
        content_lost = [
            t for t in lost
            if len(t) > 2 and t not in _FILLER_TOKENS and t not in _AUDIT_STOPWORDS
            and t not in out_tokset
        ]
        if not content_lost:
            continue
        sev = min(3, max(1, int(d.get("severity", 2) or 2)))
        span = _locate_text_in_words(mt, words)
        defects.append({**d, "severity": sev, "restore_span": span})

    penalty = sum(_COH_SEV_PENALTY[x["severity"]] for x in defects)
    coh_score = max(0, 100 - penalty)
    needs_rq = any(x["severity"] >= 2 for x in defects)
    # Fallos "accionables": graves Y arreglables con restauración → el self-heal
    # los reintenta. Un defecto grave NO arreglable detiene el loop (retención).
    fallos = sum(
        1 for x in defects
        if x["severity"] >= 2 and x.get("fixable") and x.get("restore_span")
    )
    return {
        "coherence_score": coh_score, "defects": defects,
        "coherence_needs_requeue": needs_rq, "coherence_fallos": fallos,
    }


def _count_coherence_fallos(audit: dict) -> int:
    return int((audit or {}).get("coherence_fallos", 0) or 0)


def _union_intervals(
    keeps: list[tuple[float, float]],
    spans: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Keeps ∪ spans, fusionando solapes (para RESTAURAR tramos sobre-cortados)."""
    allv = sorted(list(keeps) + [(float(a), float(b)) for a, b in spans if b > a])
    out: list[tuple[float, float]] = []
    for a, b in allv:
        if out and a <= out[-1][1] + 1e-6:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _subtract_intervals(
    keeps: list[tuple[float, float]],
    cuts: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Keeps − cuts (para aplicar cortes correctivos)."""
    if not cuts:
        return list(keeps)
    merged = _merge_intervals([(float(a), float(b)) for a, b in cuts if b > a])
    out: list[tuple[float, float]] = []
    for ka, kb in keeps:
        cur = ka
        for ca, cb in merged:
            if cb <= cur or ca >= kb:
                continue
            if ca > cur:
                out.append((cur, min(ca, kb)))
            cur = max(cur, cb)
            if cur >= kb:
                break
        if cur < kb:
            out.append((cur, kb))
    return [(a, b) for a, b in out if (b - a) > 1e-3]


def _count_word_fallos(audit: dict | None) -> int:
    """Nº de fallos de PALABRA del audit profundo: sobrantes (audio que no
    debía sonar) + perdidas (palabras sobre-cortadas). Es lo GRAVE para el
    usuario; los silencios de más NO cuentan aquí (son tolerables)."""
    deep = (audit or {}).get("deep") or {}
    return len(deep.get("inserted_blocks") or []) + len(deep.get("missing_blocks") or [])


def _snap_keeps_to_words(
    keep_intervals: list[tuple[float, float]],
    words: list[dict],
    *,
    head_pad: float = 0.04,
    tail_pad: float = 0.10,
) -> list[tuple[float, float]]:
    """Ajusta cada keep a PALABRAS COMPLETAS. Paso FINAL determinista sobre los
    keeps ya calculados que GARANTIZA que el borde de un keep nunca:
      · incluya el arranque de la palabra cortada siguiente (sliver tipo
        'to'/'pa'/'queto' que se oye colgando tras la última palabra buena), ni
      · parta a media la última palabra conservada (final 'montó' en vez de
        'montón' → vídeo que 'termina mal').
    Para cada keep: recorta el inicio al onset de la 1ª palabra cuyo centro cae
    dentro (sin invadir la palabra previa cortada) y lleva el final al fin de la
    última (sin invadir la siguiente cortada). Limpia los slivers que dejen
    valley/word-guard/merge, sea cual sea su origen. Un keep sin ninguna palabra
    dentro se deja intacto (silencios intencionales no se tocan)."""
    if not keep_intervals or not words:
        return keep_intervals
    spans = sorted(
        (float(w["start"]), float(w["end"]))
        for w in words if "start" in w and "end" in w
    )
    if not spans:
        return keep_intervals
    out: list[tuple[float, float]] = []
    for a, b in keep_intervals:
        inside = [(ws, we) for ws, we in spans if a - 0.001 <= (ws + we) / 2 <= b + 0.001]
        if not inside:
            out.append((a, b))
            continue
        fw_s, lw_e = inside[0][0], inside[-1][1]
        prev_end = max((we for ws, we in spans if we <= fw_s + 0.001), default=None)
        next_start = min((ws for ws, we in spans if ws >= lw_e - 0.001), default=None)
        na = fw_s - head_pad
        if prev_end is not None and prev_end > na:
            na = prev_end            # no arrastrar la cola de la palabra previa cortada
        na = min(na, fw_s)           # nunca empezar tras el onset de la 1ª palabra buena
        nb = lw_e + tail_pad
        if next_start is not None and next_start < nb:
            nb = next_start          # no colar el arranque de la palabra siguiente cortada
        nb = max(nb, lw_e)           # nunca cortar antes del fin de la última (no partir)
        if nb - na > 0.05:
            out.append((max(0.0, na), nb))
    return _merge_intervals(out)


# Palabras que NO pueden quedar COLGADAS al final de un segmento (conjunciones,
# preposiciones, artículos, copulas, muletillas). Si un keep termina en una de
# estas y lo siguiente está cortado, suena a frase rota ("...azul marino que |"
# o el vídeo acabando en "...bueno"). Se recortan del final del keep.
_DANGLING_TAIL_TOKENS = {
    "que", "y", "o", "u", "e", "pero", "porque", "pues", "bueno", "con",
    "de", "del", "en", "a", "al", "la", "el", "los", "las", "un", "una",
    "unos", "unas", "mi", "tu", "su", "sus", "me", "te", "se", "le", "les",
    "lo", "como", "si", "cuando", "aunque", "entonces", "tan", "para",
    "por", "mas", "más", "ni", "ya", "es", "son", "esta", "este", "esto",
    "está", "osea", "están", "estan", "estás", "estaba", "estaban", "era",
    "eran",
}


def _trim_dangling_tail_words(
    keep_intervals: list[tuple[float, float]],
    words: list[dict],
    *,
    max_drop: int = 3,
) -> tuple[list[tuple[float, float]], int]:
    """Recorta del FINAL de cada keep las palabras funcionales colgadas
    (que/y/bueno/con/...) cuando lo que sigue está cortado. Una frase que
    termina en conjunción o muletilla antes de un salto suena rota; sin
    ellas termina natural ("...azul marino" / "...estampados rayaditos").
    Deja siempre ≥2 palabras en el segmento. Devuelve (keeps, n_dropped)."""
    if not keep_intervals or not words:
        return keep_intervals, 0
    spans = sorted(
        (
            float(w["start"]), float(w["end"]),
            re.sub(r"[^\wáéíóúñü]", "", str(w.get("word", "")).lower()),
        )
        for w in words if "start" in w and "end" in w
    )
    out: list[tuple[float, float]] = []
    n_total = 0
    for idx, (a, b) in enumerate(keep_intervals):
        # SOLO recortar en SALTOS reales de contenido (>2s al siguiente keep)
        # o en el último segmento. En un micro-corte (silencio/tartamudeo) la
        # frase CONTINÚA al otro lado — "…es muy muy | muy elástica" — y
        # recortar el final mutila la frase.
        next_a = (
            keep_intervals[idx + 1][0]
            if idx + 1 < len(keep_intervals) else None
        )
        if next_a is not None and (next_a - b) <= 2.0:
            out.append((a, b))
            continue
        inside = [s for s in spans if a - 1e-3 <= (s[0] + s[1]) / 2 <= b + 1e-3]
        drops = 0
        first_dropped_start: float | None = None
        while (
            len(inside) >= 3 and drops < max_drop
            and inside[-1][2] in _DANGLING_TAIL_TOKENS
        ):
            first_dropped_start = inside[-1][0]
            inside.pop()
            drops += 1
        if drops:
            n_total += drops
            nb = inside[-1][1] + 0.10
            if first_dropped_start is not None:
                nb = min(nb, first_dropped_start)
            b = max(nb, inside[-1][1])
        if b - a > 0.05:
            out.append((a, b))
    return out, n_total


def _complete_final_phrase(
    keep_intervals: list[tuple[float, float]],
    words: list[dict],
    *,
    min_pause_s: float = 0.5,
    max_extend_s: float = 6.0,
    max_extend_words: int = 15,
) -> tuple[list[tuple[float, float]], tuple | None]:
    """El VÍDEO debe terminar al final de una frase REAL (con pausa del
    hablante). Si la última palabra conservada va seguida INMEDIATAMENTE
    (<min_pause_s) de más habla cortada en el input, el corte dejó la frase a
    medias → EXTIENDE el último keep palabra a palabra hasta la siguiente
    pausa real. Si no hay pausa alcanzable dentro del margen, RECORTA hacia
    atrás hasta la última palabra con pausa posterior (cierra en la frase
    anterior completa). Devuelve (keeps, accion|None)."""
    if not keep_intervals or not words:
        return keep_intervals, None
    spans = sorted(
        (float(w["start"]), float(w["end"]))
        for w in words if "start" in w and "end" in w
    )
    if not spans:
        return keep_intervals, None
    a, b = keep_intervals[-1]
    inside = [sp for sp in spans if a - 1e-3 <= (sp[0] + sp[1]) / 2 <= b + 1e-3]
    if not inside:
        return keep_intervals, None
    lw_e = inside[-1][1]
    after = [sp for sp in spans if sp[0] >= lw_e - 1e-3]
    if not after or (after[0][0] - lw_e) >= min_pause_s:
        return keep_intervals, None  # ya cierra en pausa real / fin del habla
    # Extender hasta la siguiente pausa real del hablante.
    prev_end = lw_e
    added = 0
    result_end: float | None = None
    for ws, we in after:
        if ws - prev_end >= min_pause_s:
            result_end = prev_end
            break
        if (we - lw_e) > max_extend_s or added >= max_extend_words:
            result_end = None
            break
        prev_end = we
        added += 1
    else:
        result_end = prev_end  # se acabó el habla → cierre natural
    if result_end is not None and added > 0:
        out = list(keep_intervals)
        out[-1] = (a, result_end + 0.10)
        return _merge_intervals(out), ("extender", added)
    if result_end is not None:
        return keep_intervals, None
    # Sin pausa alcanzable → cerrar en la frase ANTERIOR (última palabra del
    # keep con pausa real después).
    for idx in range(len(inside) - 2, -1, -1):
        we = inside[idx][1]
        nxt = next((sp for sp in spans if sp[0] >= we - 1e-3), None)
        if nxt is None or (nxt[0] - we) >= min_pause_s:
            out = list(keep_intervals)
            nb = we + 0.10
            if nb - a > 0.5:
                out[-1] = (a, nb)
                return _merge_intervals(out), ("recortar_atras", len(inside) - 1 - idx)
            break
    return keep_intervals, None


def _longest_below(
    ts: list[float], dbs: list[float], thr: float, lo: float, hi: float,
) -> float:
    """Duración del tramo CONTIGUO más largo por DEBAJO de `thr` dentro de
    [lo, hi]. Sirve para probar que una zona es silencio real (no una sílaba
    floja continua)."""
    best = 0.0
    run_start = None
    last_t = None
    for t, db in zip(ts, dbs):
        if t < lo or t > hi:
            continue
        if db < thr:
            if run_start is None:
                run_start = t
            last_t = t
        else:
            if run_start is not None and last_t is not None:
                best = max(best, last_t - run_start)
            run_start = None
    if run_start is not None and last_t is not None:
        best = max(best, last_t - run_start)
    return best


def _shrink_inflated_word_spans(words: list[dict], audio_path: str) -> int:
    """Encoge SOLO los spans INFLADOS de Whisper (palabra real + pausa absorbida)
    a su voz dominante. NUNCA mueve/inserta/borra/reordena/re-textea una palabra
    → seguro POR CONSTRUCCIÓN: no puede perder una palabra (solo edita start/end
    de un dict existente), resucitar un tartamudeo (jamás extiende un span hacia
    audio vecino, solo lo reduce), ni cortar voz floja (umbral relativo al suelo
    local + prueba de hueco mudo contiguo). Al reducir el span, el silencio
    absorbido queda LIBRE para que el cortador de pausas existente lo quite.

    Lee `audio_path` (el audio nivelado que Whisper transcribió → mismo marco de
    referencia). Determinista. Devuelve nº de palabras encogidas. Cualquier fallo
    de decode → 0 y palabras intactas."""
    if not words or not audio_path or not os.path.exists(audio_path):
        return 0
    import wave
    try:
        with wave.open(audio_path, "rb") as wf:
            sr = wf.getframerate(); n_ch = wf.getnchannels()
            sampwidth = wf.getsampwidth(); raw = wf.readframes(wf.getnframes())
    except Exception:
        return 0
    if sampwidth != 2:
        return 0
    import numpy as np
    audio = np.frombuffer(raw, dtype=np.int16)
    if n_ch > 1:
        audio = audio.reshape(-1, n_ch).mean(axis=1)
    audio = audio.astype(np.float64)
    win = max(1, int(0.020 * sr)); hop = max(1, int(0.005 * sr))

    def _windows(a: float, b: float) -> tuple[list[float], list[float]]:
        i0 = max(0, int(a * sr)); i1 = min(len(audio), int(b * sr))
        ts: list[float] = []; dbs: list[float] = []
        pos = i0
        while pos + win <= i1:
            seg = audio[pos:pos + win]
            rms = float(np.sqrt(np.mean(seg * seg))) + 1e-9
            ts.append((pos + win / 2) / sr)
            dbs.append(20.0 * float(np.log10(rms / 32768.0)))
            pos += hop
        return ts, dbs

    n_shrunk = 0
    for w in words:
        try:
            ws, we = float(w["start"]), float(w["end"])
        except (KeyError, ValueError, TypeError):
            continue
        dur = we - ws
        tok = re.sub(r"[^\wáéíóúñü]", "", str(w.get("word", "")).lower())
        # GATE 1 — pre-screen barato por duración/token (toca <5% de palabras).
        short_or_filler = (
            len(tok) <= 3 or tok in _FILLER_TOKENS or tok in _AUDIT_STOPWORDS
        )
        if not (dur >= _REALIGN_INFLATE_HARD_S
                or (dur >= _REALIGN_INFLATE_SOFT_S and short_or_filler)):
            continue
        ts, dbs = _windows(ws, we)
        if len(dbs) < 4:
            continue
        # Umbral RELATIVO al suelo local del span (voz floja sigue siendo voz).
        floor = float(np.percentile(dbs, 10))
        thr = floor + _REALIGN_VOICE_DB
        # Runs de voz, puenteando micro-dips (<BRIDGE) dentro de una palabra.
        runs: list[tuple[float, float]] = []
        run_s = None; prev_voiced_t = None
        for t, db in zip(ts, dbs):
            if db >= thr:
                if run_s is None:
                    run_s = t
                prev_voiced_t = t
            elif run_s is not None and prev_voiced_t is not None \
                    and (t - prev_voiced_t) > _REALIGN_BRIDGE_S:
                runs.append((run_s, prev_voiced_t)); run_s = None
        if run_s is not None and prev_voiced_t is not None:
            runs.append((run_s, prev_voiced_t))
        runs = [(a, b) for a, b in runs if (b - a) >= _REALIGN_MIN_RUN_S]
        if not runs:
            continue  # sin voz dentro → mis-placed → dejar a island-rescue, NO tocar
        # ANCHOR-RESPECT: run más cercano al ONSET de Whisper (confiamos el start
        # mucho más que el end). Encoge sobre todo la COLA.
        run_a, run_b = min(runs, key=lambda r: abs(r[0] - ws))
        # GATE 2 — prueba de INFLACIÓN: hueco mudo contiguo ≥MIN_DEAD entre el fin
        # del run dominante y el fin de la palabra. Sin hueco → palabra real larga
        # (un 'adidas' lento) → NO tocar.
        if _longest_below(ts, dbs, thr, run_b, we) < _REALIGN_MIN_DEAD_S:
            continue
        new_s = max(ws, run_a - _REALIGN_PAD_S)
        new_e = min(we, run_b + _REALIGN_PAD_S)
        # GATE 3 — cambio significativo.
        if not (new_e < we - 0.10 or new_s > ws + 0.10):
            continue
        # GATE 4 — nunca vaciar una palabra.
        if new_e - new_s < _REALIGN_MIN_RUN_S:
            continue
        # GATE 5 — probar que la COLA liberada es silencio real (no una sílaba
        # floja continua tipo 'claro ya'): hueco mudo contiguo ≥MIN_DEAD.
        if (we - new_e) > 0.05 and \
                _longest_below(ts, dbs, thr, new_e, we) < _REALIGN_MIN_DEAD_S:
            continue
        w["start"] = round(new_s, 3); w["end"] = round(new_e, 3)
        w["_realigned"] = True
        n_shrunk += 1

    # MONOTONICIDAD (belt-and-suspenders): como solo encogemos hacia dentro, los
    # spans no pueden solapar al vecino; este clamp garantiza la invariante que
    # asumen _snap_keeps_to_words / _protect_word_boundaries.
    for i in range(1, len(words)):
        try:
            if float(words[i]["start"]) < float(words[i - 1]["end"]):
                words[i]["start"] = round(float(words[i - 1]["end"]), 3)
                if float(words[i]["end"]) < float(words[i]["start"]):
                    words[i]["end"] = float(words[i]["start"])
        except (KeyError, ValueError, TypeError):
            continue
    return n_shrunk


def _refine_keep_edges_to_valley(
    keep_intervals: list[tuple[float, float]],
    words: list[dict],
    audio_path: str,
    *,
    contig_s: float = 0.45,
) -> tuple[list[tuple[float, float]], int]:
    """Afina los DOS bordes de cada keep al VALLE de energía real (mínimo RMS)
    cuando hay habla contigua al otro lado del corte.

    Por qué: Whisper marca los límites de palabra ~100-300ms ANTES del audio
    real. En habla contigua eso significa que:
      · el INICIO del keep (= fin de un corte) puede caer dentro de la COLA de
        la palabra eliminada previa → se cuela un resto tipo 'o'/'as'/'os'
        (sedosit-O, florecit-AS, rayadit-O) antes de la primera palabra buena;
      · el FINAL del keep (= inicio de un corte) clavado en el start Whisper de
        la siguiente palabra puede CLIPAR la última palabra buena ('ocho' que
        no termina) o colar el arranque de la cortada.
    El valle de energía entre ambas palabras es el punto de corte óptimo real.
    Solo actúa con habla contigua (<contig_s de hueco); con silencio real deja
    el borde como está. Devuelve (keeps, n_bordes_afinados)."""
    if (
        not keep_intervals or not words or not audio_path
        or not os.path.exists(audio_path)
    ):
        return keep_intervals, 0
    spans = sorted(
        (float(w["start"]), float(w["end"]))
        for w in words if "start" in w and "end" in w
    )
    if not spans:
        return keep_intervals, 0
    import wave
    try:
        with wave.open(audio_path, "rb") as wf:
            sr = wf.getframerate()
            n_ch = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            raw = wf.readframes(wf.getnframes())
    except Exception:  # noqa: BLE001
        return keep_intervals, 0
    if sampwidth != 2:
        return keep_intervals, 0
    import numpy as np
    audio = np.frombuffer(raw, dtype=np.int16)
    if n_ch > 1:
        audio = audio.reshape(-1, n_ch).mean(axis=1)
    audio = audio.astype(np.float64)
    dur_total = len(audio) / float(sr)
    win = max(1, int(0.020 * sr))
    hop = max(1, int(0.005 * sr))

    def _valley(t0: float, t1: float) -> float | None:
        t0 = max(0.0, t0)
        t1 = min(dur_total, t1)
        if t1 - t0 < 0.03:
            return None
        i0, i1 = int(t0 * sr), int(t1 * sr)
        best_t = best_rms = None
        i = i0
        while i + win <= i1:
            seg = audio[i:i + win]
            rms = float((seg * seg).mean()) ** 0.5
            if best_rms is None or rms < best_rms:
                best_rms, best_t = rms, (i + win // 2) / sr
            i += hop
        return best_t

    out: list[tuple[float, float]] = []
    n_ref = 0
    for a, b in keep_intervals:
        inside = [
            (ws, we) for ws, we in spans
            if a - 1e-3 <= (ws + we) / 2 <= b + 1e-3
        ]
        na, nb = a, b
        if inside:
            fw_s, fw_e = inside[0]
            lw_s, lw_e = inside[-1]
            prev_end = max((we for ws, we in spans if we <= fw_s + 1e-3), default=None)
            nxt = min(
                ((ws, we) for ws, we in spans if ws >= lw_e - 1e-3),
                default=None,
            )
            # HEAD — cola de la palabra cortada previa colándose al keep.
            if prev_end is not None and (fw_s - prev_end) < contig_s:
                v = _valley(
                    prev_end,
                    fw_s + min(0.25, 0.4 * max(0.05, fw_e - fw_s)),
                )
                if v is not None and abs(v - na) > 0.01:
                    na, n_ref = v, n_ref + 1
            # TAIL — última palabra clipada o arranque de la cortada colándose.
            # SOLO hacia delante desde lw_e: Whisper cierra las palabras PRONTO
            # (la cola real suena después de lw_e), así que buscar antes de
            # lw_e clipaba la palabra buena ('cintur|', 'rayadito|s'). El valle
            # real está entre la cola verdadera (>lw_e) y el onset de la
            # siguiente (>next_start).
            # Cap de avance dentro de la palabra cortada siguiente: +0.12s máx.
            # Con 40% de su span, una consonante de baja energía ('m' de
            # 'marino') hacía caer el valle DENTRO de la palabra y dejaba su
            # arranque audible ("azul m|" → se oye 'así').
            if nxt is not None and (nxt[0] - lw_e) < contig_s:
                v = _valley(
                    lw_e,
                    nxt[0] + min(0.12, 0.4 * max(0.05, nxt[1] - nxt[0])),
                )
                if v is not None and v > lw_e and abs(v - nb) > 0.01:
                    nb, n_ref = v, n_ref + 1
        if nb - na > 0.05:
            out.append((max(0.0, na), nb))
    return _merge_intervals(out), n_ref


def _ai_completeness_review(
    keep_intervals: list[tuple[float, float]],
    words: list[dict],
    *,
    language: str,
    log,
) -> tuple[list[tuple[float, float]], dict]:
    """Revisión IA de COMPLETITUD de frase por segmento (determinista: temp 0 +
    seed). El holístico a veces conserva un final colgado a mitad de idea
    ('...y están solo por ocho' sin completar el precio). Aquí gpt-5.4 ve los
    segmentos finales EN ORDEN y propone, solo donde haga falta, eliminar las
    últimas N palabras para que el segmento termine en frase completa. Nunca
    añade contenido, caps conservadores, y si falla no toca nada."""
    from src.editor_auto.api import openai_client
    diag: dict[str, Any] = {}
    if not openai_client.is_configured():
        return keep_intervals, {"skipped": "sin OpenAI"}
    spans = sorted(
        (
            float(w["start"]), float(w["end"]),
            str(w.get("word", "")).strip(),
        )
        for w in words if "start" in w and "end" in w
    )
    seg_words: list[list[tuple[float, float, str]]] = []
    for a, b in keep_intervals:
        seg_words.append(
            [s for s in spans if a - 1e-3 <= (s[0] + s[1]) / 2 <= b + 1e-3]
        )
    # SOLO son revisables los segmentos seguidos de un SALTO real de contenido
    # (>2s de hueco en el input) o el último. Si el siguiente keep está pegado
    # (corte de silencio/tartamudeo a <2s), el habla CONTINÚA la misma frase
    # al otro lado del corte — un final "a medias" ahí es normal y recortarlo
    # mutila la frase ("la cintura es muy muy | muy elástica").
    reviewable: set[int] = set()
    for k in range(len(keep_intervals)):
        if k == len(keep_intervals) - 1:
            reviewable.add(k)
        elif keep_intervals[k + 1][0] - keep_intervals[k][1] > 2.0:
            reviewable.add(k)
    segments = [
        {"i": k, "text": " ".join(s[2] for s in sw)}
        for k, sw in enumerate(seg_words) if sw and k in reviewable
    ]
    if not segments:
        return keep_intervals, {"skipped": "sin segmentos revisables"}
    system = (
        "Eres un editor de vídeo profesional. Te paso los SEGMENTOS de habla "
        "que quedarán en el vídeo final, en orden; entre segmento y segmento "
        "hay un corte (salto). Tu ÚNICA tarea: detectar segmentos cuyo FINAL "
        "queda colgado a mitad de frase o de idea — p. ej. termina en un "
        "precio sin completar ('están solo por ocho' y salta), en conjunción, "
        "o anuncia algo que ya no se dice. Para cada segmento problemático "
        "propón eliminar SOLO las últimas N palabras (N pequeño) de modo que "
        "termine en una frase completa y natural. NO propongas añadir nada. "
        "NO toques segmentos que ya terminan bien. Sé conservador: ante la "
        "duda, no toques. Responde JSON: "
        '{"fixes": [{"i": <índice del segmento>, "drop_last_words": <N>}]}'
    )
    system = _with_lessons(system, "completeness")
    try:
        data = openai_client.analyze_transcript_json(
            system_prompt=system,
            user_payload={"language": language, "segments": segments},
            model=_HOLISTIC_MODEL,
            temperature=0.0,
            seed=_HOLISTIC_SEED,
        )
    except Exception as e:  # noqa: BLE001
        log(f"[silence_cutter] ⚠️ Revisión de completitud falló (no bloquea): {e}")
        return keep_intervals, {"error": str(e)[:200]}
    fixes = (data or {}).get("fixes") or []
    diag["proposed"] = len(fixes)
    out = list(keep_intervals)
    applied = 0
    for f in fixes:
        if applied >= 3:  # cap global: nunca más de 3 recortes por vídeo
            break
        try:
            i = int(f.get("i"))
            n = int(f.get("drop_last_words", 0))
        except (TypeError, ValueError):
            continue
        if not (0 <= i < len(out)) or n <= 0 or i not in reviewable:
            continue
        sw = seg_words[i] if i < len(seg_words) else []
        # Caps: máx 8 palabras, máx 40% del segmento, deja ≥3 palabras.
        n = min(n, 8, int(len(sw) * 0.4))
        if n <= 0 or len(sw) - n < 3:
            continue
        dropped = sw[-n:]
        kept_last = sw[-n - 1]
        # Límite de cláusula: el bloque eliminado debe EMPEZAR en palabra
        # funcional (conjunción/preposición/artículo) — "y están solo por
        # ocho" ✓. Si empieza en palabra de contenido ("marino que") el modelo
        # está partiendo la frase por dentro, no quitando una cláusula colgada
        # → rechazar (mutiló "azul marino" en un caso real).
        first_tok = re.sub(r"[^\wáéíóúñü]", "", str(dropped[0][2]).lower())
        if not (
            first_tok in _AUDIT_STOPWORDS
            or first_tok in _FILLER_TOKENS
            or len(first_tok) <= 3
        ):
            log(
                f"[silence_cutter] 🛑 Completitud rechazada (seg {i}): el "
                f"recorte '{' '.join(d[2] for d in dropped)}' no empieza en "
                f"límite de cláusula."
            )
            continue
        a, b = out[i]
        nb = min(kept_last[1] + 0.10, dropped[0][0])
        nb = max(nb, kept_last[1])
        if nb - a > 0.05:
            out[i] = (a, nb)
            applied += 1
            log(
                f"[silence_cutter] ✂️ Final colgado corregido (seg {i}): fuera "
                f"'{' '.join(d[2] for d in dropped)}'"
            )
    diag["applied"] = applied
    return out, diag


def _derive_self_heal_actions(
    audit: dict,
    *,
    keep_intervals: list[tuple[float, float]],
) -> tuple[list[tuple], list[tuple], list[tuple]]:
    """Convierte los hallazgos del audit en ACCIONES correctivas concretas.

    Devuelve (residue_cuts, guarded_cuts, restores), todas en TIEMPO DE INPUT:
      · residue_cuts — audio sobrante detectado por el audit profundo (mapeado
        del output al input). NO pasan word-guard: el residuo ES una palabra
        (el guard lo protegería); se afinan al valle de energía.
      · guarded_cuts — rellenos estirados supervivientes, palabras sueltas y
        silencios internos. SÍ pasan word-guard (cortes normales).
      · restores — frases PERDIDAS (sobre-corte) que hay que devolver al keep.
    """
    deep = audit.get("deep") or {}
    residue_cuts: list[tuple] = []
    guarded_cuts: list[tuple] = []
    restores: list[tuple] = []
    for b in deep.get("inserted_blocks") or []:
        t0, t1 = b.get("output_t"), b.get("output_t_end")
        if t0 is None or t1 is None:
            continue
        i0 = _map_output_to_input(max(0.0, float(t0) - 0.02), keep_intervals)
        i1 = _map_output_to_input(float(t1) + 0.02, keep_intervals)
        if i0 is not None and i1 is not None and (i1 - i0) > 0.05:
            residue_cuts.append((i0, i1, f"sobrante:'{str(b.get('text',''))[:40]}'"))
    for b in deep.get("missing_blocks") or []:
        s, e = b.get("input_start"), b.get("input_end")
        if s is not None and e is not None and (float(e) - float(s)) > 0.05:
            restores.append((
                max(0.0, float(s) - 0.05), float(e) + 0.05,
                f"perdida:'{str(b.get('text',''))[:40]}'",
            ))
    for p in audit.get("surviving_stretched_preview") or []:
        s, e = p.get("start"), p.get("end")
        if s is not None and e is not None and (float(e) - float(s)) > 0.3:
            # conserva la cabeza de 0.15s del relleno (diseño intencional)
            guarded_cuts.append((float(s) + 0.15, float(e), "relleno_estirado"))
    for p in audit.get("loose_words_preview") or []:
        s, e = p.get("start"), p.get("end")
        if s is not None and e is not None:
            guarded_cuts.append((float(s), float(e), f"palabra_suelta:'{p.get('text','')}'"))
    for p in audit.get("internal_silences_preview") or []:
        s, e = p.get("input_start"), p.get("input_end")
        if s is not None and e is not None and (float(e) - float(s)) > 0.6:
            guarded_cuts.append((float(s) + 0.15, float(e) - 0.15, "silencio_interno"))
    # COHERENCIA: una promesa rota (dice 'dos ingredientes' y falta uno) se
    # arregla RESTAURANDO las palabras que faltan (el juez ya las localizó en
    # tiempo de input → restore_span). Solo defectos arreglables con span.
    for d in audit.get("coherence_issues") or []:
        if not d.get("fixable"):
            continue
        sp = d.get("restore_span")
        if d.get("type") == "promised_item_cut" and sp:
            restores.append((
                max(0.0, float(sp[0]) - 0.05), float(sp[1]) + 0.05,
                f"coherencia:'{str(d.get('missing_text',''))[:40]}'",
            ))
    return residue_cuts, guarded_cuts, restores


def _reanex_stutter_lead_words(
    words: list[dict],
    keep: set[int],
) -> tuple[set[int], int]:
    """Alinea los cortes de TARTAMUDEO a la repetición real. Si un bloque
    eliminado termina en N copias del token que sigue conservado (el holístico
    quitó 'es muy muy' y conservó el 'muy' siguiente), las palabras de CABECERA
    del bloque que no son parte de la repetición se re-anexan — pero solo si
    son pocas (≤2) y funcionales (cortas/stopwords), para no resucitar frases
    enteras que el holístico quitó a propósito. Devuelve (keep, n_fixes)."""
    def _norm(w: dict) -> str:
        return re.sub(r"[^\wáéíóúñü]", "", str(w.get("word", "")).lower())

    n = len(words)
    keep = set(keep)
    fixes = 0
    i = 0
    while i < n:
        if i in keep:
            i += 1
            continue
        j = i
        while j < n and j not in keep:
            j += 1
        block_len = j - i
        if j < n and 2 <= block_len <= 5:
            t_next = _norm(words[j])
            k = j - 1
            reps = 0
            while k >= i and t_next and _norm(words[k]) == t_next:
                reps += 1
                k -= 1
            lead = list(range(i, k + 1))
            if reps >= 1 and 1 <= len(lead) <= 2:
                lead_toks = [_norm(words[m]) for m in lead]
                if all(
                    t and (len(t) <= 3 or t in _AUDIT_STOPWORDS or t in _FILLER_TOKENS)
                    for t in lead_toks
                ):
                    keep.update(lead)
                    fixes += 1
        i = j
    return keep, fixes


_COMMON_VERB_FORMS = {
    "es", "son", "esta", "estan", "están", "estamos", "estoy", "estas", "estás",
    "era", "eran", "fue", "ser", "estar", "hay", "ha", "han", "he", "has",
    "habia", "había", "tiene", "tienen", "tengo", "tienes", "va", "van", "voy",
    "vas", "ir", "seria", "sería", "sera", "será", "sois", "somos", "puedes",
    "puede", "pueden", "quiero", "quiere",
}


# Fuentes de corte de CONTENIDO (IA/lingüísticas): SÍ pueden eliminar una
# palabra hablada a propósito (repetición, falso inicio, muletilla, filler).
_CONTENT_CUT_SOURCES = frozenset({
    "stretched_filler", "ai_holistic", "ai", "ngram_repetition", "ai_pass2",
})
# Fuentes ACÚSTICAS (silencio/energía): solo deben cortar SILENCIO, NUNCA
# comerse una palabra hablada. (auto_trim, inter_word_gap, acoustic, silero…)


def _protect_words_from_acoustic_cuts(
    keep_intervals: list[tuple[float, float]],
    cuts_with_source: list[tuple[float, float, str]],
    words: list[dict],
    *,
    pad: float = 0.06,
    video_duration: float | None = None,
) -> tuple[list[tuple[float, float]], int]:
    """Invariante de robustez anti-OVER-CUT a nivel global.

    Una palabra hablada (detectada por Whisper) solo puede desaparecer si una
    fase de CONTENIDO (holístico/IA/ngram/false-start/filler estirado) la quitó
    a propósito. Las fases ACÚSTICAS (VAD, energía, gap entre palabras, auto-
    trim) existen para cortar SILENCIO — si una de ellas engulló una palabra
    real (su centro cae fuera de los keeps y NINGÚN corte de contenido la quitó),
    se RE-ANEXA al keep. Resuelve el caso real de bugallo: 'proteína', 'un ojo',
    'te lo dejo aquí' comidos por acoustic/silero/inter_word_gap. Solo AÑADE
    keep, nunca corta. Devuelve (keep_intervals, n_palabras_reanexadas)."""
    if not words or not keep_intervals:
        return keep_intervals, 0
    content_cuts = [
        (s, e) for (s, e, src) in cuts_with_source if src in _CONTENT_CUT_SOURCES
    ]
    # 'noise_gap' de la IA: marcó una PAUSA ahí, NO un borrado deliberado. Si
    # tragó una palabra de CONTENIDO (proteína), la re-anexamos; el relleno que
    # la IA cortara bien en ese hueco se queda fuera.
    noise_gap_cuts = [
        (s, e) for (s, e, src) in cuts_with_source if src == "ai_noise_gap"
    ]

    def _in_keep(center: float) -> bool:
        return any(a <= center <= b for a, b in keep_intervals)

    def _content_removed(center: float) -> bool:
        return any(s <= center <= e for s, e in content_cuts)

    def _in_noise_gap(center: float) -> bool:
        return any(s <= center <= e for s, e in noise_gap_cuts)

    def _is_content_word(w: dict) -> bool:
        tok = re.sub(r"[^\wáéíóúñü]", "", str(w.get("word", "")).lower())
        return bool(tok) and tok not in _FILLER_TOKENS and len(tok) > 2

    extra: list[tuple[float, float]] = []
    n_prot = 0
    for w in words:
        try:
            ws, we = float(w["start"]), float(w["end"])
        except (KeyError, ValueError, TypeError):
            continue
        c = (ws + we) / 2.0
        if _in_keep(c):
            continue                       # ya conservada
        if _content_removed(c):
            continue                       # la quitó una fase de contenido → OK
        # Si la engulló un noise_gap de la IA, solo rescatamos CONTENIDO real
        # (no rellenos sueltos que la IA cortó a propósito en esa pausa).
        if _in_noise_gap(c) and not _is_content_word(w):
            continue
        extra.append((ws - pad, we + pad))  # corte acústico / noise_gap con contenido
        n_prot += 1
    if not extra:
        return keep_intervals, 0
    merged = _merge_intervals(list(keep_intervals) + extra)
    if video_duration is not None:
        merged = [
            (max(0.0, a), min(float(video_duration), b)) for a, b in merged
        ]
    return merged, n_prot


def _protect_unique_content(
    words: list[dict],
    keep: set[int],
) -> tuple[set[int], int]:
    """Red de seguridad anti-OVER-CUT del holístico. Si un tramo ELIMINADO
    contiene una palabra de CONTENIDO ÚNICA en toda la transcripción (nombre/
    adjetivo ≥5 chars, no stopword/muletilla/forma de verbo común, que aparece
    UNA sola vez), ese tramo lleva información única real (un ingrediente, un
    dato, un nombre) y se RE-ANEXA al keep. Las repeticiones (freq≥2) y los
    re-takes (formas verbales) NO se protegen → se siguen pudiendo cortar. Solo
    AÑADE al keep, nunca sobre-corta. Casos reales que protege: 'proteína' en
    'los dos ingredientes son proteína y crema de arroz'."""
    n = len(words)
    if not n:
        return keep, 0
    norm = [
        re.sub(r"[^\wáéíóúñü]", "", str(w.get("word", "")).lower())
        for w in words
    ]
    from collections import Counter
    freq = Counter(t for t in norm if t)

    def _is_unique_content(t: str) -> bool:
        return (
            len(t) >= 5 and freq.get(t, 0) == 1
            and t not in _AUDIT_STOPWORDS
            and t not in _FILLER_TOKENS
            and t not in _COMMON_VERB_FORMS
        )

    keep = set(keep)
    added = 0
    i = 0
    while i < n:
        if i in keep:
            i += 1
            continue
        j = i
        while j < n and j not in keep:
            j += 1
        if any(_is_unique_content(norm[k]) for k in range(i, j)):
            for k in range(i, j):
                keep.add(k)
            added += 1
        i = j
    return keep, added


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


def _build_verdict_detail(audit: dict) -> dict:
    """Veredicto EXPLICABLE por dimensiones: convierte el score opaco en algo que
    el operador entiende de un vistazo, y —clave— SEPARA los fallos REALES del
    motor (contenido) de los AVISOS de baja confianza (juez de coherencia sobre
    re-transcripción de Whisper = fuente principal de falsos positivos), y de la
    FUENTE BRUTA (muchas pausas/silencios grabados así, no culpa del motor).

    Es solo PRESENTACIÓN: no cambia el score ni el gating. Devuelve
    {overall: ok|revisar|fallo, label, dimensions[], low_confidence[]}."""
    deep = audit.get("deep") or {}
    n_residue = len(deep.get("inserted_blocks") or [])
    n_missing = len(deep.get("missing_blocks") or [])
    coh_issues = audit.get("coherence_issues") or []
    n_internal = int(audit.get("n_internal_silences") or 0)
    n_loose = int(audit.get("n_loose_words") or 0)
    n_surv = int(audit.get("n_surviving_stretched") or 0)
    n_residue = int(audit.get("n_residue_islands") or 0)
    res_edge = bool(audit.get("residue_head_tail"))
    degraded = not audit.get("transcription_ok", True)

    dims: list[dict] = []

    content_bad: list[str] = []
    if n_residue:
        content_bad.append(f"{n_residue} resto(s) de audio sobrante")
    if n_missing:
        content_bad.append(f"{n_missing} palabra(s) perdida(s)")
    dims.append({"dim": "Contenido", "ok": not content_bad,
                 "detail": "completo" if not content_bad else " · ".join(content_bad)})

    pace_bad: list[str] = []
    if n_internal:
        pace_bad.append(f"{n_internal} pausa(s) larga(s)")
    if n_surv:
        pace_bad.append(f"{n_surv} muletilla(s) estirada(s)")
    dims.append({"dim": "Ritmo", "ok": not pace_bad,
                 "detail": "ágil" if not pace_bad else " · ".join(pace_bad)})

    clean_bad: list[str] = []
    if n_loose:
        clean_bad.append(f"{n_loose} palabra(s) suelta(s)")
    if n_residue:
        clean_bad.append(
            f"{n_residue} hueco(s) sin voz" + (" (arranque/cierre)" if res_edge else "")
        )
    dims.append({"dim": "Limpieza", "ok": not clean_bad,
                 "detail": "sin restos" if not clean_bad else " · ".join(clean_bad)})

    low_conf: list[str] = []
    for c in coh_issues:
        mt = c.get("missing_text") or c.get("original_quote") or "?"
        low_conf.append(
            f"el medidor cree que falta «{mt}» — VERIFICAR (suele ser FALSO: "
            "Whisper a veces no re-oye una palabra que sí está)."
        )

    if degraded:
        overall, label = "fallo", "FALLO — sin transcripción (corte ciego)"
    elif content_bad:
        overall, label = "fallo", "FALLO REAL — revisar contenido"
    elif res_edge or n_residue >= 2:
        overall, label = ("revisar",
                          "ENTREGABLE pero con relleno sin voz "
                          "(arranque/cierre/hueco) — revisar 5s")
    elif n_internal >= 6:
        overall, label = ("revisar",
                          "ENTREGABLE pero algo picado — probable FUENTE bruta "
                          "(pausas/silencios del original), no fallo del motor")
    elif low_conf:
        overall, label = ("revisar",
                          "ENTREGABLE — solo avisos de baja confianza (revisa 5s)")
    else:
        overall, label = "ok", "ENTREGABLE — limpio"

    return {
        "overall": overall, "label": label,
        "dimensions": dims, "low_confidence": low_conf,
        "score": audit.get("quality_score"),
    }


def _absorb_keep_islands(
    keep_intervals: list[tuple[float, float]],
    words: list[dict],
    *,
    min_keep_s: float = 0.28,
) -> tuple[list[tuple[float, float]], list[dict]]:
    """Descarta 'micro-islas' de keep muy cortas (<`min_keep_s`) que NO
    contienen ninguna palabra de CONTENIDO real (token no-filler y len>2).

    Son fragmentos de palabra / cabezas de relleno / slivers que el merge de
    cortes deja entre dos cortes y suenan como media palabra o "mini-corte
    raro". Conservador y agnóstico al origen (los crea tanto `_KEEP_HEAD` de
    fillers estirados como el merge de cortes solapados): una palabra de
    contenido cuyo CENTRO caiga dentro de la isla la protege, así que una
    respuesta corta legítima en conversación (>min_keep_s o con contenido)
    nunca se elimina. Devuelve (keeps_filtrados, islas_absorbidas)."""
    if not keep_intervals:
        return keep_intervals, []
    kept: list[tuple[float, float]] = []
    absorbed: list[dict] = []
    for a, b in keep_intervals:
        if (b - a) >= min_keep_s:
            kept.append((a, b))
            continue
        has_content = False
        for w in (words or []):
            center = (float(w.get("start", 0.0)) + float(w.get("end", 0.0))) / 2.0
            if a <= center <= b:
                tok = re.sub(r"[^\wáéíóúñü]", "", str(w.get("word", "")).lower())
                if tok and tok not in _FILLER_TOKENS and len(tok) > 2:
                    has_content = True
                    break
        if has_content:
            kept.append((a, b))
        else:
            absorbed.append({"start": round(a, 3), "end": round(b, 3), "dur": round(b - a, 3)})
    return kept, absorbed


def _count_residue_islands(
    keep_intervals: list[tuple[float, float]],
    words: list[dict],
    *,
    min_s: float = 0.30,
    pad: float = 0.05,
) -> tuple[int, bool, list[dict]]:
    """Cuenta 'islas de residuo': tramos CONSERVADOS de >=`min_s` que NO solapan
    el span de NINGUNA palabra hablada (voiced). Son dead-air / tos / chasquido /
    respiración que sobrevivieron al corte — justo lo que el usuario ve como
    'empieza tarde sin nada' o '1s al final sin nada'. Un tramo con voz (aunque
    sea un relleno) NO cuenta: eso ya lo cubren loose_words/coherencia. El juez
    no tenía forma de ver esto (solo medía palabras-perdidas/silencios) → un 100
    podía traer basura sin cortar. Devuelve (n, hay_en_cabecera_o_cola, preview);
    el residuo en borde pesa más porque es lo más visible."""
    if not keep_intervals:
        return 0, False, []
    spans = [
        (float(w.get("start", 0.0)), float(w.get("end", 0.0))) for w in (words or [])
    ]
    n = len(keep_intervals)
    out: list[dict] = []
    head_tail = False
    for idx, (a, b) in enumerate(keep_intervals):
        if (b - a) < min_s:
            continue
        has_speech = any(ws < b + pad and we > a - pad for ws, we in spans)
        if has_speech:
            continue
        is_edge = (idx == 0 or idx == n - 1)
        head_tail = head_tail or is_edge
        out.append({"start": round(a, 3), "end": round(b, 3),
                    "dur": round(b - a, 3), "edge": is_edge})
    return len(out), head_tail, out


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
    words: list[dict] | None = None,
) -> list[dict]:
    """Rellenos estirados (un 'la'/risa de ~2s) que NO se cortaron: siguen
    solapando una zona conservada ≥ `min_overlap_s` → audibles en el corte.

    NO penaliza una palabra de CONTENIDO real cuyo span Whisper infló (palabra
    + pausa absorbida, p.ej. 'asegúrate' marcada 2.6s): el editor la conservó
    BIEN — penalizar el score por dejar una palabra real es incorrecto. Solo
    cuentan los rellenos de verdad (token corto/funcional/filler estirado). La
    pausa absorbida dentro sí la coge el detector de silencio interno aparte."""
    if not stretched_spans or not keep_intervals:
        return []

    def _span_is_content(a: float, b: float) -> bool:
        for w in (words or []):
            try:
                ws, we = float(w["start"]), float(w["end"])
            except (KeyError, ValueError, TypeError):
                continue
            if abs(ws - a) < 0.02 and abs(we - b) < 0.02:
                tok = re.sub(r"[^\wáéíóúñü]", "", str(w.get("word", "")).lower())
                return (
                    len(tok) >= 5
                    and tok not in _FILLER_TOKENS
                    and tok not in _AUDIT_STOPWORDS
                )
        return False

    surv: list[dict] = []
    for a, b in stretched_spans:
        if _span_is_content(a, b):
            continue  # palabra real conservada → no es un relleno superviviente
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


# Tokens que Whisper ALUCINA típicamente en silencio (créditos YouTube, ruido).
# Aunque sean ≥5 chars y "parezcan" contenido, sí son fantasmas legítimos.
_WHISPER_HALLUCINATION_TOKENS = frozenset({
    "gracias", "suscribete", "suscribirte", "suscribios", "suscribanse",
    "subtitulos", "subtitulado", "comparte", "comenta", "amara", "amaraorg",
})


def _is_real_content_word(
    w: dict, prev_w: dict | None, next_w: dict | None,
    *, max_contig_gap_s: float = 0.5,
) -> bool:
    """¿Es una palabra de CONTENIDO real (no una alucinación de Whisper)?

    Whisper alucina en silencio tokens CORTOS/funcionales ('y', 'eh', 'que')
    o créditos ('gracias', 'suscríbete') — AISLADOS en el silencio. Una palabra
    de contenido (≥5 chars, no filler/stopword/crédito) que además es CONTIGUA
    (gap ≤ `max_contig_gap_s`) a otra palabra forma parte de un RUN de habla
    real que el VAD/amplitud no detectó por voz floja / mala SNR — NO es
    fantasma. Distingue 'proteína' (pegada a 'crema') de un 'gracias' suelto al
    final. Conservador: ante voz floja real preferimos NO borrar contenido."""
    tok = re.sub(r"[^\wáéíóúñü]", "", str(w.get("word", "")).lower())
    if (
        len(tok) < 5
        or tok in _FILLER_TOKENS
        or tok in _AUDIT_STOPWORDS
        or tok in _WHISPER_HALLUCINATION_TOKENS
    ):
        return False
    try:
        ws, we = float(w["start"]), float(w["end"])
    except (KeyError, ValueError, TypeError):
        return False
    contiguous = False
    for nb in (prev_w, next_w):
        if nb is None:
            continue
        try:
            ns, ne = float(nb["start"]), float(nb["end"])
        except (KeyError, ValueError, TypeError):
            continue
        gap = ns - we if ns >= we else ws - ne  # gap al vecino (cualquier lado)
        if gap <= max_contig_gap_s:
            contiguous = True
            break
    return contiguous


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

    EXCEPCIÓN (anti over-cut): una palabra de CONTENIDO real contigua a otra
    (`_is_real_content_word`) NO se marca fantasma aunque caiga en un silencio
    Silero — es voz floja que el VAD no detectó (mala SNR), no una alucinación.
    Caso real de bugallo: Silero marcó silencio [11.6-12.9] y descartaba
    'proteína' (ingrediente, pegada a 'crema de arroz').

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
    for i, w in enumerate(words):
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
        # Guarda de contenido: voz floja real (no alucinación) → NO fantasma.
        if is_phantom and _is_real_content_word(
            w, words[i - 1] if i > 0 else None,
            words[i + 1] if i + 1 < len(words) else None,
        ):
            is_phantom = False
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

# Palabras funcionales (artículos, preposiciones, conjunciones, pronombres
# cortos) que NO cuentan como "contenido perdido" en el AUDIT PROFUNDO. Si una
# de estas falta/cambia en la re-transcripción suele ser varianza de Whisper o
# un tartamudeo del original ("…estampados que hay que hay un montón…"), NO un
# sobre-corte real. Las pérdidas que de verdad importan son nombres/verbos/
# adjetivos (euros, precioso, estampados…). Solo se usa para el conteo de
# contenido del audit — no afecta a la detección de cortes.
_AUDIT_STOPWORDS = {
    "que", "de", "la", "el", "los", "las", "un", "una", "unos", "unas",
    "con", "por", "en", "es", "son", "se", "lo", "le", "les", "su", "sus",
    "y", "o", "u", "a", "al", "del", "me", "te", "nos", "mi", "tu", "no",
    "ya", "mas", "más", "hay", "ha", "he", "has", "si", "sí", "ni", "muy",
    "este", "esta", "está", "están", "estás", "esto", "estos", "estas",
    "esos", "esas", "eso", "esa", "ese", "como", "cómo", "para", "pero",
    "porque", "aquí", "aqui", "ahí", "ahi", "allí", "alli", "así", "asi",
    "tan", "todo", "toda", "todos", "todas", "qué", "sus", "les", "soy",
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
    for i, w in enumerate(words):
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
        # Guarda de contenido: voz floja real contigua a otra palabra (no una
        # alucinación aislada) nunca es fantasma aunque el silencio la flanquee.
        if flanked and _is_real_content_word(
            w, words[i - 1] if i > 0 else None,
            words[i + 1] if i + 1 < len(words) else None,
        ):
            flanked = False
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
    system_prompt = _with_lessons(prompt_path.read_text(encoding="utf-8"), "analyst")

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
        temperature=0.0,           # determinista (antes 0.2)
        seed=_HOLISTIC_SEED,       # mismo input = mismos cortes siempre
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


def _parse_ai_cuts_tagged(
    cuts_raw: list[dict],
    *,
    words: list[dict],
    video_duration: float,
) -> list[tuple[float, float, str]]:
    """Como `_parse_ai_cuts` pero CONSERVA el `reason` de cada corte. Sirve para
    distinguir los 'noise_gap' (la IA adivina una PAUSA, no un borrado de
    contenido deliberado) del resto. Si en un noise_gap había una palabra de
    contenido real (caso 'proteína'), word-protection la re-anexa."""
    n = len(words)
    out: list[tuple[float, float, str]] = []
    for cut in cuts_raw:
        try:
            i0 = int(cut.get("start_word_idx"))
            i1 = int(cut.get("end_word_idx"))
        except (TypeError, ValueError):
            continue
        ts, te = cut.get("t_start"), cut.get("t_end")
        if i0 in (-1, -2):
            if ts is None or te is None:
                continue
            t0, t1 = float(ts), float(te)
        else:
            if not (0 <= i0 <= i1 < n):
                continue
            t0 = float(ts) if ts is not None else float(words[i0]["start"])
            t1 = float(te) if te is not None else float(words[i1]["end"])
        t0 = max(0.0, min(video_duration, t0))
        t1 = max(0.0, min(video_duration, t1))
        if t1 - t0 > 0.05:
            out.append((t0, t1, str(cut.get("reason") or "")))
    return out


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


def _content_end_output_s(
    keep_intervals: list[tuple[float, float]], audio_path: str
) -> float | None:
    """Instante de OUTPUT (s) justo tras el ÚLTIMO audio REAL (energía) del
    último keep. Sirve para anclar el fade de cierre SOLO sobre el silencio
    post-voz, de modo que NUNCA clipe la última palabra: Whisper sub-reporta la
    cola fricativa final ("-s"/"-tas"), pero la energía no. Si la voz llena el
    último keep (no hay cola muda), devuelve ~total → no habrá fade. None si no
    se puede medir (decode/formato/silencio) → el llamador usa un fade mínimo."""
    if not keep_intervals or not audio_path or not os.path.exists(audio_path):
        return None
    import wave
    try:
        with wave.open(audio_path, "rb") as wf:
            sr = wf.getframerate(); n_ch = wf.getnchannels()
            sampwidth = wf.getsampwidth(); raw = wf.readframes(wf.getnframes())
    except Exception:
        return None
    if sampwidth != 2 or sr <= 0:
        return None
    import numpy as np
    audio = np.frombuffer(raw, dtype=np.int16)
    if n_ch > 1:
        audio = audio.reshape(-1, n_ch).mean(axis=1)
    audio = audio.astype(np.float64)
    ls, le = keep_intervals[-1]
    i0 = max(0, int(ls * sr)); i1 = min(len(audio), int(le * sr))
    win = max(1, int(0.020 * sr)); hop = max(1, int(0.010 * sr))
    if i1 - i0 < win * 2:
        return None
    seg = audio[i0:i1]
    ts: list[float] = []; rms: list[float] = []
    pos = 0
    while pos + win <= len(seg):
        s = seg[pos:pos + win]
        rms.append(float(np.sqrt(np.mean(s * s))) + 1e-9)
        ts.append(ls + (pos + win / 2) / sr)
        pos += hop
    if len(rms) < 3:
        return None
    a = np.array(rms)
    # umbral relativo: suelo local (percentil 20) +12 dB, o -48 dBFS absoluto.
    floor = float(np.percentile(a, 20))
    thr = max(floor * (10.0 ** (12.0 / 20.0)), 32768.0 * 0.004)
    voiced = np.where(a > thr)[0]
    if len(voiced) == 0:
        return None
    last_src = min(le, ts[int(voiced[-1])] + 0.06)  # +60 ms de cola natural
    acc = 0.0
    for s, e in keep_intervals:
        if last_src <= e:
            return acc + max(0.0, last_src - s)
        acc += (e - s)
    return acc


def _extend_last_keep_to_word_tail(
    keep_intervals: list[tuple[float, float]],
    audio_path: str,
    video_duration: float,
) -> list[tuple[float, float]]:
    """Extiende el FINAL del último keep para cubrir la cola fricativa real de la
    ÚLTIMA palabra ("-s"/"-tas"). El detector de tail_silence + el guard de
    palabra cortan en el fin de palabra de Whisper (sub-reportado) y dejan fuera
    la cola decreciente → "cuentas" suena como "cuento". Aquí escaneamos hacia
    delante con umbral de SUELO DE RUIDO ABSOLUTO (no relativo al borde, que cae
    demasiado rápido) y extendemos hasta el silencio post-voz real. Solo el último
    keep; cap +0.4 s y duración del vídeo. Determinista; cualquier fallo → keeps
    intactos."""
    if not keep_intervals or not audio_path or not os.path.exists(audio_path):
        return keep_intervals
    import wave
    try:
        with wave.open(audio_path, "rb") as wf:
            sr = wf.getframerate(); n_ch = wf.getnchannels()
            sampwidth = wf.getsampwidth(); raw = wf.readframes(wf.getnframes())
    except Exception:
        return keep_intervals
    if sampwidth != 2 or sr <= 0:
        return keep_intervals
    import numpy as np
    audio = np.frombuffer(raw, dtype=np.int16)
    if n_ch > 1:
        audio = audio.reshape(-1, n_ch).mean(axis=1)
    amp = np.abs(audio.astype(np.float64))
    ls, le = keep_intervals[-1]
    hi = min(len(amp) / sr, le + 0.40, float(video_duration))
    if hi <= le + 0.02:
        return keep_intervals
    win = max(1, int(0.020 * sr)); hop = max(1, int(0.010 * sr))

    def _rms(i0: int) -> float:
        seg = amp[i0:i0 + win]
        return float(np.sqrt(np.mean(seg * seg))) if len(seg) else 0.0

    # Umbral RELATIVO al pico de voz de la última palabra (últimos 0.5 s del
    # keep), no al suelo de ruido (que en audio con mucha voz sube demasiado y
    # deja fuera la fricativa). 35 dB bajo el pico capta la cola "-s"/"-tas".
    p0 = max(int((le - 0.5) * sr), int(ls * sr), 0)
    p1 = int(le * sr)
    peak = 0.0
    j = p0
    while j + win <= p1:
        peak = max(peak, _rms(j)); j += hop
    if peak <= 1.0:
        return keep_intervals
    thr = peak * (10.0 ** (-35.0 / 20.0))
    t = le; last_voiced = le; silent = 0.0
    while t < hi:
        if _rms(int(t * sr)) > thr:
            last_voiced = t + win / sr; silent = 0.0
        else:
            silent += hop / sr
            if silent >= 0.12 and last_voiced > le:
                break
        t += hop / sr
    new_le = min(float(video_duration), last_voiced + 0.06)
    if new_le > le + 0.02:
        kk = list(keep_intervals)
        kk[-1] = (ls, new_le)
        return kk
    return keep_intervals


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
    content_end_s: float | None = None,
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
    _FADE_TAIL_S = 0.25  # fade-out del cierre — enmascara el residuo de render
    #                      tras la última palabra (cola de boca/lookahead loudnorm)

    filter_parts: list[str] = []
    concat_inputs: list[str] = []
    for i, (start, end) in enumerate(keep_intervals):
        filter_parts.append(
            f"[0:v]trim=start={start:.3f}:end={end:.3f},"
            f"setpts=PTS-STARTPTS{extra_vf}[v{i}]"
        )
        seg_dur = end - start
        # Micro-fade de 20ms en cada segmento (anti-clic de concat). El fade de
        # CIERRE grande ya NO se hace aquí: se aplica DESPUÉS de loudnorm (si no,
        # loudnorm ve la cola desvanecida y SUBE la ganancia para compensar →
        # amplifica el residuo del final = el "burst" del último frame).
        fade_out_d = _FADE_S
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

    # Cadena de audio de salida tras el concat: loudnorm (si toca) y SIEMPRE un
    # fade-out de cierre FINAL como ÚLTIMA operación. CLAVE: el fade va DESPUÉS de
    # loudnorm. Si fuera antes (en los segmentos), loudnorm vería la cola
    # desvaneciéndose y SUBIRÍA la ganancia para mantener −16 LUFS, amplificando
    # el residuo del final = el "burst"/ruido del último frame. Aplicándolo
    # después, loudnorm trabaja a nivel pleno (sin subir ganancia) y el fade
    # cierra limpio → nunca hay ruido raro al final. Robusto y general.
    total_output_s = sum(end - start for start, end in keep_intervals)
    a_out = "[outa]"
    _chain: list[str] = []
    if normalize_audio:
        _chain.append("[outa]loudnorm=I=-16:TP=-1.5:LRA=11[outa_norm]")
        a_out = "[outa_norm]"
    # Fade de cierre ANCLADO al fin del audio real (content_end_s): cubre SOLO el
    # silencio post-voz → JAMÁS clipa la última palabra. Si la voz llena el último
    # keep (content_end≈total) el fade es 0 (no hay cola que desvanecer; la voz se
    # respeta entera). Sin ese dato, fade mínimo de seguridad. La duración nunca
    # empieza antes de content_end porque d ≤ total−content_end.
    if content_end_s is not None:
        _fade_d = min(_FADE_TAIL_S, max(0.0, total_output_s - float(content_end_s)))
    else:
        _fade_d = min(0.06, max(0.0, total_output_s - 0.15))
    if _fade_d >= 0.05:
        _fst = max(0.0, total_output_s - _fade_d)
        _chain.append(f"{a_out}afade=t=out:st={_fst:.3f}:d={_fade_d:.3f}[outa_fin]")
        a_out = "[outa_fin]"
    norm_part = (";" + ";".join(_chain)) if _chain else ""

    concat_filter = (
        "".join(concat_inputs) + f"concat=n={n}:v=1:a=1[outv][outa]"
    )
    filter_complex = ";".join(filter_parts) + ";" + concat_filter + norm_part

    # Duración esperada del output (suma de keep_intervals) → ms para que el
    # progress callback sepa contra qué comparar `out_time_ms` y dar % real.
    total_output_ms = int(total_output_s * 1000)

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
        # Sube el umbral inter-frase de 0.5s → 0.8s: más suave que el monólogo
        # (preserva las micro-pausas de turn-taking <0.8s) pero SÍ corta las
        # pausas largas (≥0.8s). CLAVE: a 1.2s (valor antiguo) un vídeo de
        # creador con muchas pausas medias (0.8-1.2s) quedaba PICADO —
        # demasiadas pausas conservadas → vídeo lento + el audit las penaliza.
        # Estos son ads de TikTok (snappy), no podcasts: 0.8s es el equilibrio.
        new_config["inter_word_gap_threshold_s"] = max(
            0.8, float(config.get("inter_word_gap_threshold_s", 0.5))
        )
        # Padding que se conserva tras el corte: 250ms (entre el 200 del
        # monólogo y el 350 antiguo) → la pausa resultante queda por debajo del
        # umbral del audit (no la cuenta como silencio) y no suena seca.
        new_config["inter_word_gap_keep_ms"] = max(
            250, int(config.get("inter_word_gap_keep_ms", 200))
        )
    return new_config
