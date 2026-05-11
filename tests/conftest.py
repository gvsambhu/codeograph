"""
Test-suite pytest configuration (tests/conftest.py).

Registers:
  --update-goldens  CLI flag (consumed by tests/test_golden.py)
  update_goldens    fixture that exposes the flag value to test functions
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-goldens",
        action="store_true",
        default=False,
        help="Overwrite stored golden graph files instead of comparing against them.",
    )


@pytest.fixture
def update_goldens(request: pytest.FixtureRequest) -> bool:
    """True when --update-goldens was passed on the command line."""
    return bool(request.config.getoption("--update-goldens"))
