"""El servidor MCP y sus rutas HTTP.

- `POST /api/mcp/<token>`           → el protocolo MCP (Streamable HTTP, sin estado, JSON).
- `GET  /api/mcp/<token>/archivo`   → descarga para el agente (fotos, vídeos, bandeja).
- `POST /api/mcp/<token>/subir`     → el agente sube un fichero y recibe un `archivo_id`.
- `GET  /api/v1/agente/guias/<ruta>`→ las guías en Markdown (públicas, sin secretos).
- `GET  /api/v1/agente/mi-conexion` → la URL del MCP del usuario con sesión.

Las herramientas llaman a la propia API (`interno.py`), así que hacen lo mismo
que los botones de la web y con los mismos permisos del usuario del token.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Annotated, Any

from fastapi import APIRouter, File, Query, Request, UploadFile
from fastapi.responses import PlainTextResponse, Response
from mcp.server.mcpserver import Context, Image, MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from src.agente_mcp import archivos, config, menus, tareas
from src.agente_mcp.interno import ErrorApp, Interno

logger = logging.getLogger(__name__)

CABECERA_USUARIO = "x-agente-usuario"

INSTRUCCIONES = """\
Eres el ayudante de producción de vídeos de TikTok Shop del operador (España).
Con estas herramientas manejas su app «Tiktok Shop AI Pro»: carpetas de
productos, textos, guiones, prompts, subida de clips y montaje.

ANTES DE NADA llama a `guia` (sin argumentos) y luego a `guia(menu)` del menú
que te pidan: ahí está el proceso, las preguntas que tienes que hacer al
operador (hasta dónde llegar, dónde generar el vídeo, 8 s o 10 s…) y cómo
revisar fotos y clips para no cometer una infracción de «producto
incoherente».

Flujo típico: `carpetas` → `productos` → `preparar_carpeta` (y `estado` hasta
que acabe) → `preparar_bandeja` (deja fotos y PLAN.md en el Drive) → generas
imágenes y clips en Google Flow / GenAI Pro / Magnific con el navegador →
`ver` para revisarlos → `subir_clip` → `estado`/`productos` hasta que esté
montado → `videos_montados`.

