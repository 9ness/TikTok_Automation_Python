"""Editor rápido (editor.nebulabsmedia.com) — API del móvil.

Router pequeño y aislado: subir → cortar → estado → retocar → descargar, más
el saldo de créditos. Auth = ticket firmado de la web (`Authorization: Bearer`,
scope «rapido»); para `<video src>` y descargas se acepta también `?t=<ticket>`.
Los bytes del vídeo van del navegador al box (no pasan por Vercel).

Créditos: 1 = 1 minuto del original (hacia arriba). V1 sin pagos reales.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.api.dependencies import get_current_user, get_queue
from src.api.exceptions import APIError, ValidationError
from src.api.web_ticket import TicketClaims, verify_ticket
from src.api.exceptions import UnauthorizedError
from src.editor_auto.rapido import servicio as svc
from src.queue.manager import JobQueue
from src.queue.models import JobMode, JobStatus

logger = logging.getLogger("editor_auto.rapido")

router = APIRouter(prefix="/api/v1/editor-auto/rapido", tags=["editor-auto · rápido"])

_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}
_CHUNK = 1024 * 1024


def ticket_rapido(
    authorization: Annotated[str | None, Header()] = None,
    t: Annotated[str | None, Query()] = None,
) -> TicketClaims:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    elif t:
        token = t
    if not token:
        raise UnauthorizedError("Falta el ticket.")
    claims = verify_ticket(token)
    if claims.scope != "rapido":
        raise UnauthorizedError("El ticket no vale para el editor rápido.")
    return claims


Claims = Annotated[TicketClaims, Depends(ticket_rapido)]


def _nivel(claims: TicketClaims) -> str:
    """Rol de la cuenta en la web (va firmado en el ticket). Sin rol = «standard»."""
    rol = str((claims.raw or {}).get("rol") or "standard")
    return rol if rol in ("standard", "plus", "pro", "admin") else "standard"


def _es_admin(claims: TicketClaims) -> bool:
    return _nivel(claims) == "admin"


class SubsAjustes(BaseModel):
    activo: bool = True
    estilo: str | None = Field(None, description="id del catálogo (GET /opciones); por defecto el primero")
    color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$", description="hex; sobrescribe el color de resalte")
    fuente: str | None = Field(None, description="id de GET /opciones → fuentes")
    posicion: str = Field("abajo", description="abajo | centro | arriba")


class FlechaAjustes(BaseModel):
    activo: bool = False
    id: str | None = Field(None, description="id de GET /opciones → flechas")


class Ajustes(BaseModel):
    ritmo: str = Field("natural", description="natural | sin_pausas")
    formato: str = Field("9:16", description="9:16 | original")
    idioma: str = Field("auto", description="auto | es | en")
    subtitulos: SubsAjustes = Field(default_factory=SubsAjustes)
    flecha: FlechaAjustes = Field(default_factory=FlechaAjustes)


class Estilo(BaseModel):
    subtitulos: SubsAjustes | None = None
    flecha: FlechaAjustes | None = None


class DarCreditos(BaseModel):
    email: str
    creditos: int


def _validar_estilo(sub: SubsAjustes | None, fl: FlechaAjustes | None) -> tuple[dict | None, dict | None]:
    try:
        return (svc.validar_subtitulos(sub.model_dump()) if sub is not None else None,
                svc.validar_flecha(fl.model_dump()) if fl is not None else None)
    except ValueError as e:
        raise ValidationError(str(e)) from e


def _admin_o_403(claims: TicketClaims) -> None:
    if not _es_admin(claims):
        raise APIError("Solo para administradores.", status_code=403)


class Retoque(BaseModel):
    devueltos: list[int] = Field(default_factory=list, description="Ids de cortes que se devuelven al vídeo")


class Valoracion(BaseModel):
    nota: int | str = Field(..., description="1-5, o «bien» (=5) / «mal» (=1)")
    comentario: str | None = Field(None, max_length=500)


class AjusteCreditos(BaseModel):
    email: str
    delta: int


def _optout(ficha: dict, claims: TicketClaims) -> None:
    """Si el ticket lleva `no_dataset: true`, la ficha no entra en el dataset de entrenamiento."""
    ficha["no_dataset"] = bool((claims.raw or {}).get("no_dataset"))


def _ficha_o_404(vid: str, email: str) -> dict:
    f = svc.cargar_ficha(vid, email)
    if f is None:
        raise APIError("Vídeo no encontrado.", status_code=404)
    return f


def _job_de(queue: JobQueue, job_id: str | None):
    if not job_id:
        return None
    return next((j for j in queue.get_all() if j.id == job_id), None)


def _vista(ficha: dict, queue: JobQueue, *, detalle: bool = False) -> dict:
    """Ficha + progreso real del trabajo (texto de la fase que emite el cortador)."""
    # Si el trabajo murió sin avisar (reinicio, cancelado), devolvemos créditos.
    if ficha["estado"] == "cola":
        job = _job_de(queue, ficha.get("job_id"))
        if job is None or job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
            ficha = svc.cargar_ficha(ficha["id"]) or ficha
            if ficha["estado"] == "cola":
                ficha["estado"] = "listo" if svc.ruta_resultado(ficha["id"]).exists() else "error"
                ficha["error"] = ficha.get("error") or "El trabajo se interrumpió. Se han devuelto tus créditos."
                svc.guardar_ficha(ficha)
                if ficha["estado"] == "error":
                    svc.devolver_creditos(ficha)
    job = _job_de(queue, ficha.get("job_id"))
    v = {
        "id": ficha["id"], "nombre": ficha["nombre"], "estado": ficha["estado"],
        "duracion_s": ficha["duracion_s"], "duracion_final_s": ficha.get("duracion_final_s"),
        "creditos": ficha["creditos"], "creado": ficha["creado"], "error": ficha.get("error"),
        "ajustes": ficha.get("ajustes"), "version": ficha.get("version", 0),
        "aviso": ficha.get("aviso"), "resumen": svc.resumen(ficha),
        "fecha": svc.fecha_iso(ficha["creado"]), "nota": ficha.get("nota"),
        "progreso": None,
    }
    if ficha["estado"] == "cola" and job is not None:
        pos = queue.posiciones_pendientes().get(job.id) if job.status == JobStatus.PENDING else None
        v["progreso"] = {
            "fraccion": round(float(job.progress or 0.0), 3),
            "fase": job.progress_label or "En espera",
            "en_cola": job.status == JobStatus.PENDING,
            "puesto": pos,
            "eta_s": job.eta_s,
            "transcurrido_s": round(job.elapsed_s, 1),
        }
    if detalle and ficha["estado"] == "listo":
        v["cortes"] = [
            {**c, "devuelto": c["id"] in set(ficha.get("devueltos") or [])}
            for c in svc.leer_cortes(ficha["id"])
        ]
    return v


@router.get("/saldo")
def saldo(claims: Claims) -> dict:
    s = svc.saldo(claims.email)
    return {
        "creditos": int(s["creditos"]), "gratis_dados": int(s.get("gratis_dados", 0)),
        "nivel": _nivel(claims), "ilimitado": _es_admin(claims),
    }


@router.get("/opciones")
def opciones(claims: Claims) -> dict:
    """Estilos de subtítulos, colores, fuentes, flechas y posiciones que ofrece la web."""
    return svc.opciones(router.prefix)


@router.get("/flechas/{fid}.png")
def flecha_png(fid: str):
    """Imagen de una flecha (público, sin ticket: va en un <img>)."""
    png = svc.png_flecha(fid) if re.fullmatch(r"[A-Za-z0-9_-]+", fid) else None
    if png is None:
        raise APIError("Flecha no encontrada.", status_code=404)
    return FileResponse(png, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@router.get("/videos")
def listar(claims: Claims, queue: Annotated[JobQueue, Depends(get_queue)]) -> dict:
    return {"videos": [_vista(f, queue) for f in svc.listar_fichas(claims.email) if f.get("estado") != "subiendo"]}


@router.post("/videos", status_code=status.HTTP_201_CREATED)
async def subir(claims: Claims, file: Annotated[UploadFile, File(...)]) -> dict:
    """Sube el vídeo (multipart, por trozos a disco). No cobra: eso es «Cortar»."""
    nombre = (file.filename or "video.mp4")
    m = re.search(r"\.[A-Za-z0-9]+$", nombre)
    ext = m.group(0).lower() if m else ""
    if ext not in _EXTS:
        raise ValidationError(f"Formato no soportado. Acepta: {', '.join(sorted(_EXTS))}.")
    ficha_prov = svc.nueva_ficha(claims.email, nombre[:120], 0.0, 0)
    vid = ficha_prov["id"]
    destino = svc.carpeta(vid) / f"original{ext}"
    total = 0
    try:
        with open(destino, "wb") as out:
            while True:
                trozo = await file.read(_CHUNK)
                if not trozo:
                    break
                total += len(trozo)
                if total > svc.MAX_BYTES:
                    raise ValidationError(f"El vídeo pesa más de {svc.MAX_BYTES // 1024 // 1024} MB.")
                out.write(trozo)
        dur = svc.duracion_video(destino)
        if total == 0 or dur <= 0:
            raise ValidationError("No se puede leer el vídeo. Prueba con otro archivo.")
        if dur > svc.MAX_MINUTOS * 60:
            raise ValidationError(f"Máximo {svc.MAX_MINUTOS} minutos por vídeo.")
    except Exception:
        svc.borrar_ficha(ficha_prov)
        raise
    ficha_prov["duracion_s"] = round(dur, 2)
    ficha_prov["bytes"] = total
    ficha_prov["creditos"] = svc.creditos_de(dur)
    svc.guardar_ficha(ficha_prov)
    svc.indexar(vid)
    svc.registrar_evento(vid, claims.email, "subido", {
        "nombre": nombre[:120], "duracion_s": ficha_prov["duracion_s"], "bytes": total,
        "creditos": ficha_prov["creditos"], "via": "multipart"})
    return {
        "id": vid, "duracion_s": ficha_prov["duracion_s"], "creditos": ficha_prov["creditos"],
        "saldo": int(svc.saldo(claims.email)["creditos"]),
    }


# --- Subida reanudable por trozos (móvil: pantalla que se bloquea, red que cae) ---

class NuevaSubida(BaseModel):
    nombre: str = Field(..., max_length=200)
    bytes: int = Field(..., gt=0)


def _subida_o_404(vid: str, email: str) -> dict:
    f = _ficha_o_404(vid, email)
    if f.get("estado") != "subiendo":
        raise APIError("Esta subida ya está cerrada.", status_code=409)
    return f


def _ruta_parcial(ficha: dict):
    return svc.carpeta(ficha["id"]) / f"original{ficha['ext']}"


@router.post("/subidas", status_code=status.HTTP_201_CREATED)
def subida_iniciar(body: NuevaSubida, claims: Claims) -> dict:
    """Abre una subida reanudable. Acepta .mov/HEVC de iPhone tal cual."""
    m = re.search(r"\.[A-Za-z0-9]+$", body.nombre)
    ext = m.group(0).lower() if m else ""
    if ext not in _EXTS:
        raise ValidationError(f"Formato no soportado. Acepta: {', '.join(sorted(_EXTS))}.")
    if body.bytes > svc.MAX_BYTES:
        raise ValidationError(f"El vídeo pesa más de {svc.MAX_BYTES // 1024 // 1024} MB.")
    f = svc.nueva_ficha(claims.email, body.nombre[:120], 0.0, 0)
    f.update(estado="subiendo", ext=ext, total=body.bytes)
    svc.guardar_ficha(f)
    _ruta_parcial(f).write_bytes(b"")
    return {"id": f["id"], "recibidos": 0, "trozo_recomendado": 4 * _CHUNK}


@router.get("/subidas/{vid}")
def subida_estado(vid: str, claims: Claims) -> dict:
    f = _subida_o_404(vid, claims.email)
    return {"recibidos": _ruta_parcial(f).stat().st_size, "total": f["total"]}


@router.put("/subidas/{vid}")
async def subida_trozo(vid: str, request: Request, claims: Claims, offset: Annotated[int, Query(ge=0)]) -> dict:
    """Añade un trozo en `offset`. Si no coincide con lo recibido, 409 + lo que hay (el cliente retoma)."""
    f = _subida_o_404(vid, claims.email)
    ruta = _ruta_parcial(f)
    tengo = ruta.stat().st_size
    if offset != tengo:
        raise APIError("Desfase en la subida.", status_code=409, details={"recibidos": tengo})
    with open(ruta, "ab") as out:
        async for trozo in request.stream():
            if tengo + len(trozo) > f["total"]:
                raise ValidationError("Llegan más bytes de los anunciados.")
            out.write(trozo)
            tengo += len(trozo)
    return {"recibidos": tengo, "total": f["total"]}


@router.post("/subidas/{vid}/fin")
def subida_fin(vid: str, claims: Claims) -> dict:
    f = _subida_o_404(vid, claims.email)
    ruta = _ruta_parcial(f)
    tam = ruta.stat().st_size
    if tam != f["total"]:
        raise APIError("Faltan bytes por subir.", status_code=409, details={"recibidos": tam})
    dur = svc.duracion_video(ruta)
    if dur <= 0:
        svc.borrar_ficha(f)
        raise ValidationError("No se puede leer el vídeo. Prueba con otro archivo.")
    if dur > svc.MAX_MINUTOS * 60:
        svc.borrar_ficha(f)
        raise ValidationError(f"Máximo {svc.MAX_MINUTOS} minutos por vídeo.")
    f.update(estado="subido", duracion_s=round(dur, 2), bytes=tam, creditos=svc.creditos_de(dur))
    svc.guardar_ficha(f)
    svc.indexar(vid)
    svc.registrar_evento(vid, claims.email, "subido", {
        "nombre": f["nombre"], "duracion_s": f["duracion_s"], "bytes": tam,
        "creditos": f["creditos"], "via": "trozos"})
    return {"id": vid, "duracion_s": f["duracion_s"], "creditos": f["creditos"],
            "saldo": int(svc.saldo(claims.email)["creditos"])}


@router.post("/videos/{vid}/cortar", status_code=status.HTTP_202_ACCEPTED)
def cortar(vid: str, ajustes: Ajustes, claims: Claims, queue: Annotated[JobQueue, Depends(get_queue)]) -> dict:
    if ajustes.ritmo not in svc.RITMOS or ajustes.formato not in svc.FORMATOS or ajustes.idioma not in svc.IDIOMAS:
        raise ValidationError("Ajustes no válidos.", details=ajustes.model_dump())
    sub, fl = _validar_estilo(ajustes.subtitulos, ajustes.flecha)
    ficha = _ficha_o_404(vid, claims.email)
    if ficha["estado"] not in ("subido", "error"):
        raise APIError("Este vídeo ya se ha cortado o está en marcha.", status_code=409)
    admin = _es_admin(claims)  # el admin no gasta créditos
    if not admin and not svc.cobrar(claims.email, int(ficha["creditos"])):
        raise APIError(
            f"Necesitas {ficha['creditos']} crédito(s) y no te alcanzan.", status_code=402,
            details={"necesarios": ficha["creditos"], "saldo": int(svc.saldo(claims.email)["creditos"])},
        )
    ficha.update(ajustes={**ajustes.model_dump(), "subtitulos": sub, "flecha": fl}, aviso=None, cobrado=not admin, devuelto=False, error=None, estado="cola")
    job = queue.enqueue(
        JobMode.EDITOR_RAPIDO, title=f"Rápido · {ficha['nombre'][:40]}",
        params={"video_id": vid, "modo": "auto", "user_name": claims.email},
        enqueued_by=claims.email,
    )
    ficha["job_id"] = job.id
    _optout(ficha, claims)
    ficha["cobrado_fecha"] = svc.contar_uso(claims.email, int(ficha["creditos"]) if not admin else 0, ficha["duracion_s"])
    svc.guardar_ficha(ficha)
    svc.registrar_evento(vid, claims.email, "cortar", {
        "ajustes": ficha["ajustes"], "creditos": int(ficha["creditos"]) if not admin else 0,
        "duracion_s": ficha["duracion_s"]})
    return {"ok": True, "job_id": job.id, "saldo": int(svc.saldo(claims.email)["creditos"])}


@router.get("/videos/{vid}")
def estado(vid: str, claims: Claims, queue: Annotated[JobQueue, Depends(get_queue)]) -> dict:
    return _vista(_ficha_o_404(vid, claims.email), queue, detalle=True)


@router.post("/videos/{vid}/retocar", status_code=status.HTTP_202_ACCEPTED)
def retocar(vid: str, body: Retoque, claims: Claims, queue: Annotated[JobQueue, Depends(get_queue)]) -> dict:
    """Devuelve al vídeo los cortes indicados y vuelve a renderizar (sin coste en V1).

    `devueltos` es la lista COMPLETA de cortes devueltos (no incremental); vacía =
    volver al corte automático. Ids = los de `cortes` en el estado del vídeo.
    """
    ficha = _ficha_o_404(vid, claims.email)
    if ficha["estado"] != "listo":
        raise APIError("El vídeo aún no está listo para retocar.", status_code=409)
    validos = {c["id"] for c in svc.leer_cortes(vid)}
    pedidos = set(body.devueltos)
    if not pedidos <= validos:
        raise ValidationError("Hay cortes que no existen.", details={"desconocidos": sorted(pedidos - validos)})
    if pedidos == set(ficha.get("devueltos") or []):
        raise APIError("No hay cambios que aplicar.", status_code=409)
    job = queue.enqueue(
        JobMode.EDITOR_RAPIDO, title=f"Rápido (retoque) · {ficha['nombre'][:40]}",
        params={"video_id": vid, "modo": "retoque", "devueltos": sorted(pedidos), "user_name": claims.email},
        enqueued_by=claims.email,
    )
    previos = set(ficha.get("devueltos") or [])
    ficha.update(estado="cola", job_id=job.id, error=None)
    _optout(ficha, claims)
    svc.guardar_ficha(ficha)
    svc.registrar_evento(vid, claims.email, "retocar", {
        "devueltos": sorted(pedidos), "nuevos_devueltos": sorted(pedidos - previos),
        "re_aplicados": sorted(previos - pedidos), "n_cortes": len(validos)})
    return {"ok": True, "job_id": job.id}


@router.post("/videos/{vid}/estilo", status_code=status.HTTP_202_ACCEPTED)
def cambiar_estilo(vid: str, body: Estilo, claims: Claims, queue: Annotated[JobQueue, Depends(get_queue)]) -> dict:
    """Cambia subtítulos y/o flecha de un vídeo ya cortado, SIN volver a cortar y gratis."""
    if body.subtitulos is None and body.flecha is None:
        raise ValidationError("Indica subtitulos y/o flecha.")
    sub, fl = _validar_estilo(body.subtitulos, body.flecha)
    ficha = _ficha_o_404(vid, claims.email)
    if ficha["estado"] == "cola":
        raise APIError("El vídeo está en marcha; espera a que termine.", status_code=409)
    if ficha["estado"] != "listo":
        raise APIError("El vídeo aún no está cortado.", status_code=409)
    aj = dict(ficha.get("ajustes") or {})
    if sub is not None:
        aj["subtitulos"] = sub
    if fl is not None:
        aj["flecha"] = fl
    job = queue.enqueue(
        JobMode.EDITOR_RAPIDO, title=f"Rápido (estilo) · {ficha['nombre'][:40]}",
        params={"video_id": vid, "modo": "estilo", "user_name": claims.email},
        enqueued_by=claims.email,
    )
    ficha.update(ajustes=aj, estado="cola", job_id=job.id, error=None, aviso=None)
    svc.guardar_ficha(ficha)
    svc.registrar_evento(vid, claims.email, "estilo", {"subtitulos": sub, "flecha": fl})
    return {"ok": True, "job_id": job.id}


@router.post("/videos/{vid}/valorar")
def valorar(vid: str, body: Valoracion, claims: Claims) -> dict:
    """«¿Qué tal el corte?»: `nota` 1-5 (o «bien»/«mal») y comentario opcional. Se puede repetir (gana la última)."""
    nota = svc.nota_valor(body.nota)
    if nota is None:
        raise ValidationError("La nota debe ser 1-5, «bien» o «mal».")
    ficha = _ficha_o_404(vid, claims.email)
    if ficha["estado"] != "listo":
        raise APIError("El vídeo aún no está listo para valorar.", status_code=409)
    ficha.update(nota=nota, comentario=(body.comentario or "").strip() or None, valorado=time.time())
    _optout(ficha, claims)
    svc.guardar_ficha(ficha)
    svc.registrar_evento(vid, claims.email, "valoracion", {"nota": nota, "comentario": ficha["comentario"]})
    svc.guardar_dataset(ficha)
    return {"ok": True, "nota": nota, "voto": "bien" if nota >= 4 else "mal" if nota <= 2 else "regular"}


@router.get("/historial")
def historial(claims: Claims) -> dict:
    """Días con actividad de los últimos 30 (más reciente primero) y créditos gastados en total."""
    return svc.historial(claims.email, 30)


@router.get("/videos/{vid}/archivo")
def archivo(
    vid: str, claims: Claims,
    tipo: Annotated[str, Query(pattern="^(resultado|original|poster)$")] = "resultado",
    descargar: bool = False,
):
    ficha = _ficha_o_404(vid, claims.email)
    if tipo == "poster":
        p = svc.poster(vid)
        if p is None:
            raise APIError("Todavía no hay póster.", status_code=404)
        return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})
    ruta = svc.ruta_resultado(vid) if tipo == "resultado" else svc.ruta_original(vid)
    if ruta is None or not ruta.exists():
        raise APIError("Todavía no hay archivo.", status_code=404)
    if tipo == "resultado" and descargar:
        sin_retocar = not (ficha.get("devueltos") or [])
        ficha["descargas"] = int(ficha.get("descargas", 0)) + 1
        if sin_retocar:
            ficha["descarga_sin_retocar"] = True
        _optout(ficha, claims)
        svc.guardar_ficha(ficha)
        svc.registrar_evento(vid, claims.email, "descarga", {
            "version": ficha.get("version", 0), "sin_retocar": sin_retocar})
        svc.guardar_dataset(ficha)
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", ficha["nombre"].rsplit(".", 1)[0]) or "video"
    return FileResponse(
        ruta, media_type="video/mp4" if tipo == "resultado" else None,
        filename=f"{base}_cortado.mp4" if descargar else None,
        content_disposition_type="attachment" if descargar else "inline",
    )


@router.delete("/videos/{vid}")
def borrar(vid: str, claims: Claims) -> dict:
    ficha = _ficha_o_404(vid, claims.email)
    if ficha["estado"] == "cola":
        raise APIError("Espera a que termine el corte.", status_code=409)
    svc.registrar_evento(vid, claims.email, "borrado", {"estado": ficha["estado"]})
    svc.guardar_dataset(ficha)  # el original se conserva (hardlink) salvo opt-out
    svc.borrar_ficha(ficha)
    return {"ok": True}


@router.post("/admin/creditos", dependencies=[Depends(get_current_user)])
def admin_creditos(body: AjusteCreditos) -> dict:
    """Regalar/quitar créditos a mano (VIP, soporte). Requiere X-API-Key."""
    email = body.email.strip().lower()
    if not email or "@" not in email:
        raise ValidationError("Email no válido.")
    svc.saldo(email)
    return {"email": email, "creditos": svc.ajustar_creditos(email, body.delta)}


@router.get("/admin/cuentas")
def admin_cuentas(claims: Claims) -> dict:
    """Cuentas con saldo y nº de vídeos (solo rol admin del ticket)."""
    _admin_o_403(claims)
    return {"cuentas": svc.listar_cuentas()}


@router.post("/admin/dar")
def admin_dar(body: DarCreditos, claims: Claims) -> dict:
    """Suma (o resta, con negativo) créditos a una cuenta (solo rol admin del ticket)."""
    _admin_o_403(claims)
    email = body.email.strip().lower()
    if not email or "@" not in email:
        raise ValidationError("Email no válido.")
    svc.saldo(email)
    return {"email": email, "creditos": svc.ajustar_creditos(email, body.creditos)}


@router.get("/admin/actividad")
def admin_actividad(claims: Claims, dias: Annotated[int, Query(ge=1, le=90)] = 7) -> dict:
    """Uso por día (con ceros) y los últimos 100 vídeos con su puntuación (solo rol admin)."""
    _admin_o_403(claims)
    return svc.actividad(dias, 100)


@router.get("/admin/videos/{vid}")
def admin_video(vid: str, claims: Claims) -> dict:
    """Ficha completa + eventos + calidad + enlaces a original y resultado (añade `?t=<ticket>`)."""
    _admin_o_403(claims)
    f = svc.cargar_ficha(vid)
    if f is None:
        raise APIError("Vídeo no encontrado.", status_code=404)
    n = f.get("n_cortes")
    ficha = {**f, "fecha": svc.fecha_iso(f.get("creado", 0)), "calidad": svc.calidad(f),
             "n_cortes": n if n is not None else (len(svc.leer_cortes(vid)) if f.get("estado") == "listo" else None)}
    base = f"{router.prefix}/admin/videos/{vid}/archivo"
    return {
        "ficha": ficha, "eventos": svc.leer_eventos(vid),
        "cortes": svc.leer_cortes(vid) if f.get("estado") == "listo" else [],
        "original_url": f"{base}?tipo=original", "resultado_url": f"{base}?tipo=resultado",
    }


@router.get("/admin/videos/{vid}/archivo")
def admin_video_archivo(
    vid: str, claims: Claims,
    tipo: Annotated[str, Query(pattern="^(resultado|original)$")] = "resultado",
):
    """Original o resultado de cualquier usuario (ticket admin en cabecera o `?t=`)."""
    _admin_o_403(claims)
    if svc.cargar_ficha(vid) is None:
        raise APIError("Vídeo no encontrado.", status_code=404)
    ruta = svc.ruta_resultado(vid) if tipo == "resultado" else svc.ruta_original(vid)
    if ruta is None or not ruta.exists():
        raise APIError("Todavía no hay archivo.", status_code=404)
    return FileResponse(ruta, media_type="video/mp4" if tipo == "resultado" else None)
