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

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.api.dependencies import get_current_user, get_queue, get_web_user
from src.api.exceptions import APIError
from src.nicho_carruseles import config
from src.nicho_carruseles.repos import carrusel_repo
from src.nicho_carruseles.services import fotos as fotos_svc
from src.queue.manager import JobQueue

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
class EscenarioPrompt(BaseModel):
    clave: str
    label: str
    para: str
    prompt: str
    # El de la foto 2 para ese escenario: el mismo producto se recrea en la
    # cocina o en el dormitorio según dónde se use.
    prompt_producto: str
    prompt_producto_mano: str
    # Para CREAR la foto de referencia de este escenario desde cero, sin
    # adjuntar ninguna imagen: es la única forma de fijar la edad (con una foto
    # de referencia el modelo copia la cara, y con ella los años).
    prompt_referencia: str
    # Qué chica buscar (o pedirle a la IA) para este escenario: la referencia es
    # lo que manda en la tanda, así que elegirla bien es la mitad del trabajo.
    busqueda: str


class PromptsResponse(BaseModel):
    """Los prompts de Flow: uno por escenario de chica, más el del producto.

    Los escenarios existen porque la chica tiene que estar DONDE se usa el
    producto: en la cama si es un colchón, en el sofá si es un sofá. Es el mismo
    prompt del curso cambiando una frase.
    """

    escenarios: list[EscenarioPrompt]
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


