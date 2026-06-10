"""Analiza animaciones de subtítulos de un vídeo TikTok con Gemini."""
from __future__ import annotations

import sys
from dotenv import load_dotenv

load_dotenv()

from src.construccion_pov.gemini_video import analyze_video

SYSTEM = (
    "Eres un experto en motion graphics y subtitulado viral de TikTok. "
    "Analizas vídeos y describes con precisión técnica las animaciones de los "
    "subtítulos (captions) para que un desarrollador las reproduzca."
)

USER = """Analiza ÚNICAMENTE los subtítulos/captions de este vídeo (ignora el resto).

Identifica cada ESTILO de subtítulo distinto que aparezca. Para CADA estilo describe:

1. AGRUPACIÓN — ¿es "una palabra" (solo 1 palabra visible cada vez) o "varias palabras"
   (una frase visible con la palabra activa resaltada)? Dilo explícitamente.
2. ANIMACIÓN DE APARICIÓN — pop/escala, slide, fade, typewriter, bounce, etc. Con timing aproximado.
3. RESALTADO de la palabra activa — cambio de color, píldora/fondo, escala, subrayado, glow… o ninguno.
4. TIPOGRAFÍA y COLOR — fuente aprox (bold/condensada/manuscrita…), color texto, contorno/sombra.
5. POSICIÓN en pantalla.

Al final, una tabla resumen: Estilo | Agrupación recomendada (1 palabra / varias) | Por qué.

Sé concreto y técnico. Responde en español."""

video = sys.argv[1] if len(sys.argv) > 1 else "tmp/subtitulos_ejemplo.mp4"

out = analyze_video(
    video,
    system_prompt=SYSTEM,
    user_prompt=USER,
    model="gemini-2.5-pro",
    temperature=0.4,
    log_callback=lambda m: print(m, flush=True),
)
print("\n===== RESULTADO =====\n")
print(out)
