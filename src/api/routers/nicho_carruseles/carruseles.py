"""Endpoints del Nicho Carruseles (Programa 4 — módulo 14).

Como en Creativos Pro, el CATÁLOGO no vive aquí: fuentes, carpetas, fotos,
textos, hashtags, escaparate y vendidos son los del Nicho POV BOF y la pantalla
usa sus endpoints. Aquí solo está lo propio del carrusel:

- qué productos valen (clasificación + interruptor manual),
- los dos mensajes,
- el banco de fotos (chica y producto) y el texto quemado encima,
- el progreso por carpeta y qué carruseles se han publicado.

El quemado NO pasa por la cola de trabajos: es PIL sobre un JPEG, décimas de
segundo. Encolarlo solo añadiría la espera de un worker (ver
`services/texto_foto.py`).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.api.dependencies import get_current_user, get_web_user
from src.api.exceptions import APIError
from src.nicho_carruseles import config
from src.nicho_carruseles.repos import carrusel_repo
from src.nicho_carruseles.services import fotos as fotos_svc

router = APIRouter(
    prefix="/api/v1/nicho-carruseles",
    tags=["nicho-carruseles"],
    dependencies=[Depends(get_current_user)],
)

_EXTS = (".jpg", ".jpeg", ".png", ".webp")
_TOPE_FOTO_MB = 12


def _bad_request(msg: str) -> APIError:
    return APIError(msg, status_code=400)


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------
class PromptsResponse(BaseModel):
    chica: str
    producto: str
    formato: str
    referencia_drive: str


class CompletarRequest(BaseModel):
    source: str
    folder: str
    completed: bool = True


class CarpetaRequest(BaseModel):
    source: str
    folder: str


class AptoRequest(BaseModel):
    source: str
    folder: str
    producto: str
    # `None` = quitar el interruptor manual y volver a hacer caso a la IA.
    apto: bool | None = None


class MensajeRequest(BaseModel):
    source: str
    folder: str
    producto: str
    mensaje1: str | None = None
    mensaje2: str | None = None


class QuemarRequest(BaseModel):
    source: str
    folder: str
    # Sin producto = toda la carpeta (así se queman de golpe las chicas, que es
    # el caso normal: mismo gesto para las diez).
    producto: str | None = None
    tipo: str = "chica"


class SubidoRequest(BaseModel):
    source: str
    folder: str
    producto: str
    uploaded: bool


# ---------------------------------------------------------------------------
# Prompts y carpetas
# ---------------------------------------------------------------------------
@router.get("/prompts", response_model=PromptsResponse)
def get_prompts() -> PromptsResponse:
    """Los dos prompts de Flow y el formato en el que hay que generar.

    El formato viaja con el prompt por lo mismo que en Creativos Pro: el
    generador no lo deduce del texto y salir en cuadrado es el error fácil.
    """
    try:
        return PromptsResponse(
            chica=config.leer_prompt("foto_chica"),
            producto=config.leer_prompt("foto_producto"),
            formato=config.FORMATO,
            referencia_drive=(
                "Productos España › Carruseles › Pronts Carruseles "
                "(la foto de la chica de referencia)"
            ),
        )
    except OSError as e:
        raise APIError(f"No se pudieron leer los prompts: {e}", status_code=500) from e


@router.get("/folders")
def list_folders(
    source: Annotated[str, Query()],
    refresh: Annotated[bool, Query()] = False,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Carpetas de la fuente con el progreso de ESTE nicho y cuántos aptos hay.

    El recuento de aptos es lo que evita el paseo inútil: filtrando a belleza y
    suplementos, la mayoría de carpetas se quedan en dos o tres productos y
    algunas en cero. Se leen todas de una vez con un `mget` — carpeta a carpeta
    eran 35 latencias de Upstash cada vez que se abría la pantalla.
    """
    from src.nicho_carruseles.repos import progress_repo
    from src.nicho_carruseles.repos.redis_base import get_nicho_carruseles_redis
    from src.nicho_pov_bof.services import drive_client

    try:
        carpetas = drive_client.list_product_folders(source, refresh=refresh)
    except ValueError as e:
        raise _bad_request(str(e)) from e
    except RuntimeError as e:
        raise APIError(f"No se pudo leer el Drive: {e}", status_code=502) from e

    nombres = [c.get("name", "") for c in carpetas]
    try:
        hechas = progress_repo.get_completed(source, usuario)
    except RuntimeError:
        hechas = set()

    r = get_nicho_carruseles_redis()
    docs = (
        r.mget_json([f"folder:{config.fuente_canonica(source)}:{n}" for n in nombres])
        if r.is_available() and nombres else []
    )
    items = []
    for i, nombre in enumerate(nombres):
        doc = (docs[i] if i < len(docs) else None) or {}
        prods = doc.get("productos") or {}
        aptos = sum(1 for p in prods.values() if carrusel_repo.es_apto(p))
        items.append({
            "name": nombre,
            "completed": nombre in hechas,
            "aptos": aptos,
            "clasificada": bool(doc.get("clasificada")),
        })

    return {
        "source": source,
        "items": items,
        # La carpeta que toca: la primera sin hacer que TENGA algún apto. Las
        # que se quedaron a cero al filtrar no son trabajo pendiente.
        "current": next(
            (i["name"] for i in items if not i["completed"] and i["aptos"]),
            next((i["name"] for i in items if not i["completed"]), None),
        ),
        "done": len(hechas),
        "total": len(nombres),
        "aptos": sum(i["aptos"] for i in items),
    }


