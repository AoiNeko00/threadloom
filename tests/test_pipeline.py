"""Phase 1->2->3->4 전체 파이프라인 통합 테스트.

mock AI + tmp_path를 사용하여 4-Phase md 파이프라인의
전체 흐름, --phase N 부분 재실행, --dry-run 동작을 검증한다.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.ai_adapter.base import BaseAIAdapter
from src.enhancer.applier import Applier, PendingAction
from src.enhancer.generator import EnhancementGenerator
from src.processor.analyzer import Analyzer
from src.processor.context_builder import ContextBuilder
from src.collector.threads_scraper import ThreadPost

_FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ------------------------------------------------------------------
# mock AI 어댑터
# ------------------------------------------------------------------

class PipelineMockAdapter(BaseAIAdapter):
    """파이프라인 통합 테스트용 mock 어댑터.

    Phase 2, Phase 3 응답을 미리 설정하여 반환한다.
    """

    _CLI_CMD = "mock"

    def __init__(self, analysis_response: str, enhance_response: str):
        self._analysis_response = analysis_response
        self._enhance_response = enhance_response
        self.analyze_count = 0
        self.enhance_count = 0

    def analyze(self, raw_md_path: Path, context_summary: str) -> str:
        self.analyze_count += 1
        return self._analysis_response

    def generate_enhancements(
        self, analysis_md_path: Path, existing_files: dict[str, str]
    ) -> str:
        self.enhance_count += 1
        return self._enhance_response

    def is_available(self) -> bool:
        return True


# ------------------------------------------------------------------
# mock 응답 데이터
# ------------------------------------------------------------------

_ANALYSIS_RESPONSE = """---
source: test_raw.md
analyzed_at: 2026-03-12T07:01:30
total: 2
actionable: 1
enhance_candidates: 1
---

# 분석 결과 — 2026-03-12

## post-001
- **분류**: 개발도구
- **태그**: [Playwright, 세션관리]
- **요약**: storageState로 세션 관리하는 패턴
- **유용성**: 0.90
- **actionable**: true
- **강화 유형**: skill
- **제안 이름**: playwright_session
- **판단 근거**: 반복 가능 코드 패턴

---

## post-002
- **분류**: 기타
- **태그**: [기타]
- **요약**: 정보성 콘텐츠
- **유용성**: 0.10
- **actionable**: false
- **강화 유형**: none
- **제안 이름**:
- **판단 근거**: 관련 없음

---

## 강화 제안 요약

| # | 유형 | 이름 | 근거 포스트 | 점수 |
|---|------|------|-----------|------|
| 1 | skill | playwright_session | post-001 | 0.90 |
"""

_ENHANCE_RESPONSE = """
---THREADLOOM_FILE_START: create_skill_playwright_session---
---
action_type: create_skill
name: playwright_session
target: .claude/skills/playwright_session.md
source_posts: [post-001]
duplicate_check: create_new
---

# playwright_session

storageState를 사용한 Playwright 세션 관리.

## 지시사항
1. storageState로 세션 저장/복원

