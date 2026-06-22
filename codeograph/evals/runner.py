"""EvalRunner — orchestrates graph and code-quality checks (ADR-017 Forks 5+6)."""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from codeograph.evals.checks.code import (
    check_compile,
    check_coverage,
    check_llm_judge,
)
from codeograph.evals.checks.graph import (
    check_golden_graph_agreement,
    check_internal_consistency,
    check_relationship_correctness,
    check_reproducibility,
    check_schema_validity,
    check_semantic_accuracy,
    check_structural_completeness,
)
from codeograph.evals.models import (
    BooleanThreshold,
    CheckResult,
    MinRatioThreshold,
    ReproducibilityInfo,
    Scorecard,
)
from codeograph.logging_config import RunIdLoggerAdapter
from codeograph.manifest.io import read as manifest_io_read
from codeograph.manifest.models import ScorecardPointer

logger = logging.getLogger(__name__)

# Canonical scorecard filename templates (ADR-017 Fork 1).
_GRAPH_SCORECARD_NAME = "graph-scorecard.json"
_CODE_SCORECARD_NAME = "{target}-scorecard.json"

# All graph check IDs in lexicographic order (canonical for JSON sorting).
_ALL_GRAPH_CHECK_IDS = [
    "golden_graph_agreement",
    "internal_consistency",
    "relationship_correctness",
    "reproducibility",
    "schema_validity",
    "semantic_accuracy",
    "structural_completeness",
]

# All code check IDs per target.
_ALL_CODE_CHECK_IDS = ["compile", "coverage", "llm_judge"]


class MissingOutputError(RuntimeError):
    """Raised when output_dir or manifest.json does not exist."""


