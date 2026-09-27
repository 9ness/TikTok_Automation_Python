# Apelaciones de sanciones de TikTok Shop

Sanción típica: **«promoción de productos incoherente»** (-24 puntos,
visibilidad reducida y producto retirado del vídeo), detectada por
«medidas automatizadas». Se apela desde la infracción en la app de TikTok:
**un solo intento**, 180 días de plazo y el vídeo tiene que seguir
**público** mientras se revisa (no borrarlo: tampoco quita la sanción).

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
| 27/9/2026 | FUFFI mini teléfono (Tareas Productos 8 · p1) | móvil normal al lado para comparar tamaño | ⏳ pendiente |

Texto y pruebas de cada caso nuevo: en el Drive,
`TIKTOK_SHOP_AI_PRO/_apelaciones/<fecha>_<producto>/` (`apelacion.txt` +
imágenes numeradas en el orden en que se adjuntan). Cuando TikTok responda,
actualiza la tabla con el resultado.

### Texto aprobado — Cheetos (19/9/2026)

> Solicito una revisión manual. El producto del vídeo coincide con el
> enlazado: misma caja morada de Cheetos Mac'n Cheese, logotipo, personaje
> Chester, variedad «Four Cheesy» y bol de la portada. La voz solo repite el
> título de la ficha y no promete nada que el producto no tenga. Probable
> causa del error: el envase está en inglés («Four Cheesy») y la ficha y el
> vídeo en español («4 Quesos»). Adjunto ficha y capturas. Pido retirar la
> sanción, reactivar el producto y devolver los 24 puntos.
