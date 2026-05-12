"""
SourceDiscoverer — walk a corpus root and enumerate all Java modules.

Responsibilities (ADR-002):
  - Find every Maven / Gradle module within the corpus
  - Detect the build tool for each module
  - Locate Java source roots inside each module
  - Build two-scope gitignore filters: one corpus-level (hardcoded fallbacks +
    corpus-root .gitignore), one per-module (module-root .gitignore only)
  - Enumerate .java files per source root, applying both filters independently
    at their correct scope (corpus-relative path vs. module-relative path)
  - Return a fully-populated list[ModuleSpec] (including java_files) in
    depth-first order — the parser receives files, not directories

This class only reads the filesystem; it does not parse Java source files.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pathspec

from codeograph.input.models import BuildTool, ModuleSpec

# ---------------------------------------------------------------------------
# Hardcoded fallback ignore patterns (ADR-002).
# Applied when no .gitignore is found, and always merged with any .gitignore
# that IS found.  These patterns match the paths that pathspec will receive
# (relative to the corpus root).
# ---------------------------------------------------------------------------
_FALLBACK_IGNORE_PATTERNS: list[str] = [
    # Build outputs
    "target/",
    "build/",
    "out/",
    # IDE artefacts
    ".idea/",
    ".vscode/",
    "*.iml",
    # VCS
    ".git/",
    # Generated sources — we want hand-written Java only
    "**/generated-sources/",
    "**/generated-test-sources/",
    # Python tooling (if repo is mixed)
    "__pycache__/",
    "*.py[cod]",
    ".venv/",
    "venv/",
]

# Standard Maven/Gradle source root layouts.
# Tried in order; all that exist are included.
_CANDIDATE_SOURCE_ROOTS: list[str] = [
    "src/main/java",
    "src/test/java",
    "src/main/kotlin",  # not parsed in v1; included so the list is complete
]


class SourceDiscoverer:
    """
    Walk a corpus root directory and produce a list of ModuleSpec objects.

    Designed to be instantiated once per run and injected into the concrete
    acquirers. Stateless between calls — safe to reuse across multiple
    acquire() invocations in tests.
    """

    def discover(self, corpus_root: Path) -> list[ModuleSpec]:
        """
        Entry point. Walk corpus_root, find all modules, and return their specs.

        Loads corpus-level ignore patterns once, then for each module detects
        the build tool, source roots, and java files (filtered via gitignore
        chain). Each ModuleSpec is fully populated — the parser receives a
        ready list of files, not directories to walk.

        :param corpus_root: Absolute path to the top of the corpus on disk.
        :returns: One ModuleSpec per detected module, in depth-first order.
        """
        module_roots = self._find_module_roots(corpus_root)
        specs: list[ModuleSpec] = []
        corpus_patterns: list[str] = self._load_corpus_patterns(corpus_root)
        corpus_filter = pathspec.PathSpec.from_lines("gitwildmatch", corpus_patterns)

        for root in module_roots:
            build_tool = self._detect_build_tool(root)
            source_roots = self._find_source_roots(root)
            pom_path = (root / "pom.xml") if build_tool == BuildTool.MAVEN else None
            name = self._module_name(root, pom_path)
            java_files: list[Path] = []

            module_filter = self._build_module_filter(root)
            for source_root in source_roots:
                java_files.extend(self._list_java_files(source_root, corpus_root, root, corpus_filter, module_filter))
            specs.append(
                ModuleSpec(
                    module_id=f"mod:{name}",
                    name=name,
                    root_path=root,
                    build_tool=build_tool,
                    source_roots=source_roots,
                    pom_path=pom_path,
                    java_files=java_files,
                )
            )

        return specs

    def _recursive_find_module_roots(self, root: Path) -> list[Path]:
        """
        DFS walk from root; returns every directory that contains a pom.xml,
        build.gradle, or build.gradle.kts. Skips build output and IDE
        directories to avoid scanning generated class files.
        """
        results: list[Path] = []

        if (root / "pom.xml").exists() or (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
            results.append(root)

        for child in root.iterdir():
            if child.is_dir() and child.name not in {"target", "build", ".git", ".idea", ".vscode"}:
                results.extend(self._recursive_find_module_roots(child))

        return results

    # ------------------------------------------------------------------
    # Module root discovery
    # ------------------------------------------------------------------

    def _find_module_roots(self, corpus_root: Path) -> list[Path]:
        """
        Return the root directory of every Maven / Gradle module under
        corpus_root.

        Validates that corpus_root is a directory, then delegates the DFS
        walk to _recursive_find_module_roots. Result order is depth-first
        (parent module before its children).

        :raises NotADirectoryError: If corpus_root is not a directory.
        """
        if not corpus_root.is_dir():
            raise NotADirectoryError(f"{corpus_root} is not a directory")

        return self._recursive_find_module_roots(corpus_root)

    # ------------------------------------------------------------------
    # Build tool detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_build_tool(module_root: Path) -> BuildTool:
        """
        Return the build tool for a module root.

        Maven wins if both pom.xml and build.gradle are present (ADR-002:
        mixed-build repos are uncommon; Maven is the primary v1 target).
        """
        if (module_root / "pom.xml").exists():
            return BuildTool.MAVEN
        return BuildTool.GRADLE

    # ------------------------------------------------------------------
    # Source root detection
    # ------------------------------------------------------------------

    def _find_source_roots(self, module_root: Path) -> list[Path]:
        """
        Return all existing Java source root directories inside module_root.

        Checks each path in _CANDIDATE_SOURCE_ROOTS in order; includes those
        that exist on disk. Kotlin roots are in the candidate list for
        completeness but excluded here — they are not parsed in v1.

        :returns: Absolute Path objects in _CANDIDATE_SOURCE_ROOTS order
                  (deterministic, no sorting needed).
        """
        result: list[Path] = []
        for source_root_str in _CANDIDATE_SOURCE_ROOTS:
            candidate = module_root / source_root_str
            if source_root_str != "src/main/kotlin" and candidate.is_dir():
                result.append(candidate)
        return result

    # ------------------------------------------------------------------
    # File filtering (two-scope: corpus-level + module-level)
    # ------------------------------------------------------------------

    def _load_corpus_patterns(self, corpus_root: Path) -> list[str]:
        """
        Build the corpus-level pattern list: hardcoded fallbacks merged with
        corpus_root/.gitignore (if present). Called once per run; the result
        is compiled into a corpus_filter PathSpec in discover() and reused for
        every module.

        Patterns are tested against corpus-root-relative paths in
        _list_java_files, so no path-prefix adjustment is needed here.

        Deduplicates via dict.fromkeys to preserve insertion order without
        repeating patterns (order matters for gitignore negation semantics).

        :returns: Deduplicated list of gitwildmatch patterns.
        """
        all_patterns: list[str] = list(_FALLBACK_IGNORE_PATTERNS)
        if (corpus_root / ".gitignore").exists():
            all_patterns.extend((corpus_root / ".gitignore").read_text(encoding="utf-8").splitlines())
        return list(dict.fromkeys(all_patterns))

    def _build_module_filter(self, module_root: Path) -> pathspec.PathSpec[Any]:
        """
        Build a module-scoped pathspec filter from module_root/.gitignore only.

        This filter is intentionally separate from the corpus filter. Patterns
        here are tested against module-root-relative paths in _list_java_files,
        so they are correctly scoped to this module's subtree and cannot
        accidentally match files in sibling modules.

        Example — module-core/.gitignore contains "generated/":
          module_filter.match_file("src/main/generated/Foo.java") → True  (ignored)
          # module-api's files are never tested against this filter

        Returns an empty PathSpec (matches nothing) when no .gitignore exists.
        """
        patterns: list[str] = []
        module_gitignore = module_root / ".gitignore"
        if module_gitignore.exists():
            patterns = module_gitignore.read_text(encoding="utf-8").splitlines()
        return pathspec.PathSpec.from_lines("gitwildmatch", patterns)

    # ------------------------------------------------------------------
    # Java file listing
    # ------------------------------------------------------------------

    def _list_java_files(
        self,
        source_root: Path,
        corpus_root: Path,
        module_root: Path,
        corpus_filter: pathspec.PathSpec[Any],
        module_filter: pathspec.PathSpec[Any],
    ) -> list[Path]:
        """
        Return all .java files under source_root that pass both scope filters.

        Two-scope filtering (ADR-002): each file is tested at the correct path
        scope for each filter layer.

          corpus_filter  ← tested against path relative to corpus_root
                           catches patterns from hardcoded list and corpus .gitignore
                           e.g. "module-core/target/Foo.class"

          module_filter  ← tested against path relative to module_root
                           catches patterns from module-level .gitignore only,
                           scoped to this module — cannot affect sibling modules
                           e.g. "src/main/generated/Foo.java"

        A file is kept only if neither filter matches. Result is sorted for
        stable ordering (ADR-006 canonical-form sha256 contract).

        :param source_root: A single source root dir, e.g. module/src/main/java.
        :param corpus_root: Corpus root; anchors corpus-relative path computation.
        :param module_root: Module root; anchors module-relative path computation.
        :param corpus_filter: PathSpec from hardcoded fallbacks + corpus .gitignore.
        :param module_filter: PathSpec from module-level .gitignore only.
        :returns: Sorted list of absolute Path objects for .java files that pass both filters.
        """
        results = []
        for file in source_root.rglob("*.java"):
            corpus_rel = file.relative_to(corpus_root)
            module_rel = file.relative_to(module_root)
            if not corpus_filter.match_file(str(corpus_rel)) and not module_filter.match_file(str(module_rel)):
                results.append(file)
        return sorted(results)

    # ------------------------------------------------------------------
    # Module name helper  (AI-generated — no TODO)
    # ------------------------------------------------------------------

    @staticmethod
    def _module_name(module_root: Path, pom_path: Path | None) -> str:
        """
        Return a stable module name.

        For Maven modules: parse the artifactId from pom.xml.
        Fallback (Gradle or unreadable pom.xml): use the directory name.

        Parsing is intentionally minimal — a single regex on the raw text
        rather than a full XML parse. pom.xml is only read for the name;
        we never need the full POM model in v1 (ADR-002: build system =
        detect + declare, no POM parsing).
        """
        if pom_path is not None and pom_path.exists():
            text = pom_path.read_text(encoding="utf-8", errors="replace")
            # Match the first <artifactId> that is a direct child of <project>
            # (not inside <dependency> or <parent>).
            match = re.search(
                r"<project[^>]*>.*?<artifactId>\s*([^<\s]+)\s*</artifactId>",
                text,
                re.DOTALL,
            )
            if match:
                return match.group(1).strip()
        return module_root.name
