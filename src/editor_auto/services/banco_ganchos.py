"""Base de ganchos aprendidos de los virales (12/11/2026).

Cada vídeo de referencia que lee `referencia_vip` deja aquí su gancho (texto,
tipo, dato, posición). El VIP SIN referencia toma unos cuantos del mismo estilo
como inspiración, así los ganchos se parecen a los que funcionan y no a los que
inventa la IA. Con referencia el gancho se copia literal (ver vip_overlays).
Nunca lanza: si Redis falla, el VIP sigue sin ejemplos.
"""

from __future__ import annotations

import time

CLAVE = "editor_auto:vip:ganchos"
_MAX = 300


def _redis():
    from src.editor_auto.repos.redis_base import get_editor_redis
    return get_editor_redis()


def guardar(ritmo: dict, fuente: str = "") -> bool:
    """Añade el gancho de una referencia (sin repetir texto). True si entra."""
    texto = " ".join(str(ritmo.get("gancho_texto") or "").split())
    if not texto or ritmo.get("gancho_tipo") == "ninguno":
        return False
    try:
        r = _redis()
        lista = r.get_json(CLAVE) or []
        if any(str(g.get("texto", "")).lower() == texto.lower() for g in lista):
            return False
        lista.append({"texto": texto, "tipo": ritmo.get("gancho_tipo") or "",
                      "dato": ritmo.get("gancho_dato") or "",
                      "y_pct": ritmo.get("gancho_y_pct"), "fuente": fuente[:200],
                      "ts": int(time.time())})
        r.set_json(CLAVE, lista[-_MAX:])
        return True
    except Exception:  # noqa: BLE001
        return False


def ejemplos(n: int = 8) -> list[dict]:
    """Los `n` más recientes, variando de tipo (round-robin por tipo)."""
    try:
        lista = list(reversed(_redis().get_json(CLAVE) or []))
    except Exception:  # noqa: BLE001
        return []
    por_tipo: dict[str, list[dict]] = {}
    for g in lista:
        por_tipo.setdefault(g.get("tipo") or "", []).append(g)
    out: list[dict] = []
    while len(out) < n and any(por_tipo.values()):
        for t in list(por_tipo):
            if por_tipo[t] and len(out) < n:
                out.append(por_tipo[t].pop(0))
    return out
