"""Phase 2 분석(analysis) 모듈 테스트.

mock AI 어댑터를 사용하여 분석 결과 검증,
AI 호출 실패 시 fallback 동작을 테스트한다.
"""

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.ai_adapter.base import BaseAIAdapter
from src.processor.analyzer import Analyzer
from src.processor.context_builder import ContextBuilder

_FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ------------------------------------------------------------------
# mock AI 어댑터
# ------------------------------------------------------------------

class MockAIAdapter(BaseAIAdapter):
    """테스트용 mock AI 어댑터 — subprocess 호출 없이 고정 응답 반환."""

    _CLI_CMD = "mock"

    def __init__(self, response: str = "", should_fail: bool = False):
        self._response = response
        self._should_fail = should_fail
        self.call_count = 0

    def analyze(self, raw_md_path: Path, context_summary: str) -> str:
        self.call_count += 1
        if self._should_fail:
            raise RuntimeError("AI 호출 실패 (mock)")
        return self._response

    def generate_enhancements(
        self, analysis_md_path: Path, existing_files: dict[str, str]
    ) -> str:
        self.call_count += 1
        if self._should_fail:
            raise RuntimeError("AI 호출 실패 (mock)")
        return self._response

    def is_available(self) -> bool:
        return True


# ------------------------------------------------------------------
# 유효한 분석 결과 mock
# ------------------------------------------------------------------

_VALID_ANALYSIS = """---
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
- **요약**: storageState로 세션 관리
- **유용성**: 0.85
- **actionable**: true
- **강화 유형**: skill
- **제안 이름**: playwright_session
- **판단 근거**: 구체적 코드 패턴

---

## post-002
- **분류**: 기타
- **태그**: [기타]
- **요약**: 정보성 콘텐츠
- **유용성**: 0.20
- **actionable**: false
- **강화 유형**: none
- **제안 이름**:
- **판단 근거**: 개발과 무관

---

## 강화 제안 요약

| # | 유형 | 이름 | 근거 포스트 | 점수 |
|---|------|------|-----------|------|
| 1 | skill | playwright_session | post-001 | 0.85 |
"""


# ------------------------------------------------------------------
# fixture
# ------------------------------------------------------------------

@pytest.fixture
def sample_raw_path() -> Path:
    """sample_raw.md fixture 경로를 반환한다."""
    return _FIXTURE_DIR / "sample_raw.md"


@pytest.fixture
def context_builder(tmp_path) -> ContextBuilder:
    """빈 프로젝트용 ContextBuilder."""
    return ContextBuilder(str(tmp_path))


# ------------------------------------------------------------------
# 정상 분석 테스트
# ------------------------------------------------------------------

def test_analyze_creates_output_file(
    sample_raw_path, context_builder, tmp_path, monkeypatch,
):
    """분석 결과가 analysis md 파일로 저장되어야 한다."""
    monkeypatch.setattr(
        "src.processor.analyzer._ANALYSIS_DIR", tmp_path,
    )
    adapter = MockAIAdapter(response=_VALID_ANALYSIS)
    analyzer = Analyzer(adapter, context_builder)

    result_path = analyzer.analyze(sample_raw_path)

    assert result_path.exists()
    assert result_path.suffix == ".md"


def test_analyze_output_contains_post_sections(
    sample_raw_path, context_builder, tmp_path, monkeypatch,
):
    """분석 결과에 포스트별 섹션(## post-NNN)이 포함되어야 한다."""
    monkeypatch.setattr(
        "src.processor.analyzer._ANALYSIS_DIR", tmp_path,
    )
    adapter = MockAIAdapter(response=_VALID_ANALYSIS)
    analyzer = Analyzer(adapter, context_builder)

    result_path = analyzer.analyze(sample_raw_path)
    content = result_path.read_text(encoding="utf-8")

    assert "## post-001" in content
    assert "## post-002" in content


def test_analyze_output_contains_summary_table(
    sample_raw_path, context_builder, tmp_path, monkeypatch,
):
    """분석 결과에 'Enhancement Proposal Summary' 또는 '강화 제안 요약'이 포함되어야 한다."""
    monkeypatch.setattr(
        "src.processor.analyzer._ANALYSIS_DIR", tmp_path,
    )
    adapter = MockAIAdapter(response=_VALID_ANALYSIS)
    analyzer = Analyzer(adapter, context_builder)

    result_path = analyzer.analyze(sample_raw_path)
    content = result_path.read_text(encoding="utf-8")

    assert "Enhancement Proposal Summary" in content or "강화 제안 요약" in content


