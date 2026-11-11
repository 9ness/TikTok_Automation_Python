# Parte 3 · Ideas nuevas para ahorrar trabajo en el Editor y la fábrica (10/11/2026)

> Anexo de [`2026-11-10_audio_y_estilo_vip.md`](2026-11-10_audio_y_estilo_vip.md). Las rutas relativas (`scripts/`, `log/`, `estilo/`, `muestras_audio/`…) son de la carpeta de pruebas `/mnt/HC_Volume_106974679/agentes/trabajo/fable-audio/` (en el ampliado del VPS, fuera de git).

No se repite lo hecho (render 3,3×, veryfast, subtítulos con ffmpeg overlay, render en el PC de casa,
banco del cortador sin gasto) ni las 12 ideas de `~/proyectos/admin/ideas-fable/editor-auto.md`.
Tampoco se proponen dos cosas que ya existen: la **cola por prioridad** (`src/queue/manager.py`:
`_client_priority`, `queue_priority`) y la **revisión visual** del resultado
(`services/revision_visual.py`, ~0,0007 $ por vídeo).

Ordenadas por valor/esfuerzo. Los ahorros en minutos son estimaciones salvo donde pone «medido».

| # | Idea | Cuándo | Esfuerzo | Riesgo |
|---|---|---|---|---|
| 1 | Una sola transcripción por vídeo | ya | M | medio |
| 2 | Comprobador de audio al entrar | ya | S | bajo |
| 3 | Quitar la llamada de Gemini que da 404 | ya | S | bajo |
| 4 | Biblioteca de estilos con nombre | ya | M | bajo |
| 5 | Cortador una vez + N variantes | pronto | M | bajo |
| 6 | Vocabulario por cliente | pronto | S | bajo |
| 7 | Autodiagnóstico de quejas | pronto | M | bajo |
| 8 | Un solo render final | pronto | L | alto |
| 9 | Vista previa barata del estilo | pronto | M | bajo |
| 10 | Caché del plan VIP y de las fotos | pronto | S | bajo |
| 11 | Precalentar el recuento de carpetas | pronto | S | bajo |
| 12 | Reparto automático según carga | futuro | M | medio |
| 13 | Informe semanal al cliente | futuro | S | bajo |
| 14 | Control de parecido con la referencia | futuro | M | bajo |

## 1. Una sola transcripción por vídeo (ya · M · riesgo medio)
- **Verificado:** no hay caché en `src/editor_auto/asr.py` (solo `usa_deepgram` y `transcribe_words`).
  El mismo vídeo se transcribe al menos cuatro veces en un flujo VIP: `silence_cutter` al entrar
  (línea ~384), `silence_cutter` otra vez sobre su SALIDA para auditar (línea ~5090; el auto-arreglo
  puede repetirlo), `vip_overlays._transcribe` y `subs_auto.run`. Entre pasos solo viajan
  `correcciones` (`vip_overlays.py:153`) y `sin_subs`.
- **Qué ahorra:** dinero poco: Deepgram cuesta 0,0043 $/min (`cost_tracking.DEEPGRAM_PER_MIN`), así que
  se pagan ~0,013-0,017 $ por minuto de vídeo en vez de 0,0043 $. Lo que pesa es el tiempo (2 extracciones
  de audio + 2 llamadas de más; minutos si cae a Whisper) y la **incoherencia**: cada paso lee palabras
  distintas (por eso `_corregir_nombres` necesita tolerancia de 0,8 s) y el resultado no es repetible.
- **Cómo:** el cortador ya tiene las palabras de su salida; dejarlas en `ctx.extras["words"]` y que
  `vip_overlays` y `subs_auto` las usen si existen. `vip_overlays` desplaza los tiempos cuando copia el
  clip de gancho al principio. Respaldo: caché en `asr.transcribe_words` por hash del audio.
- **Riesgo:** un desfase al reproyectar tiempos descuadra subtítulos. Opción apagada por defecto y
  prueba con el banco antes de activar.

