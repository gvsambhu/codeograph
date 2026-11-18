"""Unit tests for the roadmap-to-status-table consistency check."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_roadmap_scopes.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_roadmap_scopes", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their annotations through sys.modules
    spec.loader.exec_module(module)
    return module


mod = _load()

REQUIREMENTS = """\
## 7. Status

| ID | Status | Scope | Note |
|---|---|---|---|
| FR-1 | shipped | SC-001 | |
| FR-2 | partial | SC-001 | **AC-2 not met** — a gap |
| FR-3 | planned | SC-002 | |
| FR-4 | partial | SC-002 (AC-3: SC-003) | **AC-3 not met** — a gap |
| FR-5 | planned | SC-003 | |
| FR-6 | retired | — | Retired |
| NFR-1 | shipped | SC-004 | |

---

## 8. Revision history
"""

ROADMAP_TEXT = """\
## Scopes

| Scope | Outcome | Requirements | State | Shipped in |
|---|---|---|---|---|
| **SC-001: First** | Outcome | FR-1, FR-2 | In progress | — |
| **SC-002: Second** | Outcome | FR-3, FR-4 (except AC-3, in SC-003) | In progress — design: ADR-1 | — |
| **SC-003: Third** | Outcome | FR-5, FR-4 AC-3 | Planned | — |
| **SC-004: Fourth** | Outcome | NFR-1 | Done | — |

