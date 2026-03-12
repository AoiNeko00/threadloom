"""AI CLI 환경 격리(environment isolation) 테스트.

화이트리스트 기반 환경변수 필터링을 검증한다.
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.ai_adapter.base import _build_clean_env


class TestBuildCleanEnv:
    def test_allows_whitelisted_vars(self):
        test_env = {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "LANG": "ko_KR.UTF-8",
            "LC_ALL": "ko_KR.UTF-8",
            "SHELL": "/bin/zsh",
            "TERM": "xterm-256color",
            "TMPDIR": "/tmp",
            "USER": "testuser",
            "SSH_AUTH_SOCK": "/tmp/ssh.sock",
            "XDG_CONFIG_HOME": "/home/user/.config",
        }
        with patch.dict(os.environ, test_env, clear=True):
            env = _build_clean_env()
            for key in test_env:
                assert key in env, f"{key}가 허용되어야 합니다"

    def test_blocks_claudecode(self):
        with patch.dict(os.environ, {"CLAUDECODE": "1", "PATH": "/usr/bin"}, clear=True):
            env = _build_clean_env()
            assert "CLAUDECODE" not in env
            assert "PATH" in env

    def test_blocks_unknown_vars(self):
        """화이트리스트에 없는 변수는 차단."""
        with patch.dict(os.environ, {
            "PATH": "/usr/bin",
            "SECRET_KEY": "abc123",
            "AWS_ACCESS_KEY_ID": "AKIA...",
            "RANDOM_VAR": "value",
        }, clear=True):
            env = _build_clean_env()
            assert "PATH" in env
            assert "SECRET_KEY" not in env
            assert "AWS_ACCESS_KEY_ID" not in env
            assert "RANDOM_VAR" not in env

    def test_empty_env(self):
        with patch.dict(os.environ, {}, clear=True):
            env = _build_clean_env()
            assert env == {}