def run_evals(
    output_dir: Path,
    scorecard_kinds: list[str],
    check_filter: list[str] | None = None,
    skip_checks: list[str] | None = None,
    *,
    corpus_id: str | None = None,
    run_id: str | None = None,
    codeograph_version: str | None = None,
    graph_sha256: str | None = None,
) -> tuple[list[Scorecard], dict[str, ScorecardPointer]]:
    """Run selected scorecards against *output_dir*.

    Returns a ``(scorecards, scorecard_pointers)`` tuple. Writing the
    scorecard pointers into the manifest is the **caller's responsibility**
    — the standalone ``eval run`` CLI command patches the manifest after
    calling this function; the ``run --eval`` path passes the pointers to
    the run assembler's single terminal write.

    Context params (``corpus_id``, ``run_id``, ``codeograph_version``,
    ``graph_sha256``) are resolved from the on-disk manifest when not
    supplied, which is the standalone ``codeograph eval run`` path.
    The ``run --eval`` path passes them in-memory so no manifest read is
    needed before the terminal write.

    :param output_dir:          Directory produced by ``codeograph run``.
    :param scorecard_kinds:     Which scorecards to produce. ``"graph"`` for
                                graph-quality; any other string is a renderer
                                target name (e.g. ``"ts"``).
    :param check_filter:        If non-None, run only these check IDs.
                                Mutually exclusive with *skip_checks*.
    :param skip_checks:         Check IDs to skip; all others run.
    :param corpus_id:           Corpus identifier. Read from manifest if None.
    :param run_id:              Run identifier. Read from manifest if None.
    :param codeograph_version:  Package version. Read from manifest if None.
    :param graph_sha256:        SHA-256 of graph.json. Read from manifest if None.
    :raises MissingOutputError: If output_dir absent, or manifest absent and
                                context params are not fully provided.
    """
    scorecards: list[Scorecard] = []

    manifest_path = output_dir / "manifest.json"
    graph_path = output_dir / "graph.json"

    # ---------------------------------------------------------------- #
    # 1. Preflight
    # ---------------------------------------------------------------- #
    if not output_dir.exists():
        raise MissingOutputError(f"no rendered output at {output_dir}; run `codeograph run` first.")

    # Resolve context from manifest when any param is absent (standalone path).
    if corpus_id is None or run_id is None or codeograph_version is None or graph_sha256 is None:
        if not manifest_path.exists():
            raise MissingOutputError(f"no rendered output at {output_dir}; run `codeograph run` first.")
        manifest = manifest_io_read(manifest_path)
        corpus_id = corpus_id or manifest.corpus_id
        codeograph_version = codeograph_version or manifest.codeograph_version
        run_id = run_id or manifest.run_id
        graph_sha256 = graph_sha256 or manifest.artefacts["graph"].sha256

    run_ts = datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")

    run_logger = RunIdLoggerAdapter(logger, run_id)

    # ---------------------------------------------------------------- #
    # 2. Resolve active check IDs from filter / skip parameters
    # ---------------------------------------------------------------- #
    def _is_active(check_id: str) -> bool:
        if check_filter:
            return check_id in check_filter
        if skip_checks:
            return check_id not in skip_checks
        return True

    def _explicit_skip(check_id: str) -> CheckResult:
        return CheckResult(
            id=check_id,
            category="graph" if check_id in _ALL_GRAPH_CHECK_IDS else "code",
            result="skip",
            value=None,
            threshold=BooleanThreshold(expected=True),
            rationale="Skipped via --skip-check / --check filter.",
            duration_ms=0,
            details={"skip_reason": "explicit_skip"},
        )

    # ---------------------------------------------------------------- #
    # 3. Graph scorecard
    # ---------------------------------------------------------------- #
    if "graph" in scorecard_kinds:
        if not graph_path.exists():
            raise MissingOutputError(f"graph.json missing at {graph_path}")

        with open(graph_path, encoding="utf-8") as f:
            graph_data = json.load(f)

        from codeograph.graph.models.graph_schema import CodeographKnowledgeGraph

        graph_obj = CodeographKnowledgeGraph.model_validate(graph_data)

        _graph_dispatch: dict[str, CheckResult] = {}
        if _is_active("golden_graph_agreement"):
            # corpus_id and graph_sha256 are resolved above; no manifest read inside the check.
            _graph_dispatch["golden_graph_agreement"] = check_golden_graph_agreement(corpus_id, graph_sha256)
        if _is_active("internal_consistency"):
            _graph_dispatch["internal_consistency"] = check_internal_consistency(graph_obj)
        if _is_active("relationship_correctness"):
            _graph_dispatch["relationship_correctness"] = check_relationship_correctness(graph_obj)
        if _is_active("reproducibility"):
            _graph_dispatch["reproducibility"] = check_reproducibility(output_dir)
        if _is_active("schema_validity"):
            _graph_dispatch["schema_validity"] = check_schema_validity(graph_obj)
        if _is_active("semantic_accuracy"):
            _graph_dispatch["semantic_accuracy"] = check_semantic_accuracy(graph_obj)
        if _is_active("structural_completeness"):
            _graph_dispatch["structural_completeness"] = check_structural_completeness(graph_obj)

        graph_checks: list[CheckResult] = [
            _graph_dispatch.get(cid, _explicit_skip(cid)) for cid in _ALL_GRAPH_CHECK_IDS
        ]

        scorecards.append(
            Scorecard(
                schema_version="1.0.0",
                kind="graph",
                corpus_id=corpus_id,
                run_timestamp=run_ts,
                run_id=run_id,
                reproducibility=ReproducibilityInfo(
                    codeograph_version=codeograph_version,
                    seed=0,
                ),
                checks=graph_checks,
            )
        )

    # ---------------------------------------------------------------- #
    # 4. Code scorecards — parallel across targets (Fork 6)
    # ---------------------------------------------------------------- #
    code_targets = [t for t in scorecard_kinds if t != "graph"]

    def _eval_target(target: str) -> Scorecard:
        target_path = output_dir / target
        code_checks: list[CheckResult] = []

        if not target_path.exists():
            for check_id in _ALL_CODE_CHECK_IDS:
                code_checks.append(
                    CheckResult(
                        id=check_id,
                        category="code",
                        result="skip",
                        value=None,
                        threshold=MinRatioThreshold(pass_at_or_above=1.0),
                        rationale="target_not_rendered",
                        duration_ms=0,
                        details={"skip_reason": "target_not_rendered"},
                    )
                )
        else:
            _code_dispatch: dict[str, CheckResult] = {}
            if _is_active("compile"):
                _code_dispatch["compile"] = check_compile(output_dir, target)
            if _is_active("coverage"):
                _code_dispatch["coverage"] = check_coverage(output_dir, target)
            if _is_active("llm_judge"):
                _code_dispatch["llm_judge"] = check_llm_judge(output_dir, target)
            for check_id in _ALL_CODE_CHECK_IDS:
                code_checks.append(_code_dispatch.get(check_id, _explicit_skip(check_id)))

        return Scorecard(
            schema_version="1.0.0",
            kind=target,  # type: ignore[arg-type]
            corpus_id=corpus_id,
            run_timestamp=run_ts,
            run_id=run_id,
            reproducibility=ReproducibilityInfo(
                codeograph_version=codeograph_version,
                seed=0,
            ),
            checks=code_checks,
        )

    if code_targets:
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(_eval_target, code_targets))
        scorecards.extend(results)

    # ---------------------------------------------------------------- #
    # 5. Write scorecard JSON files; build scorecard pointers
    # ---------------------------------------------------------------- #
    evals_dir = output_dir / "evals"
    evals_dir.mkdir(parents=True, exist_ok=True)

    scorecard_pointers: dict[str, ScorecardPointer] = {}

    for scorecard in scorecards:
        if scorecard.kind == "graph":
            filename = _GRAPH_SCORECARD_NAME
        else:
            filename = _CODE_SCORECARD_NAME.format(target=scorecard.kind)

        filepath = evals_dir / filename
        content = scorecard.model_dump_json(indent=2).encode("utf-8")
        filepath.write_bytes(content)
        sha256 = hashlib.sha256(content).hexdigest()

        overall = "pass" if all(c.result in ("pass", "skip") for c in scorecard.checks) else "fail"

        scorecard_pointers[scorecard.kind] = ScorecardPointer(
            path=f"evals/{filename}",
            sha256=sha256,
            overall=overall,
        )
        run_logger.info("Wrote scorecard: %s (overall=%s)", filepath, overall)

    # Manifest patching is the caller's responsibility:
    #   - standalone `eval run`: cli/eval.py reads the manifest and patches it
    #   - `run --eval`: main.py passes the pointers to the assembler's single terminal write
    return scorecards, scorecard_pointers
