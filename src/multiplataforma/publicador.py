"""Publicador: coge las publicaciones vencidas y las sube a cada plataforma.

Lo llama un timer/cron cada X horas (`scripts/multiplataforma_tick.py`). Reglas:
- Idempotente: una plataforma `publicado` o `fallido` no se vuelve a tocar, y
  los ids intermedios (contenedor de IG/Threads, video_id de FB, media_id de
  Pinterest) se guardan para que un reintento no cree duplicados.
- Límite de 24h móviles por cuenta y plataforma (`config.LIMITES_24H`): si se
  alcanza, esa plataforma espera al siguiente tick.
- Sin token o sin id de destino → MODO PRUEBA para esa plataforma: se anota
  qué se haría (estado `simulado`) y se vuelve a intentar de verdad cuando la
  cuenta tenga token.
- `dry_run=True` (o `MULTIPLATAFORMA_DRY_RUN=1`) simula TODO y no guarda nada:
  sirve para ver el plan sin tocar la cola.

No hay cerrojo entre procesos: se asume un único timer.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import httpx

from src.multiplataforma import config
from src.multiplataforma.clients.base import ClienteBase, ErrorPublicacion
from src.multiplataforma.clients.facebook import FacebookClient
from src.multiplataforma.clients.instagram import InstagramClient
from src.multiplataforma.clients.pinterest import PinterestClient
from src.multiplataforma.clients.threads import ThreadsClient
from src.multiplataforma.models import CuentaDestino, Publicacion
from src.multiplataforma.repos import cuentas_repo, publicaciones_repo
from src.multiplataforma.services import ingesta, tandas, video_url


def _noop(_: str) -> None:
    return None


def _ejecutar(plataforma: str, pub: Publicacion, cuenta: CuentaDestino, *, dry_run: bool,
              http: httpx.Client | None, sleep: Callable[[float], None]) -> dict:
    """Publica `pub` en una plataforma. Lanza `ErrorPublicacion` si falla."""
    token = "" if dry_run else cuenta.token(plataforma)
    kw = {"dry_run": dry_run, "http": http, "sleep": sleep}
    previo = {k: v for k, v in (pub.resultados.get(plataforma) or {}).items() if k != "pasos"}
    destino = cuenta.destino(plataforma) or f"<sin {plataforma}_id>"
    texto = pub.textos.get(plataforma, "")
    simulado = dry_run or not token

    if pub.tipo == "carrusel":
        return _ejecutar_carrusel(plataforma, pub, token, destino, texto, simulado, kw, previo)

    if not simulado and not pub.video_path.startswith(("http://", "https://")):
        ClienteBase._fichero(pub.video_path)  # error claro y no reintentable si no está

    if plataforma == "instagram":
        url = video_url.url_publica(pub.video_path)
        return InstagramClient(token, **kw).publicar(
            destino, caption=texto, video_url=url, cover_url=pub.cover_url,
            trial=pub.tipo == "prueba_viral" and config.IG_TRIAL_REELS, graduacion=pub.trial_graduation, previo=previo,
        )
    if plataforma == "facebook":
        return FacebookClient(token, **kw).publicar(
            destino, descripcion=texto, video_path=pub.video_path, comentario=pub.comentario, previo=previo,
        )
    if plataforma == "threads":
        return ThreadsClient(token, **kw).publicar(
            destino, texto=texto, video_url=video_url.url_publica(pub.video_path), previo=previo,
        )
    if plataforma == "pinterest":
        return PinterestClient(token, **kw).publicar(
            destino, titulo=pub.titulo or texto[:100], descripcion=texto, enlace=pub.enlace,
            video_path=pub.video_path, cover_url=pub.cover_url, previo=previo,
        )
    raise ErrorPublicacion(f"Plataforma desconocida: {plataforma}", reintentable=False)


def _ejecutar_carrusel(plataforma: str, pub: Publicacion, token: str, destino: str, texto: str,
                       simulado: bool, kw: dict, previo: dict) -> dict:
    """Carrusel de fotos (`pub.imagenes`; IG usa `pub.imagenes_ig`, en 4:5)."""
    fotos = (pub.imagenes_ig or pub.imagenes) if plataforma == "instagram" else pub.imagenes
    if not fotos:
        raise ErrorPublicacion("carrusel sin fotos", reintentable=False)
    if not simulado:
        for f in fotos:
            if not f.startswith(("http://", "https://")) and not Path(f).is_file():
                raise ErrorPublicacion(f"No existe la foto {f}", reintentable=False)
    urls = [video_url.url_publica(f) for f in fotos]
    if plataforma == "instagram":
        return InstagramClient(token, **kw).publicar_carrusel(destino, caption=texto, imagenes_url=urls, previo=previo)
    if plataforma == "facebook":
        return FacebookClient(token, **kw).publicar_fotos(destino, mensaje=texto, imagenes_url=urls,
                                                          comentario=pub.comentario, previo=previo)
    if plataforma == "threads":
        return ThreadsClient(token, **kw).publicar_carrusel(destino, texto=texto, imagenes_url=urls, previo=previo)
    if plataforma == "pinterest":
        return PinterestClient(token, **kw).publicar_carrusel(
            destino, titulo=pub.titulo or texto[:100], descripcion=texto, enlace=pub.enlace,
            imagenes_url=urls, previo=previo)
    raise ErrorPublicacion(f"Plataforma desconocida: {plataforma}", reintentable=False)


def publicar_una(pub: Publicacion, *, ahora: float, dry_run: bool = False, http: httpx.Client | None = None,
                 sleep: Callable[[float], None] = time.sleep, log: Callable[[str], None] = _noop) -> dict:
    """Procesa todas las plataformas pendientes de `pub`. Devuelve el informe."""
    informe: dict = {"id": pub.id, "cuenta": pub.cuenta, "plataformas": {}}
    cuenta = cuentas_repo.get(pub.cuenta)
    if not cuenta:
        informe["omitida"] = f"la cuenta {pub.cuenta!r} no existe"
        return informe
    if not cuenta.activa:
        informe["omitida"] = f"la cuenta {pub.cuenta!r} está desactivada"
        return informe

    # producto_ref sin enlace: el enlace puede haberse guardado después de
    # encolar (enlaces_repo). Se rellena y se rehacen los textos.
    if tandas.rellenar_enlace(pub):
        informe["enlace_rellenado"] = pub.enlace
        if not dry_run:
            publicaciones_repo.guardar(pub)

    for plat in pub.plataformas:
        estado = pub.estado.get(plat, config.ESTADO_PENDIENTE)
        if estado in config.ESTADOS_FINALES:
            continue
        real = not dry_run and cuenta.lista_para(plat)
        if estado == config.ESTADO_SIMULADO and not real and not dry_run:
            # ya se simuló y sigue sin token: nada nuevo que anotar
            informe["plataformas"][plat] = {"estado": estado, "nota": "sigue sin token"}
            continue
        if real:
            hechos = publicaciones_repo.envios_24h(cuenta.slug, plat, ahora)
            if hechos >= config.LIMITES_24H[plat]:
                informe["plataformas"][plat] = {"estado": estado, "nota": f"límite 24h ({hechos})"}
                log(f"[multiplataforma] {pub.id} {plat}: límite diario alcanzado")
                continue
        try:
            res = _ejecutar(plat, pub, cuenta, dry_run=not real, http=http, sleep=sleep)
        except ErrorPublicacion as e:
            n = pub.intentos.get(plat, 0) + 1
            pub.intentos[plat] = n
            pub.errores[plat] = str(e)
            pub.resultados[plat] = {**(pub.resultados.get(plat) or {}), **e.parcial}
            final = not e.reintentable or n >= config.MAX_INTENTOS
            pub.estado[plat] = config.ESTADO_FALLIDO if final else config.ESTADO_ERROR
            informe["plataformas"][plat] = {"estado": pub.estado[plat], "error": str(e)}
            log(f"[multiplataforma] {pub.id} {plat}: {e}")
        else:
            if real:
                pub.estado[plat] = config.ESTADO_PUBLICADO
                pub.errores.pop(plat, None)
                publicaciones_repo.registrar_envio(cuenta.slug, plat, ahora)
                res.pop("pasos", None)
                res["publicado_en"] = ahora
            else:
                pub.estado[plat] = config.ESTADO_SIMULADO
                res["simulado_en"] = ahora
            pub.resultados[plat] = res
            informe["plataformas"][plat] = {"estado": pub.estado[plat], **res}
            log(f"[multiplataforma] {pub.id} {plat}: {pub.estado[plat]}")
        if not dry_run:
            publicaciones_repo.guardar(pub)  # tras cada plataforma: no perder ids si se cae
    informe["terminada"] = pub.terminada
    if not dry_run and pub.origen == ingesta.ORIGEN and pub.plataformas and all(
            pub.estado.get(p) == config.ESTADO_PUBLICADO for p in pub.plataformas):
        nueva = ingesta.mover_a_publicados(pub, log)
        if nueva:
            pub.video_path = nueva
            publicaciones_repo.guardar(pub)
            informe["movido_a"] = nueva
    return informe


def publicar_pendientes(ahora: float | None = None, limite: int = 10, *, dry_run: bool | None = None,
                        http: httpx.Client | None = None, sleep: Callable[[float], None] = time.sleep,
                        log: Callable[[str], None] = _noop) -> dict:
    """Un tick: hasta `limite` publicaciones vencidas, por orden de `programada_en`."""
    ahora = time.time() if ahora is None else ahora
    dry = config.dry_run_global() if dry_run is None else dry_run
    vencidas = publicaciones_repo.vencidas(ahora)[: max(0, limite)]
    informes = []
    for pub in vencidas:
        try:
            informes.append(publicar_una(pub, ahora=ahora, dry_run=dry, http=http, sleep=sleep, log=log))
        except Exception as e:  # noqa: BLE001 — una publicación rota no para el tick
            informes.append({"id": pub.id, "error": f"{type(e).__name__}: {e}"})
            log(f"[multiplataforma] {pub.id}: error inesperado {e}")
    return {"ahora": ahora, "dry_run": dry, "procesadas": len(informes), "publicaciones": informes}
