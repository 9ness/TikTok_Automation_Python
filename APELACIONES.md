# Apelaciones de sanciones de TikTok Shop

Sanción típica: **«promoción de productos incoherente»** (-24 puntos,
visibilidad reducida y producto retirado del vídeo), detectada por
«medidas automatizadas». Se apela desde la infracción en la app de TikTok:
**un solo intento**, 180 días de plazo y el vídeo tiene que seguir
**público** mientras se revisa (no borrarlo: tampoco quita la sanción).

**Mejor que apelar: la «Comprobación previa» de TikTok Shop** (al añadir el
producto al vídeo › «Haz una comprobación previa de tu vídeo»). Revisa el vídeo
con las normas de contenido ANTES de publicarlo; con «Publicar» activado lo
sube solo si pasa. **10 comprobaciones al día**. TikTok avisa de que el
resultado «solo es una referencia y no garantiza el resultado final», así que
no sustituye revisar el vídeo contra la ficha. Con la cuenta al límite de
puntos, pasa por ahí todo lo que se publique (o, si hay más de 10, los de más
riesgo: aparatos con pantalla o botones, packs, marcas y letra pequeña).

Antes de apelar, comprueba de verdad que el vídeo no tiene fallo
([`revision-calidad.md`](src/agente_mcp/guias/comun/revision-calidad.md)):
producto idéntico a la ficha pieza a pieza, voz y textos sin promesas que la
ficha no tenga. Si el fallo es real (pieza inventada, puertos que aparecen…),
no se apela: se rehace el vídeo.

## Método que ha funcionado (curso + casos propios)

1. **Pruebas** (5-7 imágenes):
   - fotograma del vídeo donde se ve bien el producto,
   - captura de la ficha enlazada (Marketplace o escaparate),
   - la foto del producto de la ficha,
   - una comparativa vídeo | ficha lado a lado (ayuda mucho),
   - las capturas completas de la infracción (fecha, motivo, nº de caso).
2. **Texto** en español, tono profesional, **máximo 500 caracteres** (límite
   del campo «Motivo» de la apelación; cuéntalos antes de dárselo al
   operador, apunta a ~480), con esta forma:
   - «Solicito una revisión manual.»
   - El producto del vídeo coincide con el enlazado: diseño, color, forma,
     marca/etiqueta **concretos** (qué se ve igual).
   - La voz/texto solo repite datos de la ficha y no promete nada que el
     producto no tenga.
   - **UNA** «probable causa del error» automático (idioma del envase distinto
     al de la ficha, un objeto de comparación en la escena, etc.).
   - «Adjunto ficha y capturas. Pido retirar la sanción, reactivar el
     producto y devolver los 24 puntos.»
3. **No escribir**:
   - «La discrepancia no fue intencional» → reconoce que hubo diferencia.
   - Que has corregido el enlace o quitado imágenes → contradice el
     argumento.
   - Varias apelaciones: se envía una sola.

## Casos

| Fecha | Producto | Causa alegada | Resultado |
|---|---|---|---|
| 19/9/2026 | Cheetos Mac'n Cheese «Four Cheesy» | envase en inglés, ficha y vídeo en español («4 Quesos») | ✅ aprobada |
| (curso) | Esterilizador y secador de biberones | error de detección, producto idéntico | ✅ aprobada |
| (curso) | Producto con ficha en inglés | contenido en español y ficha en parte en inglés | ✅ aprobada |
| 28/9/2026 | MIKOMIKA espejo maquillaje LED (Inventario · Carpeta_28 · p7) | es un espejo: refleja la habitación y la mano (6 pruebas, sin fotogramas del clip 1) | ❌ rechazada 28/9 |
| 27/9/2026 | FUFFI mini teléfono (Tareas Productos 8 · p1) | móvil normal al lado para comparar tamaño (7 pruebas) | ❌ rechazada 28/9 (respuesta genérica) |
| 2/10/2026 | Multimodo (Ana) · botas altas Vintage (Zapatos C3 · p6) — «contenido estático» -4 | vídeo real: piernas que se cruzan y mano; el rótulo de temporada fijo 10 s + cámara quieta lo hizo parecer foto con texto (movimiento medido 3,3) | ⏳ pendiente |
| 2/10/2026 | Multimodo (Ana) · bolso ZS BAG Vintage, versión antigua sin mano | NO se apela: bolso quieto, sin mano y texto metido en la imagen | — |
| 29/9/2026 | Botas de fútbol SAIBI (Tareas Productos 9 · p10) — sanción -4 «contenido estático / slideshow» | vídeo real con movimiento de mano, voz y subtítulos; el detector lo confundió con imagen fija (escena parecida a las fotos de la ficha) | ✅ aprobada (4 puntos devueltos) |

Texto y pruebas de cada caso nuevo: en el Drive,
`TIKTOK_SHOP_AI_PRO/_apelaciones/<fecha>_<producto>/` (`apelacion.txt` +
imágenes numeradas en el orden en que se adjuntan). Cuando TikTok responda,
actualiza la tabla con el resultado.

### Qué nos dicen las dos rechazadas (FUFFI y MIKOMIKA, sep 2026)

