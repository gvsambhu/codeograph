"""
Unit tests for GraphAssembler.

Static helpers (_parse_call_expr, _strip_collection_wrapper) are tested
directly. Index builders and edge-addition methods are tested through the
public assemble() method using minimal two-file corpora.
"""

from __future__ import annotations

from typing import Any, cast

from codeograph.graph.graph_assembler import GraphAssembler
from codeograph.graph.graph_builder import GraphBuilder
from codeograph.graph.models.graph_schema import (
    CallsResolvedEdge,
    CallsUnresolvedEdge,
    Cardinality,
    CodeographKnowledgeGraph,
    DependsOnEdge,
    RelationEdge,
)
from codeograph.parser.models import FieldFact, MethodFact, ParsedFile

# ---------------------------------------------------------------------------
# Minimal ParsedFile factories
# ---------------------------------------------------------------------------

MODULE_ID = "mod:core"


def _class_pf(**kwargs: object) -> ParsedFile:
    base: dict[str, object] = {
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
    return cast(ParsedFile, base)


def _field(**kwargs: object) -> FieldFact:
    base: dict[str, object] = {
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
    return cast(FieldFact, base)


def _method(**kwargs: object) -> MethodFact:
    base: dict[str, object] = {
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
    return cast(MethodFact, base)


def _build_fragment(parsed_file: ParsedFile) -> CodeographKnowledgeGraph:
    """Build a graph fragment from a ParsedFile using GraphBuilder."""
    return GraphBuilder().build(parsed_file, MODULE_ID)


def _edges_of[T](graph: CodeographKnowledgeGraph, cls: type[T]) -> list[T]:
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
    def _two_class_corpus(
        self, a_imports: list[str] | None = None, a_fields: list[FieldFact] | None = None
    ) -> CodeographKnowledgeGraph:
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

    @staticmethod
    def _targets_of_a(a: ParsedFile, *others: ParsedFile) -> set[str]:
        graph = GraphAssembler().assemble([(pf, _build_fragment(pf)) for pf in (a, *others)])
        return {e.target for e in _edges_of(graph, DependsOnEdge) if e.source == a["id"]}

    def test_same_package_field_type_gives_an_edge_without_an_import(self):
        a = _class_pf(fields=[_field(id="com.example.A.address", name="address", type="Address")])
        address = _class_pf(id="com.example.Address", name="Address")
        assert self._targets_of_a(a, address) == {"com.example.Address"}

    def test_type_argument_of_a_field_gives_an_edge(self):
        a = _class_pf(fields=[_field(id="com.example.A.pets", name="pets", type="List<Pet>")])
        pet = _class_pf(id="com.example.Pet", name="Pet")
        assert self._targets_of_a(a, pet) == {"com.example.Pet"}

    def test_nested_type_arguments_and_wildcard_bounds_give_edges(self):
        a = _class_pf(
            imports=["com.example.model.Owner"],
            fields=[
                _field(id="com.example.A.index", name="index", type="Map<String, List<Pet>>"),
                _field(id="com.example.A.owners", name="owners", type="Set<? extends Owner>"),
            ],
        )
        pet = _class_pf(id="com.example.Pet", name="Pet")
        owner = _class_pf(id="com.example.model.Owner", name="Owner")
        assert self._targets_of_a(a, pet, owner) == {"com.example.Pet", "com.example.model.Owner"}

    def test_array_element_type_gives_an_edge(self):
        a = _class_pf(fields=[_field(id="com.example.A.pets", name="pets", type="Pet[]")])
        pet = _class_pf(id="com.example.Pet", name="Pet")
        assert self._targets_of_a(a, pet) == {"com.example.Pet"}

    def test_return_and_parameter_types_resolve_in_the_same_way(self):
        a = _class_pf(
            methods=[
                _method(
                    id="com.example.A#find(Optional<Owner>)",
                    name="find",
                    return_type="List<Pet>",
                    parameters=[{"name": "owner", "type": "Optional<Owner>"}],
                )
            ],
        )
        pet = _class_pf(id="com.example.Pet", name="Pet")
        owner = _class_pf(id="com.example.Owner", name="Owner")
        assert self._targets_of_a(a, pet, owner) == {"com.example.Pet", "com.example.Owner"}

    def test_edge_to_a_class_outside_the_corpus_is_not_drawn(self):
        a = _class_pf(fields=[_field(id="com.example.A.pets", name="pets", type="List<Pet>")])
        assert self._targets_of_a(a) == set()


# ---------------------------------------------------------------------------
# RelationEdge tests
# ---------------------------------------------------------------------------


class TestAddRelationEdges:
    def _corpus_with_relation(self, annotation: str, field_type: str) -> CodeographKnowledgeGraph:
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
    def _corpus(
        self, caller_calls: list[str] | None = None, callee_field: bool = False, callee_param: bool = False
    ) -> CodeographKnowledgeGraph:
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
# Superclass and interface names — resolved on the graph nodes
# ---------------------------------------------------------------------------


def _node_named(graph: CodeographKnowledgeGraph, fqcn: str) -> Any:
    return next(n.root for n in graph.nodes if n.root.id == fqcn)


class TestSupertypeNameResolution:
    """The parser reports supertypes as written; the assembled node carries FQCNs."""

    def test_explicit_import_resolves_superclass_and_interfaces(self):
        child = _class_pf(
            id="com.example.web.Child",
            name="Child",
            imports=["com.example.base.Base", "com.example.base.Auditable"],
            superclass="Base",
            implements=["Auditable"],
        )
        base = _class_pf(id="com.example.base.Base", name="Base")
        graph = GraphAssembler().assemble([(p, _build_fragment(p)) for p in (child, base)])
        node = _node_named(graph, "com.example.web.Child")
        assert node.superclass == "com.example.base.Base"
        assert node.implements == ["com.example.base.Auditable"]

    def test_same_package_class_resolves_without_an_import(self):
        child = _class_pf(id="com.example.Child", name="Child", superclass="Base")
        base = _class_pf(id="com.example.Base", name="Base")
        graph = GraphAssembler().assemble([(p, _build_fragment(p)) for p in (child, base)])
        assert _node_named(graph, "com.example.Child").superclass == "com.example.Base"
        # The dependency edge follows the same rule as the node field.
        assert any(
            e.source == "com.example.Child" and e.target == "com.example.Base" for e in _edges_of(graph, DependsOnEdge)
        )

    def test_unresolvable_name_stays_as_written(self):
        # Neither imported explicitly nor declared in the corpus: a wildcard-imported
        # or java.lang type.
        child = _class_pf(id="com.example.Child", name="Child", superclass="Exception", implements=["Runnable"])
        graph = GraphAssembler().assemble([(child, _build_fragment(child))])
        node = _node_named(graph, "com.example.Child")
        assert node.superclass == "Exception"
        assert node.implements == ["Runnable"]

    def test_qualified_name_passes_through(self):
        child = _class_pf(
            id="com.example.Child",
            name="Child",
            superclass="org.other.Base",
            implements=["java.io.Serializable"],
        )
        graph = GraphAssembler().assemble([(child, _build_fragment(child))])
        node = _node_named(graph, "com.example.Child")
        assert node.superclass == "org.other.Base"
        assert node.implements == ["java.io.Serializable"]

    def test_explicit_import_wins_over_same_package_class(self):
        child = _class_pf(
            id="com.example.Child",
            name="Child",
            imports=["org.other.Base"],
            superclass="Base",
        )
        local_base = _class_pf(id="com.example.Base", name="Base")
        graph = GraphAssembler().assemble([(p, _build_fragment(p)) for p in (child, local_base)])
        assert _node_named(graph, "com.example.Child").superclass == "org.other.Base"

    def test_nested_jdk_type_resolves_through_its_outer_type(self):
        child = _class_pf(
            id="com.example.Child",
            name="Child",
            imports=["java.util.Map"],
            implements=["Map.Entry"],
        )
        graph = GraphAssembler().assemble([(child, _build_fragment(child))])
        assert _node_named(graph, "com.example.Child").implements == ["java.util.Map.Entry"]

    def test_nested_project_type_resolves_through_its_outer_type(self):
        child = _class_pf(
            id="com.example.web.Child",
            name="Child",
            imports=["com.example.model.Outer"],
            superclass="Outer.Inner",
        )
        outer = _class_pf(id="com.example.model.Outer", name="Outer")
        graph = GraphAssembler().assemble([(p, _build_fragment(p)) for p in (child, outer)])
        assert _node_named(graph, "com.example.web.Child").superclass == "com.example.model.Outer.Inner"

    def test_nested_type_of_a_same_package_class_resolves(self):
        child = _class_pf(id="com.example.Child", name="Child", superclass="Outer.Inner")
        outer = _class_pf(id="com.example.Outer", name="Outer")
        graph = GraphAssembler().assemble([(p, _build_fragment(p)) for p in (child, outer)])
        assert _node_named(graph, "com.example.Child").superclass == "com.example.Outer.Inner"

    def test_nested_type_with_an_unresolved_outer_type_stays_as_written(self):
        child = _class_pf(id="com.example.Child", name="Child", superclass="Unknown.Inner")
        graph = GraphAssembler().assemble([(child, _build_fragment(child))])
        assert _node_named(graph, "com.example.Child").superclass == "Unknown.Inner"

    def test_package_qualified_name_with_a_lowercase_first_segment_is_unchanged(self):
        # An import of an unrelated Base must not capture a name that is already qualified.
        child = _class_pf(
            id="com.example.Child",
            name="Child",
            imports=["org.other.Base"],
            superclass="com.other.Base",
        )
        graph = GraphAssembler().assemble([(child, _build_fragment(child))])
        assert _node_named(graph, "com.example.Child").superclass == "com.other.Base"

    def test_supertype_reached_through_an_on_demand_import_of_a_project_package_resolves(self):
        child = _class_pf(
            id="com.example.web.Child",
            name="Child",
            wildcard_imports=["com.example.base"],
            superclass="Base",
            implements=["Auditable"],
        )
        base = _class_pf(id="com.example.base.Base", name="Base")
        auditable = _class_pf(id="com.example.base.Auditable", name="Auditable")
        graph = GraphAssembler().assemble([(p, _build_fragment(p)) for p in (child, base, auditable)])
        node = _node_named(graph, "com.example.web.Child")
        assert node.superclass == "com.example.base.Base"
        assert node.implements == ["com.example.base.Auditable"]
        targets = {e.target for e in _edges_of(graph, DependsOnEdge) if e.source == "com.example.web.Child"}
        assert targets == {"com.example.base.Base", "com.example.base.Auditable"}

    def test_field_type_reached_through_an_on_demand_import_draws_its_edge(self):
        a = _class_pf(
            wildcard_imports=["com.example.model"],
            fields=[_field(id="com.example.A.pets", name="pets", type="List<Pet>")],
        )
        pet = _class_pf(id="com.example.model.Pet", name="Pet")
        graph = GraphAssembler().assemble([(p, _build_fragment(p)) for p in (a, pet)])
        targets = {e.target for e in _edges_of(graph, DependsOnEdge) if e.source == "com.example.A"}
        assert targets == {"com.example.model.Pet"}

    def test_a_name_declared_in_two_on_demand_packages_stays_as_written(self):
        # Java rejects the ambiguity; the resolver does not guess.
        child = _class_pf(
            id="com.example.web.Child",
            name="Child",
            wildcard_imports=["com.example.one", "com.example.two"],
            superclass="Base",
        )
        one = _class_pf(id="com.example.one.Base", name="Base")
        two = _class_pf(id="com.example.two.Base", name="Base")
        graph = GraphAssembler().assemble([(p, _build_fragment(p)) for p in (child, one, two)])
        assert _node_named(graph, "com.example.web.Child").superclass == "Base"

    def test_a_name_declared_in_only_one_of_two_on_demand_packages_resolves(self):
        child = _class_pf(
            id="com.example.web.Child",
            name="Child",
            wildcard_imports=["com.example.one", "com.example.two"],
            superclass="Base",
        )
        two = _class_pf(id="com.example.two.Base", name="Base")
        graph = GraphAssembler().assemble([(p, _build_fragment(p)) for p in (child, two)])
        assert _node_named(graph, "com.example.web.Child").superclass == "com.example.two.Base"

    def test_the_own_package_wins_over_an_on_demand_import(self):
        child = _class_pf(
            id="com.example.Child", name="Child", wildcard_imports=["com.example.base"], superclass="Base"
        )
        own = _class_pf(id="com.example.Base", name="Base")
        other = _class_pf(id="com.example.base.Base", name="Base")
        graph = GraphAssembler().assemble([(p, _build_fragment(p)) for p in (child, own, other)])
        assert _node_named(graph, "com.example.Child").superclass == "com.example.Base"

    def test_an_explicit_import_wins_over_the_own_package_and_an_on_demand_import(self):
        child = _class_pf(
            id="com.example.Child",
            name="Child",
            imports=["org.other.Base"],
            wildcard_imports=["com.example.base"],
            superclass="Base",
        )
        own = _class_pf(id="com.example.Base", name="Base")
        other = _class_pf(id="com.example.base.Base", name="Base")
        graph = GraphAssembler().assemble([(p, _build_fragment(p)) for p in (child, own, other)])
        assert _node_named(graph, "com.example.Child").superclass == "org.other.Base"

    def test_interface_extends_resolved(self):
        iface = _class_pf(
            kind="interface",
            id="com.example.Repo",
            name="Repo",
            extends_interfaces=["Marker", "Serializable"],
        )
        marker = _class_pf(id="com.example.Marker", name="Marker")
        graph = GraphAssembler().assemble([(p, _build_fragment(p)) for p in (iface, marker)])
        node = _node_named(graph, "com.example.Repo")
        assert node.extends_interfaces == ["com.example.Marker", "Serializable"]

    def test_enum_implements_resolved(self):
        enum = _class_pf(
            kind="enum",
            id="com.example.Status",
            name="Status",
            constants=["ACTIVE"],
            implements=["Displayable"],
        )
        shown = _class_pf(id="com.example.Displayable", name="Displayable")
        graph = GraphAssembler().assemble([(p, _build_fragment(p)) for p in (enum, shown)])
        assert _node_named(graph, "com.example.Status").implements == ["com.example.Displayable"]


# ---------------------------------------------------------------------------
# CBO — set from the referenced types plus the resolved call targets
# ---------------------------------------------------------------------------


class TestCoupling:
    """CBO counts the distinct classes a class references, other than itself and the JDK's."""

    @staticmethod
    def _cbo(files: list[ParsedFile], fqcn: str = "com.example.A") -> int | None:
        graph = GraphAssembler().assemble([(pf, _build_fragment(pf)) for pf in files])
        return cast(int | None, _node_named(graph, fqcn).cbo)

    @staticmethod
    def _callee(name: str, package: str = "com.example") -> ParsedFile:
        return _class_pf(
            id=f"{package}.{name}",
            name=name,
            methods=[_method(id=f"{package}.{name}#run()", name="run")],
        )

    def test_resolved_call_to_an_unreferenced_class_adds_one(self):
        owner = _class_pf(id="com.example.Owner", name="Owner")
        without_call = _class_pf(imports=["com.example.Owner"], referenced_types=["Owner"], cbo=1)
        with_call = _class_pf(
            imports=["com.example.Owner", "com.example.util.Util"],
            referenced_types=["Owner"],
            methods=[_method(id="com.example.A#doIt()", name="doIt", calls=["Util.run()"])],
        )
        util = self._callee("Util", "com.example.util")
        assert self._cbo([without_call, owner]) == 1
        assert self._cbo([with_call, owner, util]) == 2

    def test_resolved_call_to_a_referenced_class_changes_nothing(self):
        b = self._callee("B")
        field = _field(id="com.example.A.b", name="b", type="B")
        a = _class_pf(
            imports=["com.example.B"],
            fields=[field],
            referenced_types=["B"],
            methods=[_method(id="com.example.A#doIt()", name="doIt", calls=["b.run()"])],
        )
        assert self._cbo([a, b]) == 1

    def test_names_resolving_to_one_class_count_once(self):
        owner = _class_pf(id="com.example.Owner", name="Owner")
        a = _class_pf(referenced_types=["Owner", "com.example.Owner"])
        assert self._cbo([a, owner]) == 1

    def test_unresolved_names_each_count(self):
        # Neither is a JDK type, so each is counted as written.
        a = _class_pf(referenced_types=["Foo", "Bar"])
        assert self._cbo([a]) == 2

    def test_jdk_classes_are_excluded(self):
        a = _class_pf(imports=["java.io.IOException"], referenced_types=["IOException", "java.io.File"])
        assert self._cbo([a]) == 0

    def test_java_lang_types_named_without_a_package_are_excluded(self):
        # A local StringBuilder and a throws NumberFormatException need no import.
        a = _class_pf(referenced_types=["StringBuilder", "NumberFormatException", "Thread", "Runnable"])
        assert self._cbo([a]) == 0

    def test_a_type_imported_on_demand_from_the_jdk_is_excluded(self):
        # import java.util.*;  →  Date, Iterator and Map.Entry are the JDK's.
        a = _class_pf(wildcard_imports=["java.util"], referenced_types=["Date", "Iterator", "Map.Entry", "Owner"])
        assert self._cbo([a]) == 1  # Owner only

    def test_the_same_name_without_the_wildcard_import_counts(self):
        # Date is not java.lang; with no import that names it, it is some other class.
        a = _class_pf(referenced_types=["Date"])
        assert self._cbo([a]) == 1

    def test_an_on_demand_import_of_a_project_package_does_not_make_a_type_the_jdk(self):
        a = _class_pf(wildcard_imports=["com.example.model"], referenced_types=["Owner"])
        assert self._cbo([a]) == 1

    def test_a_jdk_javax_package_is_excluded(self):
        a = _class_pf(imports=["javax.sql.DataSource"], referenced_types=["DataSource", "javax.crypto.Cipher"])
        assert self._cbo([a]) == 0

    def test_a_javax_api_outside_the_jdk_counts(self):
        a = _class_pf(
            imports=["javax.persistence.EntityManager"],
            referenced_types=["EntityManager", "javax.servlet.http.HttpServletRequest"],
        )
        assert self._cbo([a]) == 2

    def test_a_project_class_named_like_a_jdk_type_counts(self):
        record = _class_pf(id="com.example.Record", name="Record")
        a = _class_pf(referenced_types=["Record"])
        assert self._cbo([a, record]) == 1

    def test_a_default_package_project_class_named_like_a_jdk_type_counts(self):
        record = _class_pf(id="Record", name="Record", source_file="src/Record.java")
        a = _class_pf(id="A", name="A", source_file="src/A.java", referenced_types=["Record"])
        assert self._cbo([a, record], "A") == 1

    def test_an_imported_project_class_named_like_a_jdk_type_counts(self):
        date = _class_pf(id="com.example.util.Date", name="Date")
        a = _class_pf(imports=["com.example.util.Date"], wildcard_imports=["java.util"], referenced_types=["Date"])
        assert self._cbo([a, date]) == 1

    def test_a_class_named_only_in_a_type_argument_is_counted(self):
        pet = _class_pf(id="com.example.Pet", name="Pet")
        owner = _class_pf(
            id="com.example.Owner",
            name="Owner",
            imports=["java.util.List"],
            fields=[_field(id="com.example.Owner.pets", name="pets", type="List<Pet>")],
            referenced_types=["List", "Pet"],
        )
        graph = GraphAssembler().assemble([(p, _build_fragment(p)) for p in (owner, pet)])
        assert _node_named(graph, "com.example.Owner").cbo == 1  # Pet; List is the JDK's
        # The dependency edge is drawn from the same names.
        assert any(
            e.source == "com.example.Owner" and e.target == "com.example.Pet" for e in _edges_of(graph, DependsOnEdge)
        )

    def test_a_class_reached_only_through_an_on_demand_import_of_a_project_package_counts(self):
        # java.io is imported on demand too, but only the project declares a Console: it wins,
        # so the name is a corpus class and not java.io.Console.
        console = _class_pf(id="com.example.tools.Console", name="Console")
        a = _class_pf(wildcard_imports=["java.io", "com.example.tools"], referenced_types=["Console", "Owner"])
        assert self._cbo([a, console]) == 2

    def test_names_resolving_to_one_class_through_an_on_demand_import_count_once(self):
        console = _class_pf(id="com.example.tools.Console", name="Console")
        a = _class_pf(wildcard_imports=["com.example.tools"], referenced_types=["Console", "com.example.tools.Console"])
        assert self._cbo([a, console]) == 1

    def test_a_name_declared_in_two_on_demand_packages_is_left_as_written(self):
        one = _class_pf(id="com.example.one.Base", name="Base")
        two = _class_pf(id="com.example.two.Base", name="Base")
        a = _class_pf(
            wildcard_imports=["com.example.one", "com.example.two"],
            referenced_types=["Base", "com.example.one.Base"],
        )
        # "Base" stays as written and is a class of its own to count; the qualified name is the other.
        assert self._cbo([a, one, two]) == 2

    def test_the_own_package_wins_over_an_on_demand_import(self):
        own = _class_pf(id="com.example.Base", name="Base")
        other = _class_pf(id="com.example.base.Base", name="Base")
        a = _class_pf(wildcard_imports=["com.example.base"], referenced_types=["Base", "com.example.Base"])
        assert self._cbo([a, own, other]) == 1

    def test_an_explicit_import_wins_over_the_own_package_and_an_on_demand_import(self):
        own = _class_pf(id="com.example.Base", name="Base")
        other = _class_pf(id="com.example.base.Base", name="Base")
        a = _class_pf(
            imports=["org.other.Base"],
            wildcard_imports=["com.example.base"],
            referenced_types=["Base", "org.other.Base"],
        )
        assert self._cbo([a, own, other]) == 1

    def test_an_unresolved_call_adds_no_class(self):
        # `helper` is a local variable, so the call cannot be resolved even though Helper declares run().
        helper = self._callee("Helper")
        a = _class_pf(
            referenced_types=["Owner"],
            methods=[_method(id="com.example.A#doIt()", name="doIt", calls=["helper.run()"])],
        )
        assert self._cbo([a, helper]) == 1

    def test_the_class_itself_is_excluded(self):
        a = _class_pf(
            referenced_types=["A"],
            methods=[_method(id="com.example.A#outer()", name="outer", calls=["doIt()"])]
            + [_method(id="com.example.A#doIt()", name="doIt")],
        )
        assert self._cbo([a]) == 0

    def test_nested_jdk_type_is_excluded(self):
        # Map.Entry resolves through its outer type to java.util.Map.Entry.
        a = _class_pf(imports=["java.util.Map"], referenced_types=["Owner", "Map.Entry"])
        assert self._cbo([a]) == 1  # Owner only

    def test_a_class_does_not_count_its_own_nested_type(self):
        order = _class_pf(id="com.example.Order", name="Order", referenced_types=["Order.Builder", "Address"])
        assert self._cbo([order], "com.example.Order") == 1  # Address only

    def test_another_class_counts_a_nested_type(self):
        order = _class_pf(id="com.example.Order", name="Order")
        a = _class_pf(imports=["com.example.Order"], referenced_types=["Order.Builder"])
        assert self._cbo([a, order]) == 1

    def test_no_referenced_types_keeps_the_parsers_count(self):
        a = _class_pf(cbo=7)
        assert self._cbo([a]) == 7


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
