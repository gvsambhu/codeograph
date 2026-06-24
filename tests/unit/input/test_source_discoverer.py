"""
Unit tests for SourceDiscoverer — module root discovery and naming (ADR-002 D-002-1).
"""

from __future__ import annotations

from pathlib import Path

from codeograph.input.source_discoverer import SourceDiscoverer


def test_module_name_uses_directory_name(tmp_path: Path) -> None:
    """Parent-bearing pom.xml: _module_name returns directory name, NOT parent artifactId."""
    module_dir = tmp_path / "my-module"
    module_dir.mkdir()
    (module_dir / "pom.xml").write_text(
        "<project><parent><artifactId>spring-boot-starter-parent</artifactId></parent>"
        "<artifactId>my-module</artifactId></project>",
        encoding="utf-8",
    )

    name = SourceDiscoverer._module_name(module_dir, module_dir / "pom.xml")

    assert name == "my-module"
    assert name != "spring-boot-starter-parent"  # regression guard: the old bug value


def test_module_name_gradle_uses_directory_name(tmp_path: Path) -> None:
    """Gradle module (no pom.xml): directory name returned."""
    module_dir = tmp_path / "my-gradle-module"
    module_dir.mkdir()
    (module_dir / "build.gradle").write_text("// empty", encoding="utf-8")

    name = SourceDiscoverer._module_name(module_dir, None)

    assert name == "my-gradle-module"


def test_module_name_multi_module_distinct_names(tmp_path: Path) -> None:
    """Two sibling modules under a shared parent resolve to distinct directory names."""
    PARENT_ARTIFACT_ID = "codeograph-corpus"

    parent_pom = "<project><parent><artifactId>{p}</artifactId></parent><artifactId>{own}</artifactId></project>"
    for dir_name in ("module-core", "module-web"):
        d = tmp_path / dir_name
        d.mkdir()
        (d / "pom.xml").write_text(
            parent_pom.format(p=PARENT_ARTIFACT_ID, own=dir_name),
            encoding="utf-8",
        )

    name_core = SourceDiscoverer._module_name(tmp_path / "module-core", tmp_path / "module-core" / "pom.xml")
    name_web = SourceDiscoverer._module_name(tmp_path / "module-web", tmp_path / "module-web" / "pom.xml")

    assert name_core == "module-core"
    assert name_web == "module-web"
    assert name_core != name_web  # distinct — the multi-module collision that the bug caused
    assert PARENT_ARTIFACT_ID not in (name_core, name_web)  # regression guard
