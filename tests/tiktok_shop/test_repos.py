"""Tests de los repos Redis con FakeRedis (sin Upstash real)."""

import pytest

from src.tiktok_shop.models import (
    Product,
    ProductPhoto,
    ProductPhotos,
    TikTokUser,
    VideoCost,
    VideoGeneration,
    VoiceClone,
)
from src.tiktok_shop.repos import (
    GenerationRepo,
    ProductRepo,
    UserRepo,
    VoiceRepo,
)


# ---------------------------------------------------------------------------
# UserRepo
# ---------------------------------------------------------------------------
class TestUserRepo:
    def test_save_and_get_roundtrip(self, fake_redis, sample_user):
        repo = UserRepo(redis=fake_redis)
        repo.save(sample_user)
        loaded = repo.get(sample_user.id)
        assert loaded is not None
        assert loaded.username == sample_user.username
        assert loaded.display_name == sample_user.display_name
        assert loaded.default_video_tier == "standard"

    def test_get_by_username_with_at(self, fake_redis, sample_user):
        repo = UserRepo(redis=fake_redis)
        repo.save(sample_user)
        loaded = repo.get_by_username(sample_user.username)
        assert loaded is not None
        assert loaded.id == sample_user.id

    def test_get_by_username_without_at_normalizes(self, fake_redis, sample_user):
        repo = UserRepo(redis=fake_redis)
        repo.save(sample_user)
        # @test_user → "test_user" debería resolverse igual
        loaded = repo.get_by_username("test_user")
        assert loaded is not None
        assert loaded.id == sample_user.id

    def test_get_unknown_returns_none(self, fake_redis):
        repo = UserRepo(redis=fake_redis)
        assert repo.get("inexistente") is None

    def test_list_all_returns_sorted_recent_first(self, fake_redis):
        repo = UserRepo(redis=fake_redis)
        u1 = TikTokUser(username="@a", display_name="A", created_at="2026-01-01T00:00:00+00:00")
        u2 = TikTokUser(username="@b", display_name="B", created_at="2026-02-01T00:00:00+00:00")
        u3 = TikTokUser(username="@c", display_name="C", created_at="2026-03-01T00:00:00+00:00")
        repo.save(u1)
        repo.save(u2)
        repo.save(u3)
        users = repo.list_all()
        assert len(users) == 3
        assert [u.username for u in users] == ["@c", "@b", "@a"]

    def test_delete_removes_user_and_indexes(self, fake_redis, sample_user):
        repo = UserRepo(redis=fake_redis)
        repo.save(sample_user)
        assert repo.delete(sample_user.id) is True
        assert repo.get(sample_user.id) is None
        assert repo.get_by_username(sample_user.username) is None
        # Y desaparece del listado
        assert sample_user.id not in [u.id for u in repo.list_all()]

    def test_delete_unknown_returns_false(self, fake_redis):
        repo = UserRepo(redis=fake_redis)
        assert repo.delete("inexistente") is False

    def test_assign_product(self, fake_redis, sample_user):
        repo = UserRepo(redis=fake_redis)
        repo.save(sample_user)
        assert repo.assign_product(sample_user.id, "p_123") is True
        loaded = repo.get(sample_user.id)
        assert "p_123" in loaded.assigned_products

    def test_assign_product_idempotent(self, fake_redis, sample_user):
        repo = UserRepo(redis=fake_redis)
        repo.save(sample_user)
        repo.assign_product(sample_user.id, "p_123")
        repo.assign_product(sample_user.id, "p_123")
        loaded = repo.get(sample_user.id)
        assert loaded.assigned_products.count("p_123") == 1

    def test_unassign_product(self, fake_redis, sample_user):
        repo = UserRepo(redis=fake_redis)
        sample_user.assigned_products = ["p_123"]
        repo.save(sample_user)
        assert repo.unassign_product(sample_user.id, "p_123") is True
        loaded = repo.get(sample_user.id)
        assert "p_123" not in loaded.assigned_products


