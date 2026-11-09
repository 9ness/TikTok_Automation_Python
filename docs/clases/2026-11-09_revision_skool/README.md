# Revisión Skool · 9/11/2026

Esta revisión se hizo solo leyendo desde el Chrome del agente (9222).
Se miraron las dos comunidades de la cuenta:
- **TikTok Shop AI Pro**, de Jonny: feed, Llamadas Semanales y Classroom.
- **TikTok Shop Formula**, de Alex Mirapeix: gratis, 1,5k miembros.

Las transcripciones de las clases (CC de Mux) se quedan en el VPS y no van a git.
La próxima revisión semanal solo mira lo nuevo: `~/rutinas/skool-semanal.md` (en el VPS).

## 1. Qué hay de nuevo

### TikTok Shop AI Pro (Jonny)
| Fecha | Qué | Importancia |
|---|---|---|
| **9/11** | **Aviso OmniFlash.** El método de 18 meses ya no funciona y el módulo está oculto. Omni queda DESCARTADO para contenido IA de TikTok Shop. Usar **Seedance 2.0 Fast en CapCut**. | 🔴 Alta |
| **7/11** (fijado) | **Pautas para reducir sanciones.** En la fase piloto, contenido real sin IA. Con IA, **máx. 8 vídeos al día**, programados y con **≥1 h entre ellos**, subiendo poco a poco. La consistencia del producto manda (Genjutsu o Seedance mejor que Omni). Revisar el vídeo entero: forma, color, proporciones y funciones. | 🔴 Alta |
| 5/11 | Los **carruseles de su app pasan a ser de pago** (Compra → Carruseles, ~15 € por 100 imágenes ≈ 50 carruseles). Dicen que van más de 2.500 carruseles en mes y medio. | 🟡 Media |
| 16/10 | **Nueva estrategia de cuentas piloto.** 3 vídeos REALES al día durante todo el mes piloto (KitKat, Coca-Cola…), guion de la app, voz propia o de Fish y edición en CapCut. | 🟡 Media |
| 24/10 | Curso 2 «Productos e Ideas» con 3 módulos nuevos: **GMV Max** (36 min), **Social1** y **Kalo Data + IAS 20 €** (detalle en §3). | 🟡 Media |
| — | Hay una app instalable en el móvil (PWA). | ⚪ Baja |
| 11/11 | Próxima llamada de grupo: miércoles 11/11. | — |

**Lo útil que comparten los alumnos:**
- Una sanción por «contenido no original» se **aprobó en apelación** aportando una foto de la creación del vídeo.
- Hay un texto de apelación para «AIGC de baja calidad». Si hace falta, añadirlo a [`APELACIONES.md`](../../../APELACIONES.md).
- **Creatina Nina Torres:** 15 % de comisión, 29,99 €, con una carpeta de 300 vídeos de referencia de EE. UU. Producto `1729855550660975480`.
- A un usuario en fase piloto solo le dejaron subir 2 vídeos un día.

**Grabación de la llamada:**
- La última publicada es la del **28/10**, en Fathom. **No se pudo ver**: pide iniciar sesión con correo y pedir acceso.
- Néstor ya pidió acceso el 29/10 y sigue pendiente. Queda como tarea manual en el panel.
- **No hay grabación del 4/11.**

### TikTok Shop Formula (gratis)
Es un curso de iniciación. Muchas clases están **cerradas por nivel**: «Producto ganador» se abre en el nivel 2 y «¿Copiar vídeos?» en el nivel 4, y los niveles se suben con «me gusta» en la comunidad. Otras clases son páginas vacías (Hooks, Muestras, Validar productos, Herramientas, Carruseles…). Lo aprovechable:
- **Fórmula de vídeo ganador (21 min):**
  - hook visual + auditivo + **de texto** («el más infravalorado»);
  - problema → producto como solución;
  - CTA natural con urgencia (tiempo, unidades u oferta).
  - Roadmap para analizar cada vídeo: duración del hook, caídas de retención y conversión. «Parece anuncio» frente a «contenido real».
- **Piloto:** 3 vídeos al día. Darse de alta siempre como *creador*, nunca como vendedor.
- **Analizador de cuenta** gratis (`tsf-pruebalo.vercel.app/analisis`). Nota de 0 a 100 con 6 pilares: cuenta 35, productos 25, vistas 15, constancia 10, bio 10 y formato 5. Lee solo datos públicos.
- **Calculadora de ingresos** y 7 entrevistas a alumnos (YouTube).

