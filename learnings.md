# Learnings

* [Fecha] Contexto: Lección / Resolución
* [2026-05-06] Presidentes Top N: añadido auto-calibrador de palabras (`src/word_calibrator.py`) que persiste `target_total_words` por tipo de vídeo en Upstash Redis (`tiktokCR:words:presidents:t{N}:hook{0|1}:cr{0|1}`). Tras TTS se mide duración con `ffprobe` y, si está fuera de 60-65s, ajusta proporcionalmente (paso máx ±30 palabras, clamp 120-280) y regenera (hasta 3 intentos). `runners.run_presidents` envuelve guion+audio en bucle de calibración.

<!-- Test retry -->
