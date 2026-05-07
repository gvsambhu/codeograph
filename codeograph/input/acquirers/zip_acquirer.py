"""
ZipAcquirer — corpus acquisition by extracting a local zip archive.

Extracts to a temp directory; the caller is responsible for cleanup via
InputAcquirer.cleanup() after the pipeline run.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from codeograph.input.acquirers.base_acquirer import BaseAcquirer
from codeograph.input.source_discoverer import SourceDiscoverer
from codeograph.input.models import AcquisitionSource, CorpusSpec


class AcquisitionError(Exception):
    """Raised when the zip file is invalid or extraction fails."""


class ZipAcquirer(BaseAcquirer):
    """
    Extract a zip archive to a temp directory and discover modules.

    Handles the common case where the zip contains a single top-level
    directory (e.g. GitHub "Download ZIP" archives produce
    repo-main/ inside the zip). In that case the inner directory is
    used as corpus_root, not the bare extraction directory.
    """

    def __init__(self, discoverer: SourceDiscoverer) -> None:
        self._discoverer = discoverer

    def acquire(self, input_spec: str) -> CorpusSpec:
        """
        Extract input_spec (a local .zip path) to a temp directory and
        discover modules.

        :param input_spec: Absolute or relative path to a .zip file.
        :raises AcquisitionError: If the path does not exist, is not a file,
                                   or is not a valid zip archive.

        Implementation notes:
          - Validate: zip_path = Path(input_spec); check .exists() and .is_file()
          - Create temp dir: tmp_dir = Path(tempfile.mkdtemp())
          - Extract: with zipfile.ZipFile(zip_path) as zf: zf.extractall(tmp_dir)
          - Wrap zipfile.BadZipFile in AcquisitionError.
          - Single-top-level-dir pattern: list tmp_dir.iterdir(); if exactly one
            entry exists and it is a directory, use that entry as corpus_root.
            Otherwise use tmp_dir directly.
          - Call self._discoverer.discover(corpus_root) for modules.
          - Return CorpusSpec with is_temp_dir=True.

        Python APIs:
          zipfile.ZipFile, zipfile.BadZipFile, tempfile.mkdtemp,
          Path.iterdir(), Path.is_dir()
        """
        # TODO (learner): implement zip extract → temp dir → discover
        raise NotImplementedError("ZipAcquirer.acquire not yet implemented")
