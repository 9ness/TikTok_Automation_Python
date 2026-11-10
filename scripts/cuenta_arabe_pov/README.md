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
| Reaprovechar (10/11) | `reaprovechar.py cruce` · `reaprovechar.py traer --ronda DIR --numero N --fila "largo|…"` | Productos del banco que otra cuenta ya tiene en VERDE (mismo id de ficha) y con clips brutos en su bandeja del Drive → los copia a `brutos/` en 1080x1920 con hoja a 2 fps y deja `PLAN.json`/`CONTROL_CALIDAD.json` con `aceptado: false`. Sin Flow ni créditos: se sigue desde Voz. Ver `docs/CUENTA_ARABE.md` › «Reaprovechar clips en verde» |
| Imágenes (desde ronda 9) | `gen_todas_cdp.sh [NN…]` → `fimg_cdp.py`, `fwait_cdp.py` (CDP directo con `cdp.py`/`flowlib.py`; pestaña en `flow_browser.json`) | Igual que la fila de abajo, sin Playwright |
| Imágenes (ronda 8) | `gen_todas.sh [ronda]` → `fimg.py`, `fwait2.py` | Flow Nano Banana 2: `cand/NN_1.txt`, `NN_2.txt` con las refs de `refs_por_video.json`; la escena 2 lleva la 1 como ref. Pestaña de Flow por `FLOW_PROYECTO` (id del proyecto en la URL) |
| Clips (desde ronda 9) | `generar_omni.py NN_e…` (GO=1 envía), `recoger_omni.py` | GenAI Pro Omni 1.1 «Frames», **Watermark · 10s · 1080p · 9:16**, solo si dice «Cost: 1 credit»; tope en `GENERACIONES.json`; al montar, `omni: true` en `CONTROL_CALIDAD.json` |
| Clips (ronda 8) | `generar_veo8.py NN_e`, `estado_veo.py`, `recoger_veo.py` | GenAI Pro Veo «Frames» (1 cr) con `gen/NN_e.jpg` + `veo/NN_e.txt`, tope de créditos en `GENERACIONES.json`; baja a `brutos/` |
| Voz (solo si el viral habla) | `voz8.py NN…`, `subs8.py NN…`, `alinear8.py NN…` | Fish darija de `audio/guiones.json` → `audio/NN_fish.mp3` (+0,3 s) → subtítulos por palabra con Whisper small → `audio/NN_subs.json` |
| Montaje | `montar8.py N…` (usa `produccion.py`) | Clips de `CONTROL_CALIDAD.json` + cabecera animada + cierre de cupones + flecha + efectos (+ voz y subtítulos) → `videos/`, hoja en `revision/` |
| App | `registrar_app.py N [replica_id]` | Registra en Mis tandas de `nes_bugallo` (con `replica_id` sustituye el vídeo anterior). El semáforo se pone con `docker exec` (ver doc) |
| Subida | `../subir_video_movil.py` | Lee `SUBIDA.json`: `voz.si` = sin sonido; `sonido.busqueda` = sonido comercial propio; si no, «Suns» |

Ficheros de la ronda que leen: `PLAN.json` (producto, caption, bloques de texto, idioma),
`refs_por_video.json`, `cand/`, `veo/`, `CONTROL_CALIDAD.json`, `audio/guiones.json`,
`browser.json`, `SUBIDA.json`.
