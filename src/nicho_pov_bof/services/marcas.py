"""Marcas de un producto de los catálogos del operador y su prioridad.

Un producto puede llevar VARIAS marcas a la vez (no es una categoría):

- **físico** (`fisico`): lo tenemos en casa y se pueden grabar vídeos reales.
  Los de «Productos físicos» lo son siempre; en el resto se marca. Que sea
  físico no impide hacerle vídeos con IA.
- **necesita contenido** (`contenido`): la tienda pide N vídeos (1 por
  defecto, a veces 3). Cada vídeo de ese producto marcado como subido en Mis
  tandas descuenta uno (`registrar_subido`) y, al llegar a cero, deja de
  tener prioridad.
- **funciona en Q4** (`q4`): desempata el resto del catálogo.
- **clips reales** (`clips_reales`): ruta o enlace de la carpeta del Drive con
  las tomas grabadas de ese producto, para que el agente las encuentre.
- **muestra reembolsable**: vive aparte (`services/reembolsables.py`), con su
  importe; aquí solo se usa para ordenar.

Todo va en el documento COMPARTIDO de la carpeta (el mismo de `product_url`):

    "contenido": {"activo": bool, "videos": int>=1, "subidos": [ids],
                  "marcado_at": ts, "notas": str}

`subidos` guarda los ids de los vídeos (usuario|id de Mis tandas) y no un
contador: marcar y desmarcar el mismo vídeo dos veces no descuenta doble.

Contadores por FORMATO (siempre, esté o no activo `contenido`):

    "formatos":  {"ia": [ids], "viral": [ids], "fisico": [ids]}
    "objetivos": {"ia": 5, "viral": 1, "fisico": 0}     # editable 0..20

`formato_de(nicho, modo)` clasifica un vídeo de Mis tandas: pov/mm/alea y largo
(salvo estilo «viral») = `ia`; largo «viral» y rv `con_ia`/`genjutsu` = `viral`; rv
`sin_ia` = `fisico`. La tarjeta enseña «IA 0/5 · Viral 0/1 · Físico 0/2».
También son ids (idempotente), y `registrar_subido(formato=...)` los apunta
en la misma escritura que `contenido`.

Prioridad (`prioridades`): 1) necesita contenido con vídeos pendientes, el que
menos le falta antes; 2) reembolsables en curso, el que más dinero da antes;
3) el resto, primero los que funcionan en Q4.
"""

from __future__ import annotations

import time

from src.nicho_pov_bof import config
from src.nicho_pov_bof.repos import product_repo
from src.nicho_pov_bof.services import reembolsables

# Los catálogos que sube el operador (los del Drive del curso no se marcan).
FUENTES_MARCAS: tuple[str, ...] = tuple(config.CATALOGOS_OPERADOR)
# Los que son físicos por definición: no hace falta marcarlos.
FUENTES_FISICAS: tuple[str, ...] = ("productos_fisicos", "productos_fisicos_ana")
MAX_VIDEOS = 20
FORMATOS: tuple[str, ...] = ("ia", "viral", "fisico")
OBJETIVOS_DEFECTO: dict[str, int] = {"ia": 5, "viral": 1, "fisico": 0}


def formato_de(nicho: str, modo: str = "") -> str | None:
    """Formato (`ia`/`viral`/`fisico`) de un vídeo de Mis tandas, o None."""
    nicho, modo = str(nicho or ""), str(modo or "")
    if nicho in ("pov", "mm", "alea"):
        return "ia"
    if nicho == "largo":
        return "viral" if modo == "viral" else "ia"
    if nicho == "rv":
        if modo in ("con_ia", "genjutsu"):
            return "viral"
        if modo == "sin_ia":
            return "fisico"
    return None


def formatos_info(prod: dict | None) -> dict:
    """Subidos / objetivo / hecho por formato."""
    prod = prod or {}
    ids = prod.get("formatos") if isinstance(prod.get("formatos"), dict) else {}
    obj = prod.get("objetivos") if isinstance(prod.get("objetivos"), dict) else {}
    out: dict = {}
    for f in FORMATOS:
        try:
            objetivo = int(obj.get(f, OBJETIVOS_DEFECTO[f]))
        except (TypeError, ValueError):
            objetivo = OBJETIVOS_DEFECTO[f]
        n = len(set(str(i) for i in (ids.get(f) or [])))
        out[f] = {"subidos": n, "objetivo": objetivo, "hecho": objetivo > 0 and n >= objetivo}
    return out


def _ahora() -> float:
    return time.time()


def _exige_fuente(source: str) -> None:
    if source not in FUENTES_MARCAS:
        raise ValueError(
            "Las marcas solo existen en los catálogos que sube el operador "
            f"({', '.join(FUENTES_MARCAS)}), no en {source!r}."
        )


