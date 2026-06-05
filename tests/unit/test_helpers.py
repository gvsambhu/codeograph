"""Unit tests for the determinism helpers."""

import logging

import pytest

from tests.helpers.determinism import (
    assert_byte_equal_except,
    assert_compile_check_byte_equal,
    assert_iso8601,
    assert_log_contains,
    assert_scorecard_structural,
    assert_sha256,
)


def test_assert_byte_equal_except():
    """Test dictionary assertion with top-level key ignore."""
    actual = {"a": 1, "b": 2, "c": 3}
    expected = {"a": 1, "b": 99, "c": 3}
    # Should not raise exception
    assert_byte_equal_except(actual, expected, ignore_keys=["b"])

    with pytest.raises(AssertionError):
        assert_byte_equal_except(actual, expected, ignore_keys=["a"])


def test_assert_scorecard_structural():
    """Test scorecard validation shape."""
    valid_scorecard = {
        "kind": "ts",
        "checks": [
            {
                "id": "compile",
                "category": "code",
                "result": "pass",
                "value": 1.0,
                "threshold": {"kind": "min_ratio", "pass_at_or_above": 1.0},
                "rationale": "Test",
            }
        ],
    }
    # Should not raise
    assert_scorecard_structural(valid_scorecard, kind="ts")

    with pytest.raises(AssertionError):
        # wrong kind
        assert_scorecard_structural(valid_scorecard, kind="graph")

    with pytest.raises(AssertionError):
        # missing checks
        assert_scorecard_structural({"kind": "ts"}, kind="ts")

    with pytest.raises(AssertionError):
        # missing field in check
        invalid_scorecard = {
            "kind": "ts",
            "checks": [{"id": "compile"}],
        }
        assert_scorecard_structural(invalid_scorecard, kind="ts")


def test_assert_compile_check_byte_equal():
    """Test compile check assertion."""
    actual = {
        "renderer_version": "0.4.0",
        "checks": [{"name": "tsc"}],
    }
    expected_checks = [{"name": "tsc"}]
    # Should not raise
    assert_compile_check_byte_equal(actual, expected_checks)

    with pytest.raises(AssertionError):
        assert_compile_check_byte_equal(actual, [{"name": "different"}])


def test_assert_log_contains(caplog):
    """Test captured log verification."""
    logger = logging.getLogger("test_logger")
    logger.setLevel(logging.INFO)
    logger.info("Found 3 components in module.")

    assert_log_contains(caplog, "3 components", level=logging.INFO)

    with pytest.raises(AssertionError):
        assert_log_contains(caplog, "4 components", level=logging.INFO)

    with pytest.raises(AssertionError):
        assert_log_contains(caplog, "3 components", level=logging.ERROR)


def test_assert_iso8601():
    """Test timestamp regex."""
    assert_iso8601("2026-05-28T14:32:11Z")
    assert_iso8601("2026-05-28T14:32:11.123456Z")

    with pytest.raises(AssertionError):
        assert_iso8601("2026-05-28 14:32:11")

    with pytest.raises(AssertionError):
        assert_iso8601("Not a date")


def test_assert_sha256():
    """Test sha256 regex."""
    valid_hash = "a" * 64
    assert_sha256(valid_hash)

    with pytest.raises(AssertionError):
        assert_sha256("short")

    with pytest.raises(AssertionError):
        assert_sha256("z" * 64)  # invalid hex character
