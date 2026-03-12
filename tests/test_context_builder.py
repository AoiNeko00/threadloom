"""ContextBuilder 테스트 — 기존 .claude/ 스캔 결과 검증.

sample_claude_project fixture를 사용하여
build_summary(), collect_existing_files()의 동작을 검증한다.
"""

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.processor.context_builder import ContextBuilder

# 테스트 fixture 경로
_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sample_claude_project"


# ------------------------------------------------------------------
# fixture
# ------------------------------------------------------------------

@pytest.fixture
def builder() -> ContextBuilder:
    """sample_claude_project를 대상으로 ContextBuilder를 생성한다."""
    return ContextBuilder(str(_FIXTURE_DIR))


@pytest.fixture
def empty_builder(tmp_path) -> ContextBuilder:
    """빈 프로젝트(.claude/ 없음)를 대상으로 ContextBuilder를 생성한다."""
    return ContextBuilder(str(tmp_path))


@pytest.fixture
def empty_claude_builder(tmp_path) -> ContextBuilder:
    """빈 .claude/ 디렉토리만 있는 프로젝트용 ContextBuilder."""
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    return ContextBuilder(str(tmp_path))


# ------------------------------------------------------------------
# build_summary 테스트
# ------------------------------------------------------------------

def test_summary_contains_skills_section(builder):
    """요약에 '기존 Skills' 섹션이 포함되어야 한다."""
    summary = builder.build_summary()
    assert "## Existing Skills" in summary


def test_summary_contains_agents_section(builder):
    """요약에 'Existing Agents' 섹션이 포함되어야 한다."""
    summary = builder.build_summary()
    assert "## Existing Agents" in summary


def test_summary_contains_rules_section(builder):
    """요약에 'Existing Rules' 섹션이 포함되어야 한다."""
    summary = builder.build_summary()
    assert "## Existing Rules" in summary


def test_summary_lists_existing_skill(builder):
    """요약에 기존 skill의 이름과 설명이 포함되어야 한다."""
    summary = builder.build_summary()
    assert "existing_skill" in summary
    assert "커밋 메시지" in summary or "Conventional Commit" in summary


def test_summary_lists_existing_agent(builder):
    """요약에 기존 agent의 이름과 설명이 포함되어야 한다."""
    summary = builder.build_summary()
    assert "existing_agent" in summary
    assert "코드 리뷰" in summary


def test_summary_lists_rules_from_claude_md(builder):
    """요약에 CLAUDE.md에서 추출한 규칙이 포함되어야 한다."""
    summary = builder.build_summary()
    assert "함수는 20줄 이하" in summary or "20줄" in summary


def test_summary_skill_count(builder):
    """Skills 카운트가 정확해야 한다."""
    summary = builder.build_summary()
    assert "Skills (1)" in summary


def test_summary_agent_count(builder):
    """Agents 카운트가 정확해야 한다."""
    summary = builder.build_summary()
    assert "Agents (1)" in summary


# ------------------------------------------------------------------
# 빈 프로젝트 처리 테스트
# ------------------------------------------------------------------

def test_empty_project_no_error(empty_builder):
    """.claude/ 없는 프로젝트에서도 에러 없이 요약을 생성해야 한다."""
    summary = empty_builder.build_summary()
    assert "Existing Skills" in summary


def test_empty_project_shows_none(empty_builder):
    """.claude/ 없으면 각 섹션에 '(none)'이 표시되어야 한다."""
    summary = empty_builder.build_summary()
    assert "(none)" in summary


def test_empty_claude_dir_shows_zero(empty_claude_builder):
    """빈 .claude/ 디렉토리는 (0)으로 표시되어야 한다."""
    summary = empty_claude_builder.build_summary()
    assert "(0)" in summary


# ------------------------------------------------------------------
# collect_existing_files 테스트
# ------------------------------------------------------------------

def test_collect_includes_skill_files(builder):
    """기존 skill 파일이 dict에 포함되어야 한다."""
    files = builder.collect_existing_files()
    skill_keys = [k for k in files if "skills" in k]
    assert len(skill_keys) >= 1


def test_collect_includes_agent_files(builder):
    """기존 agent 파일이 dict에 포함되어야 한다."""
    files = builder.collect_existing_files()
    agent_keys = [k for k in files if "agents" in k]
    assert len(agent_keys) >= 1


def test_collect_includes_claude_md(builder):
    """CLAUDE.md가 dict에 포함되어야 한다."""
    files = builder.collect_existing_files()
    assert "CLAUDE.md" in files


def test_collect_file_content_is_string(builder):
    """수집된 파일 내용은 문자열이어야 한다."""
    files = builder.collect_existing_files()
    for value in files.values():
        assert isinstance(value, str)


def test_collect_empty_project_returns_empty(empty_builder):
    """빈 프로젝트에서는 빈 dict를 반환해야 한다."""
    files = empty_builder.collect_existing_files()
    assert files == {}


# ------------------------------------------------------------------
# frontmatter description 추출 테스트
# ------------------------------------------------------------------

def test_extract_frontmatter_description(builder):
    """frontmatter에서 description 필드를 정확히 추출해야 한다."""
    skill_path = _FIXTURE_DIR / ".claude" / "skills" / "existing_skill.md"
    desc = builder._extract_frontmatter_field(skill_path, "description")
    assert desc is not None
    assert "커밋" in desc or "Conventional Commit" in desc


def test_extract_frontmatter_missing_field(builder):
    """존재하지 않는 필드는 None을 반환해야 한다."""
    skill_path = _FIXTURE_DIR / ".claude" / "skills" / "existing_skill.md"
    result = builder._extract_frontmatter_field(skill_path, "nonexistent")
    assert result is None
