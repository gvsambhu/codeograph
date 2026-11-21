"""The pre-flight gate counts the nodes Pass 1 annotates, not every node in the graph."""

from __future__ import annotations

import json
from pathlib import Path

import click
import pytest

from codeograph.config.settings import Settings
from codeograph.llm.pre_flight_cost_gate import PreFlightCostGate
from codeograph.manifest.artefact import GraphArtefact


def _graph(path: Path) -> GraphArtefact:
    kinds = ["class"] * 4 + ["interface"] * 2 + ["method"] * 30 + ["field"] * 20
    nodes = [{"id": f"n{i}", "kind": kind} for i, kind in enumerate(kinds)]
    path.write_text(json.dumps({"nodes": nodes}), encoding="utf-8")
    return GraphArtefact(path=path, schema_version="1.0.0", sha256="0" * 64)


def test_the_estimate_counts_annotatable_classes_plus_one_pass_2_call(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    graph = _graph(tmp_path / "graph.json")

    PreFlightCostGate(Settings(llm_call_confirm_threshold=100)).check(graph, yes=True, non_interactive=True)

    assert "7 calls" in capsys.readouterr().out  # 6 type nodes + Pass 2, not the 56 nodes in the graph


def test_the_gate_threshold_is_judged_on_the_class_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("codeograph.llm.confirmation_gate.ConfirmationGate.is_tty", lambda _self: False)
    graph = _graph(tmp_path / "graph.json")

    # 7 calls is under a threshold of 10, so an unattended run proceeds; counting all 56 nodes would refuse it.
    PreFlightCostGate(Settings(llm_call_confirm_threshold=10)).check(graph, yes=False, non_interactive=False)

    with pytest.raises(click.ClickException, match=r"Estimated calls \(7\)"):
        PreFlightCostGate(Settings(llm_call_confirm_threshold=6)).check(graph, yes=False, non_interactive=False)
