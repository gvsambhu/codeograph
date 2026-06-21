from typing import Literal

from pydantic import BaseModel, Field


class HttpMetadata(BaseModel):
    http_method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"] = Field(description="The HTTP method used.")
    path: str = Field(
        description=(
            "The full absolute HTTP path including class-level @RequestMapping prefixes "
            "(e.g., '/api/v1/orders' not just '/orders')."
        )
    )
    request_body_type: str | None = Field(None, description="The semantic type of the @RequestBody parameter.")
    response_type: str | None = Field(None, description="The semantic type inside ResponseEntity<...>.")


class MethodAnnotation(BaseModel):
    name: str = Field(description="The exact method name")
    signature: str = Field(description="Full signature including return type, name, and parameter list")
    kind: Literal["business", "lifecycle", "constructor", "utility"] = Field(
        description=(
            "Classifies the method type: 'business' for domain logic, 'lifecycle' for @PostConstruct/@PreDestroy, "
            "'constructor' for DI constructors, 'utility' for private helpers promoted to public."
        )
    )
    return_type: str = Field(description="Just the return type")
    method_annotations: list[str] = Field(description="All annotations on the method")
    description: str = Field(description="One sentence from the caller's perspective in plain English")
    conversion_difficulty: Literal["Low", "Medium", "High"] = Field(
        description="Low (direct mapping), Medium (needs adaptation), High (complex translation)"
    )
    conversion_notes: str = Field(description="1-2 sentences of specific guidance for the conversion engineer")
    http_metadata: HttpMetadata | None = Field(
        None,
        description="Provide for methods on CONTROLLER or RestController classes only; null for all other stereotypes.",
    )


# Stereotype values mirror graph_schema.Stereotype — kept in sync with ADR-003 §9.
_StereotypeLiteral = Literal[
    "Component",
    "Service",
    "Repository",
    "Controller",
    "RestController",
    "Configuration",
    "ControllerAdvice",
    "Entity",
    "SpringBootApplication",
]


class NodeAnnotation(BaseModel):
    """LLM-response schema for Pass 1 per-node annotation.

    Every field except `conversion_notes` is required. The orchestrator
    injects `node_id` and `stereotype` into the prompt; the LLM echoes
    them back verbatim so the annotation is self-contained and correlatable.
    """

    node_id: str = Field(description="The unique graph node ID provided in the prompt — echo it back verbatim.")
    class_name: str = Field(description="The exact class name as declared.")
    stereotype: _StereotypeLiteral | None = Field(
        description=(
            "The architectural stereotype provided in the prompt — echo it back verbatim. "
            "Null if the class carries no recognised Spring stereotype."
        )
    )
    domain_hint: str = Field(
        description=(
            "The business domain this class belongs to (e.g., 'order management', 'user identity'). "
            "Use business language, not package names."
        )
    )
    description: str = Field(description="1-2 sentences explaining the class responsibility. Use business language.")
    conversion_notes: str | None = Field(
        default=None,
        description=(
            "Class-level migration guidance for the conversion engineer — use when the entire class "
            "has a cross-cutting concern (e.g., heavy AOP usage, class-level @Transactional, unusual inheritance). "
            "Omit when there is nothing noteworthy at the class level."
        ),
    )
    methods: list[MethodAnnotation] = Field(
        default_factory=list,
        description="All public and protected methods. Empty only when the class has none.",
    )


class AnnotationRecord(BaseModel):
    """Stored artifact unit in llm-annotations.json.

    Separates orchestrator-owned state (`degraded`, `extraction_mode`) from
    the LLM-response schema (`NodeAnnotation`).

    When `degraded` is True and `extraction_mode` is ``"signatures_only"``,
    the node was oversized (ADR-005 O3 / D-005-1): signatures were extracted
    and sent to the LLM, producing a degraded-but-real annotation.
    When `annotation` is also None, the signatures-only LLM call itself failed.
    """

    node_id: str = Field(description="Graph node ID — matches NodeAnnotation.node_id when annotation is present.")
    degraded: bool = Field(False, description="True when the orchestrator processed this node in degraded mode.")
    annotation: NodeAnnotation | None = Field(None, description="The LLM-produced annotation. None on total failure.")
    extraction_mode: str | None = None
