"""Unit tests for InputAcquirer and _detect_input_type (DC1 coverage gap).

These tests cover the type-detection heuristic and the LocalAcquirer path
using tmp_path — no external deps (no git, no network, no zip tooling).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codeograph.input.acquirers.base_acquirer import AcquisitionError
from codeograph.input.acquirers.local_acquirer import LocalAcquirer
from codeograph.input.input_acquirer import InputAcquirer, _detect_input_type
from codeograph.input.models import AcquisitionSource

# ---------------------------------------------------------------------------
# _detect_input_type heuristic
# ---------------------------------------------------------------------------


class TestDetectInputType:
    def test_zip_extension_detected(self):
        assert _detect_input_type("project.zip") == AcquisitionSource.ZIP

    def test_zip_extension_case_insensitive(self):
        assert _detect_input_type("project.ZIP") == AcquisitionSource.ZIP

    def test_https_url_detected(self):
        assert _detect_input_type("https://github.com/org/repo") == AcquisitionSource.GIT_URL

    def test_http_url_detected(self):
        assert _detect_input_type("http://github.com/org/repo") == AcquisitionSource.GIT_URL

    def test_git_at_url_detected(self):
        assert _detect_input_type("git@github.com:org/repo.git") == AcquisitionSource.GIT_URL

    def test_git_protocol_detected(self):
        assert _detect_input_type("git://github.com/org/repo.git") == AcquisitionSource.GIT_URL

    def test_local_path_is_default(self):
        assert _detect_input_type("/home/user/project") == AcquisitionSource.LOCAL

    def test_relative_path_is_local(self):
        assert _detect_input_type("./my-project") == AcquisitionSource.LOCAL

    def test_windows_path_is_local(self):
        assert _detect_input_type("C:\\Users\\user\\project") == AcquisitionSource.LOCAL


# ---------------------------------------------------------------------------
# LocalAcquirer
# ---------------------------------------------------------------------------


class TestLocalAcquirer:
    def test_raises_on_nonexistent_path(self, tmp_path: Path):
        from codeograph.input.source_discoverer import SourceDiscoverer

        acquirer = LocalAcquirer(SourceDiscoverer())
        with pytest.raises(AcquisitionError, match="does not exist"):
            acquirer.acquire(str(tmp_path / "nonexistent"))

    def test_raises_on_file_not_directory(self, tmp_path: Path):
        from codeograph.input.source_discoverer import SourceDiscoverer

        f = tmp_path / "file.txt"
        f.write_text("content", encoding="utf-8")
        acquirer = LocalAcquirer(SourceDiscoverer())
        with pytest.raises(AcquisitionError, match="not a directory"):
            acquirer.acquire(str(f))

    def test_acquires_empty_directory(self, tmp_path: Path):
        from codeograph.input.source_discoverer import SourceDiscoverer

        acquirer = LocalAcquirer(SourceDiscoverer())
        corpus = acquirer.acquire(str(tmp_path))
        assert corpus.acquisition_source == AcquisitionSource.LOCAL
        assert corpus.corpus_root == tmp_path
        assert corpus.is_temp_dir is False

    def test_acquires_directory_with_java_files(self, tmp_path: Path):
        from codeograph.input.source_discoverer import SourceDiscoverer

        src = tmp_path / "src" / "main" / "java" / "com" / "example"
        src.mkdir(parents=True)
        (src / "Foo.java").write_text("public class Foo {}", encoding="utf-8")
        (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")

        acquirer = LocalAcquirer(SourceDiscoverer())
        corpus = acquirer.acquire(str(tmp_path))
        assert corpus.acquisition_source == AcquisitionSource.LOCAL
        assert len(corpus.modules) >= 1


# ---------------------------------------------------------------------------
# InputAcquirer — type dispatch + cleanup
# ---------------------------------------------------------------------------


class TestInputAcquirer:
    def test_acquire_local_directory(self, tmp_path: Path):
        acquirer = InputAcquirer()
        corpus = acquirer.acquire(str(tmp_path))
        assert corpus.acquisition_source == AcquisitionSource.LOCAL

    def test_cleanup_is_noop_for_local(self, tmp_path: Path):
        acquirer = InputAcquirer()
        corpus = acquirer.acquire(str(tmp_path))
        # Must not raise and must not delete the real directory
        InputAcquirer.cleanup(corpus)
        assert tmp_path.exists()

    def test_acquire_nonexistent_raises(self, tmp_path: Path):
        acquirer = InputAcquirer()
        with pytest.raises(AcquisitionError):
            acquirer.acquire(str(tmp_path / "missing"))