Las imágenes y los vídeos se generan SIEMPRE en la web (Flow, GenAI Pro,
Magnific) controlando el navegador, NUNCA por API. Nunca generes nada sin
decir antes cuánto vas a lanzar y esperar el «sí». No uses `marcar` salvo que te lo pidan.
Si te piden rehacer lo marcado, `para_rehacer(menu)` lo lista todo con la nota.
Lo montado de todos los nichos, en tandas de diez para publicar, está en
`mis_tandas` (solo lectura: lo que montes aparece ahí solo, no se sube nada).
Para copiar la fórmula de un vídeo viral con un producto nuestro: `replicar_viral`;
de un carrusel de fotos: `replicar_carrusel` → fotos en Flow → `subir_imagen_carrusel`
→ `descargar_carrusel` (ZIP con el texto quemado); el producto puede darse de
alta ahí mismo con `producto_carrusel`, y los carruseles listos salen en
`mis_tandas(fotos=True)`.
Del 11 nov al 16 dic hay campañas (Black Friday, Navidad): llama a `campanas`
antes de escribir guiones o elegir productos y orienta el ángulo si toca, sin
prometer nunca ofertas que la ficha no tenga.
"""

mcp = MCPServer(name="tiktok-shop-ai-pro", instructions=INSTRUCCIONES)
_tool = mcp.tool


def _herramienta(**kw):
    """`mcp.tool` pero con los fallos inesperados convertidos en un mensaje que
    el agente pueda leer (el SDK solo le dice «Error executing tool X»)."""
    import functools
    import inspect

    def deco(fn):
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def envuelta(*a, **k):
                try:
                    return await fn(*a, **k)
                except ErrorApp:
                    raise
                except Exception as e:  # noqa: BLE001
                    logger.exception("MCP %s", fn.__name__)
                    raise ErrorApp(f"Fallo interno en {fn.__name__}: {type(e).__name__}: {e}") from e
        else:
            @functools.wraps(fn)
            def envuelta(*a, **k):
                try:
                    return fn(*a, **k)
                except ErrorApp:
                    raise
                except Exception as e:  # noqa: BLE001
                    logger.exception("MCP %s", fn.__name__)
                    raise ErrorApp(f"Fallo interno en {fn.__name__}: {type(e).__name__}: {e}") from e
        return _tool(**kw)(envuelta)

    return deco


def _usuario(ctx: Context) -> str:
    h = ctx.headers or {}
    u = h.get(CABECERA_USUARIO) or ""
    if not u:
        raise ErrorApp("Sin usuario: conéctate con la URL que da la app (/api/mcp/<token>).")
    return u


def _json(datos: Any) -> str:
    return json.dumps(datos, ensure_ascii=False, indent=1, default=str)


async def _ctx(ctx: Context, menu: str, catalogo: str, carpeta: str, modo: str = "",
               gancho: str = "", duracion: str = "") -> menus.Ctx:
    return await menus.contexto(menu, Interno(_usuario(ctx)), catalogo, carpeta,
                                modo, gancho, duracion)


# ---------------------------------------------------------------------------
# Guías y catálogo
# ---------------------------------------------------------------------------
def _leer_guia(ruta: str) -> str:
    base = config.GUIAS_DIR.resolve()
    p = (base / ruta).resolve()
    if base not in p.parents or not p.is_file():
        raise ErrorApp(f"No hay guía {ruta!r}.")
    return p.read_text(encoding="utf-8")


@_herramienta(structured_output=False)
def guia(menu: str = "") -> str:
    """Las instrucciones. Sin `menu`: reglas generales + cómo se maneja la app,
    las plataformas (Flow, GenAI Pro, Magnific) y la revisión de calidad.
    Con `menu` (ver `menus`): el paso a paso de ese menú. Léelas antes de trabajar."""
    if not menu:
        return "\n\n---\n\n".join(_leer_guia(r) for r in (
            "README.md", "comun/app.md", "comun/plataformas.md", "comun/revision-calidad.md",
            "comun/campanas.md"))
    m = menus.MENUS.get(menu)
    if not m:
        raise ErrorApp(f"Menú desconocido. Válidos: {', '.join(menus.MENUS)}.")
    return _leer_guia(f"{m.guia}.md")


@_herramienta(structured_output=False)
def menus_disponibles() -> str:
    """Los menús que cubre el MCP, con sus modos y opciones válidas."""
    return _json([
        {"menu": m.clave, "label": m.label, "que_es": m.notas, "modos": list(m.modos),
         "opciones": m.opciones, "solo_guia": m.tipo == "solo_guia"}
        for m in menus.MENUS.values()
    ])


@_herramienta(structured_output=False)
def campanas() -> str:
    """Calendario de campañas de TikTok Shop (Black Friday, Cyber Monday,
    Navidad): la campaña en curso, la próxima con los días que faltan, avisos
    de preparación y el ángulo recomendado para guiones y prompts. Míralo antes
    de escribir guiones. Regla: no prometas ofertas que la ficha no tenga."""
    from src.cuotas import campanas as cal

    e = cal.estado()
    e.pop("semanas", None)  # el agente no necesita la cuadrícula día a día
    e["contexto_guion"] = cal.contexto_guion()
    return _json(e)


@_herramienta(structured_output=False)
async def carpetas(ctx: Context, menu: str, catalogo: str = "", modo: str = "") -> str:
    """Catálogos (si no das `catalogo`) o carpetas de un catálogo con su progreso.
    Ropa: catalogo = web | muestras | tareas, y `modo` cuenta el progreso de ese modo."""
    m = menus.menu(menu)
    api = Interno(_usuario(ctx))
    if not catalogo and m.tipo != "ropa":
        return _json({"catalogos": await menus.catalogos(m, api)})
    return _json(await menus.carpetas(m, api, catalogo, modo))


@_herramienta(structured_output=False)
async def para_rehacer(ctx: Context, menu: str = "pov_bof_largo") -> str:
    """Lo que el operador ha marcado «🔁 Rehacer» en TODOS los catálogos del
    menú, con su nota (qué falló). Es de ESTE usuario (el del token) y del
    modo de guion activo de cada catálogo, lo mismo que ve él en la web.
    Empieza por aquí si te dice «rehaz lo marcado»: cada fila trae catalogo,
    carpeta y producto para `plan_producto`. En `moda_mujer_multimodo` y
    `moda_mujer` (Aleatorios: Tienda Colores, Calle Dividido…) sale de las
    tandas y trae además `modo` (el formato a repetir) y `tanda`."""
    filas = await menus.para_rehacer(menus.menu(menu), Interno(_usuario(ctx)))
    return _json(filas or {"nada": "No hay nada marcado para rehacer."})


@_herramienta(structured_output=False)
async def anadir_a_q4(ctx: Context, productos: list[str], clips: int = 3,
                      carpeta: str = "Productos Q4") -> str:
    """Copia productos a la carpeta de temporada «Productos Q4» (Black Friday /
    Navidad) del Inventario General de POV BOF Largo. Cada uno como
    "<catálogo>|<carpeta>|<producto>" (p. ej. "inventario_general|Carpeta_22|3").
    Se copian fotos y textos: el original no se toca y en la copia todo (guion,
    clips, vídeo, subido) es nuevo. `clips` fija la duración del guion (3 = 24s
    con clips de 8s). Idempotente: lo ya copiado sale en `ya_estaban`. Solo la
    cuenta de ness. `carpeta`: «Productos Q4» (por defecto), «Épico Octubre» o
    «Venta Inversa» (cualquiera de `CARPETAS_ESPECIALES`).
    Después, `preparar_carpeta(menu="pov_bof_largo",
    catalogo="inventario_general", carpeta="Productos Q4", clip_s=8, ...)`."""
    api = Interno(_usuario(ctx))
    return _json(await api.post("/api/v1/nicho-pov-bof-largo/q4/anadir",
                                {"refs": [str(p) for p in productos],
                                 "segundos_guion": 8 * max(2, int(clips or 3)),
                                 "carpeta": carpeta}))


@_herramienta(structured_output=False)
async def anadir_replica(ctx: Context, producto: str, replica_id: str) -> str:
    """«Montar en el Largo» una réplica viral (`src/replicar_viral/`): copia el
    producto "<catálogo>|<carpeta>|<producto>" a la carpeta «Réplicas virales»
    del Inventario General (modo fijo «Réplica viral», 2 clips de 8 s), le ata
    la réplica y deja escrito el guion adaptado (sin llamar a la IA). Después,
    `plan_producto(menu="pov_bof_largo", catalogo="inventario_general",
    carpeta="Réplicas virales", producto=<el que devuelve>)` da las imágenes y
    clips con los prompts de la réplica. Idempotente por producto."""
    api = Interno(_usuario(ctx))
    return _json(await api.post("/api/v1/nicho-pov-bof-largo/replica/anadir",
                                {"ref": str(producto), "replica_id": str(replica_id)}))


@_herramienta(structured_output=False)
async def productos(ctx: Context, menu: str, catalogo: str, carpeta: str, modo: str = "",
                    gancho: str = "", duracion: str = "") -> str:
    """Los productos de una carpeta con su estado: textos, guion, clips que
    necesita y ya subidos, vídeo montado, subido a TikTok, avisos.
    UGC: `gancho` (dolor|general) y `duracion` (10|8). Ropa: `modo` y `duracion`."""
    c = await _ctx(ctx, menu, catalogo, carpeta, modo, gancho, duracion)
    items = await menus.productos_crudos(c)
    return _json({"menu": c.m.clave, "catalogo": c.catalogo, "carpeta": c.carpeta,
                  "modo": c.modo, "gancho": c.gancho, "duracion": c.duracion,
                  "productos": [menus.resumen(c, p) for p in items]})


# ---------------------------------------------------------------------------
# Preparar la carpeta (textos + guiones) — en segundo plano
# ---------------------------------------------------------------------------
@_herramienta(structured_output=False)
async def preparar_carpeta(ctx: Context, menu: str, catalogo: str, carpeta: str,
                           modo: str = "", gancho: str = "", duracion: str = "",
                           clip_s: int = 0, estilo_guion: str = "",
                           rehacer: bool = False, productos: str = "") -> str:
    """El «Paso 1» de la web: lee los textos de las fichas que falten y escribe
    los guiones/escenas que falten. Devuelve un `tarea_id` para `estado`.
    POV BOF / Largo: `clip_s` (8|10) fija la duración de clip de toda la carpeta;
    Largo: `estilo_guion` (precio|dolor|epico|inversa|viral) — cambia el modo de TODO
    el catálogo; «epico» marca golpes con insertos de 5 s, «inversa» es la
    venta inversa irónica y siempre son 3 clips. `rehacer=True` REESCRIBE lo
    que ya está: solo si el operador lo pide. `productos` ("1,3,5") limita los
    guiones a esos productos (Moda y Largo; sin él, toda la carpeta)."""
    c = await _ctx(ctx, menu, catalogo, carpeta, modo, gancho, duracion)
    tid = tareas.lanzar(f"Preparar {c.m.label} · {c.carpeta}",
                        lambda: menus.preparar(c, clip_s, estilo_guion, rehacer, productos))
    return _json({"tarea_id": tid, "que": "Leyendo textos y encolando guiones. "
                  "Consulta `estado(tarea_id)`; los guiones van por la cola (varios minutos)."})


@_herramienta(structured_output=False)
async def estado(ctx: Context, id: str = "") -> str:
    """Estado de una tarea del MCP (`t_…`) o de un trabajo de la cola (job_id).
    Sin `id`: lo que el usuario tiene ahora mismo en la cola."""
    u = _usuario(ctx)
    if id.startswith("t_"):
        t = tareas.estado(id)
        return _json(t or {"error": "No existe esa tarea (¿se reinició el servidor?)."})
    api = Interno(u)
    if id:
        j = await api.get(f"/api/v1/queue/{id}")
        return _json({k: j.get(k) for k in ("job_id", "title", "status", "progress_percent",
                                            "current_step", "error", "queue_position")})
    q = await api.get("/api/v1/queue")  # ya viene filtrada: la cola de ESTE usuario
    campos = ("job_id", "title", "status", "progress_percent", "current_step", "error")
    trabajos = [{k: j.get(k) for k in campos} for j in q.get("active_jobs", [])]
    recientes = [{k: j.get(k) for k in campos} for j in q.get("recent_completed", [])]
    return _json({"en_cola": trabajos[:40], "terminados_hace_poco": recientes})


# ---------------------------------------------------------------------------
# El plan de cada producto y la bandeja
# ---------------------------------------------------------------------------
def _con_enlaces(u: str, plan: dict) -> dict:
    fotos = plan.get("fotos_producto", {})
    for k, v in list(fotos.items()):
        if isinstance(v, list):
            fotos[k] = [archivos.enlace_interno(u, x) for x in v]
        else:
            fotos[k] = archivos.enlace_interno(u, v)
    return plan


@_herramienta(structured_output=False)
async def plan_producto(ctx: Context, menu: str, catalogo: str, carpeta: str, producto: str,
                        modo: str = "", gancho: str = "", duracion: str = "") -> str:
    """Todo lo necesario para UN producto: enlaces a sus fotos, cada imagen a
    generar (prompt, qué adjuntar, dónde, formato) y cada clip (prompt, qué
    imagen, FRAME INICIAL o INGREDIENTES, segundos, si habla, plataformas
    válidas), más los avisos. Los prompts se pegan TAL CUAL. POV BOF Largo:
    una imagen POR CLIP con `dice_la_voz_en_este_clip` (elige la escena según
    ese tramo) y, en modo Épico, las imágenes/clips de cada inserto."""
    c = await _ctx(ctx, menu, catalogo, carpeta, modo, gancho, duracion)
    return _json(_con_enlaces(_usuario(ctx), await menus.plan(c, producto)))


def _plan_md(plan: dict) -> str:
    p = plan["producto"]
    lineas = [f"# {p['producto']} · {p['titulo'] or '(sin título)'}", "",
              f"- Menú: {plan['menu']} · catálogo {plan['catalogo']} · carpeta {plan['carpeta']}"
              + (f" · modo {plan['modo']}" if plan.get("modo") else ""),
              f"- Tienda: {p['tienda']} · precio: {p['precio']} · ficha: {p['ficha_tiktok'] or '—'}"]
    for a in plan.get("avisos", []):
        lineas.append(f"- ⚠️ {a}")
    if plan.get("personaje"):
        pe = plan["personaje"]
        lineas += ["", f"## Personaje → `{pe['archivo']}` ({pe['donde']}, {pe['formato']})",
                   pe.get("nota", ""), "", "```", pe.get("prompt", ""), "```"]
    for im in plan.get("imagenes", []):
        lineas += ["", f"## Imagen → `{im['archivo']}`",
                   f"{im['donde']} · {im['formato']} · adjuntar: {', '.join(im['adjuntar']) or 'nada'}"]
        if im.get("revisar"):
            lineas.append(f"Revisar: {im['revisar']}")
        lineas += ["", "```", im["prompt"], "```"]
    for cl in plan.get("clips", []):
        lineas += ["", f"## Clip {cl['clip']} → `{cl['archivo']}`",
                   f"{cl['segundos']} s · {'HABLA' if cl['habla'] else 'mudo'} · imagen: {cl['imagen']}"
                   f" como {cl['como_entra_la_imagen']} · plataformas: {', '.join(cl['plataformas'])}",
                   "", "```", cl["prompt"], "```"]
    if plan.get("montaje"):
        lineas += ["", f"_{plan['montaje']}_"]
    return "\n".join(lineas) + "\n"


async def _bajar(api: Interno, ruta: str) -> tuple[bytes, str]:
    datos, tipo, nombre = await api.get_bytes(ruta)
    return datos, nombre


@_herramienta(structured_output=False)
async def preparar_bandeja(ctx: Context, menu: str, catalogo: str, carpeta: str,
                           modo: str = "", gancho: str = "", duracion: str = "",
                           productos: list[str] | None = None) -> str:
    """Crea en el Drive (`TIKTOK_SHOP_AI_PRO/_agente/<usuario>/<menú>/<carpeta>/`)
    una subcarpeta por producto con `foto_limpia.jpg`, la ficha y `PLAN.md`
    (los prompts). Ahí mismo guarda lo que generes (`imagen_1.png`,
    `clip_1.mp4`…) y súbelo con `subir_clip(ruta_bandeja=…)`. En el PC del
    operador aparece en su Google Drive; en el VPS, en ~/gdrive."""
    u = _usuario(ctx)
    c = await _ctx(ctx, menu, catalogo, carpeta, modo, gancho, duracion)
    items = await menus.productos_crudos(c)
    if productos:
        quiero = {str(x) for x in productos}
        items = [p for p in items if str(p.get("producto")) in quiero]
    hechos = []
    for p in items:
        if p.get("sin_stock"):
            continue
        pid = str(p["producto"])
        d = archivos.dir_producto(u, c.m.clave, c.carpeta, pid, p.get("titulo", ""))
        plan = await menus.plan(c, pid)
        for nombre, clave in (("foto_limpia.jpg", "foto_limpia"), ("foto_ficha.jpg", "foto_ficha")):
            ruta = plan["fotos_producto"].get(clave)
            if ruta and not (d / nombre).exists():
                try:
                    (d / nombre).write_bytes((await _bajar(c.api, ruta))[0])
                except ErrorApp as e:
                    plan["avisos"].append(f"{nombre}: {e}")
        for k, ruta in enumerate(plan["fotos_producto"].get("fotos_color", []), 1):
            destino = d / f"foto_color_{k}.jpg"
            if not destino.exists():
                try:
                    destino.write_bytes((await _bajar(c.api, ruta))[0])
                except ErrorApp:
                    pass
        (d / "PLAN.md").write_text(_plan_md(plan), encoding="utf-8")
        hechos.append({"producto": pid, "carpeta_bandeja": archivos.relativa(u, d),
                       "imagenes": len(plan["imagenes"]), "clips": len(plan["clips"]),
                       "avisos": plan["avisos"]})
    raiz = archivos.dir_carpeta(u, c.m.clave, c.carpeta)
    return _json({"bandeja": f"Mi unidad/{config.BANDEJA_ROOT}/{u}/{archivos.relativa(u, raiz)}",
                  "productos": hechos})


@_herramienta(structured_output=False)
def listar_bandeja(ctx: Context, ruta: str = "") -> str:
    """Lista lo que hay en tu bandeja (o en una subcarpeta), con enlaces de descarga."""
    u = _usuario(ctx)
    d = archivos.ruta_en_bandeja(u, ruta)
    if not d.is_dir():
        raise ErrorApp("No es una carpeta de la bandeja.")
    out = []
    for p in sorted(d.iterdir()):
        rel = archivos.relativa(u, p)
        out.append({"ruta": rel, "carpeta": p.is_dir(),
                    **({} if p.is_dir() else {"mb": round(p.stat().st_size / 1e6, 2),
                                              "descargar": archivos.enlace_bandeja(u, rel)})})
    return _json(out)


@_herramienta(structured_output=False)
async def personaje_marca(ctx: Context) -> str:
    """Moda Mujer · Marca Personal: enlace para bajar la foto del personaje fijo
    de la cuenta (se adjunta en Flow con la prenda) y lo copia a la bandeja."""
    u = _usuario(ctx)
    api = Interno(u)
    est = await api.get("/api/v1/nicho-ropa/personaje-marca/estado")
    if not est.get("hay"):
        raise ErrorApp("El usuario no ha subido su personaje (Marca Personal › Paso 3). Pídeselo.")
    datos, _ = await _bajar(api, "/api/v1/nicho-ropa/personaje-marca?descargar=true")
    d = config.bandeja_dir(u) / "moda_mujer_marca"
    d.mkdir(parents=True, exist_ok=True)
    (d / "personaje_marca.jpg").write_bytes(datos)
    return _json({"descargar": archivos.enlace_interno(u, "/api/v1/nicho-ropa/personaje-marca?descargar=true"),
                  "en_bandeja": "moda_mujer_marca/personaje_marca.jpg"})


# ---------------------------------------------------------------------------
# Mirar: fotos del producto, imágenes generadas y fotogramas de clips
# ---------------------------------------------------------------------------
@_herramienta(structured_output=False)
async def ver_producto(ctx: Context, menu: str, catalogo: str, carpeta: str, producto: str,
                       modo: str = "") -> list[Image | str]:
    """Enseña la foto limpia y la ficha del producto: es la referencia contra la
    que se revisa cada imagen y clip generado."""
    c = await _ctx(ctx, menu, catalogo, carpeta, modo)
    p = await menus.producto(c, producto)
    pid = str(p["producto"])
    out: list[Image | str] = [f"Producto {pid} · {p.get('titulo', '')} · {p.get('tienda', '')}"]
    for var in ("limpia", "ficha"):
        ruta = menus.ruta_foto(c, pid, var)
        if not ruta:
            continue
        try:
            datos, _ = await _bajar(c.api, ruta)
            out += [f"Foto {var}:", Image(data=archivos.reducir_imagen(datos), format="jpeg")]
        except ErrorApp as e:
            out.append(f"Foto {var}: {e}")
    return out


@_herramienta(structured_output=False)
async def ver(ctx: Context, ruta_bandeja: str = "", archivo_id: str = "", url: str = "",
              fotogramas: int = 4) -> list[Image | str]:
    """Mira una imagen o un clip generado (de la bandeja, subido con /subir o
    por url). Un clip se enseña en `fotogramas` fotogramas repartidos. Úsalo
    para la revisión de calidad antes de subir nada."""
    u = _usuario(ctx)
    datos, nombre = await archivos.leer_origen(u, url=url, archivo_id=archivo_id,
                                               ruta_bandeja=ruta_bandeja)
    if archivos.es_video(nombre, datos):
        fotos, dur = archivos.fotogramas(datos, fotogramas)
        out: list[Image | str] = [f"{nombre}: vídeo de {dur:.1f} s, {len(fotos)} fotogramas"]
        return out + [Image(data=f, format="jpeg") for f in fotos]
    return [nombre, Image(data=archivos.reducir_imagen(datos), format="jpeg")]


# ---------------------------------------------------------------------------
# Subir clips, montar, recoger vídeos, marcar
# ---------------------------------------------------------------------------
@_herramienta(structured_output=False)
async def subir_clip(ctx: Context, menu: str, catalogo: str, carpeta: str, producto: str,
                     clip: int = 1, ruta_bandeja: str = "", archivo_id: str = "", url: str = "",
                     modo: str = "", gancho: str = "", duracion: str = "",
                     voz: str = "auto", flecha: bool | None = None, inserto: int = 0) -> str:
    """Sube UN clip al hueco `clip` (1, 2…) de un producto. POV BOF Largo en
    modo Épico: `inserto=N` sube el clip épico del golpe N (no un clip normal). Fuente (una):
    `ruta_bandeja` (lo guardaste en la bandeja del Drive), `archivo_id` (lo
    subiste a `<url del MCP>/subir`) o `url` pública. Al llenar el último hueco
    la app monta sola (salvo UGC: llama a `montar`). POV BOF/Largo: `voz`
    auto|hombre|mujer. Moda (multimodo): `flecha=True/False` pone o quita la
    flecha CTA de los últimos segundos (color según el vídeo); sin pasarlo,
    la del formato (el multimodo no la lleva)."""
    u = _usuario(ctx)
    c = await _ctx(ctx, menu, catalogo, carpeta, modo, gancho, duracion)
    datos, nombre = await archivos.leer_origen(u, url=url, archivo_id=archivo_id,
                                               ruta_bandeja=ruta_bandeja)
    if not archivos.es_video(nombre, datos):
        raise ErrorApp(f"{nombre!r} no parece un vídeo.")
    r = await menus.subir_clip(c, producto, int(clip), datos, nombre, voz, flecha, int(inserto or 0))
    return _json(r)


@_herramienta(structured_output=False)
async def subir_clips_de_bandeja(ctx: Context, menu: str, catalogo: str, carpeta: str,
                                 modo: str = "", gancho: str = "", duracion: str = "",
                                 productos: list[str] | None = None, voz: str = "auto",
                                 flecha: bool | None = None) -> str:
    """Sube de golpe los `clip_N.mp4` que haya en la bandeja de cada producto
    de la carpeta (los que aún no estén subidos), en orden. UGC: además monta."""
    u = _usuario(ctx)
    c = await _ctx(ctx, menu, catalogo, carpeta, modo, gancho, duracion)
    base = archivos.dir_carpeta(u, c.m.clave, c.carpeta)
    items = await menus.productos_crudos(c)
    quiero = {str(x) for x in productos} if productos else None
    informe = []
    for p in items:
        pid = str(p["producto"])
        if quiero and pid not in quiero:
            continue
        dirs = [d for d in base.glob(f"{archivos.slug(pid, 12)}_*") if d.is_dir()]
        if not dirs:
            continue
        clips = sorted(dirs[0].glob("clip_*.mp4"),
                       key=lambda x: int(re.sub(r"\D", "", x.stem) or 0))
        ya = set(menus.resumen(c, p)["clips_subidos"])
        subidos = []
        for f in clips:
            n = int(re.sub(r"\D", "", f.stem) or 0)
            if n in ya or n < 1:
                continue
            try:
                r = await menus.subir_clip(c, pid, n, f.read_bytes(), f.name, voz, flecha)
                subidos.append({"clip": n, "ok": True, "msg": r.get("message", "")})
            except ErrorApp as e:
                subidos.append({"clip": n, "ok": False, "msg": str(e)})
        if c.m.tipo == "ugc" and subidos and all(s["ok"] for s in subidos):
            try:
                await menus.montar(c, pid)
                subidos.append({"montaje": "encolado"})
            except ErrorApp as e:
                subidos.append({"montaje": str(e)})
        if subidos:
            informe.append({"producto": pid, "subidas": subidos})
    return _json(informe or {"nada": "No había clips nuevos en la bandeja."})


@_herramienta(structured_output=False)
async def montar(ctx: Context, menu: str, catalogo: str, carpeta: str, producto: str,
                 gancho: str = "", duracion: str = "") -> str:
    """UGC: monta el anuncio con los clips subidos. POV BOF: vuelve a montar con
    los clips que ya están (tras un fallo). En los demás se monta solo."""
    c = await _ctx(ctx, menu, catalogo, carpeta, "", gancho, duracion)
    return _json(await menus.montar(c, producto))


@_herramienta(structured_output=False)
async def videos_montados(ctx: Context, menu: str, catalogo: str, carpeta: str,
                          modo: str = "", gancho: str = "", duracion: str = "",
                          copiar_a_bandeja: bool = False) -> str:
    """Los vídeos ya editados de la carpeta, con enlace de descarga. Con
    `copiar_a_bandeja=True` los deja además en `<bandeja>/<carpeta>/videos/`."""
    u = _usuario(ctx)
    c = await _ctx(ctx, menu, catalogo, carpeta, modo, gancho, duracion)
    items = await menus.productos_crudos(c)
    out = []
    destino = archivos.dir_carpeta(u, c.m.clave, c.carpeta) / "videos"
    for p in items:
        if not p.get("video_path"):
            continue
        pid = str(p["producto"])
        ruta = menus.ruta_video(c, pid)
        fila = {"producto": pid, "titulo": p.get("titulo", ""),
                "descargar": archivos.enlace_interno(u, ruta),
                "ruta_drive": p.get("video_path"), "subido_a_tiktok": bool(p.get("uploaded"))}
        if copiar_a_bandeja:
            destino.mkdir(parents=True, exist_ok=True)
            datos, nombre = await _bajar(c.api, ruta)
            f = destino / (nombre or f"{pid}.mp4")
            f.write_bytes(datos)
            fila["en_bandeja"] = archivos.relativa(u, f)
        out.append(fila)
    return _json(out or {"nada": "Aún no hay vídeos montados en esta carpeta."})


@_herramienta(structured_output=False)
async def marcar(ctx: Context, menu: str, catalogo: str, carpeta: str, producto: str,
                 subido: bool | None = None, escaparate: bool | None = None,
                 vendio: bool | None = None, gancho: str = "", duracion: str = "",
                 rehacer: bool | None = None, nota_rehacer: str = "") -> str:
    """Marca «📤 Subido», «🏪 Escaparate» o «💰 Vendió» SOLO si el operador te lo
    pide: son marcas de lo que ha hecho él en su cuenta de TikTok.
    `rehacer` (POV BOF Largo): marca/quita «🔁 Rehacer» con `nota_rehacer`; se
    quita sola al montarse el vídeo nuevo."""
    c = await _ctx(ctx, menu, catalogo, carpeta, "", gancho, duracion)
    r = await menus.marcar(c, producto, subido, escaparate, vendio, rehacer, nota_rehacer)
    return _json({"ok": True, "producto": r.get("producto", producto)})


@_herramienta(structured_output=False)
async def mis_tandas(ctx: Context, todas: bool = False, fresco: bool = False,
                     fotos: bool = False) -> str:
    """«Mis tandas» del usuario del token: los vídeos YA MONTADOS de POV BOF,
    POV BOF Largo y Moda Mujer (Multimodo y Aleatorios), de diez en diez y en el orden en
    que toca publicarlos (cada tanda abierta lleva `fecha` y `temporada`).
    Es solo una vista: NO se sube nada aquí — lo que montas en su nicho aparece
    solo al final de la cola (`fresco=True` para verlo ya). Por defecto solo
    las tandas abiertas; `todas=True` trae también las ya subidas.
    Cada vídeo trae `id` (para `marcar_tanda` y `semaforo_tanda`), su nicho,
    catálogo, carpeta y producto (para ir a su menú), `descargar` y `semaforo`
    (null = sin revisar, o {color, motivo} de la revisión de ESE montaje).
    `fotos=True`: el apartado «Fotos» — los carruseles de «Replicar carrusel»
    con al menos una foto, en sus PROPIAS tandas de diez (contador aparte de
    los vídeos); cada tanda trae `zip` (todos sus carruseles; `zip_pendientes`
    si ya hay alguno subido) y cada carrusel
    su `id` (para `marcar_tanda(..., fotos=True)`) y `zip`."""
    u = _usuario(ctx)
    if fotos:
        from urllib.parse import quote

        d = await Interno(u).get("/api/v1/mis-tandas/fotos", todas="true" if todas else "false")
        for t in d.get("tandas", []):
            t["zip"] = archivos.enlace_interno(u, f"/api/v1/mis-tandas/fotos/zip?tanda={t['numero']}")
            if t.get("subidos"):
                t["zip_pendientes"] = archivos.enlace_interno(
                    u, f"/api/v1/mis-tandas/fotos/zip?tanda={t['numero']}&pendientes=true")
            for c in t.get("items", []):
                c["zip"] = archivos.enlace_interno(
                    u, f"/api/v1/replicar-viral/carrusel/{quote(c['id'], safe='')}/zip")
        return _json(d)
    params = {"todas": "true" if todas else "false", "fresco": "true" if fresco else "false"}
    d = await Interno(u).get("/api/v1/mis-tandas", **params)
    from urllib.parse import quote

    for t in d.get("tandas", []):
        for v in t.get("items", []):
            if v.get("nicho") == "mm":
                ruta = (f"/api/v1/nicho-ropa/video?producto={quote(str(v['producto']), safe='')}"
                        f"&carpeta={quote(v['carpeta'], safe='')}"
                        f"&modo={quote(v.get('formato', ''), safe='')}&descargar=true")
            else:
                ruta = f"/api/v1/mis-tandas/video?id={quote(v['id'], safe='')}&descargar=true"
            v["descargar"] = archivos.enlace_interno(u, ruta)
    return _json(d)


@_herramienta(structured_output=False)
async def marcar_tanda(ctx: Context, id: str, subido: bool | None = None,
                       sin_stock: bool | None = None, rehacer: bool | None = None,
                       nota_rehacer: str = "", quitar: bool | None = None,
                       fotos: bool = False) -> str:
    """Botones de una fila de «Mis tandas» (`id` sale de `mis_tandas`). Escribe
    en el documento del NICHO del vídeo, así que su pantalla lo ve igual.
    SOLO si el operador te lo pide: «Subido» es lo que ha publicado él;
    «sin stock» es del producto (vale para todos los usuarios y nichos);
    «rehacer» con su nota (no existe en el POV BOF corto).
    `quitar=True` saca el vídeo de la lista (ya no se va a subir; no se borra
    nada del nicho y su hueco lo ocupa el siguiente); `quitar=False` lo devuelve.
    `fotos=True`: el `id` es de un carrusel (de `mis_tandas(fotos=True)`) y
    solo vale `subido`."""
    api = Interno(_usuario(ctx))
    if fotos:
        if subido is None:
            raise ErrorApp("En un carrusel solo se marca `subido`.")
        return _json(await api.post("/api/v1/mis-tandas/fotos/estado", {"id": id, "subido": subido}))
    if quitar is not None:
        return _json(await api.post("/api/v1/mis-tandas/ocultar", {"id": id, "oculto": quitar}))
    body: dict = {"id": id}
    if subido is not None:
        body["uploaded"] = subido
    if sin_stock is not None:
        body["sin_stock"] = sin_stock
    if rehacer is not None:
        body["rehacer"] = rehacer
        body["rehacer_nota"] = nota_rehacer
    return _json(await api.post("/api/v1/mis-tandas/estado", body))


@_herramienta(structured_output=False)
async def semaforo_tanda(ctx: Context, id: str, color: str, motivo: str = "") -> str:
    """Semáforo de revisión de un vídeo de «Mis tandas» (`id` sale de `mis_tandas`),
    para que el operador sepa qué se puede subir sin riesgo de sanción:
    `verde` = producto sencillo y vídeo sin ninguna duda (el producto se ve igual
    que en la ficha en todos los clips, nombre y subtítulos correctos);
    `ambar` = está bien pero el producto es complejo (texto en el envase,
    variantes, piezas, funciones) y no compensa arriesgar; `rojo` = hay que
    rehacerlo (marca también «rehacer» con el `motivo`). `color=""` lo quita.
    Pon SIEMPRE el `motivo` (una frase). Criterios: guía `mis-tandas.md` › Semáforo.
    El color vale solo para ese montaje: si el vídeo se rehace, vuelve a «sin revisar»."""
    return _json(await Interno(_usuario(ctx)).post(
        "/api/v1/mis-tandas/semaforo", {"id": id, "color": color, "motivo": motivo, "por": "agente"}))


@_herramienta(structured_output=False)
async def replicar_viral(ctx: Context, catalogo: str, carpeta: str, producto: str,
                         url: str = "", archivo_id: str = "") -> str:
    """Copia la FÓRMULA de un vídeo viral de TikTok con un producto nuestro
    (catálogo/carpeta/producto del POV BOF). Da el enlace (`url`, lo baja la
    app) o sube el vídeo antes y pasa su `archivo_id`. Gemini ve el vídeo
    entero y devuelve: `original` (transcripción, escenas, gancho, por qué
    funciona), `apto` (si se puede hacer sin caras hablando) y `adaptacion`:
    guion de voz en off de ~16 s y, para cada uno de los DOS clips mudos de
    8 s, `prompt_imagen` (imagen inicial, con la foto del producto como
    referencia) y `prompt_video`. Tarda ~1 min; solo texto, no genera nada.
    Lee antes la guía `replicar-viral.md`."""
    api = Interno(_usuario(ctx))
    datos = {"source": catalogo, "folder": carpeta, "producto": producto, "url": url}
    if archivo_id:
        contenido, nombre = await archivos.leer_origen(_usuario(ctx), archivo_id=archivo_id)
        return _json(await api.post_form("/api/v1/replicar-viral/analizar", datos,
                                         (nombre or "viral.mp4", contenido, "video/mp4")))
    if not url:
        raise ErrorApp("Falta `url` (enlace de TikTok) o `archivo_id`.")
    r = await api._pedir("POST", "/api/v1/replicar-viral/analizar", data=datos)
    return _json(r.json())


def _enlaces_carrusel(u: str, doc: dict) -> dict:
    """Añade a cada diapositiva sus enlaces (la del viral y la ya lista) y el
    del ZIP: el agente los abre con `ver` o los baja para subirlos a Flow."""
    from urllib.parse import quote

    base = f"/api/v1/replicar-viral/carrusel/{quote(str(doc.get('id', '')), safe='')}"
    for d in doc.get("diapositivas") or []:
        n = d.get("n")
        if d.get("tiene_original"):
            d["original"] = archivos.enlace_interno(u, f"{base}/imagen/{n}?tipo=orig")
        if d.get("tiene_imagen"):
            d["descargar"] = archivos.enlace_interno(u, f"{base}/imagen/{n}?tipo=final&descargar=true")
    if doc.get("hechas"):
        doc["zip"] = archivos.enlace_interno(u, f"{base}/zip")
    return doc


@_herramienta(structured_output=False)
async def replicar_carrusel(ctx: Context, catalogo: str = "", carpeta: str = "",
                            producto: str = "", url: str = "", para: str = "",
                            replica_id: str = "") -> str:
    """Copia la FÓRMULA de un CARRUSEL de fotos viral de TikTok (`url`) con un
    producto nuestro (catálogo/carpeta/producto del POV BOF). Gemini ve todas
    las diapositivas y devuelve, por cada una: `rol` (gancho/problema/producto/
    prueba/cta), `texto_original`, `texto` (el nuestro, que la app quemará),
    `usa_foto_producto` y `prompt_imagen` (inglés, para Google Flow / Nano
    Banana, sin texto en la imagen, en el `formato` 3:4 o 9:16 del original);
    más `caption` y `hashtags`. Cada diapositiva trae `original` (enlace a la
    foto del viral). Tarda ~1 min; solo texto, NO genera imágenes: las generas
    tú en Flow y las subes con `subir_imagen_carrusel`. Guía `replicar-carrusel.md`.
    `replica_id`: vuelve a replicar ESE carrusel (mismo viral y producto,
    textos nuevos) sin pasar lo demás. `para`: otro usuario (ana, mauro…),
    solo si el token es de un admin; la réplica queda en SU lista.
    Productos que no están en ningún catálogo: dalos de alta con
    `producto_carrusel` (catálogo `carruseles_virales`, compartido)."""
    u = _usuario(ctx)
    if replica_id:
        doc = await Interno(u).post(f"/api/v1/replicar-viral/carrusel/{replica_id}/replicar",
                                    {"para": para})
        return _json(_enlaces_carrusel(doc.get("usuario") or u, doc))
    if not (catalogo and carpeta and producto and url):
        raise ErrorApp("Faltan `catalogo`, `carpeta`, `producto` y `url` (o pasa `replica_id`).")
    r = await Interno(u)._pedir("POST", "/api/v1/replicar-viral/carrusel/analizar",
                                data={"source": catalogo, "folder": carpeta,
                                      "producto": producto, "url": url, "para": para})
    doc = r.json()
    return _json(_enlaces_carrusel(doc.get("usuario") or u, doc))


@_herramienta(structured_output=False)
async def subir_imagen_carrusel(ctx: Context, id: str, n: int, archivo_id: str = "",
                                ruta_bandeja: str = "", url: str = "") -> str:
    """Sube la foto generada en Flow para la diapositiva `n` (1, 2…) del
    carrusel `id` (de `replicar_carrusel`). UNA fuente: `archivo_id` (subido a
    /subir), `ruta_bandeja` o `url`. La app le quema el texto de esa
    diapositiva (motor del nicho Carruseles). Revisa la foto ANTES de subirla
    (producto idéntico, sin texto, sin niños). Devuelve el estado del carrusel
    (`hechas`/`total`, y `zip` cuando hay alguna)."""
    u = _usuario(ctx)
    contenido, nombre = await archivos.leer_origen(u, url=url, archivo_id=archivo_id,
                                                   ruta_bandeja=ruta_bandeja)
    if archivos.es_video(nombre, contenido):
        raise ErrorApp("Eso es un vídeo: aquí va la FOTO de la diapositiva.")
    r = await Interno(u)._pedir(
        "POST", f"/api/v1/replicar-viral/carrusel/{id}/imagen/{int(n)}",
        files={"file": (nombre or f"{int(n):02d}.jpg", contenido, "image/jpeg")})
    return _json(_enlaces_carrusel(u, r.json()))


@_herramienta(structured_output=False)
async def descargar_carrusel(ctx: Context, id: str = "", texto_n: int = 0,
                             texto: str | None = None) -> str:
    """Un carrusel replicado: diapositivas con su texto, si ya tienen foto,
    `hechas`/`total`, y `zip` = enlace para bajar TODAS de golpe (con su texto
    quemado) + caption.txt. Sin `id`: la lista de carruseles replicados.
    Para corregir el texto de una diapositiva (se vuelve a quemar):
    `texto_n` + `texto`. Solo si el operador lo pide o el texto incumple las
    reglas (promesas, cupones afirmados)."""
    u = _usuario(ctx)
    api = Interno(u)
    if not id:
        return _json(await api.get("/api/v1/replicar-viral", tipo="carrusel"))
    if texto_n and texto is not None:
        doc = await api.post(f"/api/v1/replicar-viral/carrusel/{id}/texto/{int(texto_n)}",
                             {"texto": texto})
    else:
        doc = await api.get(f"/api/v1/replicar-viral/carrusel/{id}")
    return _json(_enlaces_carrusel(u, doc))


async def _foto_de(u: str, valor: str, que: str) -> tuple[bytes, str]:
    """`valor` es una url http(s), un `archivo_id` de /subir o una ruta de la bandeja."""
    import re

    if not valor:
        raise ErrorApp(f"Falta {que}.")
    if valor.startswith(("http://", "https://")):
        return await archivos.leer_origen(u, url=valor)
    if re.fullmatch(r"[a-f0-9]{16}(\.[a-z0-9]+)?", valor):
        return await archivos.leer_origen(u, archivo_id=valor)
    return await archivos.leer_origen(u, ruta_bandeja=valor)


@_herramienta(structured_output=False)
async def producto_carrusel(ctx: Context, product_url: str = "", foto_limpia: str = "",
                            foto_ficha: str = "", carrusel_url: str = "",
                            releer_carpeta: str = "", releer_producto: str = "") -> str:
    """Catálogo COMPARTIDO «🖼️ Carruseles virales» (`carruseles_virales`) de
    «Replicar carrusel». Sin argumentos: lo lista (folder, producto, titulo,
    product_url, carrusel_url = el viral con el que se replicó; con eso se
    llama a `replicar_carrusel`).
    Alta: `foto_limpia` (el producto solo, fondo limpio) + `foto_ficha`
    (captura de la ficha de TikTok Shop con título y precio) — cada una es una
    url http(s), un `archivo_id` de /subir o una ruta de tu bandeja — +
    `product_url` (ficha de TikTok Shop) y, si lo tienes, `carrusel_url` (el
    carrusel viral). La app lee los textos de la ficha (una llamada de IA) y
    guarda la URL; devuelve `aviso` si la lectura falló: reintenta con
    `releer_carpeta` + `releer_producto`. Busca antes con `buscar` que el
    producto no exista ya en otro catálogo."""
    u = _usuario(ctx)
    api = Interno(u)
    if releer_carpeta and releer_producto:
        return _json(await api.post("/api/v1/replicar-viral/carrusel/producto/textos",
                                    {"folder": releer_carpeta, "producto": releer_producto}))
    if not (product_url or foto_limpia or foto_ficha):
        return _json(await api.get("/api/v1/replicar-viral/carrusel/catalogo"))
    if not product_url:
        raise ErrorApp("Falta `product_url` (la ficha del producto en TikTok Shop).")
    limpia, n_limpia = await _foto_de(u, foto_limpia, "`foto_limpia`")
    ficha, n_ficha = await _foto_de(u, foto_ficha, "`foto_ficha`")
    for contenido, nombre in ((limpia, n_limpia), (ficha, n_ficha)):
        if archivos.es_video(nombre, contenido):
            raise ErrorApp("Eso es un vídeo: aquí van FOTOS.")
    r = await api._pedir(
        "POST", "/api/v1/replicar-viral/carrusel/producto",
        data={"product_url": product_url, "carrusel_url": carrusel_url},
        files={"foto_limpia": (n_limpia or "limpia.jpg", limpia, "image/jpeg"),
               "foto_ficha": (n_ficha or "ficha.jpg", ficha, "image/jpeg")})
    return _json(r.json())


@_herramienta(structured_output=False)
async def marcar_carpeta(ctx: Context, menu: str, catalogo: str, carpeta: str,
                         completada: bool | None = None,
                         pendiente: bool | None = None, modo: str = "") -> str:
    """Botones de la carpeta: «Completada» y «📤 Pendiente» (vídeos hechos, falta
    subirlos). Cuando termines los vídeos de una carpeta, márcala `pendiente=True`
    para que el operador sepa que tiene que subirlos. «Completada» solo si te lo
    pide. POV BOF, POV BOF Largo (del modo de guion activo) y Ropa (por `modo`)."""
    c = await _ctx(ctx, menu, catalogo, carpeta, modo)
    return _json({"ok": True, **(await menus.marcar_carpeta(c, completada, pendiente))})


@_herramienta(structured_output=False)
async def borrar_productos(ctx: Context, catalogo: str, carpeta: str,
                           productos: list[str] | None = None,
                           confirmar: bool = False) -> str:
    """BORRA productos de los catálogos PROPIOS del operador —«Muestras productos»
    (mis_productos) o «Tareas Productos» (tareas_productos)—: sus fotos y todo lo
    guardado (textos, guion, clips, vídeo, subido). Sin `productos` vacía la
    carpeta entera y la quita. No se deshace: solo si el operador lo ha pedido,
    y con `confirmar=True`. Los catálogos del curso no se pueden borrar."""
    if not confirmar:
        raise ErrorApp("Borrar no se deshace. Repite con confirmar=True si el operador lo ha pedido.")
    c = await _ctx(ctx, "pov_bof", catalogo, carpeta)
    return _json({"ok": True, **(await menus.borrar_productos(c, productos))})


# ---------------------------------------------------------------------------
# ASGI: /api/mcp/<token> → el protocolo, con el usuario en una cabecera
# ---------------------------------------------------------------------------
def _crear_app_mcp():
    return mcp.streamable_http_app(
        streamable_http_path="/",
        json_response=True,
        stateless_http=True,
        # Detrás de Caddy y con el token en la URL, la protección de DNS
        # rebinding (pensada para servidores en localhost) solo rechazaría el
        # Host público.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )


_app_mcp = None


def sesiones():
    """Arranca el gestor de sesiones; va en el lifespan de FastAPI.

    Se crea uno NUEVO en cada arranque: el gestor solo se puede arrancar una
    vez, y los tests levantan la app varias veces en el mismo proceso."""
    global _app_mcp
    _app_mcp = _crear_app_mcp()
    return mcp.session_manager.run()


class MiddlewareMCP:
    """Intercepta `/api/mcp/<token>` (exacto) y lo pasa al servidor MCP con el
    usuario del token en una cabecera; el resto sigue su camino."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            if scope.get("app") is not None:
                from src.agente_mcp import interno

                interno.APP_ACTUAL = scope["app"]
            ruta: str = scope.get("path", "")
            if ruta.startswith("/api/mcp/"):
                trozos = ruta[len("/api/mcp/"):].strip("/").split("/")
                if len(trozos) == 1 and trozos[0]:
                    usuario = config.usuario_de_token(trozos[0])
                    if not usuario:
                        return await Response("Token no válido", status_code=401)(scope, receive, send)
                    headers = [(k, v) for k, v in scope.get("headers", [])
                               if k.lower() != CABECERA_USUARIO.encode()]
                    headers.append((CABECERA_USUARIO.encode(), usuario.encode()))
                    if _app_mcp is None:
                        return await Response("MCP no arrancado", status_code=503)(scope, receive, send)
                    nuevo = dict(scope, path="/", raw_path=b"/", root_path="", headers=headers)
                    return await _app_mcp(nuevo, receive, send)
        return await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# Rutas HTTP normales
