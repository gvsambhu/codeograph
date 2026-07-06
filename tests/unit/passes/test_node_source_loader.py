from codeograph.passes.pass1.node_source_loader import NodeSourceLoader


def test_load_slices_by_line_range(tmp_path):
    (tmp_path / "Foo.java").write_text(
        "public class Foo {\n    void bar() {}\n    void baz() {}\n}\n",
        encoding="utf-8",
    )

    nodes = [{"id": "Foo", "kind": "class", "source_file": "Foo.java", "line_range": [1, 4]}]
    NodeSourceLoader(tmp_path).load(nodes)

    assert nodes[0]["source_code"] == "public class Foo {\n    void bar() {}\n    void baz() {}\n}"


def test_load_falls_back_to_whole_file_when_line_range_is_regex_fallback_placeholder(tmp_path):
    (tmp_path / "Foo.java").write_text("public class Foo {}\n", encoding="utf-8")

    nodes = [{"id": "Foo", "kind": "class", "source_file": "Foo.java", "line_range": [0, 0]}]
    NodeSourceLoader(tmp_path).load(nodes)

    assert nodes[0]["source_code"] == "public class Foo {}\n"


def test_load_falls_back_to_whole_file_when_line_range_missing(tmp_path):
    (tmp_path / "Foo.java").write_text("public class Foo {}\n", encoding="utf-8")

    nodes = [{"id": "Foo", "kind": "class", "source_file": "Foo.java"}]
    NodeSourceLoader(tmp_path).load(nodes)

    assert nodes[0]["source_code"] == "public class Foo {}\n"


def test_load_skips_node_without_source_file(tmp_path):
    nodes = [{"id": "Foo", "kind": "module"}]
    NodeSourceLoader(tmp_path).load(nodes)

    assert "source_code" not in nodes[0]


def test_load_skips_node_with_unresolvable_source_file(tmp_path):
    nodes = [{"id": "Foo", "kind": "class", "source_file": "DoesNotExist.java", "line_range": [1, 1]}]
    NodeSourceLoader(tmp_path).load(nodes)

    assert "source_code" not in nodes[0]
