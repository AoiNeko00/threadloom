"""수집 아카이브 시맨틱 검색(semantic search) 모듈."""

from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table

from src.utils.frontmatter import parse_frontmatter
from src.utils.i18n import t
from src.utils.logger import get_logger
from src.utils.paths import ANALYSIS_DIR, RAW_DIR

_logger = get_logger("search")
_console = Console()

# 중앙 경로(centralized path) 모듈에서 가져옴
_RAW_DIR = RAW_DIR
_ANALYSIS_DIR = ANALYSIS_DIR


@dataclass
class SearchHit:
    """검색 결과 항목."""

    file_path: Path
    source: str  # "raw" | "analysis"
    score: int
    tags: list[str]
    summary: str
    matched_lines: list[str]  # 본문에서 매칭된 줄 (최대 3개)


def search(query: str) -> list[SearchHit]:
    """data/raw/와 data/analysis/에서 쿼리를 검색한다."""
    hits: list[SearchHit] = []
    q = query.lower()

    for source, directory in [("raw", _RAW_DIR), ("analysis", _ANALYSIS_DIR)]:
        if not directory.is_dir():
            continue
        for md_file in directory.glob("*.md"):
            # 배치(batch) 파일 제외
            if "_batch" in md_file.stem:
                continue
            hit = _score_file(md_file, q, source)
            if hit and hit.score > 0:
                hits.append(hit)

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits


def display_search_results(query: str, hits: list[SearchHit]) -> None:
    """검색 결과를 Rich 테이블로 출력한다."""
    if not hits:
        _console.print(f"[dim]{t('search.no_results', query=query)}[/]")
        return

    table = Table(title=t("search.title", query=query, n=len(hits)))
    table.add_column(t("search.col_rank"), width=3)
    table.add_column(t("search.col_source"), width=10)
    table.add_column(t("search.col_file"), style="cyan")
    table.add_column(t("search.col_score"), justify="right", width=5)
    table.add_column(t("search.col_tags"), style="green")
    table.add_column(t("search.col_summary"))

    for i, hit in enumerate(hits[:20], 1):  # 최대 20건 표시
        tags_str = ", ".join(hit.tags[:3]) if hit.tags else "-"
        summary = hit.summary[:60] + "..." if len(hit.summary) > 60 else hit.summary
        table.add_row(
            str(i), hit.source, hit.file_path.name,
            str(hit.score), tags_str, summary or "-",
        )

    _console.print(table)

    # 매칭 라인 미리보기(preview) — 상위 3건
    for hit in hits[:3]:
        if hit.matched_lines:
            _console.print(f"\n[bold]{hit.file_path.name}[/]:")
            for line in hit.matched_lines[:3]:
                # 쿼리 하이라이트(highlight)
                _console.print(f"  [dim]...[/] {line.strip()[:120]}")


def interactive_search_results(
    query: str, hits: list[SearchHit],
) -> None:
    """검색 결과를 출력하고 대화형 프롬프트(interactive prompt)를 표시한다."""
    display_search_results(query, hits)

    if not hits:
        return

    _console.print(f"\n[dim]{t('search.prompt_help')}[/]")

    shown = hits[:20]  # 테이블에 표시된 항목만 대상

    while True:
        try:
            choice = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not choice or choice.lower() == "q":
            break

        # c번호: 경로 복사(clipboard copy)
        if choice.lower().startswith("c"):
            idx = _parse_index(choice[1:], len(shown))
            if idx is not None:
                _copy_path(shown[idx].file_path)
            continue

        # 번호: 에디터(editor)로 열기
        idx = _parse_index(choice, len(shown))
        if idx is not None:
            _open_in_editor(shown[idx].file_path)


def _parse_index(text: str, max_count: int) -> int | None:
    """입력값을 0-based 인덱스로 변환한다."""
    try:
        num = int(text)
        if 1 <= num <= max_count:
            return num - 1
    except ValueError:
        pass
    _console.print(f"[red]{t('search.invalid_range', max=max_count)}[/]")
    return None


def _open_in_editor(path: Path) -> None:
    """$EDITOR(기본 vim)로 파일을 연다."""
    import os
    import subprocess

    editor = os.environ.get("EDITOR", "vim")
    subprocess.run([editor, str(path)])


def _copy_path(path: Path) -> None:
    """파일 경로를 클립보드(clipboard)에 복사한다."""
    import subprocess
    import sys

    path_str = str(path)
    try:
        if sys.platform == "darwin":
            subprocess.run(
                ["pbcopy"], input=path_str, text=True, check=True,
            )
        elif sys.platform == "linux":
            subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=path_str, text=True, check=True,
            )
        else:
            _console.print(f"[dim]{t('search.path_display', path=path_str)}[/]")
            return
        _console.print(f"[green]{t('search.copied', path=path_str)}[/]")
    except (FileNotFoundError, subprocess.CalledProcessError):
        # 클립보드(clipboard) 명령 없을 때 경로 출력으로 폴백(fallback)
        _console.print(f"[dim]{t('search.path_display', path=path_str)}[/]")


def _score_file(path: Path, query: str, source: str) -> SearchHit | None:
    """파일을 읽고 점수(score)를 계산한다."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    tags, summary, body = _parse_md_parts(text)
    score = 0
    matched_lines: list[str] = []

    # 태그(tag) 매칭 (+3)
    for tag in tags:
        if query in tag.lower():
            score += 3
            break

    # 요약(summary) 매칭 (+2)
    if query in summary.lower():
        score += 2

    # 본문(body) 매칭 (+1 per hit, max 3)
    body_hits = 0
    for line in body.splitlines():
        if query in line.lower():
            matched_lines.append(line)
            body_hits += 1
            if body_hits >= 3:
                break
    score += body_hits

    if score == 0:
        return None

    return SearchHit(
        file_path=path, source=source, score=score,
        tags=tags, summary=summary, matched_lines=matched_lines,
    )


def _parse_md_parts(text: str) -> tuple[list[str], str, str]:
    """md 파일에서 tags, summary, body를 추출한다."""
    meta, body = parse_frontmatter(text)

    # tags 파싱(parsing) — 문자열/리스트 양쪽 대응
    tags: list[str] = []
    raw_tags = meta.get("tags", [])
    if isinstance(raw_tags, str):
        tags = [t.strip() for t in raw_tags.split(",")]
    elif isinstance(raw_tags, list):
        tags = [str(t) for t in raw_tags]

    summary = str(meta.get("summary", ""))
    return tags, summary, body
