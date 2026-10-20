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

import base64
import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode

import httpx

from src.multiplataforma import config
from src.multiplataforma.repos import cuentas_repo, redis_base


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
            _marcar_renovado(c.slug)
            return {"cuenta": c.slug, "usuario": yo.get("username", "")}
    raise TokenInvalido(f"El token es de @{yo.get('username', '?')}, que no es ninguna de nuestras cuentas")


# ── Threads por OAuth: botón «Conectar Threads» ─────────────────────────────
# El «Generador de identificadores» de Meta falla desde el navegador de
# Messenger (vuelve a una página que no existe), y es el único navegador desde
# el que Meta deja entrar a Ana sin marcar el dispositivo. Así que el permiso
# se pide desde aquí: Threads devuelve un `code` a nuestra URL de retorno, se
# canjea por un token largo (60 días) con la clave secreta de la app, y el tick
# lo renueva antes de que caduque. La clave se guarda en Redis y no se devuelve.

_APP_KEY = "threads_app"
SCOPES_THREADS = (
    "threads_basic,threads_content_publish,threads_manage_insights,"
    "threads_manage_replies,threads_read_replies"
)
RUTA_RETORNO = "/api/v1/multiplataforma/meta/threads/retorno"
RENOVAR_CADA_S = 7 * 86400  # el token dura 60 días; se renueva semanal
_STATE_TTL_S = 30 * 60


def url_retorno() -> str:
    return f"{config.base_publica()}{RUTA_RETORNO}"


def guardar_app_threads(app_id: str, app_secret: str) -> dict:
    app_id, app_secret = (app_id or "").strip(), (app_secret or "").strip()
    if not app_id.isdigit() or len(app_secret) < 16:
        raise TokenInvalido("Falta el identificador de la app de Threads o la clave secreta")
    redis_base.get_redis().set_json(_APP_KEY, {"app_id": app_id, "app_secret": app_secret})
    return {"app_id": app_id}


def _app_threads() -> dict:
    d = redis_base.get_redis().get_json(_APP_KEY) or {}
    if not d.get("app_id") or not d.get("app_secret"):
        raise TokenInvalido("Primero guarda el identificador y la clave secreta de la app de Threads")
    return d


def estado_app_threads() -> dict:
    d = redis_base.get_redis().get_json(_APP_KEY) or {}
    return {"configurada": bool(d.get("app_id") and d.get("app_secret")), "app_id": d.get("app_id", ""),
            "url_retorno": url_retorno()}


def _clave_state() -> bytes:
    key = os.getenv("AUTH_COOKIE_KEY", "").strip() or "dev-sin-clave"
    return f"{key}|multiplataforma|threads-oauth".encode()


def _firmar_state(datos: dict) -> str:
    cuerpo = base64.urlsafe_b64encode(json.dumps(datos, separators=(",", ":")).encode()).decode().rstrip("=")
    return cuerpo + "." + hmac.new(_clave_state(), cuerpo.encode(), hashlib.sha256).hexdigest()[:40]


def _leer_state(state: str) -> dict:
    cuerpo, _, firma = (state or "").partition(".")
    buena = hmac.new(_clave_state(), cuerpo.encode(), hashlib.sha256).hexdigest()[:40]
    if not cuerpo or not hmac.compare_digest(firma, buena):
        raise TokenInvalido("Enlace de vuelta no válido: vuelve a pulsar «Conectar Threads»")
    datos = json.loads(base64.urlsafe_b64decode(cuerpo + "=" * (-len(cuerpo) % 4)))
    if time.time() - float(datos.get("t", 0)) > _STATE_TTL_S:
        raise TokenInvalido("El enlace ha caducado: vuelve a pulsar «Conectar Threads»")
    return datos


def url_autorizar(usuario: str) -> str:
    app = _app_threads()
    params = {
        "client_id": app["app_id"],
        "redirect_uri": url_retorno(),
        "scope": SCOPES_THREADS,
        "response_type": "code",
        "state": _firmar_state({"u": usuario, "t": int(time.time())}),
    }
    return "https://threads.net/oauth/authorize?" + urlencode(params)


def completar_oauth(code: str, state: str) -> dict:
    """`code` de Threads → token largo → cuenta con ese id."""
    _leer_state(state)
    code = (code or "").strip().removesuffix("#_")
    if not code:
        raise TokenInvalido("Threads no ha devuelto el permiso")
    app = _app_threads()
    r = httpx.post(
        "https://graph.threads.net/oauth/access_token",
        data={
            "client_id": app["app_id"],
            "client_secret": app["app_secret"],
            "grant_type": "authorization_code",
            "redirect_uri": url_retorno(),
            "code": code,
        },
        timeout=30,
    )
    try:
        corto = r.json()
    except ValueError:
        corto = {}
    if r.status_code != 200 or not corto.get("access_token"):
        msg = (corto.get("error") or {}).get("message") if isinstance(corto.get("error"), dict) else corto.get("error_message")
        raise TokenInvalido(f"Threads no acepta el permiso: {msg or f'HTTP {r.status_code}'}")
    largo = _get(
        "https://graph.threads.net/access_token",
        {"grant_type": "th_exchange_token", "client_secret": app["app_secret"], "access_token": corto["access_token"]},
    )
    return conectar_threads(largo.get("access_token", ""))


def _marcar_renovado(slug: str) -> None:
    r = redis_base.get_redis()
    d = r.get_json("threads_renovado") or {}
    d[slug] = int(time.time())
    r.set_json("threads_renovado", d)


def renovar_tokens_threads(log=lambda _: None) -> dict:
    """Renueva los tokens de Threads con más de una semana (no hace falta la clave)."""
    hechos = redis_base.get_redis().get_json("threads_renovado") or {}
    ahora = time.time()
    informe: dict = {}
    for c in cuentas_repo.listar():
        token = (c.tokens or {}).get("threads")
        if not token:
            continue
        if ahora - float(hechos.get(c.slug, 0)) < RENOVAR_CADA_S:
            continue
        try:
            d = _get("https://graph.threads.net/refresh_access_token",
                     {"grant_type": "th_refresh_token", "access_token": token})
        except TokenInvalido as e:
            informe[c.slug] = f"error: {e}"
            log(f"[threads] {c.slug}: no se pudo renovar ({e})")
            continue
        if d.get("access_token"):
            cuentas_repo.set_tokens(c.slug, {"threads": d["access_token"]})
        _marcar_renovado(c.slug)
        informe[c.slug] = "renovado"
        log(f"[threads] {c.slug}: token renovado")
    return informe