def contenido_info(contenido: dict | None) -> dict | None:
    """El dato guardado + lo derivado (pendientes, hecho). None si no está activo."""
    if not isinstance(contenido, dict) or not contenido.get("activo"):
        return None
    videos = max(1, int(contenido.get("videos") or 1))
    subidos = [str(s) for s in (contenido.get("subidos") or [])]
    pendientes = max(0, videos - len(subidos))
    return {
        "activo": True,
        "videos": videos,
        "subidos": len(subidos),
        "pendientes": pendientes,
        "hecho": pendientes == 0,
        "marcado_at": float(contenido.get("marcado_at") or 0),
        "notas": str(contenido.get("notas") or ""),
    }


def info(source: str, prod: dict | None) -> dict:
    """Las marcas de un producto, tal y como las enseña la tarjeta."""
    prod = prod or {}
    return {
        "fisico": bool(prod.get("fisico")) or source in FUENTES_FISICAS,
        "fisico_por_catalogo": source in FUENTES_FISICAS,
        "q4": bool(prod.get("q4")),
        "clips_reales": str(prod.get("clips_reales") or ""),
        "contenido": contenido_info(prod.get("contenido")),
        "formatos": formatos_info(prod),
    }


def _videos(valor) -> int:
    try:
        n = int(valor)
    except (TypeError, ValueError) as e:
        raise ValueError("Los vídeos que pide la tienda tienen que ser un número entero.") from e
    if not 1 <= n <= MAX_VIDEOS:
        raise ValueError(f"Los vídeos que pide la tienda van de 1 a {MAX_VIDEOS}.")
    return n


def _leer(source: str, folder: str, producto: str) -> dict:
    return (
        (product_repo.load_folder(source, folder).get("productos") or {})
        .get(str(producto)) or {}
    )


def _item(source: str, folder: str, producto: str, prod: dict) -> dict:
    return {
        "source": source,
        "catalogo": reembolsables.etiqueta(source),
        "folder": folder,
        "producto": str(producto),
        "titulo": str(prod.get("titulo") or ""),
        "tienda": str(prod.get("tienda") or ""),
        "product_url": str(prod.get("product_url") or ""),
        "marcas": info(source, prod),
        "reembolso": reembolsables.info(prod.get("reembolso")),
    }


def marcar(
    folder: str, producto: str, *, source: str,
    fisico: bool | None = None, q4: bool | None = None,
    clips_reales: str | None = None,
    contenido: bool | None = None, contenido_videos=None, contenido_notas: str | None = None,
    objetivo_ia: int | None = None, objetivo_viral: int | None = None,
    objetivo_fisico: int | None = None,
    comprobar: bool = True,
) -> dict:
    """Pone o quita marcas. Solo cambia lo que se pasa (None = no tocar).

    `objetivo_*` = cuántos vídeos de ese formato se quieren subir (0..20).

    `contenido_videos` sin `contenido` también lo activa. Volver a activar
    uno ya activo conserva los vídeos ya subidos (solo cambia cuántos pide).
    """
    _exige_fuente(source)
    producto = str(producto)
    if comprobar and not reembolsables._existe(folder, producto, source):
        raise ValueError(f"No hay producto {producto} en la carpeta {folder!r}.")
    if contenido_videos is not None and contenido is None:
        contenido = True
    n_videos = _videos(contenido_videos) if contenido_videos is not None else None
    nuevos_obj: dict[str, int] = {}
    for f, v in (("ia", objetivo_ia), ("viral", objetivo_viral), ("fisico", objetivo_fisico)):
        if v is None:
            continue
        try:
            n = int(v)
        except (TypeError, ValueError) as e:
            raise ValueError("Los objetivos por formato tienen que ser números enteros.") from e
        if not 0 <= n <= MAX_VIDEOS:
            raise ValueError(f"El objetivo de {f} va de 0 a {MAX_VIDEOS}.")
        nuevos_obj[f] = n
    with product_repo._cerrojo_carpeta(source, folder):
        actual = _leer(source, folder, producto)
        campos: dict = {}
        if fisico is not None:
            campos["fisico"] = bool(fisico)
        if q4 is not None:
            campos["q4"] = bool(q4)
        if clips_reales is not None:
            campos["clips_reales"] = str(clips_reales).strip()[:500]
        if contenido is not None:
            previo = actual.get("contenido") if isinstance(actual.get("contenido"), dict) else {}
            if contenido:
                campos["contenido"] = {
                    "activo": True,
                    "videos": n_videos or int(previo.get("videos") or 1),
                    "subidos": list(previo.get("subidos") or []) if previo.get("activo") else [],
                    "marcado_at": float(previo.get("marcado_at") or 0) if previo.get("activo") else _ahora(),
                    "notas": (str(contenido_notas).strip()[:500] if contenido_notas is not None
                              else str(previo.get("notas") or "")),
                }
            else:
                campos["contenido"] = {}
        elif contenido_notas is not None and isinstance(actual.get("contenido"), dict) \
                and actual["contenido"].get("activo"):
            campos["contenido"] = {**actual["contenido"], "notas": str(contenido_notas).strip()[:500]}
        if nuevos_obj:
            previo_obj = actual.get("objetivos") if isinstance(actual.get("objetivos"), dict) else {}
            campos["objetivos"] = {**previo_obj, **nuevos_obj}
        if not campos:
            raise ValueError("No hay ninguna marca que cambiar.")
        prod = product_repo._update_product_sin_cerrojo(source, folder, producto, **campos)
    return _item(source, folder, producto, prod)