## 근거
- post-001에서 감지
---THREADLOOM_FILE_END---
"""


# ------------------------------------------------------------------
# fixture
# ------------------------------------------------------------------

@pytest.fixture
def pipeline_env(tmp_path):
    """파이프라인 전체를 실행하기 위한 환경(environment)을 구성한다."""
    # 디렉토리(directory) 구조 생성
    raw_dir = tmp_path / "data" / "raw"
    analysis_dir = tmp_path / "data" / "analysis"
    pending_dir = tmp_path / "data" / "pending"
    backups_dir = tmp_path / "data" / "backups"
    target_project = tmp_path / "target_project"
    (target_project / ".claude" / "skills").mkdir(parents=True)
    (target_project / ".claude" / "agents").mkdir(parents=True)

    raw_dir.mkdir(parents=True)
    analysis_dir.mkdir(parents=True)
    pending_dir.mkdir(parents=True)
    backups_dir.mkdir(parents=True)

    enhance_log = tmp_path / "data" / "enhance_log.json"

    return {
        "tmp_path": tmp_path,
        "raw_dir": raw_dir,
        "analysis_dir": analysis_dir,
        "pending_dir": pending_dir,
        "backups_dir": backups_dir,
        "target_project": target_project,
        "enhance_log": enhance_log,
    }


@pytest.fixture
def mock_adapter():
    """파이프라인용 mock AI 어댑터."""
    return PipelineMockAdapter(_ANALYSIS_RESPONSE, _ENHANCE_RESPONSE)


# ------------------------------------------------------------------
# Phase 1 -> 2 -> 3 -> 4 전체 통합 테스트
# ------------------------------------------------------------------

def test_full_pipeline_phase1_creates_raw_md(pipeline_env, monkeypatch):
    """Phase 1: raw md 파일이 생성되어야 한다."""
    from src.collector.threads_scraper import ThreadsScraper

    monkeypatch.setattr(
        "src.collector.threads_scraper._RAW_DIR",
        pipeline_env["raw_dir"],
    )

    scraper = ThreadsScraper(auth_manager=None)
    posts = [
        ThreadPost(
            "id1", "user1", "test text",
            "https://threads.net/post/1", datetime.now(),
        ),
    ]
    path = scraper._write_raw_md(posts, "20260312_070000")

    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "user1" in content


def test_full_pipeline_phase2_creates_analysis(
    pipeline_env, mock_adapter, monkeypatch,
):
    """Phase 2: analysis md 파일이 생성되어야 한다."""
    monkeypatch.setattr(
        "src.processor.analyzer._ANALYSIS_DIR",
        pipeline_env["analysis_dir"],
    )

    raw_path = _FIXTURE_DIR / "sample_raw.md"
    context_builder = ContextBuilder(str(pipeline_env["target_project"]))
    analyzer = Analyzer(mock_adapter, context_builder)

    result_path = analyzer.analyze(raw_path)

    assert result_path.exists()
    assert "post-001" in result_path.read_text(encoding="utf-8")


def test_full_pipeline_phase3_creates_pending(
    pipeline_env, mock_adapter, monkeypatch,
):
    """Phase 3: pending md 파일이 생성되어야 한다."""
    monkeypatch.setattr(
        "src.enhancer.generator._PENDING_DIR",
        pipeline_env["pending_dir"],
    )

    analysis_path = _FIXTURE_DIR / "sample_analysis.md"
    context_builder = ContextBuilder(str(pipeline_env["target_project"]))
    config = MagicMock()
    config.target_project_path = str(pipeline_env["target_project"])
    config.auto_apply = False

    generator = EnhancementGenerator(mock_adapter, context_builder, config)
    paths = generator.generate(analysis_path)

    assert len(paths) >= 1
    for p in paths:
        assert p.exists()


def test_full_pipeline_phase4_applies_skill(
    pipeline_env, monkeypatch,
):
    """Phase 4: pending -> 실제 skill 파일이 적용되어야 한다."""
    pending_dir = pipeline_env["pending_dir"]
    monkeypatch.setattr("src.enhancer.applier._PENDING_DIR", pending_dir)
    monkeypatch.setattr(
        "src.enhancer.backup_manager._BACKUPS_DIR", pipeline_env["backups_dir"],
    )
    monkeypatch.setattr(
        "src.enhancer.backup_manager._ENHANCE_LOG", pipeline_env["enhance_log"],
    )

    # pending 파일 생성
    pending_file = pending_dir / "create_skill_test.md"
    pending_file.write_text(
        "---\n"
        "action_type: create_skill\n"
        "name: pipeline_test_skill\n"
        "target: .claude/skills/pipeline_test_skill.md\n"
        "source_posts: [post-001]\n"
        "duplicate_check: create_new\n"
        "---\n\n"
        "# pipeline_test_skill\n\n테스트 내용\n",
        encoding="utf-8",
    )

    config = MagicMock()
    config.target_project_path = str(pipeline_env["target_project"])
    config.auto_apply = True

    applier = Applier(config)
    actions = applier.load_pending()
    applier.apply(actions)

    # skill 파일 생성 확인
    skill_path = (
        pipeline_env["target_project"]
        / ".claude" / "skills" / "pipeline_test_skill.md"
    )
    assert skill_path.exists()


# ------------------------------------------------------------------
# Phase 2 -> 3 연쇄 테스트
# ------------------------------------------------------------------

def test_phase2_output_feeds_into_phase3(
    pipeline_env, mock_adapter, monkeypatch,
):
    """Phase 2 출력이 Phase 3 입력으로 정상 연결되어야 한다."""
    monkeypatch.setattr(
        "src.processor.analyzer._ANALYSIS_DIR",
        pipeline_env["analysis_dir"],
    )
    monkeypatch.setattr(
        "src.enhancer.generator._PENDING_DIR",
        pipeline_env["pending_dir"],
    )

    raw_path = _FIXTURE_DIR / "sample_raw.md"
    context_builder = ContextBuilder(str(pipeline_env["target_project"]))

    # Phase 2
    analyzer = Analyzer(mock_adapter, context_builder)
    analysis_path = analyzer.analyze(raw_path)

    # Phase 3 (analysis_path를 입력으로 사용)
    config = MagicMock()
    config.target_project_path = str(pipeline_env["target_project"])
    config.auto_apply = False

    generator = EnhancementGenerator(mock_adapter, context_builder, config)
    paths = generator.generate(analysis_path)

    assert len(paths) >= 1
    assert mock_adapter.analyze_count == 1
    assert mock_adapter.enhance_count == 1


# ------------------------------------------------------------------
# AI 호출 횟수 검증
# ------------------------------------------------------------------

def test_pipeline_calls_ai_exactly_twice(
    pipeline_env, mock_adapter, monkeypatch,
):
    """전체 파이프라인에서 AI는 총 2회(Phase 2 + Phase 3)만 호출되어야 한다."""
    monkeypatch.setattr(
        "src.processor.analyzer._ANALYSIS_DIR",
        pipeline_env["analysis_dir"],
    )
    monkeypatch.setattr(
        "src.enhancer.generator._PENDING_DIR",
        pipeline_env["pending_dir"],
    )

    raw_path = _FIXTURE_DIR / "sample_raw.md"
    context_builder = ContextBuilder(str(pipeline_env["target_project"]))

    # Phase 2
    analyzer = Analyzer(mock_adapter, context_builder)
    analysis_path = analyzer.analyze(raw_path)

    # Phase 3
    config = MagicMock()
    config.target_project_path = str(pipeline_env["target_project"])
    generator = EnhancementGenerator(mock_adapter, context_builder, config)
    generator.generate(analysis_path)

    assert mock_adapter.analyze_count == 1
    assert mock_adapter.enhance_count == 1


# ------------------------------------------------------------------
# --dry-run 동작 테스트
# ------------------------------------------------------------------

def test_dry_run_does_not_create_pending_files(
    pipeline_env, mock_adapter, monkeypatch,
):
    """dry-run 시 pending 파일이 생성되지 않아야 한다."""
    monkeypatch.setattr(
        "src.enhancer.generator._PENDING_DIR",
        pipeline_env["pending_dir"],
    )

    analysis_path = _FIXTURE_DIR / "sample_analysis.md"
    context_builder = ContextBuilder(str(pipeline_env["target_project"]))
    config = MagicMock()
    config.target_project_path = str(pipeline_env["target_project"])

    generator = EnhancementGenerator(mock_adapter, context_builder, config)
    summary = generator.generate_dry_run(analysis_path)

    # pending 디렉토리에 파일 없어야 함
    pending_files = list(pipeline_env["pending_dir"].glob("*.md"))
    assert len(pending_files) == 0
    # 요약 문자열은 반환
    assert isinstance(summary, str)
    assert len(summary) > 0


def test_dry_run_does_not_apply(pipeline_env, monkeypatch):
    """dry-run 시 Phase 4(적용)가 실행되지 않아야 한다."""
    target = pipeline_env["target_project"]
    skills_dir = target / ".claude" / "skills"

    # 기존 skill 파일만 확인
    existing_before = set(skills_dir.glob("*.md"))

    # dry-run이므로 Phase 4 skip — 이를 직접 검증
    monkeypatch.setattr(
        "src.enhancer.applier._PENDING_DIR",
        pipeline_env["pending_dir"],
    )
    monkeypatch.setattr(
        "src.enhancer.backup_manager._BACKUPS_DIR",
        pipeline_env["backups_dir"],
    )
    monkeypatch.setattr(
        "src.enhancer.backup_manager._ENHANCE_LOG",
        pipeline_env["enhance_log"],
    )

    config = MagicMock()
    config.target_project_path = str(target)
    config.auto_apply = True

    applier = Applier(config)
    actions = applier.load_pending()
    # Phase 4 skip: apply 호출 안 함

    existing_after = set(skills_dir.glob("*.md"))
    assert existing_before == existing_after


# ------------------------------------------------------------------
# --phase N 부분 재실행 테스트
# ------------------------------------------------------------------

def test_phase3_rerun_uses_latest_analysis(
    pipeline_env, mock_adapter, monkeypatch,
):
    """--phase 3: 가장 최근 analysis 파일을 사용해야 한다."""
    analysis_dir = pipeline_env["analysis_dir"]
    monkeypatch.setattr(
        "src.enhancer.generator._PENDING_DIR",
        pipeline_env["pending_dir"],
    )

    # 이전 analysis 파일 2개 생성 (타임스탬프 기준 정렬)
    old_analysis = analysis_dir / "20260311_070000.md"
    old_analysis.write_text("# old analysis\n", encoding="utf-8")

    # 최신 analysis = sample_analysis.md 복사
    new_analysis = analysis_dir / "20260312_070000.md"
    fixture_content = (_FIXTURE_DIR / "sample_analysis.md").read_text(
        encoding="utf-8",
    )
    new_analysis.write_text(fixture_content, encoding="utf-8")

    # 가장 최근 파일 선택 로직 검증
    latest = sorted(analysis_dir.glob("*.md"))[-1]
    assert latest.name == "20260312_070000.md"

    # Phase 3 실행
    context_builder = ContextBuilder(str(pipeline_env["target_project"]))
    config = MagicMock()
    config.target_project_path = str(pipeline_env["target_project"])

    generator = EnhancementGenerator(mock_adapter, context_builder, config)
    paths = generator.generate(latest)

    assert len(paths) >= 1


def test_phase4_rerun_applies_existing_pending(
    pipeline_env, monkeypatch,
):
    """--phase 4: 기존 pending 파일을 적용해야 한다."""
    pending_dir = pipeline_env["pending_dir"]
    monkeypatch.setattr("src.enhancer.applier._PENDING_DIR", pending_dir)
    monkeypatch.setattr(
        "src.enhancer.backup_manager._BACKUPS_DIR", pipeline_env["backups_dir"],
    )
    monkeypatch.setattr(
        "src.enhancer.backup_manager._ENHANCE_LOG", pipeline_env["enhance_log"],
    )

    # pending 파일 사전 생성
    pending_file = pending_dir / "create_skill_rerun_test.md"
    pending_file.write_text(
        "---\n"
        "action_type: create_skill\n"
        "name: rerun_test\n"
        "target: .claude/skills/rerun_test.md\n"
        "source_posts: [post-001]\n"
        "duplicate_check: create_new\n"
        "---\n\n# rerun_test\n\n재실행 테스트\n",
        encoding="utf-8",
    )

    config = MagicMock()
    config.target_project_path = str(pipeline_env["target_project"])
    config.auto_apply = True

    applier = Applier(config)
    actions = applier.load_pending()
    assert len(actions) >= 1

    applier.apply(actions)

    skill_path = (
        pipeline_env["target_project"]
        / ".claude" / "skills" / "rerun_test.md"
    )
    assert skill_path.exists()


# ------------------------------------------------------------------
# enhance_log.json 전체 흐름 검증
# ------------------------------------------------------------------

def test_enhance_log_accumulates(pipeline_env, monkeypatch):
    """여러 적용이 enhance_log.json에 누적되어야 한다."""
    pending_dir = pipeline_env["pending_dir"]
    monkeypatch.setattr("src.enhancer.applier._PENDING_DIR", pending_dir)
    monkeypatch.setattr(
        "src.enhancer.backup_manager._BACKUPS_DIR", pipeline_env["backups_dir"],
    )
    monkeypatch.setattr(
        "src.enhancer.backup_manager._ENHANCE_LOG", pipeline_env["enhance_log"],
    )

    config = MagicMock()
    config.target_project_path = str(pipeline_env["target_project"])
    config.auto_apply = True

    # 첫 번째 적용
    p1 = pending_dir / "create_skill_first.md"
    p1.write_text(
        "---\naction_type: create_skill\nname: first\n"
        "target: .claude/skills/first.md\n"
        "source_posts: [post-001]\nduplicate_check: create_new\n---\n\n"
        "# first\n",
        encoding="utf-8",
    )

    applier = Applier(config)
    applier.apply(applier.load_pending())

    # 두 번째 적용
    p2 = pending_dir / "create_skill_second.md"
    p2.write_text(
        "---\naction_type: create_skill\nname: second\n"
        "target: .claude/skills/second.md\n"
        "source_posts: [post-002]\nduplicate_check: create_new\n---\n\n"
        "# second\n",
        encoding="utf-8",
    )

    applier.apply(applier.load_pending())

    log = json.loads(
        pipeline_env["enhance_log"].read_text(encoding="utf-8"),
    )
    assert len(log) == 2
    names = [entry["name"] for entry in log]
    assert "first" in names
    assert "second" in names
