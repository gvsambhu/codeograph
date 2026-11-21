"""
Unit tests for SourceDiscoverer — module root discovery and naming (ADR-002 D-002-1).
"""

from __future__ import annotations

from pathlib import Path

import pathspec

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


def test_source_packages_named_like_build_outputs_are_discovered_and_gitignore_still_applies(
    tmp_path: Path,
) -> None:
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    expected: set[str] = set()
    for directory in ("build", "out", "target"):
        source = tmp_path / "src/main/java/com/acme" / directory / f"{directory.capitalize()}.java"
        source.parent.mkdir(parents=True)
        source.write_text(f"public class {directory.capitalize()} {{}}", encoding="utf-8")
        expected.add(source.relative_to(tmp_path).as_posix())
    ignored = tmp_path / "src/main/java/com/acme/ignored/Ignored.java"
    ignored.parent.mkdir(parents=True)
    ignored.write_text("public class Ignored {}", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("ignored/\n", encoding="utf-8")

    modules = SourceDiscoverer().discover(tmp_path)

    assert len(modules) == 1
    assert {path.relative_to(tmp_path).as_posix() for path in modules[0].java_files} == expected


def test_module_root_target_is_excluded(tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    source = tmp_path / "src/main/java/App.java"
    source.parent.mkdir(parents=True)
    source.write_text("public class App {}", encoding="utf-8")
    generated = tmp_path / "target/generated/Generated.java"
    generated.parent.mkdir(parents=True)
    generated.write_text("public class Generated {}", encoding="utf-8")
    discoverer = SourceDiscoverer()
    corpus_filter = pathspec.PathSpec.from_lines("gitwildmatch", discoverer._load_corpus_patterns(tmp_path))
    module_filter = discoverer._build_module_filter(tmp_path)

    files = discoverer._list_java_files(tmp_path, tmp_path, tmp_path, corpus_filter, module_filter)

    assert files == [source]
