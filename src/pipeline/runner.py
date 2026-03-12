"""Phase 실행 오케스트레이터(pipeline runner) 모듈.

Phase 1~4 실행, 자동 심사, 전체 파이프라인 조정을 담당한다.
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console

from src.pipeline.pipeline_output import (
    display_dry_run_rich,
    print_summary,
    write_obsidian,
    write_report,
)
from src.utils.batch_splitter import split_raw_file
from src.utils.i18n import t
from src.utils.logger import get_logger
from src.utils.paths import ANALYSIS_DIR, RAW_DIR

# 중앙 경로(centralized path) 모듈에서 가져옴
_RAW_DIR: Path = RAW_DIR
_ANALYSIS_DIR: Path = ANALYSIS_DIR

_logger = get_logger("pipeline_runner")
_console = Console()


def find_latest_md(directory: Path) -> Path | None:
    """디렉토리에서 가장 최근 .md 파일을 반환한다."""
    if not directory.is_dir():
        return None
    files = sorted(directory.glob("*.md"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def run_phase1(
    since: datetime | None, full_sync: bool,
) -> Path:
    """Phase 1: 수집(collection) -> data/raw/{ts}.md."""
    from src.collector.auth_manager import AuthManager
    from src.collector.threads_scraper import ThreadsScraper
    from src.config import Config
    from src.utils.state import get_seen_post_ids

    auth = AuthManager(account=Config().threads_account)
    if not auth.is_session_valid():
        _console.print(
            f"[bold red]{t('runner.no_auth')}[/]\n"
            f"{t('runner.auth_hint')}"
        )
        sys.exit(1)

    scraper = ThreadsScraper(auth)
    collect_since = None if full_sync else since
    # seen_ids: full_sync가 아닐 때만 적용 (이중 중복 방지)
    seen_ids = None if full_sync else get_seen_post_ids()
    raw_path = scraper.collect(since=collect_since, seen_ids=seen_ids)
    _logger.info(t("runner.phase1_done", name=raw_path.name))
    return raw_path


def run_phase2(raw_md_path: Path) -> Path:
    """Phase 2: 분석(analysis) -> data/analysis/{ts}.md."""
    from src.ai_adapter import get_adapter
    from src.config import Config
    from src.processor.analyzer import Analyzer
    from src.processor.context_builder import ContextBuilder

    config = Config()
    adapter = get_adapter(config.ai_provider)
    ctx = ContextBuilder(config.target_project_path)
    analyzer = Analyzer(adapter, ctx)

    analysis_path = analyzer.analyze(raw_md_path)
    _logger.info(t("runner.phase2_done", name=analysis_path.name))
    return analysis_path


def run_phase3(
    analysis_md_path: Path, dry_run: bool,
) -> list[Path]:
    """Phase 3: 강화 초안(enhancement draft) 생성."""
    from src.ai_adapter import get_adapter
    from src.config import Config
    from src.enhancer.generator import EnhancementGenerator
    from src.processor.context_builder import ContextBuilder

    config = Config()
    adapter = get_adapter(config.ai_provider)
    ctx = ContextBuilder(config.target_project_path)
    gen = EnhancementGenerator(adapter, ctx, config)

    if dry_run:
        parsed = gen.generate_dry_run_parsed(analysis_md_path)
        _console.print(f"\n[bold]{t('runner.phase3_preview')}[/]")
        if isinstance(parsed, str):
            _console.print(parsed)
        else:
            display_dry_run_rich(parsed, config.target_project_path)
        return []

    pending_paths = gen.generate(analysis_md_path)
    _logger.info(t("runner.phase3_done", n=len(pending_paths)))
    return pending_paths


def run_auto_review(
    pending_paths: list[Path], dry_run: bool,
) -> list[Path]:
    """Phase 3->4 자동 심사(auto-review): 규칙 기반 필터링.

    Returns:
        심사 통과한 pending 파일 경로 리스트
    """
    if dry_run or not pending_paths:
        return pending_paths

    from src.config import Config
    from src.enhancer.reviewer import EnhancementReviewer

    config = Config()
    reviewer = EnhancementReviewer(config)
    result = reviewer.review(pending_paths)

    approved_count = len(result.approved)
    rejected_count = len(result.rejected)
    _console.print(
        f"[bold]{t('runner.auto_review_done', approved=approved_count, rejected=rejected_count)}[/]",
    )
    for _, reason in result.rejected:
        _console.print(f"  [dim]{t('runner.rejected_reason', reason=reason)}[/]")

    _logger.info(
        t("runner.auto_review_done", approved=approved_count, rejected=rejected_count),
    )
    return result.approved


def run_phase4(dry_run: bool) -> list:
    """Phase 4: 적용(apply) 또는 대기.

    Returns:
        적용된 PendingAction 목록 (dict 변환 포함)
    """
    from src.config import Config
    from src.enhancer.applier import Applier

    if dry_run:
        _console.print(f"[dim]{t('runner.dryrun_skip')}[/]")
        return []

    config = Config()
    applier = Applier(config)
    actions = applier.load_pending()
    applier.apply(actions)
    _logger.info(t("runner.phase4_done", n=len(actions)))
    return actions_to_dicts(actions)


def actions_to_dicts(actions: list) -> list[dict]:
    """PendingAction 리스트를 dict 리스트로 변환한다."""
    return [
        {
            "action_type": a.action_type,
            "name": a.name,
            "target": a.target,
            "source_posts": a.source_posts,
        }
        for a in actions
    ]


# ======================================================================
# 특정 Phase 재실행(phase re-run)
# ======================================================================

def cmd_phase(phase: int, dry_run: bool) -> None:
    """--phase N: 특정 Phase만 재실행한다."""
    if phase == 2:
        raw_path = find_latest_md(_RAW_DIR)
        if not raw_path:
            _console.print(f"[red]{t('runner.no_raw')}[/]")
            sys.exit(1)
        _console.print(t("runner.rerun_phase2", name=raw_path.name))
        run_phase2(raw_path)

    elif phase == 3:
        analysis_path = find_latest_md(_ANALYSIS_DIR)
        if not analysis_path:
            _console.print(f"[red]{t('runner.no_analysis')}[/]")
            sys.exit(1)
        _console.print(t("runner.rerun_phase3", name=analysis_path.name))
        run_phase3(analysis_path, dry_run)

    elif phase == 4:
        run_phase4(dry_run)


# ======================================================================
# 기본 파이프라인(default pipeline)
# ======================================================================

def parse_since(since_str: str | None) -> datetime | None:
    """--since 인자를 datetime으로 파싱한다."""
    if since_str is None:
        return None
    try:
        return datetime.fromisoformat(since_str)
    except ValueError:
        _console.print(f"[red]{t('runner.date_format_error', val=since_str)}[/]")
        sys.exit(1)


def determine_since(
    args_since: str | None, full_sync: bool,
) -> datetime | None:
    """수집 시작 시점(since)을 결정한다."""
    if full_sync:
        return None
    if args_since:
        return parse_since(args_since)

    from src.utils.state import get_last_sync
    return get_last_sync()


def is_empty_collection(raw_text: str) -> bool:
    """수집 결과가 비어있는지 확인한다."""
    # "수집 건수: 0" 또는 포스트 구분자가 없으면 비어있음
    if "수집 건수: 0" in raw_text:
        return True
    return raw_text.count("\n---\n") == 0


def update_state(
    raw_path: Path,
    collection_start: datetime | None = None,
) -> None:
    """state.json을 갱신한다.

    Args:
        raw_path: raw markdown 파일 경로
        collection_start: 수집 시작 시각 (None이면 현재 시각 사용)
    """
    from src.utils.state import update_last_sync, update_seen_post_ids

    text = raw_path.read_text(encoding="utf-8")
    post_count = max(text.count("\n---\n"), 0)
    # 마지막 post_id 추출
    ids = re.findall(r"\*\*post_id\*\*:\s*(\S+)", text)
    last_id = ids[-1] if ids else ""

    # last_sync를 수집 시작 시각(collection start)으로 기록하여
    # 재실행 시 수집 중 저장된 포스트가 필터링되는 문제를 방지
    sync_time = collection_start or datetime.now()
    update_last_sync(sync_time, post_count, last_id)

    # seen_post_ids 갱신 (중복 수집 방지)
    if ids:
        update_seen_post_ids(set(ids))


def _verify_ai_adapter(provider: str) -> None:
    """AI 어댑터(adapter) 가용성과 버전을 확인한다."""
    from src.ai_adapter import get_adapter

    adapter = get_adapter(provider)
    if not adapter.is_available():
        _console.print(
            f"[red]{t('runner.ai_unavailable', provider=provider)}[/]"
        )
        sys.exit(1)
    adapter.check_version()


def _collect_and_validate(args: argparse.Namespace) -> tuple[Path | None, datetime]:
    """Phase 1 수집(collection) 실행 후 비어있으면 (None, start_time)을 반환한다.

    Returns:
        (raw_path 또는 None, 수집 시작 시각)
    """
    # 수집 시작 시각(collection start) 기록 — last_sync에 이 값을 저장
    collection_start = datetime.now()

    since = determine_since(args.since, args.full_sync)
    raw_path = run_phase1(since, args.full_sync)

    raw_text = raw_path.read_text(encoding="utf-8")
    if is_empty_collection(raw_text):
        _console.print(f"[dim]{t('runner.no_new_posts')}[/]")
        return None, collection_start
    return raw_path, collection_start


# 배치 간 대기(delay) — Rate Limit 방어
_BATCH_DELAY_SEC: int = 10


def _run_batch_phases(
    batches: list[Path], dry_run: bool,
) -> tuple[list[Path], list[Path]]:
    """배치별 Phase 2~3을 반복 실행한다.

    Returns:
        (분석 경로 리스트, pending 경로 리스트)
    """
    analysis_paths: list[Path] = []
    pending_paths: list[Path] = []

    for i, batch_path in enumerate(batches, 1):
        if len(batches) > 1:
            _console.print(f"\n[bold]{t('runner.batch_progress', i=i, total=len(batches))}[/]")

        # 2번째 배치부터 Rate Limit 방어를 위해 대기
        if i > 1:
            _logger.info(t("runner.rate_limit", sec=_BATCH_DELAY_SEC))
            import time
            time.sleep(_BATCH_DELAY_SEC)

        analysis_path = run_phase2(batch_path)
        analysis_paths.append(analysis_path)

        pending = run_phase3(analysis_path, dry_run)
        pending_paths.extend(pending)

    return analysis_paths, pending_paths


def _finalize(
    args: argparse.Namespace, raw_path: Path,
    analysis_paths: list[Path], pending_paths: list[Path],
    enhance_actions: list,
    collection_start: datetime | None = None,
) -> None:
    """Obsidian 아카이빙, 리포트 생성, state 갱신, 요약 출력."""
    if analysis_paths:
        write_obsidian(analysis_paths, args.dry_run)

        if not args.dry_run:
            write_report(analysis_paths[-1], enhance_actions, pending_paths)

    if not args.dry_run:
        update_state(raw_path, collection_start=collection_start)


def run_pipeline(args: argparse.Namespace) -> None:
    """전체 4-Phase 파이프라인을 실행한다."""
    from src.config import Config

    config = Config()
    _console.print(f"[bold]{t('main.pipeline_start')}[/]")

    _verify_ai_adapter(config.ai_provider)

    # Phase 1: 수집
    raw_path, collection_start = _collect_and_validate(args)
    if raw_path is None:
        return

    # Phase 2~3: 배치 분할(batch split) 후 분석·강화
    batches = split_raw_file(
        raw_path, config.max_posts_per_batch, config.max_chars_per_batch,
    )
    analysis_paths, pending_paths = _run_batch_phases(batches, args.dry_run)

    # Phase 3.5: 자동 심사(auto-review)
    pending_paths = run_auto_review(pending_paths, args.dry_run)

    # Phase 4: 적용(apply)
    enhance_actions = run_phase4(args.dry_run)

    # 후처리(finalization): 아카이빙, 리포트, state, 요약
    _finalize(
        args, raw_path, analysis_paths, pending_paths,
        enhance_actions, collection_start=collection_start,
    )
    print_summary(
        len(batches), len(analysis_paths),
        len(pending_paths), args.dry_run,
    )
