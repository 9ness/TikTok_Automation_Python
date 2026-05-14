# Investigación: ¿qué modelo de IA usar para análisis de transcript?

## DECISIÓN APLICADA (mayo 2026)

**Default activo en config:**
- **Pass 1 (general)**: GPT-4o · `temperature=0.2` · ~$0.012/vid
- **Pass 2 (false-starts)**: Gemini 2.5 Pro solo · `temperature=0.0` · ~$0.003/vid
- **Capa determinística**: heurística n-gram (gratis) cubre repeticiones literales
- **Total: ~$0.015/vid**

Esto es la "estrategia B" de la tabla más abajo. Razón de elegirla sobre C:
GPT-4o pass2 era el que peor funcionaba (no-determinismo "Clean transcript"),
así que skipearlo no pierde calidad. Gemini Pro pass2 + n-gram cubre los
casos sin pagar $0.012 extra de GPT-4o pass2.

Si quieres máxima fiabilidad para un vídeo premium → activa también
`ai_pass2_openai_enabled=true` desde la UI → pasa a estrategia C ($0.027/vid).

---

## Tareas que ejecutamos

1. **Pass 1 (general)** — `silence_cutter_analyst.md`. Detecta head/tail
   silence, noise gaps, false starts, abandoned phrases. Output JSON
   complejo con múltiples categorías. Necesita instrucciones detalladas y
   buen seguimiento de schema.

2. **Pass 2 (false-starts)** — `silence_cutter_false_starts.md`. Detecta
   solo repeticiones y reformulaciones. Output JSON más simple con texto
   contextual (first_attempt / kept_version). Precisión > recall.

## Modelos candidatos (precios oficiales enero 2026)

| Modelo | Input $/1M | Output $/1M | JSON mode | Pros / Contras |
|---|---|---|---|---|
| **GPT-4o** | $2.50 | $10.00 | ✓ nativo | **Actual**. Sigue muy bien schemas complejos. No-determinístico pero a temp 0 razonable. |
| **GPT-4o-mini** | $0.15 | $0.60 | ✓ nativo | 17× más barato. Peor en matices de español. Adecuado para tareas simples. **No recomendado** para este caso. |
| **GPT-5** | n/d aún | n/d aún | — | No disponible públicamente todavía. |
| **Gemini 2.5 Pro** | $1.25 | $5.00 | ✓ nativo | 2× más barato que GPT-4o. Excelente en español. Muy buen seguimiento de schemas. **Candidato fuerte**. |
| **Gemini 2.5 Flash** | $0.30 | $2.50 | ✓ nativo | ~8× más barato. Calidad media-alta, suficiente para pass 2. **Candidato barato**. |
| **Gemini 2.0 Flash** | $0.10 | $0.40 | ✓ nativo | Muy barato. Útil como segunda opinión barata. |
| **Claude 4.5 Sonnet** | $3.00 | $15.00 | ✓ vía tool-use | Excelente razonamiento. Mejor en detectar matices semánticos sutiles. Más caro pero potencialmente más preciso para pass 2. |

## Recomendación final

### Mantener GPT-4o en pass 1 (general)
Razón: el schema es complejo (head/tail/noise_gap/false_start/...), GPT-4o
tiene la mejor combinación calidad/structured-output. Coste por job real:
~$0.005-$0.015 (transcripts de ~200 palabras).

### Pass 2 (false-starts): probar Gemini 2.5 Pro o mantener GPT-4o + heurístico
Tras nuestros fixes (temperature 0.0 + n-gram detector determinístico), el
caso "Clean transcript" alucinado ya no se traga las repeticiones literales
— el detector heurístico las captura siempre. Si quieres consenso multi-modelo
(IA + heurística + Gemini) → activar un pass 3 con Gemini Pro como segunda
opinión ($0.02 extra por job).

### Coste por video (~90s, transcript ~160 palabras)

| Setup | Coste/video | Calidad |
|---|---|---|
| Solo GPT-4o pass 1+2 (actual) | ~$0.012 | Buena pero no-determinística |
| GPT-4o + heurístico n-gram (nuevo) | ~$0.012 | **Mejor** (heurístico determinista no falla) |
| GPT-4o pass 1 + Gemini Pro pass 2 + heurístico | ~$0.015 | **Excelente** (3 capas: una falla, otra cubre) |
| Gemini Pro pass 1 + heurístico | ~$0.005 | Buena, más barata (probar) |

## Acción sugerida

1. **Ahora**: aplicar fixes actuales (heurístico + temp 0.0) y validar con
   varios runs del mismo .mov para confirmar reproducibilidad.

2. **Después**: si quieres reducir coste o mejorar fiabilidad:
   - **Reducir coste**: cambiar pass 1 a `gemini-2.5-pro` — ~50% más barato,
     calidad similar.
   - **Mejorar fiabilidad**: añadir pass 3 con `gemini-2.5-flash` que valida
     los false-starts del pass 2 GPT-4o. Si ambos coinciden → cut seguro.
     Si solo uno detecta → cut con flag "needs review".

3. **Para producción / vender el servicio**: la heurística n-gram + 2 IAs en
   consenso (GPT-4o + Gemini 2.5 Pro) da fiabilidad máxima a coste ~$0.02/vid.
   Si vendes a €5/vid el margen sigue >99%.

## Notas técnicas

- **No-determinismo de LLMs**: incluso con `temperature=0`, los modelos
  pueden devolver respuestas distintas entre runs por:
  - Cache hits/misses internos del provider
  - Floating-point non-associativity en GPU
  - Versión exacta del modelo desplegado (los providers actualizan modelos
    sin avisar; "gpt-4o" puede apuntar a "gpt-4o-2024-08-06" hoy y a
    "gpt-4o-2026-01-15" mañana)
- **Solución**: combinar IA con detectores **determinísticos** (heurística
  n-gram, ffmpeg silencedetect, Silero VAD) que cubren los casos típicos.
  La IA queda como segunda capa para casos sutiles donde la heurística no
  puede juzgar (paráfrasis, abandono semántico).