def registrar_subido(
    source: str, folder: str, producto: str, video_id: str, subido: bool,
    formato: str | None = None,
) -> dict | None:
    """Un vídeo del producto se marcó (o desmarcó) como subido.

    Idempotente: el mismo vídeo no cuenta dos veces. Con `formato`, apunta o
    quita el id en `formatos[formato]` SIEMPRE; `contenido` solo cambia si el
    producto lo necesita. Todo en una escritura bajo el cerrojo. Devuelve el
    contenido derivado o None.
    """
    if source not in FUENTES_MARCAS:
        return None
    if formato is not None and formato not in FORMATOS:
        formato = None
    producto = str(producto)
    video_id = str(video_id)
    with product_repo._cerrojo_carpeta(source, folder):
        prod = _leer(source, folder, producto)
        campos: dict = {}
        if formato:
            previos = prod.get("formatos") if isinstance(prod.get("formatos"), dict) else {}
            lista = [str(s) for s in (previos.get(formato) or [])]
            if subido and video_id not in lista:
                lista.append(video_id)
            elif not subido and video_id in lista:
                lista.remove(video_id)
            else:
                lista = None
            if lista is not None:
                campos["formatos"] = {**previos, formato: lista}
        c = prod.get("contenido")
        res = None
        if isinstance(c, dict) and c.get("activo"):
            subidos = [str(s) for s in (c.get("subidos") or [])]
            nuevo = None
            if subido and video_id not in subidos:
                subidos.append(video_id)
                nuevo = {**c, "subidos": subidos}
            elif not subido and video_id in subidos:
                subidos.remove(video_id)
                nuevo = {**c, "subidos": subidos}
            if nuevo is not None:
                campos["contenido"] = nuevo
                c = nuevo
            res = contenido_info(c)
        if campos:
            product_repo._update_product_sin_cerrojo(source, folder, producto, **campos)
    return res


def _grupo(item: dict) -> tuple:
    c = item["marcas"]["contenido"]
    r = item["reembolso"]
    if c and not c["hecho"]:
        importe = r["importe"] if r and r["estado"] == "en_curso" else 0
        return (0, c["pendientes"], -importe, item["folder"], item["producto"])
    if r and r["estado"] == "en_curso":
        return (1, -r["importe"], r["dias_restantes"], item["folder"], item["producto"])
    return (2, not item["marcas"]["q4"], 0, item["folder"], item["producto"])


def motivo(item: dict) -> str:
    """Por qué está en ese puesto, en una frase corta para la lista."""
    c = item["marcas"]["contenido"]
    r = item["reembolso"]
    if c and not c["hecho"]:
        return f"necesita contenido: faltan {c['pendientes']} de {c['videos']}"
    if r and r["estado"] == "en_curso":
        return (f"reembolsable {r['importe']:.2f} €: {r['ventas']}/{r['ventas_objetivo']} ventas, "
                f"{r['dias_restantes']} días")
    return "funciona en Q4" if item["marcas"]["q4"] else "sin prioridad"


def prioridades(
    *, fuentes: list[str] | tuple[str, ...] | None = None,
    solo_fisicos: bool = False, incluir_resto: bool = False, limite: int = 0,
) -> dict:
    """Los productos de los catálogos del operador en el orden en que tocan.

    `solo_fisicos` deja solo los que se pueden grabar en real.
    `incluir_resto=True` añade el tercer grupo (los que no tienen prisa).
    """
    from src.nicho_pov_bof.services import mis_productos

    lista = [f for f in (fuentes or FUENTES_MARCAS) if f in FUENTES_MARCAS]
    pares: list[tuple[str, str]] = []
    for fuente in lista:
        try:
            nombres = mis_productos.carpetas(fuente)
        except Exception:  # noqa: BLE001 — un catálogo sin carpeta no tumba el resto
            nombres = []
        pares.extend((fuente, c) for c in nombres)
    docs = product_repo.load_folders(pares) if pares else []
    items: list[dict] = []
    for (fuente, carpeta), doc in zip(pares, docs):
        for pid, prod in ((doc or {}).get("productos") or {}).items():
            if not isinstance(prod, dict) or prod.get("sin_stock"):
                continue
            item = _item(fuente, carpeta, str(pid), prod)
            if solo_fisicos and not item["marcas"]["fisico"]:
                continue
            items.append(item)
    items.sort(key=_grupo)
    for it in items:
        it["grupo"] = ("contenido", "reembolso", "resto")[_grupo(it)[0]]
        it["motivo"] = motivo(it)
    cuenta = {g: sum(1 for i in items if i["grupo"] == g) for g in ("contenido", "reembolso", "resto")}
    if not incluir_resto:
        items = [i for i in items if i["grupo"] != "resto"]
    if limite and limite > 0:
        items = items[:limite]
    return {"items": items, "total": len(items), **cuenta}
