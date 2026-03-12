"""의존성 헬스 체크(dependency health check) 모듈."""

import shutil
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table

from src.utils.i18n import t
from src.utils.logger import get_logger

_logger = get_logger("health_check")
_console = Console()


@dataclass
class CheckResult:
    """개별 체크 결과."""

    name: str
    status: str  # "ok", "warn", "fail"
    message: str


def run_health_check() -> list[CheckResult]:
    """모든 의존성을 점검하고 결과를 반환한다."""
    results: list[CheckResult] = []
    results.append(_check_config())
    results.append(_check_ai_cli())
    results.append(_check_ai_auth())
    results.append(_check_ai_version())
    results.append(_check_keyring())
    results.append(_check_playwright())
    results.append(_check_obsidian_vault())
    return results


def display_health_check(results: list[CheckResult]) -> None:
    """체크 결과를 rich 테이블로 출력한다."""
    # 상태(status) → 아이콘 + 색상 매핑
    status_map = {
        "ok": ("[green]OK[/]", "[green]"),
        "warn": ("[yellow]WARN[/]", "[yellow]"),
        "fail": ("[red]FAIL[/]", "[red]"),
    }

    table = Table(title=t("health.title"))
    table.add_column(t("health.col_item"), style="bold")
    table.add_column(t("health.col_status"), justify="center", width=8)
    table.add_column(t("health.col_message"))

    for r in results:
        icon, color = status_map.get(r.status, ("[dim]?[/]", "[dim]"))
        table.add_row(r.name, icon, f"{color}{r.message}[/]")

    _console.print(table)

    # 요약(summary) 출력
    fail_count = sum(1 for r in results if r.status == "fail")
    warn_count = sum(1 for r in results if r.status == "warn")
    if fail_count:
        _console.print(f"\n[red]{t('health.result_fail', n=fail_count)}[/]", end="")
    if warn_count:
        sep = ", " if fail_count else "\n"
        _console.print(f"{sep}[yellow]{t('health.result_warn', n=warn_count)}[/]", end="")
    if not fail_count and not warn_count:
        _console.print(f"\n[green]{t('health.result_ok')}[/]")
    else:
        _console.print()


def _check_config() -> CheckResult:
    """config.yaml 로드 가능 여부."""
    try:
        from src.config import Config

        Config.reset()
        Config()
        return CheckResult("config.yaml", "ok", t("health.config_ok"))
    except SystemExit:
        return CheckResult("config.yaml", "fail", t("health.config_fail"))
    except Exception as e:
        return CheckResult("config.yaml", "fail", str(e))


def _check_ai_cli() -> CheckResult:
    """AI CLI 설치 여부."""
    from src.config import Config

    config = Config()
    provider = config.ai_provider
    # 프로바이더(provider) → CLI 명령어 매핑
    cli_map = {"claude_code": "claude", "codex": "codex", "gemini": "gemini"}
    cmd = cli_map.get(provider, provider)
    if shutil.which(cmd):
        return CheckResult(f"AI CLI ({cmd})", "ok", t("health.cli_ok", cmd=cmd))
    return CheckResult(f"AI CLI ({cmd})", "fail", t("health.cli_fail", cmd=cmd))


def _check_ai_auth() -> CheckResult:
    """AI CLI 인증(authentication) 상태."""
    try:
        from src.ai_adapter import get_adapter
        from src.config import Config

        adapter = get_adapter(Config().ai_provider)
        if adapter.is_available():
            return CheckResult("AI 인증", "ok", t("health.auth_ok"))
        return CheckResult("AI 인증", "fail", t("health.auth_fail"))
    except Exception as e:
        return CheckResult("AI 인증", "fail", str(e))


def _check_ai_version() -> CheckResult:
    """AI CLI 버전 호환성(version compatibility)."""
    try:
        from src.ai_adapter import get_adapter
        from src.config import Config

        adapter = get_adapter(Config().ai_provider)
        if adapter.check_version():
            return CheckResult("AI 버전", "ok", t("health.version_ok"))
        return CheckResult("AI 버전", "warn", t("health.version_warn"))
    except Exception as e:
        return CheckResult("AI 버전", "warn", str(e))


def _check_keyring() -> CheckResult:
    """keyring 접근 가능 여부."""
    try:
        import keyring

        keyring.get_password("threadloom", "health_check_test")
        return CheckResult("keyring", "ok", t("health.keyring_ok"))
    except Exception as e:
        return CheckResult("keyring", "fail", t("health.keyring_fail", err=str(e)))


def _check_playwright() -> CheckResult:
    """Playwright 바이너리(binary) 설치 여부."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            path = pw.chromium.executable_path
            if path and Path(path).exists():
                return CheckResult("Playwright", "ok", t("health.pw_ok"))
        return CheckResult("Playwright", "warn", t("health.pw_warn"))
    except Exception as e:
        return CheckResult("Playwright", "fail", t("health.pw_fail", err=str(e)))


def _check_obsidian_vault() -> CheckResult:
    """Obsidian vault 경로 마운트(mount) 여부."""
    from src.config import Config

    config = Config()
    if not config.obsidian_enabled:
        return CheckResult("Obsidian vault", "ok", t("health.obsidian_disabled"))
    vault = config.vault_path
    if Path(vault).is_dir():
        return CheckResult("Obsidian vault", "ok", t("health.obsidian_ok", vault=vault))
    return CheckResult("Obsidian vault", "fail", t("health.obsidian_fail", vault=vault))