## 2. Lo nuestro que queda desfasado

| Qué dicen ahora | Qué tenemos | Dónde cambiarlo |
|---|---|---|
| Omni descartado para TikTok Shop; usar Seedance 2.0 Fast (CapCut) o Genjutsu | Omni (GenAI Pro) es el motor por defecto de los clips de 10 s y de los hablados con marca | Memorias `clips-10s-omni-genaipro` y `pov-veo-no-omni`; guías `src/agente_mcp/guias/` (`replicar-virales.md`, `moda-mujer-multimodo.md`, `ropa-hombre.md`, `pov-bof-largo-recetas.md`, `ugc.md`, `mis-tandas.md`, `README.md`) |
| Con IA, máx. 8 al día con ≥1 h de separación y subiendo poco a poco | Nuevas: máx. 6-10 al día; ness ~20 al día; Ana 6 al día; las subidas de la cuenta árabe sin programar | Memorias `ritmo-publicacion-cuentas` y `cuenta-arabe-subir-sin-programar`; rutinas de subida en `~/rutinas/` |
| En la fase piloto, solo contenido real sin IA (3 al día) | Casca Chollos / cuenta piloto con personaje IA (cascanueces) | Memoria `cuenta-piloto-personaje-enmascarado`; `docs/contexto/ai-pro-general-carruseles-piloto.md` |
| Carruseles de la app de pago (créditos) | Damos por hecho que el importador de su web es gratis | `WEB_CURSO.md` y `TTSHOP_AI_PRO_WEB.md` (apartado de Compras/Carruseles) |
| Revisar el vídeo ENTERO (forma, color, proporciones y funciones) | Ya lo hacemos con el semáforo y la revisión a 2 fps | Sin cambios. Se confirma `giros-producto-revision-2fps` |

## 3. Ideas aplicables (ordenadas por dinero ÷ esfuerzo)

| # | Idea | Dinero | Esfuerzo | Chat |
|---|---|---|---|---|
| 1 | **Pasar los clips de TikTok Shop de Omni a Seedance 2.0 Fast (CapCut) o Genjutsu.** Probar 2-3 productos, comparar consistencia y créditos, y actualizar las guías y memorias de la §2. Las sanciones de producto incoherente cuestan más que los créditos. | Alto | Medio | Agente Jefe TikTok (prueba) → Admin (decide) → Codex (guías) |
| 2 | **Tope de 8 vídeos IA al día por cuenta, programados con ≥1 h de separación.** Aplicarlo en las rutinas de subida y en `plan_produccion`. | Alto (menos sanciones) | Bajo | Admin + rutinas de subida |
| 3 | **Filtro de producto de GMV Max:** 7 días, crecimiento ≥100 %, comisión ≥10 % (ideal 20 %), ingresos por vídeo, ≤200 creadores, «Ads» en la 3.ª página ≈80 % y CTR a carrito 7-10 %. Llevarlo a las guías (`prioridades`) y, después, al filtro del Radar EchoTik. | Alto | Bajo (guía) / Medio (Radar) | Codex (guía y Radar) |
| 4 | **Apelaciones:** sumar a `APELACIONES.md` el caso aprobado con foto de la creación y el texto de «AIGC de baja calidad». | Medio | Bajo | Codex |
| 5 | **Roadmap de análisis** por vídeo (hook, caídas de retención y conversión) en la revisión semanal de estadísticas. Hook de texto siempre presente. | Medio | Bajo | Agente de estadísticas |
| 6 | **Creatina Nina Torres** (15 %, 300 vídeos de referencia): valorar si encaja en alguna cuenta. | Medio | Bajo | Agente Jefe TikTok |
| 7 | **Social1:** barrido mensual de «Ideas para replicar» (perfiles con virales IA sencillos) y comprobar con VPN UK/US si el vídeo tiene carrito o está baneado. | Medio | Bajo-medio | Agente de virales |
| 8 | **Analizador de cuenta** gratis de Formula: pasarlo una vez por semana a cada cuenta como señal externa. Solo datos públicos. | Bajo | Mínimo | Rutina semanal |

Descartado: Kalo + IAS (StealthPack por DICloak a 20 $), porque son cuentas compartidas de dudosa legalidad, y las sesiones 1:1 de pago (49 $).
