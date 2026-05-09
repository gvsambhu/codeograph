"""
Unit tests for GraphBuilder.

All tests go through the public build() method — no private method calls.
Each test verifies one behaviour; assertions are on the returned
CodeographKnowledgeGraph (node types, edge types, field values).
"""
import pytest

from codeograph.graph.graph_builder import GraphBuilder
from codeograph.graph.models.graph_schema import (
    AnnotationTypeNode,
    AutowiresEdge,
    BeanFactoryEdge,
    CallsUnresolvedEdge,
    ClassNode,
    ContainsEdge,
    EnumNode,
    ExtractionMode,
    FieldNode,
    Generation,
    HttpMetadata,
    InterfaceNode,
    InjectionType,
    MethodNode,
    Modifier,
    RecordNode,
    Stereotype,
)

# ---------------------------------------------------------------------------
# Shared helpers — minimal valid TypedDicts for each kind
# ---------------------------------------------------------------------------

MODULE_ID = "mod:core"


def _class_pf(**kwargs):
    """Minimal valid ParsedFile for a class."""
    base = {
        "kind": "class",
        "id": "com.example.Foo",
        "name": "Foo",
        "source_file": "src/main/java/com/example/Foo.java",
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
    """Minimal valid FieldFact."""
    base = {
        "id": "com.example.Foo.bar",
        "name": "bar",
        "type": "String",
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
    """Minimal valid MethodFact."""
    base = {
        "id": "com.example.Foo#doIt()",
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


def _param(**kwargs):
    """Minimal valid ParameterFact."""
    base = {
        "name": "arg",
        "type": "String",
        "validate": False,
        "constraints": [],
        "binding": None,
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# Helpers that extract typed roots from the graph
# ---------------------------------------------------------------------------

def _nodes_of(graph, cls):
    return [n.root for n in graph.nodes if isinstance(n.root, cls)]


def _edges_of(graph, cls):
    return [e.root for e in graph.edges if isinstance(e.root, cls)]


# ---------------------------------------------------------------------------
# Class builds
# ---------------------------------------------------------------------------

class TestBuildClass:
    def test_emits_one_class_node(self):
        graph = GraphBuilder().build(_class_pf(), MODULE_ID)
        assert len(_nodes_of(graph, ClassNode)) == 1

    def test_class_node_fields(self):
        graph = GraphBuilder().build(_class_pf(), MODULE_ID)
        node = _nodes_of(graph, ClassNode)[0]
        assert node.id == "com.example.Foo"
        assert node.name == "Foo"
        assert node.source_file == "src/main/java/com/example/Foo.java"

    def test_emits_module_contains_edge(self):
        graph = GraphBuilder().build(_class_pf(), MODULE_ID)
        edges = _edges_of(graph, ContainsEdge)
        module_edges = [e for e in edges if e.source == MODULE_ID]
        assert len(module_edges) == 1
        assert module_edges[0].target == "com.example.Foo"

    def test_extraction_mode_ast(self):
        graph = GraphBuilder().build(_class_pf(extraction_mode="ast"), MODULE_ID)
        node = _nodes_of(graph, ClassNode)[0]
        assert node.extraction_mode == ExtractionMode.ast

    def test_extraction_mode_regex_maps_to_fallback(self):
        graph = GraphBuilder().build(_class_pf(extraction_mode="regex"), MODULE_ID)
        node = _nodes_of(graph, ClassNode)[0]
        assert node.extraction_mode == ExtractionMode.regex_fallback

    def test_stereotype_mapped(self):
        graph = GraphBuilder().build(_class_pf(stereotype="Service"), MODULE_ID)
        node = _nodes_of(graph, ClassNode)[0]
        assert node.stereotype == Stereotype.Service

    def test_unknown_modifier_filtered_out(self):
        graph = GraphBuilder().build(
            _class_pf(modifiers=["public", "package"]), MODULE_ID
        )
        node = _nodes_of(graph, ClassNode)[0]
        # "package" is not a valid Modifier value — should be dropped, not crash
        assert len(node.modifiers) == 1
        assert node.modifiers[0] == Modifier.public

    def test_instance_reuse_resets_accumulators(self):
        builder = GraphBuilder()
        g1 = builder.build(_class_pf(id="com.example.A", name="A"), MODULE_ID)
        g2 = builder.build(_class_pf(id="com.example.B", name="B"), MODULE_ID)
        # Each call returns an independent fragment — no bleed-over
        assert len(g1.nodes) == 1
        assert len(g2.nodes) == 1
        assert _nodes_of(g1, ClassNode)[0].id == "com.example.A"
        assert _nodes_of(g2, ClassNode)[0].id == "com.example.B"


# ---------------------------------------------------------------------------
# Interface / enum / record / annotation_type builds
# ---------------------------------------------------------------------------

class TestBuildInterface:
    def _pf(self, **kwargs):
        base = {
            "kind": "interface",
            "id": "com.example.IFoo",
            "name": "IFoo",
            "source_file": "src/IFoo.java",
            "extraction_mode": "ast",
            "annotations": [],
            "imports": [],
            "line_range": [1, 5],
            "modifiers": ["public"],
            "extends_interfaces": [],
            "methods": [],
        }
        base.update(kwargs)
        return base

    def test_emits_interface_node(self):
        graph = GraphBuilder().build(self._pf(), MODULE_ID)
        assert len(_nodes_of(graph, InterfaceNode)) == 1

    def test_emits_contains_edge(self):
        graph = GraphBuilder().build(self._pf(), MODULE_ID)
        edges = _edges_of(graph, ContainsEdge)
        assert any(e.source == MODULE_ID and e.target == "com.example.IFoo" for e in edges)

    def test_interface_methods_are_built(self):
        m = _method(id="com.example.IFoo#doIt()", name="doIt")
        graph = GraphBuilder().build(self._pf(methods=[m]), MODULE_ID)
        assert len(_nodes_of(graph, MethodNode)) == 1


class TestBuildEnum:
    def _pf(self, **kwargs):
        base = {
            "kind": "enum",
            "id": "com.example.Status",
            "name": "Status",
            "source_file": "src/Status.java",
            "extraction_mode": "ast",
            "annotations": [],
            "imports": [],
            "line_range": [1, 5],
            "modifiers": ["public"],
            "constants": ["ACTIVE", "INACTIVE"],
            "implements": [],
            "fields": [],
            "methods": [],
        }
        base.update(kwargs)
        return base

    def test_emits_enum_node(self):
        graph = GraphBuilder().build(self._pf(), MODULE_ID)
        assert len(_nodes_of(graph, EnumNode)) == 1

    def test_constants_preserved(self):
        graph = GraphBuilder().build(self._pf(), MODULE_ID)
        node = _nodes_of(graph, EnumNode)[0]
        assert node.constants == ["ACTIVE", "INACTIVE"]

    def test_emits_contains_edge(self):
        graph = GraphBuilder().build(self._pf(), MODULE_ID)
        edges = _edges_of(graph, ContainsEdge)
        assert any(e.source == MODULE_ID and e.target == "com.example.Status" for e in edges)


class TestBuildRecord:
    def _pf(self, **kwargs):
        base = {
            "kind": "record",
            "id": "com.example.Point",
            "name": "Point",
            "source_file": "src/Point.java",
            "extraction_mode": "ast",
            "annotations": [],
            "imports": [],
            "line_range": [1, 3],
            "components": [
                {"name": "x", "type": "int"},
                {"name": "y", "type": "int"},
            ],
            "implements": [],
        }
        base.update(kwargs)
        return base

    def test_emits_record_node(self):
        graph = GraphBuilder().build(self._pf(), MODULE_ID)
        assert len(_nodes_of(graph, RecordNode)) == 1

    def test_components_count(self):
        graph = GraphBuilder().build(self._pf(), MODULE_ID)
        node = _nodes_of(graph, RecordNode)[0]
        assert len(node.components) == 2
        assert node.components[0].name == "x"
        assert node.components[1].name == "y"


class TestBuildAnnotationType:
    def _pf(self, **kwargs):
        base = {
            "kind": "annotation_type",
            "id": "com.example.MyAnnotation",
            "name": "MyAnnotation",
            "source_file": "src/MyAnnotation.java",
            "extraction_mode": "ast",
            "annotations": [],
            "imports": [],
            "line_range": [1, 5],
            "modifiers": ["public"],
            "elements": [
                {"name": "value", "type": "String", "default_value": None}
            ],
        }
        base.update(kwargs)
        return base

    def test_emits_annotation_type_node(self):
        graph = GraphBuilder().build(self._pf(), MODULE_ID)
        assert len(_nodes_of(graph, AnnotationTypeNode)) == 1

    def test_elements_count(self):
        graph = GraphBuilder().build(self._pf(), MODULE_ID)
        node = _nodes_of(graph, AnnotationTypeNode)[0]
        assert len(node.elements) == 1
        assert node.elements[0].name == "value"


class TestUnknownKind:
    def test_unknown_kind_returns_empty_graph(self):
        pf = {
            "kind": "module-info",
            "id": "com.example",
            "name": "example",
            "source_file": "module-info.java",
            "extraction_mode": "ast",
            "annotations": [],
            "imports": [],
        }
        graph = GraphBuilder().build(pf, MODULE_ID)
        assert graph.nodes == []
        assert graph.edges == []


# ---------------------------------------------------------------------------
# Field builds
# ---------------------------------------------------------------------------

class TestBuildField:
    def test_field_node_emitted(self):
        graph = GraphBuilder().build(_class_pf(fields=[_field()]), MODULE_ID)
        assert len(_nodes_of(graph, FieldNode)) == 1

    def test_field_node_name_and_type(self):
        graph = GraphBuilder().build(
            _class_pf(fields=[_field(name="repo", type="OrderRepository")]),
            MODULE_ID,
        )
        node = _nodes_of(graph, FieldNode)[0]
        assert node.name == "repo"
        assert node.type == "OrderRepository"

    def test_class_contains_field_edge(self):
        graph = GraphBuilder().build(_class_pf(fields=[_field()]), MODULE_ID)
        contains = _edges_of(graph, ContainsEdge)
        assert any(e.source == "com.example.Foo" and e.target == "com.example.Foo.bar"
                   for e in contains)

    def test_autowired_field_emits_autowires_edge(self):
        f = _field(
            id="com.example.Foo.repo",
            name="repo",
            type="OrderRepository",
            is_autowired=True,
            injection_type="field",
        )
        graph = GraphBuilder().build(_class_pf(fields=[f]), MODULE_ID)
        edges = _edges_of(graph, AutowiresEdge)
        assert len(edges) == 1
        assert edges[0].source == "com.example.Foo.repo"
        assert edges[0].target == "OrderRepository"
        assert edges[0].injection_type == InjectionType.field

    def test_non_autowired_field_no_autowires_edge(self):
        graph = GraphBuilder().build(_class_pf(fields=[_field()]), MODULE_ID)
        assert len(_edges_of(graph, AutowiresEdge)) == 0

    def test_autowired_with_qualifier(self):
        f = _field(
            id="com.example.Foo.repo", name="repo", type="Repo",
            is_autowired=True, injection_type="field", qualifier="primaryRepo",
        )
        graph = GraphBuilder().build(_class_pf(fields=[f]), MODULE_ID)
        edge = _edges_of(graph, AutowiresEdge)[0]
        assert edge.qualifier == "primaryRepo"

    def test_jpa_id_generation_translated(self):
        f = _field(is_id=True, generation="GenerationType.IDENTITY")
        graph = GraphBuilder().build(_class_pf(fields=[f]), MODULE_ID)
        node = _nodes_of(graph, FieldNode)[0]
        assert node.is_id is True
        assert node.generation == Generation.IDENTITY

    def test_column_metadata_mapped(self):
        f = _field(column={"name": "user_name", "nullable": False, "length": 100})
        graph = GraphBuilder().build(_class_pf(fields=[f]), MODULE_ID)
        node = _nodes_of(graph, FieldNode)[0]
        assert node.column is not None
        assert node.column.name == "user_name"
        assert node.column.nullable is False


# ---------------------------------------------------------------------------
# Method builds
# ---------------------------------------------------------------------------

class TestBuildMethod:
    def test_method_node_emitted(self):
        graph = GraphBuilder().build(_class_pf(methods=[_method()]), MODULE_ID)
        assert len(_nodes_of(graph, MethodNode)) == 1

    def test_method_node_fields(self):
        graph = GraphBuilder().build(_class_pf(methods=[_method()]), MODULE_ID)
        node = _nodes_of(graph, MethodNode)[0]
        assert node.name == "doIt"
        assert node.return_type == "void"
        assert node.is_constructor is False

    def test_class_contains_method_edge(self):
        graph = GraphBuilder().build(_class_pf(methods=[_method()]), MODULE_ID)
        contains = _edges_of(graph, ContainsEdge)
        assert any(
            e.source == "com.example.Foo" and e.target == "com.example.Foo#doIt()"
            for e in contains
        )

    def test_bean_factory_emits_edge(self):
        m = _method(
            id="com.example.Foo#ds()",
            name="ds",
            return_type="DataSource",
            is_bean_factory=True,
        )
        graph = GraphBuilder().build(_class_pf(methods=[m]), MODULE_ID)
        edges = _edges_of(graph, BeanFactoryEdge)
        assert len(edges) == 1
        assert edges[0].source == "com.example.Foo#ds()"
        assert edges[0].target == "DataSource"

    def test_no_bean_factory_no_edge(self):
        graph = GraphBuilder().build(_class_pf(methods=[_method()]), MODULE_ID)
        assert len(_edges_of(graph, BeanFactoryEdge)) == 0

    def test_calls_emit_unresolved_edges(self):
        m = _method(calls=["repo.save(e)", "repo.delete(id)"])
        graph = GraphBuilder().build(_class_pf(methods=[m]), MODULE_ID)
        edges = _edges_of(graph, CallsUnresolvedEdge)
        assert len(edges) == 2
        targets = {e.target for e in edges}
        assert targets == {"repo.save(e)", "repo.delete(id)"}

    def test_unresolved_edge_raw_call_expr_set(self):
        m = _method(calls=["repo.save(e)"])
        graph = GraphBuilder().build(_class_pf(methods=[m]), MODULE_ID)
        edge = _edges_of(graph, CallsUnresolvedEdge)[0]
        assert edge.raw_call_expr == "repo.save(e)"

    def test_empty_calls_no_unresolved_edges(self):
        graph = GraphBuilder().build(_class_pf(methods=[_method()]), MODULE_ID)
        assert len(_edges_of(graph, CallsUnresolvedEdge)) == 0

    def test_http_metadata_get_mapped(self):
        m = _method(http_metadata={"method": "GET", "path": "/users"})
        graph = GraphBuilder().build(_class_pf(methods=[m]), MODULE_ID)
        node = _nodes_of(graph, MethodNode)[0]
        assert node.http_metadata is not None
        assert node.http_metadata.path == "/users"

    def test_http_metadata_null_method_omitted(self):
        """@RequestMapping without method attribute — http_metadata omitted."""
        m = _method(http_metadata={"method": None, "path": "/api"})
        graph = GraphBuilder().build(_class_pf(methods=[m]), MODULE_ID)
        node = _nodes_of(graph, MethodNode)[0]
        assert node.http_metadata is None

    def test_response_status_always_none_in_v1(self):
        """String → int resolution deferred to v1.1."""
        m = _method(response_status="HttpStatus.CREATED")
        graph = GraphBuilder().build(_class_pf(methods=[m]), MODULE_ID)
        node = _nodes_of(graph, MethodNode)[0]
        assert node.response_status is None

    def test_complexity_metrics_carried(self):
        m = _method(cyclomatic_complexity=5, cognitive_complexity=3, method_loc=20)
        graph = GraphBuilder().build(_class_pf(methods=[m]), MODULE_ID)
        node = _nodes_of(graph, MethodNode)[0]
        assert node.cyclomatic_complexity == 5
        assert node.cognitive_complexity == 3
        assert node.method_loc == 20


# ---------------------------------------------------------------------------
# Parameter embedding
# ---------------------------------------------------------------------------

class TestEmbedParameter:
    def test_parameter_without_binding(self):
        p = _param(name="id", type="Long", binding=None)
        m = _method(parameters=[p])
        graph = GraphBuilder().build(_class_pf(methods=[m]), MODULE_ID)
        node = _nodes_of(graph, MethodNode)[0]
        assert len(node.parameters) == 1
        assert node.parameters[0].name == "id"
        assert node.parameters[0].type == "Long"
        assert node.parameters[0].binding is None

    def test_parameter_with_path_binding(self):
        p = _param(
            name="id", type="Long",
            binding={"kind": "path", "name": "id", "required": True, "default_value": None},
        )
        m = _method(parameters=[p])
        graph = GraphBuilder().build(_class_pf(methods=[m]), MODULE_ID)
        node = _nodes_of(graph, MethodNode)[0]
        binding = node.parameters[0].binding
        assert binding is not None
        assert binding.kind.value == "path"
        assert binding.required is True

    def test_parameter_with_body_binding(self):
        p = _param(
            name="dto", type="OrderDTO",
            binding={"kind": "body", "name": None, "required": True, "default_value": None},
        )
        m = _method(parameters=[p])
        graph = GraphBuilder().build(_class_pf(methods=[m]), MODULE_ID)
        node = _nodes_of(graph, MethodNode)[0]
        assert node.parameters[0].binding.kind.value == "body"

    def test_parameter_validate_flag(self):
        p = _param(validate=True)
        m = _method(parameters=[p])
        graph = GraphBuilder().build(_class_pf(methods=[m]), MODULE_ID)
        node = _nodes_of(graph, MethodNode)[0]
        assert node.parameters[0].validate_ is True

    def test_multiple_parameters_all_embedded(self):
        params = [
            _param(name="id", type="Long"),
            _param(name="name", type="String"),
        ]
        m = _method(parameters=params)
        graph = GraphBuilder().build(_class_pf(methods=[m]), MODULE_ID)
        node = _nodes_of(graph, MethodNode)[0]
        assert len(node.parameters) == 2
        assert node.parameters[0].name == "id"
        assert node.parameters[1].name == "name"
