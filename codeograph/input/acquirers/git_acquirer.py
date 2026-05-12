"""
GitAcquirer — corpus acquisition by cloning a remote git repository.

Clones to a temp directory; the caller is responsible for cleanup via
InputAcquirer.cleanup() after the pipeline run.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from codeograph.input.acquirers.base_acquirer import AcquisitionError, BaseAcquirer
from codeograph.input.models import AcquisitionSource, CorpusSpec
from codeograph.input.source_discoverer import SourceDiscoverer


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
        Shallow-clone input_spec into a temp directory and discover modules.

        Creates a temporary directory via tempfile.mkdtemp(), runs
        `git clone --depth 1` into it, then delegates to SourceDiscoverer.
        The returned CorpusSpec carries is_temp_dir=True so the pipeline
        orchestrator knows to call InputAcquirer.cleanup() in its finally block.

        :param input_spec: A git-clonable URL, e.g.
                           https://github.com/spring-projects/spring-petclinic.git
                           git@github.com:org/repo.git
        :raises AcquisitionError: If git is not on PATH (FileNotFoundError) or
                                   the clone fails (non-zero exit, CalledProcessError).
                                   stderr from git is included in the message.
                                   The temp directory is cleaned up before raising —
                                   no orphaned directories left on failure.
        """
        tmp_dir: Path = Path(tempfile.mkdtemp())

        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", input_spec, str(tmp_dir)],
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise AcquisitionError(f"git clone failed: {e.stderr.strip()}")
        except FileNotFoundError:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise AcquisitionError("git not found on PATH — install git and retry")

        modules = self._discoverer.discover(tmp_dir)
        return CorpusSpec(
            acquisition_source=AcquisitionSource.GIT_URL,
            corpus_root=tmp_dir,
            modules=modules,
            is_temp_dir=True,
        )
