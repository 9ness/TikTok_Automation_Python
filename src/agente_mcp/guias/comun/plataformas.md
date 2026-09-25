# Dónde se generan las fotos y los clips

La app **no genera** ni las imágenes ni los vídeos: te da el prompt y las
fotos, y tú los generas en una de estas webs (con la cuenta del operador, ya
abierta en el navegador). Luego el clip vuelve a la app para que lo edite.

## Qué se usa para qué

| Qué | Dónde | Notas |
|---|---|---|
| **Todas las imágenes** | **Google Flow** · modelo Nano Banana 2 · 9:16 | Salvo Creativos Pro, que va en 3:4 |
| Clip que **habla** (la voz va dentro del clip) | **Google Flow** · modelo Omni | Único que locuta. 8 s o 10 s |
| Clip **mudo** (la voz la pone la app, o va sin voz) | **Google Flow**, **GenAI Pro** o **Magnific** | Pregunta cuál. Ver tabla de abajo |

| Plataforma | Voz | Duración | Calidad | Coste |
|---|---|---|---|---|
| Google Flow (Omni) | ✅ | 8 s o 10 s | 720p → reescalar a 1080p | 12 créditos (8 s) · 15 créditos (10 s) |
| GenAI Pro | ❌ | hasta 8 s | 1080p | lo que marque su web |
| Magnific (spaces) | ❌ | 8 s o 10 s | la del space | lo que marque su web |

Qué menú admite qué:

- **POV BOF, POV BOF Largo**: la voz la pone la app → cualquiera de las tres.
- **Moda (formatos hablados), UGC**: la voz va en el clip → **solo Flow**.
- **Moda (formatos mudos 🔇), Marca Personal**: cualquiera de las tres.

---

## Google Flow — `https://flow.google.com/`

Trabaja dentro de un **proyecto** por carpeta de productos (ej. «Moda Mujer ·
Carpeta 24»): así las imágenes quedan juntas y puedes reutilizarlas como
frame o ingrediente sin volver a subirlas.

### Imagen (Nano Banana 2)

1. Modo de **crear imagen**, modelo **Nano Banana 2**, formato **9:16
   vertical** (3:4 en Creativos Pro). **1 resultado por prompt** (no 2 ni 4:
   gasta el doble y no hace falta).
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

Solo vídeo, **mudo**. Ajustes, siempre los mismos:

- **hasta 8 s** · modo **Frames** · **start + end frame** · **Portrait 9:16**
  · **1 vídeo** · calidad **Original**.
- **Start frame y end frame: la MISMA imagen** (la generada en Flow). Así el
  clip vuelve al punto de partida y dos clips seguidos casan.
- Pega el «Prompt vídeo» de la app (en POV BOF / Largo es el mismo para todos
  los productos).
- Si la tarjeta pide 2 clips, genera **dos clips** de la misma imagen (cada
  generación sale distinta; eso es lo que se busca).

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

> ⚠️ Estos enlaces son de septiembre de 2026, de antes de dejar Magnific y
> volver a él. Si un space no abre o no hace lo que dice la tabla, **para y
> pregunta** al operador por el enlace nuevo.

---

## Gemini / ChatGPT (texto, no imagen)

La app ya escribe con Gemini los textos, guiones y escenas («Obtener textos»,
«Escribir guiones», «Escribir las escenas»). **No** hace falta ir a ChatGPT
salvo donde la guía lo diga expresamente (la ficha del personaje de UGC, que
se saca en Gemini; el guion con plazos de Moda, en ChatGPT).
