"""Nicho General · UGC — productos, escenas, clips y montaje.

El catálogo, las fotos y los textos son los del Nicho POV BOF y se LEEN de
allí: son del producto, no de cómo se grabe, y extraerlos otra vez costaría las
mismas llamadas de Gemini dos veces. Aquí solo vive lo del anuncio UGC, que va
por usuario y por gancho + duración (ver `nicho_general/repos/product_repo.py`).
"""

from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse

from src.api.dependencies import get_current_user, get_queue, get_web_user
from src.api.exceptions import APIError
from src.api.schemas.nicho_general import (
    ConfigUGCResponse,
    EscenaUGC,
    EscenasLoteRequest,
    EstadoUGCRequest,
    MontarUGCRequest,
    OpcionUGC,
    ProductoUGC,
    ProductosUGCResponse,
)
from src.nicho_general import config
from src.nicho_general.repos import product_repo
from src.queue.manager import JobQueue
from src.queue.models import JobMode, JobStatus

router = APIRouter(
    prefix="/api/v1/nicho-general",
    tags=["nicho-general"],
    dependencies=[Depends(get_current_user)],
)

_EXTS_VIDEO = {".mp4", ".mov", ".m4v", ".webm"}


def _bad(msg: str) -> APIError:
    return APIError(msg, status_code=400)


@router.get("/config", response_model=ConfigUGCResponse)
def get_config() -> ConfigUGCResponse:
    """Los ganchos y las duraciones que existen.

    Los manda el backend para que la pantalla no se los sepa: son del curso y
    cambian cuando él publica otro formato.
    """
    return ConfigUGCResponse(
        ganchos=[OpcionUGC(clave=k, label=v["label"]) for k, v in config.GANCHOS.items()],
        duraciones=[
            OpcionUGC(clave=k, label=v["label"]) for k, v in config.DURACIONES.items()
        ],
        nichos=[OpcionUGC(clave=k, label=v["label"]) for k, v in config.NICHOS.items()],
        # Todos los personajes que existen, para poder cambiar el de un
        # producto a mano. Salen del nicho y de cuántas personas tenga.
        personajes=[
            OpcionUGC(
                clave=config.clave_personaje(n, sexo, i),
                label=(
                    f'{meta["label"]} · {config.SEXOS[sexo]}'
                    + (f" ({i})" if i > 1 else "")
                ),
                ficha=config.ficha_personaje(config.clave_personaje(n, sexo, i)),
            )
            for n, meta in config.NICHOS.items()
            for sexo in config.SEXOS
            for i in range(1, config.personas_de(n) + 1)
            # Solo se listan los del sexo del nicho salvo que se hayan creado
            # más: enseñar los dieciséis cuando hay ocho es prometer caras que
            # no existen.
            if sexo == config.sexo_de_nicho(n)
        ],
        sexos=[OpcionUGC(clave=k, label=v) for k, v in config.SEXOS.items()],
        escenas=config.ESCENAS,
        prompt_personaje=config.prompt_personaje(),
    )


def _montando(queue: JobQueue | None, source: str, folder: str) -> set[str]:
    """Productos de esta carpeta con un montaje en cola o en curso."""
    if queue is None:
        return set()
    activos: set[str] = set()
    try:
        for job in queue.get_all() or []:
            if job.mode != JobMode.NICHO_GENERAL_VIDEO:
                continue
            p = job.params or {}
            if str(p.get("source")) != source or str(p.get("folder")) != folder:
                continue
            if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
                activos.add(str(p.get("producto")))
    except Exception:  # noqa: BLE001
        pass
    return activos