### How a scope's state is read
"""


def run(requirements: str = REQUIREMENTS, roadmap: str = ROADMAP_TEXT) -> list[str]:
    problems: list[str] = mod.check(requirements, roadmap)
    return problems


def swap(text: str, old: str, new: str) -> str:
    assert old in text, f"fixture does not contain {old!r}"
    return text.replace(old, new, 1)


class TestAgreement:
    def test_agreeing_documents_report_nothing(self) -> None:
        assert run() == []

    def test_design_note_beside_state_is_not_compared(self) -> None:
        roadmap = swap(ROADMAP_TEXT, "In progress — design: ADR-1", "In progress — design: something else")
        assert run(roadmap=roadmap) == []


class TestOwnership:
    def test_requirement_listed_in_wrong_scope_names_both_scopes_and_the_requirement(self) -> None:
        roadmap = swap(ROADMAP_TEXT, "FR-1, FR-2 |", "FR-2 |")
        roadmap = swap(roadmap, "| NFR-1 |", "| NFR-1, FR-1 |")
        problems = run(roadmap=roadmap)
        assert "ROADMAP.md SC-004 lists FR-1, but the status table gives FR-1 to SC-001." in problems

    def test_requirement_missing_from_roadmap_is_named(self) -> None:
        roadmap = swap(ROADMAP_TEXT, "FR-1, FR-2", "FR-2")
        problems = run(roadmap=roadmap)
        assert "ROADMAP.md lists FR-1 in no scope, but the status table gives it to SC-001." in problems

    def test_requirement_listed_twice_names_every_row(self) -> None:
        roadmap = swap(ROADMAP_TEXT, "| NFR-1 |", "| NFR-1, FR-1 |")
        problems = run(roadmap=roadmap)
        assert any("FR-1 in SC-001, SC-004" in p and "SC-001 alone" in p for p in problems)

    def test_unknown_requirement_is_named(self) -> None:
        roadmap = swap(ROADMAP_TEXT, "FR-1, FR-2", "FR-1, FR-2, FR-99")
        problems = run(roadmap=roadmap)
        assert "ROADMAP.md SC-001 lists FR-99, but the status table has no such requirement." in problems

    def test_retired_requirement_listed_is_named(self) -> None:
        roadmap = swap(ROADMAP_TEXT, "FR-1, FR-2", "FR-1, FR-2, FR-6")
        problems = run(roadmap=roadmap)
        assert "ROADMAP.md SC-001 lists FR-6, but the status table retires it; remove it from the row." in problems

    def test_requirement_owned_by_scope_without_a_row_is_named(self) -> None:
        requirements = swap(REQUIREMENTS, "| NFR-1 | shipped | SC-004 |", "| NFR-1 | shipped | SC-009 |")
        problems = run(requirements=requirements)
        assert "docs/requirements.md gives NFR-1 to SC-009, which ROADMAP.md has no row for." in problems


class TestCriterionExceptions:
    def test_missing_exception_note_on_owning_row_is_named(self) -> None:
        roadmap = swap(ROADMAP_TEXT, "FR-4 (except AC-3, in SC-003)", "FR-4")
        problems = run(roadmap=roadmap)
        assert any(p.startswith("ROADMAP.md SC-002 should list 'FR-4 (except AC-3, in SC-003)'") for p in problems)

    def test_missing_criteria_on_other_row_is_named(self) -> None:
        roadmap = swap(ROADMAP_TEXT, "FR-5, FR-4 AC-3", "FR-5")
        problems = run(roadmap=roadmap)
        assert any(p.startswith("ROADMAP.md SC-003 should list 'FR-4 AC-3'") for p in problems)

    def test_different_criteria_on_each_side_are_named(self) -> None:
        roadmap = swap(ROADMAP_TEXT, "FR-4 (except AC-3, in SC-003)", "FR-4 (except AC-2, in SC-003)")
        problems = run(roadmap=roadmap)
        assert len(problems) == 1
        assert problems[0].startswith("ROADMAP.md SC-002 should list 'FR-4 (except AC-3, in SC-003)'")

    def test_exception_the_status_table_does_not_make_is_named(self) -> None:
        requirements = swap(REQUIREMENTS, "SC-002 (AC-3: SC-003)", "SC-002")
        problems = run(requirements=requirements)
        assert any(
            "SC-002 lists 'FR-4 (except AC-3, in SC-003)'" in p and "does not give any criterion" in p for p in problems
        )
        assert any("SC-003 lists 'FR-4 AC-3'" in p and "does not give criteria" in p for p in problems)

    def test_criteria_range_and_list_forms_match(self) -> None:
        requirements = swap(REQUIREMENTS, "SC-002 (AC-3: SC-003)", "SC-002 (AC-3 to AC-5: SC-003)")
        requirements = swap(requirements, "**AC-3 not met**", "**AC-3, AC-4 and AC-5 not met**")
        roadmap = swap(ROADMAP_TEXT, "FR-4 (except AC-3, in SC-003)", "FR-4 (except AC-3 to AC-5, in SC-003)")
        roadmap = swap(roadmap, "FR-4 AC-3", "FR-4 AC-3, AC-4, AC-5")
        assert run(requirements, roadmap) == []


class TestStates:
    def test_done_claimed_while_a_requirement_is_partial(self) -> None:
        roadmap = swap(ROADMAP_TEXT, "FR-1, FR-2 | In progress", "FR-1, FR-2 | Done")
        problems = run(roadmap=roadmap)
        assert len(problems) == 1
        assert problems[0].startswith("ROADMAP.md SC-001 is marked Done, but the status table puts it at In progress")
        assert "FR-2's note names AC-2 as not met" in problems[0]

    def test_planned_claimed_while_a_requirement_is_shipped(self) -> None:
        roadmap = swap(ROADMAP_TEXT, "NFR-1 | Done", "NFR-1 | Planned")
        problems = run(roadmap=roadmap)
        assert len(problems) == 1
        assert "SC-004 is marked Planned, but the status table puts it at Done" in problems[0]

    def test_in_progress_claimed_where_everything_is_planned(self) -> None:
        roadmap = swap(ROADMAP_TEXT, "FR-5, FR-4 AC-3 | Planned", "FR-5, FR-4 AC-3 | In progress")
        problems = run(roadmap=roadmap)
        assert len(problems) == 1
        assert "SC-003 is marked In progress, but the status table puts it at Planned" in problems[0]

    def test_shipped_requirement_with_reverify_note_is_not_done(self) -> None:
        requirements = swap(
            REQUIREMENTS, "| NFR-1 | shipped | SC-004 | |", "| NFR-1 | shipped | SC-004 | **Re-verify.** x |"
        )
        problems = run(requirements=requirements)
        assert len(problems) == 1
        assert "SC-004 is marked Done" in problems[0]
        assert "NFR-1 carries a Re-verify note" in problems[0]

    def test_shipped_requirement_naming_an_unmet_criterion_is_not_done(self) -> None:
        requirements = swap(
            REQUIREMENTS, "| NFR-1 | shipped | SC-004 | |", "| NFR-1 | shipped | SC-004 | **AC-2 not met** |"
        )
        problems = run(requirements=requirements)
        assert len(problems) == 1
        assert "NFR-1's note names AC-2 as not met" in problems[0]

    def test_criterion_owned_elsewhere_that_holds_makes_its_scope_in_progress(self) -> None:
        # FR-4 AC-3 now holds, so SC-003 (which owns FR-5, planned, and FR-4 AC-3) is no longer all-planned.
        requirements = swap(
            REQUIREMENTS,
            "| FR-4 | partial | SC-002 (AC-3: SC-003) | **AC-3 not met** — a gap |",
            "| FR-4 | partial | SC-002 (AC-3: SC-003) | AC-3 holds |",
        )
        problems = run(requirements=requirements)
        assert len(problems) == 1
        assert "SC-003 is marked Planned, but the status table puts it at In progress" in problems[0]

    def test_unmet_clause_is_read_per_criterion(self) -> None:
        # "AC-2 partially met" is a different clause from the not-met one and is not counted as unmet.
        assert mod.read_unmet("**AC-1 and AC-3 not met; AC-2 partially met**") == (frozenset({1, 3}), False)
        assert mod.read_unmet("**AC-5, AC-6 and AC-7 not met**") == (frozenset({5, 6, 7}), False)
        assert mod.read_unmet("AC-4 not met, said without bold") == (frozenset(), False)

    def test_unmet_clause_is_read_case_insensitively(self) -> None:
        assert mod.read_unmet("**AC-4 Not met**") == (frozenset({4}), False)
        assert mod.read_unmet("**AC-1 Unmet**") == (frozenset({1}), False)

    def test_unmet_clause_without_a_criterion_is_unspecified(self) -> None:
        assert mod.read_unmet("**Not met for `render`**, which shows no estimate") == (frozenset(), True)
        assert mod.read_unmet("**AC-1 not met; Not met for render**") == (frozenset({1}), True)

    def test_scope_whose_only_gap_is_a_carved_criterion_is_done(self) -> None:
        # SC-002 owns FR-3 (shipped) and FR-4, partial only because AC-3 belongs to SC-003.
        requirements = swap(REQUIREMENTS, "| FR-3 | planned | SC-002 |", "| FR-3 | shipped | SC-002 |")
        roadmap = swap(ROADMAP_TEXT, "In progress — design: ADR-1", "Done — design: ADR-1")
        assert run(requirements, roadmap) == []

    def test_carved_gap_plus_an_uncarved_unmet_criterion_is_in_progress(self) -> None:
        requirements = swap(REQUIREMENTS, "| FR-3 | planned | SC-002 |", "| FR-3 | shipped | SC-002 |")
        requirements = swap(requirements, "**AC-3 not met**", "**AC-2 and AC-3 not met**")
        roadmap = swap(ROADMAP_TEXT, "In progress — design: ADR-1", "Done — design: ADR-1")
        problems = run(requirements, roadmap)
        assert len(problems) == 1
        assert "SC-002 is marked Done, but the status table puts it at In progress" in problems[0]
        assert "FR-4's note names AC-2 as not met" in problems[0]

    def test_shipped_requirement_with_an_unspecified_not_met_clause_is_not_done(self) -> None:
        requirements = swap(
            REQUIREMENTS, "| NFR-1 | shipped | SC-004 | |", "| NFR-1 | shipped | SC-004 | **Not met for `render`** |"
        )
        problems = run(requirements=requirements)
        assert len(problems) == 1
        assert "SC-004 is marked Done" in problems[0]
        assert "NFR-1's note names an unmet criterion without a number" in problems[0]

    def test_capitalised_not_met_clause_blocks_done(self) -> None:
        requirements = swap(
            REQUIREMENTS, "| NFR-1 | shipped | SC-004 | |", "| NFR-1 | shipped | SC-004 | **AC-4 Not met** |"
        )
        problems = run(requirements=requirements)
        assert len(problems) == 1
        assert "NFR-1's note names AC-4 as not met" in problems[0]

    def test_carved_criterion_in_a_reverify_row_keeps_its_owner_from_done(self) -> None:
        # SC-003 owns FR-5 and FR-4 AC-3. With AC-3 confirmed it is Done; a Re-verify note confirms nothing.
        requirements = swap(REQUIREMENTS, "| FR-5 | planned | SC-003 |", "| FR-5 | shipped | SC-003 |")
        confirmed = swap(requirements, "**AC-3 not met** — a gap", "AC-3 holds")
        roadmap = swap(ROADMAP_TEXT, "FR-5, FR-4 AC-3 | Planned", "FR-5, FR-4 AC-3 | Done")
        assert run(confirmed, roadmap) == []

        unconfirmed = swap(confirmed, "AC-3 holds", "**Re-verify.** AC-3 holds")
        problems = run(unconfirmed, roadmap)
        assert len(problems) == 1
        assert "SC-003 is marked Done, but the status table puts it at In progress" in problems[0]
        assert "FR-4 AC-3 is unconfirmed: FR-4 carries a Re-verify note" in problems[0]

    def test_carved_criterion_that_is_not_built_keeps_its_owner_from_done(self) -> None:
        requirements = swap(REQUIREMENTS, "| FR-5 | planned | SC-003 |", "| FR-5 | shipped | SC-003 |")
        roadmap = swap(ROADMAP_TEXT, "FR-5, FR-4 AC-3 | Planned", "FR-5, FR-4 AC-3 | Done")
        problems = run(requirements, roadmap)
        assert len(problems) == 1
        assert "SC-003 is marked Done" in problems[0]
        assert "FR-4 AC-3 is not built" in problems[0]

    def test_partial_requirement_with_no_unmet_criterion_named_is_not_done(self) -> None:
        requirements = swap(
            REQUIREMENTS, "| FR-2 | partial | SC-001 | **AC-2 not met** — a gap |", "| FR-2 | partial | SC-001 | |"
        )
        roadmap = swap(ROADMAP_TEXT, "FR-1, FR-2 | In progress", "FR-1, FR-2 | Done")
        problems = run(requirements, roadmap)
        assert len(problems) == 1
        assert "FR-2 is partial and its note names no unmet criterion" in problems[0]

    def test_scope_that_owns_nothing_is_an_error_not_a_state(self) -> None:
        # NFR-1 moves to SC-001, so SC-004 is left with a row and nothing to own.
        requirements = swap(REQUIREMENTS, "| NFR-1 | shipped | SC-004 |", "| NFR-1 | shipped | SC-001 |")
        problems = run(requirements=requirements)
        assert "ROADMAP.md SC-004 has a row, but the status table gives it no requirement and no criterion." in problems
        assert not any("SC-004 is marked" in p for p in problems)


class TestParsing:
    def test_requirements_cell_forms(self) -> None:
        row = mod.parse_requirements_cell(
            "SC-009",
            "FR-4, NFR-5 AC-2, FR-39 AC-5, AC-6, AC-7, FR-7c (except AC-2, in SC-010), and Go's share — FR-7, FR-9",
        )
        assert row.whole == ["FR-4", "FR-7c"]
        assert row.excepts == [("FR-7c", frozenset({2}), "SC-010")]
        assert row.criteria == [
            ("NFR-5", frozenset({2})),
            ("FR-39", frozenset({5})),
            ("FR-39", frozenset({6})),
            ("FR-39", frozenset({7})),
        ]

    def test_dependency_note_after_a_dash_is_ignored(self) -> None:
        row = mod.parse_requirements_cell("SC-006", "FR-7, FR-7a — FR-7a's check completes with SC-010")
        assert row.whole == ["FR-7", "FR-7a"]

    def test_unreadable_requirements_cell_is_reported_not_guessed(self) -> None:
        roadmap = swap(ROADMAP_TEXT, "FR-1, FR-2", "FR-1, mostly FR-2")
        problems = run(roadmap=roadmap)
        assert problems == ["ROADMAP.md SC-001: cannot read 'mostly FR-2' in the Requirements cell"]

    def test_and_before_a_requirement_is_reported_not_dropped(self) -> None:
        roadmap = swap(ROADMAP_TEXT, "FR-1, FR-2", "FR-1, FR-2, and FR-3")
        problems = run(roadmap=roadmap)
        assert len(problems) == 1
        assert problems[0].startswith("ROADMAP.md SC-001: cannot read 'FR-1, FR-2, and FR-3'")
        assert "separate them with commas" in problems[0]

    def test_empty_requirements_cell_is_reported(self) -> None:
        roadmap = swap(ROADMAP_TEXT, "| Outcome | NFR-1 |", "| Outcome |  |")
        assert run(roadmap=roadmap) == ["ROADMAP.md SC-004: the Requirements cell is empty"]

    def test_unreadable_state_is_reported(self) -> None:
        roadmap = swap(ROADMAP_TEXT, "| Done |", "| Finished |")
        problems = run(roadmap=roadmap)
        assert len(problems) == 1
        assert problems[0].startswith("ROADMAP.md SC-004: the State cell 'Finished'")

    def test_unreadable_status_scope_is_reported(self) -> None:
        requirements = swap(REQUIREMENTS, "| FR-1 | shipped | SC-001 |", "| FR-1 | shipped | scope one |")
        problems = run(requirements=requirements)
        assert len(problems) == 1
        assert problems[0].startswith("docs/requirements.md FR-1: cannot read the scope cell 'scope one'")

    def test_unknown_status_is_reported(self) -> None:
        requirements = swap(REQUIREMENTS, "| FR-1 | shipped |", "| FR-1 | done |")
        problems = run(requirements=requirements)
        assert len(problems) == 1
        assert "FR-1: status 'done' is not one of" in problems[0]

    def test_missing_tables_are_reported(self) -> None:
        problems = run(requirements="nothing here", roadmap="nothing here")
        assert len(problems) == 2
        assert "no status table found" in problems[0]
        assert "no scope table found" in problems[1]

    def test_criteria_formatting_round_trips_the_documents_style(self) -> None:
        assert mod._fmt_acs(frozenset({5, 6, 7})) == "AC-5 to AC-7"
        assert mod._fmt_acs(frozenset({1, 2})) == "AC-1, AC-2"
        assert mod._fmt_acs(frozenset({2, 4, 5, 6})) == "AC-2, AC-4 to AC-6"


class TestRepository:
    """The script runs against the repository's own two files."""

    @pytest.fixture
    def texts(self) -> tuple[str, str]:
        root = mod.REPO_ROOT
        return (
            (root / mod.REQUIREMENTS).read_text(encoding="utf-8"),
            (root / mod.ROADMAP).read_text(encoding="utf-8"),
        )

    def test_repository_files_agree(self, texts: tuple[str, str]) -> None:
        assert mod.check(*texts) == []

    def test_main_exits_0_on_the_repository(self) -> None:
        assert mod.main() == 0

    def test_main_exits_1_and_names_the_cell_on_disagreement(
        self,
        texts: tuple[str, str],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        requirements, roadmap = texts
        (tmp_path / "docs").mkdir()
        (tmp_path / mod.REQUIREMENTS).write_text(requirements, encoding="utf-8")
        (tmp_path / mod.ROADMAP).write_text(swap(roadmap, "| In progress | — |", "| Done | — |"), encoding="utf-8")
        monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)

        assert mod.main() == 1
        err = capsys.readouterr().err
        assert "ROADMAP.md SC-001 is marked Done" in err

    def test_every_repository_scope_state_is_derived(self, texts: tuple[str, str]) -> None:
        # The derived state of each scope matches its row — guards against a check that never compares.
        requirements = mod.parse_status_table(texts[0])
        scopes = mod.parse_roadmap(texts[1])
        assert len(scopes) >= 13
        for scope, row in scopes.items():
            assert mod.derive_state(scope, requirements)[0] == row.state

    def test_main_exits_1_when_a_file_is_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
        assert mod.main() == 1
        assert "Cannot read the roadmap or the status table" in capsys.readouterr().err
