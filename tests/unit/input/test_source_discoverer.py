"""
Unit tests for SourceDiscoverer — module root discovery and naming (ADR-002 D-002-1).
"""

from __future__ import annotations

from pathlib import Path


def test_module_name_uses_directory_name(tmp_path: Path) -> None:
    """Parent-bearing pom.xml: _module_name returns directory name, NOT parent artifactId."""
    # TODO(learner): write assertions.


def test_module_name_gradle_uses_directory_name(tmp_path: Path) -> None:
    """Gradle module (no pom.xml): directory name returned."""
    # TODO(learner): write assertions.


def test_module_name_multi_module_distinct_names(tmp_path: Path) -> None:
    """Two sibling modules under a shared parent resolve to distinct directory names."""
    # TODO(learner): write assertions.
