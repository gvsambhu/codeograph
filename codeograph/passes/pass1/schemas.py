from typing import Literal, Optional
from pydantic import BaseModel, Field

class HttpMetadata(BaseModel):
    http_method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"] = Field(
        description="The HTTP method used."
    )
    path: str = Field(
        description="The full absolute HTTP path including class-level @RequestMapping prefixes (e.g., '/api/v1/orders' not just '/orders')."
    )
    request_body_type: Optional[str] = Field(
        None, description="The semantic type of the @RequestBody parameter."
    )
    response_type: Optional[str] = Field(
        None, description="The semantic type inside ResponseEntity<...>."
    )

class MethodAnnotation(BaseModel):
    name: str = Field(description="The exact method name")
    signature: str = Field(description="Full signature including return type, name, and parameter list")
    kind: Literal["business", "lifecycle", "constructor", "utility"] = Field(
        description="Classifies the method type to help focus on business logic."
    )
    return_type: str = Field(description="Just the return type")
    method_annotations: list[str] = Field(description="All annotations on the method")
    description: str = Field(description="One sentence from the caller's perspective in plain English")
    conversion_difficulty: Literal["Low", "Medium", "High"] = Field(
        description="Low (direct mapping), Medium (needs adaptation), High (complex translation)"
    )
    conversion_notes: str = Field(
        description="1-2 sentences of specific guidance for the conversion engineer"
    )
    http_metadata: Optional[HttpMetadata] = Field(
        None, description="Only provided if the class is a CONTROLLER."
    )

class NodeAnnotation(BaseModel):
    node_id: str = Field(
        description="The unique graph node ID provided in the prompt."
    )
    degraded: bool = Field(
        False, description="Set to True by the orchestrator if this node was skipped due to size limits."
    )
    class_name: str = Field(description="The exact class name as declared.")
    stereotype: str = Field(
        description="The architectural stereotype (e.g., CONTROLLER, SERVICE, REPOSITORY, COMPONENT) provided in the prompt."
    )
    domain_hint: str = Field(
        description="The business domain this class belongs to (e.g., 'order management', 'user identity'). Use business language, not package names."
    )
    description: str = Field(
        description="1-2 sentences explaining the class responsibility. Use business language."
    )
    methods: list[MethodAnnotation] = Field(
        default_factory=list,
        description="List of all public and protected methods."
    )
