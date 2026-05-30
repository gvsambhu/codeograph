"""
Unit tests for CorpusAnalyzer (codeograph/analyzer/corpus_analyzer.py).

All four collaborators (dispatcher, builder, assembler, writer) are mocked.
No filesystem I/O, no JVM, no real graph construction.

Coverage plan:
  - analyze() calls dispatcher.parse() once per java_file across all modules
  - analyze() calls builder.build() with correct (parsed_file, module_id) args
  - analyze() passes all (ParsedFile, graph) tuples to assembler.assemble()
  - analyze() calls writer.write() with (assembled_graph, output_dir)
  - analyze() returns whatever writer.write() returns
  - Empty corpus (zero modules) → assembler called with [], writer still called
  - Module with zero java_files → no parser/builder calls for that module
  - Multi-module corpus → fragments from all modules merged into one assemble() call
  - module_id from ModuleSpec is passed verbatim to builder.build()
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from codeograph.analyzer.corpus_analyzer import CorpusAnalyzer
from codeograph.input.models import AcquisitionSource, BuildTool, CorpusSpec, ModuleSpec

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_collaborators() -> tuple[MagicMock, MagicMock, MagicMock, MagicMock]:
    """Return (dispatcher, builder, assembler, writer) mocks with safe defaults."""
    dispatcher = MagicMock()
    builder = MagicMock()
    assembler = MagicMock()
    writer = MagicMock()

    # dispatcher.parse() returns a distinct object per call so assertions can
    # verify the right ParsedFile was passed to builder.
    dispatcher.parse.side_effect = lambda java_file, corpus_root: {
        "id": str(java_file),
        "kind": "class",
        "name": java_file.stem,
        "extraction_mode": "ast",
    }

    # builder.build() returns a MagicMock that acts as a graph fragment.
    builder.build.return_value = MagicMock(name="graph_fragment")

    # assembler.assemble() returns a MagicMock that acts as the assembled graph.
    assembler.assemble.return_value = MagicMock(name="assembled_graph")

    # writer.write() returns a sentinel manifest path.
    writer.write.return_value = Path("/out/manifest.json")

    return dispatcher, builder, assembler, writer


def _make_module(
    module_id: str,
    java_files: list[Path],
    root_path: Path | None = None,
) -> ModuleSpec:
    root = root_path or Path(f"/corpus/{module_id.removeprefix('mod:')}")
    return ModuleSpec(
        module_id=module_id,
        name=module_id.removeprefix("mod:"),
        root_path=root,
        build_tool=BuildTool.MAVEN,
        source_roots=[root / "src/main/java"],
        java_files=java_files,
    )


def _make_corpus(
    modules: list[ModuleSpec],
    corpus_root: Path | None = None,
) -> CorpusSpec:
    root = corpus_root or Path("/corpus")
    return CorpusSpec(
        acquisition_source=AcquisitionSource.LOCAL,
        corpus_root=root,
        modules=modules,
    )


def _make_analyzer(*mocks: MagicMock) -> CorpusAnalyzer:
    dispatcher, builder, assembler, writer = mocks
    return CorpusAnalyzer(
        dispatcher=dispatcher,
        builder=builder,
        assembler=assembler,
        writer=writer,
    )


# ---------------------------------------------------------------------------
# TestReturnValue
# ---------------------------------------------------------------------------


class TestReturnValue:
    def test_returns_manifest_path_from_writer(self, tmp_path: Path) -> None:
        mocks = _mock_collaborators()
        analyzer = _make_analyzer(*mocks)
        writer = mocks[3]
        writer.write.return_value = tmp_path / "manifest.json"

        corpus = _make_corpus(modules=[], corpus_root=tmp_path)
        result = analyzer.analyze(corpus, tmp_path)

        assert result == tmp_path / "manifest.json"


# ---------------------------------------------------------------------------
# TestDispatcherCalls
# ---------------------------------------------------------------------------


class TestDispatcherCalls:
    def test_parse_called_once_per_file(self, tmp_path: Path) -> None:
        mocks = _mock_collaborators()
        analyzer = _make_analyzer(*mocks)
        dispatcher = mocks[0]

        files = [tmp_path / "A.java", tmp_path / "B.java", tmp_path / "C.java"]
        module = _make_module("mod:core", files, root_path=tmp_path)
        corpus = _make_corpus([module], corpus_root=tmp_path)

        analyzer.analyze(corpus, tmp_path / "out")

        assert dispatcher.parse.call_count == 3

    def test_parse_called_with_corpus_root(self, tmp_path: Path) -> None:
        mocks = _mock_collaborators()
        analyzer = _make_analyzer(*mocks)
        dispatcher = mocks[0]

        java_file = tmp_path / "Foo.java"
        module = _make_module("mod:core", [java_file], root_path=tmp_path)
        corpus = _make_corpus([module], corpus_root=tmp_path)

        analyzer.analyze(corpus, tmp_path / "out")

        dispatcher.parse.assert_called_once_with(java_file, tmp_path)

    def test_parse_called_for_files_across_all_modules(self, tmp_path: Path) -> None:
        mocks = _mock_collaborators()
        analyzer = _make_analyzer(*mocks)
        dispatcher = mocks[0]

        mod_a = _make_module("mod:a", [tmp_path / "A.java"], root_path=tmp_path / "a")
        mod_b = _make_module("mod:b", [tmp_path / "B.java", tmp_path / "C.java"], root_path=tmp_path / "b")
        corpus = _make_corpus([mod_a, mod_b], corpus_root=tmp_path)

        analyzer.analyze(corpus, tmp_path / "out")

        assert dispatcher.parse.call_count == 3


# ---------------------------------------------------------------------------
# TestBuilderCalls
# ---------------------------------------------------------------------------


class TestBuilderCalls:
    def test_build_called_once_per_file(self, tmp_path: Path) -> None:
        mocks = _mock_collaborators()
        analyzer = _make_analyzer(*mocks)
        builder = mocks[1]

        files = [tmp_path / "A.java", tmp_path / "B.java"]
        module = _make_module("mod:svc", files, root_path=tmp_path)
        corpus = _make_corpus([module], corpus_root=tmp_path)

        analyzer.analyze(corpus, tmp_path / "out")

        assert builder.build.call_count == 2

    def test_build_receives_module_id_verbatim(self, tmp_path: Path) -> None:
        mocks = _mock_collaborators()
        analyzer = _make_analyzer(*mocks)
        builder = mocks[1]

        java_file = tmp_path / "Foo.java"
        module = _make_module("mod:my-service", [java_file], root_path=tmp_path)
        corpus = _make_corpus([module], corpus_root=tmp_path)

        analyzer.analyze(corpus, tmp_path / "out")

        # Second positional arg to build() must be the module_id string
        _, build_kwargs_module_id = builder.build.call_args[0]
        assert build_kwargs_module_id == "mod:my-service"

    def test_build_receives_parsed_file_from_dispatcher(self, tmp_path: Path) -> None:
        mocks = _mock_collaborators()
        analyzer = _make_analyzer(*mocks)
        dispatcher, builder = mocks[0], mocks[1]

        java_file = tmp_path / "Foo.java"
        module = _make_module("mod:core", [java_file], root_path=tmp_path)
        corpus = _make_corpus([module], corpus_root=tmp_path)

        # side_effect takes precedence over return_value — clear it first so
        # the sentinel object is actually returned.
        dispatched_pf = {"id": "com.example.Foo", "kind": "class", "name": "Foo", "extraction_mode": "ast"}
        dispatcher.parse.side_effect = None
        dispatcher.parse.return_value = dispatched_pf

        analyzer.analyze(corpus, tmp_path / "out")

        build_parsed_file_arg = builder.build.call_args[0][0]
        assert build_parsed_file_arg is dispatched_pf

    def test_build_module_id_matches_module_spec_field(self, tmp_path: Path) -> None:
        """module.module_id (not module.name or module.root_path.name) is passed."""
        mocks = _mock_collaborators()
        analyzer = _make_analyzer(*mocks)
        builder = mocks[1]

        # module_id and name deliberately differ to catch any field mix-up
        module = ModuleSpec(
            module_id="mod:artifact-id",
            name="directory-name",
            root_path=tmp_path,
            build_tool=BuildTool.MAVEN,
            java_files=[tmp_path / "X.java"],
        )
        corpus = _make_corpus([module], corpus_root=tmp_path)

        analyzer.analyze(corpus, tmp_path / "out")

        _, module_id_arg = builder.build.call_args[0]
        assert module_id_arg == "mod:artifact-id"


# ---------------------------------------------------------------------------
# TestAssemblerCalls
# ---------------------------------------------------------------------------


class TestAssemblerCalls:
    def test_assemble_called_once(self, tmp_path: Path) -> None:
        mocks = _mock_collaborators()
        analyzer = _make_analyzer(*mocks)
        assembler = mocks[2]

        module = _make_module("mod:core", [tmp_path / "A.java"], root_path=tmp_path)
        corpus = _make_corpus([module], corpus_root=tmp_path)

        analyzer.analyze(corpus, tmp_path / "out")

        assembler.assemble.assert_called_once()

    def test_assemble_receives_all_fragments(self, tmp_path: Path) -> None:
        mocks = _mock_collaborators()
        analyzer = _make_analyzer(*mocks)
        assembler = mocks[2]

        files = [tmp_path / "A.java", tmp_path / "B.java"]
        module = _make_module("mod:core", files, root_path=tmp_path)
        corpus = _make_corpus([module], corpus_root=tmp_path)

        analyzer.analyze(corpus, tmp_path / "out")

        fragments_arg = assembler.assemble.call_args[0][0]
        assert len(fragments_arg) == 2

    def test_assemble_receives_tuples_of_parsed_file_and_graph(self, tmp_path: Path) -> None:
        mocks = _mock_collaborators()
        analyzer = _make_analyzer(*mocks)
        dispatcher, builder, assembler = mocks[0], mocks[1], mocks[2]

        java_file = tmp_path / "Foo.java"
        module = _make_module("mod:core", [java_file], root_path=tmp_path)
        corpus = _make_corpus([module], corpus_root=tmp_path)

        sentinel_pf = {"id": "x", "kind": "class", "name": "x", "extraction_mode": "ast"}
        sentinel_graph = MagicMock(name="frag")
        dispatcher.parse.side_effect = None  # clear lambda; return_value takes over
        dispatcher.parse.return_value = sentinel_pf
        builder.build.return_value = sentinel_graph

        analyzer.analyze(corpus, tmp_path / "out")

        fragments_arg = assembler.assemble.call_args[0][0]
        assert fragments_arg[0] == (sentinel_pf, sentinel_graph)

    def test_assemble_receives_fragments_across_modules(self, tmp_path: Path) -> None:
        mocks = _mock_collaborators()
        analyzer = _make_analyzer(*mocks)
        assembler = mocks[2]

        mod_a = _make_module("mod:a", [tmp_path / "A.java"], root_path=tmp_path / "a")
        mod_b = _make_module("mod:b", [tmp_path / "B.java", tmp_path / "C.java"], root_path=tmp_path / "b")
        corpus = _make_corpus([mod_a, mod_b], corpus_root=tmp_path)

        analyzer.analyze(corpus, tmp_path / "out")

        fragments_arg = assembler.assemble.call_args[0][0]
        assert len(fragments_arg) == 3


# ---------------------------------------------------------------------------
# TestWriterCalls
# ---------------------------------------------------------------------------


class TestWriterCalls:
    def test_writer_called_with_assembled_graph(self, tmp_path: Path) -> None:
        mocks = _mock_collaborators()
        analyzer = _make_analyzer(*mocks)
        assembler, writer = mocks[2], mocks[3]

        sentinel_assembled = MagicMock(name="assembled")
        assembler.assemble.return_value = sentinel_assembled

        corpus = _make_corpus([], corpus_root=tmp_path)
        analyzer.analyze(corpus, tmp_path / "out")

        graph_arg = writer.write.call_args[0][0]
        assert graph_arg is sentinel_assembled

    def test_writer_called_with_output_dir(self, tmp_path: Path) -> None:
        mocks = _mock_collaborators()
        analyzer = _make_analyzer(*mocks)
        writer = mocks[3]

        out_dir = tmp_path / "graph-out"
        corpus = _make_corpus([], corpus_root=tmp_path)
        analyzer.analyze(corpus, out_dir)

        dir_arg = writer.write.call_args[0][1]
        assert dir_arg == out_dir


# ---------------------------------------------------------------------------
# TestEdgeCases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_corpus_still_calls_assembler_and_writer(self, tmp_path: Path) -> None:
        mocks = _mock_collaborators()
        analyzer = _make_analyzer(*mocks)
        dispatcher, builder, assembler, writer = mocks

        corpus = _make_corpus([], corpus_root=tmp_path)
        analyzer.analyze(corpus, tmp_path / "out")

        dispatcher.parse.assert_not_called()
        builder.build.assert_not_called()
        assembler.assemble.assert_called_once_with([])
        writer.write.assert_called_once()

    def test_module_with_no_java_files_skipped(self, tmp_path: Path) -> None:
        mocks = _mock_collaborators()
        analyzer = _make_analyzer(*mocks)
        dispatcher, builder = mocks[0], mocks[1]

        empty_module = _make_module("mod:empty", [], root_path=tmp_path)
        corpus = _make_corpus([empty_module], corpus_root=tmp_path)

        analyzer.analyze(corpus, tmp_path / "out")

        dispatcher.parse.assert_not_called()
        builder.build.assert_not_called()

    def test_mixed_modules_only_files_parsed(self, tmp_path: Path) -> None:
        """Empty module alongside a non-empty one — only non-empty module's files parsed."""
        mocks = _mock_collaborators()
        analyzer = _make_analyzer(*mocks)
        dispatcher = mocks[0]

        empty_module = _make_module("mod:empty", [], root_path=tmp_path / "empty")
        nonempty_module = _make_module("mod:core", [tmp_path / "A.java"], root_path=tmp_path / "core")
        corpus = _make_corpus([empty_module, nonempty_module], corpus_root=tmp_path)

        analyzer.analyze(corpus, tmp_path / "out")

        assert dispatcher.parse.call_count == 1
