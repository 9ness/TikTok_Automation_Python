"""Servicios de gestión de productos: CRUD de fotos + re-análisis Gemini.

Centraliza la lógica de negocio para que la UI sea pura de presentación.
Tests aplicables sin Streamlit ni red.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from src.tiktok_shop.config import (
    product_drive_folder,
    product_photos_generated_folder,
    product_photos_source_folder,
)
from src.tiktok_shop.models import Product, ProductPhoto
from src.tiktok_shop.utils.logging_setup import log_info, log_warning


_LOGGER = "tiktok_shop.product_service"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Gestión de fotos
# ---------------------------------------------------------------------------
def add_source_photo(
    product: Product,
    *,
    filename: str,
    bytes_data: bytes,
    origin: Literal["internet", "own", "tiktok_shop_url"] = "own",
    url_origin: str | None = None,
    photo_type: str | None = None,
) -> ProductPhoto:
    """Persiste una foto en `photos_source/` del producto y la añade al modelo.

    El caller debe llamar a `repo.save(product)` después.
    """
    folder = product_photos_source_folder(product.slug)
    Path(folder).mkdir(parents=True, exist_ok=True)
    dest = os.path.join(folder, filename)
    with open(dest, "wb") as f:
        f.write(bytes_data)

    photo = ProductPhoto(
        filename=filename,
        local_path=dest,
        origin=origin,
        url_origin=url_origin,
        type=photo_type,  # type: ignore[arg-type]
        added_at=_now_iso(),
    )
    product.photos.source.append(photo)
    product.touch()
    log_info(_LOGGER, "Foto source añadida",
             slug=product.slug, filename=filename, origin=origin)
    return photo


def add_generated_photo(
    product: Product,
    *,
    filename: str,
    bytes_data: bytes,
    photo_type: Literal["packshot", "lifestyle", "detail", "in_use", "macro"],
    prompt_used: str | None = None,
) -> ProductPhoto:
    """Persiste una foto premium (Nano Banana 2) en `photos_generated/`."""
    folder = product_photos_generated_folder(product.slug)
    Path(folder).mkdir(parents=True, exist_ok=True)
    dest = os.path.join(folder, filename)
    with open(dest, "wb") as f:
        f.write(bytes_data)

    photo = ProductPhoto(
        filename=filename,
        local_path=dest,
        type=photo_type,
        generation_prompt_used=prompt_used,
        generated_at=_now_iso(),
    )
    product.photos.generated.append(photo)
    # Una vez tenemos generated, el flag de "necesita regenerar" cae a False
    product.needs_nano_banana_regeneration = False
    product.touch()
    log_info(_LOGGER, "Foto generated añadida",
             slug=product.slug, filename=filename, type=photo_type)
    return photo


def mark_photo_deleted(
    product: Product,
    *,
    filename: str,
    in_source: bool = True,
) -> bool:
    """Soft-delete: marca `deleted=True` en la foto pero NO toca disco.

    Args:
        in_source: True para buscar en `photos.source`, False para `generated`.

    Returns:
        True si se encontró y marcó, False si no existe.
    """
    photos = product.photos.source if in_source else product.photos.generated
    for p in photos:
        if p.filename == filename:
            p.deleted = True
            product.touch()
            log_info(_LOGGER, "Foto soft-deleted",
                     slug=product.slug, filename=filename,
                     bucket="source" if in_source else "generated")
            return True
    log_warning(_LOGGER, "Foto a borrar no encontrada",
                slug=product.slug, filename=filename)
    return False


def restore_photo(
    product: Product,
    *,
    filename: str,
    in_source: bool = True,
) -> bool:
    """Deshace soft-delete: marca `deleted=False`. Solo aplicable a fotos
    cuyo archivo en disco siga existiendo (si se hizo hard-delete antes,
    no se puede restaurar)."""
    photos = product.photos.source if in_source else product.photos.generated
    for p in photos:
        if p.filename == filename and p.deleted:
            if p.local_path and not os.path.exists(p.local_path):
                log_warning(_LOGGER, "Restore imposible — archivo no en disco",
                            slug=product.slug, filename=filename,
                            local_path=p.local_path)
                return False
            p.deleted = False
            product.touch()
            log_info(_LOGGER, "Foto restaurada",
                     slug=product.slug, filename=filename)
            return True
    return False


def hard_delete_photo(
    product: Product,
    *,
    filename: str,
    in_source: bool = True,
) -> bool:
    """Borrado DEFINITIVO: elimina la entrada del modelo Y borra el archivo
    del disco. Operación irreversible — la UI debe pedir confirmación.

    Returns:
        True si se borró del modelo (intenta también borrar del disco; si
        el archivo no existe lo loguea sin fallar).
    """
    photos_list = product.photos.source if in_source else product.photos.generated
    for i, p in enumerate(photos_list):
        if p.filename == filename:
            # Intentar borrar del disco
            if p.local_path and os.path.exists(p.local_path):
                try:
                    os.remove(p.local_path)
                    log_info(_LOGGER, "Foto borrada del disco",
                             slug=product.slug, filename=filename,
                             local_path=p.local_path)
                except OSError as e:
                    log_warning(_LOGGER, "No se pudo borrar archivo (sigue en disco)",
                                slug=product.slug, filename=filename, error=str(e))
            else:
                log_info(_LOGGER, "Hard-delete: archivo ya no existía en disco",
                         slug=product.slug, filename=filename)
            # Quitar del modelo
            photos_list.pop(i)
            product.touch()
            return True
    log_warning(_LOGGER, "Hard-delete: foto no encontrada en modelo",
                slug=product.slug, filename=filename)
    return False


def update_photo_type(
    product: Product,
    *,
    filename: str,
    new_type: Literal["packshot", "lifestyle", "detail", "in_use", "macro"],
    in_source: bool = True,
) -> bool:
    photos = product.photos.source if in_source else product.photos.generated
    for p in photos:
        if p.filename == filename and not p.deleted:
            p.type = new_type
            product.touch()
            return True
    return False


def toggle_photo_preferred_tier(
    product: Product,
    *,
    filename: str,
    tier: str,
    in_source: bool = True,
) -> bool:
    """Toggle: si el tier está en preferred_for_tiers, lo quita; si no, lo añade."""
    photos = product.photos.source if in_source else product.photos.generated
    for p in photos:
        if p.filename == filename and not p.deleted:
            if tier in p.preferred_for_tiers:
                p.preferred_for_tiers.remove(tier)
            else:
                p.preferred_for_tiers.append(tier)
            product.touch()
            return True
    return False


# ---------------------------------------------------------------------------
# Renombrado de slug + migración de carpeta Drive
# ---------------------------------------------------------------------------
def rename_product_slug(
    product: Product,
    *,
    new_slug: str,
    move_drive_folder: bool,
) -> bool:
    """Cambia el slug del producto. Si `move_drive_folder=True`, renombra la
    carpeta en Drive y actualiza los `local_path` de cada foto.

    NO mueve los videos generados (`_users/.../products/<old_slug>/videos/`).
    El caller (UI) debe avisar al usuario que esos videos quedan con el
    nombre viejo.

    Returns:
        True si la operación fue exitosa.
    """
    from src.tiktok_shop.models.product import slugify

    new_slug_clean = slugify(new_slug)
    if new_slug_clean == product.slug:
        return False  # no cambio
    old_slug = product.slug
    old_folder = product.drive_folder or product_drive_folder(old_slug)
    new_folder = product_drive_folder(new_slug_clean)

    if move_drive_folder and os.path.isdir(old_folder):
        try:
            os.makedirs(os.path.dirname(new_folder), exist_ok=True)
            shutil.move(old_folder, new_folder)
            log_info(_LOGGER, "Drive folder renombrado",
                     old=old_folder, new=new_folder)
        except OSError as e:
            log_warning(_LOGGER, "No se pudo renombrar carpeta Drive — slug sin cambiar",
                        error=str(e))
            return False

    # Actualizar paths en cada foto
    for p in product.photos.source + product.photos.generated:
        if p.local_path and old_slug in p.local_path:
            p.local_path = p.local_path.replace(
                f"{os.sep}{old_slug}{os.sep}", f"{os.sep}{new_slug_clean}{os.sep}",
            )

    product.slug = new_slug_clean
    product.drive_folder = new_folder
    product.touch()
    return True


# ---------------------------------------------------------------------------
# Re-análisis con Gemini
# ---------------------------------------------------------------------------
def re_analyze_with_gemini(product: Product) -> dict:
    """Re-ejecuta `analyze_product` con las fotos source actuales (no
    eliminadas) y actualiza el producto in-place.

    Returns:
        El dict de análisis para que el caller pueda mostrar al usuario qué
        cambió. Si no hay fotos válidas, devuelve `{}` y no toca el producto.
    """
    from src.tiktok_shop.pipeline import analyze_product

    src_paths: list[str] = []
    for p in product.photos.source:
        if not p.deleted and p.local_path and os.path.exists(p.local_path):
            src_paths.append(p.local_path)
    if not src_paths:
        log_warning(_LOGGER, "Re-análisis sin fotos source válidas — no se ejecuta",
                    slug=product.slug)
        return {}

    log_info(_LOGGER, "Re-analizando con Gemini",
             slug=product.slug, n_photos=len(src_paths))
    analysis = analyze_product(
        src_paths,
        extra_context=f"name={product.name}, brand={product.brand or ''}",
    )

    # Actualizar campos derivados del análisis
    if analysis.get("suggested_audiences"):
        product.target_audience = analysis["suggested_audiences"][:5]
    if analysis.get("key_features"):
        product.key_features = analysis["key_features"]
    if analysis.get("selling_points"):
        product.selling_points = analysis["selling_points"]
    if "has_complex_packaging_text" in analysis:
        product.video_config.has_complex_packaging = bool(
            analysis["has_complex_packaging_text"]
        )
    if not product.subcategory and analysis.get("subcategory"):
        product.subcategory = analysis["subcategory"]
    product.needs_nano_banana_regeneration = bool(
        analysis.get("needs_nano_banana_regeneration", False)
    )

    product.last_analyzed_at = _now_iso()
    product.touch()
    return analysis


# ---------------------------------------------------------------------------
# Hooks library CRUD
# ---------------------------------------------------------------------------
def add_hook(product: Product, *, category: str, template: str) -> None:
    from src.tiktok_shop.models import Hook
    product.hooks_library.append(Hook(category=category, template=template))
    product.touch()


def remove_hook(product: Product, *, index: int) -> bool:
    if 0 <= index < len(product.hooks_library):
        product.hooks_library.pop(index)
        product.touch()
        return True
    return False


def update_hook(
    product: Product,
    *,
    index: int,
    category: str | None = None,
    template: str | None = None,
) -> bool:
    if not (0 <= index < len(product.hooks_library)):
        return False
    h = product.hooks_library[index]
    if category is not None:
        h.category = category
    if template is not None:
        h.template = template
    product.touch()
    return True
