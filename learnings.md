# Learnings

* [Fecha] Contexto: Lección / Resolución
* [2026-05-06] Presidentes Top N: añadido auto-calibrador de palabras (`src/word_calibrator.py`) que persiste `target_total_words` por tipo de vídeo en Upstash Redis (`tiktokCR:words:presidents:t{N}:hook{0|1}:cr{0|1}`). Tras TTS se mide duración con `ffprobe` y, si está fuera de 60-65s, ajusta proporcionalmente (paso máx ±30 palabras, clamp 120-280) y regenera (hasta 3 intentos). `runners.run_presidents` envuelve guion+audio en bucle de calibración.
* [2026-05-12] Subs sobre vídeo: `merge_edited_text_with_timings` reescrito en 3 iteraciones. Final: frases naturales por pausas ≥ 0.30s con cap 6s/frase (split recursivo) + **anclas matched dentro de cada frase como sub-fronteras**. Sub-segmentos entre anclas se distribuyen char-weighted con floor 80ms/palabra; si un sub-segmento es muy corto, merge bidireccional absorbe vecino. Sobrevive a +60 palabras añadidas con 96% de anclas preservadas dentro de 100ms drift. Path 1:1 directo cuando count idéntico.

<!-- Test retry -->

<!-- Test auto-deploy v3 - after NoNewPrivileges fix -->
