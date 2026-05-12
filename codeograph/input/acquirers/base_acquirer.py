"""
BaseAcquirer — abstract contract for all corpus acquisition strategies.

Each concrete acquirer handles one input type (local path, git URL, zip).
All share the same acquire() signature so the coordinator (InputAcquirer)
can dispatch without branching on type after the initial detection.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from codeograph.input.models import CorpusSpec


class AcquisitionError(Exception):
    """
    Raised when a corpus cannot be acquired.

    Defined here so callers can catch it from a single import regardless
    of which concrete acquirer (Local, Git, Zip) raises it::

        from codeograph.input.acquirers.base_acquirer import AcquisitionError
        try:
            corpus = acquirer.acquire(input_spec)
        except AcquisitionError as e:
            ...
    """


class BaseAcquirer(ABC):
    """
    Abstract base for the three acquisition strategies.

    Concrete subclasses: LocalAcquirer, GitAcquirer, ZipAcquirer.
    Instantiated by InputAcquirer; not used directly by callers.
    """

    @abstractmethod
    def acquire(self, input_spec: str) -> CorpusSpec:
        """
        Fetch the corpus identified by input_spec, run module discovery,
        and return a populated CorpusSpec.

        :param input_spec: The raw string the user passed to `codeograph run`.
                           Each subclass interprets it according to its type
                           (path, URL, or zip path).
        :raises AcquisitionError: If the corpus cannot be fetched or discovered.
        """