# ---------------------------------------------------------------------------
router = APIRouter(tags=["agente-mcp"])


def _usuario_token(token: str) -> str:
    u = config.usuario_de_token(token)
    if not u:
        raise ErrorApp("Token no válido")
    return u


@router.get("/api/mcp/{token}/archivo")
async def archivo(token: str, r: Annotated[str, Query()] = "",
                  b: Annotated[str, Query()] = "") -> Response:
    """Descarga para el agente: `r` = GET interno de la API, `b` = fichero de la bandeja."""
    u = config.usuario_de_token(token)
    if not u:
        return Response("Token no válido", status_code=401)
    try:
        if b:
            p = archivos.ruta_en_bandeja(u, b)
            if not p.is_file():
                return Response("No existe", status_code=404)
            datos, tipo, nombre = p.read_bytes(), "", p.name
        elif r.startswith("/api/v1/"):
            datos, tipo, nombre = await Interno(u).get_bytes(r)
        else:
            return Response("Ruta no permitida", status_code=400)
    except ErrorApp as e:
        return Response(str(e), status_code=404)
    import mimetypes

    tipo = tipo or mimetypes.guess_type(nombre)[0] or "application/octet-stream"
    return Response(datos, media_type=tipo, headers={
        "Content-Disposition": f'attachment; filename="{nombre or "archivo"}"',
        "Cache-Control": "no-store"})


