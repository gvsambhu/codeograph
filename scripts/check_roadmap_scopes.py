"""Fail if ROADMAP.md and the requirements' status table disagree.

The roadmap's scope table repeats facts the status table (``docs/requirements.md``,
section 7) owns. Changing a status row can silently leave the roadmap wrong, so this
gate compares the two. Three things are checked:

1. **Ownership.** Every requirement that is not retired is listed, as a whole
   requirement, in exactly one roadmap row — the row of the scope the status table
   names. Every ID a row lists exists in the status table and is not retired.
2. **Criterion exceptions.** When the status table gives some of a requirement's
   acceptance criteria to another scope (``SC-007 (AC-2: SC-010)``), the owning
   row says ``FR-7c (except AC-2, in SC-010)`` and the other row lists
   ``FR-7c AC-2`` — the same criteria on both sides.
3. **States.** A scope's state word follows the rule in the roadmap's *How a
   scope's state is read*, counting only what the scope owns: *Done* when every
   requirement it owns is shipped and verified — a requirement left ``partial`` only
   by criteria another scope owns does not hold it back — and every criterion it owns
   in another scope's requirement holds; *Planned* when none of it is built;
   *In progress* otherwise. A scope that owns nothing is an error. Only the state
   word is compared, not the design note beside it.

The status table wins; correct ``ROADMAP.md`` in the same change as the status row.
A cell this script cannot parse is reported as such rather than guessed at.

Usage::

    python scripts/check_roadmap_scopes.py
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = "docs/requirements.md"
ROADMAP = "ROADMAP.md"

STATUSES = frozenset({"shipped", "partial", "planned", "retired"})
STATES = ("Planned", "In progress", "Done")

_AC = r"AC-(\d+)(?: to AC-(\d+))?"
_REQ_ID = r"(?:N?FR)-\d+[a-z]?"
_SCOPE_ID = r"SC-\d{3}"

REQ_ID_RE = re.compile(rf"^{_REQ_ID}$")
AC_SPEC_RE = re.compile(rf"^{_AC}$")
# Status-table scope cell: "SC-004", or "SC-007 (AC-2: SC-010)" when another scope owns criteria.
OWNER_RE = re.compile(rf"^({_SCOPE_ID})(?: \({_AC}: ({_SCOPE_ID})\))?$")
SCOPE_NAME_RE = re.compile(rf"^\*\*({_SCOPE_ID}): .+\*\*$")
STATE_RE = re.compile(r"^(Planned|In progress|Done)(?: — design: .*)?$")

# One comma-separated item of a roadmap Requirements cell.
WHOLE_RE = re.compile(rf"^({_REQ_ID})$")
EXCEPT_RE = re.compile(rf"^({_REQ_ID}) \(except {_AC}, in ({_SCOPE_ID})\)$")
CRITERIA_RE = re.compile(rf"^({_REQ_ID}) {_AC}$")
CONTINUED_CRITERIA_RE = re.compile(rf"^{_AC}$")

BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
AC_REF_RE = re.compile(rf"{_AC}")


class ParseError(ValueError):
    """An input cell this script cannot read; the message names the file and cell."""


@dataclass(frozen=True)
class Requirement:
    id: str
    status: str
    owner: str | None  # None for a retired requirement
    carve: tuple[frozenset[int], str] | None  # (criteria owned elsewhere, the scope that owns them)
    note: str


@dataclass
class RoadmapRow:
    scope: str
    state: str
    whole: list[str] = field(default_factory=list)
    excepts: list[tuple[str, frozenset[int], str]] = field(default_factory=list)  # (req, criteria, other scope)
    criteria: list[tuple[str, frozenset[int]]] = field(default_factory=list)  # (req, criteria owned here)


def _expand(first: str, last: str | None) -> frozenset[int]:
    lo = int(first)
    hi = int(last) if last else lo
    return frozenset(range(lo, hi + 1))


def _fmt_acs(acs: frozenset[int]) -> str:
    """Render criteria the way the documents do: ``AC-5 to AC-7`` or ``AC-2, AC-4``."""
    nums = sorted(acs)
    parts: list[str] = []
    i = 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        if j - i >= 2:
            parts.append(f"AC-{nums[i]} to AC-{nums[j]}")
        else:
            parts.extend(f"AC-{n}" for n in nums[i : j + 1])
        i = j + 1
    return ", ".join(parts)


def _section_rows(text: str, heading: re.Pattern[str]) -> list[str]:
    """Table rows (lines starting ``|``) under the first heading that matches, up to the next heading or rule."""
    rows: list[str] = []
    inside = False
    for line in text.splitlines():
        if not inside:
            inside = bool(heading.match(line))
            continue
        if line.startswith("#") or line.strip() == "---":
            if rows:
                break
            continue
        if line.startswith("|"):
            rows.append(line)
    return rows


def _is_separator(line: str) -> bool:
    return set(line.replace("|", "").strip()) <= set("-: ")


# --------------------------------------------------------------------------- status table


def parse_status_table(text: str) -> dict[str, Requirement]:
    """Read ``docs/requirements.md`` section 7 into requirements keyed by ID."""
    rows = _section_rows(text, re.compile(r"^## 7\."))
    if not rows:
        raise ParseError(f"{REQUIREMENTS}: no status table found under the '## 7.' heading")
    requirements: dict[str, Requirement] = {}
    for line in rows:
        if _is_separator(line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|", 3)]
        if len(cells) != 4:
            raise ParseError(f"{REQUIREMENTS}: status row does not have four cells: {line[:80]}")
        req_id, status, scope, note = cells
        if req_id == "ID":
            continue
        if not REQ_ID_RE.match(req_id):
            raise ParseError(f"{REQUIREMENTS}: unreadable requirement ID '{req_id}'")
        if status not in STATUSES:
            raise ParseError(f"{REQUIREMENTS} {req_id}: status '{status}' is not one of {', '.join(sorted(STATUSES))}")
        if req_id in requirements:
            raise ParseError(f"{REQUIREMENTS}: {req_id} appears in the status table twice")
        if status == "retired":
            if scope != "—":
                raise ParseError(
                    f"{REQUIREMENTS} {req_id}: a retired requirement's scope cell must be '—', not '{scope}'"
                )
            requirements[req_id] = Requirement(req_id, status, None, None, note)
            continue
        match = OWNER_RE.match(scope)
        if not match:
            raise ParseError(
                f"{REQUIREMENTS} {req_id}: cannot read the scope cell '{scope}' "
                "(expected 'SC-NNN' or 'SC-NNN (AC-n: SC-MMM)')"
            )
        carve = (_expand(match.group(2), match.group(3)), match.group(4)) if match.group(2) else None
        requirements[req_id] = Requirement(req_id, status, match.group(1), carve, note)
    return requirements


# --------------------------------------------------------------------------- roadmap


def _split_top_level(cell: str) -> list[str]:
    """Split on commas outside parentheses."""
    parts: list[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(cell):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(cell[start:i].strip())
            start = i + 1
    parts.append(cell[start:].strip())
    return parts


def _strip_trailing_prose(scope: str, cell: str) -> str:
    """Drop a dependency note (`` — …``) or a per-target obligations clause (``, and Go's share …``).

    A ``, and`` followed by a requirement ID is a list, not prose, and is refused rather than dropped.
    """
    cell = cell.split(" — ", 1)[0]
    if re.search(rf", and {_REQ_ID}(?![A-Za-z0-9-])", cell):
        raise ParseError(
            f"{ROADMAP} {scope}: cannot read '{cell}' in the Requirements cell — "
            "', and' joins requirements; separate them with commas"
        )
    return cell.split(", and ", 1)[0].strip()


def parse_requirements_cell(scope: str, cell: str) -> RoadmapRow:
    """Parse one roadmap Requirements cell into whole requirements, exceptions and owned criteria."""
    row = RoadmapRow(scope, "")
    previous: str | None = None  # the requirement a bare "AC-n" continues
    if not cell.strip():
        raise ParseError(f"{ROADMAP} {scope}: the Requirements cell is empty")
    for item in _split_top_level(_strip_trailing_prose(scope, cell)):
        if m := WHOLE_RE.match(item):
            row.whole.append(m.group(1))
            previous = None
        elif m := EXCEPT_RE.match(item):
            row.whole.append(m.group(1))
            row.excepts.append((m.group(1), _expand(m.group(2), m.group(3)), m.group(4)))
            previous = None
        elif m := CRITERIA_RE.match(item):
            previous = m.group(1)
            row.criteria.append((previous, _expand(m.group(2), m.group(3))))
        elif (m := CONTINUED_CRITERIA_RE.match(item)) and previous:
            row.criteria.append((previous, _expand(m.group(1), m.group(2))))
        else:
            raise ParseError(f"{ROADMAP} {scope}: cannot read '{item}' in the Requirements cell")
    return row


def parse_roadmap(text: str) -> dict[str, RoadmapRow]:
    """Read the ``## Scopes`` table of ``ROADMAP.md`` into rows keyed by scope ID."""
    rows = _section_rows(text, re.compile(r"^## Scopes\s*$"))
    scopes: dict[str, RoadmapRow] = {}
    for line in rows:
        if _is_separator(line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells[0] == "Scope":
            continue
        if len(cells) != 5:
            raise ParseError(f"{ROADMAP}: scope row does not have five cells: {line[:80]}")
        name = SCOPE_NAME_RE.match(cells[0])
        if not name:
            raise ParseError(f"{ROADMAP}: cannot read the scope name '{cells[0]}'")
        scope = name.group(1)
        if scope in scopes:
            raise ParseError(f"{ROADMAP}: {scope} has two rows")
        state = STATE_RE.match(cells[3])
        if not state:
            raise ParseError(
                f"{ROADMAP} {scope}: the State cell '{cells[3]}' must start with Planned, In progress or Done"
            )
        row = parse_requirements_cell(scope, cells[2])
        row.state = state.group(1)
        scopes[scope] = row
    if not scopes:
        raise ParseError(f"{ROADMAP}: no scope table found under '## Scopes'")
    return scopes


# --------------------------------------------------------------------------- comparison


def check_ownership(requirements: dict[str, Requirement], scopes: dict[str, RoadmapRow]) -> list[str]:
    """Checks 1 and 2: who owns each requirement, and who owns each carved-out criterion."""
    errors: list[str] = []

    listed_by: dict[str, list[str]] = {}
    for scope, row in scopes.items():
        for req_id in row.whole:
            listed_by.setdefault(req_id, []).append(scope)
    mentioned = [(s, r) for s, row in scopes.items() for r in [*row.whole, *(c[0] for c in row.criteria)]]
    for scope, req_id in dict.fromkeys(mentioned):
        req = requirements.get(req_id)
        if req is None:
            errors.append(f"{ROADMAP} {scope} lists {req_id}, but the status table has no such requirement.")
        elif req.status == "retired":
            errors.append(f"{ROADMAP} {scope} lists {req_id}, but the status table retires it; remove it from the row.")

    for req_id, req in requirements.items():
        if req.owner is None:
            continue
        holders = listed_by.get(req_id, [])
        if not holders:
            errors.append(f"{ROADMAP} lists {req_id} in no scope, but the status table gives it to {req.owner}.")
        elif len(holders) > 1:
            errors.append(
                f"{ROADMAP} lists {req_id} in {', '.join(holders)}, but the status table gives it to {req.owner} alone."
            )
        elif holders[0] != req.owner:
            errors.append(f"{ROADMAP} {holders[0]} lists {req_id}, but the status table gives {req_id} to {req.owner}.")
        if req.owner not in scopes:
            errors.append(f"{REQUIREMENTS} gives {req_id} to {req.owner}, which {ROADMAP} has no row for.")

    # Criterion exceptions, both directions.
    expected_except = {(r.owner, r.id): r.carve for r in requirements.values() if r.owner and r.carve}
    expected_criteria = {(r.carve[1], r.id): r.carve[0] for r in requirements.values() if r.owner and r.carve}
    actual_except: dict[tuple[str, str], tuple[frozenset[int], str]] = {}
    actual_criteria: dict[tuple[str, str], frozenset[int]] = {}
    for scope, row in scopes.items():
        for req_id, acs, other in row.excepts:
            actual_except[(scope, req_id)] = (acs, other)
        for req_id, acs in row.criteria:
            actual_criteria[(scope, req_id)] = actual_criteria.get((scope, req_id), frozenset()) | acs

    for (scope, req_id), carve in expected_except.items():
        assert carve is not None
        acs, other = carve
        want = f"{req_id} (except {_fmt_acs(acs)}, in {other})"
        if actual_except.get((scope, req_id)) != (acs, other) and scope in scopes:
            errors.append(
                f"{ROADMAP} {scope} should list '{want}', "
                f"since the status table gives {_fmt_acs(acs)} of {req_id} to {other}."
            )
    for (scope, req_id), acs in expected_criteria.items():
        if actual_criteria.get((scope, req_id)) != acs and scope in scopes:
            errors.append(
                f"{ROADMAP} {scope} should list '{req_id} {_fmt_acs(acs)}', "
                f"since the status table gives those criteria of {req_id} to {scope}."
            )
    for (scope, req_id), (acs, other) in actual_except.items():
        if (scope, req_id) not in expected_except and req_id in requirements:
            errors.append(
                f"{ROADMAP} {scope} lists '{req_id} (except {_fmt_acs(acs)}, in {other})', "
                f"but the status table does not give any criterion of {req_id} to {other}."
            )
    for (scope, req_id), acs in actual_criteria.items():
        if (scope, req_id) not in expected_criteria and req_id in requirements:
            errors.append(
                f"{ROADMAP} {scope} lists '{req_id} {_fmt_acs(acs)}', "
                f"but the status table does not give criteria of {req_id} to {scope}."
            )
    return errors


def read_unmet(note: str) -> tuple[frozenset[int], bool]:
    """What a status note names as not met, in bold clauses such as ``**AC-4 not met**``.

    Returns the numbered criteria, and whether some clause says *not met* without naming a
    criterion (``**Not met for `render`**``) — an unspecified criterion that blocks *Done*
    for every scope that counts the requirement. Clauses are separated by ``;`` and read
    case-insensitively.
    """
    unmet: set[int] = set()
    unspecified = False
    for bold in BOLD_RE.findall(note):
        for clause in bold.split(";"):
            if "not met" not in clause.lower() and "unmet" not in clause.lower():
                continue
            refs = list(AC_REF_RE.finditer(clause))
            if not refs:
                unspecified = True
            for m in refs:
                unmet |= _expand(m.group(1), m.group(2))
    return frozenset(unmet), unspecified


def derive_state(scope: str, requirements: dict[str, Requirement]) -> tuple[str, str]:
    """The state the status table implies for a scope, with the reason an *In progress* verdict gives.

    The scope counts what it owns: whole requirements (minus criteria another scope owns), and
    criteria it owns in other scopes' requirements.
    """
    done_blockers: list[str] = []
    planned_blockers: list[str] = []

    for req in requirements.values():
        if req.owner != scope:
            continue
        unmet, unspecified = read_unmet(req.note)
        carved = req.carve[0] if req.carve else frozenset[int]()
        if req.status == "planned":
            done_blockers.append(f"{req.id} is planned")
        elif "**Re-verify" in req.note:
            done_blockers.append(f"{req.id} carries a Re-verify note")
        elif unspecified:
            done_blockers.append(f"{req.id}'s note names an unmet criterion without a number")
        elif unmet - carved:
            done_blockers.append(f"{req.id}'s note names {_fmt_acs(unmet - carved)} as not met")
        elif req.status == "partial" and not unmet:
            done_blockers.append(f"{req.id} is partial and its note names no unmet criterion")
        if req.status != "planned":
            planned_blockers.append(f"{req.id} is {req.status}")

    for req in requirements.values():
        if req.owner is None or not req.carve or req.carve[1] != scope:
            continue
        acs = req.carve[0]
        unmet, unspecified = read_unmet(req.note)
        not_met = acs & unmet
        label = f"{req.id} {_fmt_acs(acs)}"
        if req.status == "planned" or not_met:
            done_blockers.append(f"{label} is not built")
        elif unspecified:
            done_blockers.append(
                f"{label} cannot be confirmed: {req.id}'s note names an unmet criterion without a number"
            )
        elif "**Re-verify" in req.note:
            done_blockers.append(f"{label} is unconfirmed: {req.id} carries a Re-verify note")
        if req.status != "planned" and acs - not_met:
            planned_blockers.append(f"{req.id} {_fmt_acs(acs - not_met)} is not named as not met")

    if not done_blockers:
        return "Done", "every requirement and criterion it owns is shipped and verified"
    if not planned_blockers:
        return "Planned", "none of what it owns is built"
    return "In progress", f"{done_blockers[0]}, and {planned_blockers[0]}"


def owns_nothing(scope: str, requirements: dict[str, Requirement]) -> bool:
    """True when the status table gives the scope no requirement and no criterion."""
    return not any(r.owner == scope or (r.carve and r.carve[1] == scope) for r in requirements.values() if r.owner)


def check_states(requirements: dict[str, Requirement], scopes: dict[str, RoadmapRow]) -> list[str]:
    errors: list[str] = []
    for scope, row in scopes.items():
        if owns_nothing(scope, requirements):
            errors.append(
                f"{ROADMAP} {scope} has a row, but the status table gives it no requirement and no criterion."
            )
            continue
        state, reason = derive_state(scope, requirements)
        if state != row.state:
            errors.append(
                f"{ROADMAP} {scope} is marked {row.state}, but the status table puts it at {state}: {reason}."
            )
    return errors


def check(requirements_text: str, roadmap_text: str) -> list[str]:
    """All disagreements between the two documents; empty when they agree."""
    problems: list[str] = []
    requirements: dict[str, Requirement] = {}
    scopes: dict[str, RoadmapRow] = {}
    try:
        requirements = parse_status_table(requirements_text)
    except ParseError as exc:
        problems.append(str(exc))
    try:
        scopes = parse_roadmap(roadmap_text)
    except ParseError as exc:
        problems.append(str(exc))
    if problems:
        return problems
    return check_ownership(requirements, scopes) + check_states(requirements, scopes)


def main(argv: list[str] | None = None) -> int:
    del argv  # the two inputs are fixed repository files
    try:
        requirements_text = (REPO_ROOT / REQUIREMENTS).read_text(encoding="utf-8")
        roadmap_text = (REPO_ROOT / ROADMAP).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Cannot read the roadmap or the status table: {exc}", file=sys.stderr)
        return 1

    problems = check(requirements_text, roadmap_text)
    if not problems:
        return 0

    print("ROADMAP.md and the requirements' status table disagree:\n", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    print(
        "\nThe status table wins. Correct ROADMAP.md (or the status row, if it is the one that is wrong)\n"
        "in the same change.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
