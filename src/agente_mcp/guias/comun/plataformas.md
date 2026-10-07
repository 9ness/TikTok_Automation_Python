# Dónde se generan las fotos y los clips

La app **no genera** ni las imágenes ni los vídeos: te da el prompt y las
fotos, y tú los generas en una de estas webs (con la cuenta del operador, ya
abierta en el navegador). Luego el clip vuelve a la app para que lo edite.

## Qué se usa para qué

| Qué | Dónde | Notas |
|---|---|---|
| **Todas las imágenes** | **Google Flow** · modelo Nano Banana 2 · 9:16 | Salvo Creativos Pro, que va en 3:4 |
| Clip que **habla** (la voz va dentro del clip) | **GenAI Pro · Omni 1.1** (o Google Flow · Omni) | Omni locuta. 10 s |
| Clip **mudo** (la voz la pone la app, o va sin voz) | **GenAI Pro · Omni 1.1** (preferente), Google Flow o Magnific | Ver tabla de abajo |

| Plataforma | Voz | Duración | Calidad | Coste |
|---|---|---|---|---|
| Google Flow (Omni) | ✅ | 8 s o 10 s | 720p → reescalar a 1080p | 12 créditos (8 s) · 15 créditos (10 s) |
| **GenAI Pro · Omni 1.1** (desde 7/10/2026) | ✅ | **10 s** | **1080p** (1080×1920) | **1 crédito con marca de agua** (3 sin ella: NO) |
| GenAI Pro · Veo (antiguo) | ❌ | hasta 8 s | 720p | 1 crédito |
| Magnific (spaces) | ❌ | 8 s o 10 s | la del space | lo que marque su web |

Qué menú admite qué:

- **POV BOF, POV BOF Largo**: la voz la pone la app → Omni 1.1 de GenAI Pro (o cualquiera).
- **Moda (formatos hablados), UGC**: la voz va en el clip → Omni (GenAI Pro o Flow).
- **Moda (formatos mudos 🔇), Marca Personal**: cualquiera de las tres.

---

## Google Flow — `https://flow.google.com/`

Trabaja dentro de un **proyecto** por carpeta de productos (ej. «Moda Mujer ·
Carpeta 24»): así las imágenes quedan juntas y puedes reutilizarlas como
frame o ingrediente sin volver a subirlas. No metas cientos de imágenes en un
mismo proyecto: se satura y se congela.

> ⚠️ **Flow necesita la ventana del navegador VISIBLE.** Con Chrome
> minimizado u oculto (PC bloqueado, operador fuera) el selector de
> ingredientes no pinta, el envío no sale y al recargar vuelve a modo vídeo
> (se llegaron a gastar 6 vídeos Omni por error). Compruébalo antes
> (`document.visibilityState` debe ser `visible`); si no lo es, haz las
> imágenes en Magnific (abajo) y avísalo en el informe.

### Imagen (Nano Banana 2)

1. Modo de **crear imagen**, modelo **Nano Banana 2**, formato **9:16
   vertical** (3:4 en Creativos Pro). **1 resultado por prompt** (no 2 ni 4:
   gasta el doble y no hace falta). **Compruébalo cada vez que se reinicie
   el navegador**: Flow vuelve a 4:3 horizontal y las imágenes salen
   apaisadas (1200×896); un clip hecho desde una imagen apaisada sale con
   bandas negras y hay que tirarlo (oct 2026, 4 créditos de GenAI Pro).
   Mira el tamaño de lo que bajas: vertical es 768×1376.
2. **Adjunta** las fotos que diga la guía del menú (normalmente la foto
   limpia del producto; en Marca Personal, también el personaje).
3. Pega el prompt de imagen de la app y genera.
4. Revisa la imagen con [`revision-calidad.md`](revision-calidad.md). Si vale,
   descárgala a la carpeta del producto como `imagen_1.png`.
5. Cuando la guía diga **«en el MISMO chat»** (imagen 2 de Calle Dividido,
   colores de Tienda Colores), pide la siguiente imagen **en la misma
   conversación**, sin empezar otra: es lo que mantiene la misma chica y el
   mismo sitio.

