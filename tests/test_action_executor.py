"""action_executor 모듈 단위 테스트.

action_type별 파일 생성/수정/병합/규칙 추가를 검증한다.
"""

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.enhancer.action_executor import (
    _insert_rule,
    _preserve_existing,
    _resolve_subdir,
    apply_one,
    extract_target_project,
    resolve_target_path,
    resolve_target_root,
)
from tests.conftest import make_pending_action as _make_action


# ------------------------------------------------------------------
# resolve_subdir
# ------------------------------------------------------------------

def test_resolve_subdir_skill():
    """skill 관련 action_type은 skills 디렉토리를 반환한다."""
    assert _resolve_subdir("create_skill") == "skills"
    assert _resolve_subdir("refine_skill") == "skills"
    assert _resolve_subdir("merge_skill") == "skills"


def test_resolve_subdir_agent():
    """agent 관련 action_type은 agents 디렉토리를 반환한다."""
    assert _resolve_subdir("create_agent") == "agents"
    assert _resolve_subdir("refine_agent") == "agents"


# ------------------------------------------------------------------
# resolve_target_root
# ------------------------------------------------------------------

def test_resolve_target_root_default(tmp_path):
    """project_map에 없으면 default_root를 반환한다."""
    action = _make_action(tmp_path)
    result = resolve_target_root(action, {}, tmp_path)
    assert result == tmp_path


def test_resolve_target_root_from_map(tmp_path):
    """action에 target_project가 있으면 project_map에서 경로를 반환한다."""
    action = _make_action(tmp_path)
    # frontmatter에 target_project 추가
    text = action.file_path.read_text()
    text = text.replace("---\n", "---\ntarget_project: my_project\n", 1)
    action.file_path.write_text(text, encoding="utf-8")

    project_path = tmp_path / "my_project"
    project_path.mkdir()
    project_map = {"my_project": str(project_path)}

    result = resolve_target_root(action, project_map, tmp_path)
    assert result == project_path


# ------------------------------------------------------------------
# resolve_target_path
# ------------------------------------------------------------------

def test_resolve_target_path_skill(tmp_path):
    """create_skill은 .claude/skills/{name}.md 경로를 반환한다."""
    action = _make_action(tmp_path, action_type="create_skill", name="foo")
    result = resolve_target_path(action, {}, tmp_path)
    assert result == tmp_path / ".claude" / "skills" / "foo.md"


def test_resolve_target_path_agent(tmp_path):
    """create_agent는 .claude/agents/{name}.md 경로를 반환한다."""
    action = _make_action(tmp_path, action_type="create_agent", name="bar")
    result = resolve_target_path(action, {}, tmp_path)
    assert result == tmp_path / ".claude" / "agents" / "bar.md"


def test_resolve_target_path_rule(tmp_path):
    """add_rule은 CLAUDE.md 경로를 반환한다."""
    action = _make_action(tmp_path, action_type="add_rule", name="rule1")
    result = resolve_target_path(action, {}, tmp_path)
    assert result == tmp_path / "CLAUDE.md"


def test_resolve_target_path_unknown(tmp_path):
    """알 수 없는 action_type은 None을 반환한다."""
    action = _make_action(tmp_path, action_type="unknown_type")
    result = resolve_target_path(action, {}, tmp_path)
    assert result is None


# ------------------------------------------------------------------
# apply_one — create_skill
# ------------------------------------------------------------------

def test_apply_create_skill(target_project, tmp_path):
    """create_skill 시 .claude/skills/{name}.md가 생성되어야 한다."""
    action = _make_action(tmp_path, "create_skill", "my_skill", "# My Skill")
    apply_one(action, target_project, {}, target_project)
    created = target_project / ".claude" / "skills" / "my_skill.md"
    assert created.exists()
    assert "# My Skill" in created.read_text()


def test_apply_create_agent(target_project, tmp_path):
    """create_agent 시 .claude/agents/{name}.md가 생성되어야 한다."""
    action = _make_action(tmp_path, "create_agent", "my_agent", "# My Agent")
    apply_one(action, target_project, {}, target_project)
    created = target_project / ".claude" / "agents" / "my_agent.md"
    assert created.exists()


# ------------------------------------------------------------------
# apply_one — refine_skill (기존 파일 진화)
# ------------------------------------------------------------------

def test_apply_refine_preserves_existing(target_project, tmp_path):
    """refine_skill 시 기존 파일이 .prev.md로 보존되어야 한다."""
    existing = target_project / ".claude" / "skills" / "evolve.md"
    existing.write_text("# Old Content", encoding="utf-8")

    action = _make_action(tmp_path, "refine_skill", "evolve", "# New Content")
    apply_one(action, target_project, {}, target_project)

    assert existing.read_text() == "# New Content"
    prev = target_project / ".claude" / "skills" / "evolve.prev.md"
    assert prev.exists()
    assert "# Old Content" in prev.read_text()


# ------------------------------------------------------------------
# apply_one — merge_skill
# ------------------------------------------------------------------

