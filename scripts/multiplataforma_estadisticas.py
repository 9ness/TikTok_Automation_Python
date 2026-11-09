"""Estadísticas semanales de las cuentas de Meta (IG, FB, Threads), solo lectura.

Corre DENTRO del contenedor api (`scripts/multiplataforma_estadisticas.sh` lo
copia y guarda la salida) y escribe un JSON por stdout. Nunca imprime tokens: un
error de la API se guarda solo como código y mensaje, sin la URL.

Una métrica que Meta no devuelva queda en `None`, no en 0: así el informe
distingue «sin dato» de «nadie lo ha visto».
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import sys
import time
from zoneinfo import ZoneInfo

import httpx

from src.multiplataforma import config
from src.multiplataforma.repos import cuentas_repo, publicaciones_repo

try:  # el script se copia al contenedor: puede ir por delante del despliegue
    from src.multiplataforma.services import enlace_corto
except ImportError:  # pragma: no cover
    enlace_corto = None
try:
    from src.multiplataforma.services import embudo
except ImportError:  # pragma: no cover
    embudo = None

ZONA = ZoneInfo(config.ZONA_HORARIA)
CUENTAS = ("viva_shop", "viva_salud", "ama_shop")
IG_MEDIA = ("views", "reach", "likes", "comments", "shares", "saved")
TH_MEDIA = ("views", "likes", "replies", "reposts", "quotes", "shares")
IG_CUENTA = ("reach", "views", "profile_views", "accounts_engaged", "total_interactions")
TH_CUENTA = ("views", "likes", "replies", "reposts", "quotes")
FB_CUENTA = ("page_media_view", "page_post_engagements", "page_follows")
FB_VIDEO = ("fb_reels_total_plays", "post_video_avg_time_watched", "post_video_followers")


def leer(url: str, token: str, errores: list[str], etiqueta: str, **params) -> dict:
    """GET a la API; ante cualquier fallo anota la etiqueta y devuelve {}."""
    try:
        r = httpx.get(url, params={**params, "access_token": token}, timeout=30)
        datos = r.json()
    except (httpx.HTTPError, ValueError) as e:
        errores.append(f"{etiqueta}: {type(e).__name__}")
        return {}
    if r.status_code != 200:
        err = datos.get("error", {}) if isinstance(datos, dict) else {}
        errores.append(f"{etiqueta}: HTTP {r.status_code} ({err.get('code')}) {str(err.get('message'))[:120]}")
        return {}
    return datos


def valor(item: dict):
    """Lee `total_value` o suma `values` de una métrica; None si no trae nada."""
    total = item.get("total_value")
    if isinstance(total, dict) and "value" in total:
        return total["value"]
    nums = [v.get("value") for v in item.get("values") or [] if isinstance(v.get("value"), (int, float))]
    return sum(nums) if nums else None


def metricas(datos: dict, nombres: tuple[str, ...]) -> dict:
    leidas = {d.get("name"): valor(d) for d in datos.get("data") or []}
    return {n: leidas.get(n) for n in nombres}


def instagram(c, desde: int, hasta: int, errores: list[str]) -> dict:
    base, tok = f"{config.graph_base()}/{c.ig_user_id}", c.token("instagram")
    perfil = leer(base, tok, errores, "ig perfil", fields="username,followers_count,media_count")
    datos = leer(f"{base}/insights", tok, errores, "ig cuenta", metric=",".join(IG_CUENTA), period="day",
                 metric_type="total_value", since=desde, until=hasta)
    return {"usuario": perfil.get("username"), "seguidores": perfil.get("followers_count"),
            "publicaciones": perfil.get("media_count"), **metricas(datos, IG_CUENTA)}


def facebook(c, desde: int, hasta: int, errores: list[str]) -> dict:
    base, tok = f"{config.graph_base()}/{c.fb_page_id}", c.token("facebook")
    perfil = leer(base, tok, errores, "fb perfil", fields="name,followers_count")
    datos = leer(f"{base}/insights", tok, errores, "fb cuenta", metric=",".join(FB_CUENTA), period="day",
                 since=desde, until=hasta)
    return {"usuario": perfil.get("name"), "seguidores": perfil.get("followers_count"), **metricas(datos, FB_CUENTA)}


def threads(c, desde: int, hasta: int, errores: list[str]) -> dict:
    base, tok = f"{config.threads_base()}/{c.threads_user_id}", c.token("threads")
    perfil = leer(base, tok, errores, "th perfil", fields="username")
    datos = leer(f"{base}/threads_insights", tok, errores, "th cuenta", metric=",".join(TH_CUENTA),
                 since=desde, until=hasta)
    # followers_count no admite since/until: va en su propia llamada.
    seg = leer(f"{base}/threads_insights", tok, errores, "th seguidores", metric="followers_count")
    return {"usuario": perfil.get("username"), "seguidores": metricas(seg, ("followers_count",))["followers_count"],
            **metricas(datos, TH_CUENTA)}


def medir_publicacion(p, c, errores: list[str]) -> dict:
    """Lo que lleva cada publicación en cada plataforma donde salió."""
    cuando = dt.datetime.fromtimestamp(p.programada_en, ZONA)
    out: dict = {"id": p.id[:8], "pid": p.id, "tipo": p.tipo, "titulo": (p.titulo or "")[:70],
                 "fecha": cuando.strftime("%Y-%m-%d"), "hora": cuando.strftime("%H:%M"),
                 "ts": int(p.programada_en), "origen": p.origen or "", "producto_ref": p.producto_ref or ""}
    res = p.resultados or {}
    ig = (res.get("instagram") or {}).get("media_id")
    if ig and p.estado.get("instagram") == config.ESTADO_PUBLICADO:
        datos = leer(f"{config.graph_base()}/{ig}/insights", c.token("instagram"), errores, f"ig {p.id[:8]}",
                     metric=",".join(IG_MEDIA))
        out["instagram"] = metricas(datos, IG_MEDIA)
    fb = (res.get("facebook") or {}).get("video_id")
    if fb and p.estado.get("facebook") == config.ESTADO_PUBLICADO:
        datos = leer(f"{config.graph_base()}/{fb}/video_insights", c.token("facebook"), errores, f"fb {p.id[:8]}")
        out["facebook"] = metricas(datos, FB_VIDEO)
    th = (res.get("threads") or {}).get("post_id")
    if th and p.estado.get("threads") == config.ESTADO_PUBLICADO:
        datos = leer(f"{config.threads_base()}/{th}/insights", c.token("threads"), errores, f"th {p.id[:8]}",
                     metric=",".join(TH_MEDIA))
        out["threads"] = metricas(datos, TH_MEDIA)
    clics = enlace_corto.clics(p.id) if enlace_corto else {}
    if clics:
        out["clics"] = clics  # {red: n} del enlace corto (#296), acumulados
    return out


def resumen_por_tipo(medidas: list[dict]) -> dict:
    """Publicaciones y vistas medias por tipo y plataforma."""
    campos = {"instagram": "views", "facebook": "fb_reels_total_plays", "threads": "views"}
    grupos: dict = collections.defaultdict(lambda: collections.defaultdict(list))
    for m in medidas:
        for plataforma, campo in campos.items():
            v = (m.get(plataforma) or {}).get(campo)
            if v is not None:
                grupos[m["tipo"]][plataforma].append(v)
    return {tipo: {pl: {"n": len(vs), "media": round(sum(vs) / len(vs), 1), "max": max(vs)} for pl, vs in por.items()}
            for tipo, por in grupos.items()}


def salud(pubs: list) -> dict:
    """Cómo fue la publicación: estados por plataforma y comentarios de FB fallidos."""
    estados: collections.Counter = collections.Counter()
    comentarios_fallidos = 0
    for p in pubs:
        for plataforma, estado in (p.estado or {}).items():
            estados[f"{plataforma}:{estado}"] += 1
        if (p.resultados.get("facebook") or {}).get("comentario_error"):
            comentarios_fallidos += 1
    return {"estados": dict(sorted(estados.items())), "comentarios_fb_fallidos": comentarios_fallidos}


def cuenta(slug: str, todas: list, desde: int, hasta: int) -> dict:
    c = cuentas_repo.get(slug)
    if c is None:
        return {"error": "cuenta no encontrada"}
    errores: list[str] = []
    pubs = [p for p in todas if p.cuenta == slug and desde <= (p.programada_en or 0) < hasta]
    medidas = [medir_publicacion(p, c, errores) for p in sorted(pubs, key=lambda p: p.programada_en)]
    cola = [p for p in todas if p.cuenta == slug and (p.programada_en or 0) >= hasta]
    return {
        "instagram": instagram(c, desde, hasta, errores),
        "facebook": facebook(c, desde, hasta, errores),
        "threads": threads(c, desde, hasta, errores),
        "por_tipo": resumen_por_tipo(medidas),
        "publicaciones": medidas,
        "salud": salud(pubs),
        "en_cola": len(cola),
        # Página de la bio: visitas y clics por producto (solo contadores).
        "embudo": embudo.resumen(slug, desde, hasta) if embudo else None,
        "errores": errores,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=7)
    args = ap.parse_args()
    hasta = int(time.time())
    desde = hasta - args.dias * 86400
    todas = publicaciones_repo.todas(5000)
    informe = {
        "generado": dt.datetime.now(ZONA).isoformat(timespec="minutes"),
        "dias": args.dias,
        "cuentas": {slug: cuenta(slug, todas, desde, hasta) for slug in CUENTAS},
    }
    json.dump(informe, sys.stdout, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
