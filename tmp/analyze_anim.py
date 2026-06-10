"""Pregunta a Gemini la ANIMACIÓN exacta de los subtítulos para recrearla."""
from __future__ import annotations

import sys
from dotenv import load_dotenv

load_dotenv()

from src.construccion_pov.gemini_video import analyze_video

SYSTEM = (
    "Eres ingeniero de motion graphics. Tu trabajo es describir la animación de "
    "subtítulos de un vídeo con precisión suficiente para reimplementarla en un "
    "renderizador frame-a-frame (PIL/ffmpeg) sin ver el vídeo."
)

USER = """Mira SOLO la animación de los subtítulos al CAMBIAR de palabra/frase.

Necesito recrear EXACTAMENTE el movimiento. Para cada tipo de animación distinta que veas, dame:

1. NOMBRE del efecto (pop/scale, slide, fade, typewriter, bounce, blur-in…).
2. PARÁMETROS NUMÉRICOS para reimplementarlo:
   - Duración de la animación de entrada (en ms o en frames a 30fps).
   - Escala inicial → final (ej. 0.8 → 1.0) y si hay OVERSHOOT/rebote (ej. 1.0→1.1→1.0).
   - Opacidad inicial → final.
   - Desplazamiento si hay slide (px o % y dirección).
   - Curva de easing aproximada (linear, ease-out, ease-out-back, spring…).
3. ¿La animación es por PALABRA (cada palabra entra animada) o por toda la línea/frase a la vez?
4. ¿Qué pasa con la palabra anterior cuando entra la nueva? (desaparece de golpe, fade-out, se queda…).
5. ¿El resaltado (color/píldora) también se anima o es instantáneo?

Si hay varios estilos con animaciones diferentes, sepáralos. Sé MUY concreto con los números
(prefiero una estimación numérica a "rápido"). Responde en español, formato lista por estilo,
y al final una recomendación de los 2-3 efectos más fáciles de clonar que den el 90% del resultado."""

video = sys.argv[1] if len(sys.argv) > 1 else "tmp/subtitulos_ejemplo.mp4"

out = analyze_video(
    video,
    system_prompt=SYSTEM,
    user_prompt=USER,
    model="gemini-2.5-pro",
    temperature=0.3,
    log_callback=lambda m: print(str(m).encode("ascii", "ignore").decode(), flush=True),
)
print("\n===== RESULTADO =====\n")
print(out)
