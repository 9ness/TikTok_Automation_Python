"""Tests de los endpoints de usuarios TikTok."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _create_user(
    client: TestClient,
    username: str = "@test_user",
    display_name: str = "Test User",
    **overrides,
) -> dict:
    payload = {
        "username": username,
        "display_name": display_name,
        **overrides,
    }
    r = client.post("/api/v1/users", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _create_product(client: TestClient, name: str = "Producto X") -> dict:
    r = client.post("/api/v1/products", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def _username_path(username: str) -> str:
    return quote(username, safe="")


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------
class TestCreateUser:
    def test_create_minimal(self, app_client: TestClient):
        r = app_client.post(
            "/api/v1/users",
            json={"username": "@nuevo_user", "display_name": "Nuevo"},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["username"] == "@nuevo_user"
        assert body["display_name"] == "Nuevo"
        assert body["status"] == "pilot"
        assert body["assigned_products"] == []
        assert body["deleted"] is False
        assert body["drive_folder"]

    def test_create_username_without_at_normalized(self, app_client: TestClient):
        r = app_client.post(
            "/api/v1/users",
            json={"username": "sin_arroba", "display_name": "X"},
        )
        assert r.status_code == 201
        assert r.json()["username"] == "@sin_arroba"

    def test_create_invalid_username_returns_422(self, app_client: TestClient):
        r = app_client.post(
            "/api/v1/users",
            json={"username": "@bad user!", "display_name": "X"},
        )
        assert r.status_code == 422

    def test_create_duplicate_username_returns_422(self, app_client: TestClient):
        _create_user(app_client, username="@dup", display_name="A")
        r = app_client.post(
            "/api/v1/users",
            json={"username": "@dup", "display_name": "B"},
        )
        assert r.status_code == 422
        assert r.json()["code"] == "validation_error"

    def test_create_creates_drive_folder(
        self, app_client: TestClient, shop_root: Path
    ):
        _create_user(app_client, username="@drive_user")
        expected = shop_root / "_users" / "@drive_user"
        assert expected.exists()
        assert (expected / "products").exists()


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------
class TestListUsers:
    def test_list_empty(self, app_client: TestClient):
        r = app_client.get("/api/v1/users")
        assert r.status_code == 200
        assert r.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}

    def test_list_filtered_by_niche(self, app_client: TestClient):
        _create_user(app_client, username="@aa", niche="fitness")
        _create_user(app_client, username="@bb", niche="skincare")
        r = app_client.get("/api/v1/users?niche=fitness")
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["niche"] == "fitness"

    def test_list_pagination(self, app_client: TestClient):
        for i in range(5):
            _create_user(app_client, username=f"@uu_{i}")
        r = app_client.get("/api/v1/users?limit=2&offset=1")
        body = r.json()
        assert body["total"] == 5
        assert len(body["items"]) == 2
        assert body["limit"] == 2
        assert body["offset"] == 1

    def test_list_excludes_deleted_by_default(self, app_client: TestClient):
        _create_user(app_client, username="@del_me")
        app_client.delete(f"/api/v1/users/{_username_path('@del_me')}")
        r = app_client.get("/api/v1/users")
        assert r.json()["total"] == 0
        r2 = app_client.get("/api/v1/users?include_deleted=true")
        assert r2.json()["total"] == 1


# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------
class TestGetUser:
    def test_get_existing(self, app_client: TestClient):
        _create_user(app_client, username="@xx")
        r = app_client.get(f"/api/v1/users/{_username_path('@xx')}")
        assert r.status_code == 200
        assert r.json()["username"] == "@xx"

    def test_get_missing_returns_404(self, app_client: TestClient):
        r = app_client.get(f"/api/v1/users/{_username_path('@nope')}")
        assert r.status_code == 404
        assert r.json()["code"] == "user_not_found"

    def test_get_invalid_username_format_returns_422(self, app_client: TestClient):
        # carácter prohibido en handle
        r = app_client.get(f"/api/v1/users/{_username_path('@bad!')}")
        assert r.status_code == 422

    def test_get_username_without_at_works(self, app_client: TestClient):
        _create_user(app_client, username="@sin_arroba")
        r = app_client.get("/api/v1/users/sin_arroba")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------
class TestUpdateUser:
    def test_update_simple_fields(self, app_client: TestClient):
        _create_user(app_client, username="@uu")
        r = app_client.put(
            f"/api/v1/users/{_username_path('@uu')}",
            json={"followers_count": 1500, "creator_health_rating": 180},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["followers_count"] == 1500
        assert body["creator_health_rating"] == 180

    def test_update_status_to_graduated(self, app_client: TestClient):
        _create_user(app_client, username="@uu")
        r = app_client.put(
            f"/api/v1/users/{_username_path('@uu')}",
            json={"status": "graduated"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "graduated"

    def test_update_missing_returns_404(self, app_client: TestClient):
        r = app_client.put(
            f"/api/v1/users/{_username_path('@missing')}",
            json={"followers_count": 100},
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE (soft)
# ---------------------------------------------------------------------------
class TestDeleteUser:
    def test_soft_delete(self, app_client: TestClient):
        _create_user(app_client, username="@uu")
        r = app_client.delete(f"/api/v1/users/{_username_path('@uu')}")
        assert r.status_code == 204
        g = app_client.get(f"/api/v1/users/{_username_path('@uu')}")
        assert g.status_code == 200
        assert g.json()["deleted"] is True

    def test_delete_missing_returns_404(self, app_client: TestClient):
        r = app_client.delete(f"/api/v1/users/{_username_path('@missing')}")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# ASSIGN / UNASSIGN PRODUCTS
# ---------------------------------------------------------------------------
class TestAssignProduct:
    def test_assign_ok(self, app_client: TestClient):
        _create_user(app_client, username="@uu")
        prod = _create_product(app_client)
        r = app_client.post(
            f"/api/v1/users/{_username_path('@uu')}/products",
            json={"product_id": prod["id"]},
        )
        assert r.status_code == 200
        assert prod["id"] in r.json()["assigned_products"]

    def test_assign_missing_product_returns_404(self, app_client: TestClient):
        _create_user(app_client, username="@uu")
        r = app_client.post(
            f"/api/v1/users/{_username_path('@uu')}/products",
            json={"product_id": "missing"},
        )
        assert r.status_code == 404
        assert r.json()["code"] == "product_not_found"

    def test_assign_to_missing_user_returns_404(self, app_client: TestClient):
        prod = _create_product(app_client)
        r = app_client.post(
            f"/api/v1/users/{_username_path('@missing')}/products",
            json={"product_id": prod["id"]},
        )
        assert r.status_code == 404
        assert r.json()["code"] == "user_not_found"

    def test_assign_duplicate_returns_409(self, app_client: TestClient):
        _create_user(app_client, username="@uu")
        prod = _create_product(app_client)
        app_client.post(
            f"/api/v1/users/{_username_path('@uu')}/products",
            json={"product_id": prod["id"]},
        )
        r = app_client.post(
            f"/api/v1/users/{_username_path('@uu')}/products",
            json={"product_id": prod["id"]},
        )
        assert r.status_code == 409
        assert r.json()["code"] == "product_already_assigned"


class TestUnassignProduct:
    def test_unassign_ok(self, app_client: TestClient):
        _create_user(app_client, username="@uu")
        prod = _create_product(app_client)
        app_client.post(
            f"/api/v1/users/{_username_path('@uu')}/products",
            json={"product_id": prod["id"]},
        )
        r = app_client.delete(
            f"/api/v1/users/{_username_path('@uu')}/products/{prod['id']}"
        )
        assert r.status_code == 204
        g = app_client.get(f"/api/v1/users/{_username_path('@uu')}")
        assert prod["id"] not in g.json()["assigned_products"]

    def test_unassign_idempotent(self, app_client: TestClient):
        # No estaba asignado pero devolvemos 204 igualmente
        _create_user(app_client, username="@uu")
        r = app_client.delete(
            f"/api/v1/users/{_username_path('@uu')}/products/never_assigned"
        )
        assert r.status_code == 204

    def test_unassign_missing_user_returns_404(self, app_client: TestClient):
        r = app_client.delete(
            f"/api/v1/users/{_username_path('@missing')}/products/x"
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# PILOT PROGRESS
# ---------------------------------------------------------------------------
class TestPilotProgress:
    def test_pilot_progress_default_user(self, app_client: TestClient):
        _create_user(app_client, username="@uu")
        r = app_client.get(
            f"/api/v1/users/{_username_path('@uu')}/pilot-progress"
        )
        assert r.status_code == 200
        body = r.json()
        assert body["username"] == "@uu"
        assert body["status"] == "pilot"
        assert body["graduation_status"] == "not_eligible"
        # 5 vías por defecto: 0 vídeos, 0 órdenes, 0 followers, CHR 200, 0 días
        assert len(body["requirements_met"]) == 3
        names = {req["name"] for req in body["requirements_met"]}
        assert names == {
            "via_a_5000_followers",
            "via_b_videos_quiz_chr",
            "via_c_orders_30d",
        }
        assert all(not req["met"] for req in body["requirements_met"])
        assert body["weekly_shoppable_remaining"] == 5
        assert body["weekly_shoppable_used"] == 0
        assert body["days_until_eligible"] is None

    def test_pilot_progress_via_a_eligible_with_5000_followers(
        self, app_client: TestClient
    ):
        _create_user(app_client, username="@famoso", followers_count=5000)
        r = app_client.get(
            f"/api/v1/users/{_username_path('@famoso')}/pilot-progress"
        )
        body = r.json()
        assert body["graduation_status"] == "eligible"
        assert body["days_until_eligible"] == 0
        via_a = next(req for req in body["requirements_met"] if req["name"] == "via_a_5000_followers")
        assert via_a["met"] is True

    def test_pilot_progress_graduated_status(self, app_client: TestClient):
        _create_user(app_client, username="@grad")
        app_client.put(
            f"/api/v1/users/{_username_path('@grad')}",
            json={"status": "graduated"},
        )
        r = app_client.get(
            f"/api/v1/users/{_username_path('@grad')}/pilot-progress"
        )
        body = r.json()
        assert body["status"] == "graduated"
        assert body["graduation_status"] == "graduated"

    def test_pilot_progress_via_b_blocking_only_days(
        self, app_client: TestClient, fake_shop_redis
    ):
        """Si tiene 6 vídeos + quiz + CHR≥176 y solo le faltan días → days_until_eligible >0."""
        # Crear usuario y modificar pilot_program directamente en redis
        from src.tiktok_shop.models import TikTokUser, PilotProgramState

        recent_start = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        user = TikTokUser(
            username="@cerca_grad",
            display_name="Casi grad",
            creator_health_rating=180,
            pilot_program=PilotProgramState(
                started_at=recent_start,
                shoppable_videos_published=6,
                quiz_passed=True,
            ),
        )
        from src.tiktok_shop.repos import UserRepo
        repo = UserRepo(fake_shop_redis)
        repo.save(user)

        r = app_client.get(
            f"/api/v1/users/{_username_path('@cerca_grad')}/pilot-progress"
        )
        body = r.json()
        assert body["graduation_status"] == "not_eligible"
        assert body["days_until_eligible"] == 20  # 30 - 10
        via_b = next(req for req in body["requirements_met"] if req["name"] == "via_b_videos_quiz_chr")
        assert via_b["met"] is False
        # Solo debe faltar días, ningún otro requisito
        assert any("días" in m for m in via_b["missing"])

    def test_pilot_progress_missing_user(self, app_client: TestClient):
        r = app_client.get(
            f"/api/v1/users/{_username_path('@missing')}/pilot-progress"
        )
        assert r.status_code == 404
