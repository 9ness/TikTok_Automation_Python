"""Endpoints generador de hooks: variantes + temáticos.

Uso típico desde frontend `/tiktok-shop/hooks`:
  - User selecciona producto
  - Sistema muestra hooks existentes de presets agrupados
  - User pulsa "+Variantes" en un hook → POST /hooks/variants
  - User escribe tema en textarea → POST /hooks/themed

Ambos endpoints devuelven hooks generados que el user puede copiar
manualmente. NO se guardan en el producto por defecto — opcional.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.api.dependencies import get_current_user, get_product_repo
from src.api.exceptions import ProductNotFoundError, ValidationError
from src.tiktok_shop.repos import ProductRepo


router = APIRouter(
    prefix="/api/v1/tiktok-shop/products",
    tags=["tiktok-shop · hooks generator"],
    dependencies=[Depends(get_current_user)],
)


# ──────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────
class HookVariantsRequest(BaseModel):
    hook: str = Field(min_length=2, max_length=300)
    n: int = Field(default=5, ge=1, le=15)
    context: str | None = Field(default=None, max_length=500)
    angle_hint: str | None = Field(default=None, max_length=50)


class HookVariant(BaseModel):
    text: str
    rationale: str


class HookVariantsResponse(BaseModel):
    angle_detected: str
    variants: list[HookVariant]


class HookThemedRequest(BaseModel):
    theme: str = Field(min_length=2, max_length=300)
    n: int = Field(default=10, ge=1, le=20)


class HookThemed(BaseModel):
    text: str
    angle: str
    rationale: str


class HookThemedResponse(BaseModel):
    theme_interpretation: str
    hooks: list[HookThemed]


# ──────────────────────────────────────────────────────────────────
# POST /products/{id}/hooks/variants
# ──────────────────────────────────────────────────────────────────
@router.post(
    "/{product_id}/hooks/variants",
    response_model=HookVariantsResponse,
)
def generate_hook_variants_endpoint(
    product_id: str,
    payload: HookVariantsRequest,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
) -> HookVariantsResponse:
    """Genera variantes de un hook existente manteniendo el mismo ángulo."""
    product = repo.get(product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{product_id}' no encontrado.",
            details={"product_id": product_id},
        )

    try:
        from src.tiktok_shop.services.hooks_generator import generate_hook_variants

        result = generate_hook_variants(
            product,
            hook=payload.hook,
            n=payload.n,
            context=payload.context,
            angle_hint=payload.angle_hint,
        )
    except Exception as e:
        raise ValidationError(
            f"Error generando variantes: {e}",
            details={"product_id": product_id, "hook": payload.hook[:60]},
        )

    return HookVariantsResponse(
        angle_detected=result.get("angle_detected", ""),
        variants=[
            HookVariant(
                text=v.get("text", ""),
                rationale=v.get("rationale", ""),
            )
            for v in (result.get("variants") or [])
        ],
    )


# ──────────────────────────────────────────────────────────────────
# POST /products/{id}/hooks/themed
# ──────────────────────────────────────────────────────────────────
@router.post(
    "/{product_id}/hooks/themed",
    response_model=HookThemedResponse,
)
def generate_themed_hooks_endpoint(
    product_id: str,
    payload: HookThemedRequest,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
) -> HookThemedResponse:
    """Genera N hooks nuevos orientados a un tema/contexto específico."""
    product = repo.get(product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{product_id}' no encontrado.",
            details={"product_id": product_id},
        )

    try:
        from src.tiktok_shop.services.hooks_generator import generate_themed_hooks

        result = generate_themed_hooks(
            product,
            theme=payload.theme,
            n=payload.n,
        )
    except Exception as e:
        raise ValidationError(
            f"Error generando hooks temáticos: {e}",
            details={"product_id": product_id, "theme": payload.theme[:60]},
        )

    return HookThemedResponse(
        theme_interpretation=result.get("theme_interpretation", ""),
        hooks=[
            HookThemed(
                text=h.get("text", ""),
                angle=h.get("angle", ""),
                rationale=h.get("rationale", ""),
            )
            for h in (result.get("hooks") or [])
        ],
    )