# ---------------------------------------------------------------------------
# ProductRepo + auto-migración legacy
# ---------------------------------------------------------------------------
class TestProductRepo:
    def test_save_and_get_roundtrip(self, fake_redis, sample_product):
        repo = ProductRepo(redis=fake_redis)
        repo.save(sample_product)
        loaded = repo.get(sample_product.id)
        assert loaded is not None
        assert loaded.slug == sample_product.slug
        assert isinstance(loaded.photos, ProductPhotos)

    def test_get_by_slug(self, fake_redis, sample_product):
        repo = ProductRepo(redis=fake_redis)
        repo.save(sample_product)
        assert repo.get_by_slug(sample_product.slug).id == sample_product.id

    def test_invalid_slug_rejected_at_model(self):
        with pytest.raises(ValueError, match="slug inválido"):
            Product(slug="UPPER CASE", name="bad")

    def test_delete_removes_product(self, fake_redis, sample_product):
        repo = ProductRepo(redis=fake_redis)
        repo.save(sample_product)
        repo.delete(sample_product.id)
        assert repo.get(sample_product.id) is None
        assert repo.get_by_slug(sample_product.slug) is None

    def test_list_all_recent_first(self, fake_redis):
        repo = ProductRepo(redis=fake_redis)
        p1 = Product(slug="p1", name="P1", created_at="2026-01-01T00:00:00+00:00")
        p2 = Product(slug="p2", name="P2", created_at="2026-02-01T00:00:00+00:00")
        repo.save(p1)
        repo.save(p2)
        listed = repo.list_all()
        assert [p.slug for p in listed] == ["p2", "p1"]

    # ------------------------------------------------------------------
    # Auto-migración legacy v1 → v2 (tested también en _smoke pero formal aquí)
    # ------------------------------------------------------------------
    def test_migrate_legacy_photos_flat_to_dict(self, fake_redis):
        repo = ProductRepo(redis=fake_redis)
        # Producto con shape v1: photos como lista plana
        legacy = {
            "id": "leg",
            "slug": "legacy_p",
            "name": "Legacy Product",
            "photos": [
                {"filename": "a.jpg"},
                {"filename": "b.jpg"},
            ],
            "video_config": {"default_model": "seedance_1_5_pro_fast"},
        }
        fake_redis.set_json("product:leg", legacy)
        fake_redis.sadd("product:index", "leg")

        loaded = repo.get("leg")
        assert loaded is not None
        assert isinstance(loaded.photos, ProductPhotos)
        assert len(loaded.photos.source) == 2
        assert loaded.photos.generated == []
        assert loaded.photos.source[0].filename == "a.jpg"

    def test_migrate_legacy_default_model_to_default_tier(self, fake_redis):
        repo = ProductRepo(redis=fake_redis)
        legacy = {
            "id": "leg2", "slug": "legacy_p2", "name": "L2",
            "photos": [],
            "video_config": {
                "default_model": "seedance_1_5_pro_fast",
                "avoid_packaging_close_up": True,
            },
        }
        fake_redis.set_json("product:leg2", legacy)
        fake_redis.sadd("product:index", "leg2")
        loaded = repo.get("leg2")
        assert loaded.video_config.default_tier == "standard"
        assert loaded.video_config.has_complex_packaging is True

    def test_migrate_legacy_seedance_2_pro_to_pro_tier(self, fake_redis):
        repo = ProductRepo(redis=fake_redis)
        legacy = {
            "id": "leg3", "slug": "legacy_p3", "name": "L3", "photos": [],
            "video_config": {"default_model": "seedance_2_0_pro"},
        }
        fake_redis.set_json("product:leg3", legacy)
        fake_redis.sadd("product:index", "leg3")
        assert repo.get("leg3").video_config.default_tier == "pro"

    def test_migration_idempotent_on_v2_data(self, fake_redis):
        repo = ProductRepo(redis=fake_redis)
        # Producto ya en shape v2
        v2 = Product(slug="already_v2", name="V2", photos=ProductPhotos(
            source=[ProductPhoto(filename="x.jpg")],
            generated=[ProductPhoto(filename="y.jpg")],
        ))
        repo.save(v2)
        loaded = repo.get(v2.id)
        assert len(loaded.photos.source) == 1
        assert len(loaded.photos.generated) == 1

    def test_migration_unknown_legacy_model_falls_to_standard(self, fake_redis):
        repo = ProductRepo(redis=fake_redis)
        legacy = {
            "id": "lx", "slug": "lx", "name": "X", "photos": [],
            "video_config": {"default_model": "unknown_legacy_id"},
        }
        fake_redis.set_json("product:lx", legacy)
        fake_redis.sadd("product:index", "lx")
        assert repo.get("lx").video_config.default_tier == "standard"


