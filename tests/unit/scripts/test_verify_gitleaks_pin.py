"""Unit tests for the gitleaks version pin-parity verifier script.

Scaffolding is AI-generated; the assertion bodies are learner-write per the
DC5 M12 spec. Each test has a ``# TODO(learner):`` marker.
"""

from __future__ import annotations

from pathlib import Path

from codeograph.scripts import verify_gitleaks_pin as mod


class TestVerifyGitleaksPin:
    """Tests verify_gitleaks_pin script behaves correctly on pin parity/mismatch."""

    def test_main_exits_0_on_matching_pins(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(mod, "get_git_root", lambda: tmp_path)

        workflows = tmp_path / ".github" / "workflows"
        workflows.mkdir(parents=True)

        (workflows / "secrets-scan.yml").write_text(
            'env:\n  GITLEAKS_VERSION: "8.30.1"\n',
            encoding="utf-8",
        )
        (tmp_path / ".pre-commit-config.yaml").write_text(
            '- repo: https://github.com/gitleaks/gitleaks\n  rev: "v8.30.1"\n  hooks:\n    - id: gitleaks\n',
            encoding="utf-8",
        )

        assert mod.main() == 0

    def test_main_exits_1_on_mismatched_pins(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(mod, "get_git_root", lambda: tmp_path)

        workflows = tmp_path / ".github" / "workflows"
        workflows.mkdir(parents=True)

        (workflows / "secrets-scan.yml").write_text(
            'env:\n  GITLEAKS_VERSION: "8.30.1"\n',
            encoding="utf-8",
        )
        (tmp_path / ".pre-commit-config.yaml").write_text(
            '- repo: https://github.com/gitleaks/gitleaks\n  rev: "v8.18.2"\n  hooks:\n    - id: gitleaks\n',
            encoding="utf-8",
        )

        assert mod.main() == 1

    def test_main_exits_1_on_missing_files(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(mod, "get_git_root", lambda: tmp_path)

        assert mod.main() == 1

    def test_main_verifies_nightly_pin_if_present(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(mod, "get_git_root", lambda: tmp_path)

        workflows = tmp_path / ".github" / "workflows"
        workflows.mkdir(parents=True)

        (workflows / "secrets-scan.yml").write_text(
            'env:\n  GITLEAKS_VERSION: "8.30.1"\n',
            encoding="utf-8",
        )
        (tmp_path / ".pre-commit-config.yaml").write_text(
            '- repo: https://github.com/gitleaks/gitleaks\n  rev: "v8.30.1"\n  hooks:\n    - id: gitleaks\n',
            encoding="utf-8",
        )
        (workflows / "nightly.yml").write_text(
            'env:\n  GITLEAKS_VERSION: "8.18.2"\n',
            encoding="utf-8",
        )

        assert mod.main() == 1
