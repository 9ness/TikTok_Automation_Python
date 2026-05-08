"""Tests del Pilot Program tracker — graduación, reset semanal, contadores."""

from datetime import datetime, timezone

from src.tiktok_shop.models import PilotProgramState, TikTokUser
from src.tiktok_shop.services.pilot_tracker import (
    can_publish_shoppable,
    days_in_pilot,
    update_pilot_progress,
    weeks_progress,
)


def _make_user(**kwargs) -> TikTokUser:
    return TikTokUser(username="@u", display_name="U", **kwargs)


class TestDaysInPilot:
    def test_days_in_pilot_counts_from_started_at(self):
        u = _make_user(pilot_program=PilotProgramState(started_at="2026-01-01T00:00:00+00:00"))
        d = days_in_pilot(u)
        assert d > 0  # llevamos > 0 días desde el 1 enero 2026

    def test_invalid_date_returns_zero(self):
        u = _make_user(pilot_program=PilotProgramState(started_at="not-a-date"))
        assert days_in_pilot(u) == 0


class TestWeeksProgress:
    def test_full_week_unused(self):
        u = _make_user()  # default 5 remaining
        wp = weeks_progress(u)
        assert wp["shoppable_used"] == 0
        assert wp["shoppable_remaining"] == 5

    def test_partial_used(self):
        u = _make_user(pilot_program=PilotProgramState(weekly_shoppable_remaining=2))
        wp = weeks_progress(u)
        assert wp["shoppable_used"] == 3
        assert wp["shoppable_remaining"] == 2


class TestCanPublishShoppable:
    def test_pilot_can_publish_when_remaining(self):
        u = _make_user()
        assert can_publish_shoppable(u) is True

    def test_pilot_blocked_when_zero_remaining(self):
        u = _make_user(pilot_program=PilotProgramState(
            weekly_shoppable_remaining=0,
            weekly_shoppable_reset_at="2099-12-31",  # lejano → no resetea
        ))
        assert can_publish_shoppable(u) is False

    def test_graduated_always_can(self):
        u = _make_user(status="graduated")
        u.pilot_program.weekly_shoppable_remaining = 0
        assert can_publish_shoppable(u) is True


class TestUpdatePilotProgress:
    def test_shoppable_decrements_counter(self):
        u = _make_user()
        update_pilot_progress(u, video_was_shoppable=True)
        assert u.pilot_program.shoppable_videos_published == 1
        assert u.pilot_program.weekly_shoppable_remaining == 4

    def test_non_shoppable_no_decrement(self):
        u = _make_user()
        update_pilot_progress(u, video_was_shoppable=False)
        assert u.pilot_program.shoppable_videos_published == 0
        assert u.pilot_program.weekly_shoppable_remaining == 5

    def test_graduated_user_not_decremented(self):
        # Graduado: no se descuenta semanal ni se incrementa contador
        u = _make_user(status="graduated")
        update_pilot_progress(u, video_was_shoppable=True)
        assert u.pilot_program.shoppable_videos_published == 0

    def test_eligible_via_followers(self):
        u = _make_user(followers_count=5500)  # >5000 → vía A
        update_pilot_progress(u, video_was_shoppable=False)
        assert u.pilot_program.graduation_eligible is True

    def test_eligible_via_six_videos_plus_quiz_plus_chr(self):
        # Vía B: 6 vids + 30 días + quiz + CHR>=176
        old = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()
        u = _make_user(
            creator_health_rating=180,
            pilot_program=PilotProgramState(
                started_at=old, shoppable_videos_published=5,
                quiz_passed=True,
            ),
        )
        update_pilot_progress(u, video_was_shoppable=True)  # llega a 6
        assert u.pilot_program.graduation_eligible is True

    def test_not_eligible_if_chr_low(self):
        old = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()
        u = _make_user(
            creator_health_rating=170,  # <176
            pilot_program=PilotProgramState(
                started_at=old, shoppable_videos_published=10,
                quiz_passed=True,
            ),
        )
        update_pilot_progress(u, video_was_shoppable=False)
        assert u.pilot_program.graduation_eligible is False

    def test_eligible_via_ten_orders(self):
        old = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()
        u = _make_user(pilot_program=PilotProgramState(
            started_at=old, orders_generated=10,
        ))
        update_pilot_progress(u, video_was_shoppable=False)
        assert u.pilot_program.graduation_eligible is True
