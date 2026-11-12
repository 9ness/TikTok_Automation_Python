"""Puente Editor Auto → usuario de la fábrica (12/11/2026).

Un admin de la web del editor (p. ej. la cuenta de Néstor o «nueveness») puede
mandar a editar un vídeo «para» un usuario de la fábrica (ness, ana, nestor2…).
Cada envío así se apunta en `ediciones_fabrica:<usuario>` (Redis del editor,
Upstash) y los agentes lo ven con `ediciones_editor` del MCP: qué se editó, en
qué estado está y el MP4, para registrarlo en Mis tandas con su producto
(`registrar_replica_video(edicion=...)`).

No mete nada en Mis tandas por sí solo: allí cada fila necesita producto y
enlace, y eso lo pone el agente.

Los agentes también pueden MANDAR a editar (`POST .../ediciones-fabrica/enviar`,
MCP `editar_en_editor`): lo hace la cuenta del editor `EDITOR_CUENTA_AGENTES_EMAIL`
y el flujo de ESE trabajo va en el job (`params["tool_flow"]`, ver `flujo_para`),
sin tocar el flujo guardado de la cuenta.
"""

from __future__ import annotations

import os
import time

from src.editor_auto.config import user_output_day_folder
from src.editor_auto.repos.redis_base import get_editor_redis

_CLAVE = "ediciones_fabrica:{usuario}"
_MAX = 500

ESTILOS = ("vip", "normal", "pasos")
# Claves de modelo Whisper de las herramientas (subs_auto usa `model_size`).
_CLAVES_WHISPER = ("whisper_model_size", "model_size")
# Whisper large tumbó el VPS por RAM (22/10/2026): los trabajos de agentes van en small.
_WHISPER_AGENTES = "small"
# Necesita guion: no vale para un vídeo suelto.
_TOOLS_PROHIBIDAS = {"silence_cutter_scripted"}


def _rebajar_whisper(paso) -> None:
    """Pone `small` en cualquier modelo Whisper large del paso (también el de
    la config por defecto de la herramienta, que suele ser large-v3)."""
    from src.editor_auto.tools import get_tool

    tool = get_tool(paso.tool_id)
    base = tool.default_config() if tool is not None else {}
    cfg = dict(paso.config or {})
    for k in _CLAVES_WHISPER:
        if k in base or k in cfg:
            valor = str(cfg.get(k, base.get(k)) or "")
            if valor.startswith("large"):
                cfg[k] = _WHISPER_AGENTES
    paso.config = cfg


# Subtítulos del VIP completo: altura (fracción del alto) y franja del nombre del producto.
_SUBS_Y_VIP = 0.70
# Flecha al carrito: la que más contrasta con el fondo (la tool falla sin `sticker_file`).
_FLECHA_VIP = {"sticker_file": "flecha_3d_roja.mov", "color_mode": "fixed",
               "scale_width_pct": 30.0, "position_y_pct": 84.0}


def flujo_para(estilo: str, *, style_config: dict | None = None,
               pasos: list | None = None, config_vip: dict | None = None,
               flujo_ref: dict | None = None, texto_voz: str = "",
               nombre_producto: str = "", solo_rotulos: bool = False) -> list:
    """Flujo (lista de ToolStep) de UN trabajo mandado por un agente.

    - `vip`: el vídeo llega EN CRUDO y sale entero: `vip_overlays` (+ `config_vip`,
      sin fotos de internet) → flecha → subtítulos (estilo del vídeo de referencia
      `flujo_ref["subs_auto"]` si lo hay; texto exacto `texto_voz`); sin título fijo arriba: el
      gancho o un rótulo nombra el producto. `solo_rotulos=True`: solo `vip_overlays` (para un
      vídeo que ya trae subtítulos).
    - `normal`: el estilo de la web de la cuenta (`build_tool_flow`), sin guardarlo.
    - `pasos`: la lista dada ({tool_id, config, enabled?}), validada contra el registry.
    Lanza ValueError si algo no vale."""
    from src.editor_auto.models.editor_user import ToolStep
    from src.editor_auto.tools import REGISTRY

    estilo = (estilo or "vip").strip().lower()
    if estilo not in ESTILOS:
        raise ValueError(f"estilo debe ser uno de {', '.join(ESTILOS)}.")
    if estilo == "vip":
        cfg = dict(config_vip or {})
        cfg["whisper_model_size"] = _WHISPER_AGENTES
        cfg["fotos_internet"] = False
        if solo_rotulos:
            flujo = [ToolStep(tool_id="vip_overlays", config=cfg)]
        else:
            flujo = _vip_completo(cfg, flujo_ref or {}, texto_voz, nombre_producto)
    elif estilo == "normal":
        from src.editor_auto.services.style_mapper import build_tool_flow

        flujo = [s.model_copy(deep=True) for s in build_tool_flow(style_config)]
    else:
        if not pasos:
            raise ValueError("Con estilo «pasos» hay que dar la lista `pasos`.")
        flujo = []
        for i, p in enumerate(pasos):
            if not isinstance(p, dict) or not isinstance(p.get("tool_id"), str):
                raise ValueError(f"Paso {i + 1}: cada paso es {{tool_id, config}}.")
            tid = p["tool_id"].strip()
            if tid not in REGISTRY:
                raise ValueError(f"Paso {i + 1}: herramienta desconocida {tid!r} "
                                 f"(valen: {', '.join(sorted(REGISTRY))}).")
            if tid in _TOOLS_PROHIBIDAS:
                raise ValueError(f"Paso {i + 1}: {tid} necesita guion; no vale aquí.")
            cfg = p.get("config") or {}
            if not isinstance(cfg, dict):
                raise ValueError(f"Paso {i + 1}: `config` tiene que ser un objeto.")
            flujo.append(ToolStep(tool_id=tid, enabled=bool(p.get("enabled", True)), config=dict(cfg)))
    for paso in flujo:
        _rebajar_whisper(paso)
    if not any(s.enabled for s in flujo):
        raise ValueError("El flujo no tiene ninguna herramienta activa.")
    return flujo


