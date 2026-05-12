"""
Unit tests for GraphAssembler.

Static helpers (_parse_call_expr, _strip_collection_wrapper) are tested
directly. Index builders and edge-addition methods are tested through the
public assemble() method using minimal two-file corpora.
"""

from codeograph.graph.graph_assembler import GraphAssembler
from codeograph.graph.graph_builder import GraphBuilder
from codeograph.graph.models.graph_schema import (
    CallsResolvedEdge,
    CallsUnresolvedEdge,
    Cardinality,
    DependsOnEdge,
    RelationEdge,
)

# ---------------------------------------------------------------------------
# Minimal ParsedFile factories
# ---------------------------------------------------------------------------

MODULE_ID = "mod:core"


def _class_pf(**kwargs):
    base = {
        "kind": "class",
        "id": "com.example.A",
        "name": "A",
        "source_file": "src/A.java",
        "extraction_mode": "ast",
        "annotations": [],
        "imports": [],
        "line_range": [1, 10],
        "modifiers": ["public"],
        "stereotype": None,
        "superclass": None,
        "implements": [],
        "is_inner_class": False,
        "table_name": None,
        "entry_point": False,
        "wmc": None,
        "cbo": None,
        "lcom4": None,
        "fields": [],
        "methods": [],
    }
    base.update(kwargs)
    return base


def _field(**kwargs):
    base = {
        "id": "com.example.A.dep",
        "name": "dep",
        "type": "B",
        "modifiers": ["private"],
        "annotations": [],
        "is_autowired": False,
        "is_id": False,
        "injection_type": None,
        "qualifier": None,
        "generation": None,
        "column": None,
        "constraints": [],
    }
    base.update(kwargs)
    return base


def _method(**kwargs):
    base = {
        "id": "com.example.A#doIt()",
        "name": "doIt",
        "return_type": "void",
        "modifiers": ["public"],
        "annotations": [],
        "is_constructor": False,
        "line_range": [5, 8],
        "parameters": [],
        "is_bean_factory": False,
        "exception_handler": False,
        "response_body": False,
        "response_status": None,
        "http_metadata": None,
        "cyclomatic_complexity": None,
        "cognitive_complexity": None,
        "method_loc": None,
        "calls": [],
    }
    base.update(kwargs)
    return base


def _build_fragment(parsed_file):
    """Build a graph fragment from a ParsedFile using GraphBuilder."""
    return GraphBuilder().build(parsed_file, MODULE_ID)


def _edges_of(graph, cls):
    return [e.root for e in graph.edges if isinstance(e.root, cls)]


# ---------------------------------------------------------------------------
# Static helper tests — no corpus needed
# ---------------------------------------------------------------------------


class TestParseCallExpr:
    def test_field_callee(self):
        callee, method = GraphAssembler._parse_call_expr("repo.save(entity)")
        assert callee == "repo"
        assert method == "save"

    def test_self_call_no_dot(self):
        callee, method = GraphAssembler._parse_call_expr("findById(id)")
        assert callee is None
        assert method == "findById"

    def test_this_prefix_treated_as_self(self):
        callee, method = GraphAssembler._parse_call_expr("this.findById(id)")
        assert callee is None
        assert method == "findById"

    def test_static_call_uppercase_callee(self):
        callee, method = GraphAssembler._parse_call_expr("Collections.sort(list)")
        assert callee == "Collections"
        assert method == "sort"

    def test_no_parens(self):
        callee, method = GraphAssembler._parse_call_expr("repo.save")
        assert callee == "repo"
        assert method == "save"

    def test_chained_takes_last_dot_before_paren(self):
        callee, method = GraphAssembler._parse_call_expr("repo.findById(id).orElseThrow()")
        # Before first '(' → "repo.findById"; rsplit on last '.'
        assert callee == "repo"
        assert method == "findById"


