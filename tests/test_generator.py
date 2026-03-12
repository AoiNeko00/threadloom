"""Phase 3 강화 생성(enhancement generation) 테스트.

---THREADLOOM_FILE_START/END--- 구분자 파싱,
pending md 저장, fallback 동작을 검증한다.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.ai_adapter.base import BaseAIAdapter
from src.enhancer.generator import EnhancementGenerator

_FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ------------------------------------------------------------------
# mock 어댑터(adapter)
# ------------------------------------------------------------------

class MockAIAdapter(BaseAIAdapter):
    """테스트용 mock AI 어댑터."""

    _CLI_CMD = "mock"

    def __init__(
        self,
        response: str = "",
        should_fail: bool = False,
        raw_response: str = "",
    ):
        self._response = response
        self._should_fail = should_fail
        # call_raw()가 반환할 응답 (자기 수정용)
        self._raw_response = raw_response
        self.call_count = 0
        self.raw_call_count = 0

    def analyze(self, raw_md_path: Path, context_summary: str) -> str:
        return ""

    def generate_enhancements(
        self, analysis_md_path: Path, existing_files: dict[str, str]
    ) -> str:
        self.call_count += 1
        if self._should_fail:
            raise RuntimeError("AI 호출 실패 (mock)")
        return self._response

    def call_raw(self, prompt: str) -> str:
        """자기 수정(self-correction) 프롬프트 처리용 mock."""
        self.raw_call_count += 1
        return self._raw_response

    def is_available(self) -> bool:
        return True


# ------------------------------------------------------------------
# AI 응답 mock
# ------------------------------------------------------------------

_VALID_RESPONSE = """
---THREADLOOM_FILE_START: create_skill_playwright_session---
---
action_type: create_skill
name: playwright_session
target: .claude/skills/playwright_session.md
source_posts: [post-001, post-002]
duplicate_check: create_new
---

# playwright_session

Playwright 세션 관리 패턴.

## 지시사항
1. storageState 사용
2. 세션 만료 감지

## 근거
- post-001, post-002에서 감지
---THREADLOOM_FILE_END---

