"""
GraphBuilder — converts one ParsedFile intermediate envelope into a
CodeographKnowledgeGraph fragment (nodes + edges for a single .java file).

Sits between the parser layer (FileParserDispatcher) and the graph assembler.
The assembler handles cross-file concerns (DependsOnEdge, CallsResolvedEdge,
RelationEdge) after all files have been built individually.

Design decisions recorded in ADR-006.
"""

from __future__ import annotations

import logging
from typing import Any

from codeograph.graph.models.graph_schema import (
    AnnotationElement,
    AnnotationTypeNode,
    AutowiresEdge,
    BeanFactoryEdge,
    CallsUnresolvedEdge,
    ClassNode,
    CodeographKnowledgeGraph,
    ColumnMetadata,
    ContainsEdge,
    Edge,
    EnumNode,
    ExtractionMode,
    FieldNode,
    Generation,
    HttpMetadata,
    InjectionType,
    InterfaceNode,
    Kind,
    Method,
    MethodNode,
    Modifier,
    Modifier1,
    Modifier2,
    Modifier4,
    Modifier5,
    NameTypePair,
    Node,
    ParameterBinding,
    RecordNode,
    Stereotype,
)

# Alias to distinguish from parser-layer ParameterFact (TypedDict)
from codeograph.graph.models.graph_schema import ParameterFact as GraphParameterFact
from codeograph.parser.models import FieldFact, MethodFact, ParsedFile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Parser emits "ast" or "regex"; schema enum has "ast" and "regex_fallback".
# "signatures_only" is an ADR-005 token utilisation path — not emitted by the
# parser in v1, but mapped here for completeness.
_EXTRACTION_MODE: dict[str, ExtractionMode] = {
    "ast": ExtractionMode.ast,
    "regex": ExtractionMode.regex_fallback,
    "signatures_only": ExtractionMode.signatures_only,
}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _coerce_enum(enum_cls: type, value: str) -> Any:
    """
    Safely convert a string to an enum value.
    Logs a warning and returns None for unknown values rather than crashing.
    Unknown modifiers or unrecognised generation strategies are skipped so
    one bad annotation doesn't discard the entire node.
    """
    try:
        return enum_cls(value)
    except ValueError:
        logger.warning("GraphBuilder: unknown %s value %r — skipped", enum_cls.__name__, value)
        return None


def _parse_generation(raw: str | None) -> Generation | None:
    """
    Translate the parser's generation string to the schema Generation enum.

    The parser emits the full Java expression e.g. "GenerationType.IDENTITY".
    The schema enum uses the strategy name only e.g. "IDENTITY".
    Strips everything up to and including the last dot before lookup.
    """
    if raw is None:
        return None
    strategy = raw.split(".")[-1]
    return _coerce_enum(Generation, strategy)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


