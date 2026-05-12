"""Tests de los endpoints CRUD de productos.

Cubren:
- Health check
- list/create/get/update/delete (incluido soft-delete)
- Subida + edición + soft-delete de fotos
- Re-analyze con Gemini mockeado
- Nano Banana 2 prompt mockeado
- Casos error (404, 422, slug duplicado, formato foto inválido)

Todo aislado con `FakeRedis` y `shop_root` temporal — coste $0.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _create(client: TestClient, name: str = "Producto Test", **overrides) -> dict:
    payload = {"name": name, **overrides}
    r = client.post("/api/v1/products", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _make_jpeg(path: Path, size: tuple[int, int] = (1200, 1600)) -> Path:
    Image.new("RGB", size, color=(80, 120, 160)).save(path, "JPEG", quality=85)
    return path


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
class TestHealth:
    def test_health_ok(self, app_client: TestClient):
        r = app_client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "version" in body


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------
class TestCreateProduct:
    def test_create_minimal(self, app_client: TestClient):
        r = app_client.post("/api/v1/products", json={"name": "Mi Producto"})
        assert r.status_code == 201
        body = r.json()
        assert body["name"] == "Mi Producto"
        assert body["slug"] == "mi_producto"
        assert body["category"] == "otros"
        assert body["video_config"]["default_tier"] == "standard"
        assert body["deleted"] is False
        assert body["drive_folder"]

    def test_create_with_explicit_slug(self, app_client: TestClient):
        r = app_client.post(
            "/api/v1/products",
            json={"name": "X", "slug": "custom_slug_v2"},
        )
        assert r.status_code == 201
        assert r.json()["slug"] == "custom_slug_v2"

    def test_create_invalid_slug_returns_422(self, app_client: TestClient):
        r = app_client.post(
            "/api/v1/products",
            json={"name": "X", "slug": "Invalid Slug!"},
        )
        assert r.status_code == 422

    def test_create_duplicate_slug_returns_422(self, app_client: TestClient):
        _create(app_client, name="Producto A", slug="dup")
        r = app_client.post(
            "/api/v1/products",
            json={"name": "Otro", "slug": "dup"},
        )
        assert r.status_code == 422
        assert r.json()["code"] == "validation_error"

    def test_create_with_full_payload(self, app_client: TestClient):
        payload = {
            "name": "Producto Pro",
            "brand": "BrandX",
            "category": "fitness",
            "subcategory": "creatine",
            "target_audience": ["gymbros"],
            "key_features": ["sin azúcar"],
            "selling_points": ["delicioso"],
            "tiktok_shop": {
                "product_url": "https://www.tiktok.com/@shop/product/12345",
                "product_id": "tk_001",
                "commission_rate": 0.15,
                "price_eur": 29.99,
            },
            "default_tier": "advanced",
            "default_duration": 15,
            "default_resolution": "1080p-SR",
        }
        r = app_client.post("/api/v1/products", json=payload)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["brand"] == "BrandX"
        assert body["tiktok_shop"]["commission_rate"] == 0.15
        assert body["video_config"]["default_tier"] == "advanced"

    def test_create_invalid_tiktok_url_returns_422(self, app_client: TestClient):
        r = app_client.post(
            "/api/v1/products",
            json={
                "name": "X",
                "tiktok_shop": {"product_url": "not-a-url"},
            },
        )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------
class TestListProducts:
    def test_list_empty(self, app_client: TestClient):
        r = app_client.get("/api/v1/products")
        assert r.status_code == 200
        assert r.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}

    def test_list_after_create(self, app_client: TestClient):
        _create(app_client, name="A")
        _create(app_client, name="B")
        r = app_client.get("/api/v1/products")
        body = r.json()
        assert body["total"] == 2
        assert {p["name"] for p in body["items"]} == {"A", "B"}

    def test_list_filtered_by_category(self, app_client: TestClient):
        _create(app_client, name="A", category="fitness")
        _create(app_client, name="B", category="skincare")
        r = app_client.get("/api/v1/products?category=fitness")
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["category"] == "fitness"

    def test_list_pagination(self, app_client: TestClient):
        for i in range(5):
            _create(app_client, name=f"Producto {i}")
        r = app_client.get("/api/v1/products?limit=2&offset=1")
        body = r.json()
        assert body["total"] == 5
        assert len(body["items"]) == 2
        assert body["limit"] == 2
        assert body["offset"] == 1

    def test_list_excludes_deleted_by_default(self, app_client: TestClient):
        prod = _create(app_client, name="A")
        app_client.delete(f"/api/v1/products/{prod['id']}")
        r = app_client.get("/api/v1/products")
        assert r.json()["total"] == 0
        r2 = app_client.get("/api/v1/products?include_deleted=true")
        assert r2.json()["total"] == 1


# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------
class TestGetProduct:
    def test_get_existing(self, app_client: TestClient):
        prod = _create(app_client, name="X")
        r = app_client.get(f"/api/v1/products/{prod['id']}")
        assert r.status_code == 200
        assert r.json()["id"] == prod["id"]

    def test_get_missing_returns_404(self, app_client: TestClient):
        r = app_client.get("/api/v1/products/nonexistent")
        assert r.status_code == 404
        assert r.json()["code"] == "product_not_found"


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------
class TestUpdateProduct:
    def test_update_simple_fields(self, app_client: TestClient):
        prod = _create(app_client, name="Old", brand="OldBrand")
        r = app_client.put(
            f"/api/v1/products/{prod['id']}",
            json={"name": "New", "brand": "NewBrand"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "New"
        assert body["brand"] == "NewBrand"

    def test_update_video_config_field(self, app_client: TestClient):
        prod = _create(app_client, name="X")
        r = app_client.put(
            f"/api/v1/products/{prod['id']}",
            json={"default_tier": "pro", "default_duration": 10},
        )
        assert r.status_code == 200
        cfg = r.json()["video_config"]
        assert cfg["default_tier"] == "pro"
        assert cfg["default_duration"] == 10

    def test_update_slug_renames_drive_folder(
        self, app_client: TestClient, shop_root: Path
    ):
        prod = _create(app_client, name="Original Name")
        old_slug = prod["slug"]
        old_folder = shop_root / "_products" / old_slug
        assert old_folder.exists()

        r = app_client.put(
            f"/api/v1/products/{prod['id']}",
            json={"slug": "new_slug"},
        )
        assert r.status_code == 200
        assert r.json()["slug"] == "new_slug"
        assert (shop_root / "_products" / "new_slug").exists()
        assert not old_folder.exists()

    def test_update_to_existing_slug_returns_422(self, app_client: TestClient):
        _create(app_client, name="A", slug="taken")
        prod = _create(app_client, name="B", slug="not_taken")
        r = app_client.put(
            f"/api/v1/products/{prod['id']}",
            json={"slug": "taken"},
        )
        assert r.status_code == 422

    def test_update_missing_returns_404(self, app_client: TestClient):
        r = app_client.put("/api/v1/products/missing", json={"name": "X"})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE (soft)
# ---------------------------------------------------------------------------
class TestDeleteProduct:
    def test_soft_delete(self, app_client: TestClient):
        prod = _create(app_client, name="X")
        r = app_client.delete(f"/api/v1/products/{prod['id']}")
        assert r.status_code == 204

        # Aún se puede recuperar por GET (deleted=true)
        g = app_client.get(f"/api/v1/products/{prod['id']}")
        assert g.status_code == 200
        assert g.json()["deleted"] is True

    def test_delete_missing_returns_404(self, app_client: TestClient):
        r = app_client.delete("/api/v1/products/missing")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# PHOTOS
# ---------------------------------------------------------------------------
class TestPhotos:
    def test_upload_source_photo(
        self, app_client: TestClient, tmp_path: Path, shop_root: Path
    ):
        prod = _create(app_client, name="P")
        photo = _make_jpeg(tmp_path / "amazon.jpg")
        with photo.open("rb") as fh:
            r = app_client.post(
                f"/api/v1/products/{prod['id']}/photos",
                files={"file": ("amazon.jpg", fh, "image/jpeg")},
                data={"location": "source", "origin": "internet"},
            )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["location"] == "source"
        assert body["origin"] == "internet"
        assert body["filename"] == "amazon.jpg"
        # El archivo debe existir en disco
        expected = shop_root / "_products" / prod["slug"] / "photos_source" / "amazon.jpg"
        assert expected.exists()

    def test_upload_generated_requires_type(
        self, app_client: TestClient, tmp_path: Path
    ):
        prod = _create(app_client, name="P")
        photo = _make_jpeg(tmp_path / "gen.jpg")
        with photo.open("rb") as fh:
            r = app_client.post(
                f"/api/v1/products/{prod['id']}/photos",
                files={"file": ("gen.jpg", fh, "image/jpeg")},
                data={"location": "generated"},
            )
        assert r.status_code == 422
        assert r.json()["code"] == "validation_error"

    def test_upload_generated_with_type(
        self, app_client: TestClient, tmp_path: Path
    ):
        prod = _create(app_client, name="P")
        photo = _make_jpeg(tmp_path / "gen.jpg")
        with photo.open("rb") as fh:
            r = app_client.post(
                f"/api/v1/products/{prod['id']}/photos",
                files={"file": ("gen.jpg", fh, "image/jpeg")},
                data={"location": "generated", "type": "packshot"},
            )
        assert r.status_code == 201, r.text
        assert r.json()["type"] == "packshot"
        assert r.json()["location"] == "generated"

    def test_upload_invalid_extension(
        self, app_client: TestClient, tmp_path: Path
    ):
        prod = _create(app_client, name="P")
        bad = tmp_path / "doc.txt"
        bad.write_text("not an image")
        with bad.open("rb") as fh:
            r = app_client.post(
                f"/api/v1/products/{prod['id']}/photos",
                files={"file": ("doc.txt", fh, "text/plain")},
                data={"location": "source"},
            )
        assert r.status_code == 422
        assert r.json()["code"] == "validation_error"

    def test_upload_to_missing_product_returns_404(
        self, app_client: TestClient, tmp_path: Path
    ):
        photo = _make_jpeg(tmp_path / "x.jpg")
        with photo.open("rb") as fh:
            r = app_client.post(
                "/api/v1/products/missing/photos",
                files={"file": ("x.jpg", fh, "image/jpeg")},
                data={"location": "source"},
            )
        assert r.status_code == 404

    def test_update_photo_metadata(
        self, app_client: TestClient, tmp_path: Path
    ):
        prod = _create(app_client, name="P")
        photo = _make_jpeg(tmp_path / "x.jpg")
        with photo.open("rb") as fh:
            up = app_client.post(
                f"/api/v1/products/{prod['id']}/photos",
                files={"file": ("x.jpg", fh, "image/jpeg")},
                data={"location": "source"},
            )
        assert up.status_code == 201
        photo_id = up.json()["id"]
        r = app_client.put(
            f"/api/v1/products/{prod['id']}/photos/{photo_id}",
            json={"type": "lifestyle", "preferred_for_tiers": ["advanced"]},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["type"] == "lifestyle"
        assert body["preferred_for_tiers"] == ["advanced"]

    def test_delete_photo_soft(
        self, app_client: TestClient, tmp_path: Path
    ):
        prod = _create(app_client, name="P")
        photo = _make_jpeg(tmp_path / "x.jpg")
        with photo.open("rb") as fh:
            up = app_client.post(
                f"/api/v1/products/{prod['id']}/photos",
                files={"file": ("x.jpg", fh, "image/jpeg")},
                data={"location": "source"},
            )
        photo_id = up.json()["id"]

        r = app_client.delete(
            f"/api/v1/products/{prod['id']}/photos/{photo_id}"
        )
        assert r.status_code == 204

        # El producto sigue teniendo la foto pero marcada deleted
        g = app_client.get(f"/api/v1/products/{prod['id']}")
        assert g.json()["photos"]["source"][0]["deleted"] is True

    def test_delete_missing_photo_returns_404(self, app_client: TestClient):
        prod = _create(app_client, name="P")
        r = app_client.delete(
            f"/api/v1/products/{prod['id']}/photos/missing.jpg"
        )
        assert r.status_code == 404
        assert r.json()["code"] == "photo_not_found"


# ---------------------------------------------------------------------------
# ANALYZE
# ---------------------------------------------------------------------------
class TestAnalyze:
    def test_analyze_without_photos_returns_422(self, app_client: TestClient):
        prod = _create(app_client, name="P")
        r = app_client.post(f"/api/v1/products/{prod['id']}/analyze")
        assert r.status_code == 422

    def test_analyze_with_photos(
        self, app_client: TestClient, tmp_path: Path
    ):
        prod = _create(app_client, name="P")
        photo = _make_jpeg(tmp_path / "a.jpg")
        with photo.open("rb") as fh:
            app_client.post(
                f"/api/v1/products/{prod['id']}/photos",
                files={"file": ("a.jpg", fh, "image/jpeg")},
                data={"location": "source"},
            )
        r = app_client.post(f"/api/v1/products/{prod['id']}/analyze")
        assert r.status_code == 200, r.text
        body = r.json()
        # Vienen del fake en conftest
        assert body["key_features"] == ["liviano", "duradero"]
        assert body["needs_nano_banana_regeneration"] is True
        assert "warnings" in body

    def test_analyze_missing_product_returns_404(self, app_client: TestClient):
        r = app_client.post("/api/v1/products/missing/analyze")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# NANO BANANA 2 PROMPT
# ---------------------------------------------------------------------------
class TestNanoBananaPrompt:
    def test_generate_nano_banana_prompt(self, app_client: TestClient):
        prod = _create(app_client, name="P")
        r = app_client.post(
            f"/api/v1/products/{prod['id']}/nano-banana-prompt",
            json={
                "photo_types_wanted": ["packshot", "lifestyle"],
                "n_angles": 6,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "prompt" in body
        assert "instructions" in body
        assert body["product_id"] == prod["id"]

    def test_nano_banana_prompt_validation(self, app_client: TestClient):
        prod = _create(app_client, name="P")
        r = app_client.post(
            f"/api/v1/products/{prod['id']}/nano-banana-prompt",
            json={"photo_types_wanted": [], "n_angles": 5},
        )
        assert r.status_code == 422

    def test_nano_banana_prompt_missing_product(self, app_client: TestClient):
        r = app_client.post(
            "/api/v1/products/missing/nano-banana-prompt",
            json={"photo_types_wanted": ["packshot"], "n_angles": 5},
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# AUTH (cuando API_KEY está definida)
# ---------------------------------------------------------------------------
class TestAuth:
    def test_no_api_key_required_by_default(self, app_client: TestClient):
        # Sin API_KEY definida, los endpoints son abiertos
        r = app_client.get("/api/v1/products")
        assert r.status_code == 200

    def test_api_key_required_when_configured(
        self, monkeypatch: pytest.MonkeyPatch, fake_shop_redis, shop_root
    ):
        """Cuando API_KEY está definida en el entorno, los endpoints
        requieren el header X-API-Key. `shop_root` se inyecta por su
        side-effect de fijar TIKTOK_SHOP_ROOT_PATH en env."""
        del shop_root  # suppress unused warning — la fixture es side-effect-only
        from src.api.config import get_settings as _get_settings

        monkeypatch.setenv("API_KEY", "secret-token")
        _get_settings.cache_clear()

        import src.tiktok_shop.repos.redis_base as redis_base
        monkeypatch.setattr(redis_base, "_INSTANCE", fake_shop_redis)
        monkeypatch.setattr(redis_base, "get_shop_redis", lambda: fake_shop_redis)

        from src.api.dependencies import get_redis
        from src.api.main import create_app

        app = create_app()
        app.dependency_overrides[get_redis] = lambda: fake_shop_redis

        with TestClient(app) as client:
            # Sin header → 401
            r = client.get("/api/v1/products")
            assert r.status_code == 401
            assert r.json()["code"] == "unauthorized"

            # Con header válido → 200
            r2 = client.get(
                "/api/v1/products",
                headers={"X-API-Key": "secret-token"},
            )
            assert r2.status_code == 200

            # Health no requiere auth (no está bajo /api/v1/products)
            r3 = client.get("/api/health")
            assert r3.status_code == 200

        _get_settings.cache_clear()
