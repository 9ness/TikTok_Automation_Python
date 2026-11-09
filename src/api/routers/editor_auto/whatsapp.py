"""Endpoints para el bot de WhatsApp del Editor Auto (vive en otro servidor).

Auth: `X-API-Key` como el resto de la API. Ver `EDITOR_AUTO_MODULE.md`
(seccion «WhatsApp (bot)»).
"""

from __future__ import annotations

import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from src.api.dependencies import get_current_user, get_queue
from src.api.schemas.editor_auto.whatsapp import (
    CosteRequest,
    DesvincularRequest,
    VincularConfirmarRequest,
    VincularPedirRequest,
)
from src.editor_auto.services import whatsapp_vinculo as vinculo
from src.queue.manager import JobQueue

router = APIRouter(
    prefix="/api/v1/editor-auto/whatsapp",
    tags=["editor-auto · whatsapp"],
    dependencies=[Depends(get_current_user)],
)

_PROXY_TIMEOUT_S = 20.0


@router.get("/cliente")
def cliente(telefono: str, queue: Annotated[JobQueue, Depends(get_queue)]) -> dict:
    return vinculo.resumen_cliente(telefono, queue=queue)


@router.post("/vincular/pedir")
def vincular_pedir(payload: VincularPedirRequest) -> dict:
    return vinculo.pedir_codigo(payload.telefono, payload.email)


@router.post("/vincular/confirmar")
def vincular_confirmar(payload: VincularConfirmarRequest) -> dict:
    return vinculo.confirmar_codigo(payload.telefono, payload.codigo)


@router.post("/desvincular")
def desvincular(payload: DesvincularRequest) -> dict:
    return {"ok": vinculo.desvincular(payload.telefono)}


@router.post("/coste")
def coste(payload: CosteRequest) -> dict:
    """Apunta el gasto de una llamada a Claude del bot. Fuera de un job de la
    cola, `record_claude` lo guarda como coste suelto (no falla)."""
    from src.cost_tracking import record_claude
    try:
        usd = record_claude(
            input_tokens=payload.input_tokens, output_tokens=payload.output_tokens,
            model=payload.modelo, cache_read_tokens=payload.cache_read_tokens,
            cache_write_tokens=payload.cache_write_tokens,
            detail="editor_auto.whatsapp_bot",
        )
    except Exception:
        return {"ok": False, "usd": None}
    return {"ok": True, "usd": float(usd) if usd is not None else None}


# ─────────────────────── Proxy al bot (lista blanca) ───────────────────────

def _proxy(nombre: str, *, metodo: str, params: dict | None = None, cuerpo: Any = None) -> dict:
    url = (os.getenv("EDITOR_WHATSAPP_BOT_URL") or "").strip().rstrip("/")
    token = (os.getenv("EDITOR_WHATSAPP_BOT_TOKEN") or "").strip()
    faltan = [k for k, v in (("EDITOR_WHATSAPP_BOT_URL", url), ("EDITOR_WHATSAPP_BOT_TOKEN", token)) if not v]
    if faltan:
        return {"configurado": False, "faltan": faltan}
    try:
        import httpx
        resp = httpx.request(
            metodo, f"{url}/admin/{nombre}",
            headers={"Authorization": f"Bearer {token}"},
            params=params or None, json=cuerpo if metodo == "POST" else None,
            timeout=_PROXY_TIMEOUT_S,
        )
        resp.raise_for_status()
        try:
            datos = resp.json()
        except Exception:
            datos = {"texto": resp.text[:2000]}
    except Exception as e:
        # Solo el tipo de error (el mensaje podria llevar la URL/cabeceras).
        err = type(e).__name__
        code = getattr(getattr(e, "response", None), "status_code", None)
        if code:
            err = f"{err} {code}"
        return {"configurado": True, "alcanzable": False, "error": err}
    return {"configurado": True, "alcanzable": True, "datos": datos}


@router.get("/bot/diagnostico")
def bot_diagnostico() -> dict:
    return _proxy("diagnostico", metodo="GET")


@router.get("/bot/conversaciones")
def bot_conversaciones(limite: Annotated[int | None, Query(ge=1, le=500)] = None) -> dict:
    return _proxy("conversaciones", metodo="GET", params={"limite": limite} if limite else None)


@router.get("/bot/conversacion")
def bot_conversacion(wa_id: str) -> dict:
    return _proxy("conversacion", metodo="GET", params={"wa_id": wa_id})


@router.post("/bot/plantillas")
def bot_plantillas(payload: dict[str, Any] | None = None) -> dict:
    return _proxy("plantillas", metodo="POST", cuerpo=payload or {})


@router.post("/bot/suscribir")
def bot_suscribir(payload: dict[str, Any] | None = None) -> dict:
    return _proxy("suscribir", metodo="POST", cuerpo=payload or {})


@router.post("/bot/prueba")
def bot_prueba(payload: dict[str, Any] | None = None) -> dict:
    return _proxy("prueba", metodo="POST", cuerpo=payload or {})


@router.post("/bot/pausa")
def bot_pausa(payload: dict[str, Any] | None = None) -> dict:
    return _proxy("pausa", metodo="POST", cuerpo=payload or {})


@router.post("/bot/reanudar")
def bot_reanudar(payload: dict[str, Any] | None = None) -> dict:
    return _proxy("reanudar", metodo="POST", cuerpo=payload or {})
