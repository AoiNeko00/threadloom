"""파이프라인 출력(pipeline output) 모듈.

dry-run 시각화, Obsidian 아카이빙, 리포트 생성을 담당한다.
"""

from pathlib import Path

from rich.console import Console

from src.utils.frontmatter import parse_frontmatter
from src.utils.i18n import t
from src.utils.logger import get_logger

_logger = get_logger("pipeline_output")
_console = Console()


def display_dry_run_rich(
    parsed: list[dict], target_project_path: str,
) -> None:
    """dry-run 결과를 rich 테이블 + 미리보기(preview)로 시각화한다."""
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.table import Table

    # 요약 테이블(summary table)
    table = Table(title=t("output.preview_title"), show_lines=True)
    table.add_column("#", style="bold", width=3)
    table.add_column("action", style="cyan", width=14)
    table.add_column("name", style="green")
    table.add_column("target", style="dim")
    table.add_column("score", justify="right", width=6)

    for i, item in enumerate(parsed, 1):
        meta = item.get("metadata", {})
        table.add_row(
            str(i),
            meta.get("action_type", "?"),
            meta.get("name", "?"),
            meta.get("target", "?"),
            str(meta.get("relevance_score", "?")),
        )

    _console.print(table)

    # 각 항목의 내용 미리보기
    for i, item in enumerate(parsed, 1):
        meta = item.get("metadata", {})
        content = item.get("content", "")
        title = f"[{i}] {meta.get('action_type', '?')} — {meta.get('name', '?')}"

        # 30줄까지만 표시
        lines = content.splitlines()
        preview = "\n".join(lines[:30])
        if len(lines) > 30:
            preview += f"\n{t('output.more_lines', n=len(lines) - 30)}"

        _console.print(Panel(
            Syntax(preview, "markdown", theme="monokai", word_wrap=True),
            title=title,
            border_style="green" if meta.get("action_type") == "create_new" else "yellow",
        ))


def write_obsidian(
    analysis_paths: list[Path], dry_run: bool,
) -> None:
    """Obsidian vault에 모든 배치(batch)의 아카이브를 저장한다."""
    from src.config import Config
    from src.writer.obsidian_writer import ObsidianWriter

    config = Config()
    if not config.obsidian_enabled:
        return

    writer = ObsidianWriter(config)
    for path in analysis_paths:
        if dry_run:
            report = writer.dry_run_report(path)
            _console.print(f"\n[bold]{t('output.obsidian_preview')}[/]")
            _console.print(report)
        else:
            writer.write_all(path)


def write_report(
    analysis_md_path: Path,
    enhance_actions: list[dict],
    pending_paths: list[Path] | None = None,
) -> None:
    """실행 리포트(report)를 생성한다.

    Phase 4 적용 결과가 없으면 Phase 3 pending 파일에서 액션을 추출한다.
    """
    from src.config import Config
    from src.writer.report_writer import ReportWriter

    # Phase 4 결과가 비어 있고 pending 파일이 있으면 pending에서 액션 추출
    if not enhance_actions and pending_paths:
        enhance_actions = extract_actions_from_pending(pending_paths)

    config = Config()
    writer = ReportWriter(config)
    path = writer.write(
        analysis_md_path,
        enhance_actions=enhance_actions,
        obsidian_enabled=config.obsidian_enabled,
    )
    _logger.info(t("output.report_saved", name=path.name))


def extract_actions_from_pending(paths: list[Path]) -> list[dict]:
    """pending md 파일에서 강화 액션(enhancement action) 정보를 추출한다."""
    actions: list[dict] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        meta, _ = parse_frontmatter(text)
        if meta and "action_type" in meta:
            actions.append(meta)
    return actions


def print_summary(
    batch_count: int,
    analysis_count: int,
    pending_count: int,
    dry_run: bool,
) -> None:
    """파이프라인 실행 완료 요약을 출력한다."""
    from src.utils.notify import send_notification

    mode = " (dry-run)" if dry_run else ""
    _console.print(f"\n[bold green]{t('output.pipeline_done', mode=mode)}[/]")
    _console.print(f"  {t('output.batch_count', n=batch_count)}")
    _console.print(f"  {t('output.analysis_count', n=analysis_count)}")
    _console.print(f"  {t('output.pending_count', n=pending_count)}")

    # 데스크탑 알림(desktop notification)
    if pending_count > 0 and not dry_run:
        send_notification(
            "threadloom",
            f"{pending_count}건의 강화 항목이 검토를 기다리고 있습니다.",
        )
    elif dry_run:
        send_notification("threadloom", f"dry-run 완료: {pending_count}건 미리보기")
