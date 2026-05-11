"""Reproducibility envelope assertions (ADR-007 §8).

Env-var checks are skipped outside CI so local developer runs are unaffected.
The JavaParser version cross-check always runs: pom.xml and pyproject.toml
must agree at all times, not just on CI.
"""

from __future__ import annotations

import os
import sys
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent
_IN_CI = bool(os.environ.get("CI"))
_CI_ONLY = pytest.mark.skipif(not _IN_CI, reason="reproducibility envelope — CI only")

_POM_NS = "http://maven.apache.org/POM/4.0.0"


# ---------------------------------------------------------------------------
# Env var checks (CI only)
# ---------------------------------------------------------------------------


@_CI_ONLY
def test_tz_is_utc() -> None:
    assert os.environ.get("TZ") == "UTC", (
        "TZ must be UTC in CI (ADR-007 §8). "
        "Add 'TZ: UTC' to the workflow env block."
    )


@_CI_ONLY
def test_lc_all_is_c_utf8() -> None:
    assert os.environ.get("LC_ALL") == "C.UTF-8", (
        "LC_ALL must be C.UTF-8 in CI (ADR-007 §8). "
        "Add 'LC_ALL: C.UTF-8' to the workflow env block."
    )


@_CI_ONLY
def test_pythonhashseed_is_zero() -> None:
    assert os.environ.get("PYTHONHASHSEED") == "0", (
        "PYTHONHASHSEED must be '0' in CI (ADR-007 §8). "
        "Add 'PYTHONHASHSEED: \"0\"' to the workflow env block."
    )


# ---------------------------------------------------------------------------
# Python version (always)
# ---------------------------------------------------------------------------


def test_python_version_at_least_312() -> None:
    assert sys.version_info >= (3, 12), (
        f"Python ≥ 3.12 required (ADR-007); got {sys.version}"
    )


# ---------------------------------------------------------------------------
# JavaParser version cross-check (always)
# ---------------------------------------------------------------------------


def test_javaparser_version_consistent() -> None:
    """pyproject.toml [tool.codeograph.versions].javaparser must match pom.xml."""
    with open(_REPO_ROOT / "pyproject.toml", "rb") as fh:
        toml_version: str = tomllib.load(fh)["tool"]["codeograph"]["versions"]["javaparser"]

    pom_root = ET.parse(
        _REPO_ROOT / "codeograph" / "parser" / "java" / "pom.xml"
    ).getroot()
    props = pom_root.find(f"{{{_POM_NS}}}properties")
    assert props is not None, "pom.xml has no <properties> block"
    pom_elem = props.find(f"{{{_POM_NS}}}javaparser.version")
    assert pom_elem is not None, "pom.xml <properties> has no <javaparser.version>"

    assert pom_elem.text == toml_version, (
        f"JavaParser version mismatch: pom.xml={pom_elem.text!r} vs "
        f"pyproject.toml={toml_version!r}. "
        "Update both files together and rebuild parser.jar."
    )
