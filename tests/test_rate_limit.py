"""Rate limit 방어(defense) 및 exponential backoff 테스트."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.ai_adapter.base import BaseAIAdapter


# ------------------------------------------------------------------
# mock 어댑터(adapter)
# ------------------------------------------------------------------

class _TestAdapter(BaseAIAdapter):
    _CLI_CMD = "test"

    def analyze(self, raw_md_path, context_summary):
        return ""

    def generate_enhancements(self, analysis_md_path, existing_files):
        return ""

    def is_available(self):
        return True


class TestRateLimitDetection:
    def test_detects_429_in_stderr(self):
        exc = subprocess.CalledProcessError(1, "test")
        exc.stderr = "Error: 429 Too Many Requests"
        assert _TestAdapter._is_rate_limited(exc) is True

    def test_detects_rate_limit_text(self):
        exc = subprocess.CalledProcessError(1, "test")
        exc.stderr = "rate limit exceeded, please retry"
        assert _TestAdapter._is_rate_limited(exc) is True

    def test_no_rate_limit_on_normal_error(self):
        exc = subprocess.CalledProcessError(1, "test")
        exc.stderr = "Permission denied"
        assert _TestAdapter._is_rate_limited(exc) is False

    def test_handles_none_stderr(self):
        exc = subprocess.CalledProcessError(1, "test")
        exc.stderr = None
        assert _TestAdapter._is_rate_limited(exc) is False


class TestExponentialBackoff:
    @patch("src.ai_adapter.base.time.sleep")
    @patch.object(_TestAdapter, "_execute")
    def test_retries_on_rate_limit(self, mock_exec, mock_sleep):
        """Rate limit 시 backoff 후 재시도."""
        rate_err = subprocess.CalledProcessError(1, "test")
        rate_err.stderr = "429 Too Many Requests"
        mock_exec.side_effect = [rate_err, "success"]

        adapter = _TestAdapter()
        result = adapter._call_cli("prompt")
        assert result == "success"
        # 첫 재시도: 10초 대기
        mock_sleep.assert_called_once_with(10)

    @patch("src.ai_adapter.base.time.sleep")
    @patch.object(_TestAdapter, "_execute")
    def test_gives_up_after_max_retries(self, mock_exec, mock_sleep):
        """최대 재시도 횟수 초과 시 예외 발생."""
        rate_err = subprocess.CalledProcessError(1, "test")
        rate_err.stderr = "429"
        mock_exec.side_effect = [rate_err, rate_err, rate_err]

        adapter = _TestAdapter()
        # 3회 모두 rate limit → 마지막 에러에서 sleep만 하고 루프 종료
        # _call_cli가 None을 반환 (for 루프 끝)
        result = adapter._call_cli("prompt")
        assert result is None
        assert mock_sleep.call_count == 3
