"""Modelo VideoPreset — blueprint precocinado para generar un vídeo TikTok
Shop de un producto.

Cada producto puede tener N presets. El user los crea pulsando "Generar"
en el tab Presets del producto (que llama a Gemini con uno de los 2
directores: music_bof o scripted_bof). Tambien se pueden añadir/editar
a mano.

En `/tiktok-shop/generate`, cuando el user selecciona producto+tier,
aparecen los presets compatibles como cards clickables — al elegir uno,
se autorrellena el form de generación.

Hay 2 tipos (`kind`):
- `music`    — vídeo 8-15s sin voz, solo música + texto en pantalla.
  Campos clave: `text_overlay`, `music_mood`, `duration_s`, `seedance_prompt`,
  `veo3_prompt`.
- `scripted` — vídeo creator-style con narración, hooks, CTA.
  Campos clave: `title`, `voice_script`, `hooks_alternatives[]`, `cta`,
  `oratory_tips`, `keywords[]`, ángulo, `seedance_prompt`, `veo3_prompt`.

Ambos tipos llevan SIEMPRE un `seedance_prompt` (corto, para Standard/
Advanced i2v) y un `veo3_prompt` (rico, para Veo 3 prompt-only). Para
el tier `pro` (ref2v multi-shot), si es `scripted` el runtime divide el
voice_script en escenas usando el `seedance_prompt` como guía general.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Ángulos de venta soportados (matchea el prompt 2). El user puede
# crear ángulos custom — esto es solo la enumeración sugerida.
SUGGESTED_ANGLES = [
    "dolor",
    "identidad",
    "estatus",
    "nostalgia",
    "comodidad",
    "ahorro",
    "urgencia",
    "miedo",
    "deseo",
    "humor",
    "lifestyle",
    "verano",
    "gym",
    "productividad",
    "estetica",
]


PresetKind = Literal["music", "scripted"]
Tier = Literal[
    "standard", "advanced", "pro", "veo3_prompt_only", "nano_banana_prompt_only",
]


# Posiciones del texto overlay sobre el vídeo.
TEXT_OVERLAY_POSITIONS = [
    "top_center", "top_left", "top_right",
    "middle_center", "middle_left", "middle_right",
    "bottom_center", "bottom_left", "bottom_right",
]

# Animaciones de entrada/salida del texto overlay.
TEXT_OVERLAY_ANIMATIONS = [
    "none", "fade_in", "slide_up", "slide_down", "pop", "typing",
    "shake", "bounce",
]


class TextOverlayStyle(BaseModel):
    """Configuración visual del texto overlay del vídeo. El text_overlay
    propiamente dicho (lo que dice) está en VideoPreset.text_overlay —
    esto es solo el estilo de presentación."""

    # Path absoluto a la fuente .ttf/.otf (del registry /api/v1/fonts) o
    # nombre del font de sistema. Vacío = usa default del runner.
    font: str = ""
    # tamaño en píxeles relativos al ancho 1080p (40 ~ tamaño TikTok típico)
    size_px: int = 56
    color: str = "#FFFFFF"            # hex
    stroke_color: str = "#000000"     # contorno
    stroke_width: int = 6             # px
    position: str = "top_center"       # ver TEXT_OVERLAY_POSITIONS
    # Override exacto de Y como % del alto del frame (0-100). 12 = 12%
    # desde arriba (justo debajo de la safe zone superior). Si quieres
    # ignorarlo y usar el slot nombrado, deja 12.0 (matchea top_center).
    position_y_pct: float = 12.0
    animation: str = "fade_in"         # ver TEXT_OVERLAY_ANIMATIONS
    uppercase: bool = True
    # Fondo del texto: "none" (sin), "black_bar" (banda negra),
    # "white_bar" (banda blanca, combina con texto negro), "blur".
    background: str = "none"
    # Cuánto tiempo aparece el hook en pantalla. Default 4s = ventana
    # "stop scroll" típica de TikTok. Si quieres que dure todo el vídeo,
    # pon un valor >= duration_s del preset.
    duration_s: float = 4.0


class SubtitleStyle(BaseModel):
    """Configuración de los subtítulos karaoke del vídeo (cuando hay
    voz). Si `enabled=False`, el runner no añade subtítulos."""

    enabled: bool = True
    # Path absoluto a la fuente (registry). Vacío → default del runner.
    font: str = ""
    # Tamaño relativo a 1080p (alto del frame). 42px sobre 1920px de alto
    # ≈ font_scale 0.022 → ~30px en 720p. Más legible y dentro de safe
    # zone TikTok. Antes era 48 que en 1080p sale muy grande.
    size_px: int = 42
    color: str = "#FFFFFF"
    stroke_color: str = "#000000"
    stroke_width: int = 5
    # Posición de los subtítulos en el frame. Mismas opciones que el overlay.
    position: str = "bottom_center"
    # Posición vertical exacta como % del alto del frame (0-100). Override
    # fino sobre el slot nombrado en `position` — útil para mover los
    # subs unos píxeles arriba/abajo sin cambiar de slot. 75 ≈ banda
    # inferior-segura de TikTok. Si `position` ya marca slot, `position_y_pct`
    # tiene prioridad cuando se renderiza.
    position_y_pct: float = 75.0
    # Modo de resaltado de la palabra activa (karaoke). "none" desactiva
    # el karaoke — los subs salen palabra a palabra pero sin destacar la
    # actual. Opciones: pill, color_swap, underline, box_outline, glow, none.
    highlight_mode: str = "pill"
    # Karaoke: color de la palabra activa (resaltada al sonar). Ignorado
    # cuando `highlight_mode = "none"`.
    highlight_color: str = "#FFE066"
    # Máximo de palabras por línea de subtítulo (chunks).
    max_words_per_line: int = 3
    uppercase: bool = False
    # Animación de entrada por palabra (palabra a palabra).
    animation: str = "fade_in"        # ver TEXT_OVERLAY_ANIMATIONS
    # Margen lateral en % del ancho del frame por cada lado (izda + dcha).
    # 8 = 8% margen izda + 8% dcha → ancho útil 84%. TikTok añade UI
    # (avatar, descripción, music) en los bordes; mantener margen evita
    # que los subs solapen con esos elementos. Mínimo recomendado: 5-10%.
    margin_x_pct: float = 8.0


class CtaArrowStyle(BaseModel):
    """Sticker animado (.mov) de una flecha que apunta hacia abajo, hacia
    donde TikTok muestra el botón naranja del carrito al ver un vídeo
    affiliate. El sticker EN SÍ es negro o rojo (no naranja) — "naranja"
    se refiere solo al carrito de la UI nativa de TikTok al que apunta.
    Aparece en los últimos N segundos del vídeo. Los assets viven en
    `TIKTOK_EDITOR/Assets/flechas/` (`flecha_negra.mov`, `flecha_roja.mov`)."""

    enabled: bool = False
    # Nombre del archivo en TIKTOK_EDITOR/Assets/flechas/.
    # Valores típicos: "flecha_negra.mov", "flecha_roja.mov".
    sticker_file: str = "flecha_negra.mov"
    # Posición en % del frame (0-100). El botón "Comprar ahora" / carrito
    # de TikTok Shop aparece abajo-IZQUIERDA en la UI nativa (justo
    # encima del username, bajo el área de captions). La flecha apunta
    # hacia ahí desde aproximadamente x=15% (margen izquierdo), y=75%
    # (parte baja, sin tapar el caption).
    position_x_pct: float = 15.0
    position_y_pct: float = 75.0
    # Tamaño relativo al ancho del frame (10-50%).
    scale_width_pct: float = 25.0
    # Rotación en grados. Default 90 = apunta HACIA ABAJO (al carrito
    # nativo de TikTok). El asset .mov por defecto apunta a la derecha
    # (→); +90 = horario lo gira a ↓. Antes era 0 → vídeos generados
    # tenían la flecha apuntando a la derecha hacia el botón compartir,
    # no al carrito.
    rotation_deg: int = 90
    flip_horizontal: bool = False
    flip_vertical: bool = False
    # Cuántos segundos aparece. Default 4s al final del vídeo.
    duration_seconds: float = 4.0
    # Si True, fuerza que aparezca en los últimos `duration_seconds` del
    # vídeo (final = CTA). Si False, aparece desde la marca configurada
    # (no implementado todavía; siempre se usa True en MVP).
    show_at_end: bool = True


class VideoPreset(BaseModel):
    """Blueprint para generar 1 vídeo concreto del producto."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""                  # display name: "Urgencia 15s · Standard"
    kind: PresetKind = "scripted"
    angle: str = ""                 # vacío si kind=music. Ej: "urgencia", "dolor"
    # Sólo aplica a scripted. Diferencia entre vídeo con voz en off sobre
    # planos del producto (`voiceover` — funciona en todos los tiers) y
    # creator hablando a cámara con lip-sync (`creator_pov` — solo Pro
    # con foto de persona, o Veo 3 prompt-only nativo).
    style: str = ""                 # "voiceover" | "creator_pov" | ""
    # Single-shot (1 plano continuo) vs multi-shot (cortes/cambios de plano).
    # En Standard/Advanced (i2v) se traduce a número de ClipPrompts:
    #   - single_shot → 1 prompt continuo (cinematic)
    #   - multi_shot  → 2-3 prompts cortos (dynamic, mín 4s/clip)
    # En Pro (ref2v) se traduce a un único prompt con multi-shot interno.
    # En Veo 3 siempre es single_shot (modelo nativo es 1 toma 10s max).
    # "auto" deja que la lógica de tier + duración decida (recomendado).
    shot_style: str = "auto"        # "single_shot" | "multi_shot" | "auto"
    # Estrategia de cámara que pasamos al strategist + renderer.
    # "cinematic" = movimientos lentos, continuidad, 1-2 clips largos.
    # "dynamic"   = movimientos variados, cortes frecuentes, 3-4 clips.
    strategy: str = "dynamic"       # "cinematic" | "dynamic"
    duration_s: int = 15
    # Tiers compatibles con este preset. Decidido por Gemini en el
    # generator + clamp en código (Veo 3 cap a 10s). El generador
    # filtra los presets que enseña al elegir tier en /generate.
    compatible_tiers: list[str] = Field(
        default_factory=lambda: list(
            ("standard", "advanced", "pro", "veo3_prompt_only")
        )
    )

    # ─── MÚSICA / OVERLAY (music + opcional en scripted) ───
    # Texto que aparece en pantalla. Para music_only es EL gancho.
    # Para scripted puede ser el título visible o vacío.
    text_overlay: str = ""
    # Estilo visual del overlay (fuente, posición, color, animación…).
    # Vive en el preset porque distintos ángulos quedan mejor con
    # estilos distintos (urgencia con shake rojo, ahorro con verde, etc).
    text_overlay_style: TextOverlayStyle = Field(default_factory=TextOverlayStyle)
    # Subtítulos karaoke (cuando hay voz). Si enabled=False no se añaden.
    subtitle_style: SubtitleStyle = Field(default_factory=SubtitleStyle)
    # Flecha CTA al carrito de TikTok Shop. Gemini decide por ángulo si
    # incluirla (urgencia/ahorro/social_proof = sí, calma/sensorial = no).
    cta_arrow_style: CtaArrowStyle = Field(default_factory=CtaArrowStyle)
    # Mood musical para que el editor pick una pista coherente.
    # Ej: "trendy uplifting", "calm sensorial", "high energy bass".
    music_mood: str = ""

    # ─── VOZ (scripted only — los music son sin voz) ───
    # Voice ID de MiniMax (preset ES) o de una voz clonada. Si None,
    # /generate usará el voice_preference del producto o el default.
    voice_id: str | None = None
    # Tono que pasamos al TTS. Influye en la entonación.
    voice_tone: str = "energetic"     # energetic | calm | persuasive | serious | playful

    # ─── SCRIPTED ───
    title: str = ""                 # título TikTok optimizado para CTR
    voice_script: str = ""          # guion completo para TTS
    hooks_alternatives: list[str] = Field(default_factory=list)  # 3-5 hooks
    cta: str = ""                   # CTA sutil al final
    oratory_tips: str = ""          # dónde pausar, bajar voz, énfasis
    keywords: list[str] = Field(default_factory=list)  # SEO TikTok

    # ─── PROMPTS PARA LOS MODELOS DE VÍDEO ───
    # Seedance i2v (Standard/Advanced): prompt corto describiendo qué
    # pasa con la foto del producto (movimiento de cámara, acción).
    seedance_prompt: str = ""
    # Veo 3 (prompt-only): prompt rico y descriptivo de toda la escena.
    # Para `duration_s` ≤ 10s este es EL prompt único (un solo clip Veo 3).
    # Para `duration_s` > 10s este campo guarda el primer segmento como
    # fallback / preview; el flujo real es `veo3_prompt_segments[]`.
    veo3_prompt: str = ""
    # Para vídeos > 10s en Flow Gemini: lista ordenada de N prompts de
    # ~8-10s que el user pega secuencialmente en Flow para encadenar
    # clips. Cada segmento mantiene continuidad (mismo personaje,
    # outfit, setting) pero progresa el guion/acción. Vacío si el
    # vídeo cabe en un solo clip (`duration_s` ≤ 10s).
    veo3_prompt_segments: list[str] = Field(default_factory=list)
    # Fotos del producto que Gemini eligió para adjuntar a Veo 3.
    # Veo 3 NO va por API en este flujo — el user copia el prompt al chat
    # de Gemini / Flow y adjunta MANUALMENTE estas fotos para dar contexto
    # visual al modelo. Hasta 3 filenames de `product.photos.source`.
    # Gemini ve las fotos source al generar el preset y elige las que
    # mejor encajan con el ángulo/escena del Veo 3 prompt.
    veo3_photo_filenames: list[str] = Field(default_factory=list)

    # ─── META ───
    source: str = "manual"          # "music_bof" | "scripted_bof" | "manual"
    notes: str = ""                 # notas libres del admin
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)


def make_preset_id() -> str:
    return uuid.uuid4().hex[:12]
