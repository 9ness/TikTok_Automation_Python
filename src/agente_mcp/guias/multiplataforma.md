# Multiplataforma — enlaces de afiliado y resubida de Mis tandas

> Para un agente con el MCP «tiktok-shop-ai-pro» conectado con el **token de
> un administrador (ness)**: los endpoints de multiplataforma no están abiertos
> a los usuarios `pro`. Lo hace TODO el agente, de principio a fin: el
> operador no tiene pantalla para esto.

Los vídeos ya montados (los que lista **Mis tandas** del dueño de cada cuenta)
se vuelven a publicar en **Instagram Reels, Facebook Reels, Threads y
Pinterest**, cada uno con el enlace de afiliado de SU producto. Tu trabajo es
encontrar ese enlace, guardarlo y encolar los vídeos.

| Cuenta (`cuenta`) | Dueño (vídeos de su Mis tandas) | Enlaces |
|---|---|---|
| `ama_shop` | `ana` (moda) | **SHEIN**: el enlace del panel de afiliados de Ana, tal cual (`https://onelink.shein.com/...`) |
| `viva_shop` | `ness` (Pisada Viva) | **Amazon**: solo el **ASIN**; la app construye el enlace con el tag de la cuenta |

`cuentas_multiplataforma()` da la lista viva (slug, dueño, tag, ritmo, horas).

## Reglas que no se saltan

- **Los enlaces de Amazon/SHEIN van SOLO en Instagram, Facebook, Threads y
  Pinterest. NUNCA en TikTok**: allí el vídeo lleva el carrito de TikTok Shop
  y un enlace externo es motivo de sanción. No los pongas en captions,
  comentarios ni bio de TikTok.
- **Nunca acortadores** (`amzn.to`, `bit.ly`…): la app los rechaza. SHEIN se
  pega tal cual sale del panel; de Amazon solo el ASIN.
- **El parecido se decide mirando FOTOS**, no títulos. Mismo tipo de producto,
  misma forma y mismo color/estampado. «Parecido» no es «de la misma
  categoría»: si no hay uno de verdad igual, es `sin_equivalente`. Un enlace a
  otro producto distinto engaña a quien compra y nos quita la cuenta de
  afiliado.
- No compres nada ni toques la configuración del panel de afiliados.
- No publiques a mano en ninguna red: lo publica el tick del servidor.

## Paso a paso

1. **`guia("multiplataforma")`** (esta página) y `cuentas_multiplataforma()`.
2. **`productos_sin_enlace(cuenta)`** → productos del dueño sin enlace, con
   `producto_key`, título, tienda, `product_url` (ficha de TikTok), `foto`,
   `subidos_tiktok` y `en_cola`. Empieza por los que más `subidos_tiktok`
   tienen (salen primero): son los que se pueden encolar ya.
   `todos=True` enseña también los ya hechos.
3. **Mira la foto** del producto: `ver(url=<foto>)`.
4. **Busca el equivalente** con el navegador:
   - **SHEIN (`ama_shop`)**: en el **panel de afiliados de SHEIN de Ana**,
     abierto en el Chrome remoto del VPS (cómo usarlo:
     [`comun/navegador-vps.md`](comun/navegador-vps.md)). Busca por el tipo de
     prenda y color («vestido midi satinado verde»), abre los candidatos y
     genera ahí el enlace de afiliado del bueno.
   - **Amazon (`viva_shop`)**: busca en amazon.es y copia el **ASIN** de la
     ficha (10 caracteres, aparece en la URL `/dp/<ASIN>` y en «Detalles»).
5. **Compara FOTOS** del candidato con la de `productos_sin_enlace`
   (`ver(url=…)` con la imagen del candidato si hace falta): tipo, forma,
   color, detalles visibles (cuello, mangas, suela, tapa…). Si dudas entre
   dos, el más parecido; si ninguno lo es de verdad, `sin_equivalente`.
