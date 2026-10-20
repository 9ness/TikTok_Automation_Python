"""Conectar Meta pegando un token, sin que el token pase por ningún chat.

Quien tiene el token de usuario de Facebook (de larga duración, ampliado en el
depurador de tokens) lo pega en la pantalla «Conectar Meta» y aquí se sacan
los tokens de PÁGINA de cada cuenta (`/me/accounts`), que no caducan. Para
Threads cada cuenta tiene su token, y se casa por el id que devuelve `/me`.

El propio token es la prueba de permiso: solo se escribe en las cuentas cuya
página (o perfil de Threads) devuelve Meta para ese token. Nunca se devuelve
ningún token; solo qué cuentas quedaron conectadas.
"""

from __future__ import annotations

import httpx

from src.multiplataforma import config
from src.multiplataforma.repos import cuentas_repo


class TokenInvalido(ValueError):
    pass


def _get(url: str, params: dict) -> dict:
    r = httpx.get(url, params=params, timeout=30)
    try:
        datos = r.json()
    except ValueError:
        datos = {}
    if r.status_code != 200 or "error" in datos:
        msg = (datos.get("error") or {}).get("message") or f"HTTP {r.status_code}"
        raise TokenInvalido(f"Meta no acepta el token: {msg}")
    return datos


def conectar_facebook(user_token: str) -> dict:
    """Token de usuario → token de página en `facebook` e `instagram` de cada cuenta."""
    user_token = (user_token or "").strip()
    if not user_token:
        raise TokenInvalido("Falta el token")
    paginas: list[dict] = []
    url = f"{config.graph_base()}/me/accounts"
    params: dict = {"access_token": user_token, "fields": "id,name,access_token", "limit": 100}
    while url:
        datos = _get(url, params)
        paginas += datos.get("data") or []
        url = (datos.get("paging") or {}).get("next") or ""
        params = {}
    por_id = {str(p.get("id")): p for p in paginas if p.get("access_token")}
    conectadas, sin_pagina = [], []
    for c in cuentas_repo.listar():
        p = por_id.get(str(c.fb_page_id)) if c.fb_page_id else None
        if not p:
            sin_pagina.append(c.slug)
            continue
        cuentas_repo.set_tokens(c.slug, {"facebook": p["access_token"], "instagram": p["access_token"]})
        conectadas.append({"cuenta": c.slug, "pagina": p.get("name", "")})
    return {
        "conectadas": conectadas,
        "sin_pagina": sin_pagina,
        "paginas_vistas": [p.get("name", "") for p in paginas],
    }


def conectar_threads(token: str) -> dict:
    """Token de Threads de UNA cuenta → se guarda en la cuenta con ese id."""
    token = (token or "").strip()
    if not token:
        raise TokenInvalido("Falta el token")
    yo = _get(f"{config.threads_base()}/me", {"access_token": token, "fields": "id,username"})
    for c in cuentas_repo.listar():
        if c.threads_user_id and str(c.threads_user_id) == str(yo.get("id")):
            cuentas_repo.set_tokens(c.slug, {"threads": token})
            return {"cuenta": c.slug, "usuario": yo.get("username", "")}
    raise TokenInvalido(f"El token es de @{yo.get('username', '?')}, que no es ninguna de nuestras cuentas")
