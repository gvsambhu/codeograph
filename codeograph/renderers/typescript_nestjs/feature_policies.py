"""Feature policies for TypeScript/NestJS rendering (ADR-010)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codeograph.graph.models.graph_schema import ClassNode
    from codeograph.renderers.typescript_nestjs.typescript_config import TypeScriptConfig


# Spring Security annotation simple names that trigger security_feature_policy.
# Source: Spring Security 6 reference, §Method Security and §Web Security.
_SPRING_SECURITY_ANNOTATIONS: frozenset[str] = frozenset(
    {
        "PreAuthorize",
        "PostAuthorize",
        "Secured",
        "RolesAllowed",
        "PreFilter",
        "PostFilter",
        "EnableWebSecurity",
        "EnableMethodSecurity",
        "WithMockUser",  # test annotations — also trigger the policy
    }
)


def dispatch_feature_policies(
    class_node: ClassNode,
    annotations: dict[str, object],
    config: TypeScriptConfig,
) -> dict[str, str] | str | None:
    """Evaluate feature policies for *class_node*.

    Returns:
        A dict of prompt hints to inject when the class should be rendered.
        A ``str`` refuse-reason (e.g. ``"security"``, ``"webflux_refuse"``,
        ``"webflux_flux_only"``) when the class is skipped by policy.
        ``None`` is never returned — callers treat ``str`` as a skip signal
        and ``dict`` (possibly empty) as a render signal.
    """
    hints: dict[str, str] = {}

    # --- Spring Security policy ---
    class_annotations: set[str] = set(class_node.annotations or [])
    security_hits = _SPRING_SECURITY_ANNOTATIONS & class_annotations
    if security_hits:
        if config.security_feature_policy == "refuse":
            return "security"  # DC3-05: named refuse reason
        elif config.security_feature_policy == "stub_todo":
            hints["security_hint"] = (
                f"This class carries Spring Security annotation(s): "
                f"{', '.join(sorted(security_hits))}. "
                f"Emit a NestJS @UseGuards() decorator stub with a "
                f"// TODO(learner): replace with a real Guard implementation."
            )

    # --- WebFlux policy ---
    record = annotations.get(class_node.id)
    _methods: list[object] = []
    if isinstance(record, dict):
        ann = record.get("annotation") or {}
        if isinstance(ann, dict):
            methods_raw = ann.get("methods", [])
            if isinstance(methods_raw, list):
                _methods = methods_raw

    uses_mono = any("Mono<" in (m.get("return_type") or "") for m in _methods if isinstance(m, dict))
    uses_flux = any("Flux<" in (m.get("return_type") or "") for m in _methods if isinstance(m, dict))
    uses_webflux = uses_mono or uses_flux

    if uses_webflux:
        if config.webflux_policy == "refuse":
            return "webflux_refuse"  # DC3-05: named refuse reason
        if config.webflux_policy == "translate_mono_only":
            if uses_flux:
                return "webflux_flux_only"  # DC3-05: named refuse reason
            hints["webflux_hint"] = (
                "This class uses Spring WebFlux reactive return types. "
                "Translate Mono<T> to Promise<T> and render async NestJS methods. "
                "Do not use RxJS Observable. "
                "If a Flux<T> shape cannot be represented under this policy, emit a TODO stub."
            )
        elif config.webflux_policy == "best_effort":
            hints["webflux_hint"] = (
                "This class uses Spring WebFlux reactive return types. "
                "Translate Mono<T> to Promise<T> and Flux<T> to Observable<T> from rxjs. "
                "Import Observable when needed and preserve any unclear reactive semantics with TODO stubs."
            )

    return hints
