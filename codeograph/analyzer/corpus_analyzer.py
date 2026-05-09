"""
CorpusAnalyzer — orchestrates the full DC1 AST pipeline for a corpus.

Pipeline sequence (ADR-003, ADR-006, ADR-007):

    CorpusSpec
        └── for each module → for each java_file
                FileParserDispatcher.parse()   → ParsedFile
                GraphBuilder.build()           → CodeographKnowledgeGraph (fragment)
        └── GraphAssembler.assemble(fragments) → CodeographKnowledgeGraph (merged)
        └── GraphWriter.write(graph, out_dir)  → manifest_path

DC1 scope — AST-only mode.  LLM enrichment (Pass 1 / Pass 2) is a DC2
concern and is not wired here.  The `--ast-only` flag at the CLI is the
signal that this pipeline is in use; the flag is accepted but has no effect
on CorpusAnalyzer's behaviour in v1 since there is no LLM stage to skip.

Error-handling contract:
  - FileParserDispatcher.parse() never raises (falls back to regex internally).
  - GraphBuilder.build() logs and returns an empty graph for unknown-kind files;
    CorpusAnalyzer collects the (ParsedFile, empty-graph) pair without skipping
    it — GraphAssembler deduplicates nodes, so empty fragments are harmless.
  - GraphWriter.write() may raise OSError on filesystem failures; those
    propagate to the caller (the CLI reports them).
"""

from __future__ import annotations

import logging
from pathlib import Path

from codeograph.graph.graph_assembler import GraphAssembler
from codeograph.graph.graph_builder import GraphBuilder
from codeograph.graph.graph_writer import GraphWriter
from codeograph.input.models import CorpusSpec
from codeograph.parser.file_parser_dispatcher import FileParserDispatcher
from codeograph.parser.models import ParsedFile
from codeograph.graph.models.graph_schema import CodeographKnowledgeGraph

logger = logging.getLogger(__name__)


class CorpusAnalyzer:
    """
    Runs the DC1 AST pipeline for a fully-acquired corpus.

    Stateless after construction — the same instance can be reused across
    multiple analyze() calls (e.g. in tests).  All four collaborators are
    injected; CorpusAnalyzer owns none of them.

    :param dispatcher:  Parses each .java file; falls back to regex on JAR failure.
    :param builder:     Builds a per-file graph fragment from a ParsedFile.
    :param assembler:   Merges all fragments into a single corpus-level graph.
    :param writer:      Serialises the graph to disk in canonical form.
    """

    def __init__(
        self,
        dispatcher: FileParserDispatcher,
        builder:    GraphBuilder,
        assembler:  GraphAssembler,
        writer:     GraphWriter,
    ) -> None:
        self._dispatcher = dispatcher
        self._builder    = builder
        self._assembler  = assembler
        self._writer     = writer

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, corpus: CorpusSpec, output_dir: Path) -> Path:
        """
        Run the full AST pipeline for the given corpus.

        Iterates every module in corpus.modules, parses each .java file, builds
        a per-file graph fragment, assembles all fragments into a single graph,
        and writes it to output_dir.

        :param corpus:      Fully-acquired, fully-discovered corpus from InputAcquirer.
        :param output_dir:  Directory to write graph.json and manifest.json into.
                            Created if it does not exist (GraphWriter handles mkdir).
        :returns:           Path to manifest.json — the conventional entry point for
                            downstream consumers.
        :raises OSError:    If graph.json or manifest.json cannot be written.
        """
        fragments: list[tuple[ParsedFile, CodeographKnowledgeGraph]] = []

        total_files = sum(len(m.java_files) for m in corpus.modules)
        logger.info(
            "CorpusAnalyzer: starting — %d module(s), %d file(s)",
            len(corpus.modules),
            total_files,
        )

        for module in corpus.modules:
            logger.info(
                "CorpusAnalyzer: analyzing module %s (%d file(s))",
                module.module_id,
                len(module.java_files),
            )
            for java_file in module.java_files:
                parsed_file = self._dispatcher.parse(java_file, corpus.corpus_root)
                graph_fragment = self._builder.build(parsed_file, module.module_id)
                fragments.append((parsed_file, graph_fragment))

        logger.info("CorpusAnalyzer: assembling %d fragment(s)", len(fragments))
        assembled = self._assembler.assemble(fragments)

        logger.info("CorpusAnalyzer: writing graph to %s", output_dir)
        manifest_path = self._writer.write(assembled, output_dir)

        logger.info("CorpusAnalyzer: done — manifest at %s", manifest_path)
        return manifest_path
