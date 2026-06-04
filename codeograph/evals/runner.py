import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib

from codeograph.evals.scorecard_schema import Scorecard, ReproducibilityInfo, CheckResult, BooleanThreshold
from codeograph.evals.checks.graph import (
    check_structural_completeness,
    check_relationship_correctness,
    check_schema_validity,
    check_internal_consistency,
    check_semantic_accuracy,
    check_reproducibility,
    check_golden_graph_agreement,
)
from codeograph.evals.checks.code import (
    check_compile,
    check_coverage,
    check_llm_judge,
)

logger = logging.getLogger(__name__)


class EvalRunner:
    """Orchestrates graph and code evaluation checks."""

    def __init__(self) -> None:
        self.thread_pool = ThreadPoolExecutor(max_workers=4)

    def run(
        self,
        output_dir: Path,
        scorecard_kinds: list[str],
        check_filter: list[str] | None = None,
        skip_checks: list[str] | None = None,
    ) -> list[Scorecard]:
        """
        Main orchestration loop for evaluations.
        """
        scorecards: list[Scorecard] = []
        
        import sys
        import datetime
        manifest_path = output_dir / "manifest.json"
        graph_path = output_dir / "graph.json"
        
        # 1. Preflight check
        if not output_dir.exists() or not manifest_path.exists():
            logger.error(f"no rendered output at {output_dir}; run `codeograph run` first.")
            sys.exit(2)
            
        # 2. Read manifest.json
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
            
        # 3. Graph checks
        if "graph" in scorecard_kinds:
            if not graph_path.exists():
                logger.error(f"graph.json missing at {graph_path}")
                sys.exit(2)
                
            with open(graph_path, encoding="utf-8") as f:
                graph_data = json.load(f)
                
            from codeograph.graph.models.graph_schema import CodeographKnowledgeGraph
            graph_obj = CodeographKnowledgeGraph.model_validate(graph_data)
            
            graph_checks = [
                check_golden_graph_agreement(output_dir),
                check_internal_consistency(graph_obj),
                check_relationship_correctness(graph_obj),
                check_reproducibility(output_dir),
                check_schema_validity(graph_obj),
                check_semantic_accuracy(graph_obj),
                check_structural_completeness(graph_obj),
            ]
            
            # Assemble graph Scorecard
            scorecards.append(Scorecard(
                schema_version="1.0.0",
                kind="graph",
                corpus_id=manifest.get("corpus_id", "unknown"),
                run_timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                run_id=manifest.get("run_id", "unknown"),
                reproducibility=ReproducibilityInfo(
                    codeograph_version=manifest.get("codeograph_version", "unknown"),
                    seed=manifest.get("seed", 0)
                ),
                checks=graph_checks,
            ))

        # 4. Code scorecards (parallelized targets)
        code_targets = [t for t in scorecard_kinds if t != "graph"]
        
        def _eval_target(target: str) -> Scorecard:
            target_path = output_dir / target
            if not target_path.exists():
                logger.warning(f"target {target} not found at {target_path}; skipping checks")
                code_checks = [
                    CheckResult(
                        id="compile",
                        category="code",
                        result="skip",
                        value=None,
                        threshold=BooleanThreshold(expected=True),
                        rationale="target_not_rendered",
                        duration_ms=0
                    ),
                    CheckResult(
                        id="coverage",
                        category="code",
                        result="skip",
                        value=None,
                        threshold=BooleanThreshold(expected=True),
                        rationale="target_not_rendered",
                        duration_ms=0
                    ),
                    CheckResult(
                        id="llm_judge",
                        category="code",
                        result="skip",
                        value=None,
                        threshold=BooleanThreshold(expected=True),
                        rationale="target_not_rendered",
                        duration_ms=0
                    )
                ]
            else:
                # Run 3 checks sequentially for the target
                code_checks = [
                    check_compile(output_dir, target),
                    check_coverage(output_dir, target),
                    check_llm_judge(output_dir, target),
                ]
                
            return Scorecard(
                schema_version="1.0.0",
                kind=target, # type: ignore
                corpus_id=manifest.get("corpus_id", "unknown"),
                run_timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                run_id=manifest.get("run_id", "unknown"),
                reproducibility=ReproducibilityInfo(
                    codeograph_version=manifest.get("codeograph_version", "unknown"),
                    seed=manifest.get("seed", 0)
                ),
                checks=code_checks,
            )

        if code_targets:
            # Run code checks in parallel across targets
            results = list(self.thread_pool.map(_eval_target, code_targets))
            scorecards.extend(results)

        # 5. Overwrite the scorecards in `output_dir/evals/` (e.g., scorecard.graph.json).
        evals_dir = output_dir / "evals"
        evals_dir.mkdir(parents=True, exist_ok=True)
        
        for scorecard in scorecards:
            filename = f"scorecard.{scorecard.kind}.json"
            filepath = evals_dir / filename
            
            with open(filepath, "w", encoding="utf-8") as f:
                # Fixed bug: use model_dump_json directly, no json.dump
                f.write(scorecard.model_dump_json(indent=2))
            
            logger.info(f"Wrote scorecard: {filepath}")

        # 6. Patch the manifest's `scorecards` array with the new files and their updated sha256 hashes.
        # We need to read the manifest again, update the scorecards list, and write it back.
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_out = json.load(f)
        
        # Clear the old scorecards list
        manifest_out["scorecards"] = []
        
        # Add the new scorecards with their sha256 hashes
        for scorecard in scorecards:
            filename = f"scorecard.{scorecard.kind}.json"
            filepath = evals_dir / filename
            
            with open(filepath, "rb") as bf:
                sha256_hash = hashlib.sha256(bf.read()).hexdigest()
            
            manifest_out["scorecards"].append({
                "path": f"evals/{filename}",
                "sha256": sha256_hash,
            })
        
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_out, f, indent=2)
        
        logger.info(f"Patched manifest with updated scorecard information at {manifest_path}")                

        return scorecards
