"""Presets de generación TikTok Shop por (usuario × producto × modo).

Namespace Redis: `shop:<user_id>:<product_id>:<kind>` donde
`kind ∈ {auto_video, veo3, nano_banana}`. Clave completa:
`tiktokCR:config:shop:<user_id>:<product_id>:<kind>:<preset_name>`.

Permite que el usuario guarde múltiples configuraciones para un mismo
producto en cada modo y las cargue en 1 click desde la landing del
producto. Nombre especial `__default` = preset auto-cargado al entrar
en la landing (igual que Construcción POV).
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response

from src.api.dependencies import get_current_user
from src.api.exceptions import APIError, PresetNotFoundError, ValidationError
from src.api.schemas.shop_preset import (
    ShopPresetListResponse,
    ShopPresetResponse,
)


router = APIRouter(
    prefix="/api/v1/tiktok-shop/presets",
    tags=["tiktok-shop · presets"],
    dependencies=[Depends(get_current_user)],
)

PresetKind = Literal["auto_video", "veo3", "nano_banana"]
_VALID_KINDS: set[str] = {"auto_video", "veo3", "nano_banana"}


def _ns(user_id: str, product_id: str, kind: str) -> str:
    if kind not in _VALID_KINDS:
        raise ValidationError(
            f"Kind inválido: '{kind}'. Acepta: {sorted(_VALID_KINDS)}.",
            details={"kind": kind},
        )
    return f"shop:{user_id.strip()}:{product_id.strip()}:{kind.strip()}"


@router.get(
    "/{user_id}/{product_id}/{kind}",
    response_model=ShopPresetListResponse,
)
def list_shop_presets(
    user_id: str, product_id: str, kind: str,
) -> ShopPresetListResponse:
    from src.configs_store import is_available, list_configs
    if not is_available():
        return ShopPresetListResponse(items=[], total=0)
    names = list_configs(namespace=_ns(user_id, product_id, kind))
    return ShopPresetListResponse(items=names, total=len(names))


@router.get(
    "/{user_id}/{product_id}/{kind}/{name}",
    response_model=ShopPresetResponse,
)
def get_shop_preset(
    user_id: str, product_id: str, kind: str, name: str,
) -> ShopPresetResponse:
    from src.configs_store import load_config
    config = load_config(name, namespace=_ns(user_id, product_id, kind))
    if config is None:
        raise PresetNotFoundError(
            f"Preset '{name}' no encontrado para {user_id}×{product_id}×{kind}.",
            details={"user_id": user_id, "product_id": product_id, "kind": kind, "name": name},
        )
    return ShopPresetResponse(name=name, config=config)


@router.put(
    "/{user_id}/{product_id}/{kind}/{name}",
    response_model=ShopPresetResponse,
)
def save_shop_preset(
    user_id: str, product_id: str, kind: str, name: str,
    config: dict[str, Any],
) -> ShopPresetResponse:
    if not name.strip():
        raise ValidationError("El nombre del preset no puede estar vacío.")
    from src.configs_store import is_available, save_config
    if not is_available():
        raise APIError(
            "Upstash Redis no configurado — no se pueden guardar presets.",
            details={"hint": "Define UPSTASH_REDIS_REST_URL y UPSTASH_REDIS_REST_TOKEN."},
        )
    if not save_config(name, config, namespace=_ns(user_id, product_id, kind)):
        raise APIError(
            f"Fallo al guardar preset '{name}'.",
            details={"name": name},
        )
    return ShopPresetResponse(name=name, config=config)


@router.delete(
    "/{user_id}/{product_id}/{kind}/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_shop_preset(
    user_id: str, product_id: str, kind: str, name: str,
) -> Response:
    from src.configs_store import delete_config, is_available, load_config
    if not is_available():
        raise APIError("Upstash Redis no configurado.")
    ns = _ns(user_id, product_id, kind)
    if load_config(name, namespace=ns) is None:
        raise PresetNotFoundError(
            f"Preset '{name}' no encontrado.",
            details={"name": name},
        )
    delete_config(name, namespace=ns)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
