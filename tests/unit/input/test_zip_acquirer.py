"""Archive extraction is bounded, path-checked, and cleans up every failed acquisition."""

from __future__ import annotations

import struct
import zipfile
from pathlib import Path

import pytest
from click.testing import CliRunner
from pydantic import ValidationError

from codeograph.cli.main import cli
from codeograph.config.settings import Settings
from codeograph.input.acquirers.base_acquirer import AcquisitionError
from codeograph.input.acquirers.zip_acquirer import ZipAcquirer
from codeograph.input.input_acquirer import InputAcquirer
from codeograph.input.source_discoverer import SourceDiscoverer


def _write_archive(path: Path, members: dict[str, str | bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return path


def _patch_archive_entry(path: Path, *, compression: int | None = None, encrypted: bool = False) -> None:
    data = bytearray(path.read_bytes())
    local_header = data.index(b"PK\x03\x04")
    central_header = data.index(b"PK\x01\x02")
    if compression is not None:
        struct.pack_into("<H", data, local_header + 8, compression)
        struct.pack_into("<H", data, central_header + 10, compression)
    if encrypted:
        for flags_offset in (local_header + 6, central_header + 8):
            flags = struct.unpack_from("<H", data, flags_offset)[0]
            struct.pack_into("<H", data, flags_offset, flags | 1)
    path.write_bytes(data)


@pytest.fixture
def extraction_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "extracted"

    def make_temp_dir() -> str:
        root.mkdir()
        return str(root)

    monkeypatch.setattr("codeograph.input.acquirers.zip_acquirer.tempfile.mkdtemp", make_temp_dir)
    return root


def test_archive_cap_setting_default_and_lower_bound() -> None:
    assert Settings().max_archive_extracted_bytes == 1_073_741_824
    with pytest.raises(ValidationError):
        Settings(max_archive_extracted_bytes=0)


def test_normal_archive_extracts_and_discovers_modules(tmp_path: Path, extraction_root: Path) -> None:
    archive_path = _write_archive(
        tmp_path / "project.zip",
        {
            "project/pom.xml": "<project/>",
            "project/src/main/java/com/example/App.java": "public class App {}",
        },
    )

    corpus = ZipAcquirer(SourceDiscoverer()).acquire(str(archive_path))

    assert corpus.corpus_root == extraction_root
    assert [module.name for module in corpus.modules] == ["project"]
    assert [path.name for path in corpus.modules[0].java_files] == ["App.java"]
    assert (extraction_root / "project/src/main/java/com/example/App.java").is_file()
    InputAcquirer.cleanup(corpus)
    assert not extraction_root.exists()


def test_archive_over_the_aggregate_cap_is_refused_and_cleans_up(tmp_path: Path, extraction_root: Path) -> None:
    archive_path = _write_archive(tmp_path / "large.zip", {"first.txt": b"12345", "second.txt": b"67890"})

    with pytest.raises(AcquisitionError) as exc_info:
        ZipAcquirer(SourceDiscoverer(), max_archive_extracted_bytes=8).acquire(str(archive_path))

    assert str(exc_info.value) == "Archive extraction exceeds the configured cap of 8 bytes"
    assert not extraction_root.exists()


@pytest.mark.parametrize("entry_name", ["../evil.java", "/absolute/evil.java"])
def test_entry_outside_the_root_is_refused_and_cleans_up(
    tmp_path: Path, extraction_root: Path, entry_name: str
) -> None:
    archive_path = _write_archive(tmp_path / "traversal.zip", {entry_name: "public class Evil {}"})

    with pytest.raises(AcquisitionError) as exc_info:
        ZipAcquirer(SourceDiscoverer()).acquire(str(archive_path))

    assert str(exc_info.value) == f"Archive entry resolves outside the extraction root: {entry_name}"
    assert not extraction_root.exists()


def test_corrupt_archive_keeps_its_specific_error_and_cleans_up(tmp_path: Path, extraction_root: Path) -> None:
    archive_path = tmp_path / "corrupt.zip"
    archive_path.write_bytes(b"not a zip archive")

    with pytest.raises(AcquisitionError) as exc_info:
        ZipAcquirer(SourceDiscoverer()).acquire(str(archive_path))

    assert str(exc_info.value) == f"Invalid or corrupt zip file: {archive_path}"
    assert not extraction_root.exists()


@pytest.mark.parametrize(
    ("patch", "expected_cause"),
    [
        ({"encrypted": True}, "encrypted"),
        ({"compression": 99}, "compression method is not supported"),
    ],
)
def test_member_read_errors_name_their_cause_and_clean_up(
    tmp_path: Path,
    extraction_root: Path,
    patch: dict[str, int | bool],
    expected_cause: str,
) -> None:
    archive_path = _write_archive(tmp_path / "unreadable.zip", {"src/App.java": "public class App {}"})
    _patch_archive_entry(archive_path, **patch)  # type: ignore[arg-type]

    with pytest.raises(AcquisitionError) as exc_info:
        ZipAcquirer(SourceDiscoverer()).acquire(str(archive_path))

    message = str(exc_info.value)
    assert message.startswith(f"Zip acquisition failed for {archive_path}:")
    assert expected_cause in message.lower()
    assert not extraction_root.exists()


def test_run_cli_refuses_an_archive_over_the_configured_cap_without_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_path = _write_archive(tmp_path / "large.zip", {"project/src/App.java": "123456789"})
    monkeypatch.setenv("CODEOGRAPH_MAX_ARCHIVE_EXTRACTED_BYTES", "8")

    result = CliRunner().invoke(cli, ["run", str(archive_path), "--out", str(tmp_path / "out"), "--ast-only"])

    assert result.exit_code == 1
    assert "Archive extraction exceeds the configured cap of 8 bytes" in result.output
    assert "Traceback" not in result.output
