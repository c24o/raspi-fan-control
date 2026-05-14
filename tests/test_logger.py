"""Tests for src.logger — centralized logging configuration."""

from __future__ import annotations

import logging
import sys

from src.logger import setup_logging


class TestSetupLogging:
    """Tests for the logging setup function."""

    def test_sets_root_logger_level_info(self) -> None:
        setup_logging("INFO")
        assert logging.getLogger().level == logging.INFO

    def test_sets_root_logger_level_debug(self) -> None:
        setup_logging("DEBUG")
        assert logging.getLogger().level == logging.DEBUG

    def test_sets_root_logger_level_warning(self) -> None:
        setup_logging("WARNING")
        assert logging.getLogger().level == logging.WARNING

    def test_sets_root_logger_level_error(self) -> None:
        setup_logging("ERROR")
        assert logging.getLogger().level == logging.ERROR

    def test_sets_root_logger_level_critical(self) -> None:
        setup_logging("CRITICAL")
        assert logging.getLogger().level == logging.CRITICAL

    def test_accepts_lowercase_level(self) -> None:
        setup_logging("debug")
        assert logging.getLogger().level == logging.DEBUG

    def test_invalid_level_falls_back_to_info(self) -> None:
        setup_logging("NONEXISTENT")
        assert logging.getLogger().level == logging.INFO

    def test_handler_outputs_to_stdout(self) -> None:
        setup_logging("INFO")
        root = logging.getLogger()
        assert len(root.handlers) == 1
        handler = root.handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        assert handler.stream is sys.stdout

    def test_no_duplicate_handlers_on_repeated_calls(self) -> None:
        setup_logging("INFO")
        setup_logging("DEBUG")
        setup_logging("WARNING")
        root = logging.getLogger()
        assert len(root.handlers) == 1

    def test_log_format_includes_level_and_name(self) -> None:
        setup_logging("INFO")
        root = logging.getLogger()
        handler = root.handlers[0]
        fmt = handler.formatter._fmt
        assert "%(levelname)s" in fmt
        assert "%(name)s" in fmt

    def test_log_format_has_no_timestamp(self) -> None:
        """journald adds its own timestamp — we should not duplicate it."""
        setup_logging("INFO")
        handler = logging.getLogger().handlers[0]
        fmt = handler.formatter._fmt
        assert "asctime" not in fmt

    def test_default_level_is_info(self) -> None:
        setup_logging()
        assert logging.getLogger().level == logging.INFO
