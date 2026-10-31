# POV replicados para la cuenta árabe (@hmizat.spain, usuario `nes_bugallo`)

El proceso entero, con sus porqués, está en [`docs/CUENTA_ARABE.md`](../../docs/CUENTA_ARABE.md)
§4, en «Receta probada». Estos scripts salen de la ronda 8 (31/10/2026: 10 vídeos por
21 créditos de GenAI).

Para usarlos se copian a la carpeta de la ronda
(`/mnt/HC_Volume_106974679/navegador/trabajo/hmizat_rondaN/`) y se ejecutan desde allí con
`~/nav-venv/bin/python`. Todos leen y escriben rutas relativas a esa carpeta.

| Paso | Script | Qué hace |
|---|---|---|
| Virales | `s1_creadores.py`, `tikwm_hojas.py` | Productos y publicaciones de las tiendas en Social1 (Chrome 9222); caption, audio y hoja de fotogramas del viral (tikwm) |
| Imágenes | `gen_todas.sh [ronda]` → `fimg.py`, `fwait2.py` | Flow Nano Banana 2: `cand/NN_1.txt`, `NN_2.txt` con las refs de `refs_por_video.json`; la escena 2 lleva la 1 como ref. Pestaña de Flow por `FLOW_PROYECTO` (id del proyecto en la URL) |
| Clips | `generar_veo8.py NN_e`, `estado_veo.py`, `recoger_veo.py` | GenAI Pro Veo «Frames» (1 cr) con `gen/NN_e.jpg` + `veo/NN_e.txt`, tope de créditos en `GENERACIONES.json`; baja a `brutos/` |
| Voz (solo si el viral habla) | `voz8.py NN…`, `subs8.py NN…`, `alinear8.py NN…` | Fish darija de `audio/guiones.json` → `audio/NN_fish.mp3` (+0,3 s) → subtítulos por palabra con Whisper small → `audio/NN_subs.json` |
| Montaje | `montar8.py N…` (usa `produccion.py`) | Clips de `CONTROL_CALIDAD.json` + cabecera animada + cierre de cupones + flecha + efectos (+ voz y subtítulos) → `videos/`, hoja en `revision/` |
| App | `registrar_app.py N [replica_id]` | Registra en Mis tandas de `nes_bugallo` (con `replica_id` sustituye el vídeo anterior). El semáforo se pone con `docker exec` (ver doc) |
| Subida | `../subir_video_movil.py` | Lee `SUBIDA.json`: `voz.si` = sin sonido; `sonido.busqueda` = sonido comercial propio; si no, «Suns» |

Ficheros de la ronda que leen: `PLAN.json` (producto, caption, bloques de texto, idioma),
`refs_por_video.json`, `cand/`, `veo/`, `CONTROL_CALIDAD.json`, `audio/guiones.json`,
`browser.json`, `SUBIDA.json`.