6. **`guardar_enlace(cuenta, producto_key, shein=… | asin=…, nota=…)`**.
   - `nota`: una frase de qué has comparado («mismo vestido satinado verde,
     tirantes finos; SHEIN no tiene la abertura lateral»).
   - Opcional: `foto_url` (https de la foto del candidato) y `titulo` corto:
     es lo que sale en la página pública `/links/<cuenta>` (solo desde que se
     publica su vídeo; la categoría sale de las palabras del título).
   - Sin equivalente: `shein="sin_equivalente"` (o `asin=`) + `nota`. Ese
     producto ya cuenta como revisado y no se encola.
   - Producto de temporada (tumbonas, piscinas, ventiladores, paddle surf…):
     `temporada="verano"` (o `"invierno"`, `"navidad"`). Se guarda igual, pero
     solo se encola en sus meses.
   - Para corregir, vuelve a llamar; `borrar=True` lo quita.
7. Si la cuenta tiene `auto_tandas` > 0 (encolado automático), no hace falta:
   el tick encola solo, cada hora, lo subido a TikTok con enlace. Si no,
   **`encolar_tandas(cuenta)`** cuando hayas guardado unos cuantos: mete en la
   cola los vídeos de productos CON enlace que aún no estén (repetirlo no
   duplica). Por defecto **solo los ya subidos a TikTok**;
   `incluir_no_subidos=True` si el operador lo pide. Se reparten con el ritmo
   y horas «producto» de la cuenta, tras lo ya programado. Los vídeos MUDOS
   (multimodo de 10 s) se encolan con música sin copyright ya mezclada, elegida
   por su sugerencia de música (`musica` en la respuesta: «estilo/pista»); los
   que tienen voz van tal cual. Mira en la
   respuesta lo `omitidas` (`sin_enlace`, `no_subidos`, `ya_encolados`,
   `ruta_no_valida` = el vídeo está fuera del Drive del Programa 4).
8. **`cola_multiplataforma(cuenta)`** → qué sale y cuándo, y el estado por
   plataforma: `pendiente`, `simulado` (la cuenta aún no tiene token de esa
   red: modo prueba, se publicará cuando lo tenga), `publicado`, `error`
   (se reintenta), `fallido` (mira `errores`).

Los vídeos nuevos que se monten más adelante aparecen solos en
`productos_sin_enlace` (si su producto no tiene enlace) o se encolan con el
siguiente `encolar_tandas` (si ya lo tiene: el enlace vale para todas las
versiones del producto, también las copias de Productos Q4).

## Carruseles de fotos (Replicar carrusel)

Un carrusel con TODAS sus fotos hechas se publica en IG/FB/Threads con
`encolar_carrusel(cuenta, carrusel_id, asin=… | shein=…, caption=…, desde="AAAA-MM-DD")`:
- Cuenta por nicho: hogar, mascotas, accesorios → `viva_shop`; salud/belleza →
  `viva_salud`; moda mujer → `ama_shop` (SHEIN).
- El enlace es el MISMO producto o un parecido válido (tipo, forma, color),
  buscado igual que arriba. Si no hay uno fiable, ese carrusel **no va a Meta**.
- `caption` en español y sin «carrito» ni TikTok (vacío = el de la réplica
  limpio). Sale uno al día a las 17:00 (± unos minutos), tras el último ya
  programado de esa cuenta. Repetir la llamada no duplica.
- IG recibe las fotos en un lienzo 4:5 (no admite 3:4 ni 9:16). La música no
  se puede poner por API: la respuesta trae la sugerida.

## Informe al terminar

Una línea por producto: «✅ enlace (SHEIN/ASIN) · ⛔ sin_equivalente (motivo)
· ⏭️ saltado (motivo)», y cuántos vídeos has encolado y desde qué fecha.

## Detalles técnicos (por si los necesitas)

- `producto_key` = hash de `tienda|título` normalizados: la misma identidad
  que usa Mis tandas para «mismo producto». Si se reescribe el título del
  producto en su nicho, cambia y habría que volver a guardar el enlace.
- API: `GET /api/v1/multiplataforma/cuentas/{cuenta}/productos?sin_enlace=1`,
  `PUT|DELETE /cuentas/{cuenta}/enlaces/{producto_key}`,
  `POST /cuentas/{cuenta}/encolar-tandas`, `POST /cuentas/{cuenta}/carrusel`, `GET /cola`.
- Página pública (para la bio de IG/FB): `/links/<cuenta>`.
