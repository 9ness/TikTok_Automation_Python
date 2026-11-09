"""Datos en bruto para el vigía de salud del publicador Multiplataforma (solo lectura).

Corre DENTRO del contenedor api (`scripts/multiplataforma_salud.sh` lo copia) y
escribe un JSON por stdout. NUNCA saca tokens: de cada uno solo si vale, cuándo
caduca y sus permisos. No publica, no reintenta, no toca la cola.

El análisis (qué es incidencia, a quién avisar, no repetir) lo hace el host con
`src/multiplataforma/services/salud.py`, para no depender de un despliegue.
"""

from __future__ import annotations

import json
import re
import sys
import time

import httpx

from src.multiplataforma import config
from src.multiplataforma.repos import cuentas_repo, publicaciones_repo, redis_base
from src.multiplataforma.services import tandas

VENTANA_S = 7 * 86400
_TOKEN_RE = re.compile(r"(access_token|input_token)=[^&\s\"']+")


def limpio(texto) -> str:
    """Por si un error trae la URL con el token."""
    return _TOKEN_RE.sub(r"\1=XXX", str(texto))
PLATAFORMAS_META = ("instagram", "facebook", "threads")


def _get(url: str, token: str, **params) -> tuple[int, dict]:
    try:
        r = httpx.get(url, params={**params, "access_token": token}, timeout=30)
        return r.status_code, (r.json() if r.content else {})
    except (httpx.HTTPError, ValueError) as e:
        return 0, {"error": {"message": type(e).__name__}}


def _error(datos: dict) -> str:
    err = datos.get("error") if isinstance(datos, dict) else None
    if not isinstance(err, dict):
        return ""
    return f"({err.get('code')}) {limpio(err.get('message'))[:160]}"


def estado_token(plataforma: str, token: str) -> dict:
    """{valido, expira, scopes, error} sin el token."""
    if plataforma == "threads":  # Threads no tiene debug_token: una lectura barata basta
        st, d = _get(f"{config.threads_base()}/me", token, fields="id")
        return {"valido": st == 200, "expira": None, "scopes": None, "error": "" if st == 200 else _error(d) or f"HTTP {st}"}
    st, d = _get(f"{config.graph_base()}/debug_token", token, input_token=token)
    info = d.get("data") if isinstance(d, dict) else None
    if st != 200 or not isinstance(info, dict):
        return {"valido": False, "expira": None, "scopes": None, "error": _error(d) or f"HTTP {st}"}
    err = info.get("error") or {}
    return {"valido": bool(info.get("is_valid")), "expira": info.get("expires_at"),
            "scopes": info.get("scopes"), "error": str(err.get("message", ""))[:160] if err else ""}


def reels_fb(c, pubs: list, ahora: float) -> list[dict]:
    """Reproducciones de los reels de FB publicados en la ventana."""
    out = []
    for p in pubs:
        vid = ((p.resultados or {}).get("facebook") or {}).get("video_id")
        if not vid or (p.estado or {}).get("facebook") != config.ESTADO_PUBLICADO:
            continue
        st, d = _get(f"{config.graph_base()}/{vid}/video_insights", c.token("facebook"))
        plays = None
        if st == 200:
            for m in d.get("data") or []:
                if m.get("name") == "fb_reels_total_plays":
                    vals = [v.get("value") for v in m.get("values") or [] if isinstance(v.get("value"), (int, float))]
                    plays = sum(vals) if vals else None
        out.append({"ts": p.programada_en, "plays": plays})
    return out


def epocas(slug: str, ahora: float) -> dict | None:
    """¿Cabe lo de temporada antes de que acabe su época? None si la app
    desplegada aún no lo calcula o falla: el vigía no se cae por esto."""
    calcular = getattr(tandas, "capacidad_epocas", None)
    if calcular is None:
        return None
    try:
        return calcular(slug, ahora=ahora)
    except Exception as e:  # noqa: BLE001
        return {"error": type(e).__name__}


def main() -> int:
    ahora = time.time()
    todas = publicaciones_repo.todas(20000)
    recientes = [p for p in todas if ahora - VENTANA_S <= (p.programada_en or 0) <= ahora]
    renovado = redis_base.get_redis().get_json("threads_renovado") or {}
    cuentas = {}
    for c in cuentas_repo.listar():
        if not c.activa:
            continue
        propias = [p for p in recientes if p.cuenta == c.slug]
        tokens = {pl: estado_token(pl, c.token(pl)) for pl in PLATAFORMAS_META if c.lista_para(pl)}
        cuentas[c.slug] = {
            "tokens": tokens,
            "threads_renovado": renovado.get(c.slug),
            "fb_reels": reels_fb(c, propias, ahora) if "facebook" in tokens else [],
            "epocas": epocas(c.slug, ahora),
        }
    pubs = [{"id": p.id, "cuenta": p.cuenta, "titulo": (p.titulo or "")[:60], "programada_en": p.programada_en,
             "plataformas": list(p.plataformas or []), "estado": dict(p.estado or {}),
             "errores": {k: limpio(v)[:300] for k, v in (p.errores or {}).items()}} for p in recientes]
    json.dump({"ahora": ahora, "cuentas": cuentas, "pubs": pubs}, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
