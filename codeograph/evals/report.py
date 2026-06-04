"""EvalReport — aggregates and renders cross-corpus scorecard reports."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from codeograph.evals.scorecard_schema import Scorecard


class AggregatedCheck(BaseModel):
    id: str
    category: str
    threshold_type: str
    overall_result: Literal["pass", "fail", "skip"]
    corpus_results: dict[str, dict[str, Any]]  # Maps corpus_id to result & value
    aggregate_value: dict[str, Any]  # The calculated aggregate


class ReportResult(BaseModel):
    overall: Literal["pass", "fail", "mixed"]
    kinds: dict[str, list[AggregatedCheck]]


class EvalReport:
    """Generates cross-corpus eval reports from output directories."""

    @classmethod
    def generate(cls, output_dirs: list[Path]) -> ReportResult:
        """Parse scorecards in given output directories and aggregate results."""
        # 1. Load scorecards: kind -> corpus_id -> Scorecard
        scorecards_by_kind: dict[str, dict[str, Scorecard]] = defaultdict(dict)
        
        for d in output_dirs:
            evals_dir = d / "evals"
            if not evals_dir.exists():
                continue
                
            for file_path in evals_dir.glob("*-scorecard.json"):
                try:
                    with open(file_path, encoding="utf-8") as f:
                        sc = Scorecard.model_validate_json(f.read())
                    scorecards_by_kind[sc.kind][sc.corpus_id] = sc
                except Exception:
                    pass

        kinds: dict[str, list[AggregatedCheck]] = {}
        all_results: set[Literal["pass", "fail", "skip"]] = set()

        # 2. Aggregate per kind
        for kind, corpus_map in scorecards_by_kind.items():
            # Collect all check IDs for this kind (union across corpora)
            check_ids = set()
            for sc in corpus_map.values():
                for c in sc.checks:
                    check_ids.add(c.id)
            
            sorted_check_ids = sorted(list(check_ids))
            
            aggregated_checks = []
            for cid in sorted_check_ids:
                # Gather all results for this check across corpora
                c_results: dict[str, dict[str, Any]] = {}
                threshold_type = "unknown"
                category = "unknown"
                
                raw_values = []
                outcomes: set[Literal["pass", "fail", "skip"]] = set()
                
                for corpus_id, sc in corpus_map.items():
                    c_record = next((c for c in sc.checks if c.id == cid), None)
                    if c_record:
                        if threshold_type == "unknown":
                            threshold_type = c_record.threshold.__class__.__name__
                            category = c_record.category
                            
                        val = c_record.value
                        res = c_record.result
                        
                        c_results[corpus_id] = {
                            "result": res,
                            "value": val
                        }
                        
                        outcomes.add(res)
                        
                        if val is not None and res != "skip":
                            raw_values.append(val)
                
                # Determine overall outcome for this check
                check_overall: Literal["pass", "fail", "skip"] = "skip"
                if "fail" in outcomes:
                    check_overall = "fail"
                elif "pass" in outcomes:
                    check_overall = "pass"
                    
                all_results.add(check_overall)
                    
                # Calculate aggregate value
                agg_val: dict[str, Any] = {}
                if threshold_type == "BooleanThreshold":
                    pass_count = sum(1 for res in c_results.values() if res["result"] == "pass")
                    agg_val = {"pass_count": pass_count, "total": len(c_results)}
                elif threshold_type == "MinRatioThreshold":
                    if raw_values:
                        agg_val = {
                            "mean": round(sum(raw_values) / len(raw_values), 4),
                            "min": round(min(raw_values), 4),
                            "max": round(max(raw_values), 4)
                        }
                    else:
                        agg_val = {"mean": None, "min": None, "max": None}
                elif threshold_type == "MaxCountThreshold":
                    if raw_values:
                        agg_val = {
                            "sum": sum(raw_values),
                            "max": max(raw_values)
                        }
                    else:
                        agg_val = {"sum": None, "max": None}
                        
                aggregated_checks.append(AggregatedCheck(
                    id=cid,
                    category=category,
                    threshold_type=threshold_type,
                    overall_result=check_overall,
                    corpus_results=c_results,
                    aggregate_value=agg_val
                ))
            
            kinds[kind] = aggregated_checks

        # 3. Overall result
        overall: Literal["pass", "fail", "mixed"] = "pass"
        if "fail" in all_results:
            if "pass" in all_results:
                overall = "mixed"
            else:
                overall = "fail"
        elif "pass" not in all_results and "skip" in all_results:
            # Only skips
            overall = "pass"

        return ReportResult(
            overall=overall,
            kinds=kinds
        )

    @classmethod
    def render_markdown(cls, report: ReportResult) -> str:
        """Render the ReportResult as markdown tables."""
        lines = []
        
        emoji_map = {
            "pass": "✅",
            "fail": "❌",
            "skip": "⏭️",
            "mixed": "⚠️"
        }
        
        lines.append("# Evaluation Report")
        lines.append(f"**Overall Result:** {emoji_map.get(report.overall, '')} {report.overall.upper()}\n")
        
        for kind, checks in sorted(report.kinds.items()):
            lines.append(f"## Scorecard: `{kind}`\n")
            
            # Determine all corpus IDs for column headers
            corpus_ids: set[str] = set()
            for c in checks:
                corpus_ids.update(c.corpus_results.keys())
            sorted_corpora = sorted(list(corpus_ids))
            
            # Build table header
            header = ["Check"] + sorted_corpora + ["Aggregate"]
            lines.append("| " + " | ".join(header) + " |")
            lines.append("| " + " | ".join(["---"] * len(header)) + " |")
            
            # Build rows
            for c in checks:
                row = [f"`{c.id}`"]
                
                # Corpus columns
                for corpus in sorted_corpora:
                    res = c.corpus_results.get(corpus)
                    if res:
                        e = emoji_map.get(res["result"], "❓")
                        val = res["value"]
                        val_str = f" ({val})" if val is not None else ""
                        row.append(f"{e}{val_str}")
                    else:
                        row.append("-")
                        
                # Aggregate column
                if c.threshold_type == "BooleanThreshold":
                    pass_c = c.aggregate_value.get("pass_count", 0)
                    tot = c.aggregate_value.get("total", 0)
                    agg_str = f"{pass_c}/{tot} pass"
                elif c.threshold_type == "MinRatioThreshold":
                    mean = c.aggregate_value.get("mean")
                    agg_str = f"mean: {mean}" if mean is not None else "N/A"
                elif c.threshold_type == "MaxCountThreshold":
                    s = c.aggregate_value.get("sum")
                    agg_str = f"sum: {s}" if s is not None else "N/A"
                else:
                    agg_str = ""
                    
                e_overall = emoji_map.get(c.overall_result, "❓")
                row.append(f"{e_overall} {agg_str}")
                
                lines.append("| " + " | ".join(row) + " |")
                
            lines.append("")
            
        return "\n".join(lines)
