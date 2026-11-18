"""A source location carrying a secret is refused before anything is written or echoed."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from codeograph.cli.main import cli
from codeograph.input.acquirers.base_acquirer import AcquisitionError
from codeograph.input.input_acquirer import InputAcquirer
from codeograph.input.source_location import carries_secret, redact_source_location

SECRET_LOCATIONS = [
    ("https://user:s3cr3t@host.example/org/repo.git", "https://host.example/org/repo.git"),
    ("https://s3cr3t@host.example/org/repo.git", "https://host.example/org/repo.git"),
    ("http://user:s3cr3t@host.example/repo.git", "http://host.example/repo.git"),
    ("ssh://git:s3cr3t@host.example/org/repo.git", "ssh://host.example/org/repo.git"),
    ("git://user:s3cr3t@host.example/repo.git", "git://host.example/repo.git"),
    # a .zip suffix routes to the zip acquirer; the secret must still be refused first
    ("https://user:s3cr3t@host.example/archive.zip", "https://host.example/archive.zip"),
    # an unencoded "@" in the password
    ("https://user:s3c@r3t@host.example/repo.git", "https://host.example/repo.git"),
]

ACCEPTED_LOCATIONS = [
    "git@host.example:org/repo.git",
    "ssh://git@host.example/org/repo.git",
    "https://host.example/org/repo.git",
    "https://host.example/org/repo.git?ref=main",
    "/home/user/project",
    r"C:\work\project",
    "project.zip",
]


@pytest.mark.parametrize(("location", "safe"), SECRET_LOCATIONS)
def test_secret_location_is_detected_and_redacted(location: str, safe: str) -> None:
    assert carries_secret(location)
    assert redact_source_location(location) == safe


@pytest.mark.parametrize("location", ACCEPTED_LOCATIONS)
def test_location_without_a_secret_passes(location: str) -> None:
    assert not carries_secret(location)
    InputAcquirer.check_source(location)  # does not raise


@pytest.mark.parametrize(("location", "safe"), SECRET_LOCATIONS)
def test_refusal_names_alternatives_and_omits_the_secret(location: str, safe: str) -> None:
    with pytest.raises(AcquisitionError) as exc_info:
        InputAcquirer.check_source(location)

    message = str(exc_info.value)
    assert "s3cr3t" not in message
    assert "s3c@r3t" not in message
    assert safe in message
    for alternative in ("SSH key or agent", "credential helper", "GIT_ASKPASS", "GIT_CONFIG_COUNT"):
        assert alternative in message


@pytest.mark.parametrize(("location", "_safe"), SECRET_LOCATIONS)
def test_acquire_refuses_before_any_acquirer_runs(location: str, _safe: str) -> None:
    with patch("codeograph.input.acquirers.git_acquirer.subprocess.run") as clone:
        with pytest.raises(AcquisitionError):
            InputAcquirer().acquire(location)

    clone.assert_not_called()


@pytest.mark.parametrize(
    "location",
    [
        "https://user:s3cr3t@host.example/org/repo.git",
        "https://s3cr3t@host.example/org/repo.git",
    ],
)
def test_run_exits_1_and_writes_nothing(location: str, tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()

    with (
        patch("tempfile.tempdir", str(temp_root)),
        patch("codeograph.input.acquirers.git_acquirer.subprocess.run") as clone,
    ):
        result = CliRunner().invoke(cli, ["run", location, "--out", str(out_dir), "--ast-only"])

    assert result.exit_code == 1
    assert "s3cr3t" not in result.output
    assert "carries credentials" in result.output
    assert "host.example/org/repo.git" in result.output
    clone.assert_not_called()
    assert not out_dir.exists()
    assert list(temp_root.iterdir()) == []
    assert list(tmp_path.iterdir()) == [temp_root]


@pytest.mark.parametrize("location", ["git@host.example:org/repo.git", "ssh://git@host.example/org/repo.git"])
def test_run_does_not_refuse_a_bare_user_name(location: str, tmp_path: Path) -> None:
    failed_clone = subprocess.CalledProcessError(128, "git", stderr="network stubbed out")
    with patch("codeograph.input.acquirers.git_acquirer.subprocess.run", side_effect=failed_clone):
        result = CliRunner().invoke(cli, ["run", location, "--out", str(tmp_path / "out"), "--ast-only"])

    # The run proceeds past the check and fails later, at acquisition, not at the credential refusal.
    assert "carries credentials" not in result.output
    assert result.exit_code == 1
