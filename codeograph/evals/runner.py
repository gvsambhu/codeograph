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
from codeograph.evals.scorecard_schema import (
    BooleanThreshold,
    CheckResult,
    MinRatioThreshold,
    ReproducibilityInfo,
    Scorecard,
)

logger = logging.getLogger(__name__)

# Canonical scorecard filename templates (ADR-017 Fork 1).
# graph scorecard → graph-scorecard.json
# code scorecard  → <target>-scorecard.json  (e.g. ts-scorecard.json)
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


class EvalRunner:
    """Orchestrates graph and code evaluation checks per ADR-017 Forks 5+6.

    Usage::

        runner = EvalRunner()
        scorecards = runner.run(
            output_dir=Path("out/"),
            scorecard_kinds=["graph", "ts"],
        )
    """

    def __init__(self) -> None:
        pass  # No long-lived resources; ThreadPoolExecutor is scoped to run()

    def run(
        self,
        output_dir: Path,
        scorecard_kinds: list[str],
        check_filter: list[str] | None = None,
        skip_checks: list[str] | None = None,
    ) -> list[Scorecard]:
        """Run selected scorecards against *output_dir*.

        :param output_dir:      Directory produced by ``codeograph run``.
        :param scorecard_kinds: Which scorecards to produce. ``"graph"`` for
                                graph-quality; any other string is a renderer
                                target name (e.g. ``"ts"``).
        :param check_filter:    If non-None, run only these check IDs.
                                Mutually exclusive with *skip_checks*.
        :param skip_checks:     Check IDs to skip; all others run.
        :raises MissingOutputError: If output_dir or manifest.json absent.
        """
        scorecards: list[Scorecard] = []

        manifest_path = output_dir / "manifest.json"
        graph_path = output_dir / "graph.json"

        # ---------------------------------------------------------------- #
        # 1. Preflight — raise rather than sys.exit (CLI owns exit codes)
        # ---------------------------------------------------------------- #
        if not output_dir.exists() or not manifest_path.exists():
            raise MissingOutputError(
                f"no rendered output at {output_dir}; run `codeograph run` first."
            )

        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

        corpus_id = manifest.get("corpus_id", "unknown")
        codeograph_version = manifest.get("codeograph_version", "unknown")
        run_id = manifest.get("run_id", "unknown")
        run_ts = datetime.datetime.now(datetime.UTC).isoformat()

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
            """Return a skip record for a check excluded by --skip-check."""
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
                _graph_dispatch["golden_graph_agreement"] = check_golden_graph_agreement(output_dir)
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
                _graph_dispatch.get(cid, _explicit_skip(cid))
                for cid in _ALL_GRAPH_CHECK_IDS
            ]

            scorecards.append(Scorecard(
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
            ))

        # ---------------------------------------------------------------- #
        # 4. Code scorecards — parallel across targets (Fork 6)
        # ---------------------------------------------------------------- #
        code_targets = [t for t in scorecard_kinds if t != "graph"]

        def _eval_target(target: str) -> Scorecard:
            target_path = output_dir / target
            code_checks: list[CheckResult] = []

            if not target_path.exists():
                # Target not rendered → skip all three slots
                for check_id in _ALL_CODE_CHECK_IDS:
                    code_checks.append(CheckResult(
                        id=check_id,
                        category="code",
                        result="skip",
                        value=None,
                        threshold=MinRatioThreshold(pass_at_or_above=1.0),
                        rationale="target_not_rendered",
                        duration_ms=0,
                        details={"skip_reason": "target_not_rendered"},
                    ))
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
        # 5. Write scorecards to evals/ (ADR-017 Fork 1 filenames)
        # ---------------------------------------------------------------- #
        evals_dir = output_dir / "evals"
        evals_dir.mkdir(parents=True, exist_ok=True)

        scorecard_pointers: dict[str, dict[str, str]] = {}

        for scorecard in scorecards:
            if scorecard.kind == "graph":
                filename = _GRAPH_SCORECARD_NAME
            else:
                filename = _CODE_SCORECARD_NAME.format(target=scorecard.kind)

            filepath = evals_dir / filename
            content = scorecard.model_dump_json(indent=2).encode("utf-8")
            filepath.write_bytes(content)
            sha256 = hashlib.sha256(content).hexdigest()

            # Derive overall: "pass" iff every check passes; skips don't fail overall
            overall = "pass" if all(
                c.result in ("pass", "skip") for c in scorecard.checks
            ) else "fail"

            scorecard_pointers[scorecard.kind] = {
                "path": f"evals/{filename}",
                "sha256": sha256,
                "overall": overall,
            }
            logger.info("Wrote scorecard: %s (overall=%s)", filepath, overall)

        # ---------------------------------------------------------------- #
        # 6. Patch manifest.artefacts.scorecards (dict keyed by kind)
        # ---------------------------------------------------------------- #
        with open(manifest_path, encoding="utf-8") as f:
            manifest_out = json.load(f)

        manifest_out.setdefault("artefacts", {})["scorecards"] = scorecard_pointers

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_out, f, indent=2)

        logger.info("Patched manifest scorecards pointer at %s", manifest_path)

        return scorecards
