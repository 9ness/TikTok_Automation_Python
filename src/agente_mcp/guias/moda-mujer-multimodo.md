# Moda Mujer · Multimodo — `/tiktok-shop-ai-pro/moda-mujer-multimodo`

Lee antes [`README.md`](README.md) y las tres guías de [`comun/`](comun/).
Es la misma pantalla que [Moda Mujer · Aleatorios](moda-mujer-aleatorios.md)
(pasos y tarjetas iguales). Lo que cambia es que **no hay un modo fijo**: en
**cada producto eliges tú el formato** que mejor le va, y así la cuenta no se
ancla en uno solo. Está pensado para que lo trabaje un agente.

## Qué sale

Un clip **mudo** de 10 s por producto. Nadie habla: la música la pone el
operador en TikTok al publicar (en Camiseta Sarcástica, además, el sonido de
risas). La app encuadra a 1080×1920 y limpia metadatos; los dos formatos
«Multi Escena» llevan además el grado de color y el texto de temporada. Los
Vintage traen su texto otoñal quemado YA en la imagen (lo pone Nano Banana).

## Catálogos

| Catálogo (`catalogo`) | Qué hay |
|---|---|
| `web` | Ropa Mujer de su web (las carpetas de siempre) |
| `zapatos` | Zapatos Mujer (zapatillas, botas, tacones…) |
| `accesorios` | Accesorios Mujer (bolsos y gafas) |
| `muestras` / `tareas` | Los del operador |

## Qué formato para cada producto

Cada producto trae `tipo_multimodo` (sale del título): `ropa`, `camiseta`,
`calzado`, `botas`, `bolso` o `gafas`. Elige un formato de SU tipo y **alterna**
dentro de la carpeta (no pongas el mismo a todos).

| Tipo | Formatos (`modo`) | Personaje | Imagen en el clip |
|---|---|---|---|
| ropa (vestidos, pantalones, jerséis, chaquetas…) | `mm_espejo` (Espejo Solo Música) · `mm_espejo_escenas` (Espejo Multi Escena) | **sí** | FRAME INICIAL |
| camiseta | `mm_maniqui` (sin persona) · `mm_sarcastica` (solo si la camiseta lleva FRASE) · o los de ropa | maniquí no / sarcástica sí | FRAME INICIAL |
| calzado (zapatillas, zapatos, tacones) | `mm_zapatillas_espejo` · `mm_zapatos_escenas` · `mm_zapatos_pov` | espejo y escenas sí; POV no | escenas = **INGREDIENTE**; resto FRAME INICIAL |
| botas | `mm_botas_1` · `mm_botas_2` · `mm_botas_largas_1` · `mm_botas_largas_2` (las «largas», solo botas altas) · o los de calzado | no | FRAME INICIAL |
| bolso | `mm_bolso_1` · `mm_bolso_2` · `mm_bolso_3` | no | FRAME INICIAL |
| gafas | — **se saltan** (no hay formato mudo) | | |

Si el `tipo_multimodo` no cuadra con lo que ves en la foto (el título engaña),
manda la foto.

## El personaje

Donde pone «Personaje: sí», adjunta en Flow el personaje de la cuenta (el
mismo en todos los vídeos) junto a la foto del producto. Los formatos que el
curso publica con chica aleatoria llevan delante una línea
«CHARACTER OVERRIDE» que manda sobre el «random woman» del texto: no la
quites. Con el MCP, el personaje sale de `personaje_marca`.

## Dónde generar

- **Imagen**: Google Flow · Nano Banana 2 · 9:16 (gratis: repite hasta que
  salga bien).
- **Clip**: Magnific · Kling 2.5 · 10 s · imagen como fotograma inicial
  (ilimitado, aunque lento). `mm_zapatos_escenas` es la excepción: la imagen
  entra como INGREDIENTE, así que va en Flow.
- Descarga a 720p/1080p vertical, sin fotos fijas.
- **Kling 2.5 solo es ilimitado a 720p** (a 1080p gasta créditos). El Video
  Generator de Magnific deja **una** generación a la vez; para una carpeta
  entera usa un **Space** propio (duplica «Foto con IA a Video»): «Clear list»
  en la lista de entrada, «Add media» (máx. 20 por tanda), prompt en el nodo
  generador y Run. Se encola en el servidor (~5 min por clip con la cola
  libre; 10-30 si la cuenta tiene más Spaces corriendo). Agrupa por
  prompt: todos los Vintage comparten movimiento; los de espejo, otro.
- **Un nodo que pasa 60 min sin terminar falla entero** («Node execution
  timed out after 60 minutes») y se pierden los clips que no salieron. La cola
  de Kling es de la CUENTA, no del Space: lanza tandas de **2 clips** y
  no abras varios Spaces a la vez si otra persona u otro agente también
  está generando.

## Revisar antes de subir

- Imagen: el producto idéntico (forma, color, estampado, piezas); es el
  personaje en los que lo llevan; los Vintage con su texto otoñal legible y
  sin tapar el producto.
- Clip: el producto no cambia ni se mueve solo, no aparecen manos o piernas
  de más, la cara no se deforma. Compara con el vídeo de ejemplo del formato
  en su web. Repite SOLO por inconsistencias visuales.

## Paso a paso (MCP)

1. `carpetas(menu="moda_mujer_multimodo", catalogo=…)` — el progreso es del
   multimodo entero (una carpeta está hecha cuando cada producto tiene SU
   vídeo, del formato que sea).
2. `productos(menu, catalogo, carpeta)` → mira `tipo_multimodo` y
   `formato_hecho` (lo que ya tiene vídeo) y decide el formato de cada uno.
3. `plan_producto(…, modo="mm_…")` → prompts de imagen y de movimiento de ESE
   formato.
4. Imagen en Flow → clip en Magnific → revisa.
5. `subir_clip(…, modo="mm_…", clip=1)` → se monta solo.
6. Al terminar la carpeta: `marcar_carpeta(…, modo="multimodo", pendiente=True)`.

`modo="multimodo"` es solo la vista de todos los vídeos: sirve para listar y
marcar carpetas, no para subir.

## Vídeos listos

Arriba de la pantalla, **«📦 Vídeos listos por tandas»** junta todo lo montado
del multimodo (de cualquier catálogo y carpeta) de diez en diez, por orden de
montaje: «Bajar» baja la tanda entera y «Subir» marca cada vídeo como
publicado. No marques Subido/Escaparate/Vendió salvo que te lo pidan.
