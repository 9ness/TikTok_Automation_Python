# Subidas (contador diario de publicaciones)

Pantalla `/subidas` (menú lateral de `nes_bugallo` y de `ness`): cuántos
**carruseles** y **vídeos** se publican cada día en la cuenta, el total del mes
y la media por día frente al objetivo. Es de la **cuenta árabe** de Bugallo
(Xiaomi Mi 8): contexto completo en `docs/CUENTA_ARABE.md` (§1 ritmo, §5
subida automática, §6 usuario `nes_bugallo`).

La pantalla **solo lee**: lo apuntan los agentes con el MCP. Cada usuario
apunta en SU contador (el del token). `ness` puede apuntar o ver el de
Bugallo con `usuario="nes_bugallo"`.

## Objetivo

| Etapa | Carruseles/día | Vídeos/día |
|---|---|---|
| Primeros días | 15 | 5-10 |
| Después | **45** | **10** |
| Más adelante | 45 | 20 |

La pantalla pinta en verde lo que llega a 45 + 10 y en ámbar lo que no.

## Cuándo apuntar

- **Al terminar cada tanda de subida del Mi 8** (la de carruseles y la de
  vídeos, a mano o con la tarea nocturna de las 00:00): `registrar_subidas`
  con lo que se ha **publicado de verdad** en esa tanda, en modo `sumar`.
  Lo que falló o se quedó en borradores no cuenta.
- La fecha es la del día en que se publica (hora de Madrid). Sin `fecha`,
  hoy. Una tanda que empieza a las 00:00 cuenta para el día que empieza.
- Si te equivocas o hay que cuadrar con lo que se ve en el perfil de TikTok,
  corrige con `modo="fijar"`: pone el número exacto del día.

## Herramientas

- `registrar_subidas(fecha="", videos=0, carruseles=0, nota="", modo="sumar", usuario="")`
  - `sumar` (por defecto) añade a lo que ya había ese día; `fijar` lo
    sustituye.
  - `nota`: corta («tanda 00:00», «3 fallaron por Comprobar contenido»…). Con
    `sumar` se añade detrás de la anterior; vacía deja la que había.
  - Devuelve el día apuntado y los totales del mes.
- `ver_subidas(mes="", usuario="")`: días apuntados del mes (`AAAA-MM`, por
  defecto el actual) y totales: `videos`, `carruseles`, `total`,
  `dias_con_subida`, `dias_transcurridos` y `media_dia`.

Ejemplo, al acabar la tanda de carruseles de la noche:
`registrar_subidas(carruseles=15, nota="tanda 00:00")`; y luego la de vídeos:
`registrar_subidas(videos=6)`.
