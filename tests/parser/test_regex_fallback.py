"""
Unit tests for RegexFallback (codeograph/parser/regex_fallback.py).

All tests use tmp_path to write real .java files — no mocking needed.
RegexFallback only reads file text via Path.read_text, so real files are
the simplest and most faithful way to drive it.

Coverage plan:
  - package declaration → fqcn and id
  - no package → simple name as id
  - annotations before class decl → annotations list + stereotype detection
  - imports → imports list (static / wildcard included)
  - field declarations → type + name (various modifier combinations)
  - method signatures → return_type + name (no false positives for keywords)
  - kind mapping: class / interface / enum / record / @interface
  - unreadable file (OSError) → minimal empty envelope, no exception raised
  - no type declaration found → minimal empty envelope
  - extraction_mode is always "regex"
  - interface kind → has extends_interfaces key
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codeograph.parser.regex_fallback import RegexFallback

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fb() -> RegexFallback:
    return RegexFallback()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(tmp_path: Path, filename: str, source: str) -> tuple[Path, Path]:
    """Write source to tmp_path/filename. Returns (file_path, corpus_root)."""
    p = tmp_path / filename
    p.write_text(source, encoding="utf-8")
    return p, tmp_path


# ---------------------------------------------------------------------------
# TestPackageAndId
# ---------------------------------------------------------------------------

class TestPackageAndId:

    def test_package_builds_fqcn(self, fb: RegexFallback, tmp_path: Path) -> None:
        src = "package com.example.service;\npublic class OrderService {}\n"
        f, root = _write(tmp_path, "OrderService.java", src)
        pf = fb.parse(f, root)
        assert pf["id"] == "com.example.service.OrderService"
        assert pf["name"] == "OrderService"

    def test_no_package_uses_simple_name(self, fb: RegexFallback, tmp_path: Path) -> None:
        src = "public class Standalone {}\n"
        f, root = _write(tmp_path, "Standalone.java", src)
        pf = fb.parse(f, root)
        assert pf["id"] == "Standalone"
        assert pf["name"] == "Standalone"

    def test_source_file_relative_to_corpus_root(self, fb: RegexFallback, tmp_path: Path) -> None:
        sub = tmp_path / "src" / "main"
        sub.mkdir(parents=True)
        f = sub / "Foo.java"
        f.write_text("public class Foo {}\n", encoding="utf-8")
        pf = fb.parse(f, tmp_path)
        # POSIX separators in source_file regardless of OS
        assert pf["source_file"] == "src/main/Foo.java"

    def test_extraction_mode_always_regex(self, fb: RegexFallback, tmp_path: Path) -> None:
        src = "package a.b;\npublic class X {}\n"
        f, root = _write(tmp_path, "X.java", src)
        pf = fb.parse(f, root)
        assert pf["extraction_mode"] == "regex"


# ---------------------------------------------------------------------------
# TestAnnotationsAndStereotype
# ---------------------------------------------------------------------------

class TestAnnotationsAndStereotype:

    def test_annotations_before_class_decl(self, fb: RegexFallback, tmp_path: Path) -> None:
        src = (
            "package com.example;\n"
            "@RestController\n"
            "@RequestMapping(\"/api\")\n"
            "public class ApiCtrl {}\n"
        )
        f, root = _write(tmp_path, "ApiCtrl.java", src)
        pf = fb.parse(f, root)
        assert "RestController" in pf["annotations"]
        assert "RequestMapping" in pf["annotations"]

    def test_stereotype_detected_for_service(self, fb: RegexFallback, tmp_path: Path) -> None:
        src = (
            "package com.example;\n"
            "@Service\n"
            "public class OrderService {}\n"
        )
        f, root = _write(tmp_path, "OrderService.java", src)
        pf = fb.parse(f, root)
        assert pf["stereotype"] == "Service"

    def test_stereotype_none_when_no_matching_annotation(
        self, fb: RegexFallback, tmp_path: Path
    ) -> None:
        src = "package com.example;\n@SomeCustomAnnotation\npublic class Foo {}\n"
        f, root = _write(tmp_path, "Foo.java", src)
        pf = fb.parse(f, root)
        assert pf["stereotype"] is None

    def test_annotations_inside_body_not_included(self, fb: RegexFallback, tmp_path: Path) -> None:
        """Annotations on fields / methods must not leak into class-level annotations."""
        src = (
            "package com.example;\n"
            "public class Repo {\n"
            "    @Autowired\n"
            "    private OrderService svc;\n"
            "}\n"
        )
        f, root = _write(tmp_path, "Repo.java", src)
        pf = fb.parse(f, root)
        assert "Autowired" not in pf["annotations"]

    def test_entry_point_true_for_spring_boot_application(
        self, fb: RegexFallback, tmp_path: Path
    ) -> None:
        src = (
            "package com.example;\n"
            "@SpringBootApplication\n"
            "public class App {}\n"
        )
        f, root = _write(tmp_path, "App.java", src)
        pf = fb.parse(f, root)
        assert pf["entry_point"] is True

    def test_entry_point_false_without_annotation(self, fb: RegexFallback, tmp_path: Path) -> None:
        src = "package com.example;\npublic class Plain {}\n"
        f, root = _write(tmp_path, "Plain.java", src)
        pf = fb.parse(f, root)
        assert pf["entry_point"] is False


# ---------------------------------------------------------------------------
# TestImports
# ---------------------------------------------------------------------------

class TestImports:

    def test_regular_imports(self, fb: RegexFallback, tmp_path: Path) -> None:
        src = (
            "package com.example;\n"
            "import java.util.List;\n"
            "import java.util.Map;\n"
            "public class Foo {}\n"
        )
        f, root = _write(tmp_path, "Foo.java", src)
        pf = fb.parse(f, root)
        assert "java.util.List" in pf["imports"]
        assert "java.util.Map" in pf["imports"]

    def test_static_import(self, fb: RegexFallback, tmp_path: Path) -> None:
        src = (
            "package com.example;\n"
            "import static org.junit.Assert.assertEquals;\n"
            "public class Foo {}\n"
        )
        f, root = _write(tmp_path, "Foo.java", src)
        pf = fb.parse(f, root)
        assert "org.junit.Assert.assertEquals" in pf["imports"]

    def test_wildcard_import(self, fb: RegexFallback, tmp_path: Path) -> None:
        src = (
            "package com.example;\n"
            "import java.util.*;\n"
            "public class Foo {}\n"
        )
        f, root = _write(tmp_path, "Foo.java", src)
        pf = fb.parse(f, root)
        assert "java.util.*" in pf["imports"]

    def test_no_imports(self, fb: RegexFallback, tmp_path: Path) -> None:
        src = "package com.example;\npublic class Bare {}\n"
        f, root = _write(tmp_path, "Bare.java", src)
        pf = fb.parse(f, root)
        assert pf["imports"] == []


# ---------------------------------------------------------------------------
# TestFields
# ---------------------------------------------------------------------------

class TestFields:

    def _field_names(self, pf: dict) -> list[str]:
        return [ff["name"] for ff in pf["fields"]]

    def _field_types(self, pf: dict) -> dict[str, str]:
        return {ff["name"]: ff["type"] for ff in pf["fields"]}

    def test_private_field_extracted(self, fb: RegexFallback, tmp_path: Path) -> None:
        src = (
            "package com.example;\n"
            "public class Svc {\n"
            "    private OrderRepository orderRepo;\n"
            "}\n"
        )
        f, root = _write(tmp_path, "Svc.java", src)
        pf = fb.parse(f, root)
        assert "orderRepo" in self._field_names(pf)

    def test_field_type_captured(self, fb: RegexFallback, tmp_path: Path) -> None:
        src = (
            "package com.example;\n"
            "public class Svc {\n"
            "    private OrderRepository orderRepo;\n"
            "}\n"
        )
        f, root = _write(tmp_path, "Svc.java", src)
        pf = fb.parse(f, root)
        types = self._field_types(pf)
        assert types["orderRepo"] == "OrderRepository"

    def test_private_final_field(self, fb: RegexFallback, tmp_path: Path) -> None:
        src = (
            "package com.example;\n"
            "public class Svc {\n"
            "    private final String name;\n"
            "}\n"
        )
        f, root = _write(tmp_path, "Svc.java", src)
        pf = fb.parse(f, root)
        assert "name" in self._field_names(pf)

    def test_field_id_is_fqcn_dot_name(self, fb: RegexFallback, tmp_path: Path) -> None:
        src = (
            "package com.example;\n"
            "public class Svc {\n"
            "    private String label;\n"
            "}\n"
        )
        f, root = _write(tmp_path, "Svc.java", src)
        pf = fb.parse(f, root)
        ids = [ff["id"] for ff in pf["fields"]]
        assert "com.example.Svc.label" in ids

    def test_field_metadata_defaults(self, fb: RegexFallback, tmp_path: Path) -> None:
        """Regex path cannot recover injection metadata — defaults must be safe."""
        src = (
            "package com.example;\n"
            "public class Svc {\n"
            "    private OrderRepository repo;\n"
            "}\n"
        )
        f, root = _write(tmp_path, "Svc.java", src)
        pf = fb.parse(f, root)
        field = pf["fields"][0]
        assert field["is_autowired"] is False
        assert field["is_id"] is False
        assert field["injection_type"] is None
        assert field["annotations"] == []

    def test_no_fields_in_empty_class(self, fb: RegexFallback, tmp_path: Path) -> None:
        src = "package com.example;\npublic class Empty {}\n"
        f, root = _write(tmp_path, "Empty.java", src)
        pf = fb.parse(f, root)
        assert pf["fields"] == []


# ---------------------------------------------------------------------------
# TestMethods
# ---------------------------------------------------------------------------

class TestMethods:

    def _method_names(self, pf: dict) -> list[str]:
        return [m["name"] for m in pf["methods"]]

    def test_public_method_extracted(self, fb: RegexFallback, tmp_path: Path) -> None:
        src = (
            "package com.example;\n"
            "public class Svc {\n"
            "    public Order findById(Long id) {\n"
            "        return null;\n"
            "    }\n"
            "}\n"
        )
        f, root = _write(tmp_path, "Svc.java", src)
        pf = fb.parse(f, root)
        assert "findById" in self._method_names(pf)

    def test_method_return_type_captured(self, fb: RegexFallback, tmp_path: Path) -> None:
        src = (
            "package com.example;\n"
            "public class Svc {\n"
            "    public Order findById(Long id) { return null; }\n"
            "}\n"
        )
        f, root = _write(tmp_path, "Svc.java", src)
        pf = fb.parse(f, root)
        m = next(m for m in pf["methods"] if m["name"] == "findById")
        assert m["return_type"] == "Order"

    def test_method_id_uses_empty_parens(self, fb: RegexFallback, tmp_path: Path) -> None:
        """Regex cannot recover param types — id must use () without param types."""
        src = (
            "package com.example;\n"
            "public class Svc {\n"
            "    public void doWork(String s, int n) {}\n"
            "}\n"
        )
        f, root = _write(tmp_path, "Svc.java", src)
        pf = fb.parse(f, root)
        m = next(m for m in pf["methods"] if m["name"] == "doWork")
        assert m["id"] == "com.example.Svc#doWork()"

    def test_keyword_noise_not_extracted_as_method(self, fb: RegexFallback, tmp_path: Path) -> None:
        """Control-flow keywords must not be mistaken for method names."""
        src = (
            "package com.example;\n"
            "public class Svc {\n"
            "    public void realMethod() {\n"
            "        if (true) { return; }\n"
            "        for (int i = 0; i < 10; i++) {}\n"
            "    }\n"
            "}\n"
        )
        f, root = _write(tmp_path, "Svc.java", src)
        pf = fb.parse(f, root)
        names = self._method_names(pf)
        assert "if" not in names
        assert "for" not in names
        assert "realMethod" in names

    def test_method_metadata_defaults(self, fb: RegexFallback, tmp_path: Path) -> None:
        src = (
            "package com.example;\n"
            "public class Svc {\n"
            "    public void process() {}\n"
            "}\n"
        )
        f, root = _write(tmp_path, "Svc.java", src)
        pf = fb.parse(f, root)
        m = pf["methods"][0]
        assert m["parameters"] == []
        assert m["calls"] == []
        assert m["http_metadata"] is None
        assert m["cyclomatic_complexity"] is None
        assert m["is_constructor"] is False

    def test_no_methods_in_empty_class(self, fb: RegexFallback, tmp_path: Path) -> None:
        src = "package com.example;\npublic class Empty {}\n"
        f, root = _write(tmp_path, "Empty.java", src)
        pf = fb.parse(f, root)
        assert pf["methods"] == []


# ---------------------------------------------------------------------------
# TestKindMapping
# ---------------------------------------------------------------------------

class TestKindMapping:

    def test_class_kind(self, fb: RegexFallback, tmp_path: Path) -> None:
        src = "package com.example;\npublic class Foo {}\n"
        f, root = _write(tmp_path, "Foo.java", src)
        assert fb.parse(f, root)["kind"] == "class"

    def test_interface_kind(self, fb: RegexFallback, tmp_path: Path) -> None:
        src = "package com.example;\npublic interface IRepo {}\n"
        f, root = _write(tmp_path, "IRepo.java", src)
        pf = fb.parse(f, root)
        assert pf["kind"] == "interface"
        # Interface nodes carry extends_interfaces key
        assert "extends_interfaces" in pf

    def test_enum_kind(self, fb: RegexFallback, tmp_path: Path) -> None:
        src = "package com.example;\npublic enum Status { OPEN, CLOSED }\n"
        f, root = _write(tmp_path, "Status.java", src)
        assert fb.parse(f, root)["kind"] == "enum"

    def test_record_kind(self, fb: RegexFallback, tmp_path: Path) -> None:
        src = "package com.example;\npublic record Point(int x, int y) {}\n"
        f, root = _write(tmp_path, "Point.java", src)
        assert fb.parse(f, root)["kind"] == "record"

    def test_annotation_type_kind(self, fb: RegexFallback, tmp_path: Path) -> None:
        src = "package com.example;\npublic @interface MyAnnotation {}\n"
        f, root = _write(tmp_path, "MyAnnotation.java", src)
        assert fb.parse(f, root)["kind"] == "annotation_type"


# ---------------------------------------------------------------------------
# TestErrorPaths
# ---------------------------------------------------------------------------

class TestErrorPaths:

    def test_unreadable_file_returns_envelope_no_exception(
        self, fb: RegexFallback, tmp_path: Path
    ) -> None:
        """RegexFallback must never raise — simulate OSError via a non-existent path."""
        # Pass a non-existent file; read_text will raise OSError internally.
        missing = tmp_path / "Ghost.java"
        # We need a corpus_root that doesn't cause relative_to() to fail.
        # Use a partial workaround: write a stub, then remove it immediately.
        missing.write_text("", encoding="utf-8")
        missing.unlink()

        # Should not raise
        pf = fb.parse(missing, tmp_path)
        # Must return a minimal envelope
        assert pf["extraction_mode"] == "regex"
        assert pf["source_file"] == "Ghost.java"
        assert pf["annotations"] == []
        assert pf["imports"] == []

    def test_no_type_decl_returns_empty_envelope(self, fb: RegexFallback, tmp_path: Path) -> None:
        """A file with no class/interface/enum/record → empty envelope."""
        src = "// Just a comment\nimport java.util.List;\n"
        f, root = _write(tmp_path, "NoDecl.java", src)
        pf = fb.parse(f, root)
        assert pf["extraction_mode"] == "regex"
        # id falls back to dotted path from source_file
        assert "NoDecl" in pf["id"]
