"""Unit tests for ``generate_run_id()`` (ADR-022 Fork 3 Confirmation 4 + 5).

Scaffolding is AI-generated; the assertion bodies are learner-write per
the DC5 M12 spec. Note: run_id generation is governed by ADR-022
Fork 3, not ADR-025 directly; the tests live in this package because
the assembler (which is ADR-025 territory) consumes run_id.

Per ADR-022 §"Confirmation":
* 4 — ``generate_run_id()`` produces a string matching
      ``^\\d{4}-\\d{2}-\\d{2}T\\d{2}-\\d{2}-\\d{2}Z-[0-9a-f]{6}$``.
* 5 — Two calls to ``generate_run_id()`` in rapid succession produce
      different strings (collision check; 1000-call uniqueness).
"""

from __future__ import annotations

# Imports used by the learner-written assertion bodies; suppress
# unused-import warnings until the bodies are filled in.
import re  # noqa: F401

import pytest  # noqa: F401

from codeograph.manifest.run_id import RUN_ID_PATTERN, generate_run_id  # noqa: F401

# ---------------------------------------------------------------------------
# TestFormat (ADR-022 Confirmation #4)
# ---------------------------------------------------------------------------


class TestFormat:
    """The run_id is chronologically sortable + collision-resistant."""

    def test_pattern_compiles(self) -> None:
        compiled = re.compile(RUN_ID_PATTERN)
        assert isinstance(compiled, re.Pattern)

    def test_generated_run_id_matches_pattern(self) -> None:
        run_id = generate_run_id()
        assert re.fullmatch(RUN_ID_PATTERN, run_id) is not None

    def test_run_id_is_27_chars(self) -> None:
        run_id = generate_run_id()
        assert len(run_id) == 27

    def test_run_id_timestamp_prefix_is_sortable(self) -> None:
        from datetime import UTC
        import datetime as dt
        from unittest.mock import patch

        with patch("codeograph.manifest.run_id.datetime") as mock_datetime:
            mock_datetime.now.return_value = dt.datetime(2026, 6, 22, 18, 0, 0, tzinfo=UTC)
            id1 = generate_run_id()

            mock_datetime.now.return_value = dt.datetime(2026, 6, 22, 18, 0, 1, tzinfo=UTC)
            id2 = generate_run_id()

            assert id1 < id2


# ---------------------------------------------------------------------------
# TestUniqueness (ADR-022 Confirmation #5)
# ---------------------------------------------------------------------------


class TestUniqueness:
    """Two calls produce different values; 1000-call uniqueness."""

    def test_two_calls_differ(self) -> None:
        # TODO(learner): assert generate_run_id() != generate_run_id().
        ...

    def test_thousand_calls_are_unique(self) -> None:
        # TODO(learner): call generate_run_id() 1000 times in a tight
        # loop; assert len(set(ids)) == 1000 (all distinct).
        ...
