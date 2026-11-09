# Programa 4 AI Pro — transversales: MCP de agentes, Multiplataforma, Estadísticas/Subidas, Mi menú, Escaparate y vendidos

> Movido literal desde CLAUDE.md (nov 2026) para no cargarlo en cada chat. Se lee solo al tocar este tema.

### Agentes de IA (MCP) — transversal al Programa 4

[`src/agente_mcp/`](src/agente_mcp/) deja que Claude / ChatGPT / Codex hagan
el trabajo de un menú: servidor MCP (paquete `mcp` 2.x, `MCPServer`) montado
en la propia API en `POST /api/mcp/<token>` (Streamable HTTP sin estado,
JSON). Las herramientas **no reimplementan nada**: llaman a los endpoints de
cada nicho en proceso (`interno.py`, `httpx.ASGITransport`) con la cookie
firmada del usuario del token, así que permisos, cola, coste y progreso por
usuario son los de la web. Adaptador por menú en `menus.py` (POV BOF, Largo,
Moda Mujer ×2, Ropa Hombre, UGC, Creativos; Carruseles solo guía).

- **Token** = `<usuario>.<HMAC(AUTH_COOKIE_KEY, MCP_TOKEN_SALT)>`: no se guarda
  en ningún sitio; cambiar `MCP_TOKEN_SALT` revoca todos. La URL de cada uno
  sale en Settings › «Conectar una IA (MCP)» (`/api/v1/agente/mi-conexion`).
- **Bandeja**: `Nebulabs/TikTok/TikTok Shop/_agente/<usuario>/` en el Drive — el MCP deja
  fotos + `PLAN.md` por producto, el agente guarda al lado lo que genera y el
  MCP lo sube a la app. Es lo único que vale igual para un agente de
  escritorio (Drive sincronizado) y uno del VPS (mount).
- **Guías** (`src/agente_mcp/guias/*.md`): la misma fuente la lee el MCP
  (`guia`), la API la sirve pública en `/api/v1/agente/guias/…` y cada
  pantalla la enlaza con «Guía IA». **Si cambias el flujo de una pantalla,
  cambia su guía.**

### Multiplataforma — publicar fuera de TikTok (oct 2026)

[`src/multiplataforma/`](src/multiplataforma/) (prefijo `multiplataforma:`, API `/api/v1/multiplataforma/*`) sube los vídeos ya montados a IG Reels (reel de prueba con `trial_params` para viralización), FB Page Reels (+ comentario con enlace), Threads y Pinterest v5 por API oficial, con enlace de afiliado Amazon/SHEIN. Sin token → `simulado`. Tick: `scripts/multiplataforma_tick.py`. Ingesta sola desde `Drive/Nebulabs/TikTok/TikTok Shop/Multiplataforma/<cuenta>/{viralizacion,producto}/` (ritmo y horas por cuenta; `MULTIPLATAFORMA_DRIVE_ROOT`, `MULTIPLATAFORMA_TZ`); el tick corre DENTRO del contenedor api. Enlace por producto (`enlaces:<slug>`) y resubida de Mis tandas del dueño de la cuenta, SOLO por MCP (guía `multiplataforma.md`); página pública sin login `/links/<cuenta>` para la bio. Los vídeos MUDOS de Mis tandas salen con música Mixkit mezclada (banco `Multiplataforma/_musica/<estilo>/`, `services/musica.py`). Enlaces NUNCA en TikTok. Detalle en [`MULTIPLATAFORMA_MODULE.md`](MULTIPLATAFORMA_MODULE.md).

### Estadísticas — ventas de la cuenta de Néstor (oct 2026)

[`src/estadisticas/`](src/estadisticas/) (prefijo `estadisticas:`, clave `ventas:<usuario>`, API `/api/v1/estadisticas`, `ness` y `nes_bugallo`, cada uno la suya) guarda lo que se lee en la app de TikTok (Datos por mes + productos con venta + tendencias por día) y la pantalla `/estadisticas` lo enseña: GMV/ventas/clics por mes, correlación clics→ventas y previsión, por día, por tipo y por país; `ness` tiene selector de cuenta (Ama Shop, Casca Chollos, cuenta árabe) y «⚖️ Comparar» (`components/estadisticas/CompararCuentas.tsx`). No hay API de TikTok: lo lee un agente en el OPPO por ADB (MCP `estadisticas_ventas`/`guardar_estadisticas`, guía `estadisticas.md`).