@router.post("/api/mcp/{token}/subir")
async def subir(token: str, file: Annotated[UploadFile, File()]) -> dict:
    """El agente sube aquí un fichero (curl -F file=@clip.mp4 <url>/subir) y
    recibe el `archivo_id` que se pasa a `subir_clip` o a `ver`."""
    u = config.usuario_de_token(token)
    if not u:
        return Response("Token no válido", status_code=401)  # type: ignore[return-value]
    datos = await file.read()
    if not datos:
        return {"error": "Fichero vacío"}
    if len(datos) > config.MAX_FICHERO_MB * 1024 * 1024:
        return {"error": f"Pasa de {config.MAX_FICHERO_MB} MB"}
    return {"archivo_id": archivos.guardar_subida(u, datos, file.filename or "")}


@router.get("/api/v1/agente/guias/{ruta:path}")
def ver_guia(ruta: str) -> PlainTextResponse:
    """Las guías, en Markdown tal cual (públicas: no llevan nada secreto)."""
    try:
        texto = _leer_guia(ruta or "README.md")
    except ErrorApp as e:
        return PlainTextResponse(str(e), status_code=404)
    return PlainTextResponse(texto, media_type="text/markdown; charset=utf-8")


@router.get("/api/v1/agente/mi-conexion")
def mi_conexion(request: Request) -> dict:
    """La URL del MCP de quien tiene la sesión abierta, para pegarla en Claude
    o en ChatGPT. Es personal: con ella se trabaja como ese usuario."""
    from src.api.session import usuario_de_request

    u = usuario_de_request(request) or ""
    if not u:
        return {"error": "Entra en la app primero."}
    from src.api import users

    datos = {"usuario": u, "url": config.url_mcp(u),
             "subir": f"{config.url_mcp(u)}/subir",
             "guias": f"{config.base_publica()}/api/v1/agente/guias/README.md"}
    # El admin reparte las conexiones: los demás no pueden entrar en Settings,
    # y el conector de cada cuenta lo monta él en su PC.
    if users.es_admin(u):
        datos["todos"] = [
            {"usuario": x["username"], "nombre": x["nombre"], "url": config.url_mcp(x["username"])}
            for x in users.listar()
        ]
    return datos

