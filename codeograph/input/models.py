"""
Input acquisition data models.

These dataclasses represent the *acquired* corpus — what was fetched, where it
lives on disk, and what modules were discovered inside it.  They are the
contract between M4 (input) and M6 (parser).

Note: BuildTool is duplicated here (also in codeograph/graph/models/ as a
generated schema enum).  The input layer must not import from generated models
— those are graph *output* types.  The duplication is intentional and small.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class AcquisitionSource(StrEnum):
    """How the corpus was obtained."""

    LOCAL = "local"
    GIT_URL = "git_url"
    ZIP = "zip"


class BuildTool(StrEnum):
    """Build system detected for a module (ADR-002)."""

    MAVEN = "maven"
    GRADLE = "gradle"


@dataclass(frozen=True)
class ModuleSpec:
    """
    A single Maven/Gradle module within the corpus.

    Produced by SourceDiscoverer and consumed by the Parser. All paths are
    absolute (discovery resolves them); the graph writer converts them to
    repo-root-relative strings before serialisation (DECISION-2).
    """

    #: Stable module identifier written into graph nodes.  Format: mod:<name>
    #: where <name> is the Maven artifactId (or directory name as fallback).
    module_id: str

    #: Human-readable name (Maven artifactId or directory name).
    name: str

    #: Absolute path to the module root directory (contains pom.xml / build.gradle).
    root_path: Path

    #: Detected build tool for this module.
    build_tool: BuildTool

    #: Absolute paths to Java source roots inside this module.
    #: Typically [root_path/src/main/java] but may include additional roots.
    source_roots: list[Path] = field(default_factory=list)

    #: Absolute path to pom.xml, or None for Gradle modules (v1 limitation per ADR-002).
    pom_path: Path | None = None

    #: Absolute paths to .java files that passed the gitignore filter, across
    #: all source roots in this module. Populated by SourceDiscoverer.discover();
    #: the parser iterates this list directly without any further filesystem walking.
    java_files: list[Path] = field(default_factory=list)


@dataclass(frozen=True)
class CorpusSpec:
    """
    The fully-acquired, fully-discovered corpus ready for parsing.

    Produced by InputAcquisition.acquire() and consumed by the pipeline
    orchestrator (cli/main.py run command).
    """

    #: How this corpus was obtained.
    acquisition_source: AcquisitionSource

    #: Absolute path to the root of the corpus on disk.
    #: For LOCAL: the path the user passed.
    #: For GIT_URL / ZIP: the temp directory where content was extracted.
    corpus_root: Path

    #: All discovered modules, in discovery order (depth-first).
    modules: list[ModuleSpec] = field(default_factory=list)

    #: True if corpus_root is a temp directory that should be cleaned up
    #: after the pipeline run.  False for LOCAL acquisitions.
    is_temp_dir: bool = False
