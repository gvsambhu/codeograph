from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from codeograph.manifest.io import read
from codeograph.manifest.schema import Manifest


class TestNoManifestOnInterrupt:
    """A full run interrupted after the graph pass leaves no manifest."""

    def test_no_manifest_when_graph_passes_but_llm_fails(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Arrange: minimal Java project so Pass 0 (graph) actually runs.
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        src = input_dir / "Main.java"
        src.write_text(
            "public class Main { public static void main(String[] args) {} }",
            encoding="utf-8",
        )

        out_dir = tmp_path / "out"

        # Ensure LLM path is enabled (ast_only=False and API key present).
        monkeypatch.setenv("CODEOGRAPH_ANTHROPIC_API_KEY", "dummy-key")

        import os
        import platform

        is_windows = platform.system() == "Windows"
        path_sep = ";" if is_windows else ":"

        if is_windows:
            java_home = "C:/alldev/Java/jdk-25.0.1"
            java_bin = "C:/alldev/Java/jdk-25.0.1/bin"
            maven_bin = "C:/alldev/maven_root/apache-maven-3.8.6/bin"
        else:
            # Under WSL/Linux, convert Windows-style JAVA_HOME if set, or search common WSL mount paths.
            java_home = os.environ.get("JAVA_HOME")
            if java_home and java_home.upper().startswith("C:"):
                if os.path.exists("/c/alldev"):
                    java_home = java_home.replace("C:", "/c")
                elif os.path.exists("/mnt/c/alldev"):
                    java_home = java_home.replace("C:", "/mnt/c")

            if not java_home:
                if os.path.exists("/c/alldev/Java/jdk-25.0.1"):
                    java_home = "/c/alldev/Java/jdk-25.0.1"
                elif os.path.exists("/mnt/c/alldev/Java/jdk-25.0.1"):
                    java_home = "/mnt/c/alldev/Java/jdk-25.0.1"

            java_bin = f"{java_home}/bin" if java_home else ""

            if os.path.exists("/c/alldev/maven_root/apache-maven-3.8.6/bin"):
                maven_bin = "/c/alldev/maven_root/apache-maven-3.8.6/bin"
            elif os.path.exists("/mnt/c/alldev/maven_root/apache-maven-3.8.6/bin"):
                maven_bin = "/mnt/c/alldev/maven_root/apache-maven-3.8.6/bin"
            else:
                maven_bin = ""

        if java_home:
            monkeypatch.setenv("JAVA_HOME", java_home)

        current_path = os.environ.get("PATH", "")
        path_parts = []
        if maven_bin:
            path_parts.append(maven_bin)
        if java_bin:
            path_parts.append(java_bin)
        if current_path:
            path_parts.append(current_path)

        if path_parts:
            new_path = path_sep.join(path_parts)
            monkeypatch.setenv("PATH", new_path)

        # Patch NodeAnnotator.annotate to simulate a Pass 1 crash.
        from codeograph.passes.pass1.annotator import NodeAnnotator

        def boom(self: Any, nodes: list[Any]) -> None:
            raise RuntimeError("synthetic pass-1 failure")

        monkeypatch.setattr(NodeAnnotator, "annotate", boom)

        # Patch AnthropicProvider to bypass ChatAnthropic constructor validation errors.
        from unittest.mock import MagicMock

        monkeypatch.setattr(
            "codeograph.llm.providers.anthropic_provider.AnthropicProvider",
            lambda *args, **kwargs: MagicMock(),
        )

        # Import CLI after patch so lazy imports pick up the patched class.
        from codeograph.cli import main as cli_mod

        runner = CliRunner()
        result = runner.invoke(
            cli_mod.cli,
            [
                "run",
                str(input_dir),
                "--out",
                str(out_dir),
                # ensure we take the full LLM path
                "--eval",  # optional; mainly ensures we’re on the “full run” code path
            ],
        )

        # The run should fail due to our synthetic exception.
        assert result.exit_code != 0
        assert result.exception is not None
        assert "synthetic pass-1 failure" in str(result.exception)

        # Graph pass should have completed and written graph.json.
        graph_path = out_dir / "graph.json"
        assert graph_path.exists()

        # Terminal-write invariant: no manifest.json exists on interrupt.
        manifest_path = out_dir / "manifest.json"
        assert not manifest_path.exists()


class TestTerminalWritePresenceImpliesValid:
    """If a manifest is on disk, it satisfies all §Invariants."""

    def test_manifest_written_by_run_satisfies_all_invariants(
        self,
        tmp_path: Path,
    ) -> None:
        # We exercise the assembler directly to avoid the full CLI/LLM pipeline.
        from codeograph.manifest import ManifestAssembler
        from codeograph.manifest.artefact import GraphArtefact
        from codeograph.manifest.run_id import generate_run_id

        out_dir = tmp_path / "out"
        out_dir.mkdir()

        # Prepare a dummy graph artefact file with a valid SHA256.
        graph_path = out_dir / "graph.json"
        graph_content: dict[str, list[Any]] = {"nodes": [], "edges": []}
        graph_path.write_text(json.dumps(graph_content), encoding="utf-8")

        import hashlib

        graph_sha = hashlib.sha256(graph_path.read_bytes()).hexdigest()
        graph_artefact = GraphArtefact(
            path=graph_path,
            schema_version="1.0.0",
            sha256=graph_sha,
        )

        # Prepare a dummy LLM annotations artefact.
        llm_path = out_dir / "llm-annotations.json"
        llm_path.write_text("{}", encoding="utf-8")
        llm_sha = hashlib.sha256(llm_path.read_bytes()).hexdigest()
        llm_artefact = GraphArtefact(
            path=llm_path,
            schema_version="1.0.0",
            sha256=llm_sha,
        )

        run_id = generate_run_id()

        assembler = ManifestAssembler()

        # Case 1: full run (llm_skipped=False, both pointers present).
        manifest_full = assembler.assemble(
            run_id=run_id,
            codeograph_version="0.1.0",
            source_path=str(tmp_path / "source"),
            corpus_id="corpus-1",
            llm_skipped=False,
            graph_artefact=graph_artefact,
            llm_annotations_artefact=llm_artefact,
            cache_stats=None,
            scorecards=None,
            compile_checks=None,
        )
        manifest_path_full = assembler.write_to(manifest_full, out_dir)

        reread_full: Manifest = read(manifest_path_full)

        # §Invariants:
        # - artefacts.graph is always present
        assert "graph" in reread_full.artefacts
        # - every present pointer's sha256 is 64-hex and non-null
        for ptr_map in (
            reread_full.artefacts,
            reread_full.scorecards or {},
            reread_full.compile_checks or {},
        ):
            for ptr in ptr_map.values():
                assert isinstance(ptr.sha256, str)
                assert len(ptr.sha256) == 64
                assert all(c in "0123456789abcdef" for c in ptr.sha256)

        # - if llm_skipped is False, llm_annotations is present
        assert reread_full.llm_skipped is False
        assert "llm_annotations" in reread_full.artefacts

        # Case 2: AST-only run (llm_skipped=True, no llm_annotations pointer).
        manifest_ast_only = assembler.assemble(
            run_id=run_id,
            codeograph_version="0.1.0",
            source_path=str(tmp_path / "source"),
            corpus_id="corpus-1",
            llm_skipped=True,
            graph_artefact=graph_artefact,
            llm_annotations_artefact=None,
            cache_stats=None,
            scorecards=None,
            compile_checks=None,
        )
        manifest_path_ast = assembler.write_to(manifest_ast_only, out_dir)

        reread_ast: Manifest = read(manifest_path_ast)

        assert reread_ast.llm_skipped is True
        # - if llm_skipped is True, llm_annotations is absent
        assert "llm_annotations" not in reread_ast.artefacts
