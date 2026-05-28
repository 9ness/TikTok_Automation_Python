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
    AnalyzeUrlPreviewRequest,
    AnalyzeUrlPreviewResponse,
    BulkStyleRequest,
    BulkStyleResponse,
    CommitImportedPhotosRequest,
    CommitImportedPhotosResponse,
    GeneratePresetsRequest,
    GeneratePresetsResponse,
    GenerateVariantsRequest,
    GenerateVariantsResponse,
    PresetGenStatusResponse,
    VariantMeta,
    GoogleImageSearchRequest,
    GoogleImageSearchResponse,
    GoogleImageSearchResultItem,
    ImportPhotosFromUrlsRequest,
    ImportPhotosFromUrlsResponse,
    NanoBananaPromptRequest,
    NanoBananaPromptResponse,
    PhotoCandidateGrade,
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
    VideoPresetResponse,
    VideoPresetUpdateRequest,
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
        language=payload.language,
        tiktok_shop=TikTokShopMeta(**payload.tiktok_shop.model_dump()),
        video_config=video_config,
        drive_folder=drive_folder,
    )

    # Auto-descarga de la `og:image` detectada al pegar URL en el form
    # crear-producto. Best-effort: si falla (URL caída, content-type
    # raro, lo que sea) el producto YA está creado, el usuario sube la
    # foto a mano luego. Nunca aborta la creación.
    if payload.image_url_to_download:
        try:
            from src.tiktok_shop.utils.photo_downloader import (
                download_image_to_product,
            )
            photo = download_image_to_product(
                product_slug=slug,
                image_url=payload.image_url_to_download,
                photo_type="packshot",
                origin="tiktok_shop_url",
            )
            if photo is not None:
                product.photos.source.append(photo)
        except Exception as e:
            # Log y seguimos — la creación del producto tiene prioridad
            import logging
            logging.getLogger("api.products").warning(
                "[create_product] download_image_to_product falló: %s", e,
            )

    repo.save(product)

    if payload.analyze_with_gemini:
        background.add_task(_analyze_in_background, product.id)

    return _to_response(product)


def _build_analyzer_context(product: Product) -> str:
    """Construye el `extra_context` para `analyze_product` con la info
    que el user ya tiene metida en el producto (nombre, marca, categoría).
    SIN esto, Gemini Vision solo ve las fotos y aluciña — ej. silicona
    translúcida → parche capilar. Con esto, ANCLA la inferencia al
    contexto real del producto.

    Además, si el producto tiene URL TikTok Shop, intenta hacer scrape
    en best-effort para extraer la descripción real del producto (la
    misma que pondría el vendedor). Esto da MUCHO más contexto a
    Gemini que solo el nombre, eliminando casi todas las alucinaciones.
    """
    parts: list[str] = []
    if product.name:
        parts.append(f"Product name: {product.name}")
    if product.brand:
        parts.append(f"Brand: {product.brand}")
    if product.category:
        parts.append(f"Category (user-defined): {product.category}")
    if product.subcategory:
        parts.append(f"Subcategory: {product.subcategory}")

    # Best-effort: scrape la URL TikTok Shop para coger la descripción.
    # Timeout corto (~6s) y nunca rompe el análisis si falla. La
    # descripción suele venir en og:description y es muy descriptiva
    # ("Pezoneras de silicona invisibles reutilizables triangulares...").
    url = (product.tiktok_shop.product_url if product.tiktok_shop else "") or ""
    if url:
        parts.append(f"TikTok Shop URL: {url}")
        try:
            from src.tiktok_shop.utils.url_scraper import scrape_product_url
            scraped = scrape_product_url(url, use_gemini=False)
            desc = (scraped.get("description") or "").strip()
            if desc:
                # Limitar a 600 chars para no inflar el prompt con HTML largo
                parts.append(f"Official product description: {desc[:600]}")
        except Exception:
            # Scrape opcional, falla silenciosa.
            pass

    if not parts:
        return ""
    return (
        "TRUST this product context over visual inference if conflict. "
        "Visual cues alone can mislead (e.g. translucent silicone could "
        "be many things). Use the name/brand/category/description as "
        "ground truth. "
        + " | ".join(parts)
    )


def _resolve_photo_paths(product: Product) -> list[str]:
    """Devuelve paths absolutos de las fotos del producto que existan en
    disco. Resuelve el caso Redis-compartido entre Windows local y Linux
    VPS: si `local_path` no existe, reconstruye desde slug + filename
    usando los helpers de config (respetan `TIKTOK_SHOP_ROOT_PATH` del
    entorno actual). Mismo patrón que `_resolve_photo_path` del runner."""
    photos_list, source = product.photos.best_available()
    paths: list[str] = []
    for ph in photos_list:
        # 1) Probar el local_path persistido tal cual.
        if ph.local_path and os.path.exists(ph.local_path):
            paths.append(ph.local_path)
            continue
        # 2) Reconstruir desde slug + filename + carpeta del entorno actual.
        folder = (
            product_photos_generated_folder(product.slug)
            if source == "generated"
            else product_photos_source_folder(product.slug)
        )
        candidate = os.path.join(folder, ph.filename)
        if os.path.exists(candidate):
            paths.append(candidate)
    return paths