@router.post("/complete")
def marcar_completada(
    body: CompletarRequest,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    from src.nicho_carruseles.repos import progress_repo

    try:
        if body.completed:
            progress_repo.mark_completed(body.source, body.folder, usuario)
        else:
            progress_repo.unmark_completed(body.source, body.folder, usuario)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return {"ok": True}


# ---------------------------------------------------------------------------
# Estado de la carpeta
# ---------------------------------------------------------------------------
def _estado_carpeta(source: str, folder: str, usuario: str) -> dict:
    from src.nicho_carruseles.repos import subidos_repo

    prods = carrusel_repo.productos(source, folder)
    horas = subidos_repo.subidos(source, folder, usuario)
    salida: dict[str, dict] = {}
    for pid, prod in prods.items():
        salida[pid] = {
            "categoria": prod.get("categoria") or "",
            "apto": carrusel_repo.es_apto(prod),
            "apto_manual": prod.get("apto"),
            "mensaje1": prod.get("mensaje1") or "",
            "mensaje2": prod.get("mensaje2") or "",
            "fotos": fotos_svc.estado(usuario, source, folder, pid),
            "subido_at": horas.get(pid, 0.0),
        }
    return {
        "source": source,
        "folder": folder,
        "clasificada": bool(carrusel_repo.load_folder(source, folder).get("clasificada")),
        "productos": salida,
    }


@router.get("/estado")
def estado_carpeta(
    source: Annotated[str, Query()],
    folder: Annotated[str, Query()],
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Lo que este nicho sabe de cada producto de la carpeta.

    Va aparte de la lista de productos (que es la del POV BOF) para no duplicar
    allí campos que solo entiende el carrusel: la pantalla junta las dos cosas.
    """
    return _estado_carpeta(source, folder, usuario)


@router.post("/clasificar")
def clasificar_carpeta(
    body: CarpetaRequest,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Decide con IA qué productos de la carpeta valen para carrusel.

    Lee los títulos YA extraídos por el POV BOF: si la carpeta no los tiene,
    primero hay que pulsar "Obtener textos" allí (o en esta misma pantalla, que
    llama a su endpoint).
    """
    from src.nicho_carruseles.services import clasificador
    from src.nicho_pov_bof.repos import product_repo

    productos = (product_repo.load_folder(body.source, body.folder).get("productos") or {})
    if not productos:
        raise _bad_request(
            "Esta carpeta no tiene textos extraídos todavía: pulsa antes "
            "'Obtener textos'."
        )
    cats = clasificador.clasificar(productos)
    if not cats:
        raise APIError(
            "No se pudo clasificar la carpeta (Gemini falló o no hay títulos). "
            "Vuelve a intentarlo.",
            status_code=502,
        )
    try:
        carrusel_repo.guardar_categorias(body.source, body.folder, cats)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return _estado_carpeta(body.source, body.folder, usuario)


@router.post("/apto")
def marcar_apto(
    body: AptoRequest,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Fuerza (o suelta) el veredicto de la IA para un producto."""
    try:
        # `None` no se puede mandar por `update_product` (descarta los nulos),
        # así que quitar el interruptor se hace a mano sobre el documento.
        if body.apto is None:
            data = carrusel_repo.load_folder(body.source, body.folder)
            prod = (data.setdefault("productos", {})).setdefault(body.producto, {})
            prod.pop("apto", None)
            carrusel_repo.save_folder(body.source, body.folder, data)
        else:
            carrusel_repo.update_product(
                body.source, body.folder, body.producto, apto=body.apto,
            )
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return _estado_carpeta(body.source, body.folder, usuario)


# ---------------------------------------------------------------------------
# Mensajes
# ---------------------------------------------------------------------------
@router.post("/mensajes")
def escribir_mensajes(
    body: CarpetaRequest,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Escribe los dos mensajes de todos los productos APTOS de la carpeta.

    En una sola llamada, que es lo único que garantiza que el mensaje 1 salga
    distinto en cada uno (ver `services/mensajes.py`). Los mensajes 1 que ya se
    usaron en otras carpetas viajan en la petición para que tampoco se repitan
    entre carpetas.
    """
    from src.nicho_carruseles.services import mensajes as mensajes_svc
    from src.nicho_pov_bof.repos import product_repo

    del usuario  # el estado que se devuelve se recalcula abajo con el suyo

    guardados = carrusel_repo.productos(body.source, body.folder)
    aptos = {pid for pid, prod in guardados.items() if carrusel_repo.es_apto(prod)}
    if not aptos:
        raise _bad_request(
            "En esta carpeta no hay ningún producto apto para carrusel. "
            "Clasifícala o marca alguno a mano."
        )

    textos = (product_repo.load_folder(body.source, body.folder).get("productos") or {})
    pendientes = {
        pid: prod for pid, prod in textos.items()
        if pid in aptos and not (guardados.get(pid) or {}).get("mensaje1")
    }
    if not pendientes:
        raise _bad_request("Todos los productos aptos de esta carpeta ya tienen mensajes.")

    escritos = mensajes_svc.escribir(pendientes, evitar=_mensajes_usados(body.source))
    if not escritos:
        raise APIError(
            "No se pudieron escribir los mensajes (Gemini falló). Vuelve a "
            "intentarlo.",
            status_code=502,
        )
    try:
        carrusel_repo.guardar_mensajes(body.source, body.folder, escritos)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    return {"escritos": len(escritos)}


def _mensajes_usados(source: str) -> list[str]:
    """Los mensajes 1 ya escritos en esta fuente, para no repetirlos.

    Se leen de una tacada con `mget`. Si Redis no está, se devuelve vacío: es
    una ayuda al prompt, no un requisito.
    """
    from src.nicho_carruseles.repos.redis_base import get_nicho_carruseles_redis
    from src.nicho_pov_bof.services import drive_client

    r = get_nicho_carruseles_redis()
    if not r.is_available():
        return []
    try:
        nombres = [c.get("name", "") for c in drive_client.list_product_folders(source)]
    except Exception:  # noqa: BLE001 — Drive caído: se sigue sin la lista
        return []
    docs = r.mget_json([f"folder:{config.fuente_canonica(source)}:{n}" for n in nombres])
    usados: list[str] = []
    for doc in docs:
        for prod in ((doc or {}).get("productos") or {}).values():
            m1 = str(prod.get("mensaje1") or "").strip()
            if m1:
                usados.append(m1)
    return usados


@router.post("/mensaje")
def editar_mensaje(
    body: MensajeRequest,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Corrige a mano un mensaje. Tira la versión quemada con el texto viejo."""
    campos = {}
    if body.mensaje1 is not None:
        campos["mensaje1"] = body.mensaje1.strip()
    if body.mensaje2 is not None:
        campos["mensaje2"] = body.mensaje2.strip()
    if not campos:
        raise _bad_request("No has mandado ningún mensaje que cambiar.")
    try:
        carrusel_repo.update_product(body.source, body.folder, body.producto, **campos)
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e

    # Sin esto la foto seguiría enseñando el mensaje anterior y no habría forma
    # de saber cuál de las dos cosas es la buena.
    if "mensaje1" in campos:
        fotos_svc.borrar("chica_txt", usuario, body.source, body.folder, body.producto)
    if "mensaje2" in campos:
        fotos_svc.borrar("producto_txt", usuario, body.source, body.folder, body.producto)
    return _estado_carpeta(body.source, body.folder, usuario)


# ---------------------------------------------------------------------------
# Fotos
# ---------------------------------------------------------------------------
def _pendientes_de_chica(source: str, usuario: str) -> list[dict]:
    """Productos aptos de la fuente que aún no tienen foto de chica.

    En ORDEN de trabajo (carpeta y número): es el mismo orden en el que se
    reparte la tanda que sube el operador.
    """
    from src.nicho_carruseles.repos.redis_base import get_nicho_carruseles_redis
    from src.nicho_pov_bof.services import drive_client

    r = get_nicho_carruseles_redis()
    if not r.is_available():
        return []
    try:
        nombres = [c.get("name", "") for c in drive_client.list_product_folders(source)]
    except Exception as e:  # noqa: BLE001
        raise APIError(f"No se pudo leer el Drive: {e}", status_code=502) from e

    docs = r.mget_json([f"folder:{config.fuente_canonica(source)}:{n}" for n in nombres])
    pendientes: list[dict] = []
    for i, folder in enumerate(nombres):
        prods = ((docs[i] if i < len(docs) else None) or {}).get("productos") or {}
        for pid in sorted(prods, key=lambda p: (len(p), p)):
            if not carrusel_repo.es_apto(prods[pid]):
                continue
            if fotos_svc.tiene("chica", usuario, source, folder, pid):
                continue
            pendientes.append({"source": source, "folder": folder, "producto": pid})
    return pendientes


@router.get("/chicas/pendientes")
def chicas_pendientes(
    source: Annotated[str, Query()],
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Cuántas fotos de chica hacen falta en esta fuente, y para quién.

    Es el número que el operador se lleva a Flow: genera esa cantidad de cuatro
    en cuatro y las sube todas juntas.
    """
    pendientes = _pendientes_de_chica(source, usuario)
    return {
        "source": source,
        "faltan": len(pendientes),
        "por_tanda": config.CHICAS_POR_TANDA,
        "items": pendientes[: config.CHICAS_POR_TANDA * 4],
    }


async def _leer_foto(archivo: UploadFile, que: str = "La foto") -> bytes:
    nombre = (archivo.filename or "").lower()
    if not any(nombre.endswith(e) for e in _EXTS):
        raise _bad_request(
            f"{que} tiene un formato no soportado ({archivo.filename!r}). "
            "Acepta jpg, jpeg, png o webp."
        )
    datos = await archivo.read()
    if not datos:
        raise _bad_request(f"{que} llegó vacía.")
    if len(datos) > _TOPE_FOTO_MB * 1024 * 1024:
        raise _bad_request(
            f"{que} pesa {len(datos) / 1e6:.0f} MB; el tope son {_TOPE_FOTO_MB} MB."
        )
    return datos


@router.post("/chicas")
async def subir_chicas(
    source: Annotated[str, Form()],
    archivos: Annotated[list[UploadFile], File()],
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Sube la tanda de chicas y la reparte entre los productos que no tienen.

    Se asignan POR ORDEN (carpeta y número). La foto 1 no depende del producto,
    así que da igual cuál caiga dónde — lo que importa es que cada producto
    acabe con una y que no se repita ninguna.

    Se ordenan por nombre de fichero antes de repartir: Flow los baja numerados
    y así el reparto es reproducible si hay que repetirlo.
    """
    if not archivos:
        raise _bad_request("No has adjuntado ninguna foto.")

    pendientes = _pendientes_de_chica(source, usuario)
    if not pendientes:
        raise _bad_request(
            "Ningún producto apto está esperando foto de chica en esta fuente."
        )

    leidos: list[tuple[str, bytes]] = []
    for archivo in sorted(archivos, key=lambda a: (a.filename or "").lower()):
        leidos.append((archivo.filename or "", await _leer_foto(archivo)))

    try:
        asignados = fotos_svc.repartir_chicas(usuario, pendientes, leidos)
    except OSError as e:
        raise APIError(f"No se pudieron guardar las fotos: {e}", status_code=500) from e

    return {
        "asignadas": len(asignados),
        "items": asignados,
        "sobran_fotos": max(0, len(leidos) - len(pendientes)),
        "faltan": max(0, len(pendientes) - len(leidos)),
    }


@router.post("/foto")
async def subir_foto(
    source: Annotated[str, Form()],
    folder: Annotated[str, Form()],
    producto: Annotated[str, Form()],
    archivo: Annotated[UploadFile, File()],
    tipo: Annotated[str, Form()] = "producto",
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Sube (o sustituye) UNA foto de un producto.

    Lo normal es la foto 2 —la del producto, que sí es de cada uno—; con
    `tipo=chica` se cambia la chica que le tocó, cuando la tanda dejó una que no
    convence.
    """
    if tipo not in ("chica", "producto"):
        raise _bad_request("El tipo de foto tiene que ser 'chica' o 'producto'.")
    datos = await _leer_foto(archivo)
    try:
        fotos_svc.guardar(
            tipo, usuario, source, folder, producto, datos,
            filename=archivo.filename or "",
        )
        # La versión con texto era de la foto vieja: se tira para que no quede
        # un carrusel con la foto nueva y el quemado de la anterior.
        fotos_svc.borrar(f"{tipo}_txt", usuario, source, folder, producto)
    except OSError as e:
        raise APIError(f"No se pudo guardar la foto: {e}", status_code=500) from e
    return _estado_carpeta(source, folder, usuario)


@router.delete("/foto")
def borrar_foto(
    source: Annotated[str, Query()],
    folder: Annotated[str, Query()],
    producto: Annotated[str, Query()],
    tipo: Annotated[str, Query()] = "producto",
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    if tipo not in config.SUBCARPETAS:
        raise _bad_request(f"Tipo de foto desconocido: {tipo!r}.")
    fotos_svc.borrar(tipo, usuario, source, folder, producto)
    if tipo in ("chica", "producto"):
        fotos_svc.borrar(f"{tipo}_txt", usuario, source, folder, producto)
    return _estado_carpeta(source, folder, usuario)


@router.post("/quemar")
def quemar(
    body: QuemarRequest,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Escribe el mensaje encima de la foto.

    Sin `producto` va toda la carpeta de una vez, que es como se usa con las
    chicas: mismo gesto para las diez. Un producto sin foto o sin mensaje no
    tumba la tanda — se cuenta como saltado y se sigue.
    """
    if body.tipo not in ("chica", "producto"):
        raise _bad_request("Solo se puede quemar texto sobre 'chica' o 'producto'.")
    campo = "mensaje1" if body.tipo == "chica" else "mensaje2"

    guardados = carrusel_repo.productos(body.source, body.folder)
    if body.producto:
        objetivos = {body.producto: guardados.get(body.producto, {})}
    else:
        objetivos = {
            pid: prod for pid, prod in guardados.items() if carrusel_repo.es_apto(prod)
        }

    hechas, saltados = 0, []
    for pid, prod in sorted(objetivos.items(), key=lambda kv: (len(kv[0]), kv[0])):
        texto = str(prod.get(campo) or "").strip()
        if not texto:
            saltados.append(f"{pid} (sin mensaje)")
            continue
        try:
            fotos_svc.quemar_texto(
                body.tipo, usuario, body.source, body.folder, pid, texto,
            )
            hechas += 1
        except ValueError:
            saltados.append(f"{pid} (sin foto)")
        except OSError as e:
            saltados.append(f"{pid} ({e})")

    if not hechas and saltados:
        raise _bad_request(f"No se pudo quemar ninguna: {', '.join(saltados)}.")
    return {
        "quemadas": hechas,
        "saltados": saltados,
        "estado": _estado_carpeta(body.source, body.folder, usuario),
    }


@router.get("/foto")
def ver_foto(
    source: Annotated[str, Query()],
    folder: Annotated[str, Query()],
    producto: Annotated[str, Query()],
    tipo: Annotated[str, Query()] = "chica",
    descargar: Annotated[bool, Query()] = False,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> FileResponse:
    """Sirve una foto del banco. Auth por `?api_key=` (va en un `<img src>`).

    Con `descargar=1` fuerza la descarga: el atributo `download` de un `<a>` se
    ignora entre orígenes distintos —y la API es otro origen—, así que lo único
    que la baja en el móvil es el `Content-Disposition` de aquí.
    """
    if tipo not in config.SUBCARPETAS:
        raise _bad_request(f"Tipo de foto desconocido: {tipo!r}.")
    ruta = fotos_svc.buscar(tipo, usuario, source, folder, producto)
    if not ruta:
        raise APIError("Esa foto todavía no está subida.", status_code=404)

    headers = {"Cache-Control": "no-cache"}
    if descargar:
        pos = 1 if tipo.startswith("chica") else 2
        nombre = fotos_svc.nombre_descarga(source, folder, producto, pos)
        headers["Content-Disposition"] = f'attachment; filename="{nombre}"'
    media = "image/png" if ruta.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(ruta, media_type=media, headers=headers)


# ---------------------------------------------------------------------------
# Publicado
# ---------------------------------------------------------------------------
@router.get("/subidos")
def list_subidos(
    source: Annotated[str, Query()],
    folder: Annotated[str, Query()],
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    from src.nicho_carruseles.repos import subidos_repo

    marcados = subidos_repo.subidos(source, folder, usuario)
    return {"items": sorted(marcados), "horas": marcados}


@router.post("/subido")
def marcar_subido(
    body: SubidoRequest,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Lo marca el operador: aquí no hay montaje que termine."""
    from src.nicho_carruseles.repos import subidos_repo

    try:
        subidos_repo.marcar(
            body.source, body.folder, body.producto, body.uploaded, usuario,
        )
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e

    # Un carrusel publicado cuenta para el tope diario de la cuenta.
    try:
        from src.cuotas.repos import cuota_repo

        cuota_repo.marcar(
            "carruseles",
            f"carruseles|{body.source}|{body.folder}|{body.producto}",
            usuario, body.uploaded,
        )
    except Exception:  # noqa: BLE001 — el tope es un aviso, no un bloqueo
        pass
    marcados = subidos_repo.subidos(body.source, body.folder, usuario)
    return {"items": sorted(marcados), "horas": marcados}
