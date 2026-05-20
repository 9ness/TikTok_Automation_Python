"""Herramienta: subtítulos automáticos karaoke.

Reusa la pipeline existente del nicho Creator Reward → Subs Auto:
- `src.subtitles_only.extract_audio_from_video` para extraer audio
- `src.subtitles_only.transcribe_with_reference` para Whisper local
- `src.subtitles_only.render_subtitles_on_video` para render karaoke
- `src.subtitles_only.STYLE_PRESETS` para presets visuales

NO toca timestamps del vídeo — solo añade un overlay. Por eso su
`position_weight` es alto (90) → siempre se ejecuta al final, después
de cualquier herramienta que recorte el vídeo (silence_cutter, etc.).
"""

from __future__ import annotations

from typing import Any

from src.editor_auto.config import TOOL_POSITION_WEIGHTS, TOOL_SUBS_AUTO

from .base import ToolContext


# Modelos Whisper soportados (mismo set que el router subs_auto existente).
_WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v3"]
_QUALITY_LABELS = ["1080p (Lento)", "720p (Medio)", "480p (Rápido)", "240p (Ultra Rápido)"]
_AUDIO_TYPES = ["speech", "music"]


class SubsAutoTool:
    tool_id: str = TOOL_SUBS_AUTO
    display_name: str = "Subtítulos automáticos"
    description: str = (
        "Genera subtítulos karaoke palabra-a-palabra con Whisper local + "
        "overlay sobre el vídeo. Sin coste de API (Whisper corre en local)."
    )
    position_weight: int = TOOL_POSITION_WEIGHTS[TOOL_SUBS_AUTO]

    def default_config(self) -> dict[str, Any]:
        # Default = preset "TikTok Classic" del STYLE_PRESETS existente.
        from src.subtitles_only import STYLE_PRESETS

        preset_name = "🔴 TikTok Classic (Impact + píldora)"
        preset = STYLE_PRESETS.get(preset_name, next(iter(STYLE_PRESETS.values())))
        # Vocabulario por defecto — se pasa como `initial_prompt` a Whisper
        # para reducir errores de transcripción de palabras clave del nicho
        # TikTok Shop / afiliados (carrito, link, descuento, etc.). Ayuda
        # con audio sucio o conversaciones rápidas. El operador puede
        # editarlo libremente o vaciarlo para usar Whisper sin contexto.
        default_vocab = (
            "Esta es una conversación sobre productos de TikTok Shop y Amazon. "
            "Vocabulario relevante: carrito, link en mi perfil, enlace, "
            "código descuento, oferta, comprar, envío gratis, calidad, "
            "valoración, reseña, opinión, recomendación, tienda, checkout."
        )
        return {
            "preset_name": preset_name,
            "model_size": "small",
            "language": None,            # auto-detect
            "audio_type": "speech",
            "quality_label": "1080p (Lento)",
            "reference_text": default_vocab,
            # Pre-procesar audio con ffmpeg `afftdn` (FFT denoise) antes de
            # Whisper. Mejora ~5-10% en audios con ruido de fondo o voces
            # de baja calidad. Coste: +5-10s al pipeline. OFF por defecto
            # para no ralentizar lo que ya va bien.
            "audio_denoise": False,
            # Estilo (copiado del preset — la UI puede sobreescribir cada uno)
            "font_path": preset["font_path"],
            "highlight_mode": preset["highlight_mode"],
            "highlight_color": preset["highlight_color"],
            "text_color": preset["text_color"],
            "stroke_color": preset["stroke_color"],
            "stroke_width": preset["stroke_width"],
            "case_mode": preset["case_mode"],
            "font_scale": preset["font_scale"],
            "max_words": preset.get("max_words_per_chunk", 3),
            "y_position": preset["y_position_pct"],
            "pill_enabled": preset.get("pill_enabled", True),
            "max_width": preset.get("max_width_pct", 0.85),
            "sync_offset": 0,
        }

    def config_schema(self) -> list[dict[str, Any]]:
        # Esquema declarativo — la UI pinta formulario + preview WYSIWYG
        # sobre estos campos. Tipos no triviales:
        #   font_picker     → carga GET /api/v1/fonts y guarda el `path`
        #   preset_picker   → carga GET /api/v1/creator-reward/subs-auto/presets
        #   highlight_mode  → select cerrado (mismos valores que subs_only)
        _HIGHLIGHT_MODES = ["pill", "color_swap", "underline", "box_outline", "glow", "none"]
        _CASE_MODES = ["UPPERCASE", "lowercase", "Title Case", "None"]
        return [
            # --- Transcripción ---
            {"key": "model_size", "label": "Modelo Whisper", "type": "select",
             "options": _WHISPER_MODELS},
            {"key": "language", "label": "Idioma (vacío = auto)", "type": "string"},
            {"key": "audio_type", "label": "Tipo de audio", "type": "select",
             "options": _AUDIO_TYPES},
            {"key": "quality_label", "label": "Calidad render", "type": "select",
             "options": _QUALITY_LABELS},
            {"key": "reference_text",
             "label": "Vocabulario / contexto (opcional, mejora precisión)",
             "type": "text"},
            {"key": "audio_denoise",
             "label": "Denoise audio antes de Whisper (más lento, mejor en audio sucio)",
             "type": "bool"},
            # --- Estilo visual (afecta preview) ---
            {"key": "preset_name", "label": "Preset visual", "type": "preset_picker"},
            {"key": "font_path", "label": "Fuente", "type": "font_picker"},
            {"key": "highlight_mode", "label": "Modo highlight", "type": "select",
             "options": _HIGHLIGHT_MODES},
            {"key": "case_mode", "label": "Mayúsculas/minúsculas", "type": "select",
             "options": _CASE_MODES},
            {"key": "highlight_color", "label": "Color resaltado", "type": "color"},
            {"key": "text_color", "label": "Color texto", "type": "color"},
            {"key": "stroke_color", "label": "Color borde", "type": "color"},
            {"key": "stroke_width", "label": "Grosor borde", "type": "int",
             "min": 0, "max": 10},
            {"key": "font_scale", "label": "Tamaño fuente (% altura)",
             "type": "float", "min": 0.02, "max": 0.10, "step": 0.005},
            {"key": "max_words", "label": "Palabras por chunk",
             "type": "int", "min": 1, "max": 8},
            {"key": "max_width", "label": "Ancho máximo (% pantalla)",
             "type": "float", "min": 0.5, "max": 1.0, "step": 0.05},
            {"key": "y_position", "label": "Posición vertical (0-1)",
             "type": "float", "min": 0.0, "max": 1.0, "step": 0.01},
            {"key": "sync_offset", "label": "Offset sync (ms)",
             "type": "int", "min": -2000, "max": 2000, "step": 50},
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
        import os
        import time

        from src.subtitles_only import (
            QUALITY_FROM_SIDEBAR,
            extract_audio_from_video,
            render_subtitles_on_video,
            transcribe_with_reference,
        )

        quality_label = config.get("quality_label", "1080p (Lento)")
        quality = QUALITY_FROM_SIDEBAR.get(
            quality_label,
            {"preset": "medium", "crf": 20, "max_long_side": 1280},
        )

        ctx.on_progress(0.02, "🔊 Extrayendo audio…")
        ctx.on_log("[subs_auto] Extrayendo audio del vídeo…")
        tmp_audio = os.path.join(
            ctx.temp_folder,
            f"editor_subs_audio_{ctx.job_id}_{int(time.time())}.mp3",
        )
        extract_audio_from_video(input_path, tmp_audio)

        # Denoise opcional con ffmpeg `afftdn`. Mejora 5-10% en audios con
        # ruido de fondo / voz lejana. Re-encodea a MP3 (mismo formato que
        # extract_audio_from_video) para que el resto del pipeline siga
        # tratándolo igual. Si falla, se sigue con el audio original.
        if bool(config.get("audio_denoise", False)):
            ctx.on_progress(0.06, "🎚️ Denoise audio…")
            ctx.on_log("[subs_auto] afftdn denoise activo…")
            denoised = tmp_audio + ".denoised.mp3"
            import subprocess as _sp
            try:
                _sp.run(
                    ["ffmpeg", "-y", "-loglevel", "error",
                     "-i", tmp_audio,
                     "-af", "afftdn=nr=12:nf=-25",
                     "-acodec", "libmp3lame", "-b:a", "128k",
                     denoised],
                    check=True, capture_output=True, timeout=180,
                )
                os.replace(denoised, tmp_audio)
                ctx.on_log("[subs_auto] ✅ Audio denoised")
            except _sp.CalledProcessError as e:
                stderr = (e.stderr or b"").decode("utf-8", errors="ignore")[:200]
                ctx.on_log(
                    f"[subs_auto] ⚠️ afftdn falló ({stderr}) — uso audio original."
                )
                try:
                    os.remove(denoised)
                except OSError:
                    pass

        try:
            ctx.on_progress(0.10, "🎙️ Whisper transcribiendo…")
            ref = (config.get("reference_text") or "").strip() or None

            def _on_transcribe_progress(frac: float, msg: str) -> None:
                # Whisper [0..1] → sub-slot [0.10..0.55] de esta herramienta.
                ctx.on_progress(0.10 + frac * 0.45, msg)

            words = transcribe_with_reference(
                tmp_audio,
                reference_script=ref,
                model_size=config.get("model_size", "small"),
                language=config.get("language") or None,
                audio_type=config.get("audio_type", "speech"),
                progress_callback=_on_transcribe_progress,
            )
            if not words:
                raise RuntimeError(
                    "Whisper no detectó palabras. Prueba un modelo más grande."
                )
            ctx.on_log(f"[subs_auto] {len(words)} palabras transcritas")
        finally:
            try:
                os.remove(tmp_audio)
            except OSError:
                pass

        ctx.on_progress(0.58, "🎬 Render overlay subtítulos…")
        style = {
            "font_path": config["font_path"],
            "highlight_mode": config["highlight_mode"],
            "highlight_color": config["highlight_color"],
            "text_color": config["text_color"],
            "stroke_color": config["stroke_color"],
            "stroke_width": config["stroke_width"],
            "case_mode": config["case_mode"],
            "font_scale": config["font_scale"],
            "max_words_per_chunk": config["max_words"],
            "y_position_pct": config["y_position"],
            "pill_enabled": config.get("pill_enabled", True),
            "max_width_pct": config.get("max_width", 0.85),
            "sync_offset_ms": config.get("sync_offset", 0),
        }
        render_subtitles_on_video(
            input_path, words, style, output_path,
            quality_settings=quality,
            log_callback=ctx.on_log,
            logger=None,
        )
        ctx.on_progress(1.0, "✅ Subtítulos aplicados")
        return output_path
