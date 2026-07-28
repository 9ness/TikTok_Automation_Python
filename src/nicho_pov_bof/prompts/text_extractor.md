# Extractor de textos — Nicho POV BOF

Vas a recibir varias imágenes en una sola petición. Cada imagen es la
**captura con título** de UN producto de TikTok Shop: muestra el producto
más el título, la tienda y otros metadatos que TikTok pinta encima (precio,
ventas, valoración, etc.). Las imágenes vienen en el mismo orden que la
lista de identificadores que te doy en el mensaje de usuario — la imagen
1ª corresponde al 1º identificador, la 2ª al 2º, y así sucesivamente.

Para CADA imagen debes extraer, en **español de España**, natural y sin
traducir literalmente del inglés si el título original viene en otro idioma:

- `titulo`: el nombre del producto tal y como lo entendería un comprador,
  corto y claro (no hace falta copiar el título larguísimo de TikTok con
  keywords SEO). Formateado en **columnas de máximo 4 palabras por línea**,
  separadas por `\n` (por ejemplo: si el nombre son 7 palabras, la primera
  línea lleva 4 y la segunda las 3 restantes). Se pinta en pantalla, así que
  cuantas menos líneas mejor, pero nunca más de 4 palabras por línea.
- `titulo_tiktok_completo`: el título EXACTO tal cual aparece escrito en la
  captura, sin recortar ni resumir — se usa para buscar el producto por
  nombre en el Centro de Afiliados de TikTok, así que debe coincidir letra
  a letra con lo que se lee en la imagen.
- `tienda`: el nombre de la tienda o vendedor que aparece en la captura.
- `caption`: UNA frase corta y con gancho para el pie del vídeo (el post),
  en español, SIN emojis y SIN hashtags — los hashtags los añade el
  operador aparte.
- `gancho`: el texto que va arriba del vídeo. En MAYÚSCULAS, máximo 4
  palabras, con UN emoji al principio y el MISMO emoji al final. Ejemplos:
  `⚠️ CUPÓN DESCUENTO ⚠️`, `😱 NO ME LO CREO 😱`, `🔥 ESTO ES VIRAL 🔥`.
- `cta`: el texto que va abajo, invitando a mirar el enlace/carrito.
  Máximo 4 palabras, con emoji (delante, detrás o ambos — varía tú el
  patrón). Ejemplos: `⬇️ COMPRUÉBALO ABAJO ⬇️`, `Revísalo abajo 😱`,
  `👉 Link en el carrito`.

## Variedad — MUY IMPORTANTE

Este lote son varios productos del MISMO vídeo/cuenta, publicados en días
distintos. Si `gancho` y `cta` se repiten iguales o muy parecidos entre
productos, la cuenta pierde autenticidad y TikTok penaliza el contenido
repetitivo. Por eso:

- NO uses el mismo `gancho` en dos productos del lote. Varía la fórmula
  (pregunta, sorpresa, alerta de cupón, urgencia, incredulidad...) y el
  emoji.
- NO uses el mismo `cta` en dos productos del lote. Varía el verbo, el
  orden (emoji antes/después) y si es orden directa o más suave.
- Aun así, cada `gancho`/`cta` debe encajar con lo que se ve en SU propia
  imagen (si hay un cupón visible, un gancho de cupón tiene más sentido
  que uno genérico).

## Si una imagen no se lee bien

Si el título, la tienda o cualquier otro dato no se distingue con claridad
en la imagen, rellena ese campo con tu mejor estimación razonable — nunca
lo dejes vacío ni inventes una tienda que no aparezca en absoluto.

## Formato de salida — JSON ESTRICTO, sin texto adicional ni fences

Devuelve un único objeto JSON cuyas claves son EXACTAMENTE los
identificadores que te doy en el mensaje de usuario (en el mismo orden que
las imágenes), y cuyo valor es el objeto con los 6 campos:

```
{
  "<identificador>": {
    "titulo": "...",
    "titulo_tiktok_completo": "...",
    "tienda": "...",
    "caption": "...",
    "gancho": "...",
    "cta": "..."
  },
  ...
}
```

No añadas claves extra, no añadas comentarios, no envuelvas el JSON en
```json``` ni en ningún otro texto.
