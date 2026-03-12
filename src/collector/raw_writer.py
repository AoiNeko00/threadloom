"""raw markdown 출력(writing) 모듈.

수집된 ThreadPost 목록을 markdown 파일로 저장한다.
"""

from pathlib import Path

from src.collector.models import ThreadPost
from src.utils.i18n import t
from src.utils.logger import get_logger

_logger = get_logger("collector.writer")


def write_raw_md(
    posts: list[ThreadPost], timestamp: str, raw_dir: Path,
) -> Path:
    """ThreadPost 목록을 raw markdown 파일로 저장한다.

    Args:
        posts: 수집된 포스트 목록
        timestamp: 파일명용 타임스탬프(timestamp)
        raw_dir: raw 파일 저장 디렉토리

    Returns:
        저장된 파일 경로
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_path = raw_dir / f"{timestamp}.md"

    lines: list[str] = [
        f"# Threads Collection — {timestamp}",
        f"collected: {len(posts)}",
        "",
    ]

    for post in posts:
        lines.extend(format_post_md(post))

    output_path.write_text(
        "\n".join(lines), encoding="utf-8",
    )
    _logger.info(t("collector.raw_saved", ts=timestamp))
    return output_path


def format_post_md(post: ThreadPost) -> list[str]:
    """단일 포스트를 markdown 블록으로 변환한다.

    본문과 self-reply(이어쓰기)를 구분하여 표시한다.
    """
    reply_count = len(post.replies)
    block = [
        "---",
        "",
        f"**author**: @{post.author}",
        f"**post_id**: {post.post_id}",
        f"**URL**: {post.url}",
        f"**saved_at**: {post.saved_at.isoformat()}",
        f"**replies**: {reply_count}",
        "",
        post.text,
        "",
    ]
    if post.media_urls:
        block.append("**media:**")
        for url in post.media_urls:
            block.append(f"- {url}")
        block.append("")
    if post.link_contents:
        block.append("**link_contents:**")
        block.append("")
        for lc in post.link_contents:
            title = lc.get("title", "")
            url = lc.get("url", "")
            text = lc.get("text", "")
            block.append(f"> **[{title}]({url})**")
            block.append(f"> {text}")
            block.append("")
    return block
