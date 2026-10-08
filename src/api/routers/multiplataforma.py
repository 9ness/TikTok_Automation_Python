"""Publicador Multiplataforma: cuentas de destino, cola y vídeo firmado.

Publica los vídeos ya montados en IG Reels, FB Reels, Threads y Pinterest
(ver `src/multiplataforma/` y MULTIPLATAFORMA_MODULE.md). Los tokens se
escriben aquí pero NUNCA se devuelven.

Dos routers: `router` (con API key) y `router_publico` (solo el vídeo
firmado, que lo descargan Meta/Threads sin cabeceras).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.api.dependencies import get_current_user, get_web_user
from src.api.exceptions import APIError
from src.multiplataforma import config, publicador
from src.multiplataforma.models import CuentaDestino, Publicacion
from src.multiplataforma.repos import cuentas_repo, publicaciones_repo
from src.multiplataforma.services import enlaces, ingesta, textos, video_url

router = APIRouter(
    prefix="/api/v1/multiplataforma",
    tags=["multiplataforma"],
    dependencies=[Depends(get_current_user)],
)
router_publico = APIRouter(prefix="/api/v1/multiplataforma", tags=["multiplataforma"])


class CuentaIn(BaseModel):
    slug: str
    nombre: str = ""
    dueno: str = ""
    ig_user_id: str = ""
    fb_page_id: str = ""
    threads_user_id: str = ""
    pinterest_board_id: str = ""
    afiliado_amazon_tag: str = ""
    afiliado_shein: str = ""
    activa: bool = True
    ritmo: dict[str, int] = Field(default_factory=lambda: dict(config.RITMO_DEFAULT))  # vídeos/día por tipo
    horas: dict[str, list[str]] = Field(default_factory=lambda: {k: list(v) for k, v in config.HORAS_DEFAULT.items()})


class TokensIn(BaseModel):
    """{plataforma: token}. Cadena vacía borra ese token."""

    tokens: dict[str, str]


class PublicacionIn(BaseModel):
    cuenta: str
    video_path: str
    tipo: str = "producto"
    producto_ref: str = ""
    titulo: str = ""
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)
    asin: str = ""  # Amazon: se construye el enlace con el tag de la cuenta
    enlace: str = ""  # SHEIN u otro: tal cual
    cover_url: str = ""
    plataformas: list[str] = Field(default_factory=lambda: list(config.PLATAFORMAS))
    programada_en: float | None = None
    trial_graduation: str = "MANUAL"
    textos: dict[str, str] = Field(default_factory=dict)  # override por plataforma


@router.get("/cuentas")
def listar_cuentas(dueno: Annotated[str, Query()] = "") -> dict:
    return {"cuentas": [c.publico() for c in cuentas_repo.listar(dueno or None)]}


@router.post("/cuentas")
def guardar_cuenta(body: CuentaIn, usuario: Annotated[str, Depends(get_web_user)] = "") -> dict:
    datos = body.model_dump()
    datos["dueno"] = datos["dueno"] or usuario
    malos = (set(body.ritmo) | set(body.horas)) - set(config.TIPOS)
    if malos or any(v < 0 for v in body.ritmo.values()):
        raise APIError(f"ritmo/horas: tipos no válidos {sorted(malos)} o ritmo negativo", status_code=400)
    try:
        for hs in body.horas.values():
            for h in hs:
                ingesta.horas_del_dia(1, [h])
    except ValueError as e:
        raise APIError("horas: formato «HH:MM»", status_code=400) from e
    try:
        c = cuentas_repo.guardar(CuentaDestino(**datos))
    except ValueError as e:
        raise APIError(str(e), status_code=400) from e
    carpeta = ingesta.asegurar_carpetas(c.slug)
    return {"cuenta": c.publico(), "carpeta_drive": str(carpeta)}


@router.post("/cuentas/{slug}/ingestar")
def ingestar_cuenta(slug: str) -> dict:
    """Encola los vídeos nuevos de `<Multiplataforma>/<slug>/{viralizacion,producto}/`."""
    if not cuentas_repo.get(slug):
        raise APIError(f"No existe la cuenta {slug}", status_code=404)
    return ingesta.ingestar(slug)


@router.put("/cuentas/{slug}/tokens")
def guardar_tokens(slug: str, body: TokensIn) -> dict:
    malas = set(body.tokens) - set(config.PLATAFORMAS)
    if malas:
        raise APIError(f"Plataformas desconocidas: {sorted(malas)}", status_code=400)
    try:
        c = cuentas_repo.set_tokens(slug, body.tokens)
    except KeyError as e:
        raise APIError(f"No existe la cuenta {slug}", status_code=404) from e
    return {"cuenta": c.publico()}


@router.post("/publicaciones")
def encolar(body: PublicacionIn) -> dict:
    cuenta = cuentas_repo.get(body.cuenta)
    if not cuenta:
        raise APIError(f"No existe la cuenta {body.cuenta}", status_code=404)
    if body.tipo not in config.TIPOS:
        raise APIError(f"tipo no válido: {body.tipo}", status_code=400)
    malas = set(body.plataformas) - set(config.PLATAFORMAS)
    if malas or not body.plataformas:
        raise APIError(f"Plataformas no válidas: {sorted(malas) or 'ninguna'}", status_code=400)
    if not video_url.servible(body.video_path):
        raise APIError("video_path tiene que ser .mp4 o .mov", status_code=400)
    try:
        enlace = enlaces.resolver(asin=body.asin, enlace=body.enlace, amazon_tag=cuenta.afiliado_amazon_tag)
        t = textos.construir(titulo=body.titulo, caption=body.caption, enlace=enlace,
                             hashtags=body.hashtags, plataformas=body.plataformas)
    except enlaces.EnlaceInvalido as e:
        raise APIError(str(e), status_code=400) from e
    pub = Publicacion(
        cuenta=cuenta.slug, video_path=body.video_path, tipo=body.tipo, producto_ref=body.producto_ref,
        titulo=t["titulo_pin"], textos={**t["textos"], **body.textos}, comentario=t["comentario"],
        enlace=enlace, cover_url=body.cover_url, plataformas=list(body.plataformas),
        programada_en=body.programada_en or time.time(), trial_graduation=body.trial_graduation.upper(),
    )
    pub, creada = publicaciones_repo.encolar(pub)
    return {
        "publicacion": pub.to_dict(),
        "creada": creada,
        "video_existe": Path(body.video_path).is_file(),
        "modo_prueba": [p for p in pub.plataformas if not cuenta.lista_para(p)],
    }


@router.get("/cola")
def ver_cola(todas: Annotated[bool, Query()] = False, limite: Annotated[int, Query(ge=1, le=500)] = 100) -> dict:
    pubs = publicaciones_repo.todas(limite) if todas else publicaciones_repo.pendientes()[:limite]
    return {"publicaciones": [p.to_dict() for p in pubs]}


@router.post("/tick")
def tick(dry_run: Annotated[bool, Query()] = True, limite: Annotated[int, Query(ge=1, le=50)] = 5) -> dict:
    """Lanza un tick a mano. Por defecto en modo prueba (no guarda ni publica)."""
    return publicador.publicar_pendientes(limite=limite, dry_run=dry_run)


@router_publico.get("/archivo/{token}")
def archivo_firmado(token: str) -> FileResponse:
    ruta = video_url.verificar(token)
    if not ruta:
        raise APIError("Enlace no válido o caducado", status_code=403)
    if not video_url.ruta_permitida(ruta):
        raise APIError("Ruta no permitida", status_code=403)
    p = Path(ruta)
    if not p.is_file():
        raise APIError("El fichero ya no existe", status_code=404)
    return FileResponse(p, filename=p.name)
