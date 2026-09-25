"""Un adaptador por menú: traduce "carpeta / producto / clip" a los endpoints
de cada nicho, que no se llaman igual ni esperan lo mismo.

Todo lo que devuelve va NORMALIZADO para que el agente no tenga que saber que
en el POV BOF la carpeta es `folder` y en Ropa un slug `mujer_web__Carpeta 24`.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from src.agente_mcp.interno import ErrorApp, Interno

POV = "/api/v1/nicho-pov-bof"
LARGO = "/api/v1/nicho-pov-bof-largo"
ROPA = "/api/v1/nicho-ropa"
UGC = "/api/v1/nicho-general"
CREATIVOS = "/api/v1/nicho-creativos"

FLOW = "Google Flow"
GENAIPRO = "GenAI Pro"
MAGNIFIC = "Magnific"


@dataclass(frozen=True)
class Menu:
    clave: str
    label: str
    guia: str
    tipo: str  # pov | largo | ropa | ugc | creativos | solo_guia
    sexo: str = ""
    modalidad: str = ""
    modos: tuple[str, ...] = ()
    notas: str = ""
    opciones: dict[str, Any] = field(default_factory=dict)


MENUS: dict[str, Menu] = {
    m.clave: m
    for m in [
        Menu(
            "pov_bof_largo", "POV BOF Largo", "pov-bof-largo", "largo",
            opciones={"estilo_guion": ["precio", "dolor"], "clip_s": [8, 10]},
            notas="Mano POV señalando el producto; 2-5 clips mudos de la MISMA imagen; la voz la pone la app.",
        ),
        Menu(
            "pov_bof", "Nicho POV BOF", "pov-bof", "pov",
            opciones={"clip_s": [8, 10]},
            notas="Como el Largo pero ~10 s: 1 clip de 10 s o 2 de 8 s (lo dice cada producto).",
        ),
        Menu(
            "moda_mujer", "Moda Mujer · Aleatorios", "moda-mujer-aleatorios", "ropa",
            sexo="mujer", modalidad="aleatorios",
            modos=("espejo", "camara", "calle_1", "calle_2", "calle_dividido", "tienda_colores"),
            opciones={"duracion": ["10", "8"]},
            notas="Chica distinta cada vez; el clip HABLA (solo Google Flow).",
        ),
        Menu(
            "moda_mujer_marca", "Moda Mujer · Marca Personal", "moda-mujer-marca", "ropa",
            sexo="mujer", modalidad="marca",
            modos=("marca_espejo", "marca_zapatos", "marca_pov"),
            notas="Personaje FIJO de la cuenta (descárgalo con `personaje_marca`); clips mudos.",
        ),
        Menu(
            "ropa_hombre", "Ropa Hombre", "ropa-hombre", "ropa",
            sexo="hombre", modalidad="aleatorios",
            modos=("espejo", "camara", "calle_1", "calle_2", "gafas_coche", "sarcastica", "maniqui"),
            opciones={"duracion": ["10", "8"]},
            notas="Chico distinto cada vez. Las carpetas mezclan categorías: elige productos que encajen con el modo.",
        ),
        Menu(
            "ugc", "Nicho General · UGC", "ugc", "ugc",
            opciones={"gancho": ["dolor", "general"], "duracion": ["10", "8"]},
            notas="Anuncio de 3 clips hablados con un personaje; todo en Google Flow.",
        ),
        Menu(
            "creativos", "Creativos Pro", "creativos-pro", "creativos",
            notas="Una imagen 3:4 por producto, sin vídeo; no se sube a la app.",
        ),
        Menu(
            "carruseles", "Carruseles", "carruseles", "solo_guia",
            notas="Solo guía por ahora: el MCP no cubre sus tandas. Hazlo desde la web.",
        ),
    ]
}

CATALOGOS_ROPA = ("web", "muestras", "tareas")


def menu(clave: str) -> Menu:
    m = MENUS.get((clave or "").strip())
    if not m:
        raise ErrorApp(f"Menú desconocido {clave!r}. Válidos: {', '.join(MENUS)}.")
    if m.tipo == "solo_guia":
        raise ErrorApp(f"{m.label}: {m.notas}")
    return m


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _elegir(nombre: str, opciones: list[str], que: str) -> str:
    """Casa lo que escribe el agente («carpeta 24», «Carpeta_24») con el nombre
    exacto. Exacto → normalizado → por número si solo hay uno con ese número."""
    if nombre in opciones:
        return nombre
    n = _norm(nombre)
    for o in opciones:
        if _norm(o) == n or _norm(o).endswith(" " + n) or _norm(o.split("__")[-1]) == n:
            return o
    parecidos = [o for o in opciones if n and n in _norm(o)]
    if len(parecidos) == 1:
        return parecidos[0]
    nums = re.findall(r"\d+", nombre or "")
    if nums:
        cand = [o for o in opciones if re.findall(r"\d+", o.split("__")[-1])[-1:] == nums[-1:]]
        if len(cand) == 1:
            return cand[0]
    raise ErrorApp(
        f"No encuentro {que} {nombre!r}. Opciones: " + ", ".join(opciones[:60])
        + (" …" if len(opciones) > 60 else "")
    )


# ---------------------------------------------------------------------------
# Contexto de trabajo: menú + catálogo + carpeta (+ modo/gancho/duración)
# ---------------------------------------------------------------------------
@dataclass
class Ctx:
    m: Menu
    api: Interno
    catalogo: str
    carpeta: str  # nombre/slug EXACTO, ya resuelto
    modo: str = ""
    gancho: str = ""
    duracion: str = ""


async def catalogos(m: Menu, api: Interno) -> list[dict]:
    if m.tipo == "ropa":
        return [{"clave": c, "label": c} for c in CATALOGOS_ROPA]
    datos = await api.get(f"{POV}/sources")
    return [{"clave": s["slug"], "label": s["label"]} for s in datos.get("items", [])]


async def carpetas(m: Menu, api: Interno, catalogo: str, modo: str = "") -> list[dict]:
    if m.tipo == "ropa":
        modo = _modo_ropa(m, modo)
        cat = catalogo or "web"
        if cat not in CATALOGOS_ROPA:
            raise ErrorApp(f"Catálogo de ropa: {', '.join(CATALOGOS_ROPA)}.")
        datos = await api.get(f"{ROPA}/carpetas", sexo=m.sexo, modo=modo, catalogo=cat)
        return [
            {"carpeta": c["slug"], "label": c["label"], "productos": c.get("total", 0),
             "con_ficha": c.get("con_url", 0), "con_video": c.get("con_video", 0),
             "con_colores": c.get("con_colores", 0), "completada": c.get("completada", False)}
            for c in datos.get("items", [])
        ]
    base = LARGO if m.tipo == "largo" else POV
    cats = [c["clave"] for c in await catalogos(m, api)]
    catalogo = _elegir(catalogo or "inventario_general", cats, "el catálogo")
    datos = await api.get(f"{base}/folders", source=catalogo)
    return [
        {"carpeta": f["name"], **({"productos": f["total"]} if f.get("total") else {}), "con_ficha": f.get("con_url", 0),
         "sin_stock": f.get("sin_stock", 0), "completada": f.get("completed", False)}
        for f in datos.get("items", []) if not f.get("virtual")
    ]


def _modo_ropa(m: Menu, modo: str) -> str:
    modo = (modo or "").strip()
    if not modo:
        return m.modos[0]
    if modo not in m.modos:
        raise ErrorApp(f"Modo {modo!r} no existe en {m.label}. Válidos: {', '.join(m.modos)}.")
    return modo


async def contexto(
    menu_clave: str, api: Interno, catalogo: str, carpeta: str,
    modo: str = "", gancho: str = "", duracion: str = "",
) -> Ctx:
    m = menu(menu_clave)
    if m.tipo == "ropa":
        catalogo = catalogo or "web"
        modo = _modo_ropa(m, modo)
        duracion = duracion or "10"
    else:
        cats = [c["clave"] for c in await catalogos(m, api)]
        catalogo = _elegir(catalogo, cats, "el catálogo") if catalogo else "inventario_general"
    if m.tipo == "ugc":
        gancho = gancho or "dolor"
        duracion = duracion or "10"
    nombres = [c["carpeta"] for c in await carpetas(m, api, catalogo, modo)]
    carpeta = _elegir(carpeta, nombres, "la carpeta")
    return Ctx(m, api, catalogo, carpeta, modo, gancho, duracion)


# ---------------------------------------------------------------------------
# Productos
# ---------------------------------------------------------------------------
async def productos_crudos(c: Ctx) -> list[dict]:
    t = c.m.tipo
    if t == "ropa":
        d = await c.api.get(f"{ROPA}/prendas", carpeta=c.carpeta, modo=c.modo)
    elif t == "largo":
        d = await c.api.get(f"{LARGO}/productos", source=c.catalogo, folder=c.carpeta)
    elif t == "ugc":
        d = await c.api.get(f"{UGC}/productos", source=c.catalogo, folder=c.carpeta,
                            gancho=c.gancho, duracion=c.duracion)
    else:
        d = await c.api.get(f"{POV}/productos", source=c.catalogo, folder=c.carpeta)
    return d.get("items", [])


def _clips_subidos(c: Ctx, p: dict) -> list[int]:
    if c.m.tipo == "ropa":
        return list(p.get("clips_subidos") or [])
    if c.m.tipo == "ugc":
        return list(range(1, len(p.get("clips") or []) + 1))
    return [i for i in range(1, 6) if p.get(f"clip{i}")]


def resumen(c: Ctx, p: dict) -> dict:
    avisos = [a for a in (p.get("foto_aviso"), p.get("caption_riesgo") and
              f"Caption arriesgado: {p.get('caption_riesgo')}") if a]
    if p.get("sin_stock"):
        avisos.append("SIN STOCK: sáltalo")
    r = {
        "producto": p.get("producto"),
        "titulo": " ".join(str(p.get("titulo") or "").split()),
        "tienda": p.get("tienda", ""),
        "precio": p.get("precio", ""),
        "ficha_tiktok": p.get("product_url", ""),
        "textos": bool(p.get("titulo")),
        "clips_subidos": _clips_subidos(c, p),
        "video_montado": bool(p.get("video_path")),
        "montando": bool(p.get("montando")),
        "subido_a_tiktok": bool(p.get("uploaded")),
        "escaparate": bool(p.get("en_escaparate")),
        "avisos": avisos,
    }
    if c.m.tipo in ("pov", "largo"):
        r.update(guion=bool(p.get("guion")), clips_necesarios=p.get("clips_necesarios", 2),
                 clip_s=p.get("clip_s"))
        if c.m.tipo == "largo":
            r["estilo_guion"] = p.get("guion_estilo") or p.get("estilo_guion")
    elif c.m.tipo == "ropa":
        r.update(guion=bool(p.get("guion") or p.get("guiones")), plazos=p.get("plazos", False))
        if c.modo == "tienda_colores":
            r["colores"] = p.get("guion_colores") or p.get("variantes_colores") or []
    elif c.m.tipo == "ugc":
        r.update(escenas=len(p.get("escenas") or []), clips_necesarios=len(p.get("escenas") or []) or 3)
    return r


async def producto(c: Ctx, prod: str) -> dict:
    items = await productos_crudos(c)
    ids = [str(p.get("producto")) for p in items]
    elegido = _elegir(str(prod), ids, "el producto")
    return next(p for p in items if str(p.get("producto")) == elegido)


# ---------------------------------------------------------------------------
# Rutas internas de ficheros (se sirven al agente por el proxy del MCP)
# ---------------------------------------------------------------------------
def ruta_foto(c: Ctx, prod: str, variante: str = "limpia") -> str:
    from urllib.parse import urlencode

    if c.m.tipo == "ropa":
        if variante == "ficha":
            return ""  # Ropa no sirve la ficha por separado
        return f"{ROPA}/foto-limpia?" + urlencode({"producto": prod, "carpeta": c.carpeta})
    return f"{POV}/foto-limpia?" + urlencode(
        {"source": c.catalogo, "folder": c.carpeta, "producto": prod, "variante": variante})


def ruta_foto_color(c: Ctx, prod: str, k: int) -> str:
    from urllib.parse import urlencode

    return f"{ROPA}/foto-color-producto?" + urlencode(
        {"carpeta": c.carpeta, "producto": prod, "k": k, "descargar": 1})


def ruta_video(c: Ctx, prod: str) -> str:
    from urllib.parse import urlencode

    t = c.m.tipo
    if t == "ropa":
        q = {"producto": prod, "carpeta": c.carpeta, "modo": c.modo, "descargar": "true"}
        return f"{ROPA}/video?" + urlencode(q)
    q = {"source": c.catalogo, "folder": c.carpeta, "producto": prod, "descargar": "true"}
    if t == "ugc":
        q.update(gancho=c.gancho, duracion=c.duracion)
        return f"{UGC}/video?" + urlencode(q)
    return f"{LARGO if t == 'largo' else POV}/video?" + urlencode(q)


# ---------------------------------------------------------------------------
# Preparar: textos + guiones/escenas
# ---------------------------------------------------------------------------
async def preparar(c: Ctx, clip_s: int = 0, estilo_guion: str = "", rehacer: bool = False,
                   productos: str = "") -> dict:
    """Lo que en la web es el Paso 1. Devuelve qué ha hecho y qué ha encolado.
    `productos` ("1,3,5") limita los guiones de Moda a esas prendas: rehacer la
    carpeta entera le escribía guion también a las que no tocaba (una prenda de
    un solo color en Tienda Colores)."""
    solo = [x.strip() for x in (productos or "").split(",") if x.strip()]
    hecho: list[str] = []
    t = c.m.tipo
    if t == "largo" and estilo_guion:
        await c.api.post(f"{LARGO}/estilo-guion", {"source": c.catalogo, "estilo": estilo_guion})
        hecho.append(f"modo del guion = {estilo_guion} (todo el catálogo)")
    if t in ("pov", "largo") and clip_s:
        base = LARGO if t == "largo" else POV
        await c.api.post(f"{base}/clip-s/carpeta",
                         {"source": c.catalogo, "folder": c.carpeta, "clip_s": int(clip_s)})
        hecho.append(f"clips de {clip_s} s en toda la carpeta")

    items = await productos_crudos(c)
    faltan_textos = [p for p in items if not p.get("titulo") and not p.get("sin_stock")]
    if faltan_textos:
        if t == "ropa":
            await c.api.post(f"{ROPA}/extraer-textos", carpeta=c.carpeta, cola="true")
            hecho.append(f"textos de {len(faltan_textos)} prendas → en la cola")
        else:
            # Síncrono (~1 min): lo hace el llamador en segundo plano.
            await c.api.post(f"{POV}/extraer-textos", {"source": c.catalogo, "folder": c.carpeta})
            hecho.append(f"textos leídos ({len(faltan_textos)} productos)")
            items = await productos_crudos(c)
    elif t == "ropa" or not rehacer:
        hecho.append("textos: ya estaban")

    if t == "ropa" and faltan_textos:
        hecho.append("guiones: vuelve a llamar a `preparar_carpeta` cuando la cola termine los textos")
        return {"hecho": hecho}

    if t == "pov":
        if rehacer or any(not p.get("guion") for p in items):
            await c.api.post(f"{POV}/guiones/lote", {"source": c.catalogo, "folder": c.carpeta})
            hecho.append("guiones que faltaban → en la cola")
    elif t == "largo":
        if rehacer or any(not p.get("guion") for p in items):
            await c.api.post(f"{LARGO}/guiones/lote",
                             {"source": c.catalogo, "folder": c.carpeta, "rehacer": rehacer})
            hecho.append("guiones → en la cola")
    elif t == "ugc":
        if rehacer or any(not p.get("escenas") for p in items):
            await c.api.post(f"{UGC}/escenas/lote", {"source": c.catalogo, "folder": c.carpeta,
                                                    "gancho": c.gancho, "duracion": c.duracion,
                                                    "rehacer": rehacer})
            hecho.append("escenas → en la cola")
    elif t == "ropa":
        est = await estilo_ropa(c)
        if solo:
            items = [p for p in items if str(p.get("producto")) in solo]
        if est.get("escrito_fuera") and (
            rehacer or any(not (p.get("guion") or p.get("guiones")) for p in items)
        ):
            await c.api.post(f"{ROPA}/guiones", {"carpeta": c.carpeta, "modo": c.modo,
                                                "duracion": c.duracion, "rehacer": rehacer,
                                                "productos": solo})
            hecho.append("guiones" + (f" de {', '.join(solo)}" if solo else "") + " → en la cola")
        elif not est.get("escrito_fuera"):
            hecho.append("este modo no lleva guion por prenda (diálogo fijo o movimiento)")
    return {"hecho": hecho or ["nada que hacer: todo estaba listo"]}


# ---------------------------------------------------------------------------
# El plan de un producto: qué generar, con qué prompt, dónde y cómo
# ---------------------------------------------------------------------------
async def estilo_ropa(c: Ctx) -> dict:
    from src.nicho_ropa import config as ropa_config

    d = await c.api.get(f"{ROPA}/prompts", carpeta=c.carpeta, modo=c.modo,
                        duracion=c.duracion, modalidad=c.m.modalidad)
    clave = ropa_config.estilo_de_modo(c.modo)
    est = next((e for e in d.get("mof10", []) if e.get("clave") == clave), None)
    if not est:
        raise ErrorApp(f"No hay prompts para el modo {c.modo!r} en {c.carpeta!r}.")
    est = dict(est)
    est["_familias"] = d.get("familias") or {}
    return est


def _con_familia(texto: str, familia: str, familias: dict) -> str:
    fam = familias.get(familia or "") or familias.get("pantalon")
    if not fam:
        return texto
    for k, v in fam.items():
        texto = texto.replace("{{" + k.upper() + "}}", str(v))
    return texto


def _dice(bloque: str) -> str:
    m = re.search(r"«([^«»]*)[«»]", bloque or "")
    return m.group(1).strip() if m else ""


def _plataformas(habla: bool, ingrediente: bool, seg: int) -> list[str]:
    if habla or ingrediente:
        return [FLOW]
    return [FLOW, MAGNIFIC] + ([GENAIPRO] if seg <= 8 else [])


async def plan(c: Ctx, prod: str) -> dict:
    p = await producto(c, prod)
    pid = str(p["producto"])
    t = c.m.tipo
    out: dict[str, Any] = {
        "menu": c.m.clave, "catalogo": c.catalogo, "carpeta": c.carpeta, "modo": c.modo,
        "gancho": c.gancho, "duracion": c.duracion,
        "producto": resumen(c, p),
        "fotos_producto": {"foto_limpia": ruta_foto(c, pid, "limpia")},
        "imagenes": [], "clips": [], "avisos": list(resumen(c, p)["avisos"]),
    }
    if t != "ropa":
        out["fotos_producto"]["foto_ficha"] = ruta_foto(c, pid, "ficha")

    if t in ("pov", "largo"):
        pr = await c.api.get(f"{POV}/prompts")
        if not p.get("guion"):
            out["avisos"].append("Aún no tiene guion: llama a `preparar_carpeta` y espera la cola.")
        seg = int(p.get("clip_s") or (8 if t == "largo" else 10))
        n = int(p.get("clips_necesarios") or 2)
        out["imagenes"].append({
            "archivo": "imagen_1.png", "prompt": pr["imagen"], "adjuntar": ["foto_limpia"],
            "donde": f"{FLOW} · Nano Banana 2", "formato": "9:16",
            "revisar": "El producto idéntico a la foto limpia; la mano señala sin tocarlo; sin precios ni texto inventado.",
        })
        for i in range(1, n + 1):
            out["clips"].append({
                "clip": i, "archivo": f"clip_{i}.mp4", "prompt": pr["video"],
                "imagen": "imagen_1.png",
                "como_entra_la_imagen": "FRAME INICIAL (en GenAI Pro: start frame Y end frame = la misma imagen_1.png)",
                "segundos": seg, "habla": False, "plataformas": _plataformas(False, False, seg),
            })
        out["voz"] = "La pone la app (Fish). Por defecto «auto»: decide por la mano."
    elif t == "ugc":
        cfg = await c.api.get(f"{UGC}/config")
        ficha = next((x.get("ficha") for x in cfg.get("personajes", [])
                      if x.get("clave") == p.get("personaje_clave")), "")
        escenas = p.get("escenas") or []
        if not escenas:
            out["avisos"].append("Aún no tiene escenas: llama a `preparar_carpeta` y espera la cola.")
        out["personaje"] = {
            "archivo": "personaje.png", "prompt": ficha, "sexo": p.get("personaje_sexo", ""),
            "donde": f"{FLOW} · Nano Banana 2", "formato": "9:16",
            "nota": "Salvo que el operador use el personaje fijo de su cuenta (mismo sexo).",
        }
        seg = int(c.duracion or 10)
        for e in escenas:
            n = e["n"]
            out["imagenes"].append({
                "archivo": f"imagen_{n}.png", "prompt": e.get("prompt_imagen", ""),
                "adjuntar": ["personaje.png", "foto_limpia"], "donde": f"{FLOW} · Nano Banana 2",
                "formato": "9:16", "escena": e.get("titulo", ""),
                "revisar": "La MISMA persona en todas las escenas; mismo escenario; producto idéntico.",
            })
            out["clips"].append({
                "clip": n, "archivo": f"clip_{n}.mp4", "prompt": e.get("prompt_video", ""),
                "imagen": f"imagen_{n}.png", "como_entra_la_imagen": "FRAME INICIAL",
                "segundos": seg, "habla": True, "dice": e.get("guion", ""),
                "plataformas": [FLOW],
            })
        out["montaje"] = "Sube todos los clips con `subir_clip` y luego llama a `montar`."
    elif t == "creativos":
        pr = await c.api.get(f"{CREATIVOS}/prompt")
        out["imagenes"].append({
            "archivo": "creativo.png", "prompt": pr.get("imagen", ""), "adjuntar": ["foto_ficha"],
            "donde": f"{FLOW} · Nano Banana 2", "formato": pr.get("formato", "3:4"),
            "revisar": "Ningún beneficio, cifra u oferta que no esté en la ficha; texto bien escrito.",
        })
        out["montaje"] = "No hay vídeo: guarda el creativo y listo."
    elif t == "ropa":
        await _plan_ropa(c, p, out)
    return out


async def _plan_ropa(c: Ctx, p: dict, out: dict) -> None:
    est = await estilo_ropa(c)
    fam = est.pop("_familias", {})
    familia = p.get("familia", "")
    pid = str(p["producto"])
    habla = bool(est.get("voz", True))
    ingrediente = bool(est.get("ingrediente"))
    partes = int(est.get("partes") or 1)
    seg = 8 if (partes > 1 or est.get("colores")) else int(c.duracion or 10)
    adjuntar = ["personaje_marca.jpg", "foto_limpia"] if est.get("personaje") else ["foto_limpia"]

    out["imagenes"].append({
        "archivo": "imagen_1.png", "prompt": _con_familia(est.get("imagen", ""), familia, fam),
        "adjuntar": adjuntar, "donde": f"{FLOW} · Nano Banana 2", "formato": "9:16",
        "revisar": "La prenda conserva diseño, color, estampado y largo" +
                   ("; es EL personaje de la cuenta" if est.get("personaje") else ""),
    })
    if est.get("personaje"):
        out["avisos"].append("Adjunta el personaje fijo: descárgalo con la herramienta `personaje_marca`.")
    if est.get("plazos_fijo"):
        out["avisos"].append(
            "Este guion PROMETE pago a plazos: úsalo solo si la prenda los ofrece "
            f"(plazos={p.get('plazos')}); si no, borra esa frase antes de pegarlo.")

    if est.get("colores"):
        colores = p.get("guion_colores") or []
        if len(colores) < 2:
            out["avisos"].append("Sin colores en el guion: llama a `preparar_carpeta` (escribe los guiones) o la prenda no tiene 3+ colores.")
        n_fotos = int(p.get("fotos_color_producto") or 0)
        if len(colores) > 1 and not n_fotos:
            out["avisos"].append(
                "La app no tiene las fotos de la prenda en sus otros colores (ZIP importado "
                "antes del 22/9): sin ellas las imágenes de color se inventan el tono. Avisa al operador.")
        out["fotos_producto"]["fotos_color"] = [ruta_foto_color(c, pid, k) for k in range(1, n_fotos + 1)]
        for col in colores[:-1]:
            out["imagenes"].append({
                "archivo": f"imagen_color_{_norm(col).replace(' ', '_')}.png",
                "prompt": _con_familia(est.get("imagen_color") or "", familia, fam).replace("{{COLOR}}", col),
                "adjuntar": [f"la foto del producto en color {col} (de fotos_color)"],
                "donde": f"{FLOW} · en el MISMO chat que imagen_1", "formato": "9:16",
            })
        if est.get("imagen2"):
            out["imagenes"].append({
                "archivo": "imagen_2.png", "prompt": _con_familia(est["imagen2"], familia, fam),
                "adjuntar": [], "donde": f"{FLOW} · en el MISMO chat", "formato": "9:16",
            })
        cols = ", ".join(colores)
        guiones = p.get("guiones") or []
        for i, clave in enumerate(("video_omni", "video_omni2")):
            txt = _con_familia(est.get(clave) or "", familia, fam)
            txt = txt.replace("{{DICE}}", _dice(guiones[i] if i < len(guiones) else "")).replace("{{COLORES}}", cols)
            out["clips"].append({
                "clip": i + 1, "archivo": f"clip_{i + 1}.mp4", "prompt": txt,
                "imagen": "TODAS las imagen_color_* + imagen_1.png (la del color puesto, la ÚLTIMA)" if i == 0 else "imagen_2.png",
                "como_entra_la_imagen": "INGREDIENTES" if i == 0 else "FRAME INICIAL",
                "segundos": 8, "habla": True, "plataformas": [FLOW],
            })
        return

    if partes > 1 and est.get("imagen2"):
        out["imagenes"].append({
            "archivo": "imagen_2.png", "prompt": _con_familia(est["imagen2"], familia, fam),
            "adjuntar": [], "donde": f"{FLOW} · en el MISMO chat que imagen_1", "formato": "9:16",
            "revisar": "La MISMA persona y la misma prenda que en imagen_1.",
        })

    if partes > 1:
        guiones = p.get("guiones") or []
        if len(guiones) < partes:
            out["avisos"].append("Faltan los guiones por clip: llama a `preparar_carpeta`.")
        for i in range(partes):
            out["clips"].append({
                "clip": i + 1, "archivo": f"clip_{i + 1}.mp4",
                "prompt": guiones[i] if i < len(guiones) else "",
                "imagen": f"imagen_{i + 1}.png", "como_entra_la_imagen": "FRAME INICIAL",
                "segundos": 8, "habla": habla, "plataformas": _plataformas(habla, ingrediente, 8),
            })
        return

    if est.get("escrito_fuera"):
        texto = p.get("guion", "")
        if not texto:
            out["avisos"].append("Aún no tiene guion: llama a `preparar_carpeta` y espera la cola.")
    else:
        texto = est.get("guion", "")  # diálogo fijo del curso o prompt de movimiento
    out["clips"].append({
        "clip": 1, "archivo": "clip_1.mp4", "prompt": texto, "imagen": "imagen_1.png",
        "como_entra_la_imagen": "INGREDIENTE" if ingrediente else "FRAME INICIAL",
        "segundos": seg, "habla": habla, "plataformas": _plataformas(habla, ingrediente, seg),
    })


# ---------------------------------------------------------------------------
# Subir un clip y montar
# ---------------------------------------------------------------------------
async def subir_clip(c: Ctx, prod: str, clip: int, datos: bytes, nombre: str,
                     voz: str = "auto") -> dict:
    p = await producto(c, prod)
    pid = str(p["producto"])
    fichero = (nombre or f"clip_{clip}.mp4", datos, "video/mp4")
    t = c.m.tipo
    if t == "largo":
        n = int(p.get("clips_necesarios") or 2)
        if not 1 <= clip <= n:
            raise ErrorApp(f"Este producto lleva {n} clips: clip debe ir de 1 a {n}.")
        return await c.api.post_form(f"{LARGO}/clip/upload", {
            "source": c.catalogo, "folder": c.carpeta, "producto": pid, "slot": clip,
            "sexo": voz or "auto"}, fichero)
    if t == "pov":
        n = int(p.get("clips_necesarios") or 1)
        slot = 0 if n <= 1 else clip
        return await c.api.post_form(f"{POV}/video/upload", {
            "source": c.catalogo, "folder": c.carpeta, "producto": pid,
            "sexo": voz or "auto", "slot": slot}, fichero)
    if t == "ugc":
        return await c.api.post_form(f"{UGC}/clips/subir", {
            "source": c.catalogo, "folder": c.carpeta, "producto": pid,
            "gancho": c.gancho, "duracion": c.duracion}, fichero)
    if t == "ropa":
        est = await estilo_ropa(c)
        partes = int(est.get("partes") or 1)
        form: dict[str, Any] = {"producto": pid, "carpeta": c.carpeta, "modo": c.modo, "sexo": ""}
        if partes > 1:
            form["parte"] = clip
        if not est.get("voz", True):
            form["conservar_audio"] = "0"
        return await c.api.post_form(f"{ROPA}/video/upload", form, fichero)
    raise ErrorApp(f"{c.m.label} no lleva clips.")


async def montar(c: Ctx, prod: str) -> dict:
    p = await producto(c, prod)
    pid = str(p["producto"])
    if c.m.tipo == "ugc":
        return await c.api.post(f"{UGC}/montar", {"source": c.catalogo, "folder": c.carpeta,
                                                 "producto": pid, "gancho": c.gancho,
                                                 "duracion": c.duracion})
    if c.m.tipo == "pov":
        return await c.api.post(f"{POV}/video/montar", {"source": c.catalogo,
                                                       "folder": c.carpeta, "producto": pid})
    raise ErrorApp(f"En {c.m.label} el montaje arranca solo al subir el último clip.")


async def marcar(c: Ctx, prod: str, subido: bool | None, escaparate: bool | None,
                 vendio: bool | None) -> dict:
    p = await producto(c, prod)
    pid = str(p["producto"])
    cambios = {k: v for k, v in (("uploaded", subido), ("en_escaparate", escaparate),
                                 ("sold", vendio)) if v is not None}
    if not cambios:
        raise ErrorApp("Nada que marcar.")
    t = c.m.tipo
    if t == "ropa":
        return await c.api.post(f"{ROPA}/producto/estado", {"carpeta": c.carpeta, "producto": pid, **cambios})
    body = {"source": c.catalogo, "folder": c.carpeta, "producto": pid, **cambios}
    if t == "ugc":
        body.update(gancho=c.gancho, duracion=c.duracion)
        return await c.api.post(f"{UGC}/producto/estado", body)
    if t == "creativos":
        raise ErrorApp("En Creativos marca «Subido» desde la web.")
    return await c.api.post(f"{LARGO if t == 'largo' else POV}/producto/estado", body)
