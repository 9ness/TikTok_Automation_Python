"""Nicho 4 de Creator Reward — Construcción POV.

Flujo:
  1. Recibe vídeo input (sin voz) del cliente.
  2. Aplica las transformaciones visuales de "Quitar Copy" (anti-detección
     copyright TikTok: blur de subs originales, zoom, metadata strip).
  3. Llama a Gemini 2.5 Pro para analizar el vídeo y generar un guion en
     primera persona, inglés US, sincronizado con la duración del vídeo.
  4. Sintetiza la voz narrada con MiniMax (voz preset EN o clonada).
  5. Renderiza subtítulos karaoke sobre el resultado.
  6. Devuelve MP4 final en `<output_folder>/CONSTRUCCION_POV/`.

NO comparte lógica con TikTok Shop ni con Editor Auto — solo reusa
módulos transversales (video_remover, locutor, subtitles, gemini cliente).
"""