def test_apply_merge_appends_content(target_project, tmp_path):
    """merge_skill 시 기존 파일에 내용이 추가되어야 한다."""
    existing = target_project / ".claude" / "skills" / "merged.md"
    existing.write_text("# Existing", encoding="utf-8")

    action = _make_action(tmp_path, "merge_skill", "merged", "## Added Section")
    apply_one(action, target_project, {}, target_project)

    content = existing.read_text()
    assert "# Existing" in content
    assert "## Added Section" in content


def test_apply_merge_creates_if_not_exist(target_project, tmp_path):
    """merge_skill 대상 파일이 없으면 새로 생성해야 한다."""
    action = _make_action(tmp_path, "merge_skill", "new_merge", "# Brand New")
    apply_one(action, target_project, {}, target_project)

    created = target_project / ".claude" / "skills" / "new_merge.md"
    assert created.exists()


# ------------------------------------------------------------------
# apply_one — add_rule (CLAUDE.md)
# ------------------------------------------------------------------

def test_apply_rule_creates_claude_md(target_project, tmp_path):
    """CLAUDE.md가 없으면 규칙 섹션과 함께 생성해야 한다."""
    action = _make_action(tmp_path, "add_rule", "rule1", "### No bare except")
    apply_one(action, target_project, {}, target_project)

    claude_md = target_project / "CLAUDE.md"
    assert claude_md.exists()
    text = claude_md.read_text()
    assert "## threadloom-rules" in text
    assert "### No bare except" in text
    assert "<!-- threadloom-rules-end -->" in text


def test_apply_rule_appends_to_existing(target_project, tmp_path):
    """기존 CLAUDE.md에 threadloom-rules 섹션이 추가되어야 한다."""
    claude_md = target_project / "CLAUDE.md"
    claude_md.write_text("# Project\n\nExisting content.", encoding="utf-8")

    action = _make_action(tmp_path, "add_rule", "rule1", "### Max 20 lines")
    apply_one(action, target_project, {}, target_project)

    text = claude_md.read_text()
    assert "Existing content." in text
    assert "## threadloom-rules" in text
    assert "### Max 20 lines" in text


def test_apply_rule_inserts_into_existing_section(target_project, tmp_path):
    """기존 threadloom-rules 섹션에 규칙을 추가한다."""
    claude_md = target_project / "CLAUDE.md"
    claude_md.write_text(
        "# Project\n\n## threadloom-rules\n\n### Old Rule\n\n"
        "<!-- threadloom-rules-end -->\n",
        encoding="utf-8",
    )
    action = _make_action(tmp_path, "add_rule", "rule2", "### New Rule")
    apply_one(action, target_project, {}, target_project)

    text = claude_md.read_text()
    assert "### Old Rule" in text
    assert "### New Rule" in text


# ------------------------------------------------------------------
# apply_one — unknown action_type
# ------------------------------------------------------------------

def test_apply_unknown_action_no_error(target_project, tmp_path):
    """알 수 없는 action_type은 경고만 출력하고 에러 없이 통과한다."""
    action = _make_action(tmp_path, "invalid_type", "test")
    apply_one(action, target_project, {}, target_project)
    # 에러 없이 통과 확인


# ------------------------------------------------------------------
# _preserve_existing
# ------------------------------------------------------------------

def test_preserve_existing_no_file(tmp_path):
    """파일이 없으면 None을 반환한다."""
    result = _preserve_existing(tmp_path / "nonexist.md")
    assert result is None


def test_preserve_existing_creates_prev(tmp_path):
    """기존 파일을 .prev.md로 복사한다."""
    original = tmp_path / "file.md"
    original.write_text("original", encoding="utf-8")
    result = _preserve_existing(original)
    assert result is not None
    assert result.exists()
    assert "prev" in result.name


def test_preserve_existing_timestamp_on_conflict(tmp_path):
    """.prev.md가 이미 있으면 타임스탬프로 구분한다."""
    original = tmp_path / "file.md"
    original.write_text("v2", encoding="utf-8")
    prev = tmp_path / "file.prev.md"
    prev.write_text("v1", encoding="utf-8")

    result = _preserve_existing(original)
    assert result != prev
    assert "prev_" in result.name


# ------------------------------------------------------------------
# _insert_rule
# ------------------------------------------------------------------

def test_insert_rule_no_section():
    """threadloom-rules 섹션이 없으면 끝에 추가한다."""
    text = "# Project\n\nSome content."
    result = _insert_rule(text, "### New Rule")
    assert "## threadloom-rules" in result
    assert "### New Rule" in result
    assert "Some content." in result


def test_insert_rule_with_end_marker():
    """end marker 앞에 규칙을 삽입한다."""
    text = (
        "# Project\n\n## threadloom-rules\n\n"
        "### Old\n\n<!-- threadloom-rules-end -->\n"
    )
    result = _insert_rule(text, "### Added")
    assert result.index("### Added") < result.index("<!-- threadloom-rules-end -->")
    assert "### Old" in result