def _vip_completo(cfg_vip: dict, flujo_ref: dict, texto_voz: str, nombre: str) -> list:
    from src.editor_auto.models.editor_user import ToolStep
    from src.editor_auto.tools import get_tool

    subs = dict(get_tool("subs_auto").default_config())
    ref_subs = flujo_ref.get("subs_auto") or {}
    subs.update(ref_subs)
    # Su defecto (0.78) choca con la flecha: si la referencia no dice nada, 0.70.
    subs["y_position"] = ref_subs.get("y_position", _SUBS_Y_VIP)
    subs.update(language="es", model_size=_WHISPER_AGENTES)
    if (texto_voz or "").strip():
        subs["reference_text"] = texto_voz.strip()
    # El VIP no pone rótulos encima de los subtítulos ni del nombre.
    cfg = dict(cfg_vip)
    cfg["_flujo"] = {"subs_auto": {"y_position": subs["y_position"]}}
    if (nombre or "").strip():
        # Sin título fijo arriba (12/11, Néstor: los VIP llevan gancho y ya); el
        # nombre va a las notas para que el gancho o un rótulo lo diga (anti-sanción).
        cfg["notas_estilo"] = (f"{cfg.get('notas_estilo') or ''} Producto: {nombre.strip()}. "
                               "Que el gancho o un rótulo nombre el producto.").strip()
    flecha = dict(get_tool("sticker_arrow").default_config())
    flecha.update(_FLECHA_VIP)
    flecha.update(flujo_ref.get("sticker_arrow") or {})
    flujo = [ToolStep(tool_id="vip_overlays", config=cfg),
             ToolStep(tool_id="sticker_arrow", config=flecha),
             ToolStep(tool_id="subs_auto", config=subs)]
    return flujo


def usuarios_validos() -> list[str]:
    from src.api import users

    return list(users.USUARIOS.keys())


def apuntar(usuario: str, editor_user, day: str, enqueued: list[dict]) -> None:
    """Añade los trabajos recién encolados al índice del usuario de fábrica."""
    if not usuario or not enqueued:
        return
    r = get_editor_redis()
    clave = _CLAVE.format(usuario=usuario)
    cur = r.get_json(clave)
    lista = cur if isinstance(cur, list) else []
    ahora = time.time()
    for e in enqueued:
        lista.append({
            "job_id": e.get("job_id"),
            "filename": e.get("filename"),
            "day": day,
            "editor_user": editor_user.name,
            "editor_user_id": editor_user.id,
            "ts": ahora,
            # Envíos de agentes: estilo (vip/normal/pasos) y la referencia copiada (url o nombre).
            "estilo": e.get("agente") or "",
            "referencia": e.get("referencia") or "",
        })
    r.set_json(clave, lista[-_MAX:])


def _buscar_salida(editor_user: str, day: str, filename: str) -> str | None:
    """Si el trabajo ya salió de la cola: el editado en `salida/<día>/`."""
    try:
        carpeta = user_output_day_folder(editor_user, day)
        base = os.path.splitext(filename or "")[0]
        if not base or not os.path.isdir(carpeta):
            return None
        for n in sorted(os.listdir(carpeta)):
            if n.startswith(base) and n.lower().endswith(".mp4"):
                return os.path.join(carpeta, n)
    except Exception:
        return None
    return None


def listar(usuario: str, queue, *, limite: int = 50) -> list[dict]:
    """Ediciones del usuario, las más nuevas primero, con estado y salida."""
    cur = get_editor_redis().get_json(_CLAVE.format(usuario=usuario))
    lista = cur if isinstance(cur, list) else []
    jobs = {j.id: j for j in queue.get_all()}
    out: list[dict] = []
    for e in reversed(lista[-limite:]):
        job = jobs.get(e.get("job_id"))
        if job is not None:
            estado = job.status.value if hasattr(job.status, "value") else str(job.status)
            ruta = job.result_path if job.result_path and os.path.exists(job.result_path) else None
            error = job.error
        else:
            ruta = _buscar_salida(e.get("editor_user", ""), e.get("day", ""), e.get("filename", ""))
            estado = "completed" if ruta else "desconocido"
            error = None
        out.append({
            **e,
            "estado": estado,
            "listo": bool(ruta),
            "salida": os.path.basename(ruta) if ruta else None,
            "error": error,
        })
    return out


def ruta_mp4(usuario: str, job_id: str, queue) -> str | None:
    for e in listar(usuario, queue, limite=_MAX):
        if e.get("job_id") == job_id:
            if not e["listo"]:
                return None
            job = next((j for j in queue.get_all() if j.id == job_id), None)
            if job is not None and job.result_path and os.path.exists(job.result_path):
                return job.result_path
            return _buscar_salida(e.get("editor_user", ""), e.get("day", ""), e.get("filename", ""))
    return None
