"""
ZipAcquirer — corpus acquisition by extracting a local zip archive.

Extracts to a temp directory; the caller is responsible for cleanup via
InputAcquirer.cleanup() after the pipeline run.
"""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

from codeograph.input.acquirers.base_acquirer import AcquisitionError, BaseAcquirer
from codeograph.input.models import AcquisitionSource, CorpusSpec
from codeograph.input.source_discoverer import SourceDiscoverer


class ZipAcquirer(BaseAcquirer):
    """
    Extract a zip archive to a temp directory and discover modules.

    The extraction directory itself is used as corpus_root. GitHub
    "Download ZIP" archives that produce a single inner directory
    (e.g. repo-main/) are handled correctly by SourceDiscoverer's DFS —
    it will locate modules inside that inner directory automatically.
    """

    def __init__(self, discoverer: SourceDiscoverer) -> None:
        self._discoverer = discoverer

    def acquire(self, input_spec: str) -> CorpusSpec:
        """
        Validate, extract, and discover modules from a local .zip archive.

        Resolves and validates the zip path, extracts into a temp directory,
        then delegates to SourceDiscoverer. The returned CorpusSpec carries
        is_temp_dir=True so the pipeline orchestrator knows to call
        InputAcquirer.cleanup() in its finally block.

        :param input_spec: Absolute or relative path to a .zip file.
        :raises AcquisitionError: If the path does not exist, is not a file,
                                   or is not a valid zip archive. The temp
                                   directory is cleaned up before raising.
        """
        zip_path = Path(input_spec).resolve()
        if not zip_path.exists():
            raise AcquisitionError(f"Path does not exist: {input_spec}")
        if not zip_path.is_file():
            raise AcquisitionError(f"Not a file: {input_spec}")

        tmp_dir: Path = Path(tempfile.mkdtemp())

        try:
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(tmp_dir)
        except zipfile.BadZipFile:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise AcquisitionError(f"Invalid or corrupt zip file: {zip_path}")

        modules = self._discoverer.discover(tmp_dir)
        return CorpusSpec(
            acquisition_source=AcquisitionSource.ZIP,
            corpus_root=tmp_dir,
            modules=modules,
            is_temp_dir=True,
        )
