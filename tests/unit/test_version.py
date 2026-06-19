"""Confirmation tests for ADR-026 Fork 4 — single version source.

The version is authored once in pyproject.toml and read at runtime via
importlib.metadata; codeograph.__version__ must resolve from that metadata, not
from an independent hand-maintained literal (ADR-026 Confirmations #1 and #3).
"""

from __future__ import annotations

from importlib.metadata import version

import codeograph


def test_version_attribute_resolves_from_metadata() -> None:
    """__version__ equals the installed package metadata version (ADR-026 #1/#3)."""
    assert codeograph.__version__ == version("codeograph")


def test_version_is_nonempty_pep440_like() -> None:
    """A real version was resolved (not the source-tree fallback)."""
    assert codeograph.__version__
    assert codeograph.__version__[0].isdigit()
