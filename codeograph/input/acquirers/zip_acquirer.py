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

    def __init__(self, discoverer: SourceDiscoverer, max_archive_extracted_bytes: int = 1_073_741_824) -> None:
        self._discoverer = discoverer
        self._max_archive_extracted_bytes = max_archive_extracted_bytes

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
                extraction_root = tmp_dir.resolve()
                extracted_bytes = 0
                for entry in zf.infolist():
                    target = (extraction_root / entry.filename).resolve()
                    if not target.is_relative_to(extraction_root):
                        raise AcquisitionError(f"Archive entry resolves outside the extraction root: {entry.filename}")
                    if entry.is_dir():
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(entry) as source, target.open("wb") as destination:
                        while chunk := source.read(1024 * 1024):
                            if extracted_bytes + len(chunk) > self._max_archive_extracted_bytes:
                                raise AcquisitionError(
                                    "Archive extraction exceeds the configured cap of "
                                    f"{self._max_archive_extracted_bytes} bytes"
                                )
                            extracted_bytes += destination.write(chunk)
            modules = self._discoverer.discover(tmp_dir)
        except AcquisitionError:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise
        except zipfile.BadZipFile as exc:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise AcquisitionError(f"Invalid or corrupt zip file: {zip_path}") from exc
        except Exception as exc:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise AcquisitionError(f"Zip acquisition failed for {zip_path}: {exc}") from exc

        return CorpusSpec(
            acquisition_source=AcquisitionSource.ZIP,
            corpus_root=tmp_dir,
            modules=modules,
            is_temp_dir=True,
        )
