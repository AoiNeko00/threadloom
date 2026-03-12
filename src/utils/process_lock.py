"""실행 잠금(process lock) 관리 모듈.

동시 실행을 방지하기 위해 data/.lock 파일 기반 PID 잠금을 제공한다.
"""

import os
import sys
from pathlib import Path

from src.utils.i18n import t
from src.utils.logger import get_logger

# 프로젝트 루트(project root) 경로
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
LOCK_FILE: Path = _PROJECT_ROOT / "data" / ".lock"

_logger = get_logger("process_lock")


def acquire_lock() -> None:
    """data/.lock 파일에 PID를 기록하여 실행 잠금을 획득한다.

    Stale lock(이미 종료된 프로세스의 잠금) 감지 포함.
    """
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)

    if LOCK_FILE.exists():
        stale = is_stale_lock()
        if not stale:
            _logger.error(t("util.lock_exists"))
            sys.exit(1)
        _logger.warning(t("util.stale_lock"))

    LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")


def is_stale_lock() -> bool:
    """잠금 파일의 PID가 실제 실행 중인지 확인한다."""
    try:
        pid = int(LOCK_FILE.read_text(encoding="utf-8").strip())
        os.kill(pid, 0)  # 프로세스 존재 확인 (시그널 전송 없음)
        return False
    except (ValueError, OSError):
        return True


def release_lock() -> None:
    """실행 잠금을 해제한다."""
    LOCK_FILE.unlink(missing_ok=True)