# ---------------------------------------------------------------------------
# GenerationRepo (CRUD + agregaciones)
# ---------------------------------------------------------------------------
class TestGenerationRepo:
    def test_save_and_get(self, fake_redis, sample_generation):
        repo = GenerationRepo(redis=fake_redis)
        repo.save(sample_generation)
        loaded = repo.get(sample_generation.id)
        assert loaded is not None
        assert loaded.tier_used == "standard"
        assert loaded.cost.total == 0.275

    def test_save_indexes_first_time_only(self, fake_redis, sample_generation):
        # Updates posteriores no deben re-indexar (test que no se duplica en LIST)
        repo = GenerationRepo(redis=fake_redis)
        repo.save(sample_generation)
        repo.save(sample_generation)  # update, mismo id
        ids = repo.r.lrange(GenerationRepo.INDEX_LIST, 0, -1)
        assert ids.count(sample_generation.id) == 1

    def test_list_recent_returns_newest_first(self, fake_redis):
        repo = GenerationRepo(redis=fake_redis)
        for i in range(5):
            g = VideoGeneration(
                user_id="u1", product_id="p1", tier_used="standard",
                cost=VideoCost(total=0.1 * (i + 1)),
                created_at=f"2026-05-0{i+1}T10:00:00+00:00",
            )
            repo.save(g)
        recent = repo.list_recent(limit=3)
        assert len(recent) == 3
        # LPUSH inserta al principio → el último guardado sale primero
        assert recent[0].cost.total == pytest.approx(0.5, abs=0.001)

    def test_list_by_user(self, fake_redis):
        repo = GenerationRepo(redis=fake_redis)
        g1 = VideoGeneration(user_id="u1", product_id="p1", tier_used="standard")
        g2 = VideoGeneration(user_id="u1", product_id="p2", tier_used="advanced")
        g3 = VideoGeneration(user_id="u2", product_id="p1", tier_used="pro")
        repo.save(g1)
        repo.save(g2)
        repo.save(g3)
        u1_gens = repo.list_by_user("u1")
        assert len(u1_gens) == 2

    def test_list_by_product(self, fake_redis):
        repo = GenerationRepo(redis=fake_redis)
        g1 = VideoGeneration(user_id="u1", product_id="p1", tier_used="standard")
        g2 = VideoGeneration(user_id="u2", product_id="p1", tier_used="advanced")
        g3 = VideoGeneration(user_id="u1", product_id="p2", tier_used="pro")
        repo.save(g1)
        repo.save(g2)
        repo.save(g3)
        p1_gens = repo.list_by_product("p1")
        assert len(p1_gens) == 2

    def test_total_cost_by_user(self, fake_redis):
        repo = GenerationRepo(redis=fake_redis)
        for total in (0.27, 0.71, 1.08):
            repo.save(VideoGeneration(
                user_id="u1", product_id="p1", tier_used="standard",
                cost=VideoCost(total=total),
                created_at="2026-05-07T10:00:00+00:00",
            ))
        assert repo.total_cost_by_user("u1") == pytest.approx(2.06)

    def test_total_cost_by_tier_only_matches_tier(self, fake_redis):
        repo = GenerationRepo(redis=fake_redis)
        repo.save(VideoGeneration(user_id="u", product_id="p", tier_used="standard",
                                  cost=VideoCost(total=0.27),
                                  created_at="2026-05-07T10:00:00+00:00"))
        repo.save(VideoGeneration(user_id="u", product_id="p", tier_used="pro",
                                  cost=VideoCost(total=1.08),
                                  created_at="2026-05-07T10:00:00+00:00"))
        assert repo.total_cost_by_tier("standard") == 0.27
        assert repo.total_cost_by_tier("pro") == 1.08
        assert repo.total_cost_by_tier("advanced") == 0

    def test_monthly_summary_groups_by_month(self, fake_redis):
        repo = GenerationRepo(redis=fake_redis)
        repo.save(VideoGeneration(user_id="u", product_id="p", tier_used="standard",
                                  cost=VideoCost(total=0.27),
                                  created_at="2026-05-07T10:00:00+00:00"))
        repo.save(VideoGeneration(user_id="u", product_id="p", tier_used="pro",
                                  cost=VideoCost(total=1.08),
                                  created_at="2026-05-15T10:00:00+00:00"))
        repo.save(VideoGeneration(user_id="u", product_id="p", tier_used="advanced",
                                  cost=VideoCost(total=0.71),
                                  created_at="2026-04-15T10:00:00+00:00"))
        summary = repo.monthly_summary()
        assert "2026-05" in summary and "2026-04" in summary
        assert summary["2026-05"]["total"] == pytest.approx(1.35)
        assert summary["2026-05"]["count"] == 2
        assert summary["2026-04"]["total"] == 0.71

    def test_monthly_summary_skips_invalid_dates(self, fake_redis):
        repo = GenerationRepo(redis=fake_redis)
        repo.save(VideoGeneration(user_id="u", product_id="p", tier_used="standard",
                                  cost=VideoCost(total=0.27),
                                  created_at="invalid-date"))
        summary = repo.monthly_summary()
        # No revienta y no incluye la fecha inválida
        assert all("invalid" not in m for m in summary.keys())


