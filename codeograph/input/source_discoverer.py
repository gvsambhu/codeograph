"""
SourceDiscoverer — walk a corpus root and enumerate all Java modules.

Responsibilities (ADR-002):
  - Find every Maven / Gradle module within the corpus
  - Detect the build tool for each module
  - Locate Java source roots inside each module
  - Build a pathspec file filter from .gitignore files (chain: repo root →
    module root) plus a hardcoded fallback set
  - Return a list[ModuleSpec] ordered by discovery (depth-first)

This class only reads the filesystem; it does not parse Java source files.
"""

from __future__ import annotations

from pathlib import Path

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
        Entry point. Walk corpus_root, find modules, return their specs.

        :param corpus_root: Absolute path to the top of the corpus on disk.
        :returns: List of ModuleSpec, one per detected module, depth-first.
        """
        module_roots = self._find_module_roots(corpus_root)
        specs: list[ModuleSpec] = []
        for root in module_roots:
            build_tool = self._detect_build_tool(root)
            source_roots = self._find_source_roots(root)
            pom_path = (root / "pom.xml") if build_tool == BuildTool.MAVEN else None
            name = self._module_name(root, pom_path)
            specs.append(
                ModuleSpec(
                    module_id=f"mod:{name}",
                    name=name,
                    root_path=root,
                    build_tool=build_tool,
                    source_roots=source_roots,
                    pom_path=pom_path,
                )
            )
        return specs

    # ------------------------------------------------------------------
    # Module root discovery  — YOU WRITE THIS
    # ------------------------------------------------------------------

    def _find_module_roots(self, corpus_root: Path) -> list[Path]:
        """
        Recursively walk corpus_root and return the root directory of every
        Maven / Gradle module found.

        A module root is any directory that contains a pom.xml OR a
        build.gradle / build.gradle.kts file.

        Implementation notes:
          - Use Path.rglob("pom.xml") and Path.rglob("build.gradle") to find
            all candidate files, then take their parent directories.
          - De-duplicate: a directory may have both pom.xml and build.gradle
            (rare but possible). Use a set of Path objects, then sort for
            stable ordering.
          - Exclude paths that live inside another module's build output.
            Simplest approach: after collecting all candidate roots, drop any
            root whose path contains "target/" or "build/" as a path component.
          - Return the de-duplicated list sorted by path (depth-first order
            falls out naturally from lexicographic sort on absolute paths).

        Example: given this tree —
          my-app/
            pom.xml               → module root
            module-api/pom.xml    → module root
            module-core/pom.xml   → module root
        Returns: [my-app/, my-app/module-api/, my-app/module-core/]

        Python APIs you will use:
          - Path.rglob(pattern)  — yields Path objects matching the glob
          - path.parent  — the directory containing a file
          - set / sorted  — de-duplication and stable ordering
          - path.parts   — tuple of path components, useful for the
                           "target/" / "build/" exclusion check
        """
        # TODO (learner): implement recursive module root discovery
        raise NotImplementedError("_find_module_roots not yet implemented")

    # ------------------------------------------------------------------
    # Build tool detection  (AI-generated — trivial, no TODO)
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
    # Source root detection  — YOU WRITE THIS
    # ------------------------------------------------------------------

    def _find_source_roots(self, module_root: Path) -> list[Path]:
        """
        Return all existing Java source root directories inside module_root.

        Check each path in _CANDIDATE_SOURCE_ROOTS; include those that exist
        and are directories. Return absolute Path objects.

        Example: for a standard Maven module —
          module_root/src/main/java  → exists → include
          module_root/src/test/java  → exists → include
          module_root/src/main/kotlin → does not exist → skip

        Implementation notes:
          - Iterate _CANDIDATE_SOURCE_ROOTS, resolve each with
            (module_root / candidate).
          - Include only if candidate.is_dir().
          - Return the list in the same order as _CANDIDATE_SOURCE_ROOTS
            (deterministic).

        Python APIs you will use:
          - Path.__truediv__ (the / operator)
          - Path.is_dir()
        """
        # TODO (learner): implement source root detection
        raise NotImplementedError("_find_source_roots not yet implemented")

    # ------------------------------------------------------------------
    # .gitignore-based file filter  — YOU WRITE THIS
    # ------------------------------------------------------------------

    def build_file_filter(self, corpus_root: Path, module_root: Path) -> pathspec.PathSpec:
        """
        Build a pathspec filter by chaining .gitignore files and the fallback
        pattern set.

        Chain (merged into one PathSpec — any match = ignored):
          1. Hardcoded _FALLBACK_IGNORE_PATTERNS (always present)
          2. corpus_root/.gitignore  (if it exists)
          3. module_root/.gitignore  (if it exists and differs from corpus_root)

        The returned PathSpec is used to test relative paths:
          filter.match_file("target/classes/Foo.class")  → True  (ignored)
          filter.match_file("src/main/java/Foo.java")    → False (include)

        Implementation notes:
          - Read .gitignore files with Path.read_text(encoding="utf-8").
            splitlines() gives you the individual patterns.
          - Merge all pattern lines into a single list, then build one
            PathSpec from the combined list. Do NOT build multiple PathSpec
            objects and AND them — merge the line lists instead.
          - pathspec.PathSpec.from_lines("gitwildmatch", all_lines) constructs
            the filter.

        Python APIs you will use:
          - Path.exists(), Path.read_text()
          - str.splitlines()
          - pathspec.PathSpec.from_lines("gitwildmatch", lines)
        """
        # TODO (learner): implement .gitignore chain → pathspec filter
        raise NotImplementedError("build_file_filter not yet implemented")

    # ------------------------------------------------------------------
    # Java file listing  — YOU WRITE THIS
    # ------------------------------------------------------------------

    def list_java_files(
        self, source_root: Path, corpus_root: Path, file_filter: pathspec.PathSpec
    ) -> list[Path]:
        """
        Return all .java files under source_root that pass the file_filter.

        The filter operates on paths relative to corpus_root (that is the
        convention pathspec expects when the patterns came from a repo-root
        .gitignore).

        Implementation notes:
          - Use source_root.rglob("*.java") to get all .java files.
          - For each file, compute its path relative to corpus_root:
              relative = file.relative_to(corpus_root)
          - Call file_filter.match_file(str(relative)) — if True, skip it.
          - Return the list of absolute Path objects for files that pass.
          - Sort the result for stable ordering (required by ADR-006
            canonical-form sha256 contract).

        Python APIs you will use:
          - Path.rglob("*.java")
          - Path.relative_to(base)
          - pathspec.PathSpec.match_file(path_str)
          - sorted(...)
        """
        # TODO (learner): implement filtered Java file walk
        raise NotImplementedError("list_java_files not yet implemented")

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
            import re
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