@router.get("/productos", response_model=ProductosUGCResponse)
def list_productos(
    source: Annotated[str, Query()],
    folder: Annotated[str, Query()],
    gancho: Annotated[str, Query()] = "",
    duracion: Annotated[str, Query()] = "",
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> ProductosUGCResponse:
    """Los productos de la carpeta con lo que lleva hecho cada uno.

    Los textos salen del POV BOF; si una carpeta no los tiene, aquí no hay nada
    que enseñar todavía — se sacan una vez y sirven para todos los nichos.
    """
    from src.nicho_pov_bof import config as pov_config
    from src.nicho_pov_bof.repos import product_repo as pov_repo

    gancho = config.gancho_valido(gancho)
    duracion = config.duracion_valida(duracion)
    textos = (pov_repo.load_folder_para(source, folder, usuario).get("productos") or {})
    mios = (
        product_repo.load_folder(source, folder, usuario, gancho, duracion)
        .get("productos") or {}
    )
    escaparate = pov_repo.escaparate_index(usuario)
    activos = _montando(queue, source, folder)

    items = []
    for pid in sorted(textos, key=lambda x: (len(x), x)):
        t = textos[pid] or {}
        mio = mios.get(pid) or {}
        items.append(ProductoUGC(
            producto=pid,
            titulo=t.get("titulo", ""),
            titulo_tiktok_completo=t.get("titulo_tiktok_completo", ""),
            tienda=t.get("tienda", ""),
            caption=t.get("caption", ""),
            precio=str(t.get("precio") or ""),
            plazos=pov_config.hay_plazos(t),
            clean_photo_id=t.get("clean_photo_id"),
            titled_photo_id=t.get("titled_photo_id"),
            product_url=pov_repo.url_de(t),
            en_escaparate=pov_repo.marcado_en_escaparate(t, escaparate),
            escenas=[EscenaUGC(**e) for e in (mio.get("escenas") or [])],
            voz=str(mio.get("voz") or ""),
            nicho=str(mio.get("nicho") or ""),
            # El personaje que le toca. Si el operador eligió uno a mano manda
            # ese; si no, el del nicho, repartiendo entre las personas que haya
            # para no sacar la misma cara en todos.
            personaje_clave=str(mio.get("personaje") or "") or config.clave_personaje(
                str(mio.get("nicho") or ""),
                str(mio.get("personaje_sexo") or ""),
                config.reparte_persona(str(mio.get("nicho") or ""), folder, pid),
            ),
            personaje=str(mio.get("personaje") or ""),
            personaje_sexo=str(mio.get("personaje_sexo") or ""),
            clips=[str(c) for c in (mio.get("clips") or [])],
            video_path=mio.get("video_path"),
            video_listo_at=int(mio.get("video_listo_at") or 0),
            montando=pid in activos,
            uploaded=bool(mio.get("uploaded")),
            sold=bool(mio.get("sold")),
        ))
    return ProductosUGCResponse(items=items, gancho=gancho, duracion=duracion)


@router.post("/escenas/lote", status_code=201)
def escenas_lote(
    body: EscenasLoteRequest,
    queue: Annotated[JobQueue, Depends(get_queue)],
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Encola las tres escenas de una carpeta (o del catálogo entero).

    El gancho y la duración viajan en el trabajo: la cola tarda y cambiarlos en
    la pantalla mientras escribe metería lo escrito en el documento del otro.
    """
    if not body.source:
        raise _bad("Falta el catálogo.")
    gancho = config.gancho_valido(body.gancho)
    duracion = config.duracion_valida(body.duracion)
    etiqueta = (
        f"{config.GANCHOS[gancho]['label']} · {config.DURACIONES[duracion]['label']}"
    )
    alcance = body.folder or "todas"
    job = queue.enqueue(
        JobMode.NICHO_GENERAL_ESCENAS,
        title=f"🎬 Escenas UGC · {alcance} · {etiqueta}"
        + (" (rehacer)" if body.rehacer else ""),
        params={
            "source": body.source, "folder": body.folder, "usuario": usuario,
            "gancho": gancho, "duracion": duracion,
            "rehacer": bool(body.rehacer),
            "productos": [str(x) for x in (body.productos or [])],
        },
        enqueued_by=usuario or None,
    )
    return {"job_id": job.id}


@router.post("/clips/subir")
async def subir_clip(
    file: Annotated[UploadFile, File()],
    source: Annotated[str, Form()],
    folder: Annotated[str, Form()],
    producto: Annotated[str, Form()],
    gancho: Annotated[str, Form()] = "",
    duracion: Annotated[str, Form()] = "",
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Guarda UN clip del anuncio. Se suben todos, sin decir cuál es cuál.

    De uno en uno para poder enseñar el porcentaje de cada fichero, como en el
    POV BOF Largo. El ORDEN no se pregunta: lo decide el montaje escuchándolos.
    """
    from src.api.temp_storage import upload_subdir

    nombre = (file.filename or "").lower()
    ext = next((e for e in _EXTS_VIDEO if nombre.endswith(e)), "")
    if not ext:
        raise _bad(
            f"Formato de vídeo no soportado: {file.filename!r}. "
            f"Acepta: {', '.join(sorted(_EXTS_VIDEO))}."
        )
    dest = upload_subdir("nicho_general")
    stub = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{source}_{folder}_{producto}")
    token = f"ugc_{stub}_{int(time.time() * 1000)}_{os.getpid()}{ext}"
    try:
        with (dest / token).open("wb") as out:
            shutil.copyfileobj(file.file, out)
    except Exception as e:  # noqa: BLE001
        raise APIError(f"No se pudo guardar {file.filename!r}: {e}", status_code=500) from e

    prod = product_repo.anadir_clips(
        source, folder, producto, [str(dest / token)],
        usuario=usuario, gancho=gancho, duracion=duracion,
    )
    return {"clips": len(prod.get("clips") or [])}


@router.post("/clips/limpiar")
def limpiar_clips(
    body: MontarUGCRequest,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Vacía los clips para volver a subirlos (salió mal uno y se rehace)."""
    prod = product_repo.quitar_clips(
        body.source, body.folder, body.producto,
        usuario=usuario, gancho=body.gancho, duracion=body.duracion,
    )
    return {"clips": len(prod.get("clips") or [])}


@router.post("/montar", status_code=201)
def montar(
    body: MontarUGCRequest,
    queue: Annotated[JobQueue, Depends(get_queue)],
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> dict:
    """Encola el montaje del anuncio de un producto."""
    gancho = config.gancho_valido(body.gancho)
    duracion = config.duracion_valida(body.duracion)
    mio = product_repo.get_product(
        body.source, body.folder, body.producto, usuario, gancho, duracion,
    )
    clips = [c for c in (mio.get("clips") or []) if c]
    if not clips:
        raise _bad("Sube antes los clips del anuncio.")
    if not (mio.get("escenas") or []):
        # Sin escenas se puede montar, pero no se pueden ORDENAR: el orden sale
        # de casar la voz con el guion de cada una.
        raise _bad(
            "Este producto no tiene escenas escritas: sin ellas no se sabe qué "
            "clip va primero. Genera los textos antes."
        )
    job = queue.enqueue(
        JobMode.NICHO_GENERAL_VIDEO,
        title=(
            f"🎬 UGC: producto {body.producto} · {body.folder} · "
            f"{config.GANCHOS[gancho]['label']} {config.DURACIONES[duracion]['label']}"
        ),
        params={
            "source": body.source, "folder": body.folder,
            "producto": body.producto, "usuario": usuario,
            "gancho": gancho, "duracion": duracion,
        },
        enqueued_by=usuario or None,
    )
    return {"job_id": job.id}


@router.post("/producto/estado", response_model=ProductoUGC)
def set_estado(
    body: EstadoUGCRequest,
    queue: Annotated[JobQueue, Depends(get_queue)] = None,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> ProductoUGC:
    """Marca en qué punto está el producto, o con qué personaje se graba.

    El escaparate y los vendidos NO son de este nicho: van a los índices
    comunes por usuario (`nicho_pov_bof/repos/product_repo.py`), así que
    marcarlo aquí lo marca en todos.
    """
    from src.nicho_pov_bof.repos import product_repo as pov_repo

    gancho = config.gancho_valido(body.gancho)
    duracion = config.duracion_valida(body.duracion)
    campos = {
        k: v for k, v in (
            ("uploaded", body.uploaded), ("sold", body.sold), ("nicho", body.nicho),
            ("personaje", body.personaje), ("personaje_sexo", body.personaje_sexo),
        ) if v is not None
    }
    if campos:
        product_repo.update_product(
            body.source, body.folder, body.producto, usuario, gancho, duracion,
            **campos,
        )
    if body.sold is not None:
        try:
            if body.sold:
                pov_repo.marcar_vendido(
                    body.source, body.folder, body.producto, usuario=usuario,
                )
            else:
                pov_repo.desmarcar_vendido(
                    body.source, body.folder, body.producto, usuario,
                )
        except Exception:  # noqa: BLE001 — el dato ya está guardado
            pass
    if body.en_escaparate is not None:
        from src.nicho_pov_bof.repos import product_repo as pov

        textos = pov.get_product(body.source, body.folder, body.producto, usuario)
        pov.marcar_escaparate_producto(textos, body.en_escaparate, usuario)

    listado = list_productos(
        body.source, body.folder, gancho, duracion, queue, usuario,
    )
    for item in listado.items:
        if item.producto == body.producto:
            return item
    raise APIError(f"No existe el producto {body.producto}.", status_code=404)


@router.get("/video")
def ver_video(
    source: Annotated[str, Query()],
    folder: Annotated[str, Query()],
    producto: Annotated[str, Query()],
    gancho: Annotated[str, Query()] = "",
    duracion: Annotated[str, Query()] = "",
    descargar: Annotated[bool, Query()] = False,
    usuario: Annotated[str, Depends(get_web_user)] = "",
) -> FileResponse:
    """El anuncio montado, para verlo o descargarlo."""
    mio = product_repo.get_product(
        source, folder, producto, usuario, gancho, duracion,
    )
    ruta = Path(str(mio.get("video_path") or ""))
    if not ruta.name or not ruta.exists():
        raise APIError("Ese producto no tiene vídeo montado.", status_code=404)
    return FileResponse(
        ruta,
        media_type="video/mp4",
        filename=ruta.name if descargar else None,
    )