## 2. Comprobador de audio al entrar (ya · S · riesgo bajo)
- **Verificado:** el nivel solo se mide dentro del cortador para sus umbrales
  (`_measure_mean_volume_db`); nadie avisa al cliente. Existe `tools/audio_clean.py` pero no se activa solo.
- **Qué ahorra:** reediciones y quejas («se oye bajo») antes de gastar render: 5-15 min por vídeo
  rechazado, más la conversación con el cliente.
- **Cómo:** una pasada de ffmpeg (`ebur128` + `astats`) al subir: LUFS, pico, y relación voz/fondo con
  el percentil 90/10 del nivel (ya escrito en `medir_estilo.py:audio`). Semáforo: verde, ámbar («se oye
  bajo: lo subimos») y rojo («mucho ruido o música: regrábalo o activa Mejorar voz»). En ámbar, activar
  `audio_clean` solo. DNSMOS opcional y fuera del contenedor de la API.
- **Riesgo:** falsos avisos con música intencionada; empezar solo informando.

## 3. Quitar la llamada de Gemini que da 404 (ya · S · riesgo bajo)
- Ya está en `tasks.md` (línea 31): el pass2 del cortador pide `gemini-2.5-pro` y recibe 404. Se cita
  aquí porque es tiempo perdido en cada vídeo y es un cambio de una constante.
- **Qué ahorra:** una llamada fallida con su espera y reintentos por vídeo.
- **Cómo:** cambiar el modelo a uno vigente o quitar el paso si Claude ya lo cubre (hoy hace 3
  comprobaciones por render, `learnings.md` 3/11). Medir con el banco antes y después.

## 4. Biblioteca de estilos con nombre (ya · M · riesgo bajo)
- **Verificado:** los endpoints de estilo «NO guardan nada» (`routers/editor_auto/tools.py:50-90`); el
  estilo queda dentro del flujo de un usuario y hay que rehacerlo para otro.
- **Qué ahorra:** 10-20 min de configuración por cliente nuevo y el análisis repetido. Permite vender
  «estilo Hormozi» como producto de catálogo.
- **Cómo:** `editor_auto:estilo:<nombre>` en Redis local (config de `vip_overlays` + `_flujo`),
  listar/guardar/aplicar, y `style_mapper.build_tool_flow` que acepte un preset guardado. Detalle en
  `estilo_vip.md` §e.

## 5. Cortador una vez + N variantes (pronto · M · riesgo bajo)
- **Qué ahorra:** el cortador es el paso caro (transcribe, audita y puede renderizar hasta 5 veces por
  trabajo, `learnings.md` 9/11). Para 3 estilos o 3 ganchos del mismo vídeo se pagaría una vez en lugar
  de tres: cerca de dos tercios del tiempo total.
- **Cómo:** guardar `cortado.mp4` + palabras + mapa de cortes con clave del hash del original y de la
  config del cortador; un trabajo «variante» entra por el paso `vip_overlays` o `subs_auto`. Es la base
  técnica de las ideas ya listadas «tres ganchos» y «versión Reels/Shorts».
- **Riesgo:** disco; el intermedio va al ampliado y lo borra `retention_sweeper`.

## 6. Vocabulario por cliente (pronto · S · riesgo bajo)
- **Verificado:** `vip_plan` devuelve `correcciones` de nombres propios por vídeo y se pierden al
  terminar; `asr.py` no tiene `keyterm`/`keywords`.
- **Qué ahorra:** el error que más se repite en subtítulos (marcas y nombres mal escritos): 1-3 min
  de retoque por vídeo, y quejas.
- **Cómo:** acumular las correcciones por usuario (`editor_auto:vocabulario:<usuario>`), pasarlas a
  Deepgram como términos clave y aplicarlas en `subs_auto` antes de pintar. Pantalla mínima para que el
  cliente añada su marca.

## 7. Autodiagnóstico de quejas (pronto · M · riesgo bajo)
- **Qué ahorra:** hoy una queja del cortador es depuración a mano siguiendo `EDITOR_DEBUGGING.md`:
  20-40 min por caso.