### Vídeo (Omni)

1. Modo de **vídeo**, modelo **Omni**, **9:16**, duración **8 s o 10 s** (la
   que acordaste), **1 resultado**.
2. Cómo entra la imagen — la guía de cada modo dice cuál, y equivocarse no da
   error, simplemente sale otro vídeo:
   - **FRAME INICIAL** (frames / start frame): el vídeo EMPIEZA en esa imagen.
     Es lo normal.
   - **INGREDIENTES**: las imágenes son referencias (personaje, producto,
     colores) y el vídeo se compone con ellas. Solo donde la guía lo diga.
3. Pega el guion / prompt de vídeo que te da la tarjeta del producto en la app.
4. Genera, revisa el clip con [`revision-calidad.md`](revision-calidad.md).
5. Descarga **en 1080p** (opción de reescalar/upscale al descargar). Si solo
   deja 720p, descárgalo así y avísalo en el informe. Guárdalo como
   `clip_1.mp4`, `clip_2.mp4`… en el orden que diga la tarjeta.

---

## GenAI Pro — `https://genaipro.io/video-image-ai`

### Omni 1.1 — lo de ahora (desde 7/10/2026)

Ajustes, siempre los mismos:

- Modelo **Omni 1.1** · **Portrait 9:16** · **1080p** · **10 s** · **CON marca
  de agua** (1 crédito; sin marca son 3 y no compensa).
- **La marca de agua la quita la app sola al montar**: es una estrellita
  abajo a la derecha y el montaje reconoce los clips de Omni (vienen firmados
  `encoder=Google`) y amplía un 14% recortando por abajo. **No la tapes ni la
  recortes tú, y sube el MP4 TAL CUAL lo da GenAI Pro** (si lo reencodeas o
  recortas, pierde la firma y la estrella se queda en el vídeo).
- 10 s por clip aunque el guion sea de 8 s por clip: la voz manda y el clip se
  recorta a ella; sobra material, no falta.
- Omni habla: en los menús donde la voz la pone la app (POV BOF, Largo) el
  audio del clip se descarta al montar, así que pide en el prompt que el clip
  sea sin voz/diálogo para no gastar intentos en eso.
- Lo demás (imagen de inicio, prompt del vídeo, frase del producto,
  prohibiciones) igual que con Veo, abajo. La primera vez comprueba si deja
  imagen de inicio y fin (modo Frames) y apúntalo aquí.

### Veo (antiguo)

Solo vídeo, **mudo**. Ajustes, siempre los mismos:

- **hasta 8 s** · modo **Frames** · **start + end frame** · **Portrait 9:16**
  · **1 vídeo** · calidad **Original**.
- **Start frame y end frame: la MISMA imagen** (la generada en Flow). Así el
  clip vuelve al punto de partida y dos clips seguidos casan.
- Pega el «Prompt vídeo» de la app (en POV BOF / Largo es el mismo para todos
  los productos).
- Si la tarjeta pide 2 clips, genera **dos clips** de la misma imagen (cada
  generación sale distinta; eso es lo que se busca).
- **Calidad SIEMPRE «Original» (720×1280).** Con «1080p» el vídeo sale
  **1920×1080 horizontal** aunque esté en Portrait — bug reconfirmado el
  29/9/2026, no lo vuelvas a probar. Los ~0,5 s finales de cada clip hacen un
  fundido de vuelta al primer fotograma: recorta a **7,3 s** antes de subir.
- Al prompt base añade **una frase del producto** («la máquina está apagada y
  quieta, la puerta no se abre…») y, si hace falta, prohibiciones concretas:
  «exactly ONE hand, never a second hand» (salían dos manos), «NO steam, NO
  smoke» (salió humo de una taza), «the workbench stays EMPTY» (apareció un
  metro). Un producto ENCENDIDO (lámpara) se dice «stays lit, constant light».
