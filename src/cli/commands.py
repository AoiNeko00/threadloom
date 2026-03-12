"""독립 커맨드(standalone commands) 핸들러 모듈.

CLI에서 잠금 없이/있이 실행되는 개별 커맨드를 처리한다.
"""

import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from src.utils.i18n import t
from src.utils.logger import get_logger
from src.utils.paths import REJECTED_DIR

_logger = get_logger("commands")

from src.cli.status_display import (
    count_applied,
    count_pending,
    count_rejected,
    extract_rejected_meta,
    print_enhancement_map,
    print_pending_list,
)

# 중앙 경로(centralized path) 모듈에서 가져옴
_REJECTED_DIR: Path = REJECTED_DIR

_console = Console()


def cmd_setup_auth() -> None:
    """--setup-auth: Threads 최초 인증 설정."""
    from src.collector.auth_manager import AuthManager
    from src.config import Config

    auth = AuthManager(account=Config().threads_account)
    success = auth.setup_auth()
    if success:
        _console.print(f"[bold green]{t('cmd.auth_setup_ok')}[/]")
    else:
        _console.print(f"[bold red]{t('cmd.auth_setup_fail', err='setup returned False')}[/]")
        sys.exit(1)


def cmd_clear_auth() -> None:
    """--clear-auth: 인증 정보 삭제."""
    from src.collector.auth_manager import AuthManager
    from src.config import Config

    AuthManager(account=Config().threads_account).clear_auth()
    _console.print(t("cmd.auth_cleared"))


def cmd_check() -> None:
    """--check: 의존성 헬스 체크(dependency health check) 실행."""
    from src.utils.health_check import display_health_check, run_health_check

    results = run_health_check()
    display_health_check(results)


def cmd_status() -> None:
    """--status: 현재 상태 출력."""
    from src.utils.state import get_last_sync, get_total_collected

    last_sync = get_last_sync()
    total = get_total_collected()
    pending = count_pending()
    applied = count_applied()

    _console.print(f"\n[bold]{t('cmd.status_title')}[/]")
    _console.print("=" * 30)
    ts = last_sync.strftime('%Y-%m-%d %H:%M') if last_sync else t("status.none")
    _console.print(t("cmd.last_sync", ts=ts))
    _console.print(t("cmd.total_collected", n=total))
    _console.print(t("cmd.pending_count", n=pending))
    print_pending_list()
    _console.print(t("cmd.applied_count", n=applied))

    # 강화 맵(enhancement map) 출력 — Config 로드 실패 시 건너뜀
    try:
        from src.config import Config
        config = Config()
        print_enhancement_map(Path(config.target_project_path))
    except Exception:
        _logger.debug("enhancement map 출력 건너뜀")
    _console.print()


def cmd_show_rejected() -> None:
    """--show-rejected: 자동 심사 탈락(rejected) 항목을 테이블로 출력."""
    if not _REJECTED_DIR.exists():
        _console.print(t("cmd.no_rejected"))
        return
    files = sorted(_REJECTED_DIR.glob("*.md"))
    if not files:
        _console.print(t("cmd.no_rejected"))
        return

    table = Table(title=t("cmd.rejected_title"))
    table.add_column("#", width=3)
    table.add_column(t("cli.col_name"))
    table.add_column(t("cli.col_reject_reason"))

    for i, f in enumerate(files, 1):
        name, reason = extract_rejected_meta(f)
        table.add_row(str(i), name, reason)
    _console.print(table)


def cmd_review() -> None:
    """--review: 대기 중인 강화 항목 대화형 검토."""
    from src.config import Config
    from src.enhancer.applier import Applier
    from src.writer.review_display import display_summary

    # 탈락(rejected) 항목 존재 알림
    rejected = count_rejected()
    if rejected > 0:
        _console.print(
            f"[dim]{t('cli.auto_review_rejected', n=rejected)}[/dim]",
        )

    config = Config()
    applier = Applier(config)

    approved, rejected_items = applier.review()
    skipped = applier.count_pending_remaining(approved, rejected_items)
    display_summary(len(approved), len(rejected_items), skipped)

    if rejected_items:
        applier.reject(rejected_items)

    if approved:
        confirm = input(t("cli.confirm_apply")).strip().lower()
        if confirm == "y":
            applier.apply_approved(approved)
            _console.print(f"[green]{t('cmd.applied_ok', n=len(approved))}[/]")
        else:
            _console.print(f"[dim]{t('cmd.apply_cancelled')}[/]")
    elif not rejected_items:
        _console.print(t("cmd.no_changes"))


def cmd_rollback() -> None:
    """--rollback: 최근 적용 되돌리기."""
    from src.config import Config
    from src.enhancer.applier import Applier

    Applier(Config()).rollback()
    _console.print(t("cmd.rollback_ok"))


def cmd_clean_pending() -> None:
    """--clean-pending: 오래된 pending 파일 정리."""
    from src.config import Config
    from src.enhancer.applier import Applier

    Applier(Config()).clean_pending()
    _console.print(t("cmd.clean_ok"))


def cmd_search(query: str) -> None:
    """--search: 수집 아카이브 시맨틱 검색(semantic search)."""
    from src.utils.search import interactive_search_results, search

    hits = search(query)
    interactive_search_results(query, hits)
