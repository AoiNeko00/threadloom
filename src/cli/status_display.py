"""상태 표시(status display) 모듈.

pending, applied, rejected 건수 조회 및 상태 출력을 담당한다.
"""

import json
from pathlib import Path

from rich.console import Console

from src.utils.frontmatter import parse_frontmatter
from src.utils.i18n import t

# 프로젝트 루트(project root) 경로
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
_PENDING_DIR: Path = _PROJECT_ROOT / "data" / "pending"
_REJECTED_DIR: Path = _PROJECT_ROOT / "data" / "rejected"
_ENHANCE_LOG: Path = _PROJECT_ROOT / "data" / "enhance_log.json"

_console = Console()


def count_pending() -> int:
    """pending 파일 개수를 반환한다."""
    if not _PENDING_DIR.is_dir():
        return 0
    return len(list(_PENDING_DIR.glob("*.md")))


def count_applied() -> int:
    """enhance_log.json에서 적용(applied) 건수를 반환한다."""
    if not _ENHANCE_LOG.exists():
        return 0
    try:
        data = json.loads(_ENHANCE_LOG.read_text(encoding="utf-8"))
        return sum(1 for e in data if e.get("result") == "applied")
    except (json.JSONDecodeError, OSError):
        return 0


def count_rejected() -> int:
    """rejected 파일 개수를 반환한다."""
    if not _REJECTED_DIR.is_dir():
        return 0
    return len(list(_REJECTED_DIR.glob("*.md")))


def print_pending_list() -> None:
    """대기 중인 pending 항목을 간략히 출력한다."""
    if not _PENDING_DIR.is_dir():
        return
    for md_file in sorted(_PENDING_DIR.glob("*.md")):
        name = md_file.stem
        # action_type과 name 분리: "create_skill_foo" -> "[create_skill] foo"
        parts = name.split("_", 2)
        if len(parts) >= 3:
            _console.print(f"  - [{parts[0]}_{parts[1]}] {parts[2]}")
        else:
            _console.print(f"  - {name}")


def extract_rejected_meta(path: Path) -> tuple[str, str]:
    """rejected md의 frontmatter에서 name과 rejection_reason을 추출한다."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return path.stem, t("status.read_error")
    meta, _ = parse_frontmatter(text)
    if not meta:
        return path.stem, t("status.no_frontmatter")
    name = meta.get("name", path.stem)
    reason = meta.get("rejection_reason", t("status.no_reason"))
    return name, reason
