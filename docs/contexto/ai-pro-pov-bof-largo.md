# Programa 4 AI Pro — Nicho POV BOF Largo (estilos de guion, Fish, Épico, Inversa, Acción, Regalo, Réplica viral, Q4)

> Movido literal desde CLAUDE.md (nov 2026) para no cargarlo en cada chat. Se lee solo al tocar este tema.

### Nicho POV BOF Largo (mismo programa)

Módulos en [`src/nicho_pov_bof_largo/`](src/nicho_pov_bof_largo/) (prefijo
Redis `nicho_pov_bof_largo:`). API: `/api/v1/nicho-pov-bof-largo/*`. Es el POV
BOF con la voz cambiada: en vez de una frase genérica del banco, un **guion
escrito para ESE producto** (prompt del curso, literal en `prompts/guion.md`)
y locutado con **Fish Audio** (`FISH_API_KEY`, modelo gratuito
`s2.1-pro-free`). El guion se escribe para ~16s (284 car), que es lo que dan
**DOS clips de 8s** sin rebobinar; la duración la manda la voz y el vídeo se
recorta a ella.

Tres cosas del guion que no son del curso y hay que saber:
- El **cierre es la pieza de ajuste**, no un texto fijo: hay una escalera de
  CTA de 43 a 139 caracteres (`config.ctas_posibles`, solo con lo que el
  producto CUMPLE) y al locutar se elige la que deja el vídeo en su ventana
  (`ventana_video`, 15-16s), rematando con el acelerón (máx x1.10). Guion
  largo → cierre corto y acelerar; guion corto → primero cierre largo y luego
  voz a tono normal. El cuerpo del guion NO se toca: cambiarlo cuesta una
  llamada y es lo que vende.
- La duración se pide **en CLIPS, no en segundos sueltos** (`opciones_guion`):
  con clips de 8s son 2/3/4/5 → 16/24/32/40s, y con los de 10s 2/3/4 →
  20/30/40s. El tope son 40s (`SEGUNDOS_GUION_TOPE`); 60 se quitó porque la
  ficha de un producto no da para tanto y el guion se llenaba de relleno.
  Pedir "30s" con clips de 8 no era múltiplo de nada: salían 3 clips (24s de
  material) y un vídeo de 26 acelerando la voz.
- El banco de voces se cambió entero en sep 2026: fuera las de vendedor/locutor
  (suenan a anuncio en la primera frase), dentro diez `conversational` elegidas
  escuchándolas decir un guion nuestro. El car/s de cada una está MEDIDO con
  nuestro texto: el que anuncia el catálogo de Fish se desvía hasta 3 car/s.

**⚡ Modo «Épico»** (`estilo_guion="epico"`): el prompt de dolor + `prompts/guion_epico.md`.
La IA marca `[[GOLPE: TEXTO | escena]]`, que se guardan en `golpes` y la voz no
lee. `pipeline/insertos.py` mete tras el montaje un inserto de 1 s por golpe
(clip de 5 s de Kling subido con `inserto=N`), con destello, texto y
un sonido del banco `assets/sfx/epico/` (uno por vídeo; boom y letras rojas si el inserto es de fondo blanco), y recorta la pausa de antes y de después. **Desde el 8/10/2026 va SIN insertos** (solo el guion): no se piden ni bloquean el montaje salvo `EPICO_CON_INSERTOS=1`.

**🔄 Venta inversa** (`estilo_guion="inversa"`): «No lo compres si no quieres…»,
prompt nuestro por ingeniería inversa de la web del curso (`prompts/guion_inversa.md`,
muestras en `docs/venta_inversa/`); cierre de disponibilidad (`CTAS_INVERSA`), sin precio, siempre 3 clips (`SEGUNDOS_INVERSA`).

**⚡ Acción** (`estilo_guion="accion"`): el «UGC Desde 0 · Gancho Acción» del curso pasado a POV (`prompts/guion_accion.md`, original en `docs/ugc_accion/`): sin dolor, el producto ya en uso y «Mira cómo…», luego características y la CTA de precio de siempre.

**🎁 Regalo** (`estilo_guion="regalo"`, 27/10/2026): prompt nuestro `prompts/guion_regalo.md` — el gancho dice a QUIÉN regalarlo (adulto, situación real), luego características, precio y CTA de siempre; sin promesas de campaña. Se elige por producto (lo que no pega como regalo, dolor o precio).

**🔁 Réplica viral** (`estilo_guion="viral"`, carpeta especial «Réplicas virales», de todos los usuarios): el guion y los prompts de los clips salen de la réplica (`src/replicar_viral/`, campo `replica_id`), sin IA; `POST /replica/anadir` y MCP `anadir_replica`. Siempre 2 clips.

**Calendario de subidas** (qué carpeta toca cada día): [`docs/CALENDARIO_POV_BOF_LARGO.md`](docs/CALENDARIO_POV_BOF_LARGO.md).
Las carpetas especiales (`CARPETAS_ESPECIALES`: Épico Octubre, Venta Inversa, Q4) van en orden de publicación y con sus fechas en la etiqueta.

**🎄 Productos Q4** (`nicho_pov_bof/services/productos_q4.py`): carpeta real
«Productos Q4» dentro del Inventario General, primera de la lista y solo para
`ness`, con COPIAS de productos (fotos + textos + `segundos_guion`) para grabar
vídeos de Black Friday/Navidad sin pisar el original. Manifiesto
`q4:manifiesto`; se llena con `POST /q4/anadir` o el MCP `anadir_a_q4`.

Si el producto pasa de `PRECIO_MIN_PLAZOS`, al guion se le añade el bloque de
`prompts/guion_plazos.md` (una frase de financiación, sin nombrar la pasarela):
misma estructura del curso, un párrafo más en el prompt. `guion_plazos` guarda
en qué modo se escribió y se reescribe si el precio lo cambia.

Su pantalla es un CALCO de la del POV BOF (misma UI y flujo) — solo cambia que
se sube el guion + DOS clips. Comparte catálogo/carpetas/textos/fotos con el POV
BOF (reusa sus endpoints), pero el **progreso es individual**: carpeta hecha
(`progress_repo` propio + `/complete`), subido y guion/clips/vídeo viven en
`nicho_pov_bof_largo:` (`/producto/estado`). Dos progresos son GLOBALES a
propósito (ver "Escaparate y vendidos" abajo).

