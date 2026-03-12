"""CLI 버전 체크(version check) 테스트."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.ai_adapter.base import BaseAIAdapter


class _TestAdapter(BaseAIAdapter):
    _CLI_CMD = "test"
    _MIN_VERSION = (1, 5)

    def analyze(self, raw_md_path, context_summary):
        return ""

    def generate_enhancements(self, analysis_md_path, existing_files):
        return ""

    def is_available(self):
        return True


class TestParseVersion:
    def test_simple_version(self):
        assert BaseAIAdapter._parse_version("1.2.3") == (1, 2, 3)

    def test_version_with_prefix(self):
        assert BaseAIAdapter._parse_version("claude 1.0.8") == (1, 0, 8)

    def test_version_with_text(self):
        assert BaseAIAdapter._parse_version("v0.33.0-beta") == (0, 33, 0)

    def test_no_version(self):
        assert BaseAIAdapter._parse_version("no version here") is None

    def test_gemini_format(self):
        assert BaseAIAdapter._parse_version("0.33.0") == (0, 33, 0)


class TestCheckVersion:
    @patch("subprocess.run")
    def test_compatible_version(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="2.0.0\n",
        )
        adapter = _TestAdapter()
        assert adapter.check_version() is True

    @patch("subprocess.run")
    def test_incompatible_version_warns(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="1.0.0\n",
        )
        adapter = _TestAdapter()
        assert adapter.check_version() is False

    @patch("subprocess.run")
    def test_exact_min_version_passes(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="1.5.0\n",
        )
        adapter = _TestAdapter()
        assert adapter.check_version() is True

    @patch("subprocess.run")
    def test_timeout_allows_execution(self, mock_run):
        """버전 확인 실패 시 실행은 허용한다."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=15)
        adapter = _TestAdapter()
        assert adapter.check_version() is True

    def test_no_min_version_skips_check(self):
        """_MIN_VERSION이 (0,0)이면 체크를 건너뛴다."""

        class _NoCheck(BaseAIAdapter):
            _CLI_CMD = "x"
            _MIN_VERSION = (0, 0)

            def analyze(self, *a):
                return ""

            def generate_enhancements(self, *a):
                return ""

            def is_available(self):
                return True

        assert _NoCheck().check_version() is True
