"""
InputAcquirer — detects input type and dispatches to the right acquirer.

This is the only class callers outside the input module need to import.
It owns the type-detection heuristic and the cleanup helper; all
acquisition logic lives in the concrete acquirers.
"""

from __future__ import annotations

import shutil

from codeograph.input.acquirers.base_acquirer import BaseAcquirer
from codeograph.input.acquirers.git_acquirer import GitAcquirer
from codeograph.input.acquirers.local_acquirer import LocalAcquirer
from codeograph.input.acquirers.zip_acquirer import ZipAcquirer
from codeograph.input.models import AcquisitionSource, CorpusSpec
from codeograph.input.source_discoverer import SourceDiscoverer


def _detect_input_type(input_spec: str) -> AcquisitionSource:
    """
    Classify the raw CLI argument as local path, git URL, or zip file.

    Heuristic order (ADR-002):
      1. Ends with .zip                              → ZIP
      2. Starts with http(s)://, git@, or git://    → GIT_URL
      3. Everything else                             → LOCAL
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


class InputAcquirer:
    """
    Public entry point for corpus acquisition.

    Detects the input type from the CLI argument, selects the matching
    concrete acquirer, and delegates. Callers see only acquire() and cleanup().

    Usage::

        acquirer = InputAcquirer()
        corpus = acquirer.acquire("/path/to/project")
        try:
            run_pipeline(corpus)
        finally:
            acquirer.cleanup(corpus)
    """

    def __init__(self) -> None:
        discoverer = SourceDiscoverer()
        self._acquirers: dict[AcquisitionSource, BaseAcquirer] = {
            AcquisitionSource.LOCAL: LocalAcquirer(discoverer),
            AcquisitionSource.GIT_URL: GitAcquirer(discoverer),
            AcquisitionSource.ZIP: ZipAcquirer(discoverer),
        }

    def acquire(self, input_spec: str) -> CorpusSpec:
        """
        Detect input type, dispatch to the correct acquirer, and return a
        fully-discovered CorpusSpec.

        :param input_spec: Raw argument from `codeograph run <INPUT>`.
        :raises AcquisitionError: Propagated from the concrete acquirer.
            Import from codeograph.input.acquirers.base_acquirer to catch it.
        """
        source_type = _detect_input_type(input_spec)
        return self._acquirers[source_type].acquire(input_spec)

    @staticmethod
    def cleanup(corpus: CorpusSpec) -> None:
        """
        Remove the temp directory for git- or zip-acquired corpora.

        Safe to call on LOCAL corpora (is_temp_dir=False) — no-ops silently.
        Call in a finally block in the pipeline orchestrator.
        """
        if corpus.is_temp_dir and corpus.corpus_root.exists():
            shutil.rmtree(corpus.corpus_root, ignore_errors=True)
