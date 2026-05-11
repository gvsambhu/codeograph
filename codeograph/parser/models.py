"""
Intermediate envelope TypedDicts for the Java parser layer.

These types represent the JSON produced by JavaParserRunner (the fat JAR)
and consumed by FileParserDispatcher before it reaches the graph builder.
They are NOT the final graph.schema.json node types — the graph builder
converts them to GraphNode / GraphEdge objects.

Type hierarchy
--------------
ParsedFile              top-level envelope; one per .java file
  ├─ FieldFact          one per field variable
  │    └─ ColumnFact    JPA @Column metadata (optional)
  ├─ MethodFact         one per method or constructor
  │    ├─ ParameterFact one per parameter
  │    │    └─ BindingFact  Spring binding annotation metadata (optional)
  │    └─ HttpMetadata  HTTP mapping metadata (optional)
  ├─ NameTypePair       record component  (name + type)
  └─ AnnotationElement  annotation member (name + type + default_value)

Design note: ParsedFile uses a required-base / optional-extras split because
different Java kinds (class, interface, enum, record, annotation_type) carry
different fields. The graph builder checks `kind` first, then accesses
kind-specific fields safely. See ADR-003 for the full field catalogue.
"""

from typing import TypedDict

# ---------------------------------------------------------------------------
# Leaf types (no nested TypedDicts)
# ---------------------------------------------------------------------------

class ColumnFact(TypedDict, total=False):
    """
    JPA @Column annotation attributes extracted from a field.

    All three attributes are optional in @Column itself, so every field
    here uses total=False. Absent → the annotation attribute was not set.
    """
    name:     str   | None   # explicit column name; None = JPA default (field name)
    nullable: bool  | None   # False → NOT NULL constraint; None = not specified
    length:   int   | None   # varchar length; None = not specified


class BindingFact(TypedDict):
    """
    Spring parameter-binding annotation metadata for a single method parameter.

    Present when the parameter carries one of:
      @PathVariable, @RequestParam, @RequestBody, @RequestHeader, @ModelAttribute
    """
    kind:          str        # "path" | "query" | "body" | "header" | "model_attribute"
    name:          str | None # explicit binding name from annotation value/name attr
    required:      bool       # annotation's required attribute; Spring default = True
    default_value: str | None # annotation's defaultValue attribute


class HttpMetadata(TypedDict):
    """
    HTTP mapping extracted from a method-level mapping annotation.

    Present when the method carries one of:
      @GetMapping, @PostMapping, @PutMapping, @DeleteMapping,
      @PatchMapping, @RequestMapping
    """
    method: str | None  # "GET" | "POST" | "PUT" | "DELETE" | "PATCH" | None
    path:   str         # URL path pattern; empty string when not specified


class NameTypePair(TypedDict):
    """A name + type pair — used for record components."""
    name: str
    type: str


class AnnotationElement(TypedDict):
    """
    One element declaration inside a Java @interface (annotation type).

    Example:  String value() default "";
      → name="value", type="String", default_value='""'
    """
    name:          str
    type:          str
    default_value: str | None  # stringified default expression; None if absent


# ---------------------------------------------------------------------------
# Composite types
# ---------------------------------------------------------------------------

class ParameterFact(TypedDict):
    """One parameter of a method or constructor."""
    name:        str
    type:        str
    validate:    bool       # True when @Valid or @Validated is present
    constraints: list[str]  # Bean Validation annotation names on this param
    binding:     BindingFact | None


class FieldFact(TypedDict):
    """One field variable in a class or enum body."""
    id:             str         # "<classFqcn>.<fieldName>"
    name:           str
    type:           str
    modifiers:      list[str]
    annotations:    list[str]
    is_autowired:   bool
    is_id:          bool        # True when @Id is present (JPA primary key)
    injection_type: str | None  # "field" | "constructor" | "setter" | None
    qualifier:      str | None  # @Qualifier value, or None
    generation:     str | None  # @GeneratedValue strategy string, or None
    column:         ColumnFact | None
    constraints:    list[str]   # Bean Validation annotation names


class MethodFact(TypedDict):
    """One method or constructor in a class or interface body."""
    id:                     str          # "<classFqcn>#<name>(<param-types>)"
    name:                   str
    return_type:            str          # "void" / type name; FQCN for constructors
    modifiers:              list[str]
    annotations:            list[str]
    is_constructor:         bool
    line_range:             list[int]    # [begin, end]
    parameters:             list[ParameterFact]
    is_bean_factory:        bool         # @Bean
    exception_handler:      bool         # @ExceptionHandler
    response_body:          bool         # @ResponseBody
    response_status:        str | None   # @ResponseStatus value string; int resolution needs symbol solver
    http_metadata:          HttpMetadata | None
    cyclomatic_complexity:  int | None   # populated by M7; None here
    cognitive_complexity:   int | None   # populated by M7; None here
    method_loc:             int | None   # populated by M7; None here
    calls:                  list[str]    # raw MethodCallExpr strings from body


# ---------------------------------------------------------------------------
# Top-level envelope
# ---------------------------------------------------------------------------

class _ParsedFileBase(TypedDict):
    """
    Fields guaranteed to be present in every intermediate envelope,
    regardless of Java kind.
    """
    kind:            str       # "class"|"interface"|"enum"|"record"|"annotation_type"
    id:              str       # fully-qualified class/interface/enum name
    name:            str       # simple name
    source_file:     str       # corpus-relative path, forward slashes
    extraction_mode: str       # "ast" (JAR) | "regex" (fallback)
    annotations:     list[str] # annotation simple names on the type declaration
    imports:         list[str] # fully-qualified import strings


class ParsedFile(_ParsedFileBase, total=False):
    """
    Complete intermediate envelope for one .java file.

    Kind-specific fields are optional (total=False on this subclass).
    The graph builder checks `kind` before accessing kind-specific keys.

    Present by kind:
      class            — modifiers, stereotype, superclass, implements,
                         is_inner_class, table_name, entry_point,
                         fields, methods, wmc, cbo, lcom4
      interface        — modifiers, extends_interfaces, methods
      enum             — modifiers, constants, implements, fields, methods
      record           — components, implements
      annotation_type  — modifiers, elements
    """
    line_range: list[int]   # [begin_line, end_line]; base keeps it optional
                            # because regex fallback may not know the range

    # --- present for class, interface, enum, annotation_type ---
    modifiers: list[str]

    # --- present for class, enum ---
    implements: list[str]
    fields:     list[FieldFact]
    methods:    list[MethodFact]

    # --- class-only ---
    stereotype:    str | None
    superclass:    str | None
    is_inner_class: bool
    table_name:    str | None
    entry_point:   bool
    wmc:           int | None    # Weighted Methods per Class; M7
    cbo:           int | None    # Coupling Between Objects; M7
    lcom4:         float | None  # Lack of Cohesion of Methods 4; M7

    # --- interface-only ---
    extends_interfaces: list[str]

    # --- interface also has methods ---
    # (already declared above under class/enum; same key, same type)

    # --- enum-only ---
    constants: list[str]

    # --- record-only ---
    components: list[NameTypePair]

    # --- annotation_type-only ---
    elements: list[AnnotationElement]
