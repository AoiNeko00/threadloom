"""pending 파일 생명주기(lifecycle) 관리 모듈.

pending 파일의 승인 표시, 거절 이동, 삭제, 정리를 담당한다.
"""

from datetime import datetime, timedelta
from pathlib import Path

from src.enhancer.models import PendingAction
from src.utils.frontmatter import set_frontmatter_field
from src.utils.i18n import t
from src.utils.logger import get_logger

_logger = get_logger("pending_manager")

# 프로젝트 루트(project root) 경로
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_PENDING_DIR = _PROJECT_ROOT / "data" / "pending"
_REJECTED_DIR = _PROJECT_ROOT / "data" / "rejected"


def remove_pending(action: PendingAction) -> None:
    """처리 완료된 pending 파일을 삭제한다."""
    try:
        action.file_path.unlink(missing_ok=True)
    except OSError:
        _logger.warning(
            t("enhancer.pending_delete_fail", name=action.file_path.name),
        )


def remove_old_files(cutoff: datetime) -> int:
    """cutoff 이전에 수정된 pending 파일을 삭제한다."""
    removed = 0
    for md_file in _PENDING_DIR.glob("*.md"):
        mtime = datetime.fromtimestamp(md_file.stat().st_mtime)
        if mtime < cutoff:
            md_file.unlink()
            removed += 1
    return removed


def clean_pending(days: int = 30) -> None:
    """오래된 pending 파일을 정리한다."""
    if not _PENDING_DIR.is_dir():
        return
    cutoff = datetime.now() - timedelta(days=days)
    removed = remove_old_files(cutoff)
    _logger.info(t("enhancer.old_pending_cleaned", days=days, n=removed))


def mark_approved(action: PendingAction) -> None:
    """pending 파일에 status: approved frontmatter를 추가한다."""
    try:
        text = action.file_path.read_text(encoding="utf-8")
    except OSError:
        return
    updated = set_frontmatter_field(text, "status", "approved")
    action.file_path.write_text(updated, encoding="utf-8")


def move_to_rejected(action: PendingAction) -> None:
    """pending 파일을 data/rejected/로 이동하고 거부 사유를 추가한다."""
    _REJECTED_DIR.mkdir(parents=True, exist_ok=True)
    try:
        text = action.file_path.read_text(encoding="utf-8")
    except OSError:
        remove_pending(action)
        return
    updated = set_frontmatter_field(
        text, "rejection_reason", "user_rejected",
    )
    dest = _REJECTED_DIR / action.file_path.name
    dest.write_text(updated, encoding="utf-8")
    remove_pending(action)
