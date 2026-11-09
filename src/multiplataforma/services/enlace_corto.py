"""Enlace corto con contador de clics (#296).

Cada publicación y red lleva su propio código: `<base>/<código>` redirige
(302) al enlace de afiliado y suma un clic en `clics:<publicación>` (campo =
red). Así el informe semanal sabe qué vídeo lleva gente a la tienda.

- Código determinista (`sha1(id|red)`, 8 letras base32): reintentar una
  publicación no crea otro código ni otro registro.
- Solo con `config.enlace_corto_activo()` (apagado por defecto) y, para
  Amazon, también `enlace_corto_amazon()`.
- Los rastreadores de vista previa (facebookexternalhit…) no cuentan.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import re
import time

from src.multiplataforma import config
from src.multiplataforma.models import Publicacion
from src.multiplataforma.repos.redis_base import get_redis
from src.multiplataforma.services import enlaces

CODIGO_RE = re.compile(r"^[a-z2-7]{8}$")


def codigo(pub_id: str, plataforma: str) -> str:
    h = hashlib.sha1(f"{pub_id}|{plataforma}".encode()).digest()
    return base64.b32encode(h).decode().lower()[:8]


def url_corta(cod: str) -> str:
    return f"{config.enlace_corto_base().rstrip('/')}/{cod}"


def aplica(enlace: str) -> bool:
    if not config.enlace_corto_activo() or not enlace:
        return False
    return not enlaces.es_amazon(enlace) or config.enlace_corto_amazon()


def registrar(pub: Publicacion, plataforma: str, *, guardar: bool = True) -> str:
    """Devuelve la URL corta de `pub` en `plataforma` y guarda a dónde va."""
    cod = codigo(pub.id, plataforma)
    if guardar:
        get_redis().set_json(f"corto:{cod}", {
            "url": pub.enlace, "cuenta": pub.cuenta, "pid": pub.id, "plataforma": plataforma,
            "producto_ref": pub.producto_ref, "creado_en": time.time(),
        })
    return url_corta(cod)


def para_envio(pub: Publicacion, plataforma: str, *, guardar: bool = True) -> Publicacion:
    """Copia de `pub` con el enlace cambiado por el corto en el texto de esa
    red, el comentario de FB y el `link` de Pinterest. Si no aplica, `pub`."""
    if not aplica(pub.enlace):
        return pub
    corto = registrar(pub, plataforma, guardar=guardar)
    textos = dict(pub.textos)
    if plataforma in textos:
        textos[plataforma] = textos[plataforma].replace(pub.enlace, corto)
    return dataclasses.replace(pub, enlace=corto, textos=textos,
                               comentario=(pub.comentario or "").replace(pub.enlace, corto))


def es_bot(user_agent: str) -> bool:
    return not user_agent or bool(config.BOTS_USER_AGENT.search(user_agent))


def resolver(cod: str, *, user_agent: str = "", contar: bool = True) -> str | None:
    """URL de destino del código (o None). Suma el clic si es una persona."""
    if not CODIGO_RE.match(cod or ""):
        return None
    datos = get_redis().get_json(f"corto:{cod}") or {}
    url = str(datos.get("url") or "")
    if not url.startswith("https://") or enlaces.es_acortador(url):
        return None  # nunca redirigir a algo que no validamos al guardar
    if contar and not es_bot(user_agent) and datos.get("pid"):
        get_redis().hincrby(f"clics:{datos['pid']}", str(datos.get("plataforma") or "?"))
    return url


def clics(pub_id: str) -> dict[str, int]:
    """{red: clics} de una publicación."""
    return get_redis().hgetall(f"clics:{pub_id}")