Las dos eran vídeos generados con IA donde el producto **no se veía igual en
los dos clips** (otro móvil al lado y pantallas inventadas; espejo muy de lado,
luces apagadas y sin los botones táctiles en un clip). La revisión humana mira
el vídeo ENTERO, no nuestras capturas: si en algún plano el producto no es
idéntico a la ficha, la apelación se pierde aunque las pruebas enseñen el plano
bueno. La aprobada (Cheetos) era un vídeo sin inconsistencias y un fallo de la
máquina explicable (idioma del envase).

Por tanto:
- **Antes de apelar, mira el vídeo PUBLICADO fotograma a fotograma.** Si algún
  plano no coincide con la ficha, no gastes el intento: la sanción no se quita
  borrando, así que lo que toca es no repetir el fallo.
- Apela solo cuando el vídeo sea coherente de principio a fin y haya una causa
  de la máquina clara (idioma, marca que no se lee, producto de aspecto raro
  pero idéntico a la ficha).
- La prevención vale más que la apelación: revisar con
  [`revision-calidad.md`](src/agente_mcp/guias/comun/revision-calidad.md)
  antes de publicar.

### Rechazada — FUFFI mini teléfono (27/9/2026)

Respuesta genérica («infracción válida de nuestras pautas»), sin decir qué
vio. Lo más probable, y es de NUESTRO vídeo, no de la apelación:

- En una escena pusimos **otro teléfono** (uno normal) al lado para que se
  viera lo pequeño que es. En un vídeo que vende un teléfono, un segundo
  teléfono es «otro producto» para el revisor.
- En esa misma escena el generador **encendió las pantallas con iconos de
  apps inventados**, y la ficha enseña otro fondo de pantalla y la trasera
  con doble cámara.

Lección: si el vídeo lleva un objeto de la MISMA categoría que el producto,
la apelación no se sostiene; alegarlo como «causa probable» es admitir que
está. Esos vídeos no se apelan: se rehacen sin ese objeto (ver
[`pov-bof-largo.md`](src/agente_mcp/guias/pov-bof-largo.md)).

### Texto aprobado — Cheetos (19/9/2026)

> Solicito una revisión manual. El producto del vídeo coincide con el
> enlazado: misma caja morada de Cheetos Mac'n Cheese, logotipo, personaje
> Chester, variedad «Four Cheesy» y bol de la portada. La voz solo repite el
> título de la ficha y no promete nada que el producto no tenga. Probable
> causa del error: el envase está en inglés («Four Cheesy») y la ficha y el
> vídeo en español («4 Quesos»). Adjunto ficha y capturas. Pido retirar la
> sanción, reactivar el producto y devolver los 24 puntos.

### Otro tipo de sanción: «contenido estático» (-4 puntos, 29/9/2026)

Motivo automático: «slideshow or scrolling images… still-frame content: no se
permiten imágenes estáticas… usa contenido dinámico con movimiento o
interacción». Fue el vídeo de las botas de fútbol (Tareas Productos 9 · p10):
producto y cámara **inmóviles**, solo se mueve el dedo, y encima rótulos fijos
a pantalla completa. Medido (diferencia media entre fotogramas): 1,63 en todo
el vídeo y **1,15 en el segundo clip**; los que no dan problema andan en 2-3.
Es una sanción de 4 puntos (no 24), pero cuenta.

**Resultado: apelación APROBADA (29/9/2026), sin confirmar la causa real.** Todos nuestros vídeos tienen la misma
estructura (mano señalando + rótulos + voz + subtítulos) y la mayoría pasa sin
problema; el detector automático es inconsistente. La poca cámara en movimiento
es solo una hipótesis (los clips se parecían mucho a las fotos de la ficha).
Como no era un fallo claro del vídeo se apeló (vídeo público, capturas de
fotogramas sin etiquetas de «clip» —para ellos es un vídeo entero— y texto de
478 caracteres) y **se aprobó**. Pruebas y texto en el Drive:
`_apelaciones/2026-09-29_botas_futbol_estatico/`. Lección: cuando el vídeo es
coherente y la sanción es de la máquina, apelar funciona; no hace falta
rehacerlo.

Prevención (por si ayuda): al generar los clips pide **movimiento real** — cámara con paseo o
acercamiento suave, la mano moviéndose de forma natural, no solo «quieto y
quieto» — y comprueba con la «Comprobación previa» antes de publicar. El
prompt «One continuous shot with the same framing… completely motionless»
deja el clip casi como una foto: mantén el producto quieto pero deja mover la
cámara y la mano. Vídeos ya hechos con poco movimiento (diferencia < ~1,5,
sobre todo en el 2.º clip) son los de más riesgo.

**Rótulo fijo + cámara quieta (2/10/2026, multimodo):** dos vídeos Vintage
sancionados a los 6 min de publicarse. Uno era de verdad casi una foto (bolso
quieto, sin mano); el otro tenía movimiento de sobra (3,3), pero el rótulo
quieto en el centro los 10 s con el fondo inmóvil se lee como «texto animado
sobre imagen». Desde entonces el rótulo del multimodo dura 3 s.
