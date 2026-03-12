"""--review 대화형 검토(interactive review)의 rich 기반 표시 모듈.

Side-by-Side Diff 뷰, 새 파일 미리보기, 헤더 패널 등을 담당한다.
"""

import difflib
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from src.enhancer.models import PendingAction
from src.utils.i18n import t

_console = Console()

# 미리보기(preview) 최대 줄 수
_PREVIEW_MAX_LINES = 30


def display_header(
    idx: int, total: int, action: PendingAction,
) -> None:
    """검토 항목의 헤더(header) 패널을 표시한다."""
    title = f"[{idx}/{total}] {action.action_type} \u2014 {action.name}"
    body = (
        f"relevance_score: {_extract_score(action)}  "
        f"\u2502  action: {action.duplicate_check}\n"
        f"target: {action.target}"
    )
    _console.print(Panel(body, title=title, border_style="cyan"))


def display_diff(
    action: PendingAction, target_root: Path,
) -> None:
    """기존 파일 vs 새 내용의 Side-by-Side Diff(차분) 뷰를 표시한다."""
    old_text = _read_existing(action, target_root)
    new_text = action.content

    if not old_text:
        _console.print(f"[dim]{t('review.no_existing')}[/]")
        display_new_file(action, max_lines=_PREVIEW_MAX_LINES)
        return

    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    _render_side_by_side(old_lines, new_lines)


def display_new_file(
    action: PendingAction, max_lines: int = _PREVIEW_MAX_LINES,
) -> None:
    """새 파일(create_new) 내용을 Syntax 하이라이트(highlight)로 표시한다."""
    content = action.content
    lines = content.splitlines()
    truncated = len(lines) > max_lines
    if truncated:
        content = "\n".join(lines[:max_lines])

    syntax = Syntax(content, "markdown", theme="monokai", line_numbers=True)
    panel = Panel(syntax, title=t("review.preview_title"))
    _console.print(panel)

    if truncated:
        _console.print(f"[dim]{t('review.truncated', total=len(lines), shown=max_lines)}[/]")


def display_full_content(action: PendingAction) -> None:
    """전체 내용을 상세(detail) 출력한다."""
    syntax = Syntax(
        action.content, "markdown", theme="monokai", line_numbers=True,
    )
    _console.print(Panel(syntax, title=t("review.full_content_title")))


def display_prompt() -> None:
    """사용자 입력 프롬프트(prompt)를 표시한다."""
    _console.print(
        f"[bold][y][/bold]{t('review.prompt_approve')}  "
        f"[bold][n][/bold]{t('review.prompt_reject')}  "
        f"[bold][s][/bold]{t('review.prompt_skip')}  "
        f"[bold][e][/bold]{t('review.prompt_edit')}  "
        f"[bold][d][/bold]{t('review.prompt_detail')}  "
        f"[bold][q][/bold]{t('review.prompt_quit')}",
        end=" > ",
    )


def display_summary(
    approved: int, rejected: int, skipped: int,
) -> None:
    """검토 완료 후 최종 요약(summary)을 표시한다."""
    _console.print()
    _console.print(
        f"[bold]{t('review.summary', approved=approved, rejected=rejected, skipped=skipped)}[/]",
    )


# ------------------------------------------------------------------
# 내부 헬퍼(helper) 함수
# ------------------------------------------------------------------

def _extract_score(action: PendingAction) -> str:
    """pending 파일의 frontmatter에서 relevance_score를 추출한다."""
    import re
    try:
        text = action.file_path.read_text(encoding="utf-8")
    except OSError:
        return "N/A"
    match = re.search(r"relevance_score:\s*([\d.]+)", text)
    return match.group(1) if match else "N/A"


def _read_existing(action: PendingAction, target_root: Path) -> str:
    """action의 target에 해당하는 기존 파일 내용을 읽는다."""
    target = action.target
    if not target:
        return ""
    # 경로(path) 정규화: 절대경로 또는 상대경로 처리
    target_path = _resolve_target_file(action, target_root)
    if not target_path or not target_path.exists():
        return ""
    try:
        return target_path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _resolve_target_file(
    action: PendingAction, target_root: Path,
) -> Path | None:
    """action_type 기반으로 실제 대상 파일 경로를 결정한다."""
    at = action.action_type
    if at in ("create_skill", "merge_skill", "refine_skill"):
        return target_root / ".claude" / "skills" / f"{action.name}.md"
    if at in ("create_agent", "refine_agent"):
        return target_root / ".claude" / "agents" / f"{action.name}.md"
    if at == "add_rule":
        return target_root / "CLAUDE.md"
    return None


def _render_side_by_side(
    old_lines: list[str], new_lines: list[str],
) -> None:
    """difflib을 활용한 좌우 비교(Side-by-Side) 테이블을 렌더링한다."""
    table = Table(show_header=True, expand=True, border_style="dim")
    table.add_column(t("review.existing_col"), style="dim", ratio=1)
    table.add_column(t("review.changed_col"), ratio=1)

    opcodes = difflib.SequenceMatcher(
        None, old_lines, new_lines,
    ).get_opcodes()

    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            _add_equal_rows(table, old_lines[i1:i2])
        elif tag == "replace":
            _add_replace_rows(table, old_lines[i1:i2], new_lines[j1:j2])
        elif tag == "delete":
            _add_delete_rows(table, old_lines[i1:i2])
        elif tag == "insert":
            _add_insert_rows(table, new_lines[j1:j2])

    panel = Panel(table, title=t("review.diff_title"))
    _console.print(panel)


def _add_equal_rows(table: Table, lines: list[str]) -> None:
    """변경 없는(equal) 줄들을 테이블에 추가한다."""
    for line in lines:
        table.add_row(line, line)


def _add_replace_rows(
    table: Table, old: list[str], new: list[str],
) -> None:
    """교체(replace)된 줄들을 빨강/초록으로 표시한다."""
    max_len = max(len(old), len(new))
    for k in range(max_len):
        old_text = Text(old[k], style="red") if k < len(old) else Text("")
        new_text = Text(new[k], style="green") if k < len(new) else Text("")
        table.add_row(old_text, new_text)


def _add_delete_rows(table: Table, lines: list[str]) -> None:
    """삭제(delete)된 줄을 적색으로 표시한다."""
    for line in lines:
        table.add_row(Text(line, style="red"), Text(""))


def _add_insert_rows(table: Table, lines: list[str]) -> None:
    """추가(insert)된 줄을 녹색으로 표시한다."""
    for line in lines:
        table.add_row(Text(""), Text(line, style="green"))
