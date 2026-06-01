import time

from codeograph.evals.scorecard_schema import CheckResult, MinRatioThreshold
from codeograph.graph.models.graph_schema import CodeographKnowledgeGraph


def check_structural_completeness(graph: CodeographKnowledgeGraph) -> CheckResult:
    start_time = time.perf_counter()

    from codeograph.graph.models.graph_schema import (
        AnnotationTypeNode,
        ClassNode,
        EnumNode,
        ExtractionMode,
        FieldNode,
        InterfaceNode,
        MethodNode,
        RecordNode,
    )

    # Nodes that represent source declarations (exclude ModuleNode — not a declaration)
    _DECLARATION_TYPES = (ClassNode, InterfaceNode, EnumNode, RecordNode,
                          AnnotationTypeNode, MethodNode, FieldNode)

    total = 0
    ast_extracted = 0

    for node_wrapper in graph.nodes:
        node = node_wrapper.root
        if not isinstance(node, _DECLARATION_TYPES):
            continue
        total += 1
        if getattr(node, "extraction_mode", ExtractionMode.ast) == ExtractionMode.ast:
            ast_extracted += 1

    value: float = (ast_extracted / total) if total > 0 else 1.0

    duration_ms = int((time.perf_counter() - start_time) * 1000)

    return CheckResult(
        id="structural_completeness",
        category="graph",
        value=value,
        threshold=MinRatioThreshold(pass_at_or_above=1.0),
        rationale="FR-7a — structural_completeness ensures all parsed source declarations are emitted as nodes in the graph (ADR-017 Fork 3).",
        duration_ms=duration_ms,
        details={"total_nodes": total, "ast_nodes": ast_extracted},        
    )