- **Cómo:** botón «Algo salió mal» con el segundo aproximado. El sistema arma el paquete (palabras de
  entrada y salida, mapa de cortes, señales de silero/energía del tramo), lo clasifica según la
  casuística del playbook (frase comida, muletilla, corte en mitad de palabra, subtítulo descuadrado) y
  añade el caso al banco de regresión. Devuelve al operador un diagnóstico de una línea.
- **Nota:** el reintento con comentario del cliente aparece planeado en `tasks.md` (línea 797), pero
  `retry_feedback` no está en `src/editor_auto`: sin confirmar que exista.

## 8. Un solo render final (pronto · L · riesgo alto)
- **Verificado:** cada herramienta codifica por su cuenta (`libx264` en `vip_overlays.py`,
  `photo_insert.py`, `sticker_arrow.py`, `subs_auto`/`subtitles_only.py` y el cortador): un flujo VIP
  completo recodifica el vídeo 4-5 veces.
- **Qué ahorra:** tiempo de CPU (la mayor parte del render) y calidad, que se pierde en cada generación.
- **Cómo, por pasos:** (a) intermedios rápidos y casi sin pérdida (`-preset ultrafast -crf 14`) y
  solo el último paso con la calidad final: cambio pequeño y casi todo el beneficio; (b) más adelante,
  que flecha, rótulos y subtítulos compartan una sola pasada de overlay.
- **Riesgo:** toca todas las herramientas; medir tamaño y tiempo con 5 vídeos antes de decidir.

## 9. Vista previa barata del estilo (pronto · M · riesgo bajo)
- **Qué ahorra:** hoy para ver cómo queda un estilo hay que renderizar el vídeo entero; con 3 pruebas
  son 3 renders completos.
- **Cómo:** modo «muestra»: primeros 8-10 s a 540 px con el flujo de estilo (sin cortador), en la
  pantalla de configuración. Segundos en vez de minutos.

## 10. Caché del plan VIP y de las fotos de apoyo (pronto · S · riesgo bajo)
- **Verificado:** las fotos salen de `photo_insert._search_and_download` (buscador + verificación de
  cada foto con Haiku, `record_claude`); en un reintento se vuelve a buscar y a verificar todo.
- **Qué ahorra:** llamadas de búsqueda y de visión en cada reintento o variante, y resultados distintos
  cada vez.
- **Cómo:** guardar plan y fotos aceptadas con clave del hash de la transcripción + config; con la
  idea 1 la transcripción es estable y la caché acierta.

## 11. Precalentar el recuento de carpetas (pronto · S · riesgo bajo)
- Ya está en `tasks.md` (línea 17): `editor-auto/folders/counts` tarda minutos en frío. Se cita porque
  es espera diaria del operador.
- **Cómo:** recuento en segundo plano cada pocos minutos, guardado en Redis, y la pantalla lee lo guardado.

## 12. Reparto automático según carga (futuro · M · riesgo medio)
- **Qué ahorra:** esperas cuando el VPS va justo (hoy carga ~17 con varios agentes).
- **Cómo:** que el planificador consulte `donde-montar` y mande al PC de casa los trabajos VIP largos
  (extiende `render_remoto.py`), y que la cola muestre al cliente una espera estimada con los tiempos de
  `estadisticas`.
- **Riesgo:** el PC de casa puede estar apagado; siempre con vuelta al VPS.

## 13. Informe semanal al cliente (futuro · S · riesgo bajo)
- **Qué ahorra:** retención más que minutos: el cliente ve cuántos vídeos y cuánto tiempo de edición se
  ha ahorrado.
- **Cómo:** datos de `services/estadisticas` (SQLite) + envío con `email_notify` o `whatsapp_notify`.

## 14. Control de parecido con la referencia (futuro · M · riesgo bajo)
- **Qué ahorra:** revisar a ojo si el vídeo editado se parece al estilo pedido.
- **Cómo:** pasar el medidor de estilo por el resultado y comparar con las cifras del preset (palabras
  por línea, altura, mayúsculas, color, saltos por minuto). Aviso si se desvía.
