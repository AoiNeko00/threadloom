"""threadloom CLI 진입점(entry point).

4-Phase md 파이프라인을 오케스트레이션(orchestration)하고,
실행 잠금(lock) 기반으로 커맨드와 파이프라인을 디스패치한다.
"""

import argparse

from rich.console import Console

from src.utils.i18n import t
from src.utils.logger import get_logger
from src.utils.notify import send_notification
from src.utils.process_lock import acquire_lock, release_lock

_logger = get_logger("main")
_console = Console()


# ======================================================================
# CLI 인자 파싱(argument parsing)
# ======================================================================

def _build_parser() -> argparse.ArgumentParser:
    """argparse 파서를 구성한다."""
    parser = argparse.ArgumentParser(
        description="threadloom - Threads -> AI 자기강화 도구",
    )
    parser.add_argument(
        "--setup-auth", action="store_true", help="최초 인증 설정",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="파일 변경 없이 결과 미리보기",
    )
    parser.add_argument(
        "--full-sync", action="store_true", help="전체 재수집",
    )
    parser.add_argument(
        "--since", type=str, help="특정 날짜 이후 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--phase", type=int, choices=[2, 3, 4],
        help="특정 Phase만 재실행",
    )
    parser.add_argument(
        "--review", action="store_true",
        help="대기 중인 강화 항목 검토",
    )
    parser.add_argument(
        "--status", action="store_true", help="현재 상태 출력",
    )
    parser.add_argument(
        "--clear-auth", action="store_true", help="인증 정보 삭제",
    )
    parser.add_argument(
        "--rollback", action="store_true",
        help="최근 auto_apply 적용 되돌리기",
    )
    parser.add_argument(
        "--clean-pending", action="store_true",
        help="오래된 pending 파일 정리",
    )
    parser.add_argument(
        "--show-rejected", action="store_true",
        help="자동 심사에서 탈락한 항목 조회",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="의존성 헬스 체크",
    )
    parser.add_argument(
        "--search", type=str, metavar="QUERY", help="수집 아카이브 검색",
    )
    return parser


# ======================================================================
# main
# ======================================================================

def main() -> None:
    """CLI 진입점."""
    from src.cli.commands import (
        cmd_check,
        cmd_clean_pending,
        cmd_clear_auth,
        cmd_review,
        cmd_rollback,
        cmd_search,
        cmd_setup_auth,
        cmd_show_rejected,
        cmd_status,
    )
    from src.pipeline.runner import cmd_phase, run_pipeline

    parser = _build_parser()
    args = parser.parse_args()

    # 잠금 불필요(lock-free) 커맨드
    if args.setup_auth:
        cmd_setup_auth()
        return
    if args.clear_auth:
        cmd_clear_auth()
        return
    if args.status:
        cmd_status()
        return
    if args.show_rejected:
        cmd_show_rejected()
        return
    if args.check:
        cmd_check()
        return
    if args.search:
        cmd_search(args.search)
        return

    # 잠금 필요(lock-required) 커맨드
    acquire_lock()
    try:
        if args.review:
            cmd_review()
        elif args.rollback:
            cmd_rollback()
        elif args.clean_pending:
            cmd_clean_pending()
        elif args.phase:
            cmd_phase(args.phase, args.dry_run)
        else:
            run_pipeline(args)
    except KeyboardInterrupt:
        _console.print(f"\n[yellow]{t('main.interrupted')}[/]")
    except Exception:
        _logger.exception(t("main.pipeline_error"))
        send_notification("threadloom", t("main.pipeline_error_notify"))
        import sys
        sys.exit(1)
    finally:
        release_lock()


if __name__ == "__main__":
    main()
