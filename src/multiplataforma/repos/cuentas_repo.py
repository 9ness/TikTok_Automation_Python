"""Cuentas de destino: `cuenta:<slug>` + índice `cuentas:index` (SET)."""

from __future__ import annotations

import re

from src.multiplataforma.models import CuentaDestino
from src.multiplataforma.repos import redis_base

_INDEX = "cuentas:index"
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,40}$")


def _key(slug: str) -> str:
    return f"cuenta:{slug}"


def slug_valido(slug: str) -> bool:
    return bool(_SLUG_RE.match(slug or ""))


def get(slug: str) -> CuentaDestino | None:
    d = redis_base.get_redis().get_json(_key(slug))
    return CuentaDestino.from_dict(d) if d else None


def listar(dueno: str | None = None) -> list[CuentaDestino]:
    r = redis_base.get_redis()
    out = []
    for slug in sorted(r.smembers(_INDEX)):
        c = get(slug)
        if c and (not dueno or c.dueno == dueno):
            out.append(c)
    return out


def guardar(cuenta: CuentaDestino) -> CuentaDestino:
    """Crea o actualiza. Si ya existía, conserva los tokens que tenía."""
    if not slug_valido(cuenta.slug):
        raise ValueError(f"Slug de cuenta no válido: {cuenta.slug!r} (minúsculas, números, - y _)")
    previa = get(cuenta.slug)
    if previa and not cuenta.tokens:
        cuenta.tokens = previa.tokens
        cuenta.creada_en = previa.creada_en
    r = redis_base.get_redis()
    r.set_json(_key(cuenta.slug), cuenta.to_dict())
    r.sadd(_INDEX, cuenta.slug)
    return cuenta


def set_tokens(slug: str, tokens: dict[str, str]) -> CuentaDestino:
    """Fusiona tokens (cadena vacía = borrar ese token)."""
    c = get(slug)
    if not c:
        raise KeyError(slug)
    actuales = dict(c.tokens or {})
    for plat, tok in (tokens or {}).items():
        if tok:
            actuales[plat] = tok
        else:
            actuales.pop(plat, None)
    c.tokens = actuales
    redis_base.get_redis().set_json(_key(slug), c.to_dict())
    return c
