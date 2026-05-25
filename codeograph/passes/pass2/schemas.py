from pydantic import BaseModel, Field


class CrossDomainDependency(BaseModel):
    from_class: str = Field(description="The fully-qualified class name that holds the dependency.")
    from_domain: str = Field(description="The business domain the source class belongs to.")
    to_class: str = Field(description="The class being injected or imported from another domain.")
    to_domain: str = Field(description="The business domain the target class belongs to.")
    dependency_type: str = Field(
        description="How the dependency is expressed: 'injected_field', 'method_param', 'return_type'."
    )


class SynthesisResult(BaseModel):
    description: str = Field(description="2-3 sentences describing what the system does in plain business English.")
    architecture_pattern: str = Field(
        description="Overall architectural pattern (e.g., 'Layered Controller-Service-Repository with domain-driven packaging')."
    )
    domains: list[str] = Field(description="Echoed list of business domain names from the prompt.")
    cross_domain_dependencies: list[CrossDomainDependency] = Field(
        default_factory=list,
        description="Concrete cross-domain dependencies — injected fields only, not general patterns.",
    )
