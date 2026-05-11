package io.codeograph.corpus.core;

// This file intentionally contains a syntax error to exercise the regex
// fallback path in FileParserDispatcher (the AST parser will reject it).
// The regex extractor captures the class name and package; the golden
// records extraction_mode="regex" for this file.
public class Malformed {
    private String id;
    // missing closing brace — parser.jar exits non-zero, regex fallback activates