class EscenarioRequest(BaseModel):
    source: str
    folder: str
    producto: str
    # `""` = volver al que le toca por su categoría.
    escenario: str = ""


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
    # "chica", "producto" o "ambas" — que es el botón de "mandar a editar" de
    # la carpeta entera, cuando ya están las dos fotos de cada producto.
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
def get_prompts(
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> PromptsResponse:
    """Los dos prompts de Flow y el formato en el que hay que generar.

    El formato viaja con el prompt por lo mismo que en Creativos Pro: el
    generador no lo deduce del texto y salir en cuadrado es el error fácil.

    Si el operador tiene ficha de chica, los prompts de referencia salen con
    ELLA dentro (JSON) en vez del párrafo genérico.
    """
    from src.nicho_carruseles.services import chica_ficha

    try:
        return PromptsResponse(
            escenarios=[
                EscenarioPrompt(
                    clave=clave,
                    label=meta["label"],
                    para=meta["para"],
                    prompt=config.leer_prompt(f"foto_chica_{clave}"),
                    prompt_producto=config.prompt_producto(clave),
                    prompt_producto_mano=config.prompt_producto(clave, con_mano=True),
                    prompt_referencia=chica_ficha.prompt_referencia(usuario, clave),
                    busqueda=config.BUSQUEDA_CHICA.get(clave, ""),
                )
                for clave, meta in config.ESCENARIOS.items()
            ],
            producto=config.prompt_producto(),
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
            "escenario": carrusel_repo.escenario_de(prod),
            "escenario_manual": prod.get("escenario") or "",
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


@router.post("/escenario")
def cambiar_escenario(
    body: EscenarioRequest,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Cambia dónde tiene que estar la chica de ese producto.

    Se usa cuando la categoría se queda corta: un difusor de aroma es belleza,
    pero la foto queda mejor con la chica en el sofá. Tirar la chica que ya
    tuviera sería peor que dejarla: si molesta, se borra desde su tarjeta.
    """
    if body.escenario and body.escenario not in config.ESCENARIOS:
        raise _bad_request(f"Escenario desconocido: {body.escenario!r}.")
    try:
        data = carrusel_repo.load_folder(body.source, body.folder)
        prod = (data.setdefault("productos", {})).setdefault(body.producto, {})
        if body.escenario:
            prod["escenario"] = body.escenario
        else:
            prod.pop("escenario", None)
        carrusel_repo.save_folder(body.source, body.folder, data)
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
# La chica de la casa
# ---------------------------------------------------------------------------
@router.get("/chica")
def ver_chica(usuario: Annotated[str, Depends(get_web_user)] = "") -> dict:
    """La ficha de la chica del operador, si tiene."""
    from src.nicho_carruseles.services import chica_ficha

    doc = chica_ficha.leer(usuario)
    ficha = doc.get("ficha") if isinstance(doc, dict) else None
    return {
        "hay": bool(ficha),
        "creada_at": (doc or {}).get("creada_at", 0),
        "resumen": _resumen_chica(ficha) if ficha else "",
    }


def _resumen_chica(ficha: dict) -> str:
    """Una línea para la pantalla: pelo, edad y rasgos."""
    s = ficha.get("subject") or {}
    partes = [
        str(s.get("age") or ""),
        str(s.get("hair_color") or ""),
        str(s.get("nationality") or ""),
    ]
    return " · ".join(p for p in partes if p)


@router.post("/chica")
async def crear_chica(
    archivo: Annotated[UploadFile, File()],
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Convierte la foto de una chica en la ficha con la que se crean las
    referencias de todos los escenarios.

    Es el paso del Nicho Ropa Con Personas traído aquí: un párrafo no clava a
    una persona y la referencia es lo que manda en la foto final.
    """
    from src.nicho_carruseles.services import chica_ficha

    datos = await _leer_foto(archivo, "La foto de la chica")
    try:
        ficha = chica_ficha.crear_desde_foto(datos)
        chica_ficha.guardar(usuario, ficha)
    except ValueError as e:
        raise _bad_request(str(e)) from e
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e
    except Exception as e:  # noqa: BLE001 — Gemini caído o sin cuota
        raise APIError(f"No se pudo crear la ficha: {e}", status_code=502) from e
    return {"hay": True, "resumen": _resumen_chica(ficha)}


@router.delete("/chica")
def borrar_chica(usuario: Annotated[str, Depends(get_web_user)] = "") -> dict:
    """Vuelve a los prompts genéricos."""
    from src.nicho_carruseles.services import chica_ficha

    chica_ficha.borrar(usuario)
    return {"hay": False, "resumen": ""}


# ---------------------------------------------------------------------------
# Fotos de referencia (las que se adjuntan en Flow)
# ---------------------------------------------------------------------------
@router.get("/referencias")
def estado_referencias(
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Qué referencias hay: la de la chica (del curso o propia) y la de la
    foto 2 (siempre propia — el curso no da ninguna)."""
    from src.nicho_carruseles.services import referencia

    return {"items": referencia.estado(usuario)}


@router.get("/referencia")
def ver_referencia(
    tipo: Annotated[str, Query()] = "chica",
    escenario: Annotated[str, Query()] = "",
    descargar: Annotated[bool, Query()] = False,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> FileResponse:
    """Sirve la foto de referencia. Auth por `?api_key=` (va en un `<img src>`).

    Con `escenario` devuelve la de ese escenario si la hay; si no, la general.
    """
    from src.nicho_carruseles.services import referencia

    try:
        ruta = referencia.obtener(tipo, usuario, escenario)
    except ValueError as e:
        raise _bad_request(str(e)) from e
    if not ruta:
        raise APIError(
            "No hay foto de referencia. Sube una desde la pantalla.", status_code=404,
        )
    headers = {"Cache-Control": "no-cache"}
    if descargar:
        headers["Content-Disposition"] = f'attachment; filename="referencia_{tipo}.jpg"'
    media = "image/png" if ruta.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(ruta, media_type=media, headers=headers)


@router.post("/referencia")
async def subir_referencia(
    archivo: Annotated[UploadFile, File()],
    tipo: Annotated[str, Form()] = "chica",
    escenario: Annotated[str, Form()] = "",
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Pone una referencia propia (gana sobre la general y sobre la del curso).

    Con `escenario` es solo para ese escenario: es lo que deja tener una chica
    joven para la playa y otra para la cocina.
    """
    from src.nicho_carruseles.services import referencia

    datos = await _leer_foto(archivo, "La foto de referencia")
    try:
        referencia.guardar(
            tipo, usuario, datos, filename=archivo.filename or "",
            escenario=escenario,
        )
    except ValueError as e:
        raise _bad_request(str(e)) from e
    except OSError as e:
        raise APIError(f"No se pudo guardar la referencia: {e}", status_code=500) from e
    return {"items": referencia.estado(usuario)}


@router.delete("/referencia")
def borrar_referencia(
    tipo: Annotated[str, Query()] = "chica",
    escenario: Annotated[str, Query()] = "",
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Quita la propia y vuelve a la de arriba (la general o la del curso)."""
    from src.nicho_carruseles.services import referencia

    try:
        referencia.borrar(tipo, usuario, escenario)
    except ValueError as e:
        raise _bad_request(str(e)) from e
    return {"items": referencia.estado(usuario)}


# ---------------------------------------------------------------------------
# Fotos
# ---------------------------------------------------------------------------
def _pendientes_de_chica(usuario: str, escenario: str = "") -> list[dict]:
    """Productos aptos SIN foto de chica, de TODOS los catálogos.

    Global a propósito: la foto 1 no depende del producto ni del catálogo, así
    que la tanda de Flow se hace una vez para todo el trabajo pendiente y no
    catálogo a catálogo (lo pidió así el operador).

    En ORDEN de trabajo (catálogo, carpeta y número): es el mismo orden en el
    que se reparte la tanda que sube.
    """
    from src.nicho_carruseles.repos.redis_base import get_nicho_carruseles_redis
    from src.nicho_pov_bof.services import drive_client

    r = get_nicho_carruseles_redis()
    if not r.is_available():
        return []

    pendientes: list[dict] = []
    for source in config.fuentes_a_barrer():
        try:
            nombres = [c.get("name", "") for c in drive_client.list_product_folders(source)]
        except Exception:  # noqa: BLE001 — un catálogo ilegible no tumba el resto
            continue
        docs = r.mget_json(
            [f"folder:{config.fuente_canonica(source)}:{n}" for n in nombres]
        )
        for i, folder in enumerate(nombres):
            prods = ((docs[i] if i < len(docs) else None) or {}).get("productos") or {}
            for pid in sorted(prods, key=lambda p: (len(p), p)):
                prod = prods[pid]
                if not carrusel_repo.es_apto(prod):
                    continue
                suyo = carrusel_repo.escenario_de(prod)
                if escenario and suyo != escenario:
                    continue
                if fotos_svc.tiene("chica", usuario, source, folder, pid):
                    continue
                pendientes.append({
                    "source": source, "folder": folder, "producto": pid,
                    "escenario": suyo,
                })
    return pendientes


@router.get("/chicas/pendientes")
def chicas_pendientes(
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Cuántas fotos de chica hacen falta EN TOTAL, repartidas por escenario.

    Es lo que el operador se lleva a Flow: tantas en casa, tantas en la cama,
    tantas en el sofá… Cada escenario tiene su prompt (`GET /prompts`) y su
    tanda, porque una chica del sofá no vale para un producto de jardín.
    """
    pendientes = _pendientes_de_chica(usuario)
    por_escenario = {
        clave: sum(1 for p in pendientes if p["escenario"] == clave)
        for clave in config.ESCENARIOS
    }
    return {
        "faltan": len(pendientes),
        "por_escenario": por_escenario,
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
    archivos: Annotated[list[UploadFile], File()],
    escenario: Annotated[str, Form()] = "generico",
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Sube la tanda de chicas de un escenario y la reparte.

    Se asignan POR ORDEN (catálogo, carpeta y número) entre los productos de ESE
    escenario que aún no tienen. Dentro de un escenario la foto 1 no depende del
    producto, así que da igual cuál caiga dónde — lo que importa es que cada
    producto acabe con una y que no se repita ninguna.

    Se ordenan por nombre de fichero antes de repartir: Flow los baja numerados
    y así el reparto es reproducible si hay que repetirlo.
    """
    if not archivos:
        raise _bad_request("No has adjuntado ninguna foto.")
    if escenario not in config.ESCENARIOS:
        raise _bad_request(f"Escenario desconocido: {escenario!r}.")

    pendientes = _pendientes_de_chica(usuario, escenario)
    if not pendientes:
        raise _bad_request(
            "Ningún producto está esperando foto de chica "
            f"«{config.ESCENARIOS[escenario]['label']}»."
        )

    leidos: list[tuple[str, bytes]] = []
    for archivo in sorted(archivos, key=lambda a: (a.filename or "").lower()):
        leidos.append((archivo.filename or "", await _leer_foto(archivo)))

    try:
        asignados = fotos_svc.repartir_chicas(usuario, pendientes, leidos)
    except OSError as e:
        raise APIError(f"No se pudieron guardar las fotos: {e}", status_code=500) from e

    return {
        "escenario": escenario,
        "asignadas": len(asignados),
        "items": asignados,
        "sobran_fotos": max(0, len(leidos) - len(pendientes)),
        "faltan": max(0, len(pendientes) - len(leidos)),
    }


@router.get("/aptos")
def list_aptos(
    categoria: Annotated[str, Query()] = "",
    sin_foto2: Annotated[bool, Query()] = False,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Todos los productos aptos, de TODOS los catálogos, con su categoría.

    Es lo que deja bajar las fotos limpias EN LOTE por categoría: se generan en
    Flow todas las de dormitorio de una sentada, luego todas las de belleza…
    Trabajar carpeta a carpeta con dos productos por carpeta era el cuello de
    botella de este nicho.

    Devuelve también el resumen del filtro ("248/290 pasan"), que es lo que
    dice de un vistazo si merece la pena seguir clasificando.
    """
    todos = _barrer(usuario)
    aptos = [i for i in todos if i["apto"]]

    items = aptos
    if categoria:
        items = [i for i in items if i["categoria"] == categoria]
    if sin_foto2:
        items = [i for i in items if not i["tiene_foto2"]]

    por_categoria: dict[str, int] = {}
    for i in aptos:
        if i["categoria"]:
            por_categoria[i["categoria"]] = por_categoria.get(i["categoria"], 0) + 1

    return {
        "items": items,
        "por_categoria": por_categoria,
        "resumen": {
            # Productos con textos extraídos: los que se han podido mirar.
            "total": len(todos),
            "clasificados": sum(1 for i in todos if i["categoria"]),
            "aptos": len(aptos),
            "filtros": len(config.CATEGORIAS_APTAS),
        },
    }


def _barrer_aptos(usuario: str) -> list[dict]:
    """Solo los que valen para carrusel."""
    return [i for i in _barrer(usuario) if i["apto"]]


def _barrer(usuario: str) -> list[dict]:
    """TODOS los productos con textos, de todos los catálogos, en orden.

    Cruza tres cosas: lo que sabe este nicho (categoría, mensajes), los textos
    del POV BOF (título, para reconocerlos) y qué fotos hay ya en el Drive.
    Todo con dos `mget` por catálogo — leer carpeta a carpeta eran 35 latencias
    de Upstash por cada una de las dos fuentes.
    """
    from src.nicho_carruseles.repos.redis_base import get_nicho_carruseles_redis
    from src.nicho_pov_bof.repos import product_repo
    from src.nicho_pov_bof.services import drive_client

    r = get_nicho_carruseles_redis()
    if not r.is_available():
        return []

    salida: list[dict] = []
    for source in config.fuentes_a_barrer():
        try:
            nombres = [c.get("name", "") for c in drive_client.list_product_folders(source)]
        except Exception:  # noqa: BLE001
            continue
        canon = config.fuente_canonica(source)
        mios = r.mget_json([f"folder:{canon}:{n}" for n in nombres])
        textos = product_repo.load_folders([(source, n) for n in nombres])
        for i, folder in enumerate(nombres):
            prods = ((mios[i] if i < len(mios) else None) or {}).get("productos") or {}
            suyos = ((textos[i] if i < len(textos) else None) or {}).get("productos") or {}
            # Se recorren los que tienen TEXTOS, no los clasificados: si no, el
            # resumen diría "12/12 pasan" contando solo lo ya mirado.
            for pid in sorted(suyos, key=lambda p: (len(p), p)):
                texto = suyos[pid] or {}
                if not str(texto.get("titulo") or "").strip():
                    continue
                prod = prods.get(pid) or {}
                apto = carrusel_repo.es_apto(prod)
                salida.append({
                    "source": source,
                    "folder": folder,
                    "producto": pid,
                    "ref": f"{source}|{folder}|{pid}",
                    "titulo": texto.get("titulo") or "",
                    "tienda": texto.get("tienda") or "",
                    "categoria": prod.get("categoria") or "",
                    "apto": apto,
                    "escenario": carrusel_repo.escenario_de(prod) if apto else "",
                    "tiene_foto2": apto and fotos_svc.tiene(
                        "producto", usuario, source, folder, pid,
                    ),
                })
    return salida


class PrepararRequest(BaseModel):
    """Filtrar (y escribir mensajes de) TODO un catálogo, por la cola."""

    source: str
    rehacer: bool = False
    # Solo el filtro, sin escribir mensajes: para mirar primero cuántos pasan.
    solo_filtrar: bool = False


@router.post("/preparar", status_code=201)
def preparar_catalogo(
    body: PrepararRequest,
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> dict:
    """Encola el filtro + los mensajes de todas las carpetas del catálogo.

    Los dos pasos de la pantalla, pero para las 35 carpetas: de una en una son
    70 botones. Las dos llamadas son de TEXTO (leen los títulos ya extraídos),
    así que salen baratas.
    """
    from src.nicho_pov_bof import config as pov_config
    from src.queue.models import JobMode, JobStatus

    if body.source not in pov_config.SOURCES:
        raise _bad_request(f"Catálogo desconocido: {body.source!r}")

    etiqueta = pov_config.SOURCES[body.source].get("label") or body.source
    title = f"🖼️ Carruseles · {etiqueta}" + (" (solo filtro)" if body.solo_filtrar else "")
    job = queue.enqueue(
        JobMode.NICHO_CARRUSELES_PREPARAR,
        title=title,
        params={
            "source": body.source,
            "rehacer": bool(body.rehacer),
            "solo_filtrar": bool(body.solo_filtrar),
        },
    )
    pendientes = [
        j for j in queue.get_all()
        if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
    ]
    return {
        "job_id": job.id,
        "title": title,
        "position_in_queue": next(
            (i for i, j in enumerate(pendientes) if j.id == job.id), 0
        ),
    }


@router.post("/fotos2", status_code=201)
async def subir_fotos2(
    archivos: Annotated[list[UploadFile], File()],
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Guarda un trozo de la tanda de fotos de PRODUCTO. NO reparte todavía.

    La pantalla las sube de ocho en ocho (para poder enseñar el porcentaje y no
    mandar 150 MB de una vez) y al terminar llama a `/fotos2/repartir`. Hasta
    entonces viven en "sin asignar", que es donde no se pierden pase lo que
    pase.
    """
    if not archivos:
        raise _bad_request("No has adjuntado ninguna foto.")

    guardadas = 0
    for archivo in sorted(archivos, key=lambda a: (a.filename or "").lower()):
        datos = await _leer_foto(archivo)
        try:
            fotos_svc.guardar_sin_asignar(
                usuario, datos, filename=archivo.filename or "",
            )
            guardadas += 1
        except OSError as e:
            raise APIError(f"No se pudieron guardar las fotos: {e}", status_code=500) from e
    return {"recibidas": guardadas}


@router.post("/fotos2/repartir", status_code=201)
def repartir_fotos2(
    queue: Annotated[JobQueue, Depends(get_queue)],
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Encola el reconocimiento de las fotos que estén sin asignar.

    Va por la cola porque es una llamada de visión por cada 12 fotos: con una
    tanda de 40 el navegador se quedaba minuto y medio esperando.
    """
    from src.queue.models import JobMode

    sueltas = fotos_svc.listar_sin_asignar(usuario)
    if not sueltas:
        raise _bad_request("No hay fotos pendientes de repartir.")
    job = queue.enqueue(
        JobMode.NICHO_CARRUSELES_REPARTO,
        title=f"🧩 Repartir {len(sueltas)} foto(s) de carrusel",
        params={"usuario": usuario},
    )
    return {"pendientes": len(sueltas), "job_id": job.id}


@router.get("/sin-asignar")
def list_sin_asignar(usuario: Annotated[str, Depends(get_web_user)] = "") -> dict:
    """Fotos de producto que la IA no supo colocar."""
    return {"items": fotos_svc.listar_sin_asignar(usuario)}


@router.get("/sin-asignar/foto")
def ver_sin_asignar(
    archivo: Annotated[str, Query()],
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> FileResponse:
    ruta = fotos_svc.ruta_sin_asignar(usuario, archivo)
    if not ruta:
        raise APIError("Esa foto ya no está.", status_code=404)
    media = "image/png" if ruta.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(ruta, media_type=media, headers={"Cache-Control": "no-cache"})


class AsignarRequest(BaseModel):
    archivo: str
    source: str
    folder: str
    producto: str


@router.post("/sin-asignar/asignar")
def asignar_suelta(
    body: AsignarRequest,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Coloca a mano una de las fotos sueltas en su producto."""
    try:
        fotos_svc.asignar_sin_asignar(
            usuario, body.archivo, body.source, body.folder, body.producto,
        )
    except ValueError as e:
        raise _bad_request(str(e)) from e
    except OSError as e:
        raise APIError(f"No se pudo guardar la foto: {e}", status_code=500) from e
    return {"items": fotos_svc.listar_sin_asignar(usuario)}


@router.delete("/sin-asignar")
def borrar_suelta(
    archivo: Annotated[str, Query()],
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    ruta = fotos_svc.ruta_sin_asignar(usuario, archivo)
    if ruta:
        ruta.unlink(missing_ok=True)
    return {"items": fotos_svc.listar_sin_asignar(usuario)}


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
    if body.tipo not in ("chica", "producto", "ambas"):
        raise _bad_request("Solo se puede quemar 'chica', 'producto' o 'ambas'.")
    tipos = ("chica", "producto") if body.tipo == "ambas" else (body.tipo,)

    guardados = carrusel_repo.productos(body.source, body.folder)
    if body.producto:
        objetivos = {body.producto: guardados.get(body.producto, {})}
    else:
        objetivos = {
            pid: prod for pid, prod in guardados.items() if carrusel_repo.es_apto(prod)
        }

    hechas, saltados = 0, []
    for pid, prod in sorted(objetivos.items(), key=lambda kv: (len(kv[0]), kv[0])):
        for tipo in tipos:
            campo = "mensaje1" if tipo == "chica" else "mensaje2"
            etiqueta = f"{pid}·{'1' if tipo == 'chica' else '2'}"
            texto = str(prod.get(campo) or "").strip()
            if not texto:
                saltados.append(f"{etiqueta} (sin mensaje)")
                continue
            try:
                fotos_svc.quemar_texto(
                    tipo, usuario, body.source, body.folder, pid, texto,
                )
                hechas += 1
            except ValueError:
                saltados.append(f"{etiqueta} (sin foto)")
            except OSError as e:
                saltados.append(f"{etiqueta} ({e})")

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
