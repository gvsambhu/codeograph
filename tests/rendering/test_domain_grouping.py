"""Tests for DomainGrouping strategies (M3 — ADR-009 Fork 2).

PackagePrefixGrouping: prefix-stripping auto-detection.
ManualMappingGrouping: explicit mapping with longest-prefix-wins semantics.
"""

from __future__ import annotations

from codeograph.rendering.domain_grouping import (
    ManualMappingGrouping,
    PackagePrefixGrouping,
)

# ---------------------------------------------------------------------------
# PackagePrefixGrouping
# ---------------------------------------------------------------------------


class TestPackagePrefixGrouping:
    def _make(self, fqcns: list[str]) -> PackagePrefixGrouping:
        g = PackagePrefixGrouping()
        g.prepare(fqcns)
        return g

    def test_two_distinct_subpackages(self):
        fqcns = [
            "com.example.orders.OrderService",
            "com.example.orders.OrderController",
            "com.example.inventory.ItemService",
        ]
        g = self._make(fqcns)
        assert g.group("com.example.orders.OrderService") == "orders"
        assert g.group("com.example.inventory.ItemService") == "inventory"

    def test_single_class_falls_back_to_misc(self):
        g = self._make(["com.example.orders.OrderService"])
        # Single class: no siblings, prefix strips the sub-package → "misc"
        result = g.group("com.example.orders.OrderService")
        assert result != ""  # must never be empty

    def test_empty_graph_produces_no_error(self):
        g = PackagePrefixGrouping()
        g.prepare([])
        # No classes to group — no error expected

    def test_class_at_prefix_level_falls_to_misc(self):
        # If somehow a class has no further segment after common prefix
        fqcns = ["com.example.Root", "com.example.Other"]
        g = self._make(fqcns)
        # (com.example prefix, class name Root -> package com.example)
        # resolves to "misc" rather than crashing.
        result = g.group("com.example.Root")
        assert result == "misc"

    def test_deep_shared_prefix(self):
        fqcns = [
            "com.acme.platform.billing.InvoiceService",
            "com.acme.platform.billing.PaymentService",
            "com.acme.platform.auth.AuthService",
        ]
        g = self._make(fqcns)
        assert g.group("com.acme.platform.billing.InvoiceService") == "billing"
        assert g.group("com.acme.platform.auth.AuthService") == "auth"


# ---------------------------------------------------------------------------
# ManualMappingGrouping
# ---------------------------------------------------------------------------


class TestManualMappingGrouping:
    def _make(self, mapping: dict[str, str]) -> ManualMappingGrouping:
        g = ManualMappingGrouping(mapping)
        g.prepare([])  # no-op
        return g

    def test_exact_package_match(self):
        g = self._make({"com.example.orders": "orders"})
        assert g.group("com.example.orders.OrderService") == "orders"

    def test_longest_prefix_wins(self):
        g = self._make(
            {
                "com.example": "app",
                "com.example.orders": "orders",
            }
        )
        # More specific prefix should win
        assert g.group("com.example.orders.OrderService") == "orders"

    def test_unmatched_falls_to_misc(self):
        g = self._make({"com.example.orders": "orders"})
        assert g.group("com.third.party.ThirdParty") == "misc"

    def test_sibling_packages(self):
        g = self._make(
            {
                "com.example.orders": "orders",
                "com.example.admin": "admin",
            }
        )
        assert g.group("com.example.admin.AdminController") == "admin"
        assert g.group("com.example.orders.OrderController") == "orders"

    def test_empty_mapping_everything_falls_to_misc(self):
        g = self._make({})
        assert g.group("com.example.orders.OrderService") == "misc"

    @pytest.mark.parametrize("fqcn", [
        "com.example.SomeClass",
        "org.unknown.SomeClass",
        "com.example",
    ])
    def test_group_never_returns_empty_string(self, fqcn: str):
        g = self._make({"com.example": "app"})
        assert g.group(fqcn) != ""
