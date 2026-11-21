from codeograph.passes.pass1.annotatable_nodes import select_annotatable_nodes


def test_only_source_bearing_type_nodes_are_selected_in_graph_order() -> None:
    nodes = [
        {"id": "a", "kind": "class"},
        {"id": "a.m", "kind": "method"},
        {"id": "a.f", "kind": "field"},
        {"id": "b", "kind": "interface"},
        {"id": "c", "kind": "enum"},
        {"id": "d", "kind": "record"},
        {"id": "e", "kind": "annotation_type"},
        {"id": "mod", "kind": "module"},
        {"id": "no-kind"},
    ]

    assert [n["id"] for n in select_annotatable_nodes(nodes)] == ["a", "b", "c", "d", "e"]
