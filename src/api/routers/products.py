"""Endpoints CRUD de productos + fotos + análisis Gemini.

Este router NO ejecuta lógica de Atlas/Minimax/FFmpeg — solo persistencia
y orquestación de operaciones de catálogo. La generación de vídeos vive
en `src/queue/runners.py` y se expone en otro router (Fase 1B).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Header,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse

from src.api.config import APISettings, get_settings
from src.api.dependencies import get_current_user, get_product_repo
from src.api.exceptions import (
    DriveError,
    GeminiError,
    PhotoNotFoundError,
    ProductNotFoundError,
    UnauthorizedError,
    ValidationError,
)
from src.api.schemas.product import (
    NanoBananaPromptRequest,
    NanoBananaPromptResponse,
    PhotoLocation,
    PhotoOrigin,
    PhotoResponse,
    PhotoType,
    PhotoUpdateRequest,
    ProductCreate,
    ProductListResponse,
    ProductResponse,
    ProductUpdate,
    ReanalyzeResponse,
)
from src.tiktok_shop.config import (
    product_drive_folder,
    product_photos_generated_folder,
    product_photos_source_folder,
)
from src.tiktok_shop.models import Product
from src.tiktok_shop.models.product import (
    ProductPhoto,
    TikTokShopMeta,
    VideoConfig,
)
from src.tiktok_shop.repos import ProductRepo
from src.tiktok_shop.utils.validators import (
    validate_photo_extension,
    validate_photo_size,
)


router = APIRouter(
    prefix="/api/v1/products",
    tags=["products"],
    dependencies=[Depends(get_current_user)],
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_response(product: Product) -> ProductResponse:
    return ProductResponse.model_validate(product.model_dump())


def _photo_to_response(p: ProductPhoto, location: PhotoLocation) -> PhotoResponse:
    return PhotoResponse(
        id=p.filename,
        location=location,
        filename=p.filename,
        local_path=p.local_path,
        drive_file_id=p.drive_file_id,
        type=p.type,
        preferred_for_tiers=list(p.preferred_for_tiers or []),
        origin=p.origin,
        url_origin=p.url_origin,
        added_at=p.added_at,
        generation_prompt_used=p.generation_prompt_used,
        generated_at=p.generated_at,
        deleted=p.deleted,
    )


def _find_photo(product: Product, photo_id: str) -> tuple[ProductPhoto, PhotoLocation]:
    for p in product.photos.source:
        if p.filename == photo_id:
            return p, "source"
    for p in product.photos.generated:
        if p.filename == photo_id:
            return p, "generated"
    raise PhotoNotFoundError(
        f"Foto '{photo_id}' no existe en el producto.",
        details={"photo_id": photo_id},
    )


# ---------------------------------------------------------------------------
# GET /products
# ---------------------------------------------------------------------------
@router.get("", response_model=ProductListResponse)
def list_products(
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    category: str | None = Query(default=None),
    include_deleted: bool = Query(default=False),
) -> ProductListResponse:
    products = repo.list_all()
    if not include_deleted:
        products = [p for p in products if not p.deleted]
    if category:
        products = [p for p in products if p.category == category]
    total = len(products)
    page = products[offset : offset + limit]
    return ProductListResponse(
        items=[_to_response(p) for p in page],
        total=total,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# POST /products
# ---------------------------------------------------------------------------
@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    background: BackgroundTasks,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
) -> ProductResponse:
    slug = payload.resolve_slug()
    if repo.get_by_slug(slug) is not None:
        raise ValidationError(
            f"Ya existe un producto con slug '{slug}'.",
            details={"slug": slug},
        )

    drive_folder = product_drive_folder(slug)
    try:
        Path(drive_folder).mkdir(parents=True, exist_ok=True)
        Path(product_photos_source_folder(slug)).mkdir(parents=True, exist_ok=True)
        Path(product_photos_generated_folder(slug)).mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise DriveError(
            f"No se pudo crear la estructura de carpetas: {e}",
            details={"slug": slug, "path": drive_folder},
        )

    video_config = VideoConfig(
        default_tier=payload.default_tier,
        default_duration=payload.default_duration,
        default_resolution=payload.default_resolution,
    )
    product = Product(
        slug=slug,
        name=payload.name,
        brand=payload.brand,
        category=payload.category,
        subcategory=payload.subcategory,
        target_audience=payload.target_audience,
        key_features=payload.key_features,
        selling_points=payload.selling_points,
        tiktok_shop=TikTokShopMeta(**payload.tiktok_shop.model_dump()),
        video_config=video_config,
        drive_folder=drive_folder,
    )
    repo.save(product)

    if payload.analyze_with_gemini:
        background.add_task(_analyze_in_background, product.id)

    return _to_response(product)


def _analyze_in_background(product_id: str) -> None:
    """Hook para análisis Gemini async tras crear producto. Importa repo
    aquí para evitar problemas circulares y poder mockear en tests."""
    try:
        repo = ProductRepo()
        product = repo.get(product_id)
        if product is None:
            return
        photos, _ = product.photos.best_available()
        photo_paths = [p.local_path for p in photos if p.local_path and os.path.exists(p.local_path)]
        if not photo_paths:
            return
        from src.tiktok_shop.pipeline.analyzer import analyze_product

        result = analyze_product(photo_paths)
        _apply_analysis(product, result)
        repo.save(product)
    except Exception as e:
        print(f"[products.analyze_in_background] {product_id}: {e}")


def _apply_analysis(product: Product, result: dict) -> None:
    """Aplica el resultado de Gemini al modelo. Helper compartido por
    background task y endpoint /analyze síncrono."""
    if "key_features" in result:
        product.key_features = list(result.get("key_features") or [])
    if "suggested_audiences" in result:
        product.target_audience = list(result.get("suggested_audiences") or [])
    if "selling_points" in result:
        product.selling_points = list(result.get("selling_points") or [])
    if "category" in result and result["category"]:
        product.category = result["category"]
    if "subcategory" in result:
        product.subcategory = result.get("subcategory")
    if "has_complex_packaging_text" in result:
        product.video_config.has_complex_packaging = bool(
            result.get("has_complex_packaging_text")
        )
    if "needs_nano_banana_regeneration" in result:
        product.needs_nano_banana_regeneration = bool(
            result.get("needs_nano_banana_regeneration")
        )
    product.last_analyzed_at = _now_iso()


# ---------------------------------------------------------------------------
# GET /products/{id}
# ---------------------------------------------------------------------------
@router.get("/{product_id}", response_model=ProductResponse)
def get_product(
    product_id: str,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
) -> ProductResponse:
    product = repo.get(product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{product_id}' no encontrado.",
            details={"product_id": product_id},
        )
    return _to_response(product)


# ---------------------------------------------------------------------------
# PUT /products/{id}
# ---------------------------------------------------------------------------
@router.put("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: str,
    payload: ProductUpdate,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
) -> ProductResponse:
    product = repo.get(product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{product_id}' no encontrado.",
            details={"product_id": product_id},
        )

    data = payload.model_dump(exclude_unset=True)
    new_slug = data.pop("slug", None)
    if new_slug is not None and new_slug != product.slug:
        existing = repo.get_by_slug(new_slug)
        if existing is not None and existing.id != product.id:
            raise ValidationError(
                f"Ya existe otro producto con slug '{new_slug}'.",
                details={"slug": new_slug},
            )
        _rename_product_folder(product.slug, new_slug)
        repo.r.delete(f"{repo.SLUG_INDEX}{product.slug}")
        product.slug = new_slug
        product.drive_folder = product_drive_folder(new_slug)

    tiktok_shop_data = data.pop("tiktok_shop", None)
    if tiktok_shop_data is not None:
        product.tiktok_shop = TikTokShopMeta(**tiktok_shop_data)

    video_config_keys = {"default_tier", "default_duration", "default_resolution"}
    for key in list(data.keys()):
        if key in video_config_keys:
            setattr(product.video_config, key, data.pop(key))

    for key, value in data.items():
        setattr(product, key, value)

    repo.save(product)
    return _to_response(product)


def _rename_product_folder(old_slug: str, new_slug: str) -> None:
    old_path = Path(product_drive_folder(old_slug))
    new_path = Path(product_drive_folder(new_slug))
    if not old_path.exists():
        return
    if new_path.exists():
        raise DriveError(
            f"El destino ya existe: {new_path}",
            details={"old_slug": old_slug, "new_slug": new_slug},
        )
    try:
        old_path.rename(new_path)
    except OSError as e:
        raise DriveError(
            f"No se pudo renombrar la carpeta del producto: {e}",
            details={"old_slug": old_slug, "new_slug": new_slug},
        )


# ---------------------------------------------------------------------------
# DELETE /products/{id} — soft delete
# ---------------------------------------------------------------------------
@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: str,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
) -> Response:
    product = repo.get(product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{product_id}' no encontrado.",
            details={"product_id": product_id},
        )
    product.deleted = True
    repo.save(product)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# POST /products/{id}/photos
# ---------------------------------------------------------------------------
@router.post(
    "/{product_id}/photos",
    response_model=PhotoResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_photo(
    product_id: str,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
    file: Annotated[UploadFile, File(...)],
    location: Annotated[PhotoLocation, Form()] = "source",
    photo_type: Annotated[PhotoType | None, Form(alias="type")] = None,
    origin: Annotated[PhotoOrigin | None, Form()] = None,
    url_origin: Annotated[str | None, Form()] = None,
) -> PhotoResponse:
    product = repo.get(product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{product_id}' no encontrado.",
            details={"product_id": product_id},
        )

    filename = file.filename or ""
    ok, err = validate_photo_extension(filename)
    if not ok:
        raise ValidationError(err, details={"filename": filename})

    contents = await file.read()
    ok, err = validate_photo_size(len(contents))
    if not ok:
        raise ValidationError(err, details={"filename": filename, "size": len(contents)})

    if location == "generated" and photo_type is None:
        raise ValidationError(
            "El campo 'type' es obligatorio para fotos en 'generated'.",
            details={"location": "generated"},
        )

    folder = (
        product_photos_generated_folder(product.slug)
        if location == "generated"
        else product_photos_source_folder(product.slug)
    )
    try:
        Path(folder).mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise DriveError(f"No se pudo crear carpeta: {e}", details={"path": folder})

    safe_name = _next_unique_filename(folder, filename)
    dest = Path(folder) / safe_name
    try:
        dest.write_bytes(contents)
    except OSError as e:
        raise DriveError(
            f"No se pudo escribir la foto en disco: {e}",
            details={"path": str(dest)},
        )

    now = _now_iso()
    photo = ProductPhoto(
        filename=safe_name,
        local_path=str(dest),
        type=photo_type,
        origin=origin if location == "source" else None,
        url_origin=url_origin if location == "source" else None,
        added_at=now if location == "source" else None,
        generated_at=now if location == "generated" else None,
    )

    if location == "generated":
        product.photos.generated.append(photo)
    else:
        product.photos.source.append(photo)
    repo.save(product)
    return _photo_to_response(photo, location)


def _next_unique_filename(folder: str, filename: str) -> str:
    """Si ya existe `filename` en la carpeta, le añade un sufijo numérico
    para evitar pisar fotos. Útil cuando el frontend sube varias con el
    mismo nombre (ej. `image.jpg` desde drag&drop)."""
    base, ext = os.path.splitext(filename)
    safe_base = "".join(c for c in base if c.isalnum() or c in ("_", "-")) or "photo"
    candidate = f"{safe_base}{ext.lower()}"
    if not Path(folder, candidate).exists():
        return candidate
    suffix = uuid.uuid4().hex[:6]
    return f"{safe_base}_{suffix}{ext.lower()}"


# ---------------------------------------------------------------------------
# DELETE /products/{id}/photos/{photo_id}
# ---------------------------------------------------------------------------
@router.delete(
    "/{product_id}/photos/{photo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_photo(
    product_id: str,
    photo_id: str,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
) -> Response:
    product = repo.get(product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{product_id}' no encontrado.",
            details={"product_id": product_id},
        )
    photo, _ = _find_photo(product, photo_id)
    photo.deleted = True
    repo.save(product)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# GET /products/{id}/photos/{photo_id}/file — sirve el archivo (para <img>)
# ---------------------------------------------------------------------------
# Router separado sin auth global porque <img src> no puede enviar headers
# X-API-Key. Acepta `?api_key=...` query param como fallback.
photo_file_router = APIRouter(
    prefix="/api/v1/products",
    tags=["products"],
)


@photo_file_router.get("/{product_id}/photos/{photo_id}/file")
def get_photo_file(
    product_id: str,
    photo_id: str,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
    settings: Annotated[APISettings, Depends(get_settings)],
    api_key: Annotated[str | None, Query()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> FileResponse:
    if settings.api_key:
        provided = x_api_key or api_key
        if not provided or provided != settings.api_key:
            raise UnauthorizedError("API key inválida o ausente.")

    product = repo.get(product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{product_id}' no encontrado.",
            details={"product_id": product_id},
        )
    photo, location = _find_photo(product, photo_id)

    # `local_path` puede venir de otra máquina (VPS Linux ↔ Windows local) y
    # no existir aquí — reconstruimos siempre desde el slug + filename usando
    # el root actual.
    folder = (
        product_photos_generated_folder(product.slug)
        if location == "generated"
        else product_photos_source_folder(product.slug)
    )
    path = Path(folder) / photo.filename
    if not path.exists() or not path.is_file():
        # Fallback al path persistido por si algún flujo lo escribió fuera de
        # la convención estándar.
        if photo.local_path:
            fallback = Path(photo.local_path)
            if fallback.exists() and fallback.is_file():
                path = fallback
            else:
                raise PhotoNotFoundError(
                    f"Archivo no encontrado en disco: {path}",
                    details={"photo_id": photo_id, "path": str(path)},
                )
        else:
            raise PhotoNotFoundError(
                f"Archivo no encontrado en disco: {path}",
                details={"photo_id": photo_id, "path": str(path)},
            )

    ext = path.suffix.lower()
    media_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "application/octet-stream")
    return FileResponse(path=str(path), media_type=media_type, filename=path.name)


# ---------------------------------------------------------------------------
# PUT /products/{id}/photos/{photo_id}
# ---------------------------------------------------------------------------
@router.put(
    "/{product_id}/photos/{photo_id}",
    response_model=PhotoResponse,
)
def update_photo(
    product_id: str,
    photo_id: str,
    payload: PhotoUpdateRequest,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
) -> PhotoResponse:
    product = repo.get(product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{product_id}' no encontrado.",
            details={"product_id": product_id},
        )
    photo, location = _find_photo(product, photo_id)
    data = payload.model_dump(exclude_unset=True)
    if "type" in data:
        photo.type = data["type"]
    if "preferred_for_tiers" in data:
        photo.preferred_for_tiers = list(data["preferred_for_tiers"] or [])
    repo.save(product)
    return _photo_to_response(photo, location)


# ---------------------------------------------------------------------------
# POST /products/{id}/analyze
# ---------------------------------------------------------------------------
@router.post(
    "/{product_id}/analyze",
    response_model=ReanalyzeResponse,
)
def reanalyze_product(
    product_id: str,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
) -> ReanalyzeResponse:
    product = repo.get(product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{product_id}' no encontrado.",
            details={"product_id": product_id},
        )

    photos, _origin = product.photos.best_available()
    photo_paths = [
        p.local_path for p in photos
        if p.local_path and os.path.exists(p.local_path)
    ]
    if not photo_paths:
        raise ValidationError(
            "El producto no tiene fotos disponibles en disco para analizar.",
            details={"product_id": product_id},
        )

    try:
        from src.tiktok_shop.pipeline.analyzer import analyze_product

        result = analyze_product(photo_paths)
    except Exception as e:
        raise GeminiError(f"Análisis Gemini falló: {e}", details={"product_id": product_id})

    _apply_analysis(product, result)
    repo.save(product)

    return ReanalyzeResponse(
        product_id=product.id,
        analyzed_at=product.last_analyzed_at or _now_iso(),
        key_features=product.key_features,
        suggested_audiences=product.target_audience,
        selling_points=product.selling_points,
        has_complex_packaging_text=product.video_config.has_complex_packaging,
        needs_nano_banana_regeneration=product.needs_nano_banana_regeneration,
        warnings=list(result.get("warnings") or []),
        raw=result,
    )


# ---------------------------------------------------------------------------
# POST /products/{id}/nano-banana-prompt
# ---------------------------------------------------------------------------
@router.post(
    "/{product_id}/nano-banana-prompt",
    response_model=NanoBananaPromptResponse,
)
def generate_nano_banana_prompt(
    product_id: str,
    payload: NanoBananaPromptRequest,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
) -> NanoBananaPromptResponse:
    product = repo.get(product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{product_id}' no encontrado.",
            details={"product_id": product_id},
        )

    source_photos = [
        p.local_path for p in product.photos.source
        if not p.deleted and p.local_path and os.path.exists(p.local_path)
    ]

    description_parts = [product.name]
    if product.brand:
        description_parts.append(f"Marca: {product.brand}.")
    if product.selling_points:
        description_parts.append("Selling points: " + "; ".join(product.selling_points))
    description = " ".join(description_parts)

    try:
        from src.tiktok_shop.pipeline.nano_banana_prompt_generator import (
            generate_nano_banana_prompt as gen,
        )

        prompt_text = gen(
            product_name=product.name,
            product_description=description,
            use_cases=list(payload.photo_types_wanted),
            n_angles=payload.n_angles,
            photo_paths=source_photos or None,
        )
    except Exception as e:
        raise GeminiError(
            f"Generación de prompt Nano Banana falló: {e}",
            details={"product_id": product_id},
        )

    instructions = (
        "1. Abre Gemini chat con modelo Nano Banana 2.\n"
        "2. Sube las fotos source del producto.\n"
        "3. Pega este prompt en el chat.\n"
        "4. Guarda las imágenes generadas y súbelas al endpoint "
        "POST /products/{id}/photos con location=generated."
    )
    return NanoBananaPromptResponse(
        product_id=product.id,
        prompt=prompt_text,
        instructions=instructions,
    )
