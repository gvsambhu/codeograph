"""
GraphAssembler — merges per-file CodeographKnowledgeGraph fragments into a
single corpus-wide graph and adds cross-file edges.

Sits between GraphBuilder (per-file) and GraphWriter (serialization).

Cross-file edges added here:
  DependsOnEdge     — type-level dependencies from imports, field types,
                      param types, return types, superclass, implements
  CallsResolvedEdge — method calls where the callee exists in the corpus;
                      promoted from CallsUnresolvedEdge
  RelationEdge      — JPA @OneToMany / @ManyToOne / @OneToOne / @ManyToMany

Design decisions recorded in ADR-006.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from codeograph.graph.models.graph_schema import (
    CallsResolvedEdge,
    Cardinality,
    CodeographKnowledgeGraph,
    DependsOnEdge,
    Edge,
    Node,
    RelationEdge,
)
from codeograph.parser.models import ParsedFile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# JPA relation annotation simple name → Cardinality enum value
_JPA_CARDINALITY: dict[str, Cardinality] = {
    "OneToOne": Cardinality.ONE_TO_ONE,
    "OneToMany": Cardinality.ONE_TO_MANY,
    "ManyToOne": Cardinality.MANY_TO_ONE,
    "ManyToMany": Cardinality.MANY_TO_MANY,
}

# Generic collection wrappers stripped when resolving RelationEdge targets
_COLLECTION_WRAPPERS = ("List<", "Set<", "Collection<", "Optional<")


# ---------------------------------------------------------------------------
# Assembler
# ---------------------------------------------------------------------------


class GraphAssembler:
    """
    Merges per-file graph fragments and adds corpus-wide cross-file edges.

    Stateless between calls — all working state is local to assemble().
    A single instance can be reused across corpus runs.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assemble(
        self,
        corpus: list[tuple[ParsedFile, CodeographKnowledgeGraph]],
    ) -> CodeographKnowledgeGraph:
        """
        Merge all per-file fragments and add cross-file edges.

        :param corpus: list of (parsed_file, fragment) pairs — one per .java file,
                       produced by GraphBuilder.build().
        :returns:      single unified CodeographKnowledgeGraph containing all nodes,
                       all intra-file edges, and all cross-file edges.
        """
        # Step 1 — flatten every fragment into two mutable lists
        all_nodes, all_edges = self._merge_fragments(corpus)
        logger.debug(
            "GraphAssembler: merged %d nodes, %d edges from %d files",
            len(all_nodes),
            len(all_edges),
            len(corpus),
        )

        # Step 2 — build corpus-wide lookup structures (single pass over nodes)
        node_id_set = self._build_node_id_set(all_nodes)
        method_index = self._build_method_index(all_nodes)
        field_index = self._build_field_index(all_nodes)
        param_index = self._build_param_index(all_nodes)
        import_maps = self._build_import_maps(corpus)

        # Step 3 — per-file cross-file edge addition
        # Dedup sets track emitted pairs so multiple sources don't repeat edges.
        dep_pairs: set[tuple[str, str]] = set()
        rel_pairs: set[tuple[str, str, str]] = set()

        for parsed_file, _ in corpus:
            import_map = import_maps.get(parsed_file["id"], {})
            self._add_dep_edges(
                parsed_file,
                import_map,
                node_id_set,
                all_edges,
                dep_pairs,
            )
            if parsed_file["kind"] == "class":
                self._add_relation_edges(
                    parsed_file,
                    import_map,
                    node_id_set,
                    all_edges,
                    rel_pairs,
                )

        # Step 4 — promote CallsUnresolvedEdge → CallsResolvedEdge where possible
        self._convert_unresolved_to_resolved(
            all_edges,
            field_index,
            param_index,
            method_index,
            import_maps,
        )

        # Step 5 — safety dedup and return
        return CodeographKnowledgeGraph(
            nodes=self._dedup_nodes(all_nodes),
            edges=self._dedup_edges(all_edges),
        )

    # ------------------------------------------------------------------
    # Step 1 — merge fragments
    # ------------------------------------------------------------------

    def _merge_fragments(
        self,
        corpus: list[tuple[ParsedFile, CodeographKnowledgeGraph]],
    ) -> tuple[list[Node], list[Edge]]:
        """
        Concatenate nodes and edges from every per-file fragment.
        Node IDs are globally unique (FQCN-based) so no dedup is needed here.
        Edge dedup is handled later by emitted-pair guards and _dedup_edges.
        """
        all_nodes: list[Node] = []
        all_edges: list[Edge] = []
        for _, fragment in corpus:
            all_nodes.extend(fragment.nodes)
            all_edges.extend(fragment.edges)
        return all_nodes, all_edges

    # ------------------------------------------------------------------
    # Step 2 — index builders
    # ------------------------------------------------------------------

    def _build_node_id_set(self, nodes: list[Node]) -> set[str]:
        """
        Flat set of every node ID in the corpus.
        Used as a corpus-membership filter — if a resolved FQCN is not in
        this set, it is an external library type and should be skipped.
        """
        return {node.root.id for node in nodes}  # type: ignore[union-attr]

    def _build_method_index(
        self,
        nodes: list[Node],
    ) -> dict[str, dict[str, list[str]]]:
        """
        class_fqcn → method_simple_name → [method_id, ...]

        Grouped by name rather than full signature because raw call expressions
        carry argument *values*, not types. Overloads produce multiple candidates;
        all are emitted as CallsResolvedEdge entries (signature disambiguation
        requires a symbol solver — deferred to v1.1).
        """
        index: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        for node in nodes:
            if node.root.kind == "method":  # type: ignore[union-attr]
                method_id = node.root.id  # type: ignore[union-attr]
                class_fqcn = method_id.split("#")[0]
                method_name = node.root.name  # type: ignore[union-attr]
                index[class_fqcn][method_name].append(method_id)
        return index

    def _build_field_index(self, nodes: list[Node]) -> dict[str, list[Any]]:
        """
        class_fqcn → [FieldNode model, ...]

        Field ID format: {class_fqcn}.{field_name}
        The class FQCN is recovered by stripping the trailing ".{field_name}"
        segment using the known field name from FieldNode.name.
        """
        index: dict[str, list[Any]] = defaultdict(list)
        for node in nodes:
            if node.root.kind == "field":  # type: ignore[union-attr]
                field_node = node.root  # type: ignore[union-attr]
                field_id = field_node.id
                field_name = field_node.name
                class_fqcn = field_id[: -(len(field_name) + 1)]
                index[class_fqcn].append(field_node)
        return index

    def _build_param_index(self, nodes: list[Node]) -> dict[str, list[Any]]:
        """
        method_id → [ParameterFact, ...]

        Parameters are embedded inside MethodNode (not separate graph nodes).
        Extracted here so call resolution can look up parameter types by
        variable name without re-traversing the graph.
        """
        index: dict[str, list[Any]] = {}
        for node in nodes:
            if node.root.kind == "method":  # type: ignore[union-attr]
                index[node.root.id] = node.root.parameters or []  # type: ignore[union-attr]
        return index

    def _build_import_maps(
        self,
        corpus: list[tuple[ParsedFile, CodeographKnowledgeGraph]],
    ) -> dict[str, dict[str, str]]:
        """
        class_fqcn → {simple_name: fqcn}

        Built from parsed_file["imports"] for each file. Used by all three
        cross-file edge builders to resolve simple type names to FQCNs without
        re-reading the source.

        Example for OwnerService:
          "Owner"            → "com.example.model.Owner"
          "OwnerRepository"  → "com.example.repository.OwnerRepository"
          "Service"          → "org.springframework.stereotype.Service"
        """
        maps: dict[str, dict[str, str]] = {}
        for parsed_file, _ in corpus:
            maps[parsed_file["id"]] = {fqcn.split(".")[-1]: fqcn for fqcn in parsed_file.get("imports", [])}
        return maps

    # ------------------------------------------------------------------
    # Step 3a — DependsOnEdge
    # ------------------------------------------------------------------

    def _add_dep_edges(
        self,
        parsed_file: ParsedFile,
        import_map: dict[str, str],
        node_id_set: set[str],
        all_edges: list[Edge],
        emitted: set[tuple[str, str]],
    ) -> None:
        """
        Emit DependsOnEdge for every corpus type this file depends on.

        Six sources are checked in order. All funnel through maybe_emit(),
        which enforces three invariants: target must be in corpus, target
        must differ from source, and the (source, target) pair must not
        have been emitted already.

        Sources:
          1. imports list               — already FQCN; fastest path
          2. field declared types       — simple name via import_map
          3. method return types        — simple name via import_map
          4. method parameter types     — simple name via import_map
          5. superclass                 — simple name or FQCN
          6. implements / extends_interfaces — simple names or FQCNs
        """
        source = parsed_file["id"]

        def maybe_emit(target: str | None) -> None:
            if not target:
                return
            if target not in node_id_set:
                return
            if target == source:
                return
            pair = (source, target)
            if pair in emitted:
                return
            emitted.add(pair)
            all_edges.append(
                Edge(
                    root=DependsOnEdge(
                        source=source,
                        target=target,
                        kind="depends_on",
                    )
                )
            )

        # Source 1 — imports (FQCNs directly)
        for fqcn in parsed_file.get("imports", []):
            maybe_emit(fqcn)

        # Source 2 — field declared types
        for field in parsed_file.get("fields", []):
            maybe_emit(import_map.get(field["type"]))

        # Source 3 & 4 — method return types and parameter types
        for method in parsed_file.get("methods", []):
            maybe_emit(import_map.get(method["return_type"]))
            for param in method.get("parameters", []):
                maybe_emit(import_map.get(param["type"]))

        # Source 5 — superclass (may arrive as simple name or FQCN)
        superclass = parsed_file.get("superclass")
        if superclass:
            maybe_emit(import_map.get(superclass, superclass))

        # Source 6 — implements (class / enum) and extends_interfaces (interface)
        for iface in parsed_file.get("implements") or []:
            maybe_emit(import_map.get(iface, iface))
        for iface in parsed_file.get("extends_interfaces") or []:
            maybe_emit(import_map.get(iface, iface))

    # ------------------------------------------------------------------
    # Step 3b — RelationEdge
    # ------------------------------------------------------------------

    def _add_relation_edges(
        self,
        parsed_file: ParsedFile,
        import_map: dict[str, str],
        node_id_set: set[str],
        all_edges: list[Edge],
        emitted: set[tuple[str, str, str]],
    ) -> None:
        """
        Emit RelationEdge for each field carrying a JPA relationship annotation.

        Cardinality is determined from the annotation name. The target FQCN is
        resolved by stripping collection wrappers from the field type and looking
        up the resulting simple name in the file's import_map.

        join_column is always None in v1 — JavaParser does not extract @JoinColumn
        attribute values into FieldFact (v1.1 enhancement).
        """
        source = parsed_file["id"]

        for field in parsed_file.get("fields", []):
            annotations = field.get("annotations", [])
            cardinality = next(
                (_JPA_CARDINALITY[a] for a in annotations if a in _JPA_CARDINALITY),
                None,
            )
            if cardinality is None:
                continue

            raw_type = self._strip_collection_wrapper(field["type"])
            target_fqcn = import_map.get(raw_type)

            if not target_fqcn or target_fqcn not in node_id_set:
                logger.debug(
                    "GraphAssembler: RelationEdge skipped — %s.%s target type %r not in corpus",
                    source,
                    field["name"],
                    raw_type,
                )
                continue

            triple = (source, target_fqcn, cardinality.value)
            if triple in emitted:
                continue
            emitted.add(triple)

            all_edges.append(
                Edge(
                    root=RelationEdge(
                        source=source,
                        target=target_fqcn,
                        kind="relation",
                        cardinality=cardinality,
                        join_column=None,
                    )
                )
            )

    # ------------------------------------------------------------------
    # Step 4 — CallsUnresolvedEdge → CallsResolvedEdge promotion
    # ------------------------------------------------------------------

    def _convert_unresolved_to_resolved(
        self,
        all_edges: list[Edge],
        field_index: dict[str, list[Any]],
        param_index: dict[str, list[Any]],
        method_index: dict[str, dict[str, list[str]]],
        import_maps: dict[str, dict[str, str]],
    ) -> None:
        """
        Walk every CallsUnresolvedEdge. Where the callee type can be determined
        and maps to a known corpus method, promote to CallsResolvedEdge and drop
        the unresolved edge.

        Callee type resolution — four sub-cases in priority order:
          1. No callee variable / 'this.' prefix → self-call; class B = class A
          2. Callee starts with uppercase         → static call; class B via import_map
          3. Callee matches a field name          → field type via import_map
          4. Callee matches a method param name   → param type via import_map

        Overloaded methods (same name, multiple signatures) each produce a
        separate CallsResolvedEdge. Full signature disambiguation requires a
        symbol solver — deferred to v1.1.

        Local variable callees (case not covered by 1–4) remain unresolved.
        """
        to_remove: list[int] = []
        to_add: list[Edge] = []

        for idx, edge in enumerate(all_edges):
            if edge.root.kind != "calls_unresolved":  # type: ignore[union-attr]
                continue

            source = edge.root.source  # type: ignore[union-attr]
            raw_expr = (  # type: ignore[union-attr]
                edge.root.raw_call_expr or edge.root.target
            )

            class_a = source.split("#")[0]
            import_map = import_maps.get(class_a, {})
            callee_var, method_name = self._parse_call_expr(raw_expr)

            class_b: str | None = None

            if callee_var is None:
                # Case 1 — self-call (no dot / 'this.' stripped)
                class_b = class_a

            elif callee_var[0].isupper():
                # Case 2 — static call; callee is a class name
                class_b = import_map.get(callee_var)

            else:
                # Case 3 — check field index
                field = next(
                    (f for f in field_index.get(class_a, []) if f.name == callee_var),
                    None,
                )
                if field:
                    class_b = import_map.get(field.type)
                else:
                    # Case 4 — check param index
                    param = next(
                        (p for p in param_index.get(source, []) if p.name == callee_var),
                        None,
                    )
                    if param:
                        class_b = import_map.get(param.type)

            if not class_b:
                logger.debug(
                    "GraphAssembler: %r from %s — callee %r type not resolvable",
                    raw_expr,
                    source,
                    callee_var,
                )
                continue

            candidates = method_index.get(class_b, {}).get(method_name, [])
            if not candidates:
                logger.debug(
                    "GraphAssembler: %r from %s — method %r not found on %s",
                    raw_expr,
                    source,
                    method_name,
                    class_b,
                )
                continue

            to_remove.append(idx)
            for target_id in candidates:
                to_add.append(
                    Edge(
                        root=CallsResolvedEdge(
                            source=source,
                            target=target_id,
                            kind="calls_resolved",
                        )
                    )
                )

        # Remove promoted edges in reverse order to preserve list indices
        for idx in reversed(to_remove):
            all_edges.pop(idx)
        all_edges.extend(to_add)

    # ------------------------------------------------------------------
    # Step 5 — dedup
    # ------------------------------------------------------------------

    def _dedup_nodes(self, nodes: list[Node]) -> list[Node]:
        """
        Remove duplicate nodes by ID. Preserves first-seen order.
        Duplicates should not occur (node IDs are globally unique by design);
        this guard makes the merge step robust against malformed input.
        """
        seen: set[str] = set()
        result: list[Node] = []
        for node in nodes:
            nid = node.root.id  # type: ignore[union-attr]
            if nid not in seen:
                seen.add(nid)
                result.append(node)
        return result

    def _dedup_edges(self, edges: list[Edge]) -> list[Edge]:
        """
        Remove duplicate edges by (kind, source, target). Preserves first-seen order.
        DependsOnEdge and RelationEdge are already guarded by emitted-pair sets
        during construction; this is a final safety net covering all edge types.
        """
        seen: set[tuple[str, str, str]] = set()
        result: list[Edge] = []
        for edge in edges:
            key = (
                edge.root.kind,  # type: ignore[union-attr]
                edge.root.source,  # type: ignore[union-attr]
                edge.root.target,  # type: ignore[union-attr]
            )
            if key not in seen:
                seen.add(key)
                result.append(edge)
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_call_expr(expr: str) -> tuple[str | None, str]:
        """
        Extract (callee_variable, method_name) from a raw call expression.

        Examples:
          "ownerRepo.findById(id)"   → ("ownerRepo", "findById")
          "findById(id)"             → (None,         "findById")
          "this.findById(id)"        → (None,         "findById")
          "Collections.sort(list)"   → ("Collections", "sort")
          "save(owner)"              → (None,          "save")
        """
        # Take the part before the first '(' (discards arguments)
        before_paren = expr.split("(")[0] if "(" in expr else expr

        # 'this.' is a self-call — treat as no callee variable
        if before_paren.startswith("this."):
            before_paren = before_paren[5:]

        if "." in before_paren:
            callee, method = before_paren.rsplit(".", 1)
            return callee.strip(), method.strip()

        return None, before_paren.strip()

    @staticmethod
    def _strip_collection_wrapper(type_str: str) -> str:
        """
        Strip a Java collection generic wrapper to obtain the element type.

        Examples:
          "List<Pet>"        → "Pet"
          "Set<Item>"        → "Item"
          "Collection<User>" → "User"
          "Optional<Owner>"  → "Owner"
          "Owner"            → "Owner"
        """
        for wrapper in _COLLECTION_WRAPPERS:
            if type_str.startswith(wrapper) and type_str.endswith(">"):
                return type_str[len(wrapper) : -1]
        return type_str
