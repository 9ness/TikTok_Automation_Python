"""Tracking de carpetas de producto ya completadas.

El estado vive en Redis (SET por fuente), NUNCA en Drive — "Productos España"
es un Drive de terceros y es solo lectura.

Key: `nicho_pov_bof:completed:<source>` → SET de nombres de carpeta.
"""

from __future__ import annotations

from src.nicho_pov_bof import config
from src.nicho_pov_bof.repos.redis_base import get_nicho_pov_bof_redis


def _key(source: str, usuario: str = "") -> str:
    """Clave del progreso. Es POR USUARIO: cada uno va por su carpeta.

    El histórico (sin usuario) se conserva como clave de `ness`, que es quien
    lo generó — así no pierde por dónde iba al separar las cuentas.
    """
    # La copia de seguridad comparte progreso con la fuente del curso: son las
    # mismas carpetas, solo cambia de dónde se leen las fotos.
    source = config.fuente_canonica(source)
    if not usuario or usuario == "ness":
        return f"completed:{source}"
    return f"completed:{source}:{usuario}"


def _require_redis():
    r = get_nicho_pov_bof_redis()
    if not r.is_available():
        raise RuntimeError(
            "Redis (Upstash) no está configurado — no se puede leer/guardar el "
            "progreso del Nicho POV BOF. Define UPSTASH_REDIS_REST_URL y "
            "UPSTASH_REDIS_REST_TOKEN."
        )
    return r


def get_completed(source: str, usuario: str = "") -> set[str]:
    """Nombres de carpeta marcados como completados en esta fuente."""
    return set(_require_redis().smembers(_key(source, usuario)))


def is_completed(source: str, folder: str, usuario: str = "") -> bool:
    return _require_redis().sismember(_key(source, usuario), folder)


def _key_tamano(source: str, usuario: str = "") -> str:
    """Cuántos productos tenía cada carpeta AL COMPLETARLA."""
    source = config.fuente_canonica(source)
    if not usuario or usuario == "ness":
        return f"completed:size:{source}"
    return f"completed:size:{source}:{usuario}"


def mark_completed(
    source: str, folder: str, usuario: str = "", productos: int = 0,
) -> None:
    """Marca la carpeta como hecha y apunta CUÁNTOS productos tenía.

    Lo segundo es para poder avisar después: el catálogo de la web se
    actualiza, y una carpeta ya terminada puede recibir productos nuevos. Sin
    guardar el tamaño de entonces no hay forma de saber cuántos han entrado
    desde que la diste por hecha, y quedarían escondidos para siempre.
    """
    r = _require_redis()
    r.sadd(_key(source, usuario), folder)
    if productos > 0:
        tamanos = r.get_json(_key_tamano(source, usuario)) or {}
        tamanos[folder] = int(productos)
        r.set_json(_key_tamano(source, usuario), tamanos)


def tamanos_al_completar(source: str, usuario: str = "") -> dict[str, int]:
    """`{carpeta: cuántos productos tenía al marcarla}`. Una lectura."""
    r = get_nicho_pov_bof_redis()
    if not r.is_available():
        return {}
    doc = r.get_json(_key_tamano(source, usuario)) or {}
    return {str(k): int(v) for k, v in doc.items() if str(v).isdigit()}


# ---------------------------------------------------------------------------
# Carpetas con los vídeos hechos pero SIN subir todavía
# ---------------------------------------------------------------------------
# SET propio, no un flag dentro de las completadas, porque son dos cosas
# distintas: se preparan vídeos de días futuros y esa carpeta no está cerrada
# —queda por subirlos—, y una carpeta ya cerrada puede seguir sin subir.


def _key_pendientes(source: str, usuario: str = "") -> str:
    source = config.fuente_canonica(source)
    if not usuario or usuario == "ness":
        return f"pending_upload:{source}"
    return f"pending_upload:{source}:{usuario}"


def get_pendientes(source: str, usuario: str = "") -> set[str]:
    """Carpetas marcadas como "vídeos listos, falta subirlos".

    Degrada a vacío si Redis no está: es un aviso de color, no puede dejar sin
    listado de carpetas (igual que `tamanos_al_completar`).
    """
    r = get_nicho_pov_bof_redis()
    if not r.is_available():
        return set()
    return set(r.smembers(_key_pendientes(source, usuario)))


def set_pendiente(
    source: str, folder: str, pendiente: bool, usuario: str = "",
) -> None:
    r = _require_redis()
    clave = _key_pendientes(source, usuario)
    if pendiente:
        r.sadd(clave, folder)
    else:
        r.srem(clave, folder)


def unmark_completed(source: str, folder: str, usuario: str = "") -> None:
    """Rollback — degrada en silencio si Redis no está (igual que viralización)."""
    r = get_nicho_pov_bof_redis()
    if r.is_available():
        r.srem(_key(source, usuario), folder)
        # Y se olvida el tamaño: si se vuelve a marcar, se apunta el de
        # entonces. Dejarlo haría que al recompletarla saliera un "+N" viejo.
        tamanos = r.get_json(_key_tamano(source, usuario)) or {}
        if tamanos.pop(folder, None) is not None:
            r.set_json(_key_tamano(source, usuario), tamanos)