class GraphBuilder:
    """
    Converts one ParsedFile into a CodeographKnowledgeGraph fragment.

    Stateless between calls — accumulators are reset at the start of each
    build() invocation, so a single instance can be reused across the corpus.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, parsed_file: ParsedFile, module_id: str) -> CodeographKnowledgeGraph:
        """
        Build a graph fragment for one .java file.

        :param parsed_file: intermediate envelope from FileParserDispatcher.
        :param module_id:   module this file belongs to, e.g. "mod:order-service".
                            Source of the module → type ContainsEdge.
        :returns:           CodeographKnowledgeGraph with nodes and edges for
                            this file only. Cross-file edges are the assembler's job.
        """
        # Reset accumulators — keeps the instance reusable across files.
        self._nodes: list[Any] = []
        self._edges: list[Any] = []

        kind = parsed_file["kind"]

        if kind == "class":
            self._build_class(parsed_file, module_id)
        elif kind == "interface":
            self._build_interface(parsed_file, module_id)
        elif kind == "enum":
            self._build_enum(parsed_file, module_id)
        elif kind == "record":
            self._build_record(parsed_file, module_id)
        elif kind == "annotation_type":
            self._build_annotation_type(parsed_file, module_id)
        else:
            logger.warning(
                "GraphBuilder: unknown kind %r in %s — skipped",
                kind,
                parsed_file["source_file"],
            )

        return CodeographKnowledgeGraph(
            nodes=[Node(root=n) for n in self._nodes],
            edges=[Edge(root=e) for e in self._edges],
        )

    # ------------------------------------------------------------------
    # Level 0 — type declaration builders
    # ------------------------------------------------------------------

    def _build_class(self, parsed_file: ParsedFile, module_id: str) -> None:
        """
        Build ClassNode, emit module → class ContainsEdge.
        Delegate each field to _build_field, each method to _build_method.
        """
        class_id = parsed_file["id"]

        # Translate modifiers: ["public"] → [Modifier.public]
        # _coerce_enum filters unknown values rather than crashing.
        modifiers = [
            m for m in (_coerce_enum(Modifier, raw) for raw in parsed_file.get("modifiers", [])) if m is not None
        ]

        # Stereotype: "Service" → Stereotype.Service; None stays None.
        stereotype_raw = parsed_file.get("stereotype")
        stereotype = _coerce_enum(Stereotype, stereotype_raw) if stereotype_raw else None

        class_node = ClassNode(
            id=class_id,
            kind="class",
            name=parsed_file["name"],
            source_file=parsed_file["source_file"],
            line_range=parsed_file.get("line_range", [0, 0]),
            extraction_mode=_EXTRACTION_MODE.get(parsed_file["extraction_mode"], ExtractionMode.regex_fallback),
            modifiers=modifiers,
            annotations=parsed_file.get("annotations") or None,
            stereotype=stereotype,
            superclass=parsed_file.get("superclass"),
            implements=parsed_file.get("implements") or None,
            is_inner_class=parsed_file.get("is_inner_class"),
            table_name=parsed_file.get("table_name"),
            entry_point=parsed_file.get("entry_point"),
            wmc=parsed_file.get("wmc"),
            cbo=parsed_file.get("cbo"),
            lcom4=parsed_file.get("lcom4"),
        )
        self._nodes.append(class_node)

        self._edges.append(ContainsEdge(source=module_id, target=class_id, kind="contains"))

        for field in parsed_file.get("fields", []):
            self._build_field(field, class_id)

        for method in parsed_file.get("methods", []):
            self._build_method(method, class_id)

    def _build_interface(self, parsed_file: ParsedFile, module_id: str) -> None:
        """
        Build InterfaceNode, emit module → interface ContainsEdge.
        Delegate each method to _build_method.
        """
        interface_id = parsed_file["id"]

        interface_node = InterfaceNode(
            id=interface_id,
            kind="interface",
            name=parsed_file["name"],
            source_file=parsed_file["source_file"],
            line_range=parsed_file.get("line_range", [0, 0]),
            modifiers=[
                m for m in (_coerce_enum(Modifier1, raw) for raw in parsed_file.get("modifiers", [])) if m is not None
            ],
            annotations=parsed_file.get("annotations") or None,
            # extends_interfaces: hierarchy stored as strings; no edge emitted in v1
            # (ExtendsEdge deferred to v1.1 per ADR-006 amendment).
            extends_interfaces=parsed_file.get("extends_interfaces") or None,
        )
        self._nodes.append(interface_node)

        self._edges.append(ContainsEdge(source=module_id, target=interface_id, kind="contains"))

        for method in parsed_file.get("methods", []):
            self._build_method(method, interface_id)

    def _build_enum(self, parsed_file: ParsedFile, module_id: str) -> None:
        """
        Build EnumNode, emit module → enum ContainsEdge.
        """
        enum_id = parsed_file["id"]

        enum_node = EnumNode(
            id=enum_id,
            kind="enum",
            name=parsed_file["name"],
            source_file=parsed_file["source_file"],
            line_range=parsed_file.get("line_range", [0, 0]),
            modifiers=[
                m for m in (_coerce_enum(Modifier2, raw) for raw in parsed_file.get("modifiers", [])) if m is not None
            ],
            # constants is required by the schema; default to [] if parser omits it
            # (shouldn't happen for a well-formed enum, but guards against crashes).
            constants=parsed_file.get("constants") or [],
            annotations=parsed_file.get("annotations") or None,
            implements=parsed_file.get("implements") or None,
        )
        self._nodes.append(enum_node)

        self._edges.append(ContainsEdge(source=module_id, target=enum_id, kind="contains"))

    def _build_record(self, parsed_file: ParsedFile, module_id: str) -> None:
        """
        Build RecordNode, emit module → record ContainsEdge.
        """
        record_id = parsed_file["id"]

        # components: list[{"name": str, "type": str}] from the parser
        components = [NameTypePair(name=c["name"], type=c["type"]) for c in parsed_file.get("components", [])]

        record_node = RecordNode(
            id=record_id,
            kind="record",
            name=parsed_file["name"],
            source_file=parsed_file["source_file"],
            line_range=parsed_file.get("line_range", [0, 0]),
            components=components,
            annotations=parsed_file.get("annotations") or None,
            implements=parsed_file.get("implements") or None,
        )
        self._nodes.append(record_node)

        self._edges.append(ContainsEdge(source=module_id, target=record_id, kind="contains"))

    def _build_annotation_type(self, parsed_file: ParsedFile, module_id: str) -> None:
        """
        Build AnnotationTypeNode, emit module → annotation_type ContainsEdge.
        """
        annotation_type_id = parsed_file["id"]

        # elements: list[{"name": str, "type": str, "default_value": str|None}]
        raw_elements = parsed_file.get("elements") or []
        elements = [
            AnnotationElement(
                name=e["name"],
                type=e["type"],
                default_value=e.get("default_value"),
            )
            for e in raw_elements
        ] or None  # schema allows null when no elements declared

        annotation_type_node = AnnotationTypeNode(
            id=annotation_type_id,
            kind="annotation_type",
            name=parsed_file["name"],
            source_file=parsed_file["source_file"],
            line_range=parsed_file.get("line_range", [0, 0]),
            modifiers=[
                m for m in (_coerce_enum(Modifier2, raw) for raw in parsed_file.get("modifiers", [])) if m is not None
            ],
            elements=elements,
        )
        self._nodes.append(annotation_type_node)

        self._edges.append(ContainsEdge(source=module_id, target=annotation_type_id, kind="contains"))

    # ------------------------------------------------------------------
    # Level 1 — field builder
    # ------------------------------------------------------------------

    def _build_field(self, field: FieldFact, class_id: str) -> None:
        """
        Build FieldNode, emit class → field ContainsEdge.
        Inline: emit AutowiresEdge if field is autowired.
        """
        # Translate generation: "GenerationType.IDENTITY" → Generation.IDENTITY
        generation = _parse_generation(field.get("generation"))

        # Translate column dict → ColumnMetadata if present
        column_dict = field.get("column")
        column = ColumnMetadata(**column_dict) if column_dict else None

        field_node = FieldNode(
            id=field["id"],
            kind="field",
            name=field["name"],
            type=field["type"],
            modifiers=[
                m for m in (_coerce_enum(Modifier5, raw) for raw in field.get("modifiers", [])) if m is not None
            ],
            annotations=field.get("annotations") or None,
            is_autowired=field.get("is_autowired"),
            is_id=field.get("is_id"),
            generation=generation,
            column=column,
            constraints=field.get("constraints") or None,
        )
        self._nodes.append(field_node)

        self._edges.append(ContainsEdge(source=class_id, target=field["id"], kind="contains"))

        if field.get("is_autowired"):
            injection_raw = field.get("injection_type")
            self._edges.append(
                AutowiresEdge(
                    source=field["id"],
                    target=field["type"],
                    kind="autowires",
                    injection_type=(_coerce_enum(InjectionType, injection_raw) if injection_raw else None),
                    qualifier=field.get("qualifier"),
                )
            )

    # ------------------------------------------------------------------
    # Level 1 — method builder
    # ------------------------------------------------------------------

    def _build_method(self, method: MethodFact, class_id: str) -> None:
        """
        Build MethodNode, emit class → method ContainsEdge.
        Inline: emit BeanFactoryEdge if @Bean method.
        Delegates: _build_call_edges for raw call expressions.
        """
        parameters = [self._embed_parameter(p) for p in method.get("parameters", [])]

        # Translate http_metadata dict → HttpMetadata if present.
        # Schema HttpMetadata.method is non-optional — skip entirely when
        # the parser emits null (e.g. @RequestMapping without method attribute).
        http_metadata: HttpMetadata | None = None
        http_dict = method.get("http_metadata")
        if http_dict:
            method_str = http_dict.get("method")
            http_method = _coerce_enum(Method, method_str) if method_str else None
            if http_method is not None:
                http_metadata = HttpMetadata(
                    method=http_method,
                    path=http_dict.get("path", ""),
                )
            else:
                logger.debug(
                    "GraphBuilder: %s has @RequestMapping without method attribute — http_metadata omitted",
                    method["id"],
                )

        method_node = MethodNode(
            id=method["id"],
            kind="method",
            name=method["name"],
            return_type=method["return_type"],
            modifiers=[
                m for m in (_coerce_enum(Modifier4, raw) for raw in method.get("modifiers", [])) if m is not None
            ],
            annotations=method.get("annotations") or None,
            is_constructor=method["is_constructor"],
            line_range=method.get("line_range", [0, 0]),
            parameters=parameters,
            is_bean_factory=method.get("is_bean_factory"),
            exception_handler=method.get("exception_handler"),
            response_body=method.get("response_body"),
            # response_status: parser emits a string like "HttpStatus.CREATED";
            # schema expects int | None. Int resolution needs a symbol table —
            # deferred to v1.1. Always None in v1.
            response_status=None,
            http_metadata=http_metadata,
            cyclomatic_complexity=method.get("cyclomatic_complexity"),
            cognitive_complexity=method.get("cognitive_complexity"),
            method_loc=method.get("method_loc"),
        )
        self._nodes.append(method_node)

        self._edges.append(ContainsEdge(source=class_id, target=method["id"], kind="contains"))

        if method.get("is_bean_factory"):
            self._edges.append(
                BeanFactoryEdge(
                    source=method["id"],
                    target=method["return_type"],
                    kind="bean_factory",
                )
            )

        self._build_call_edges(method["id"], method.get("calls", []))

    # ------------------------------------------------------------------
    # Level 2 — parameter embedding (not a graph node)
    # ------------------------------------------------------------------

    def _embed_parameter(self, param: dict[str, Any]) -> GraphParameterFact:
        """
        Convert one parser ParameterFact dict into the schema ParameterFact.
        Not added to self._nodes — embedded directly in MethodNode.parameters.
        """
        # Translate binding dict → ParameterBinding if present.
        # Parser emits {"kind": "path", "name": "id", "required": true} or null.
        binding: ParameterBinding | None = None
        binding_dict = param.get("binding")
        if binding_dict:
            kind_raw = binding_dict.get("kind")
            kind = _coerce_enum(Kind, kind_raw) if kind_raw else None
            if kind is not None:
                binding = ParameterBinding(
                    kind=kind,
                    name=binding_dict.get("name"),
                    required=binding_dict.get("required"),
                )
            else:
                logger.warning(
                    "GraphBuilder: parameter %r has binding with unknown kind %r — binding omitted",
                    param.get("name"),
                    kind_raw,
                )

        # ParameterFact has extra="forbid" and no populate_by_name=True, so the
        # constructor only accepts the alias key "validate", not the Python
        # attribute name "validate_". model_validate() with a dict is the
        # clean way to pass alias-keyed fields programmatically.
        return GraphParameterFact.model_validate(
            {
                "name": param["name"],
                "type": param["type"],
                "validate": param.get("validate"),
                "constraints": param.get("constraints") or None,
                "binding": binding,
            }
        )

    # ------------------------------------------------------------------
    # Edge helpers
    # ------------------------------------------------------------------

    def _build_call_edges(self, method_id: str, calls: list[str]) -> None:
        """
        Emit one CallsUnresolvedEdge per raw call expression.
        All calls are unresolved at builder stage — resolution to
        CallsResolvedEdge requires a corpus-wide method ID index,
        which the assembler holds.
        """
        for call in calls:
            self._edges.append(
                CallsUnresolvedEdge(
                    source=method_id,
                    target=call,
                    kind="calls_unresolved",
                    raw_call_expr=call,
                )
            )
