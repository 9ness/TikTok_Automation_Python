"""Tests del product_service: CRUD de fotos + soft-delete + re-analyze."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.tiktok_shop.models import Hook, Product, ProductPhoto, ProductPhotos
from src.tiktok_shop.services import product_service as ps


@pytest.fixture
def isolated_shop_root(tmp_path, monkeypatch):
    """Aísla TIKTOK_SHOP_ROOT_PATH para que `product_drive_folder` apunte a tmp."""
    monkeypatch.setenv("TIKTOK_SHOP_ROOT_PATH", str(tmp_path))
    return tmp_path


@pytest.fixture
def product_with_photos(isolated_shop_root):
    """Producto con 2 fotos source y 1 generated, todas en disco."""
    slug = "test_prod"
    src_dir = isolated_shop_root / "_products" / slug / "photos_source"
    gen_dir = isolated_shop_root / "_products" / slug / "photos_generated"
    src_dir.mkdir(parents=True, exist_ok=True)
    gen_dir.mkdir(parents=True, exist_ok=True)

    a_path = src_dir / "a.jpg"
    a_path.write_bytes(b"fake-a")
    b_path = src_dir / "b.jpg"
    b_path.write_bytes(b"fake-b")
    g_path = gen_dir / "g.jpg"
    g_path.write_bytes(b"fake-g")

    return Product(
        slug=slug, name="Test",
        photos=ProductPhotos(
            source=[
                ProductPhoto(filename="a.jpg", local_path=str(a_path), origin="own"),
                ProductPhoto(filename="b.jpg", local_path=str(b_path), origin="internet"),
            ],
            generated=[
                ProductPhoto(filename="g.jpg", local_path=str(g_path), type="packshot"),
            ],
        ),
    )


# ---------------------------------------------------------------------------
# add_source_photo / add_generated_photo
# ---------------------------------------------------------------------------
class TestAddPhoto:
    def test_add_source_writes_file_and_appends(self, product_with_photos):
        photo = ps.add_source_photo(
            product_with_photos, filename="c.jpg", bytes_data=b"fake-c",
            origin="own",
        )
        # Archivo escrito
        assert photo.local_path
        assert os.path.exists(photo.local_path)
        assert Path(photo.local_path).read_bytes() == b"fake-c"
        # Modelo actualizado
        assert any(p.filename == "c.jpg" for p in product_with_photos.photos.source)

    def test_add_generated_with_prompt(self, product_with_photos):
        photo = ps.add_generated_photo(
            product_with_photos, filename="g2.jpg", bytes_data=b"fake-g2",
            photo_type="lifestyle", prompt_used="big prompt",
        )
        assert photo.type == "lifestyle"
        assert photo.generation_prompt_used == "big prompt"
        assert photo.generated_at is not None

    def test_adding_generated_clears_regeneration_flag(self, product_with_photos):
        product_with_photos.needs_nano_banana_regeneration = True
        ps.add_generated_photo(
            product_with_photos, filename="g2.jpg", bytes_data=b"x",
            photo_type="packshot",
        )
        assert product_with_photos.needs_nano_banana_regeneration is False

    def test_origin_stored_for_source(self, product_with_photos):
        ps.add_source_photo(
            product_with_photos, filename="from_amazon.jpg", bytes_data=b"x",
            origin="internet", url_origin="https://amazon.com/x",
        )
        added = next(p for p in product_with_photos.photos.source
                     if p.filename == "from_amazon.jpg")
        assert added.origin == "internet"
        assert added.url_origin == "https://amazon.com/x"


# ---------------------------------------------------------------------------
# Soft-delete
# ---------------------------------------------------------------------------
class TestMarkPhotoDeleted:
    def test_soft_delete_source(self, product_with_photos):
        ok = ps.mark_photo_deleted(product_with_photos, filename="a.jpg", in_source=True)
        assert ok
        a = next(p for p in product_with_photos.photos.source if p.filename == "a.jpg")
        assert a.deleted is True
        # Archivo NO se borra
        assert os.path.exists(a.local_path)

    def test_soft_delete_generated(self, product_with_photos):
        ok = ps.mark_photo_deleted(product_with_photos, filename="g.jpg", in_source=False)
        assert ok
        g = next(p for p in product_with_photos.photos.generated if p.filename == "g.jpg")
        assert g.deleted is True

    def test_delete_unknown_returns_false(self, product_with_photos):
        assert ps.mark_photo_deleted(
            product_with_photos, filename="no_existe.jpg", in_source=True,
        ) is False

    def test_best_available_filters_deleted(self, product_with_photos):
        # Marca todas las generated como deleted → fallback a source
        ps.mark_photo_deleted(product_with_photos, filename="g.jpg", in_source=False)
        photos, origin = product_with_photos.photos.best_available()
        assert origin == "source"
        assert all(p.filename != "g.jpg" for p in photos)
        assert len(photos) == 2

    def test_best_available_excludes_deleted_source(self, product_with_photos):
        ps.mark_photo_deleted(product_with_photos, filename="a.jpg", in_source=True)
        # generated tiene 1 foto activa → seguirá usando generated
        photos, origin = product_with_photos.photos.best_available()
        assert origin == "generated"
        assert len(photos) == 1


class TestRestoreAndHardDelete:
    def test_restore_after_soft_delete(self, product_with_photos):
        ps.mark_photo_deleted(product_with_photos, filename="a.jpg", in_source=True)
        ok = ps.restore_photo(product_with_photos, filename="a.jpg", in_source=True)
        assert ok
        a = next(p for p in product_with_photos.photos.source if p.filename == "a.jpg")
        assert a.deleted is False

    def test_restore_fails_if_file_gone(self, product_with_photos):
        # Simula hard-delete previo: marcamos soft-deleted Y borramos archivo
        a = next(p for p in product_with_photos.photos.source if p.filename == "a.jpg")
        a.deleted = True
        os.remove(a.local_path)
        ok = ps.restore_photo(product_with_photos, filename="a.jpg", in_source=True)
        assert ok is False
        assert a.deleted is True  # sigue marcada

    def test_restore_unknown_returns_false(self, product_with_photos):
        ok = ps.restore_photo(product_with_photos, filename="nope.jpg", in_source=True)
        assert ok is False

    def test_hard_delete_removes_from_model_and_disk(self, product_with_photos):
        a = next(p for p in product_with_photos.photos.source if p.filename == "a.jpg")
        path = a.local_path
        assert os.path.exists(path)

        ok = ps.hard_delete_photo(product_with_photos, filename="a.jpg", in_source=True)
        assert ok
        # Modelo: ya no aparece
        assert all(p.filename != "a.jpg" for p in product_with_photos.photos.source)
        # Disco: archivo borrado
        assert not os.path.exists(path)

    def test_hard_delete_works_even_if_file_missing(self, product_with_photos):
        a = next(p for p in product_with_photos.photos.source if p.filename == "a.jpg")
        os.remove(a.local_path)  # simula que ya estaba borrado
        ok = ps.hard_delete_photo(product_with_photos, filename="a.jpg", in_source=True)
        assert ok
        assert all(p.filename != "a.jpg" for p in product_with_photos.photos.source)

    def test_hard_delete_unknown_returns_false(self, product_with_photos):
        ok = ps.hard_delete_photo(
            product_with_photos, filename="nope.jpg", in_source=True,
        )
        assert ok is False

    def test_hard_delete_generated_bucket(self, product_with_photos):
        g = next(p for p in product_with_photos.photos.generated if p.filename == "g.jpg")
        path = g.local_path
        ok = ps.hard_delete_photo(product_with_photos, filename="g.jpg", in_source=False)
        assert ok
        assert all(p.filename != "g.jpg" for p in product_with_photos.photos.generated)
        assert not os.path.exists(path)


# ---------------------------------------------------------------------------
# update_photo_type / toggle_photo_preferred_tier
# ---------------------------------------------------------------------------
class TestPhotoMetadataUpdates:
    def test_change_type(self, product_with_photos):
        ok = ps.update_photo_type(
            product_with_photos, filename="a.jpg", new_type="macro", in_source=True,
        )
        assert ok
        a = next(p for p in product_with_photos.photos.source if p.filename == "a.jpg")
        assert a.type == "macro"

    def test_change_type_skips_deleted(self, product_with_photos):
        ps.mark_photo_deleted(product_with_photos, filename="a.jpg", in_source=True)
        ok = ps.update_photo_type(
            product_with_photos, filename="a.jpg", new_type="macro", in_source=True,
        )
        assert ok is False

    def test_toggle_preferred_tier_adds(self, product_with_photos):
        ok = ps.toggle_photo_preferred_tier(
            product_with_photos, filename="g.jpg", tier="pro", in_source=False,
        )
        assert ok
        g = next(p for p in product_with_photos.photos.generated if p.filename == "g.jpg")
        assert "pro" in g.preferred_for_tiers

    def test_toggle_preferred_tier_removes_on_second_toggle(self, product_with_photos):
        ps.toggle_photo_preferred_tier(
            product_with_photos, filename="g.jpg", tier="pro", in_source=False,
        )
        ps.toggle_photo_preferred_tier(
            product_with_photos, filename="g.jpg", tier="pro", in_source=False,
        )
        g = next(p for p in product_with_photos.photos.generated if p.filename == "g.jpg")
        assert "pro" not in g.preferred_for_tiers


# ---------------------------------------------------------------------------
# rename_product_slug
# ---------------------------------------------------------------------------
class TestRenameSlug:
    def test_rename_moves_folder(self, product_with_photos, isolated_shop_root):
        old_slug = product_with_photos.slug
        old_folder = isolated_shop_root / "_products" / old_slug
        assert old_folder.is_dir()

        ok = ps.rename_product_slug(
            product_with_photos, new_slug="new_slug_v2", move_drive_folder=True,
        )
        assert ok
        assert product_with_photos.slug == "new_slug_v2"

        new_folder = isolated_shop_root / "_products" / "new_slug_v2"
        assert new_folder.is_dir()
        assert not old_folder.exists()

        # Paths de fotos actualizados
        for p in product_with_photos.photos.source:
            assert "new_slug_v2" in p.local_path
            assert old_slug not in p.local_path

    def test_rename_same_slug_returns_false(self, product_with_photos):
        ok = ps.rename_product_slug(
            product_with_photos,
            new_slug=product_with_photos.slug,  # mismo slug
            move_drive_folder=True,
        )
        assert ok is False

    def test_rename_normalizes_slug(self, product_with_photos):
        # "My New Slug" → "my_new_slug" después del slugify
        ps.rename_product_slug(
            product_with_photos, new_slug="My New Slug", move_drive_folder=True,
        )
        assert product_with_photos.slug == "my_new_slug"

    def test_rename_without_move_keeps_old_folder(self, product_with_photos, isolated_shop_root):
        old_slug = product_with_photos.slug
        old_folder = isolated_shop_root / "_products" / old_slug

        ps.rename_product_slug(
            product_with_photos, new_slug="just_metadata", move_drive_folder=False,
        )
        # Carpeta vieja sigue ahí porque move_drive_folder=False
        assert old_folder.is_dir()
        # Slug actualizado en modelo
        assert product_with_photos.slug == "just_metadata"


# ---------------------------------------------------------------------------
# re_analyze_with_gemini
# ---------------------------------------------------------------------------
class TestReAnalyze:
    def test_no_valid_source_photos_returns_empty(self, product_with_photos, monkeypatch):
        # Borrar archivos en disco para forzar paths inválidos
        for p in product_with_photos.photos.source:
            os.remove(p.local_path)
        result = ps.re_analyze_with_gemini(product_with_photos)
        assert result == {}
        # last_analyzed_at no se actualizó
        assert product_with_photos.last_analyzed_at is None

    def test_re_analyze_updates_fields_and_timestamp(self, product_with_photos, monkeypatch):
        fake_analysis = {
            "subcategory": "creatine",
            "key_features": ["nuevo feature 1", "nuevo feature 2"],
            "suggested_audiences": ["aud1", "aud2", "aud3"],
            "selling_points": ["sp1", "sp2"],
            "has_complex_packaging_text": True,
            "needs_nano_banana_regeneration": False,
        }
        # `analyze_product` se importa dentro de re_analyze_with_gemini
        # (lazy import). Patcheamos el atributo en el módulo `pipeline`.
        from src.tiktok_shop import pipeline as pipe_mod
        monkeypatch.setattr(
            pipe_mod, "analyze_product",
            lambda paths, **kw: fake_analysis,
        )

        result = ps.re_analyze_with_gemini(product_with_photos)

        assert result == fake_analysis
        assert product_with_photos.subcategory == "creatine"
        assert "nuevo feature 1" in product_with_photos.key_features
        assert product_with_photos.video_config.has_complex_packaging is True
        assert product_with_photos.last_analyzed_at is not None
        assert "T" in product_with_photos.last_analyzed_at  # ISO


# ---------------------------------------------------------------------------
# Hooks library CRUD
# ---------------------------------------------------------------------------
class TestHooksLibraryCRUD:
    def test_add_hook(self, product_with_photos):
        ps.add_hook(product_with_photos, category="curiosity", template="POV: ...")
        assert len(product_with_photos.hooks_library) == 1
        assert product_with_photos.hooks_library[0].category == "curiosity"

    def test_remove_hook(self, product_with_photos):
        product_with_photos.hooks_library = [
            Hook(category="x", template="x"),
            Hook(category="y", template="y"),
        ]
        ok = ps.remove_hook(product_with_photos, index=0)
        assert ok
        assert len(product_with_photos.hooks_library) == 1
        assert product_with_photos.hooks_library[0].category == "y"

    def test_remove_hook_invalid_index(self, product_with_photos):
        assert ps.remove_hook(product_with_photos, index=99) is False

    def test_update_hook(self, product_with_photos):
        product_with_photos.hooks_library = [Hook(category="old", template="old")]
        ps.update_hook(product_with_photos, index=0, category="new", template="newt")
        assert product_with_photos.hooks_library[0].category == "new"
        assert product_with_photos.hooks_library[0].template == "newt"