---THREADLOOM_FILE_START: add_rule_error_handling---
---
action_type: add_rule
name: error_handling
target: CLAUDE.md (## threadloom-rules 섹션)
source_posts: [post-006]
duplicate_check: create_new
---

### 에러 핸들링 컨벤션
<!-- threadloom: 2026-03-12 | source: post-006 -->
- bare except 금지
- 외부 API 호출 시 retry 1회
---THREADLOOM_FILE_END---
"""

_NO_DELIMITER_RESPONSE = """
여기에는 구분자가 없습니다.
그냥 텍스트만 있어요.
skill을 만들어야 하지만 형식이 맞지 않습니다.
"""

# 코드블록(code block) 안에 구분자가 있는 응답
_CODEBLOCK_WRAPPED_RESPONSE = """
아래는 생성된 파일입니다:

```markdown
---THREADLOOM_FILE_START: create_skill_test_skill---
---
action_type: create_skill
name: test_skill
target: .claude/skills/test_skill.md
---

# test_skill

테스트 스킬입니다.
---THREADLOOM_FILE_END---
```
"""

# 구분자 없이 frontmatter만 있는 응답
_FRONTMATTER_ONLY_RESPONSE = """
---
action_type: create_skill
name: frontmatter_skill
target: .claude/skills/frontmatter_skill.md
---

# frontmatter_skill

Frontmatter 기반 파싱 테스트.

---
action_type: add_rule
name: frontmatter_rule
target: CLAUDE.md
---

### 규칙 내용

- 규칙 1
- 규칙 2
"""


# ------------------------------------------------------------------
# mock Config
# ------------------------------------------------------------------

def _make_mock_config():
    """테스트용 Config mock 객체를 생성한다."""
    config = MagicMock()
    config.target_project_path = "/tmp/test_project"
    config.auto_apply = False
    config.enhance_config = {"skills": True, "agents": True, "rules": True}
    return config


# ------------------------------------------------------------------
# mock ContextBuilder
# ------------------------------------------------------------------

def _make_mock_context_builder():
    """테스트용 ContextBuilder mock 객체를 생성한다."""
    cb = MagicMock()
    cb.build_summary.return_value = "## 기존 Skills (0개)\n(없음)"
    cb.collect_existing_files.return_value = {}
    return cb


# ------------------------------------------------------------------
# fixture
# ------------------------------------------------------------------

@pytest.fixture
def analysis_path() -> Path:
    """sample_analysis.md fixture 경로를 반환한다."""
    return _FIXTURE_DIR / "sample_analysis.md"


# ------------------------------------------------------------------
# _parse_response 테스트
# ------------------------------------------------------------------

def test_parse_response_extracts_two_files():
    """유효한 응답에서 2개 파일을 파싱해야 한다."""
    gen = EnhancementGenerator(
        MockAIAdapter(), _make_mock_context_builder(), _make_mock_config(),
    )
    result = gen._parse_response(_VALID_RESPONSE)
    assert len(result) == 2


def test_parse_response_extracts_action_type():
    """파싱된 파일의 action_type이 정확해야 한다."""
    gen = EnhancementGenerator(
        MockAIAdapter(), _make_mock_context_builder(), _make_mock_config(),
    )
    result = gen._parse_response(_VALID_RESPONSE)
    action_types = [r["metadata"].get("action_type") for r in result]
    assert "create_skill" in action_types
    assert "add_rule" in action_types


def test_parse_response_extracts_name():
    """파싱된 파일의 name이 정확해야 한다."""
    gen = EnhancementGenerator(
        MockAIAdapter(), _make_mock_context_builder(), _make_mock_config(),
    )
    result = gen._parse_response(_VALID_RESPONSE)
    names = [r["metadata"].get("name") for r in result]
    assert "playwright_session" in names
    assert "error_handling" in names


def test_parse_response_empty_on_no_delimiters():
    """구분자가 없는 응답은 빈 리스트를 반환해야 한다."""
    gen = EnhancementGenerator(
        MockAIAdapter(), _make_mock_context_builder(), _make_mock_config(),
    )
    result = gen._parse_response(_NO_DELIMITER_RESPONSE)
    assert result == []


def test_parse_response_fuzzy_matching():
    """구분자의 공백/대소문자 차이를 허용해야 한다 (fuzzy matching)."""
    gen = EnhancementGenerator(
        MockAIAdapter(), _make_mock_context_builder(), _make_mock_config(),
    )
    fuzzy_response = """
--- THREADLOOM FILE START : create_skill_test ---
---
action_type: create_skill
name: test
---
# test skill
--- THREADLOOM FILE END ---
"""
    result = gen._parse_response(fuzzy_response)
    assert len(result) == 1


def test_parse_response_case_insensitive():
    """구분자가 대소문자 무관하게 매칭되어야 한다."""
    gen = EnhancementGenerator(
        MockAIAdapter(), _make_mock_context_builder(), _make_mock_config(),
    )
    upper_response = """
---threadloom_file_start: create_skill_lower---
---
action_type: create_skill
name: lower
---
content
---threadloom_file_end---
"""
    result = gen._parse_response(upper_response)
    assert len(result) == 1


# ------------------------------------------------------------------
# generate 테스트
# ------------------------------------------------------------------

def test_generate_creates_pending_files(analysis_path, tmp_path, monkeypatch):
    """Phase 3 실행 시 pending md 파일이 생성되어야 한다."""
    monkeypatch.setattr(
        "src.enhancer.generator._PENDING_DIR", tmp_path,
    )
    adapter = MockAIAdapter(response=_VALID_RESPONSE)
    gen = EnhancementGenerator(
        adapter, _make_mock_context_builder(), _make_mock_config(),
    )

    paths = gen.generate(analysis_path)

    assert len(paths) == 2
    for p in paths:
        assert p.exists()
        assert p.suffix == ".md"


def test_generate_pending_filenames(analysis_path, tmp_path, monkeypatch):
    """pending 파일명이 {action_type}_{name}.md 형식이어야 한다."""
    monkeypatch.setattr(
        "src.enhancer.generator._PENDING_DIR", tmp_path,
    )
    adapter = MockAIAdapter(response=_VALID_RESPONSE)
    gen = EnhancementGenerator(
        adapter, _make_mock_context_builder(), _make_mock_config(),
    )

    paths = gen.generate(analysis_path)
    names = {p.name for p in paths}

    assert "create_skill_playwright_session.md" in names
    assert "add_rule_error_handling.md" in names


def test_generate_returns_empty_when_no_proposals(tmp_path, monkeypatch):
    """강화 제안이 없는 경우 빈 리스트를 반환해야 한다."""
    monkeypatch.setattr(
        "src.enhancer.generator._PENDING_DIR", tmp_path,
    )
    # 강화 제안 요약이 없는 analysis md 생성
    no_proposal = tmp_path / "empty_analysis.md"
    no_proposal.write_text(
        "# 분석 결과\n\n## post-001\n- **분류**: 기타\n", encoding="utf-8",
    )

    adapter = MockAIAdapter(response=_VALID_RESPONSE)
    gen = EnhancementGenerator(
        adapter, _make_mock_context_builder(), _make_mock_config(),
    )

    paths = gen.generate(no_proposal)
    assert paths == []


def test_generate_ai_called_once(analysis_path, tmp_path, monkeypatch):
    """AI 어댑터는 Phase 3에서 1회만 호출되어야 한다."""
    monkeypatch.setattr(
        "src.enhancer.generator._PENDING_DIR", tmp_path,
    )
    adapter = MockAIAdapter(response=_VALID_RESPONSE)
    gen = EnhancementGenerator(
        adapter, _make_mock_context_builder(), _make_mock_config(),
    )

    gen.generate(analysis_path)
    assert adapter.call_count == 1


# ------------------------------------------------------------------
# fallback 테스트
# ------------------------------------------------------------------

def test_fallback_on_parse_failure(analysis_path, tmp_path, monkeypatch):
    """구분자 파싱 실패 시 raw_fallback 파일이 생성되어야 한다."""
    monkeypatch.setattr(
        "src.enhancer.generator._PENDING_DIR", tmp_path,
    )
    adapter = MockAIAdapter(response=_NO_DELIMITER_RESPONSE)
    gen = EnhancementGenerator(
        adapter, _make_mock_context_builder(), _make_mock_config(),
    )

    paths = gen.generate(analysis_path)

    assert len(paths) == 1
    assert "raw_fallback" in paths[0].name


def test_fallback_preserves_original_response(
    analysis_path, tmp_path, monkeypatch,
):
    """fallback 파일에 AI 원본 응답이 보존되어야 한다."""
    monkeypatch.setattr(
        "src.enhancer.generator._PENDING_DIR", tmp_path,
    )
    adapter = MockAIAdapter(response=_NO_DELIMITER_RESPONSE)
    gen = EnhancementGenerator(
        adapter, _make_mock_context_builder(), _make_mock_config(),
    )

    paths = gen.generate(analysis_path)
    content = paths[0].read_text(encoding="utf-8")

    assert "구분자가 없습니다" in content


def test_fallback_on_ai_failure(analysis_path, tmp_path, monkeypatch):
    """AI 호출 자체가 실패하면 빈 리스트를 반환해야 한다."""
    monkeypatch.setattr(
        "src.enhancer.generator._PENDING_DIR", tmp_path,
    )
    adapter = MockAIAdapter(should_fail=True)
    gen = EnhancementGenerator(
        adapter, _make_mock_context_builder(), _make_mock_config(),
    )

    paths = gen.generate(analysis_path)
    assert paths == []


# ------------------------------------------------------------------
# 파일명 충돌 해결 테스트
# ------------------------------------------------------------------

def test_resolve_conflict_no_existing(tmp_path):
    """기존 파일 없으면 원래 경로를 반환해야 한다."""
    gen = EnhancementGenerator(
        MockAIAdapter(), _make_mock_context_builder(), _make_mock_config(),
    )
    path = tmp_path / "test.md"
    result = gen._resolve_conflict(path)
    assert result == path


def test_resolve_conflict_with_existing(tmp_path):
    """기존 파일이 있으면 _1 접미사를 추가해야 한다."""
    gen = EnhancementGenerator(
        MockAIAdapter(), _make_mock_context_builder(), _make_mock_config(),
    )
    path = tmp_path / "test.md"
    path.touch()
    result = gen._resolve_conflict(path)
    assert result.name == "test_1.md"


# ------------------------------------------------------------------
# 대체 파싱(alternative parsing) 테스트
# ------------------------------------------------------------------

def test_parse_response_codeblock_wrapped():
    """코드블록으로 감싸진 구분자를 파싱해야 한다."""
    gen = EnhancementGenerator(
        MockAIAdapter(), _make_mock_context_builder(), _make_mock_config(),
    )
    result = gen._parse_response(_CODEBLOCK_WRAPPED_RESPONSE)
    assert len(result) == 1
    assert result[0]["metadata"]["name"] == "test_skill"


def test_parse_response_frontmatter_fallback():
    """구분자 없이 frontmatter만 있는 응답도 파싱해야 한다."""
    gen = EnhancementGenerator(
        MockAIAdapter(), _make_mock_context_builder(), _make_mock_config(),
    )
    result = gen._parse_response(_FRONTMATTER_ONLY_RESPONSE)
    assert len(result) == 2
    action_types = {r["metadata"]["action_type"] for r in result}
    assert "create_skill" in action_types
    assert "add_rule" in action_types


def test_parse_response_frontmatter_extracts_name():
    """frontmatter 대체 파싱에서 name이 정확히 추출되어야 한다."""
    gen = EnhancementGenerator(
        MockAIAdapter(), _make_mock_context_builder(), _make_mock_config(),
    )
    result = gen._parse_response(_FRONTMATTER_ONLY_RESPONSE)
    names = {r["metadata"]["name"] for r in result}
    assert "frontmatter_skill" in names
    assert "frontmatter_rule" in names


def test_generate_codeblock_creates_pending(
    analysis_path, tmp_path, monkeypatch,
):
    """코드블록 감싸진 응답도 pending 파일을 생성해야 한다."""
    monkeypatch.setattr(
        "src.enhancer.generator._PENDING_DIR", tmp_path,
    )
    adapter = MockAIAdapter(response=_CODEBLOCK_WRAPPED_RESPONSE)
    gen = EnhancementGenerator(
        adapter, _make_mock_context_builder(), _make_mock_config(),
    )
    paths = gen.generate(analysis_path)
    assert len(paths) == 1
    assert paths[0].exists()


def test_generate_frontmatter_creates_pending(
    analysis_path, tmp_path, monkeypatch,
):
    """frontmatter 기반 응답도 pending 파일을 생성해야 한다."""
    monkeypatch.setattr(
        "src.enhancer.generator._PENDING_DIR", tmp_path,
    )
    adapter = MockAIAdapter(response=_FRONTMATTER_ONLY_RESPONSE)
    gen = EnhancementGenerator(
        adapter, _make_mock_context_builder(), _make_mock_config(),
    )
    paths = gen.generate(analysis_path)
    assert len(paths) == 2


# ------------------------------------------------------------------
# 자기 수정(self-correction) 테스트
# ------------------------------------------------------------------

def test_self_correction_on_parse_failure(
    analysis_path, tmp_path, monkeypatch,
):
    """첫 응답 파싱 실패 -> 자기 수정 재시도 -> 성공해야 한다."""
    monkeypatch.setattr(
        "src.enhancer.generator._PENDING_DIR", tmp_path,
    )
    # 첫 호출: 파싱 불가 응답, call_raw: 유효한 응답
    adapter = MockAIAdapter(
        response=_NO_DELIMITER_RESPONSE,
        raw_response=_VALID_RESPONSE,
    )
    gen = EnhancementGenerator(
        adapter, _make_mock_context_builder(), _make_mock_config(),
    )

    paths = gen.generate(analysis_path)

    # 자기 수정으로 정상 파싱되어 2건 생성
    assert len(paths) == 2
    assert adapter.raw_call_count == 1
    # fallback 파일이 아닌 정상 파일이어야 함
    for p in paths:
        assert "raw_fallback" not in p.name


def test_self_correction_failure_falls_back(
    analysis_path, tmp_path, monkeypatch,
):
    """첫 응답도 자기 수정도 실패하면 fallback 파일이 생성되어야 한다."""
    monkeypatch.setattr(
        "src.enhancer.generator._PENDING_DIR", tmp_path,
    )
    # 첫 호출, 재시도 모두 파싱 불가
    adapter = MockAIAdapter(
        response=_NO_DELIMITER_RESPONSE,
        raw_response=_NO_DELIMITER_RESPONSE,
    )
    gen = EnhancementGenerator(
        adapter, _make_mock_context_builder(), _make_mock_config(),
    )

    paths = gen.generate(analysis_path)

    assert len(paths) == 1
    assert "raw_fallback" in paths[0].name
    assert adapter.raw_call_count == 1
