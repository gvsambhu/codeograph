"""Tests for TypeScriptConfig (M5 — ADR-010).

Verifies defaults, field validation, and extra='forbid' policy.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from codeograph.renderers.typescript_nestjs.typescript_config import TypeScriptConfig


class TestTypeScriptConfigDefaults:
    def test_all_defaults_instantiate_cleanly(self):
        cfg = TypeScriptConfig()
        assert cfg.db_layer == "typeorm"
        assert cfg.db_adapter == "pg"
        assert cfg.render_strategy == "from_manifest"
        assert cfg.render_budget == 50
        assert cfg.domain_mapping == {}
        assert cfg.unsupported_feature_policy == "stub_todo"
        assert cfg.security_feature_policy == "refuse"
        assert cfg.webflux_policy == "refuse"
        assert cfg.include_scaffold is True
        assert cfg.strict is True

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError, match="extra_inputs_not_permitted|Extra"):
            TypeScriptConfig(**{"db_layer": "typeorm", "unknown_field": "bad"})  # type: ignore[call-arg]


class TestTypeScriptConfigValidation:
    def test_invalid_db_layer_raises(self):
        with pytest.raises(ValidationError):
            TypeScriptConfig(db_layer="prisma")  # type: ignore[arg-type]

    def test_invalid_db_adapter_raises(self):
        with pytest.raises(ValidationError):
            TypeScriptConfig(db_adapter="mysql2")  # type: ignore[arg-type]

    def test_render_budget_below_minimum_raises(self):
        with pytest.raises(ValidationError, match="greater_than_equal|ge"):
            TypeScriptConfig(render_budget=0)

    def test_render_budget_above_maximum_raises(self):
        with pytest.raises(ValidationError, match="less_than_equal|le"):
            TypeScriptConfig(render_budget=501)

    def test_render_budget_at_boundaries_accepted(self):
        cfg_low = TypeScriptConfig(render_budget=1)
        assert cfg_low.render_budget == 1
        cfg_high = TypeScriptConfig(render_budget=500)
        assert cfg_high.render_budget == 500

    def test_invalid_unsupported_feature_policy_raises(self):
        # "refuse" was removed from UnsupportedFeaturePolicy in the 2026-05-28 fixup
        # (no deterministic class-level signal exists; see ADR-010 Amendments).
        with pytest.raises(ValidationError):
            TypeScriptConfig(unsupported_feature_policy="refuse")  # type: ignore[arg-type]

    def test_invalid_security_feature_policy_raises(self):
        with pytest.raises(ValidationError):
            TypeScriptConfig(security_feature_policy="allow")  # type: ignore[arg-type]

    def test_invalid_webflux_policy_raises(self):
        with pytest.raises(ValidationError):
            TypeScriptConfig(webflux_policy="stub_with_todo")  # type: ignore[arg-type]


class TestTypeScriptConfigOverrides:
    def test_domain_mapping_override(self):
        cfg = TypeScriptConfig(domain_mapping={"com.example.orders": "orders"})
        assert cfg.domain_mapping == {"com.example.orders": "orders"}

    def test_no_scaffold_override(self):
        cfg = TypeScriptConfig(include_scaffold=False)
        assert cfg.include_scaffold is False

    def test_non_strict_tsconfig(self):
        cfg = TypeScriptConfig(strict=False)
        assert cfg.strict is False

    def test_better_sqlite3_adapter(self):
        cfg = TypeScriptConfig(db_adapter="better-sqlite3")
        assert cfg.db_adapter == "better-sqlite3"