# ---------------------------------------------------------------------------
# VoiceRepo
# ---------------------------------------------------------------------------
class TestVoiceRepo:
    def test_list_all_includes_presets(self, fake_redis):
        repo = VoiceRepo(redis=fake_redis)
        voices = repo.list_all(include_presets=True)
        # 3 presets ES por defecto
        assert len([v for v in voices if v.is_preset]) == 3

    def test_list_all_excludes_presets_if_disabled(self, fake_redis):
        repo = VoiceRepo(redis=fake_redis)
        voices = repo.list_all(include_presets=False)
        assert all(not v.is_preset for v in voices)
        assert voices == []  # no hay clonadas todavía

    def test_save_clone_appears_in_list(self, fake_redis):
        repo = VoiceRepo(redis=fake_redis)
        v = VoiceClone(name="My Voice", minimax_voice_id="custom_xyz", language="es")
        repo.save(v)
        voices = repo.list_all(include_presets=False)
        assert len(voices) == 1
        assert voices[0].minimax_voice_id == "custom_xyz"

    def test_delete_preset_blocked(self, fake_redis):
        repo = VoiceRepo(redis=fake_redis)
        # Los presets tienen id "preset_..." y delete devuelve False sin tocar Redis
        assert repo.delete("preset_Spanish_EnergeticBoy") is False

    def test_delete_clone_works(self, fake_redis):
        repo = VoiceRepo(redis=fake_redis)
        v = VoiceClone(name="X", minimax_voice_id="vid_x", language="es")
        repo.save(v)
        assert repo.delete(v.id) is True
        assert repo.get(v.id) is None