def test_analyze_calls_ai_once(
    sample_raw_path, context_builder, tmp_path, monkeypatch,
):
    """AI 어댑터는 정확히 1회 호출되어야 한다."""
    monkeypatch.setattr(
        "src.processor.analyzer._ANALYSIS_DIR", tmp_path,
    )
    adapter = MockAIAdapter(response=_VALID_ANALYSIS)
    analyzer = Analyzer(adapter, context_builder)

    analyzer.analyze(sample_raw_path)

    assert adapter.call_count == 1


# ------------------------------------------------------------------
# 검증(validation) 테스트
# ------------------------------------------------------------------

def test_validate_analysis_valid():
    """필수 섹션이 있는 분석 결과는 검증 통과해야 한다."""
    adapter = MockAIAdapter()
    analyzer = Analyzer(adapter, ContextBuilder("/tmp"))
    assert analyzer._validate_analysis(_VALID_ANALYSIS) is True


def test_validate_analysis_missing_post_section():
    """## post-NNN 섹션이 없으면 검증 실패해야 한다."""
    adapter = MockAIAdapter()
    analyzer = Analyzer(adapter, ContextBuilder("/tmp"))
    invalid = "# 분석 결과\n\n## 강화 제안 요약\n| # | 유형 |"
    assert analyzer._validate_analysis(invalid) is False


def test_validate_analysis_missing_summary():
    """'강화 제안 요약'이 없으면 검증 실패해야 한다."""
    adapter = MockAIAdapter()
    analyzer = Analyzer(adapter, ContextBuilder("/tmp"))
    invalid = "# 분석 결과\n\n## post-001\n- **분류**: 기타"
    assert analyzer._validate_analysis(invalid) is False


# ------------------------------------------------------------------
# fallback 동작 테스트
# ------------------------------------------------------------------

def test_fallback_on_ai_failure(
    sample_raw_path, context_builder, tmp_path, monkeypatch,
):
    """AI 호출 실패 시 fallback 분석 결과가 생성되어야 한다."""
    monkeypatch.setattr(
        "src.processor.analyzer._ANALYSIS_DIR", tmp_path,
    )
    adapter = MockAIAdapter(should_fail=True)
    analyzer = Analyzer(adapter, context_builder)

    result_path = analyzer.analyze(sample_raw_path)
    content = result_path.read_text(encoding="utf-8")

    assert "폴백" in content or "fallback" in content.lower()


def test_fallback_on_invalid_response(
    sample_raw_path, context_builder, tmp_path, monkeypatch,
):
    """AI 응답이 검증 실패 시 fallback 분석 결과가 생성되어야 한다."""
    monkeypatch.setattr(
        "src.processor.analyzer._ANALYSIS_DIR", tmp_path,
    )
    adapter = MockAIAdapter(response="잘못된 응답 형식입니다.")
    analyzer = Analyzer(adapter, context_builder)

    result_path = analyzer.analyze(sample_raw_path)
    content = result_path.read_text(encoding="utf-8")

    assert "other" in content


def test_fallback_contains_empty_summary_table(
    sample_raw_path, context_builder, tmp_path, monkeypatch,
):
    """fallback 결과에도 강화 제안 요약 테이블(빈 테이블)이 있어야 한다."""
    monkeypatch.setattr(
        "src.processor.analyzer._ANALYSIS_DIR", tmp_path,
    )
    adapter = MockAIAdapter(should_fail=True)
    analyzer = Analyzer(adapter, context_builder)

    result_path = analyzer.analyze(sample_raw_path)
    content = result_path.read_text(encoding="utf-8")

    assert "Enhancement Proposal Summary" in content


# ------------------------------------------------------------------
# 중복 파일명 처리 테스트
# ------------------------------------------------------------------

def test_resolve_output_path_no_conflict(tmp_path, monkeypatch):
    """기존 파일이 없으면 그대로 경로를 반환해야 한다."""
    analysis_dir = tmp_path / "analysis_output"
    analysis_dir.mkdir()
    monkeypatch.setattr(
        "src.processor.analyzer._ANALYSIS_DIR", analysis_dir,
    )
    adapter = MockAIAdapter()
    analyzer = Analyzer(adapter, ContextBuilder("/tmp"))

    raw_path = tmp_path / "20260312_070000.md"
    raw_path.touch()
    result = analyzer._resolve_output_path(raw_path)

    assert result.name == "20260312_070000.md"


def test_resolve_output_path_with_conflict(tmp_path, monkeypatch):
    """기존 파일이 있으면 접미사(suffix)를 추가해야 한다."""
    monkeypatch.setattr(
        "src.processor.analyzer._ANALYSIS_DIR", tmp_path,
    )
    # 기존 파일 생성
    (tmp_path / "20260312_070000.md").touch()

    adapter = MockAIAdapter()
    analyzer = Analyzer(adapter, ContextBuilder("/tmp"))

    raw_path = tmp_path / "20260312_070000.md"
    result = analyzer._resolve_output_path(raw_path)

    assert result.name == "20260312_070000_1.md"
