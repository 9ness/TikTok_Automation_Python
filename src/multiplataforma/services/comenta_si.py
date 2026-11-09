"""«Comenta SÍ» → enlace por mensaje privado en Instagram (#297).

La CTA de los reels pide «Comenta SÍ»: aquí se leen los comentarios de los
reels de IG publicados con enlace (últimos `COMENTA_SI_DIAS` días), se
detecta el «sí» y se contesta con un MENSAJE PRIVADO (Private Replies de
Meta: `POST /{ig_user_id}/messages` con `recipient.comment_id`), porque un
enlace en una respuesta pública de IG no es clicable.

- EN SECO por defecto: solo anota lo que mandaría (`comenta_si:seco:<fecha>`).
  Enviar de verdad = `MULTIPLATAFORMA_COMENTA_SI_ENVIAR=1`, que exige la app
  en Live con `instagram_manage_comments` + `instagram_manage_messages` y el
  «sí» de Néstor.
- Una sola vez por comentario y por usuario y reel (`set_nx` en Redis), y un
  tope por cuenta y hora (`COMENTA_SI_TOPE_HORA`).
- Leer comentarios sí toca la API (GET); sin permiso, el error se anota y
  sigue con el resto.
"""

from __future__ import annotations

import datetime as dt
import re
import time
import unicodedata
from typing import Callable

import httpx

from src.multiplataforma import config
from src.multiplataforma.clients.base import ClienteBase, ErrorPublicacion, _sin_token
from src.multiplataforma.models import CuentaDestino, Publicacion
from src.multiplataforma.repos import cuentas_repo, publicaciones_repo
from src.multiplataforma.repos.redis_base import get_redis
from src.multiplataforma.services import enlace_corto, enlaces, textos

_SI = re.compile(r"^(s+i+|y+e+s+|s)$")
_RELLENO = {"por", "favor", "porfa", "porfavor", "plis", "pls", "please", "quiero", "yo", "me", "interesa",
            "gracias", "info", "link", "enlace", "claro", "obvio", "porfi", "x", "xfa", "xfavor"}
MAX_REGISTRO = 500


def _normal(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9\s]", " ", t)


def es_si(texto: str) -> bool:
    """«Sí», «si!!», «SIIII 🙌», «sí porfa», «yes please»… Corto y empezando por sí."""
    palabras = _normal(texto).split()
    if not palabras or len(palabras) > config.COMENTA_SI_MAX_PALABRAS:
        return False
    if not _SI.match(palabras[0]) or palabras[0] == "s":
        return False
    return all(_SI.match(p) or p in _RELLENO for p in palabras[1:])


class _Cliente(ClienteBase):
    plataforma = "instagram"

    def __init__(self, token: str, **kw) -> None:
        super().__init__(token, **kw)
        self.base = config.graph_base()

    def comentarios(self, media_id: str, limite: int = 200) -> list[dict]:
        url = f"{self.base}/{media_id}/comments"
        params = {"fields": "id,text,username,timestamp", "limit": 50, "access_token": self.token}
        out: list[dict] = []
        while url and len(out) < limite:
            j = self._request("GET", url, params=params)
            out += j.get("data") or []
            url = ((j.get("paging") or {}).get("next") or "")
            params = None  # `next` ya trae los parámetros
        return out

    def responder_privado(self, ig_user_id: str, comment_id: str, mensaje: str) -> dict:
        return self._request("POST", f"{self.base}/{ig_user_id}/messages",
                             json={"recipient": {"comment_id": comment_id}, "message": {"text": mensaje}},
                             params={"access_token": self.token})


def mensaje(pub: Publicacion, *, guardar: bool = False) -> str:
    """Texto del mensaje privado (`prompts/comenta_si.md`); con el enlace
    corto si está encendido (red `instagram_dm`, clics aparte)."""
    enlace = enlace_corto.para_envio(pub, "instagram_dm", guardar=guardar).enlace
    aviso = textos.aviso_amazon() if enlaces.es_amazon(pub.enlace) else ""
    return textos.rellenar("comenta_si", {"enlace": enlace, "aviso_afiliado": aviso}).strip()


