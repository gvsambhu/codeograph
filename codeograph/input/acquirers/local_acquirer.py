"""
LocalAcquirer — corpus acquisition from a local directory path.

No copying; the directory the user points at IS the corpus root.
Discovery runs directly against it.
"""

from __future__ import annotations

from pathlib import Path

from codeograph.input.acquirers.base_acquirer import AcquisitionError, BaseAcquirer
from codeograph.input.source_discoverer import SourceDiscoverer
from codeograph.input.models import AcquisitionSource, CorpusSpec


class LocalAcquirer(BaseAcquirer):
    """
    Validate a local directory and discover its modules.

    No temp directory is created; is_temp_dir is always False.
    """

    def __init__(self, discoverer: SourceDiscoverer) -> None:
        self._discoverer = discoverer

    def acquire(self, input_spec: str) -> CorpusSpec:
        """
        Resolve and validate input_spec as a local directory path, then
        run module discovery.

        :raises AcquisitionError: If the path does not exist or is not a directory.
        """
        resolved = Path(input_spec).resolve()
        if not resolved.exists():
            raise AcquisitionError(f"Path does not exist: {resolved}")
        if not resolved.is_dir():
            raise AcquisitionError(
                f"Path is not a directory: {resolved}. "
                "Pass a directory, a .zip file, or a git URL."
            )

        modules = self._discoverer.discover(resolved)
        return CorpusSpec(
            acquisition_source=AcquisitionSource.LOCAL,
            corpus_root=resolved,
            modules=modules,
            is_temp_dir=False,
        )
