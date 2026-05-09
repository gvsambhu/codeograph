"""
codeograph.parser — per-file Java structural extraction.

Public surface:
    FileParserDispatcher  primary entry point; tries AST then regex fallback
    ParsedFile            TypedDict for the intermediate envelope
    JavaParseError        raised by JavaFileParser on non-zero JAR exit
"""

from codeograph.parser.file_parser_dispatcher import FileParserDispatcher
from codeograph.parser.java_file_parser import JavaFileParser, JavaParseError
from codeograph.parser.models import ParsedFile
from codeograph.parser.regex_fallback import RegexFallback

__all__ = [
    "FileParserDispatcher",
    "JavaFileParser",
    "JavaParseError",
    "ParsedFile",
    "RegexFallback",
]