class TestStripCollectionWrapper:
    def test_list_wrapper(self):
        assert GraphAssembler._strip_collection_wrapper("List<Pet>") == "Pet"

    def test_set_wrapper(self):
        assert GraphAssembler._strip_collection_wrapper("Set<Item>") == "Item"

    def test_collection_wrapper(self):
        assert GraphAssembler._strip_collection_wrapper("Collection<User>") == "User"

    def test_optional_wrapper(self):
        assert GraphAssembler._strip_collection_wrapper("Optional<Owner>") == "Owner"

    def test_no_wrapper_unchanged(self):
        assert GraphAssembler._strip_collection_wrapper("Owner") == "Owner"

    def test_nested_generic_not_stripped(self):
        # "Map<String,List<Pet>>" — not in _COLLECTION_WRAPPERS; returned as-is
        result = GraphAssembler._strip_collection_wrapper("Map<String,List<Pet>>")
        assert result == "Map<String,List<Pet>>"


# ---------------------------------------------------------------------------
# DependsOnEdge tests
# ---------------------------------------------------------------------------


class TestAddDepEdges:
    def _two_class_corpus(self, a_imports=None, a_fields=None):
        """A depends on B; B is a separate class in the corpus."""
        pf_a = _class_pf(
            id="com.example.A",
            imports=a_imports or ["com.example.B"],
            fields=a_fields or [],
        )
        pf_b = _class_pf(id="com.example.B", name="B")

        corpus = [
            (pf_a, _build_fragment(pf_a)),
            (pf_b, _build_fragment(pf_b)),
        ]
        return GraphAssembler().assemble(corpus)

    def test_dep_edge_from_import(self):
        graph = self._two_class_corpus()
        dep_edges = _edges_of(graph, DependsOnEdge)
        assert any(e.source == "com.example.A" and e.target == "com.example.B" for e in dep_edges)

    def test_external_import_skipped(self):
        pf_a = _class_pf(
            id="com.example.A",
            imports=["com.example.B", "org.springframework.stereotype.Service"],
        )
        pf_b = _class_pf(id="com.example.B", name="B")
        corpus = [(pf_a, _build_fragment(pf_a)), (pf_b, _build_fragment(pf_b))]
        graph = GraphAssembler().assemble(corpus)
        dep_edges = _edges_of(graph, DependsOnEdge)
        targets = {e.target for e in dep_edges if e.source == "com.example.A"}
        assert "org.springframework.stereotype.Service" not in targets

    def test_dep_edge_from_field_type(self):
        field = _field(id="com.example.A.b", name="b", type="B")
        pf_a = _class_pf(
            id="com.example.A",
            imports=["com.example.B"],
            fields=[field],
        )
        pf_b = _class_pf(id="com.example.B", name="B")
        corpus = [(pf_a, _build_fragment(pf_a)), (pf_b, _build_fragment(pf_b))]
        graph = GraphAssembler().assemble(corpus)
        dep_edges = _edges_of(graph, DependsOnEdge)
        # Both import and field type resolve to same target — only one edge emitted
        assert sum(1 for e in dep_edges if e.source == "com.example.A" and e.target == "com.example.B") == 1

    def test_no_self_dep_edge(self):
        pf_a = _class_pf(id="com.example.A", imports=["com.example.A"])
        corpus = [(pf_a, _build_fragment(pf_a))]
        graph = GraphAssembler().assemble(corpus)
        dep_edges = _edges_of(graph, DependsOnEdge)
        assert all(e.source != e.target for e in dep_edges)

    def test_dep_from_superclass(self):
        pf_a = _class_pf(
            id="com.example.Child",
            name="Child",
            imports=["com.example.Base"],
            superclass="Base",
        )
        pf_b = _class_pf(id="com.example.Base", name="Base")
        corpus = [(pf_a, _build_fragment(pf_a)), (pf_b, _build_fragment(pf_b))]
        graph = GraphAssembler().assemble(corpus)
        dep_edges = _edges_of(graph, DependsOnEdge)
        assert any(e.source == "com.example.Child" and e.target == "com.example.Base" for e in dep_edges)

    def test_dep_from_implements(self):
        pf_a = _class_pf(
            id="com.example.Impl",
            name="Impl",
            imports=["com.example.IFoo"],
            implements=["IFoo"],
        )
        pf_b = _class_pf(id="com.example.IFoo", name="IFoo")
        corpus = [(pf_a, _build_fragment(pf_a)), (pf_b, _build_fragment(pf_b))]
        graph = GraphAssembler().assemble(corpus)
        dep_edges = _edges_of(graph, DependsOnEdge)
        assert any(e.source == "com.example.Impl" and e.target == "com.example.IFoo" for e in dep_edges)


