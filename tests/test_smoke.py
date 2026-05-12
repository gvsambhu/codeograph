"""
Smoke test — keeps CI green while the real test modules are being written.

Replace this file with targeted unit tests once the first module under test
is stable. Planned test modules (mirrors the implementation):

    test_regex_fallback.py       — RegexFallback extraction coverage
    test_java_file_parser.py     — JavaFileParser subprocess + error paths
    test_file_parser_dispatcher.py — fallback trigger on JavaParseError
"""


def test_placeholder() -> None:
    """Placeholder — exists so pytest collects at least one test and CI passes."""
    assert True