[`src/subidas/`](src/subidas/) (prefijo `subidas:` o `SUBIDAS_REDIS_PREFIX`, clave `<usuario>:<YYYY-MM>` → `{dias: {fecha: {videos, carruseles, nota, actualizado}}}`, API `/api/v1/subidas`, `nes_bugallo` y `ness`; ness puede pasar `usuario=`) cuenta los vídeos y carruseles publicados cada día con total y media del mes frente al objetivo 45 + 10; pantalla `/subidas` de solo lectura. Lo apuntan los agentes al terminar cada tanda (MCP `registrar_subidas`/`ver_subidas`, guía `subidas.md`). El usuario `nes_bugallo` (`pro`, cuenta árabe del Mi 8, `docs/CUENTA_ARABE.md`) solo ve Subidas y Estadísticas: menú propio (`CUENTAS_SUBIDAS` en `Sidebar.tsx`) y rutas extra en `_PREFIJOS_POR_USUARIO` de `src/api/main.py`.

### Mi menú — la sidebar, por usuario

Cada persona esconde y reordena su menú lateral desde `/settings` ("Mi menú",
`components/settings/MenuPersonalizado.tsx`). Va en Redis
(`ui:menu:<usuario>`, router transversal `src/api/routers/ui_menu.py`) y no en
`localStorage`: la misma cuenta entra desde móvil, PC y APK. Se guardan solo
CLAVES (el `href` de un item, el `basePath` de un grupo), nunca el menú entero
— la lista la manda `Sidebar.tsx` y una copia guardada se quedaría vieja al
añadir un nicho. Es COSMÉTICO: se aplica encima del menú que da el rol, que
es lo que de verdad corta (y el backend lo comprueba aparte).

**«Más» (9/11/2026).** `PRINCIPAL` en `Sidebar.tsx` fija lo que un usuario ve a
primera vista (hoy solo `ness`: Mis tandas suelta, Subidas, Estadísticas,
Costes, Claude, Accesos y Editor Auto). Lo demás se pliega en «Más» al final
del menú (sin borrar nada: el MCP y los agentes usan esas pantallas), y lo
escondido en «Mi menú» sale dentro de «Más» › «Ocultos en Mi menú». Lo de
«Más» va con `prefetch={false}`. Usuario sin entrada en `PRINCIPAL` = menú de
siempre. «Panel de mando ↗» enlaza a panel.nebulabsmedia.com (controles del VPS).

**Salud de la app (9/11/2026).** `GET /api/health/completo` (`src/api/routers/salud.py`,
con sesión) mira lo que el panel de mando no ve: los dos Redis, el Drive montado,
el disco de trabajo y la cola (workers vivos y trabajos ATASCADOS: corriendo
> `SALUD_CORRIENDO_MAX_MIN`=60 o pendientes > `SALUD_PENDIENTE_MAX_MIN`=10 sin nada
corriendo; lo programado a futuro no cuenta). Cada sonda en su hilo con tope de 4 s.
Se ve en Diagnóstico › Resumen. `GET /api/health` sigue siendo el latido de Docker.

### Escaparate y vendidos — transversales a TODOS los nichos

Dos cosas NO son de ningún nicho: se hacen una sola vez por producto porque la
cuenta de TikTok es la misma. Las dos viven en
[`src/nicho_pov_bof/repos/product_repo.py`](src/nicho_pov_bof/repos/product_repo.py)
y los demás nichos las reusan (no dupliques índices por nicho):

- **Escaparate** — `escaparate:index[:usuario]`, clave `norm(tienda)|norm(titulo)`
  (`clave_escaparate` / `escaparate_index` / `set_escaparate`). El mismo producto
  sale repetido en varias carpetas del Drive y se graba con varios nichos:
  marcado en uno, aparece marcado en todos. Sin textos extraídos la clave es
  vacía y no deduplica.
- **Vendidos** — `vendidos:index[:usuario]` + `vendido:[u:<usuario>:]<ref>`,
  un ranking por persona; **no** se clasifica por nicho (`NICHOS_VENTA` queda
  solo por compatibilidad del dato antiguo). La carpeta "Top vendidos" del
  Drive sí es común: es un catálogo, no un progreso.

Ambos son **por usuario**: Ana y Mauro son otras personas con su propia cuenta,
y una venta o un escaparate es el resultado de SU cuenta. El histórico va en la
clave sin sufijo, que es la de `ness` (mismo criterio que el progreso de
carpetas).

Cosas que ya costaron una vez:
- El documento del curso pide 260 caracteres "para 15 segundos", pero su propio
  ejemplo tiene 357 y a 18,2 car/s eso son 20s. **No se recorta**: forzarlo con
  reintentos deja el guion telegráfico. Solo se avisa.
- Los textos del producto (título, tienda, caption) se **leen** del Nicho POV
  BOF, no se re-extraen: costarían las llamadas de Gemini dos veces.
- La cadena de nivelado del POV BOF (`TP=-1.5`) NO vale para Fish: daba +0,20
  dBTP. Aquí es `TP=-2.0` con limitador 0.89.