- **No cambies el gesto de la mano del «Prompt vídeo» de la app.** El original
  dice «The person gestures with the visible hand as if explaining the product…
  Only the hand moves». Si lo sustituyes por «la mano se queda quieta
  señalando / pointing calmly», el dedo queda casi fijo y el vídeo tiembla. Deja
  ese texto tal cual y solo AÑADE al final, por producto: «Exactly one hand,
  never a second one», la pantalla apagada o «nothing lights up», y lo que no
  debe moverse. (29/9/2026: los clips hechos con «stays at the bottom… pointing
  calmly» salieron con la mano temblando.)
- «Generation failed, please try again» = fallo genérico, **se reembolsa**:
  reintenta con el mismo botón. Van varios en paralelo, ~3-5 min cada uno.
- Las URL de los resultados están en el DOM (`video.currentSrc`,
  `files.genaipro.io/video_<uuid>.mp4`): se bajan con curl sin tocar el botón.

---

## Magnific — «spaces» con el prompt dentro

Aquí no se pega prompt: cada **space** ya lleva el flujo montado. Se abre el
space, se sube la imagen y se lanza. Mudo, 8 s o 10 s.

| Space | Para qué | Enlace |
|---|---|---|
| Foto limpia → vídeo (pago normal) | 1 clip por foto | https://www.magnific.com/app/spaces/a27c380f-a674-49e7-9434-29fb441f4a08?page=1 |
| Foto limpia → vídeo (pago a plazos) | 2 clips por foto | https://www.magnific.com/app/spaces/a27da99c-562d-4289-bef5-7e0f591d4dc6?page=1 |
| Foto con IA → vídeo | cuando ya tienes la imagen generada en Flow | https://www.magnific.com/app/spaces/a271e815-cff4-46b6-8597-16153024b453 |
| Foto con IA → vídeo (2) | el mismo, otro space para repartir la carga | https://www.magnific.com/app/spaces/a285a2e7-03d4-426c-9053-4ef927673519?page=1 |
| Carrusel de 1 foto | una sola foto de partida | https://www.magnific.com/app/spaces/a279e062-6d19-44bf-bb6c-2775ab35d74c |

Cómo se usa el space «Foto con IA → vídeo» en lote (Kling 2.5 · 9:16 · 10 s ·
**720p**, que es lo ilimitado; 1080p gasta créditos):

- El nodo de lista de entrada: **«⋯ › Clear list»** y luego **«Add media»**
  con las imágenes; después **Run** en el nodo Video Generator. El prompt
  anti-movimiento ya está dentro: no lo cambies.
- **Tandas de ≤5 imágenes.** Kling va a ~8 min por clip, uno detrás de otro,
  y un nodo que pasa de **60 min falla entero** («Node execution timed
  out») — con 24 imágenes se perdió la tanda.
- La cola de Kling es **de la cuenta**: si otra sesión o persona está
  generando, alternad tandas y avisaos. No vacíes la lista mientras el nodo
  diga «Generating video N of M».
- Los resultados salen en la lista de salida y en el historial de la cuenta;
  recorta cada clip a ~7,3 s (el final trae fundido) antes de subirlo.

**Imágenes en Magnific** (Image Generator, modelo **Nano Banana 2
«Unlimited»**, 9:16): solo si Flow no se puede usar (p. ej. el navegador del
PC está minimizado u oculto: Flow deja de responder, Magnific no). Va lento
(~5-6 min por imagen, cola de 8 por cuenta). Recarga la página entre
productos: las referencias adjuntas se acumulan y mezclan productos. Tras
recargar, comprueba otra vez 9:16 y el modelo.

> ⚠️ Estos enlaces son de septiembre de 2026, de antes de dejar Magnific y
> volver a él. Si un space no abre o no hace lo que dice la tabla, **para y
> pregunta** al operador por el enlace nuevo.

---

## Gemini / ChatGPT (texto, no imagen)

La app ya escribe con Gemini los textos, guiones y escenas («Obtener textos»,
«Escribir guiones», «Escribir las escenas»). **No** hace falta ir a ChatGPT
salvo donde la guía lo diga expresamente (la ficha del personaje de UGC, que
se saca en Gemini; el guion con plazos de Moda, en ChatGPT).
