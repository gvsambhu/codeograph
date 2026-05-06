"""
InputAcquisition — fetch the corpus from local path, git URL, or zip file.

Responsibilities (ADR-002):
  - Detect input type from the raw string the user passed to `codeograph run`
  - Clone / extract to a temp directory when needed
  - Delegate module discovery to SourceDiscovery
  - Return a fully-populated CorpusSpec

This class does NOT do module discovery itself; it calls SourceDiscovery after
the corpus is on disk.  That keeps each class focused on one job.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from codeograph.input.discovery import SourceDiscovery
from codeograph.input.models import AcquisitionSource, CorpusSpec


class InputAcquisitionError(Exception):
    """Raised when the corpus cannot be acquired."""


class InputAcquisition:
    """
    Acquire a Java corpus from any of the three supported input types.

    Usage::

        corpus = InputAcquisition().acquire("/path/to/project")
        corpus = InputAcquisition().acquire("https://github.com/org/repo.git")
        corpus = InputAcquisition().acquire("/downloads/project.zip")
    """

    def __init__(self) -> None:
        self._discovery = SourceDiscovery()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def acquire(self, input_spec: str) -> CorpusSpec:
        """
        Main entry point.  Detects input type, fetches/extracts the corpus,
        runs module discovery, and returns a CorpusSpec.

        :param input_spec: Raw CLI argument — local path, git URL, or zip path.
        :raises InputAcquisitionError: If the input cannot be found or fetched.
        """
        source_type = self._detect_input_type(input_spec)

        if source_type == AcquisitionSource.LOCAL:
            return self._acquire_local(Path(input_spec))
        elif source_type == AcquisitionSource.GIT_URL:
            return self._acquire_git(input_spec)
        else:
            return self._acquire_zip(Path(input_spec))

    # ------------------------------------------------------------------
    # Input type detection  (AI-generated — pure heuristic, no TODO)
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_input_type(input_spec: str) -> AcquisitionSource:
        """
        Classify the input string as local path, git URL, or zip file.

        Heuristic order (ADR-002):
          1. Ends with .zip → ZIP
          2. Starts with http:// / https:// / git@ / git:// → GIT_URL
          3. Everything else → LOCAL (validation happens in _acquire_local)
        """
        lowered = input_spec.lower()
        if lowered.endswith(".zip"):
            return AcquisitionSource.ZIP
        if (
            lowered.startswith("http://")
            or lowered.startswith("https://")
            or lowered.startswith("git@")
            or lowered.startswith("git://")
        ):
            return AcquisitionSource.GIT_URL
        return AcquisitionSource.LOCAL

    # ------------------------------------------------------------------
    # LOCAL acquisition  (AI-generated — trivial validation, no TODO)
    # ------------------------------------------------------------------

    def _acquire_local(self, path: Path) -> CorpusSpec:
        """
        Validate the local path and run module discovery.

        No copying — the corpus_root IS the path the user provided.
        """
        resolved = path.resolve()
        if not resolved.exists():
            raise InputAcquisitionError(f"Path does not exist: {resolved}")
        if not resolved.is_dir():
            raise InputAcquisitionError(
                f"Path is not a directory: {resolved}. "
                "Pass a directory, a .zip file, or a git URL."
            )

        modules = self._discovery.discover(resolved)
        return CorpusSpec(
            acquisition_source=AcquisitionSource.LOCAL,
            corpus_root=resolved,
            modules=modules,
            is_temp_dir=False,
        )

    # ------------------------------------------------------------------
    # GIT acquisition  — YOU WRITE THIS
    # ------------------------------------------------------------------

    def _acquire_git(self, url: str) -> CorpusSpec:
        """
        Clone a git repository to a temporary directory and discover modules.

        Implementation notes:
          - Use subprocess to call `git clone <url> <tmp_dir>`.
            subprocess.run(["git", "clone", url, str(tmp_dir)], check=True)
          - Create the temp dir with tempfile.mkdtemp(); set is_temp_dir=True
            so the pipeline orchestrator knows to clean it up.
          - A shallow clone (--depth 1) is faster and sufficient — we only
            need the source files, not full history.
          - Raise InputAcquisitionError (wrapping CalledProcessError) if git
            is not on PATH or the clone fails.
          - After clone, call self._discovery.discover(tmp_path) for modules.

        Python APIs you will use:
          - subprocess.run  (stdlib)
          - tempfile.mkdtemp  (stdlib) — returns a str; wrap in Path()
          - subprocess.CalledProcessError  (the exception check=True raises)
        """
        # TODO (learner): implement git clone → temp dir → discover
        raise NotImplementedError("_acquire_git not yet implemented")

    # ------------------------------------------------------------------
    # ZIP acquisition  — YOU WRITE THIS
    # ------------------------------------------------------------------

    def _acquire_zip(self, zip_path: Path) -> CorpusSpec:
        """
        Extract a zip archive to a temporary directory and discover modules.

        Implementation notes:
          - Validate that zip_path exists and is a file first.
          - Use zipfile.ZipFile (stdlib) to extract all members to a temp dir.
          - Create the temp dir with tempfile.mkdtemp(); set is_temp_dir=True.
          - After extraction, the zip may contain a single top-level directory
            (common for GitHub "Download ZIP" archives).  If so, use that
            inner directory as corpus_root rather than the bare temp dir —
            it makes module discovery cleaner.
          - Call self._discovery.discover(corpus_root) for modules.

        Python APIs you will use:
          - zipfile.ZipFile  (stdlib)
          - zipfile.ZipFile.extractall(path)
          - tempfile.mkdtemp  (stdlib)
          - Path.iterdir()  — to check for the single-top-level-dir pattern
        """
        # TODO (learner): implement zip extract → temp dir → discover
        raise NotImplementedError("_acquire_zip not yet implemented")

    # ------------------------------------------------------------------
    # Cleanup helper  (AI-generated)
    # ------------------------------------------------------------------

    @staticmethod
    def cleanup(corpus: CorpusSpec) -> None:
        """
        Remove the temp directory for a corpus acquired via git or zip.

        Call this in a finally block in the pipeline orchestrator after the
        run is complete (success or failure).  Safe to call on LOCAL corpora
        (is_temp_dir=False) — it will no-op.
        """
        if corpus.is_temp_dir and corpus.corpus_root.exists():
            shutil.rmtree(corpus.corpus_root, ignore_errors=True)
