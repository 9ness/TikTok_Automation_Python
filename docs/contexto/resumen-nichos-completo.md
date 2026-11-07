# Tabla completa de programas y nichos (versión larga)

> Movido literal desde CLAUDE.md (nov 2026). CLAUDE.md lleva la tabla acortada; aquí están las celdas completas de cada fila (Mis tandas, Replicar viral/carrusel, Multimodo, UGC...).

## Resumen del proyecto

`TikTok_Automation_Python` — fábrica Streamlit que genera vídeos virales 9:16
para TikTok. **4 programas principales** seleccionables en la sidebar (Creator
Reward / TikTok Shop / Editor Auto / Tiktok Shop AI Pro), cada uno con sus
nichos.

### Programa 1 — Creator Reward (existente)

| Nicho | Modo | Propósito |
|---|---|---|
| 🏛️ Presidentes Top 5 | `PRESIDENTS_TOP5` | Rankings de presidentes USA con guion IA + assets locales |
| 📊 Pronósticos Diarios | `PRONOSTICOS_DIARIOS` | Vídeos de pronósticos deportivos desde Redis (bet-ai-master) |
| 🛡️ Quitar Copy | `COPYRIGHT_CLEANER` | Re-subtitula vídeos para evadir copyright |
| 🏗️ Construcción POV | `CONSTRUCCION_POV` | Vídeo input → guion Gemini 1ª persona → voz MiniMax EN + anti-copy + subs |
| 🔧 Herramientas · Voces | (sin modo) | Hub global voces MiniMax: presets ES/EN + clonado reutilizable entre modos |

### Programa 2 — TikTok Shop (en construcción)

| Función | Modo | Propósito |
|---|---|---|
| 🛒 Generador Shop | `TIKTOK_SHOP` | Vídeos affiliate AI con Seedance/Veo3, multi-cuenta, multi-producto |

### Programa 3 — Editor Auto

| Función | Modo | Propósito |
|---|---|---|
| ✂️ Editor Auto | `EDITOR_AUTO` | Edita vídeo input con flujo configurable de herramientas componibles por usuario (subs, cortador silencios + IA, ...) |

### Programa 4 — Tiktok Shop AI Pro

