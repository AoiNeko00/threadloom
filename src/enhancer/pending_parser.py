"""pending 파일 파싱(parsing) 모듈.

data/pending/*.md 파일을 읽어 PendingAction으로 변환한다.
"""

from pathlib import Path

from src.enhancer.models import PendingAction
from src.utils.frontmatter import parse_frontmatter
from src.utils.i18n import t
from src.utils.logger import get_logger

_logger = get_logger("pending_parser")


def parse_pending_file(path: Path) -> PendingAction | None:
    """pending md 파일을 파싱하여 PendingAction으로 변환한다."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        _logger.warning(t("enhancer.pending_read_fail", name=path.name))
        return None
    return build_action(path, text)


def build_action(path: Path, text: str) -> PendingAction | None:
    """텍스트에서 frontmatter와 본문(body)을 분리하여 Action 생성."""
    meta, body = parse_frontmatter(text)
    if not meta:
        return build_raw_action(path, text)

    content = body.strip()
    source_posts = meta.get("source_posts", [])
    if isinstance(source_posts, str):
        source_posts = [s.strip() for s in source_posts.split(",")]

    return PendingAction(
        file_path=path,
        action_type=meta.get("action_type", "unknown"),
        name=meta.get("name", path.stem),
        target=meta.get("target", ""),
        content=content,
        source_posts=source_posts,
        duplicate_check=meta.get("duplicate_check", "create_new"),
    )


def build_raw_action(path: Path, text: str) -> PendingAction:
    """frontmatter가 없는 raw fallback 파일을 Action으로 변환."""
    return PendingAction(
        file_path=path,
        action_type="raw_fallback",
        name=path.stem,
        target="",
        content=text,
    )