def candidatas(slug: str, ahora: float) -> list[Publicacion]:
    desde = ahora - config.COMENTA_SI_DIAS * 86400
    return [p for p in publicaciones_repo.de_cuenta(slug)
            if p.enlace and p.estado.get("instagram") == config.ESTADO_PUBLICADO
            and (p.resultados.get("instagram") or {}).get("media_id") and p.programada_en >= desde]


def _anotar_seco(fila: dict, ahora: float) -> None:
    r = get_redis()
    clave = f"comenta_si:seco:{dt.date.fromtimestamp(ahora).isoformat()}"
    filas = r.get_json(clave) or []
    if len(filas) < MAX_REGISTRO:
        r.set_json(clave, filas + [fila])


def procesar_cuenta(cuenta: CuentaDestino, *, ahora: float | None = None, enviar: bool | None = None,
                    http: httpx.Client | None = None, log: Callable[[str], None] = lambda _: None) -> dict:
    ahora = time.time() if ahora is None else ahora
    enviar = config.comenta_si_envia() if enviar is None else enviar
    inf: dict = {"cuenta": cuenta.slug, "modo": "envio" if enviar else "seco", "reels": 0, "comentarios": 0,
                 "si": 0, "mandados": [], "repetidos": 0, "tope": 0, "errores": []}
    token = cuenta.token("instagram")
    if not token or not cuenta.ig_user_id:
        inf["errores"].append("sin token o ig_user_id de Instagram")
        return inf
    r = get_redis()
    if enviar and not r.is_available():
        # Sin Redis no hay dedup ni tope: con envío real, no se arriesga a mandar dos veces.
        inf["errores"].append("Redis no disponible: no se manda nada")
        return inf
    cli = _Cliente(token, http=http)
    hora = dt.datetime.fromtimestamp(ahora).strftime("%Y%m%d%H")
    for pub in candidatas(cuenta.slug, ahora):
        media = pub.resultados["instagram"]["media_id"]
        inf["reels"] += 1
        try:
            coms = cli.comentarios(media)
        except ErrorPublicacion as e:
            inf["errores"].append(f"{pub.id[:8]}: {_sin_token(e)}")
            continue
        inf["comentarios"] += len(coms)
        for c in coms:
            if not es_si(c.get("text", "")) or not c.get("id"):
                continue
            inf["si"] += 1
            usuario = (c.get("username") or "").lower()
            k_hecho = f"comenta_si:hecho:{c['id']}"
            k_usuario = f"comenta_si:usuario:{media}:{usuario}" if usuario else ""
            if k_usuario and r.get_json(k_usuario) is not None:
                inf["repetidos"] += 1
                continue
            # Reserva ANTES de mandar (atómica): dos pases solapados no mandan el mismo.
            if not r.set_nx(k_hecho, config.COMENTA_SI_DEDUP_S):
                inf["repetidos"] += 1
                continue
            if r.incr_ttl(f"comenta_si:hora:{cuenta.slug}:{hora}", 3600) > config.COMENTA_SI_TOPE_HORA:
                r.delete(k_hecho)  # sin plaza esta hora: que lo coja el siguiente pase
                inf["tope"] += 1
                continue
            fila = {"comentario": c["id"], "usuario": usuario, "texto": (c.get("text") or "")[:80],
                    "pid": pub.id, "media_id": media, "mensaje": mensaje(pub, guardar=enviar), "en": ahora}
            if enviar:
                try:
                    cli.responder_privado(cuenta.ig_user_id, c["id"], fila["mensaje"])
                except ErrorPublicacion as e:
                    inf["errores"].append(f"{c['id']}: {_sin_token(e)}")
                    if e.reintentable:
                        r.delete(k_hecho)  # pasajero: se reintenta; definitivo: queda marcado
                    continue
            else:
                _anotar_seco({**fila, "cuenta": cuenta.slug}, ahora)
            if k_usuario:
                r.set_nx(k_usuario, config.COMENTA_SI_DEDUP_S)
            inf["mandados"].append({k: fila[k] for k in ("comentario", "usuario", "pid")})
            log(f"[comenta_si] {cuenta.slug} {pub.id[:8]} @{usuario}: {'mandado' if enviar else 'en seco'}")
    return inf


def procesar_todas(**kw) -> list[dict]:
    return [procesar_cuenta(c, **kw) for c in cuentas_repo.listar() if c.activa and c.ig_user_id]