# ---------------------------------------------------------------------------
# RelationEdge tests
# ---------------------------------------------------------------------------


class TestAddRelationEdges:
    def _corpus_with_relation(self, annotation, field_type):
        field = _field(
            id="com.example.Owner.pets",
            name="pets",
            type=field_type,
            annotations=[annotation],
        )
        pf_owner = _class_pf(
            id="com.example.Owner",
            name="Owner",
            imports=["com.example.Pet"],
            fields=[field],
        )
        pf_pet = _class_pf(id="com.example.Pet", name="Pet")
        corpus = [
            (pf_owner, _build_fragment(pf_owner)),
            (pf_pet, _build_fragment(pf_pet)),
        ]
        return GraphAssembler().assemble(corpus)

    def test_one_to_many_emitted(self):
        graph = self._corpus_with_relation("OneToMany", "List<Pet>")
        rel_edges = _edges_of(graph, RelationEdge)
        assert len(rel_edges) == 1
        assert rel_edges[0].source == "com.example.Owner"
        assert rel_edges[0].target == "com.example.Pet"
        assert rel_edges[0].cardinality == Cardinality.ONE_TO_MANY

    def test_many_to_one_emitted(self):
        graph = self._corpus_with_relation("ManyToOne", "Pet")
        rel_edges = _edges_of(graph, RelationEdge)
        assert rel_edges[0].cardinality == Cardinality.MANY_TO_ONE

    def test_collection_wrapper_stripped(self):
        graph = self._corpus_with_relation("OneToMany", "Set<Pet>")
        rel_edges = _edges_of(graph, RelationEdge)
        assert rel_edges[0].target == "com.example.Pet"

    def test_join_column_always_none_in_v1(self):
        graph = self._corpus_with_relation("ManyToOne", "Pet")
        rel_edges = _edges_of(graph, RelationEdge)
        assert rel_edges[0].join_column is None

    def test_target_not_in_corpus_skipped(self):
        field = _field(
            id="com.example.Owner.pets",
            name="pets",
            type="List<ExternalEntity>",
            annotations=["OneToMany"],
        )
        pf_owner = _class_pf(
            id="com.example.Owner",
            name="Owner",
            imports=[],  # ExternalEntity not imported → not resolvable
            fields=[field],
        )
        corpus = [(pf_owner, _build_fragment(pf_owner))]
        graph = GraphAssembler().assemble(corpus)
        assert len(_edges_of(graph, RelationEdge)) == 0


# ---------------------------------------------------------------------------
# CallsResolvedEdge tests
# ---------------------------------------------------------------------------