def _analyze_in_background(product_id: str) -> None:
    """Hook para análisis Gemini async tras crear producto. Importa repo
    aquí para evitar problemas circulares y poder mockear en tests."""
    try:
        repo = ProductRepo()
        product = repo.get(product_id)
        if product is None:
            return
        photo_paths = _resolve_photo_paths(product)
        if not photo_paths:
            return
        from src.tiktok_shop.pipeline.analyzer import analyze_product

        result = analyze_product(
            photo_paths,
            extra_context=_build_analyzer_context(product),
        )
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
    if "photos_quality_assessment" in result:
        q = str(result.get("photos_quality_assessment") or "").lower()
        if q in ("high", "medium", "low"):
            product.photos_quality_assessment = q
    if "warnings" in result:
        product.last_analysis_warnings = [
            str(w)[:300] for w in (result.get("warnings") or [])
        ][:10]
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
    """Soft-delete del producto en Redis + borra recursivamente la
    carpeta del producto en Drive (TIKTOK_SHOP/_products/<slug>/).

    El borrado de la carpeta es best-effort: si falla (Drive no
    sincronizado, permisos, lo que sea) sólo logueamos warning y
    devolvemos 204 igual — el producto ya no aparece en el listado.
    Drive Desktop sincroniza el delete a la papelera de Google Drive
    (~30 días recuperable). El modelo Redis queda como `deleted=true`
    por si hace falta auditoría histórica.
    """
    import logging
    import shutil

    product = repo.get(product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{product_id}' no encontrado.",
            details={"product_id": product_id},
        )

    # 1) Borrar carpeta del producto en Drive (best-effort)
    drive_folder = product.drive_folder or product_drive_folder(product.slug)
    if drive_folder:
        try:
            folder_path = Path(drive_folder)
            if folder_path.exists() and folder_path.is_dir():
                shutil.rmtree(str(folder_path), ignore_errors=True)
                logging.getLogger("api.products").info(
                    "[delete_product] carpeta Drive borrada: %s", folder_path,
                )
        except Exception as e:
            logging.getLogger("api.products").warning(
                "[delete_product] no se pudo borrar carpeta Drive %s: %s",
                drive_folder, e,
            )

    # 2) Soft-delete en Redis
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
    """HARD delete: elimina la foto del array source/generated y guarda.
    Antes era soft-delete (`deleted=true`) pero la UI mostraba la foto
    de vuelta tras refetch — soft-delete no se reflejaba bien en algún
    paso de la cadena. Hard delete garantiza desaparición. El archivo en
    disco se mantiene (no borrado físico) por si hay jobs en cola que la
    necesitan."""
    product = repo.get(product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{product_id}' no encontrado.",
            details={"product_id": product_id},
        )

    # Localizar y eliminar de source o generated (lo que matchee).
    removed = False
    for i, p in enumerate(product.photos.source):
        if p.filename == photo_id:
            product.photos.source.pop(i)
            removed = True
            break
    if not removed:
        for i, p in enumerate(product.photos.generated):
            if p.filename == photo_id:
                product.photos.generated.pop(i)
                removed = True
                break
    if not removed:
        raise PhotoNotFoundError(
            f"Foto '{photo_id}' no existe en el producto.",
            details={"photo_id": photo_id},
        )
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
    # Cache 1h en navegador — las fotos son inmutables por filename. Sin esto
    # cada `<img>` o descarga vuelve a pegar contra el VPS (servido desde
    # Drive sync local = lento).
    return FileResponse(
        path=str(path),
        media_type=media_type,
        filename=path.name,
        headers={"Cache-Control": "public, max-age=3600"},
    )


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
# ---------------------------------------------------------------------------
# POST /products/analyze-url-preview
# ---------------------------------------------------------------------------
# Endpoint STATELESS — no toca Redis ni Drive. El usuario pega una URL
# de TikTok Shop en el form de Identidad y este endpoint devuelve los
# campos detectados (name/brand/category/price_eur/…) para autopoblar
# el form. El usuario revisa y guarda con el PUT habitual.
@router.post(
    "/analyze-url-preview",
    response_model=AnalyzeUrlPreviewResponse,
)
def analyze_url_preview(payload: AnalyzeUrlPreviewRequest) -> AnalyzeUrlPreviewResponse:
    from src.cost_tracking import finalize_and_persist, start_job
    from src.tiktok_shop.utils.url_scraper import (
        extract_from_text,
        scrape_product_url,
    )

    # Job adhoc para capturar el coste de las llamadas Gemini que haga
    # el scraper / extract_from_text. Sin user/product_id porque el
    # producto aún no existe (este endpoint se llama desde el dialog
    # de crear).
    start_job(
        job_id=f"analyze_url_{uuid.uuid4().hex[:12]}",
        program="tiktok_shop",
        mode="url_analysis",
        title="Analyze URL/text (product create)",
    )

    url = (payload.url or "").strip()
    raw_text = (payload.raw_text or "").strip()

    if not url and not raw_text:
        raise ValidationError(
            "Necesito al menos una URL o un texto del producto.",
            details={},
        )
    if url and not url.startswith(("http://", "https://")):
        raise ValidationError(
            "La URL debe empezar por http:// o https://",
            details={"url": url},
        )

    # Combinamos las 2 vías. Lo encontrado por scraping va primero; lo
    # del raw_text sólo rellena lo que falte (el user pegó texto bueno
    # pero scraping ya encontró algo más fiable estructuralmente).
    scraped: dict = {}
    warnings: list[str] = []

    if url:
        scraped = scrape_product_url(url, use_gemini=payload.use_gemini)
        warnings.extend(scraped.get("warnings") or [])

    if raw_text:
        extra = extract_from_text(raw_text)
        warnings.extend(extra.get("warnings") or [])
        # Solo rellenamos campos que el scraper no encontró
        for k, v in extra.items():
            if k == "warnings":
                continue
            if v and not scraped.get(k):
                scraped[k] = v

    # Sanea price_eur a float si vino como string
    raw_price = scraped.get("price_eur")
    price: float | None = None
    if raw_price is not None:
        try:
            price = float(raw_price)
        except (TypeError, ValueError):
            price = None

    response = AnalyzeUrlPreviewResponse(
        name=scraped.get("name"),
        brand=scraped.get("brand"),
        description=scraped.get("description"),
        category=(scraped.get("category") or "").lower() or None,
        subcategory=scraped.get("subcategory"),
        price_eur=price,
        currency=scraped.get("currency"),
        image_url=scraped.get("image_url"),
        warnings=warnings,
    )
    # Cerrar el job adhoc y persistir el coste (Gemini tokens).
    try:
        finalize_and_persist()
    except Exception:
        pass
    return response


