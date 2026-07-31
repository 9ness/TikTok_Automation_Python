"""Cuentas de TikTok de referencia, editables por el operador.

Son las cuentas que ya usan esta misma estrategia (las del mentor del curso y
las que el operador vaya encontrando). Sirven para mirar qué suben, con qué
frecuencia y con qué hashtags — no las toca el pipeline, es material de
consulta.

Viven en Redis y no en el código porque el operador las añade y las quita
sobre la marcha, y no tiene sentido un despliegue por cada cuenta nueva.
"""

from __future__ import annotations

import re

from src.viralizacion.repos.redis_base import get_viralizacion_redis

_KEY = "cuentas_ejemplo"

# Con las que se arranca si nunca se ha tocado la lista. Son del mentor del
# curso: se sabe que son suyas porque hace un año tienen vídeos orgánicos en
# los que sale él.
CUENTAS_DEFECTO = [
    {"handle": "@danigumoficial", "nota": "Productos + reflexiones, misma plantilla"},
    {"handle": "@rudyskateoficial", "nota": "Pablo Motos, estilo serif"},
    {"handle": "@todoparatucasa.shop", "nota": ""},
]

# Un handle de TikTok es alfanumérico + punto + guion bajo.
_HANDLE_RE = re.compile(r"^[A-Za-z0-9._]{1,24}$")


def normalizar(handle: str) -> str:
    """`@usuario` limpio, o "" si no es un handle válido.

    Se acepta que peguen la URL entera: es lo que sale al compartir desde la
    app y obligar a recortarla a mano solo da errores.
    """
    h = (handle or "").strip()
    if not h:
        return ""
    if "tiktok.com" in h:
        # https://www.tiktok.com/@usuario?lang=es  →  usuario
        trozo = h.split("tiktok.com/", 1)[-1]
        h = trozo.split("?", 1)[0].split("/", 1)[0]
    h = h.lstrip("@").strip()
    if not _HANDLE_RE.match(h):
        return ""
    return f"@{h}"


def url_de(handle: str) -> str:
    return f"https://www.tiktok.com/{handle}"


def get_cuentas() -> list[dict]:
    r = get_viralizacion_redis()
    if not r.is_available():
        return [dict(c) for c in CUENTAS_DEFECTO]
    doc = r.get_json(_KEY)
    if not isinstance(doc, dict) or "cuentas" not in doc:
        return [dict(c) for c in CUENTAS_DEFECTO]
    salida = []
    for c in doc.get("cuentas") or []:
        h = normalizar(str(c.get("handle", "")))
        if h:
            salida.append({"handle": h, "nota": str(c.get("nota", ""))})
    return salida


def save_cuentas(cuentas: list[dict]) -> list[dict]:
    """Guarda la lista entera (la UI manda siempre el conjunto completo).

    Una lista VACÍA es válida: significa "no quiero ninguna", y hay que poder
    distinguirlo de "nunca las he tocado".
    """
    limpias: list[dict] = []
    vistos: set[str] = set()
    for c in cuentas:
        h = normalizar(str(c.get("handle", "")))
        if not h or h.lower() in vistos:
            continue
        vistos.add(h.lower())
        limpias.append({"handle": h, "nota": str(c.get("nota", "")).strip()[:80]})
    r = get_viralizacion_redis()
    if not r.is_available():
        raise RuntimeError(
            "Redis (Upstash) no está configurado — no se pueden guardar las "
            "cuentas de ejemplo."
        )
    r.set_json(_KEY, {"cuentas": limpias})
    return limpias
