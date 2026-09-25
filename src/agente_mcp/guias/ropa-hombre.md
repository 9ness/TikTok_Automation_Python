# Ropa Hombre — `/tiktok-shop-ai-pro/nicho-ropa-hombre`

Lee antes [`README.md`](README.md), las guías de [`comun/`](comun/) y
**[`moda-mujer-aleatorios.md`](moda-mujer-aleatorios.md)**: es la misma
pantalla con los mismos pasos (situarte → textos → fotos → copiar el prompt →
subir → descargar). Aquí solo va lo que cambia.

## Qué sale

Un clip por prenda y por modo, con un **chico distinto cada vez** (o sin
persona, en Maniquí). Cuenta nueva → **máximo 10 vídeos al día**, mezclando
modos.

## Los siete modos

| Botón | Producto | Voz | Imagen | Guion / movimiento | Clip |
|---|---|---|---|---|---|
| 🪞 **BOF Frente a Espejo** | ropa | 🗣️ habla | foto de la prenda | la app lo escribe («✍️ Escribir guiones») | Flow · FRAME INICIAL · 10 s u 8 s |
| 🤳 **BOF Selfie** | ropa | 🗣️ | foto de la prenda | la app lo escribe | Flow · FRAME INICIAL · 10 s u 8 s |
| 🚶 **Situación Real 1** | ropa | 🗣️ (diálogo) | foto de la prenda | «2 · Guion (Flow)» fijo, tal cual | Flow · FRAME INICIAL · 10 s |
| ☕ **Situación Real 2** | ropa | 🗣️ (diálogo) | la MISMA imagen que Real 1 | «2 · Guion (Flow)» fijo | Flow · FRAME INICIAL · 10 s |
| 🕶️ **Gafas en Coche** | **solo gafas** | 🗣️ | foto de las gafas | la app lo escribe · ⚠️ promete plazos | Flow · FRAME INICIAL · 10 s u 8 s |
| 😏 **Camiseta Sarcástica** | **solo camisetas con frase** | 🔇 mudo | foto de la camiseta | «2 · Vídeo (movimiento)» | Flow (Omni) · FRAME INICIAL · 10 s |
| 🧍 **Camiseta Maniquí** | **solo camisetas** | 🔇 mudo | foto de la camiseta (maniquí sin cabeza, sin persona) | «2 · Vídeo (movimiento)» | Flow · FRAME INICIAL · 10 s |

⚠️ La pantalla **no filtra por categoría**: las carpetas de hombre mezclan
abrigos, zapatillas, gafas y camisetas. Elige tú los productos que encajan con
el modo y sáltate el resto (anótalo en el informe).

## Lo que cambia respecto a Moda Mujer

- **Real 2**: si ya hiciste Real 1 de esa prenda, reutiliza su `imagen_1.png`;
  solo cambia el diálogo.
- **Gafas en Coche**: como el Selfie de mujer, su guion **promete pago a
  plazos** → solo con productos que los tengan, o borra esa frase antes de
  pegarlo en Flow.
- **Camiseta Sarcástica**: en Flow/Omni, además del movimiento, hay que
  poner **una risa** del banco de sonidos del propio generador (primero se
  mete el producto para que filtre por sonidos comerciales, luego se vuelve
  atrás y se busca «RISAS»). Si tu entorno no lo permite, genera el clip sin
  la risa y dilo en el informe. En la tarjeta el clip se sube tal cual.
- Los **mudos** (Sarcástica, Maniquí) también se pueden hacer en GenAI Pro
  (8 s) o Magnific; pregunta. En la tarjeta, al ser mudos, no hay chip de voz.
- Revisa que la **frase de la camiseta** sale igual que en la foto (letra por
  letra): una frase inventada es «alterar el producto».

## API útil (solo lectura)

- `GET /api/v1/nicho-ropa/carpetas?sexo=hombre&modo=<modo>&catalogo=<web|muestras|tareas>`
- `GET /api/v1/nicho-ropa/prendas?carpeta=<slug>&modo=<modo>`
- `GET /api/v1/nicho-ropa/prompts?carpeta=<slug>&modo=<modo>&duracion=10|8`

Claves de modo: `espejo`, `camara`, `calle_1`, `calle_2`, `gafas_coche`,
`sarcastica`, `maniqui`. Salida en el VPS:
`~/gdrive/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Nicho_Ropa_Sin_Personas/videos/[<usuario>/]<carpeta>/<nombre>__<modo>.mp4`.

## Con el MCP

Con el MCP: `menu="ropa_hombre"`, `modo=` una de las claves de arriba.
