# Nicho POV BOF — Programa 4 (Tiktok Shop AI Pro)

Automatiza vídeos POV de producto para TikTok Shop: el operador genera la
imagen y el vídeo fuera (Veo3 / Kling) con los prompts que da esta app, sube
el vídeo, y la app hace **toda la edición**: quitar marca de agua, textos,
flechas, audio y cuadre de duración.

> **Fase 1 (hecha)**: navegación del Drive compartido "Productos España" +
> progreso por carpeta. Ver `src/nicho_pov_bof/`.
> **Fase 2 (este documento)**: automatización de los vídeos.

---

## Flujo del operador

1. Abre una carpeta de 10 productos (p. ej. `1 Pront Flow`).
2. Copia el **prompt de imagen** → genera la imagen fuera.
3. Copia el **prompt de vídeo** → genera el vídeo en **Veo3** o **Kling**.
4. Descarga las **fotos limpias** de la carpeta.
5. Pulsa **"Obtener textos"** una vez → la app saca de las capturas con
   metadatos: título de producto, título completo de TikTok, tienda y caption.
6. Por producto: copia título / caption / tienda, elige **hombre o mujer**,
   elige **Veo3 o Kling**, y **sube el vídeo**.
7. La app edita y deja el vídeo listo en Drive. El producto queda **Subido**.
8. Si vende, marca **Vendió** → aparece en el apartado de productos que
   vendieron, con foto y título.

---

## Dato clave: las fotos van EN PARES

Dentro de una carpeta de producto hay **dos ficheros con el mismo nombre**
(p. ej. `2.PNG` dos veces). NO son duplicados:

| | Contenido | Uso |
|---|---|---|
| **Foto limpia** | El producto solo | Se descarga y se manda a Veo3/Kling |
| **Captura con título** | El producto + título y metadatos de TikTok | De aquí se extraen título, tienda y caption |

La captura con título es **más grande**. Detección: primero por dimensiones
(instantáneo), y solo si hay duda se pregunta a Gemini. El identificador
canónico de cada foto es su **file ID de Drive**, nunca el nombre.

---

## Composición del vídeo

Todo respeta las zonas seguras de TikTok: `x ∈ [0.05, 0.78]`, `y ∈ [0.15, 0.75]`
(`src/subtitles.py:TIKTOK_SAFE_Y/TIKTOK_SAFE_X`).

**Bloque de texto, en el tercio superior, 3 líneas:**

1. **Gancho** — MAYÚSCULAS, emoji a cada lado, relleno blanco y **glow de
   color** (magenta/rosa). Ej: `⚠️ CUPÓN DESCUENTO ⚠️`, `😱 NO ME LO CREO 😱`.
2. **Producto** — el título, **blanco con borde negro**, hasta 2 líneas.
3. **CTA** — emojis + glow de color (cyan/azul). Ej: `Revísalo abajo 😱`,
   `⬇️ COMPRUÉBALO ABAJO ⬇️`.

**Flecha `.mov`**: abajo a la izquierda (`x≈0.22`, `y≈0.82`), justo encima de
la etiqueta naranja de la tienda. Alpha nativo, sin chroma key. Se activa
**1 s antes** de que el audio diga *carrito / enlace / abajo / tienda*
(detección con Whisper, ver `sticker_arrow._STRONG_CTA`); si no se detecta la
palabra, desde el principio.

Fuente: **Montserrat-ExtraBold** (`assets/fonts/`). Emojis en color con
`NotoColorEmoji.ttf` (ver `ready_video.py:_render_text_png`).

---

## Audio

Ruta en Drive: `TIKTOK_SHOP_AI_PRO/Nicho_POV_BOF/audios/{hombre,mujer}/`
Nombre: `hombre1_frase1.mp3` (voz, frase).

Al detectar un audio nuevo, la app **recorta sus silencios** (sobre todo el
inicial y los intermedios) y guarda la versión recortada; el original se
conserva en `_originales/`.

El operador elige solo **hombre o mujer**; la frase y la voz se sortean.

**Cuadre de duración** (vídeo objetivo: 10 s):
- Audio más corto → se **recorta el final del vídeo**.
- Audio más largo → se **alarga el vídeo rebobinando el tramo final**
  (ida y vuelta) hasta cuadrar. No se ralentiza: deformaría el gesto de la mano.

---

## Marca de agua

- **Veo3** → se quita con `watermark_remover` (caja `veo_flow`).
- **Kling** → no lleva, no se toca.

---

## Salida

`TIKTOK_SHOP_AI_PRO/Nicho_POV_BOF/videos/<carpeta de productos>/`
Un vídeo por producto, nombrado `<n> <carpeta>.mp4` (p. ej. `1 Pront Flow.mp4`).
Vertical **1080x1920, 30 fps**.

---

## Prompts (los usa el operador fuera de la app)

**Imagen** — se copia con un botón:
> Este producto en una ubicacion ideal adaptada en un entorno donde pueda
> estar ubicado de manera real. Debe ser una ubicación diferente a la de la
> foto referencia. Respeta a la perfeccion las propiedades y caracteristicas
> del producto. Aparece una mano de una persona ultra realista en modo POV
> señalando el producto. Visto como desde la ultura de los ojos de una
> persona. No mostrar precios. No mostrar en tiendas. El producto debe verse
> con textura colores ultra realista no sintetico. La imagen tambien debe
> verse en formato ultra realista como una imagen de la vida real sacada con
> iphone 17. Sin efecto cinematografico. Iluminacion y sombras realistas. La
> imagen esta completamente enfocada.

**Vídeo** — se copia con un botón:
> La cámara se mueve de manera realista con pequeñas vibraciones. La persona
> gesticula con la mano visible de la imagen como explicando el producto.

**Extracción de títulos** (a Gemini, con las capturas):
> Te voy a pasar imágenes de productos para que extraigas los nombres y los
> ordenes del 1.jpeg al 10.jpeg (ordenados numéricamente), en columnas de 4
> palabras por línea.

---

## Estado (Redis, prefijo `nicho_pov_bof:`)

Por producto: `titulo`, `titulo_tiktok_completo`, `tienda`, `caption`,
`gancho`, `cta`, `uploaded`, `sold`, `video_path`.
Mismo patrón que `month_plan_repo` + `OutcomeBar` del calendario.

---

## Piezas del repo que se reutilizan

| Necesidad | De dónde |
|---|---|
| Botón copiar + toast | `frontend/app/tiktok-shop/calendar/page.tsx:1044` |
| Toggle Subido/Vendió optimista | `calendar/OutcomeBar.tsx` |
| Texto + emoji en PNG | `tiktok_shop/pipeline/ready_video.py:_render_text_png` |
| Overlay flecha `.mov` (alpha) | `ready_video.py:_overlay_arrow_ffmpeg` |
| Palabra CTA en el audio | `editor_auto/tools/sticker_arrow.py:_STRONG_CTA` |
| Quitar marca Veo | `tiktok_shop/pipeline/watermark_remover.py` |
| Subida multipart + cola | `api/routers/tiktok_shop/radar.py:984` |
| Gemini con imágenes | `tiktok_shop/api/gemini.py:generate_text(images=...)` |
| Zonas seguras | `src/subtitles.py:31` |
| Fuentes | `assets/fonts/` (Montserrat-ExtraBold, NotoColorEmoji) |
