"""Cross-renderer utilities: class selection, domain grouping (ADR-008, ADR-009).

Public surface:
    ClassSelector    — budget-aware class selection (ADR-009 three-tier ladder)
    SelectionResult  — frozen value object returned by ClassSelector.select()
    DomainGrouping   — ABC for package → module-name mapping strategies
    PackagePrefixGrouping — auto-detect grouping from longest common prefix
    ManualMappingGrouping — explicit {package_prefix: group_name} mapping
"""

from codeograph.rendering.class_selector import ClassSelector
from codeograph.rendering.models import SelectionResult
from codeograph.rendering.base import DomainGrouping
from codeograph.rendering.package_prefix_grouping import PackagePrefixGrouping
from codeograph.rendering.manual_mapping_grouping import ManualMappingGrouping

__all__ = [
    "ClassSelector",
    "DomainGrouping",
    "ManualMappingGrouping",
    "PackagePrefixGrouping",
    "SelectionResult",
]