# ---------------------------------------------------------------------------
# POST /products/{id}/import-photos-from-urls
# ---------------------------------------------------------------------------
# Workflow: el user pega N URLs de fotos del producto (las copia desde
# Google Images, la web de la marca, donde sea). Descargamos cada una a
# temp_work/, pasamos por Gemini Vision para puntuar 0-10 + detectar
# tipo (packshot/lifestyle/…) + detectar problemas (watermark, collage,
# texto promo). Devolvemos los resultados sin guardar — el frontend
# muestra el grid de candidatas con scores y el user marca cuáles quiere.
# Luego llamará a /commit-imported-photos.
def _photo_candidate_dir(product_id: str) -> Path:
    """temp_work/product_photo_candidates/{product_id}/"""
    from src.tiktok_shop.config import resolve_shop_root  # lazy
    base = Path("temp_work") / "product_photo_candidates" / product_id
    base.mkdir(parents=True, exist_ok=True)
    return base


@router.post(
    "/{product_id}/import-photos-from-urls",
    response_model=ImportPhotosFromUrlsResponse,
)
def import_photos_from_urls(
    product_id: str,
    payload: ImportPhotosFromUrlsRequest,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
) -> ImportPhotosFromUrlsResponse:
    from src.cost_tracking import finalize_and_persist, start_job
    from src.tiktok_shop.pipeline.photo_grader import grade_photo
    from src.tiktok_shop.utils.photo_downloader import download_image_to_product

    product = repo.get(product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{product_id}' no encontrado.",
            details={"product_id": product_id},
        )

    # Job adhoc para que record_gemini se acumule
    start_job(
        job_id=f"import_photos_{uuid.uuid4().hex[:12]}",
        program="tiktok_shop",
        mode="photo_grading",
        title=f"Import photos: {product.slug}",
        product_id=product_id,
    )

    candidates_dir = _photo_candidate_dir(product_id)
    candidates: list[PhotoCandidateGrade] = []

    # Fotos source ya verificadas del producto = ground truth para detectar
    # "producto diferente". Pasamos hasta 2 (más infla el cost del Gemini).
    reference_paths: list[str] = []
    for p in product.photos.source:
        if p.deleted or not p.local_path:
            continue
        if not os.path.exists(p.local_path):
            continue
        reference_paths.append(p.local_path)
        if len(reference_paths) >= 2:
            break

    import requests as _rq

    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    for url in payload.urls:
        url = url.strip()
        if not url:
            continue
        candidate_id = uuid.uuid4().hex[:12]

        # 1) Descargar al temp del candidato. Reusamos un mini-helper
        # inline porque queremos respetar la URL original y guardarla
        # con el `candidate_id` (no con la nomenclatura final de
        # `download_image_to_product`, que es para fotos definitivas).
        try:
            r = _rq.get(
                url,
                headers={"User-Agent": _UA},
                timeout=20,
                allow_redirects=True,
                stream=True,
            )
            if r.status_code >= 400:
                candidates.append(PhotoCandidateGrade(
                    candidate_id=candidate_id, url=url,
                    score=0, type="other",
                    is_same_product=True,
                    same_product_confidence="no_reference",
                    is_branded=False, has_text_overlay=False,
                    has_watermark=False, is_collage=False,
                    shows_product_clearly=False, reasons="",
                    preview_url="",
                    error=f"HTTP {r.status_code} al descargar",
                ))
                continue
            content_type = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            ext = {
                "image/jpeg": ".jpg", "image/jpg": ".jpg",
                "image/png": ".png", "image/webp": ".webp",
                "image/gif": ".gif",
            }.get(content_type, ".jpg")
            chunks: list[bytes] = []
            total = 0
            for chunk in r.iter_content(64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > 10 * 1024 * 1024:
                    raise IOError("Imagen > 10MB, cancelo")
                chunks.append(chunk)
            data = b"".join(chunks)
            if not data:
                raise IOError("Descarga vacía")
            dest = candidates_dir / f"{candidate_id}{ext}"
            dest.write_bytes(data)
        except Exception as e:
            candidates.append(PhotoCandidateGrade(
                candidate_id=candidate_id, url=url,
                score=0, type="other",
                is_same_product=True,
                same_product_confidence="no_reference",
                is_branded=False, has_text_overlay=False,
                has_watermark=False, is_collage=False,
                shows_product_clearly=False, reasons="",
                preview_url="",
                error=f"Descarga falló: {e}",
            ))
            continue

        # 2) Grade con Gemini Vision — pasamos las fotos source como
        # referencia para que Gemini detecte si la candidata es el MISMO
        # producto o solo uno parecido (resuelve el problema del usuario
        # con productos similares de otras marcas / variantes).
        grade = grade_photo(
            str(dest),
            product_name=product.name,
            product_brand=product.brand or "",
            product_category=product.category or "",
            reference_image_paths=reference_paths,
        )
        candidates.append(PhotoCandidateGrade(
            candidate_id=candidate_id,
            url=url,
            score=int(grade["score"]),
            type=str(grade["type"]),
            is_same_product=bool(grade.get("is_same_product", True)),
            same_product_confidence=str(grade.get("same_product_confidence", "no_reference")),
            is_duplicate_of_reference=bool(grade.get("is_duplicate_of_reference", False)),
            is_branded=bool(grade["is_branded"]),
            has_text_overlay=bool(grade["has_text_overlay"]),
            has_watermark=bool(grade["has_watermark"]),
            is_collage=bool(grade["is_collage"]),
            shows_product_clearly=bool(grade["shows_product_clearly"]),
            reasons=str(grade["reasons"]),
            preview_url=f"/api/v1/products/{product_id}/photo-candidates/{candidate_id}{ext}",
        ))

    try:
        finalize_and_persist()
    except Exception:
        pass

    # Ordena por score desc para que las mejores aparezcan arriba en la UI
    candidates.sort(key=lambda c: c.score, reverse=True)
    return ImportPhotosFromUrlsResponse(
        product_id=product_id,
        candidates=candidates,
    )


@photo_file_router.get(
    "/{product_id}/photo-candidates/{filename}",
    include_in_schema=False,
)
def serve_photo_candidate(
    product_id: str,
    filename: str,
    settings: Annotated[APISettings, Depends(get_settings)],
    api_key: Annotated[str | None, Query()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
):
    """Sirve los temp files de los candidatos para que la UI los muestre
    como `<img src>` preview. Vive en `photo_file_router` (sin auth global
    por header) para aceptar `?api_key=...` query — los <img> no pueden
    mandar X-API-Key. En producción la API_KEY es obligatoria, en local
    si APISettings.api_key vacío se sirve sin validar."""
    # Mismo patrón que get_photo_file: si la app tiene API_KEY definida,
    # exigir que el caller la mande por header o query.
    if settings.api_key:
        provided = x_api_key or api_key
        if not provided or provided != settings.api_key:
            raise UnauthorizedError("API key inválida o ausente.")

    # Sanitización: rechazar paths fuera del temp dir.
    if "/" in filename or "\\" in filename or ".." in filename:
        raise ValidationError("filename inválido", details={"filename": filename})
    path = _photo_candidate_dir(product_id) / filename
    if not path.exists():
        raise PhotoNotFoundError(
            f"Candidate {filename} no existe.",
            details={"product_id": product_id, "filename": filename},
        )
    return FileResponse(str(path))


@router.post(
    "/{product_id}/search-photos-on-google",
    response_model=GoogleImageSearchResponse,
)
def search_photos_on_google(
    product_id: str,
    payload: GoogleImageSearchRequest,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
) -> GoogleImageSearchResponse:
    """Busca imágenes en Google CSE para autorellenar la textarea de URLs.

    Requiere `GOOGLE_CSE_API_KEY` + `GOOGLE_CSE_ID` en .env. Si no están
    set, devuelve `configured: false` y un mensaje de cómo configurarlo.
    """
    from src.tiktok_shop.utils.image_search import (
        ddg_image_search,
        google_cse_is_configured,
        google_image_search,
        search_product_images,
    )

    product = repo.get(product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{product_id}' no encontrado.",
            details={"product_id": product_id},
        )

    # Query default: marca + nombre. El user puede override con payload.query.
    # Evitamos duplicar la marca si el name ya empieza con ella (ej. brand
    # "Freshly" + name "Freshly - Crema..." → solo "Freshly - Crema...").
    if payload.query and payload.query.strip():
        query = payload.query.strip()
    else:
        brand = (product.brand or "").strip()
        name = (product.name or "").strip()
        if brand and name and not name.lower().startswith(brand.lower()):
            query = f"{brand} {name}"
        else:
            query = name or brand or product.slug

    provider_pref = (payload.provider or "auto").lower()
    raw_results: list[dict] = []
    provider_used = "none"

    if provider_pref == "google":
        # Modo forzado — falla si CSE no configurado
        if not google_cse_is_configured():
            return GoogleImageSearchResponse(
                configured=False,
                provider_used="none",
                query_used=query,
                results=[],
                hint=(
                    "Google CSE no configurado. Define GOOGLE_CSE_API_KEY "
                    "y GOOGLE_CSE_ID en .env. Por defecto se usa DuckDuckGo."
                ),
            )
        raw_results = google_image_search(query, num=payload.num)
        provider_used = "google_cse" if raw_results else "none"
    elif provider_pref == "ddg":
        raw_results = ddg_image_search(query, max_results=payload.num)
        provider_used = "ddg" if raw_results else "none"
    else:
        # auto: DDG primero, fallback CSE si está disponible
        provider_used, raw_results = search_product_images(
            query, num=payload.num, prefer_google=False,
        )

    return GoogleImageSearchResponse(
        configured=True,
        provider_used=provider_used,
        query_used=query,
        results=[
            GoogleImageSearchResultItem(
                link=r["link"], title=r.get("title", ""),
            )
            for r in raw_results
        ],
        hint=(
            "" if raw_results else f"Sin resultados para '{query}'."
        ),
    )


@router.post(
    "/{product_id}/commit-imported-photos",
    response_model=CommitImportedPhotosResponse,
)
def commit_imported_photos(
    product_id: str,
    payload: CommitImportedPhotosRequest,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
) -> CommitImportedPhotosResponse:
    """Mueve los candidatos seleccionados de temp_work a la carpeta de
    fotos source del producto y los registra en `product.photos.source`.
    """
    import shutil

    product = repo.get(product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{product_id}' no encontrado.",
            details={"product_id": product_id},
        )

    candidates_dir = _photo_candidate_dir(product_id)
    source_folder = Path(product_photos_source_folder(product.slug))
    source_folder.mkdir(parents=True, exist_ok=True)

    skipped: list[str] = []
    saved = 0
    for item in payload.candidates:
        # Buscar el file en temp (cualquier extensión)
        matches = list(candidates_dir.glob(f"{item.candidate_id}.*"))
        if not matches:
            skipped.append(item.candidate_id)
            continue
        src_path = matches[0]
        ext = src_path.suffix.lower()
        stamp = _now_iso().replace(":", "").replace("-", "")[:14]
        safe_name = f"import_{stamp}_{item.candidate_id}{ext}"
        dest_path = source_folder / safe_name
        try:
            shutil.move(str(src_path), str(dest_path))
        except OSError as e:
            skipped.append(item.candidate_id)
            continue

        photo = ProductPhoto(
            filename=safe_name,
            local_path=str(dest_path),
            type=item.type or "packshot",
            origin="internet",
            added_at=_now_iso(),
        )
        product.photos.source.append(photo)
        saved += 1

    if saved > 0:
        repo.save(product)

    return CommitImportedPhotosResponse(
        product_id=product_id,
        saved_count=saved,
        skipped=skipped,
    )


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

    photo_paths = _resolve_photo_paths(product)
    if not photo_paths:
        raise ValidationError(
            "El producto no tiene fotos disponibles en disco para analizar. "
            "Verifica que Drive Desktop está sincronizando "
            f"TIKTOK_SHOP/_products/{product.slug}/.",
            details={"product_id": product_id, "slug": product.slug},
        )

    try:
        from src.tiktok_shop.pipeline.analyzer import analyze_product

        result = analyze_product(
            photo_paths,
            extra_context=_build_analyzer_context(product),
        )
    except Exception as e:
        raise GeminiError(f"Análisis Gemini falló: {e}", details={"product_id": product_id})

    _apply_analysis(product, result)

    # ─── Investigación profunda: reviews + TikTok virales + análisis Gemini ───
    # Adicional al análisis de fotos. Rellena `product.research_context`
    # con pains/benefits/objections de reviews reales y patrones de los
    # top vídeos virales de TikTok del producto. Los prompts directores
    # leen esto al generar guiones para afinar hooks + estructura.
    # Best-effort: si Apify/Gemini grounded search falla, el análisis
    # de fotos ya se aplicó arriba, así que el producto queda OK.
    try:
        from src.tiktok_shop.services.research_service import deep_research_product

        research = deep_research_product(
            product,
            max_videos_to_analyze=5,
            max_tiktok_search_results=10,
            log_callback=lambda m: print(f"[research {product.id[:8]}] {m}"),
        )
        product.research_context = research
    except Exception as e:
        # No abortamos el reanálisis si la research falla. Logueamos y
        # seguimos — el análisis de fotos ya está aplicado.
        print(f"[reanalyze {product.id[:8]}] research falló: {e}")

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


# ---------------------------------------------------------------------------
# Video presets — blueprints precocinados de vídeo por producto
# ---------------------------------------------------------------------------
def _preset_to_response(p) -> VideoPresetResponse:
    return VideoPresetResponse(**p.model_dump())


@router.get(
    "/{product_id}/video-presets",
    response_model=list[VideoPresetResponse],
)
def list_video_presets(
    product_id: str,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
) -> list[VideoPresetResponse]:
    product = repo.get(product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{product_id}' no encontrado.",
            details={"product_id": product_id},
        )
    return [_preset_to_response(p) for p in product.video_presets]


def _generate_presets_background(
    *,
    product_id: str,
    gen_id: str,
    kind: str,
    n_music: int,
    n_scripted: int,
    replace_existing: bool,
) -> None:
    """Función que corre en BackgroundTasks. Actualiza el tracker en
    Redis por stages para que el frontend pueda mostrar progress.

    NO usar `get_product_repo` aquí — es una FastAPI dependency que
    necesita la request scope (redis injection). Construimos `ProductRepo()`
    directo, igual que `_analyze_in_background`.
    """
    from src.cost_tracking import finalize_and_persist, get_active, start_job
    from src.tiktok_shop.pipeline.preset_generator import (
        _generate_music,
        _generate_scripted,
    )
    from src.tiktok_shop.services import preset_gen_tracker

    def _current_cost() -> float:
        """Lee el coste acumulado del job activo en USD. 0.0 si no hay
        tracker activo (no debería pasar — `start_job` corre justo
        antes). Solo se usa para reportarlo al frontend."""
        job = get_active()
        return float(job.total_usd) if job is not None else 0.0

    try:
        repo = ProductRepo()
        product = repo.get(product_id)
    except Exception as e:
        preset_gen_tracker.update(
            gen_id, stage="error", error=f"No se pudo cargar el producto: {e}",
        )
        return
    if product is None:
        preset_gen_tracker.update(
            gen_id, stage="error", error=f"Producto {product_id} no encontrado",
        )
        return

    start_job(
        job_id=f"presets_{gen_id}",
        program="tiktok_shop",
        mode="preset_generation",
        title=f"Generate presets: {product.slug} · {kind}",
        product_id=product_id,
    )

    all_presets = []
    all_warnings: list[str] = []
    try:
        # ── Música ──
        if kind in ("music", "both"):
            preset_gen_tracker.update(
                gen_id, stage="generating_music", percent=5,
            )
            try:
                music_presets, lib_warnings = _generate_music(product, n=n_music)
                all_presets.extend(music_presets)
                all_warnings.extend(lib_warnings)
                preset_gen_tracker.update(
                    gen_id,
                    percent=50 if kind == "both" else 80,
                    created_count=len(all_presets),
                    cost_usd=_current_cost(),
                )
            except Exception as e:
                all_warnings.append(f"Music director falló: {e}")

        # ── Scripted ──
        if kind in ("scripted", "both"):
            preset_gen_tracker.update(
                gen_id, stage="generating_scripted",
                percent=55 if kind == "both" else 5,
            )
            try:
                scripted_presets = _generate_scripted(product, n=n_scripted)
                all_presets.extend(scripted_presets)
                preset_gen_tracker.update(
                    gen_id, percent=90,
                    created_count=len(all_presets),
                    cost_usd=_current_cost(),
                )
            except Exception as e:
                all_warnings.append(f"Scripted director falló: {e}")

        # ── Persistir ──
        preset_gen_tracker.update(gen_id, stage="saving", percent=95)
        if replace_existing:
            sources_to_drop = set()
            if kind in ("music", "both"):
                sources_to_drop.add("music_bof")
            if kind in ("scripted", "both"):
                sources_to_drop.add("scripted_bof")
            product.video_presets = [
                p for p in product.video_presets if p.source not in sources_to_drop
            ]
        product.video_presets.extend(all_presets)
        product.touch()
        repo.save(product)

        preset_gen_tracker.update(
            gen_id, stage="done", percent=100,
            created_count=len(all_presets), warnings=all_warnings,
            cost_usd=_current_cost(),
        )
    except Exception as e:
        preset_gen_tracker.update(gen_id, stage="error", error=str(e))
        return
    finally:
        try:
            finalize_and_persist()
        except Exception:
            pass


@router.post(
    "/{product_id}/video-presets/generate",
    response_model=GeneratePresetsResponse,
)
def generate_video_presets(
    product_id: str,
    payload: GeneratePresetsRequest,
    background: BackgroundTasks,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
) -> GeneratePresetsResponse:
    """ASÍNCRONO. Lanza la generación en background y devuelve gen_id
    al instante. La UI hace polling de /preset-gen-status/{gen_id} para
    mostrar progress y refrescar la lista cuando termine. El gen_id se
    persiste en localStorage en el frontend, así un refresh del navegador
    no pierde la generación.
    """
    from src.tiktok_shop.services import preset_gen_tracker

    product = repo.get(product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{product_id}' no encontrado.",
            details={"product_id": product_id},
        )

    expected = 0
    if payload.kind in ("music", "both"):
        expected += payload.n_music
    if payload.kind in ("scripted", "both"):
        expected += payload.n_scripted

    gen_id = preset_gen_tracker.create(
        product_id=product_id,
        kind=payload.kind,
        expected_count=expected,
    )

    background.add_task(
        _generate_presets_background,
        product_id=product_id,
        gen_id=gen_id,
        kind=payload.kind,
        n_music=payload.n_music,
        n_scripted=payload.n_scripted,
        replace_existing=payload.replace_existing,
    )

    return GeneratePresetsResponse(
        product_id=product_id,
        gen_id=gen_id,
        stage="started",
        created_count=0,
        presets=[],
        warnings=[],
    )


@router.get(
    "/{product_id}/preset-gen-status/{gen_id}",
    response_model=PresetGenStatusResponse,
)
def get_preset_gen_status(
    product_id: str,
    gen_id: str,
) -> PresetGenStatusResponse:
    """Devuelve el progreso actual de la generación. La UI hace polling
    cada 2s hasta ver stage=done o error."""
    from src.tiktok_shop.services import preset_gen_tracker

    state = preset_gen_tracker.get(gen_id)
    if state is None:
        raise PhotoNotFoundError(
            f"Generación {gen_id} no encontrada o expirada.",
            details={"product_id": product_id, "gen_id": gen_id},
        )
    return PresetGenStatusResponse(**state)


# IMPORTANTE: `/bulk-style` debe ir ANTES que `/{preset_id}` porque FastAPI
# matchea rutas en orden de declaración — si `/{preset_id}` va primero,
# captura "bulk-style" como un preset_id y devuelve 404.
@router.patch(
    "/{product_id}/video-presets/bulk-style",
    response_model=BulkStyleResponse,
)
def bulk_apply_preset_style(
    product_id: str,
    payload: BulkStyleRequest,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
) -> BulkStyleResponse:
    """Aplica un patch de estilo VISUAL a TODOS los presets del producto
    (o a un scope). NO toca campos de posición — sólo color, fuente,
    tamaño, animación, etc. Devuelve cuántos presets se modificaron.

    Whitelist defensiva: incluso si el cliente envía `position` o
    `enabled`, los ignoramos para no romper layouts existentes ni
    habilitar subs en presets `music`. `position_y_pct` SÍ se permite —
    es el override fino del Y que el user ajusta en el bulk dialog.
    """
    product = repo.get(product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{product_id}' no encontrado.",
            details={"product_id": product_id},
        )

    if payload.text_overlay_style is None and payload.subtitle_style is None:
        raise ValidationError(
            "Debes enviar text_overlay_style o subtitle_style (o ambos).",
            details={},
        )

    OVERLAY_BLOCKED = {"position"}
    SUBS_BLOCKED = {"position", "enabled"}

    overlay_patch = {
        k: v
        for k, v in (payload.text_overlay_style or {}).items()
        if k not in OVERLAY_BLOCKED
    }
    subs_patch = {
        k: v
        for k, v in (payload.subtitle_style or {}).items()
        if k not in SUBS_BLOCKED
    }

    updated = 0
    skipped = 0
    total = len(product.video_presets)
    for preset in product.video_presets:
        if payload.scope == "music" and preset.kind != "music":
            skipped += 1
            continue
        if payload.scope == "scripted" and preset.kind != "scripted":
            skipped += 1
            continue
        if (
            payload.scope == "viral_replica"
            and getattr(preset, "source", "") != "viral_replica"
        ):
            skipped += 1
            continue

        changed = False
        if overlay_patch and preset.text_overlay_style is not None:
            for k, v in overlay_patch.items():
                if hasattr(preset.text_overlay_style, k):
                    setattr(preset.text_overlay_style, k, v)
                    changed = True
        if subs_patch and preset.subtitle_style is not None:
            subs_enabled = getattr(preset.subtitle_style, "enabled", False)
            if preset.kind == "music" and not subs_enabled:
                skipped += 1
                continue
            for k, v in subs_patch.items():
                if hasattr(preset.subtitle_style, k):
                    setattr(preset.subtitle_style, k, v)
                    changed = True
        if changed:
            from datetime import datetime, timezone
            preset.updated_at = datetime.now(timezone.utc).isoformat()
            updated += 1
        else:
            skipped += 1

    if updated > 0:
        product.touch()
        repo.save(product)
    return BulkStyleResponse(
        updated_count=updated,
        skipped_count=skipped,
        total_presets=total,
    )


@router.patch(
    "/{product_id}/video-presets/{preset_id}",
    response_model=VideoPresetResponse,
)
def update_video_preset(
    product_id: str,
    preset_id: str,
    payload: VideoPresetUpdateRequest,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
) -> VideoPresetResponse:
    """Edita campos sueltos de un preset existente."""
    product = repo.get(product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{product_id}' no encontrado.",
            details={"product_id": product_id},
        )
    preset = next((p for p in product.video_presets if p.id == preset_id), None)
    if preset is None:
        raise PhotoNotFoundError(
            f"Preset {preset_id} no encontrado en el producto.",
            details={"product_id": product_id, "preset_id": preset_id},
        )
    updates = payload.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(preset, k, v)
    from datetime import datetime, timezone
    preset.updated_at = datetime.now(timezone.utc).isoformat()
    product.touch()
    repo.save(product)
    return _preset_to_response(preset)


@router.post(
    "/{product_id}/video-presets/{preset_id}/generate-variants",
    response_model=GenerateVariantsResponse,
)
def generate_preset_variants(
    product_id: str,
    preset_id: str,
    payload: GenerateVariantsRequest,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
) -> GenerateVariantsResponse:
    """Genera N variantes A/B de un preset existente via Gemini. Las
    variantes NO se persisten — el frontend las usa one-shot para encolar
    una tanda de tests. Cada variante difiere del base en las dimensiones
    pedidas (text_overlay, color, cta_arrow, voice_tone, etc).
    """
    from src.cost_tracking import finalize_and_persist, start_job
    from src.tiktok_shop.pipeline.variants_generator import generate_variants

    product = repo.get(product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{product_id}' no encontrado.",
            details={"product_id": product_id},
        )
    base_preset = next(
        (p for p in product.video_presets if p.id == preset_id), None,
    )
    if base_preset is None:
        raise PhotoNotFoundError(
            f"Preset {preset_id} no encontrado.",
            details={"product_id": product_id, "preset_id": preset_id},
        )

    start_job(
        job_id=f"variants_{uuid.uuid4().hex[:12]}",
        program="tiktok_shop",
        mode="variant_generation",
        title=f"A/B variants: {base_preset.name}",
        product_id=product_id,
    )
    try:
        variants, meta = generate_variants(
            base_preset,
            count=payload.count,
            dimensions=payload.dimensions,
        )
    except Exception as e:
        try:
            finalize_and_persist()
        except Exception:
            pass
        raise GeminiError(
            f"Generación de variantes falló: {e}",
            details={"product_id": product_id, "preset_id": preset_id},
        )

    try:
        finalize_and_persist()
    except Exception:
        pass

    return GenerateVariantsResponse(
        base_preset_id=preset_id,
        variants=[_preset_to_response(v) for v in variants],
        meta=[VariantMeta(**m) for m in meta],
        warnings=[] if variants else ["Gemini no devolvió variantes válidas."],
    )


@router.post(
    "/{product_id}/video-presets/save-viral",
    response_model=VideoPresetResponse,
)
def save_viral_video_preset(
    product_id: str,
    payload: dict,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
) -> VideoPresetResponse:
    """Persiste un VideoPreset generado por `analyze_viral_video` en el
    producto. El payload trae el dict completo (con name, kind, prompts,
    fotos, etc.) que devolvió `analyze_viral_video` en `result.video_preset`.

    Source automático: `viral_replica` para distinguirlo de los autogen
    (`music_bof`/`scripted_bof`) y los manuales.
    """
    from src.tiktok_shop.models.video_preset import VideoPreset, make_preset_id

    product = repo.get(product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{product_id}' no encontrado.",
            details={"product_id": product_id},
        )

    if not isinstance(payload, dict) or not payload.get("seedance_prompt"):
        raise ValidationError(
            "Payload inválido — esperado el dict `video_preset` que devuelve "
            "analyze_viral_video (con seedance_prompt, veo3_prompt, etc.).",
            details={},
        )

    # Forzamos source=viral_replica y un id fresco
    payload_clean = {**payload, "id": make_preset_id(), "source": "viral_replica"}
    try:
        preset = VideoPreset(**payload_clean)
    except Exception as e:
        raise ValidationError(
            f"VideoPreset payload no validó: {e}",
            details={"keys": sorted(list(payload.keys()))[:30]},
        )

    product.video_presets.append(preset)
    product.touch()
    repo.save(product)
    return _preset_to_response(preset)


@router.delete(
    "/{product_id}/video-presets/all",
    status_code=status.HTTP_200_OK,
)
def delete_all_video_presets(
    product_id: str,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
    only_autogenerated: bool = False,
) -> dict:
    """Borra TODOS los presets del producto. Si `only_autogenerated=true`,
    mantiene los `source=manual`. Devuelve cuántos borró."""
    product = repo.get(product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{product_id}' no encontrado.",
            details={"product_id": product_id},
        )
    before = len(product.video_presets)
    if only_autogenerated:
        product.video_presets = [
            p for p in product.video_presets if p.source == "manual"
        ]
    else:
        product.video_presets = []
    deleted = before - len(product.video_presets)
    product.touch()
    repo.save(product)
    return {"deleted_count": deleted, "remaining": len(product.video_presets)}


@router.delete(
    "/{product_id}/video-presets/{preset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_video_preset(
    product_id: str,
    preset_id: str,
    repo: Annotated[ProductRepo, Depends(get_product_repo)],
) -> Response:
    product = repo.get(product_id)
    if product is None:
        raise ProductNotFoundError(
            f"Producto '{product_id}' no encontrado.",
            details={"product_id": product_id},
        )
    before = len(product.video_presets)
    product.video_presets = [p for p in product.video_presets if p.id != preset_id]
    if len(product.video_presets) == before:
        raise PhotoNotFoundError(
            f"Preset {preset_id} no encontrado.",
            details={"product_id": product_id, "preset_id": preset_id},
        )
    product.touch()
    repo.save(product)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
