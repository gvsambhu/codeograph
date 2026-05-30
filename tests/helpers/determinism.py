"""Determinism helpers for evaluation framework tests."""

import logging
import re
from typing import Any


def assert_byte_equal_except(actual: dict[str, Any], expected: dict[str, Any], *, ignore_keys: list[str]) -> None:
    """Assert that two dictionaries are equal except for the specified top-level keys."""
    actual_filtered = {k: v for k, v in actual.items() if k not in ignore_keys}
    expected_filtered = {k: v for k, v in expected.items() if k not in ignore_keys}
    assert actual_filtered == expected_filtered


def assert_scorecard_structural(actual: dict[str, Any], *, kind: str) -> None:
    """Validate the shape of a scorecard dictionary."""
    assert actual.get("kind") == kind
    assert "checks" in actual
    assert isinstance(actual["checks"], list)
    for check in actual["checks"]:
        assert "id" in check
        assert "category" in check
        assert "result" in check
        assert "value" in check
        assert "threshold" in check
        assert "rationale" in check


def assert_compile_check_byte_equal(actual: dict[str, Any], expected_checks: list[dict[str, Any]], *, ignore_renderer_version: bool = True) -> None:
    """Assert that a compile_checks sidecar matches expected_checks."""
    assert "checks" in actual
    assert actual["checks"] == expected_checks


def assert_log_contains(caplog: Any, message_substring: str, *, level: int = logging.INFO) -> None:
    """Assert that a given string appears in the captured logs at the specified level."""
    found = any(
        message_substring in record.message and record.levelno == level
        for record in caplog.records
    )
    assert found, f"Expected substring '{message_substring}' not found in logs at level {level}"


def assert_iso8601(value: str) -> None:
    """Assert that the value is an ISO 8601 (RFC 3339 subset) formatted string."""
    pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$"
    assert re.match(pattern, value) is not None, f"'{value}' does not match ISO 8601 format"


def assert_sha256(value: str, *, length: int = 64) -> None:
    """Assert that the value is a valid hex string representing a SHA-256 hash."""
    pattern = rf"^[a-fA-F0-9]{{{length}}}$"
    assert re.match(pattern, value) is not None, f"'{value}' is not a valid {length}-character hex string"
