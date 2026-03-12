"""의존성 헬스 체크(dependency health check) 테스트."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.utils.health_check import (
    CheckResult,
    _check_ai_cli,
    _check_ai_auth,
    _check_ai_version,
    _check_config,
    _check_keyring,
    _check_obsidian_vault,
    _check_playwright,
    display_health_check,
    run_health_check,
)


class TestCheckResult:
    def test_fields(self):
        r = CheckResult("test", "ok", "all good")
        assert r.name == "test"
        assert r.status == "ok"
        assert r.message == "all good"


class TestCheckConfig:
    @patch("src.config.Config.reset")
    @patch("src.config.Config.__init__", return_value=None)
    def test_ok(self, mock_init, mock_reset):
        """config 로드 성공 시 ok."""
        result = _check_config()
        assert result.status == "ok"

    @patch("src.config.Config.reset")
    @patch("src.config.Config.__init__", side_effect=SystemExit(1))
    def test_fail_system_exit(self, mock_init, mock_reset):
        """config 로드 실패(SystemExit) 시 fail."""
        result = _check_config()
        assert result.status == "fail"

    @patch("src.config.Config.reset")
    @patch("src.config.Config.__init__", side_effect=RuntimeError("broken"))
    def test_fail_exception(self, mock_init, mock_reset):
        """config 로드 중 예외(exception) 시 fail."""
        result = _check_config()
        assert result.status == "fail"
        assert "broken" in result.message


class TestCheckAiCli:
    @patch("shutil.which", return_value="/usr/local/bin/claude")
    @patch("src.config.Config.__init__", return_value=None)
    @patch("src.config.Config.ai_provider", new_callable=lambda: property(lambda s: "claude_code"))
    def test_ok(self, mock_prop, mock_init, mock_which):
        """CLI 설치 확인 시 ok."""
        result = _check_ai_cli()
        assert result.status == "ok"

    @patch("shutil.which", return_value=None)
    @patch("src.config.Config.__init__", return_value=None)
    @patch("src.config.Config.ai_provider", new_callable=lambda: property(lambda s: "claude_code"))
    def test_fail(self, mock_prop, mock_init, mock_which):
        """CLI 미설치 시 fail."""
        result = _check_ai_cli()
        assert result.status == "fail"


class TestCheckAiAuth:
    @patch("src.ai_adapter.get_adapter")
    @patch("src.config.Config.__init__", return_value=None)
    @patch("src.config.Config.ai_provider", new_callable=lambda: property(lambda s: "claude_code"))
    def test_ok(self, mock_prop, mock_init, mock_get_adapter):
        """인증 유효 시 ok."""
        mock_get_adapter.return_value.is_available.return_value = True
        result = _check_ai_auth()
        assert result.status == "ok"

    @patch("src.ai_adapter.get_adapter")
    @patch("src.config.Config.__init__", return_value=None)
    @patch("src.config.Config.ai_provider", new_callable=lambda: property(lambda s: "claude_code"))
    def test_fail(self, mock_prop, mock_init, mock_get_adapter):
        """인증 실패 시 fail."""
        mock_get_adapter.return_value.is_available.return_value = False
        result = _check_ai_auth()
        assert result.status == "fail"


class TestCheckAiVersion:
    @patch("src.ai_adapter.get_adapter")
    @patch("src.config.Config.__init__", return_value=None)
    @patch("src.config.Config.ai_provider", new_callable=lambda: property(lambda s: "claude_code"))
    def test_ok(self, mock_prop, mock_init, mock_get_adapter):
        """버전 호환 시 ok."""
        mock_get_adapter.return_value.check_version.return_value = True
        result = _check_ai_version()
        assert result.status == "ok"

    @patch("src.ai_adapter.get_adapter")
    @patch("src.config.Config.__init__", return_value=None)
    @patch("src.config.Config.ai_provider", new_callable=lambda: property(lambda s: "claude_code"))
    def test_warn(self, mock_prop, mock_init, mock_get_adapter):
        """버전 미달 시 warn."""
        mock_get_adapter.return_value.check_version.return_value = False
        result = _check_ai_version()
        assert result.status == "warn"


class TestCheckKeyring:
    @patch("keyring.get_password", return_value=None)
    def test_ok(self, mock_get):
        """keyring 접근 성공 시 ok."""
        result = _check_keyring()
        assert result.status == "ok"

    @patch("keyring.get_password", side_effect=Exception("no backend"))
    def test_fail(self, mock_get):
        """keyring 접근 실패 시 fail."""
        result = _check_keyring()
        assert result.status == "fail"


class TestCheckPlaywright:
    @patch("playwright.sync_api.sync_playwright")
    def test_ok(self, mock_sp):
        """Chromium 바이너리 존재 시 ok."""
        mock_pw = MagicMock()
        mock_pw.chromium.executable_path = "/tmp/chromium"
        mock_sp.return_value.__enter__ = MagicMock(return_value=mock_pw)
        mock_sp.return_value.__exit__ = MagicMock(return_value=False)
        with patch.object(Path, "exists", return_value=True):
            result = _check_playwright()
        assert result.status == "ok"

    @patch(
        "playwright.sync_api.sync_playwright",
        side_effect=Exception("not installed"),
    )
    def test_fail(self, mock_sp):
        """Playwright 미설치 시 fail."""
        result = _check_playwright()
        assert result.status == "fail"


class TestCheckObsidianVault:
    @patch("src.config.Config.__init__", return_value=None)
    @patch("src.config.Config.obsidian_enabled", new_callable=lambda: property(lambda s: False))
    def test_disabled(self, mock_prop, mock_init):
        """비활성화 시 ok (건너뜀)."""
        result = _check_obsidian_vault()
        assert result.status == "ok"
        assert "비활성화" in result.message or "Disabled" in result.message

    @patch("src.config.Config.__init__", return_value=None)
    @patch("src.config.Config.obsidian_enabled", new_callable=lambda: property(lambda s: True))
    @patch("src.config.Config.vault_path", new_callable=lambda: property(lambda s: "/tmp/vault"))
    def test_ok(self, mock_vault, mock_enabled, mock_init):
        """vault 경로 존재 시 ok."""
        with patch.object(Path, "is_dir", return_value=True):
            result = _check_obsidian_vault()
        assert result.status == "ok"

    @patch("src.config.Config.__init__", return_value=None)
    @patch("src.config.Config.obsidian_enabled", new_callable=lambda: property(lambda s: True))
    @patch("src.config.Config.vault_path", new_callable=lambda: property(lambda s: "/nonexistent"))
    def test_fail(self, mock_vault, mock_enabled, mock_init):
        """vault 경로 없을 시 fail."""
        with patch.object(Path, "is_dir", return_value=False):
            result = _check_obsidian_vault()
        assert result.status == "fail"


class TestRunHealthCheck:
    @patch("src.utils.health_check._check_obsidian_vault")
    @patch("src.utils.health_check._check_playwright")
    @patch("src.utils.health_check._check_keyring")
    @patch("src.utils.health_check._check_ai_version")
    @patch("src.utils.health_check._check_ai_auth")
    @patch("src.utils.health_check._check_ai_cli")
    @patch("src.utils.health_check._check_config")
    def test_returns_seven_results(self, *mocks):
        """7개 체크 항목 모두 실행 확인."""
        for m in mocks:
            m.return_value = CheckResult("test", "ok", "ok")
        results = run_health_check()
        assert len(results) == 7


class TestDisplayHealthCheck:
    def test_no_error(self):
        """display 호출이 에러 없이 완료되는지 확인."""
        results = [
            CheckResult("A", "ok", "good"),
            CheckResult("B", "warn", "maybe"),
            CheckResult("C", "fail", "bad"),
        ]
        display_health_check(results)