class TestConvertUnresolvedToResolved:
    def _corpus(self, caller_calls=None, callee_field=None, callee_param=None):
        """
        Two-class corpus:
          - A has a field of type B (optional) and a method that calls B's method
          - B has a method named 'process'
        """
        fields = []
        if callee_field:
            fields = [
                _field(
                    id="com.example.A.b",
                    name="b",
                    type="B",
                    annotations=[],
                )
            ]

        params = []
        if callee_param:
            params = [{"name": "b", "type": "B", "validate": False, "constraints": [], "binding": None}]

        method_a = _method(
            id="com.example.A#doIt()",
            name="doIt",
            calls=caller_calls or [],
            parameters=params,
        )
        pf_a = _class_pf(
            id="com.example.A",
            imports=["com.example.B"],
            fields=fields,
            methods=[method_a],
        )

        method_b = _method(
            id="com.example.B#process()",
            name="process",
        )
        pf_b = _class_pf(
            id="com.example.B",
            name="B",
            methods=[method_b],
        )

        corpus = [
            (pf_a, _build_fragment(pf_a)),
            (pf_b, _build_fragment(pf_b)),
        ]
        return GraphAssembler().assemble(corpus)

    def test_field_callee_resolved(self):
        graph = self._corpus(
            caller_calls=["b.process()"],
            callee_field=True,
        )
        resolved = _edges_of(graph, CallsResolvedEdge)
        assert any(e.source == "com.example.A#doIt()" and e.target == "com.example.B#process()" for e in resolved)

    def test_field_callee_unresolved_edge_dropped(self):
        graph = self._corpus(
            caller_calls=["b.process()"],
            callee_field=True,
        )
        unresolved = _edges_of(graph, CallsUnresolvedEdge)
        targets = {e.target for e in unresolved}
        assert "b.process()" not in targets

    def test_param_callee_resolved(self):
        graph = self._corpus(
            caller_calls=["b.process()"],
            callee_param=True,
        )
        resolved = _edges_of(graph, CallsResolvedEdge)
        assert any(e.target == "com.example.B#process()" for e in resolved)

    def test_self_call_resolved(self):
        method_a = _method(
            id="com.example.A#outer()",
            name="outer",
            calls=["doIt()"],
        )
        method_a2 = _method(
            id="com.example.A#doIt()",
            name="doIt",
        )
        pf_a = _class_pf(
            id="com.example.A",
            imports=[],
            methods=[method_a, method_a2],
        )
        corpus = [(pf_a, _build_fragment(pf_a))]
        graph = GraphAssembler().assemble(corpus)
        resolved = _edges_of(graph, CallsResolvedEdge)
        assert any(e.source == "com.example.A#outer()" and e.target == "com.example.A#doIt()" for e in resolved)

    def test_local_variable_stays_unresolved(self):
        """Callee is a local variable — not in field or param index."""
        method_a = _method(
            id="com.example.A#doIt()",
            name="doIt",
            calls=["localVar.process()"],
        )
        pf_a = _class_pf(id="com.example.A", methods=[method_a])
        pf_b = _class_pf(id="com.example.B", name="B")
        corpus = [
            (pf_a, _build_fragment(pf_a)),
            (pf_b, _build_fragment(pf_b)),
        ]
        graph = GraphAssembler().assemble(corpus)
        unresolved = _edges_of(graph, CallsUnresolvedEdge)
        assert any(e.target == "localVar.process()" for e in unresolved)

    def test_unknown_method_name_stays_unresolved(self):
        """Callee type resolved but method name not in corpus."""
        graph = self._corpus(
            caller_calls=["b.nonExistentMethod()"],
            callee_field=True,
        )
        resolved = _edges_of(graph, CallsResolvedEdge)
        assert not any(e.target == "com.example.B#nonExistentMethod()" for e in resolved)
        unresolved = _edges_of(graph, CallsUnresolvedEdge)
        assert any("nonExistentMethod" in e.target for e in unresolved)


# ---------------------------------------------------------------------------
# Full assemble() integration
# ---------------------------------------------------------------------------


class TestAssemble:
    def test_all_nodes_merged(self):
        pf_a = _class_pf(id="com.example.A")
        pf_b = _class_pf(id="com.example.B", name="B")
        corpus = [(pf_a, _build_fragment(pf_a)), (pf_b, _build_fragment(pf_b))]
        graph = GraphAssembler().assemble(corpus)
        node_ids = {n.root.id for n in graph.nodes}
        assert "com.example.A" in node_ids
        assert "com.example.B" in node_ids

    def test_no_duplicate_nodes(self):
        pf_a = _class_pf(id="com.example.A")
        corpus = [(pf_a, _build_fragment(pf_a))]
        graph = GraphAssembler().assemble(corpus)
        ids = [n.root.id for n in graph.nodes]
        assert len(ids) == len(set(ids))

    def test_no_duplicate_edges(self):
        pf_a = _class_pf(
            id="com.example.A",
            imports=["com.example.B"],
        )
        pf_b = _class_pf(id="com.example.B", name="B")
        corpus = [(pf_a, _build_fragment(pf_a)), (pf_b, _build_fragment(pf_b))]
        graph = GraphAssembler().assemble(corpus)
        keys = [(e.root.kind, e.root.source, e.root.target) for e in graph.edges]
        assert len(keys) == len(set(keys))

    def test_empty_corpus_returns_empty_graph(self):
        graph = GraphAssembler().assemble([])
        assert graph.nodes == []
        assert graph.edges == []
