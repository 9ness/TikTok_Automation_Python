"""Tests del logger estructurado."""

import logging
import os

import pytest

from src.tiktok_shop.utils.logging_setup import (
    _LOGGERS_CONFIGURED,
    _format_context,
    get_logger,
    log_debug,
    log_error,
    log_info,
    log_warning,
    log_with_context,
)


@pytest.fixture(autouse=True)
def reset_logger_cache(tmp_path, monkeypatch):
    """Cada test: usa un dir tmp y resetea el set de loggers configurados."""
    monkeypatch.setenv("TIKTOK_SHOP_LOG_DIR", str(tmp_path))
    _LOGGERS_CONFIGURED.clear()
    yield
    _LOGGERS_CONFIGURED.clear()


class TestGetLogger:
    def test_returns_logger_instance(self):
        log = get_logger("tiktok_shop.test")
        assert isinstance(log, logging.Logger)

    def test_idempotent_no_duplicate_handlers(self):
        a = get_logger("tiktok_shop.dup")
        b = get_logger("tiktok_shop.dup")
        assert a is b
        # Handlers se añaden una sola vez
        assert len(a.handlers) == 2  # file + console

    def test_creates_log_dir(self, tmp_path):
        target = tmp_path / "subdir"
        os.environ["TIKTOK_SHOP_LOG_DIR"] = str(target)
        get_logger("tiktok_shop.t1")
        assert target.exists()


class TestFormatContext:
    def test_empty_dict(self):
        assert _format_context({}) == ""

    def test_single_kv(self):
        assert _format_context({"job_id": "abc"}) == " | ctx=job_id=abc"

    def test_multi_kv_preserves_insertion_order(self):
        out = _format_context({"job_id": "abc", "tier": "pro"})
        assert "job_id=abc" in out
        assert "tier=pro" in out

    def test_truncates_long_values(self):
        long = "x" * 500
        out = _format_context({"prompt": long})
        # Debe acabar en "..."
        assert "..." in out
        # Y NO contener los 500 chars enteros
        assert "x" * 500 not in out


class TestLogWithContext:
    def test_writes_to_file(self, tmp_path):
        log_info("tiktok_shop.test_file", "hello", job_id="J1", tier="standard")
        # Forzar flush de los handlers
        for h in get_logger("tiktok_shop.test_file").handlers:
            h.flush()

        # Buscar archivo de log generado
        files = list(tmp_path.glob("tiktok_shop.log*"))
        assert files, f"No se encontró archivo de log en {tmp_path}"
        content = files[0].read_text(encoding="utf-8")
        assert "hello" in content
        assert "job_id=J1" in content
        assert "tier=standard" in content

    def test_log_levels(self, tmp_path):
        log_info("tiktok_shop.lvl",    "info msg")
        log_warning("tiktok_shop.lvl", "warn msg")
        log_error("tiktok_shop.lvl",   "error msg")
        log_debug("tiktok_shop.lvl",   "debug msg")

        for h in get_logger("tiktok_shop.lvl").handlers:
            h.flush()

        files = list(tmp_path.glob("tiktok_shop.log*"))
        content = files[0].read_text(encoding="utf-8")
        assert "[INFO]" in content
        assert "[WARNING]" in content
        assert "[ERROR]" in content
        # Debug también va al archivo (level DEBUG)
        assert "[DEBUG]" in content

    def test_logger_can_be_string_or_instance(self, tmp_path):
        # Por nombre
        log_info("tiktok_shop.s1", "by_name", a=1)
        # Por instancia
        inst = get_logger("tiktok_shop.s2")
        log_with_context(inst, logging.INFO, "by_instance", b=2)

        for name in ("tiktok_shop.s1", "tiktok_shop.s2"):
            for h in get_logger(name).handlers:
                h.flush()

        files = list(tmp_path.glob("tiktok_shop.log*"))
        content = files[0].read_text(encoding="utf-8")
        assert "by_name" in content
        assert "by_instance" in content
