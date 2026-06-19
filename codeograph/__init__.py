"""Codeograph package.

The version is authored once in ``pyproject.toml`` (ADR-026 Fork 4, option a)
and read at runtime from installed package metadata — there is no
hand-maintained version literal in package source. ``__version__`` is kept for
the conventional ``from codeograph import __version__`` import, but it resolves
*from* ``importlib.metadata`` rather than being an independent source.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("codeograph")
except PackageNotFoundError:  # pragma: no cover - running from a source tree without an install
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
