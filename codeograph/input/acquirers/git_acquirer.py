"""
GitAcquirer — corpus acquisition by cloning a remote git repository.

Clones to a temp directory; the caller is responsible for cleanup via
InputAcquirer.cleanup() after the pipeline run.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from codeograph.input.acquirers.base_acquirer import BaseAcquirer
from codeograph.input.source_discoverer import SourceDiscoverer
from codeograph.input.models import AcquisitionSource, CorpusSpec


class AcquisitionError(Exception):
    """Raised when git clone fails or git is not on PATH."""


class GitAcquirer(BaseAcquirer):
    """
    Clone a remote git repository to a temp directory and discover modules.

    Uses a shallow clone (--depth 1) — only the latest snapshot is needed;
    full history would waste time and disk for large repos.
    """

    def __init__(self, discoverer: SourceDiscoverer) -> None:
        self._discoverer = discoverer

    def acquire(self, input_spec: str) -> CorpusSpec:
        """
        Clone input_spec (a git URL) to a temp directory and discover modules.

        :param input_spec: A git-clonable URL.
                           e.g. https://github.com/spring-projects/spring-petclinic.git
                                git@github.com:org/repo.git
        :raises AcquisitionError: If git is not on PATH or clone fails.

        Implementation notes:
          - Create a temp dir: tmp_dir = Path(tempfile.mkdtemp())
          - Run: subprocess.run(
                ["git", "clone", "--depth", "1", input_spec, str(tmp_dir)],
                check=True,
            )
          - Wrap subprocess.CalledProcessError and FileNotFoundError in
            AcquisitionError with a human-readable message.
          - Call self._discoverer.discover(tmp_dir) for modules.
          - Return CorpusSpec with is_temp_dir=True so the orchestrator
            knows to call InputAcquirer.cleanup() after the run.

        Python APIs:
          subprocess.run, subprocess.CalledProcessError, tempfile.mkdtemp
        """
        # TODO (learner): implement git clone → temp dir → discover
        raise NotImplementedError("GitAcquirer.acquire not yet implemented")