| Función | Modo | Propósito |
|---|---|---|
| 📦 Mis tandas | (sin modo — no edita vídeo) | PRIMERO del menú para los tres: lo ya montado en POV BOF, POV BOF Largo y Multimodo del usuario, de 10 en 10 con fecha y época. Solo lee; subido/sin stock/rehacer escriben en el nicho de cada vídeo (`src/mis_tandas/`, guía `mis-tandas.md`). Semáforo 🟢🟡🔴 de revisión antes de subir por vídeo y montaje (`mis_tandas:semaforo:<usuario>`, MCP `semaforo_tanda`; rojo marca rehacer). Época por vídeo (`mis_tandas:epoca:<usuario>`, MCP `epoca_video`) y cuentas `SOLO_HABLADOS` (Ana): tandas de 6 hablados y mudos aparte en «Solo Meta». Filtro 🎯 por tarea de Campañas de creadores (N vídeos de productos concretos antes de una fecha; casa por ID de producto; `mis_tandas:tareas:<usuario>`, `src/mis_tandas/tareas.py`, MCP `guardar_tarea`/`tareas_tiktok`) |
| 🔁 Replicar viral | (sin modo — solo texto) | Enlace de TikTok (lo baja tikwm) + producto del catálogo POV → Gemini ve el vídeo y devuelve guion de voz en off + prompts de 2 clips mudos de 8 s (`src/replicar_viral/`, MCP `replicar_viral`, guía `replicar-viral.md`). Se monta con el estilo `viral` del Largo (carpeta «Réplicas virales») |
| 🎞️ Replicar virales | (sin modo — no edita vídeo) | MP4 de un viral replicado y YA MONTADO por el agente, `con_ia` (Omni) o `sin_ia` (real), con título y enlace de TikTok Shop → sale solo en Mis tandas (`rv|<id>`) con semáforo (`src/replicar_viral/video.py`, mismo Redis `replicar_viral:` con `tipo="video"` e índice propio `replicar_viral:videos:<usuario>`, MP4 en `Nebulabs/TikTok/TikTok Shop/Replicar_Viral/<usuario>/`, MCP `registrar_replica_video`/`listar_replicas_video`, guía `replicar-virales.md`) |
| 🖼️ Replicar carrusel | (sin modo — solo texto) | Enlace de un carrusel de FOTOS (tikwm `images`) + producto POV → Gemini devuelve por diapositiva rol, texto adaptado y prompt de Flow; las fotos se generan a mano, se suben y se les quema el texto con el motor de Carruseles → ZIP (`src/replicar_viral/carrusel.py`, mismo Redis `replicar_viral:` con `tipo="carrusel"`, fotos en `Nebulabs/TikTok/TikTok Shop/Replicar_Carrusel/`, MCP `replicar_carrusel`/`subir_imagen_carrusel`/`descargar_carrusel`, guía `replicar-carrusel.md`). `pais` (10 de TikTok Shop Europa, `carrusel.PAISES`): virales de otros países en su idioma, con bandera. Sale también en Mis tandas |
| 🚀 Viralización 1K | `VIRALIZACION_BATCH` | Vídeos POV/reacción en lote (gancho + paisajes) por ponente, sin repetir recursos, para llegar a 1000 seguidores |
| 🎙️ POV BOF Largo | `NICHO_POV_BOF_LARGO_VIDEO` | Como POV BOF pero la voz es un guion escrito por IA para ESE producto y locutado con Fish; el guion se escribe para ~16s (284 car), que es lo que dan DOS clips de 8s sin tener que rebobinar |
| 🧪 Cuenta Piloto | `CUENTA_PILOTO_VIDEO` | Productos que crea el operador SUBIENDO las dos fotos (no de Drive), por usuario y con VARIOS vídeos por producto; vídeo orgánico + edición del POV BOF |
| 🎛️ Moda Mujer · Multimodo | (modos `mm_*` de Ropa) | Formatos MUDOS de 10s (espejo solo música, camisetas, zapatillas, marca, Vintage botas/bolsos) + dos de zapatillas de 20s (`mm_zapatillas_pov20`/`_sentado20`: dos clips mudos + guion de dolor locutado con Fish y montado con el editor del POV BOF Largo, `lleva_fish`) + seis HABLADOS de ropa (`mm_habla_*`: espejo, selfie, situación real 1/2, calle dividido, tienda colores; la chica de la cuenta habla en el clip, Omni 1.1 de GenAI Pro, prioritarios para ropa) elegidos producto a producto por un agente; catálogos ropa + zapatos + accesorios (`mujer_zapatos_web`/`mujer_accesorios_web`); vista «multimodo» y tandas de 10 (`/multimodo/tandas`) |
| 🎯 Nicho POV BOF | (sin modo — fase 1) | Navega el Drive COMPARTIDO "Productos España" y lleva el progreso de qué carpeta de producto ya está hecha |
| 🎨 Creativos Pro | (sin modo — no edita vídeo) | Módulo 13: un creativo publicitario por producto. Mismo catálogo que POV BOF (fuentes, fotos, textos, hashtags, escaparate, vendidos); solo cambia el prompt y el formato 3:4 |
| 🖼️ Carruseles | (sin modo — no edita vídeo) | Módulo 14: carrusel de DOS fotos (chica sorprendida + producto) con el texto quemado. Solo productos donde la chica pueda estar EN el sitio |
| 💬 Plantillas mensajes | (sin modo — no edita vídeo) | Mensajes para el vendedor (muestra gratuita, colaboración) listos para copiar. Editables y guardados POR USUARIO (`src/plantillas/`, prefijo `plantillas:`) |
| 🧢 Nicho Gorras | (sin modo — no edita vídeo) | Módulo 11: solo listar gorras + textos + prompts; el vídeo se publica tal cual |
| 🌐 Nicho General · UGC | `NICHO_GENERAL_ESCENAS` · `NICHO_GENERAL_VIDEO` | Módulo 9, formato "UGC Desde 0" (sep 2026): anuncio de TRES clips de 8 o 10s generados por separado y pegados (más, hasta 8, si la tienda pide una duración mínima). Dos ganchos (dolor / general) y dos duraciones, y cada combinación es un anuncio distinto |
| 🎬 Nicho BOF Cinematográfico | `NICHO_BOF_CINE_VIDEO` | Módulo 10: como POV BOF pero sin mano — DOS clips de 5s con paneo, pegados y cuadrados por velocidad |
| 👗 Nicho Ropa Con Personas | `NICHO_ROPA_PERSONAS_VIDEO` | Módulo 7: SOLO ropa de mujer, puesta por una modelo creada con IA (ficha JSON por usuario) |
| 👕 Nicho Ropa Sin Personas | `NICHO_ROPA_VIDEO` | Módulo 8 del curso: prendas de una carpeta de Drive compartida POR ENLACE → textos/caption → prompts (vídeo con y sin manos) → montaje 9:16 SIN texto quemado y MUDO |

Punto de entrada: [`main.py`](main.py). Lanza con `streamlit run main.py`.
