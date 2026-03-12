"""Phase 4 적용(apply) 모듈 테스트.

skill/agent 파일 생성, CLAUDE.md threadloom-rules 섹션 관리,
auto_apply, 백업, enhance_log.json을 검증한다.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.enhancer.applier import Applier
from src.enhancer.models import PendingAction


# ------------------------------------------------------------------
# mock Config 헬퍼
# ------------------------------------------------------------------

def _make_config(
    target_path: str,
    auto_apply: bool = False,
    target_projects: list[dict] | None = None,
) -> MagicMock:
    """테스트용 Config mock을 생성한다."""
    config = MagicMock()
    config.target_project_path = target_path
    config.auto_apply = auto_apply
    if target_projects is None:
        # 하위 호환(backward compatibility): 단일 프로젝트
        config.target_projects = [{
            "name": Path(target_path).name,
            "path": target_path,
            "tags": [],
        }]
    else:
        config.target_projects = target_projects
    return config


# ------------------------------------------------------------------
# fixture
# ------------------------------------------------------------------


# target_project fixture는 conftest.py에서 자동 주입(inject)됨


@pytest.fixture
def pending_dir(tmp_path) -> Path:
    """테스트용 pending 디렉토리."""
    d = tmp_path / "pending"
    d.mkdir()
    return d


@pytest.fixture
def backups_dir(tmp_path) -> Path:
    """테스트용 backups 디렉토리."""
    d = tmp_path / "backups"
    d.mkdir()
    return d


@pytest.fixture
def enhance_log_path(tmp_path) -> Path:
    """테스트용 enhance_log.json 경로."""
    return tmp_path / "enhance_log.json"


@pytest.fixture
def applier(target_project, pending_dir, backups_dir, enhance_log_path, monkeypatch):
    """테스트용 Applier를 생성하고 경로를 monkeypatch 한다."""
    monkeypatch.setattr("src.enhancer.applier._PENDING_DIR", pending_dir)
    monkeypatch.setattr("src.enhancer.backup_manager._BACKUPS_DIR", backups_dir)
    monkeypatch.setattr("src.enhancer.backup_manager._ENHANCE_LOG", enhance_log_path)
    monkeypatch.setattr("src.enhancer.pending_manager._PENDING_DIR", pending_dir)
    monkeypatch.setattr("src.enhancer.pending_manager._REJECTED_DIR", pending_dir.parent / "rejected")

    config = _make_config(str(target_project), auto_apply=True)
    return Applier(config)


@pytest.fixture
def skill_action(pending_dir) -> PendingAction:
    """skill 생성 PendingAction fixture."""
    pending_file = pending_dir / "create_skill_test_skill.md"
    pending_file.write_text("skill content", encoding="utf-8")
    return PendingAction(
        file_path=pending_file,
        action_type="create_skill",
        name="test_skill",
        target=".claude/skills/test_skill.md",
        content="# test_skill\n\n테스트 스킬 내용",
        source_posts=["post-001"],
        duplicate_check="create_new",
    )


@pytest.fixture
def agent_action(pending_dir) -> PendingAction:
    """agent 생성 PendingAction fixture."""
    pending_file = pending_dir / "create_agent_test_agent.md"
    pending_file.write_text("agent content", encoding="utf-8")
    return PendingAction(
        file_path=pending_file,
        action_type="create_agent",
        name="test_agent",
        target=".claude/agents/test_agent.md",
        content="# test_agent\n\n테스트 에이전트",
        source_posts=["post-004"],
        duplicate_check="create_new",
    )


@pytest.fixture
def rule_action(pending_dir) -> PendingAction:
    """rule 추가 PendingAction fixture."""
    pending_file = pending_dir / "add_rule_test_rule.md"
    pending_file.write_text("rule content", encoding="utf-8")
    return PendingAction(
        file_path=pending_file,
        action_type="add_rule",
        name="test_rule",
        target="CLAUDE.md (## threadloom-rules 섹션)",
        content="### 테스트 규칙\n<!-- threadloom: 2026-03-12 -->\n- 테스트 규칙 내용",
        source_posts=["post-006"],
        duplicate_check="create_new",
    )


# ------------------------------------------------------------------
# skill/agent 파일 생성 테스트
# ------------------------------------------------------------------

def test_apply_creates_skill_file(applier, skill_action, target_project):
    """create_skill 액션이 .claude/skills/ 에 파일을 생성해야 한다."""
    applier._apply_one(skill_action)

    skill_path = target_project / ".claude" / "skills" / "test_skill.md"
    assert skill_path.exists()
    content = skill_path.read_text(encoding="utf-8")
    assert "test_skill" in content


def test_apply_creates_agent_file(applier, agent_action, target_project):
    """create_agent 액션이 .claude/agents/ 에 파일을 생성해야 한다."""
    applier._apply_one(agent_action)

    agent_path = target_project / ".claude" / "agents" / "test_agent.md"
    assert agent_path.exists()
    content = agent_path.read_text(encoding="utf-8")
    assert "test_agent" in content


# ------------------------------------------------------------------
# CLAUDE.md threadloom-rules 섹션 테스트
# ------------------------------------------------------------------

def test_apply_rule_creates_section_when_missing(
    applier, rule_action, target_project,
):
    """CLAUDE.md에 threadloom-rules 섹션이 없으면 새로 생성해야 한다."""
    claude_md = target_project / "CLAUDE.md"
    claude_md.write_text("# 프로젝트\n\n기존 내용\n", encoding="utf-8")

    applier._apply_one(rule_action)

    content = claude_md.read_text(encoding="utf-8")
    assert "## threadloom-rules" in content
    assert "테스트 규칙 내용" in content


def test_apply_rule_appends_to_existing_section(
    applier, rule_action, target_project,
):
    """기존 threadloom-rules 섹션에 규칙을 추가해야 한다."""
    claude_md = target_project / "CLAUDE.md"
    claude_md.write_text(
        "# 프로젝트\n\n"
        "## threadloom-rules\n\n"
        "### 기존 규칙\n- 기존 내용\n\n"
        "<!-- threadloom-rules-end -->\n\n"
        "## 기타\n- 다른 내용\n",
        encoding="utf-8",
    )

    applier._apply_one(rule_action)

    content = claude_md.read_text(encoding="utf-8")
    assert "기존 내용" in content  # 기존 규칙 보존
    assert "테스트 규칙 내용" in content  # 새 규칙 추가
    assert "<!-- threadloom-rules-end -->" in content


def test_apply_rule_preserves_user_content(
    applier, rule_action, target_project,
):
    """기존 사용자 규칙(threadloom-rules 외부)은 수정하지 않아야 한다."""
    claude_md = target_project / "CLAUDE.md"
    original = (
        "# 프로젝트\n\n"
        "## 코딩 컨벤션\n"
        "- 함수 20줄 이하\n"
        "- 타입 힌트 필수\n\n"
        "## threadloom-rules\n\n"
        "<!-- threadloom-rules-end -->\n\n"
        "## 기타\n- 다른 내용\n"
    )
    claude_md.write_text(original, encoding="utf-8")

    applier._apply_one(rule_action)

    content = claude_md.read_text(encoding="utf-8")
    assert "함수 20줄 이하" in content
    assert "타입 힌트 필수" in content
    assert "다른 내용" in content


def test_apply_rule_creates_claude_md_when_missing(
    applier, rule_action, target_project,
):
    """CLAUDE.md가 없으면 새로 생성해야 한다."""
    applier._apply_one(rule_action)

    claude_md = target_project / "CLAUDE.md"
    assert claude_md.exists()
    content = claude_md.read_text(encoding="utf-8")
    assert "## threadloom-rules" in content


# ------------------------------------------------------------------
# auto_apply 테스트
# ------------------------------------------------------------------

def test_auto_apply_true_applies_immediately(
    applier, skill_action, target_project,
):
    """auto_apply=true 시 즉시 적용되어야 한다."""
    applier.apply([skill_action])

    skill_path = target_project / ".claude" / "skills" / "test_skill.md"
    assert skill_path.exists()


def test_auto_apply_true_removes_pending(applier, skill_action):
    """auto_apply=true 시 pending 파일이 삭제되어야 한다."""
    applier.apply([skill_action])
    assert not skill_action.file_path.exists()


def test_auto_apply_false_keeps_pending(
    target_project, pending_dir, backups_dir, enhance_log_path,
    skill_action, monkeypatch,
):
    """auto_apply=false 시 pending 파일이 유지되어야 한다."""
    monkeypatch.setattr("src.enhancer.applier._PENDING_DIR", pending_dir)
    monkeypatch.setattr("src.enhancer.backup_manager._BACKUPS_DIR", backups_dir)
    monkeypatch.setattr("src.enhancer.backup_manager._ENHANCE_LOG", enhance_log_path)
    monkeypatch.setattr("src.enhancer.pending_manager._PENDING_DIR", pending_dir)

    config = _make_config(str(target_project), auto_apply=False)
    applier = Applier(config)

    applier.apply([skill_action])

    # pending 파일 유지
    assert skill_action.file_path.exists()
    # skill 파일 미생성
    skill_path = target_project / ".claude" / "skills" / "test_skill.md"
    assert not skill_path.exists()


# ------------------------------------------------------------------
# 백업(backup) 테스트
# ------------------------------------------------------------------

def test_backup_creates_backup_dir(applier, skill_action, target_project):
    """적용 전 백업 디렉토리가 생성되어야 한다."""
    # 기존 파일을 만들어 백업 대상 확보
    existing = target_project / ".claude" / "skills" / "test_skill.md"
    existing.write_text("기존 내용", encoding="utf-8")

    applier.apply([skill_action])

    # backups 디렉토리에 백업이 존재
    from src.enhancer.backup_manager import _BACKUPS_DIR
    backup_dirs = list(_BACKUPS_DIR.iterdir())
    assert len(backup_dirs) >= 1


def test_backup_preserves_original_content(
    applier, skill_action, target_project, backups_dir,
):
    """백업 파일에 기존 내용이 보존되어야 한다."""
    existing = target_project / ".claude" / "skills" / "test_skill.md"
    existing.write_text("기존 skill 내용", encoding="utf-8")

    applier.apply([skill_action])

    # 백업 디렉토리에서 파일 확인
    backup_dirs = list(backups_dir.iterdir())
    if backup_dirs:
        backup_file = list(backup_dirs[0].rglob("*.md"))
        assert len(backup_file) >= 1
        content = backup_file[0].read_text(encoding="utf-8")
        assert "기존 skill 내용" in content


# ------------------------------------------------------------------
# enhance_log.json 테스트
# ------------------------------------------------------------------

def test_enhance_log_records_applied(
    applier, skill_action, enhance_log_path,
):
    """적용 시 enhance_log.json에 이력이 기록되어야 한다."""
    applier.apply([skill_action])

    assert enhance_log_path.exists()
    log = json.loads(enhance_log_path.read_text(encoding="utf-8"))
    assert len(log) >= 1
    assert log[-1]["result"] == "applied"
    assert log[-1]["action_type"] == "create_skill"
    assert log[-1]["name"] == "test_skill"


def test_enhance_log_records_rejected(
    applier, skill_action, enhance_log_path,
):
    """거절 시 enhance_log.json에 rejected로 기록되어야 한다."""
    applier.reject([skill_action])

    assert enhance_log_path.exists()
    log = json.loads(enhance_log_path.read_text(encoding="utf-8"))
    assert len(log) >= 1
    assert log[-1]["result"] == "rejected"


# ------------------------------------------------------------------
# load_pending 테스트
# ------------------------------------------------------------------

def test_load_pending_parses_frontmatter(applier, pending_dir):
    """pending 파일의 frontmatter를 정확히 파싱해야 한다."""
    md_content = (
        "---\n"
        "action_type: create_skill\n"
        "name: loaded_skill\n"
        "target: .claude/skills/loaded_skill.md\n"
        "source_posts: [post-001]\n"
        "duplicate_check: create_new\n"
        "---\n\n"
        "# loaded_skill content\n"
    )
    (pending_dir / "create_skill_loaded_skill.md").write_text(
        md_content, encoding="utf-8",
    )

    actions = applier.load_pending()

    assert len(actions) == 1
    assert actions[0].action_type == "create_skill"
    assert actions[0].name == "loaded_skill"


def test_load_pending_empty_dir(applier, pending_dir):
    """pending 디렉토리가 비어 있으면 빈 리스트를 반환해야 한다."""
    # pending_dir에 파일 없음
    for f in pending_dir.glob("*.md"):
        f.unlink()
    actions = applier.load_pending()
    assert actions == []


def test_load_pending_handles_raw_fallback(applier, pending_dir):
    """frontmatter 없는 raw fallback 파일도 파싱해야 한다."""
    raw_content = "# Raw AI 응답\n\n구분자 없는 원문 텍스트"
    (pending_dir / "raw_fallback_test.md").write_text(
        raw_content, encoding="utf-8",
    )

    actions = applier.load_pending()
    assert len(actions) == 1
    assert actions[0].action_type == "raw_fallback"


# ------------------------------------------------------------------
# merge_skill 테스트
# ------------------------------------------------------------------

def test_merge_skill_appends_to_existing(applier, target_project):
    """merge_skill은 기존 파일에 내용을 추가해야 한다."""
    existing = target_project / ".claude" / "skills" / "merge_target.md"
    existing.write_text("# 기존 내용\n\n원래 텍스트", encoding="utf-8")

    action = PendingAction(
        file_path=Path("/tmp/dummy.md"),
        action_type="merge_skill",
        name="merge_target",
        target=".claude/skills/merge_target.md",
        content="## 추가 섹션\n새로운 내용",
    )
    applier._apply_one(action)

    content = existing.read_text(encoding="utf-8")
    assert "원래 텍스트" in content
    assert "새로운 내용" in content


def test_merge_skill_creates_when_missing(applier, target_project):
    """merge 대상 파일이 없으면 새로 생성해야 한다."""
    action = PendingAction(
        file_path=Path("/tmp/dummy.md"),
        action_type="merge_skill",
        name="new_merge_target",
        target=".claude/skills/new_merge_target.md",
        content="# 신규 merge 내용",
    )
    applier._apply_one(action)

    path = target_project / ".claude" / "skills" / "new_merge_target.md"
    assert path.exists()


# ------------------------------------------------------------------
# 기존 파일 보존(preserve) 테스트
# ------------------------------------------------------------------

def test_create_skill_preserves_existing(applier, target_project):
    """기존 skill 파일이 있으면 .prev.md로 보존해야 한다."""
    existing = target_project / ".claude" / "skills" / "old_skill.md"
    existing.write_text("# 기존 스킬", encoding="utf-8")

    action = PendingAction(
        file_path=Path("/tmp/dummy.md"),
        action_type="create_skill",
        name="old_skill",
        target=".claude/skills/old_skill.md",
        content="# 새로운 스킬",
    )
    applier._apply_one(action)

    prev = target_project / ".claude" / "skills" / "old_skill.prev.md"
    assert prev.exists()
    assert prev.read_text(encoding="utf-8") == "# 기존 스킬"
    assert existing.read_text(encoding="utf-8") == "# 새로운 스킬"


def test_create_agent_preserves_existing(applier, target_project):
    """기존 agent 파일이 있으면 .prev.md로 보존해야 한다."""
    existing = target_project / ".claude" / "agents" / "old_agent.md"
    existing.write_text("# 기존 에이전트", encoding="utf-8")

    action = PendingAction(
        file_path=Path("/tmp/dummy.md"),
        action_type="create_agent",
        name="old_agent",
        target=".claude/agents/old_agent.md",
        content="# 새로운 에이전트",
    )
    applier._apply_one(action)

    prev = target_project / ".claude" / "agents" / "old_agent.prev.md"
    assert prev.exists()
    assert prev.read_text(encoding="utf-8") == "# 기존 에이전트"


def test_merge_skill_preserves_existing(applier, target_project):
    """merge 시 기존 파일이 .prev.md로 보존되어야 한다."""
    existing = target_project / ".claude" / "skills" / "merge_prev.md"
    existing.write_text("# 원본", encoding="utf-8")

    action = PendingAction(
        file_path=Path("/tmp/dummy.md"),
        action_type="merge_skill",
        name="merge_prev",
        target=".claude/skills/merge_prev.md",
        content="## 추가",
    )
    applier._apply_one(action)

    prev = target_project / ".claude" / "skills" / "merge_prev.prev.md"
    assert prev.exists()
    assert prev.read_text(encoding="utf-8") == "# 원본"


def test_add_rule_preserves_claude_md(applier, target_project):
    """rule 추가 시 기존 CLAUDE.md가 .prev.md로 보존되어야 한다."""
    claude_md = target_project / "CLAUDE.md"
    claude_md.write_text("# 프로젝트 규칙\n\n기존 내용", encoding="utf-8")

    action = PendingAction(
        file_path=Path("/tmp/dummy.md"),
        action_type="add_rule",
        name="new_rule",
        target="CLAUDE.md",
        content="### 새 규칙\n- 규칙 내용",
    )
    applier._apply_one(action)

    prev = target_project / "CLAUDE.prev.md"
    assert prev.exists()
    assert "기존 내용" in prev.read_text(encoding="utf-8")


def test_preserve_no_file_does_nothing(applier, target_project):
    """기존 파일이 없으면 .prev.md를 생성하지 않아야 한다."""
    action = PendingAction(
        file_path=Path("/tmp/dummy.md"),
        action_type="create_skill",
        name="brand_new",
        target=".claude/skills/brand_new.md",
        content="# 신규",
    )
    applier._apply_one(action)

    prev = target_project / ".claude" / "skills" / "brand_new.prev.md"
    assert not prev.exists()


# ------------------------------------------------------------------
# refine (진화) 테스트
# ------------------------------------------------------------------

def test_refine_skill_preserves_existing(applier, target_project):
    """refine_skill 시 기존 파일이 .prev.md로 보존되어야 한다."""
    existing = target_project / ".claude" / "skills" / "evolve_target.md"
    existing.write_text("# 기존 skill 내용", encoding="utf-8")

    action = PendingAction(
        file_path=Path("/tmp/dummy.md"),
        action_type="refine_skill",
        name="evolve_target",
        target=".claude/skills/evolve_target.md",
        content="# 진화된 skill 내용\n\n기존 + 새 인사이트",
    )
    applier._apply_one(action)

    prev = target_project / ".claude" / "skills" / "evolve_target.prev.md"
    assert prev.exists()
    assert prev.read_text(encoding="utf-8") == "# 기존 skill 내용"


def test_refine_skill_replaces_with_refined_content(applier, target_project):
    """refine_skill 시 기존 파일이 진화된 내용으로 교체되어야 한다."""
    existing = target_project / ".claude" / "skills" / "evolve_target.md"
    existing.write_text("# 기존 skill 내용", encoding="utf-8")

    refined_content = "# 진화된 skill 내용\n\n기존 + 새 인사이트"
    action = PendingAction(
        file_path=Path("/tmp/dummy.md"),
        action_type="refine_skill",
        name="evolve_target",
        target=".claude/skills/evolve_target.md",
        content=refined_content,
    )
    applier._apply_one(action)

    content = existing.read_text(encoding="utf-8")
    assert content == refined_content


def test_refine_agent_preserves_and_replaces(applier, target_project):
    """refine_agent 시 기존 파일 보존 + 진화된 내용으로 교체되어야 한다."""
    existing = target_project / ".claude" / "agents" / "evolve_agent.md"
    existing.write_text("# 기존 agent", encoding="utf-8")

    refined_content = "# 진화된 agent\n\n새로운 역할 정의"
    action = PendingAction(
        file_path=Path("/tmp/dummy.md"),
        action_type="refine_agent",
        name="evolve_agent",
        target=".claude/agents/evolve_agent.md",
        content=refined_content,
    )
    applier._apply_one(action)

    prev = target_project / ".claude" / "agents" / "evolve_agent.prev.md"
    assert prev.exists()
    assert prev.read_text(encoding="utf-8") == "# 기존 agent"
    assert existing.read_text(encoding="utf-8") == refined_content


def test_refine_skill_creates_when_no_existing(applier, target_project):
    """refine 대상 파일이 없어도 정상 생성되어야 한다."""
    action = PendingAction(
        file_path=Path("/tmp/dummy.md"),
        action_type="refine_skill",
        name="no_existing",
        target=".claude/skills/no_existing.md",
        content="# 신규 refine",
    )
    applier._apply_one(action)

    path = target_project / ".claude" / "skills" / "no_existing.md"
    assert path.exists()
    # .prev.md는 생성되지 않아야 함
    prev = target_project / ".claude" / "skills" / "no_existing.prev.md"
    assert not prev.exists()


def test_preserve_multiple_times_uses_timestamp(applier, target_project):
    """이미 .prev.md가 있으면 타임스탬프로 구분해야 한다."""
    skill_dir = target_project / ".claude" / "skills"
    existing = skill_dir / "multi.md"
    existing.write_text("v1", encoding="utf-8")
    # 첫 번째 .prev.md를 미리 생성
    (skill_dir / "multi.prev.md").write_text("v0", encoding="utf-8")

    action = PendingAction(
        file_path=Path("/tmp/dummy.md"),
        action_type="create_skill",
        name="multi",
        target=".claude/skills/multi.md",
        content="v2",
    )
    applier._apply_one(action)

    # .prev.md는 v0 유지, 타임스탬프 붙은 새 파일 생성
    prev_files = list(skill_dir.glob("multi.prev*.md"))
    assert len(prev_files) == 2


# ------------------------------------------------------------------
# 다중 프로젝트 라우팅(multi-project routing) 테스트
# ------------------------------------------------------------------

@pytest.fixture
def multi_projects(tmp_path) -> tuple[Path, Path]:
    """다중 프로젝트 테스트용 디렉토리 2개를 생성한다."""
    proj_a = tmp_path / "project_a"
    (proj_a / ".claude" / "skills").mkdir(parents=True)
    (proj_a / ".claude" / "agents").mkdir(parents=True)
    proj_b = tmp_path / "project_b"
    (proj_b / ".claude" / "skills").mkdir(parents=True)
    (proj_b / ".claude" / "agents").mkdir(parents=True)
    return proj_a, proj_b


@pytest.fixture
def multi_applier(
    multi_projects, pending_dir, backups_dir, enhance_log_path, monkeypatch,
):
    """다중 프로젝트 라우팅 테스트용 Applier."""
    monkeypatch.setattr("src.enhancer.applier._PENDING_DIR", pending_dir)
    monkeypatch.setattr("src.enhancer.backup_manager._BACKUPS_DIR", backups_dir)
    monkeypatch.setattr("src.enhancer.backup_manager._ENHANCE_LOG", enhance_log_path)
    monkeypatch.setattr("src.enhancer.pending_manager._PENDING_DIR", pending_dir)

    proj_a, proj_b = multi_projects
    config = _make_config(
        str(proj_a),
        auto_apply=True,
        target_projects=[
            {"name": "project_a", "path": str(proj_a), "tags": ["Python"]},
            {"name": "project_b", "path": str(proj_b), "tags": ["Rust"]},
        ],
    )
    return Applier(config)


def test_routing_to_project_b(multi_applier, multi_projects, pending_dir):
    """frontmatter에 target_project가 있으면 해당 프로젝트로 라우팅해야 한다."""
    proj_a, proj_b = multi_projects
    # pending 파일에 target_project: project_b 지정
    pending_file = pending_dir / "create_skill_routed.md"
    pending_file.write_text(
        "---\n"
        "action_type: create_skill\n"
        "name: routed\n"
        "target: .claude/skills/routed.md\n"
        "target_project: project_b\n"
        "---\n\n"
        "# 라우팅 테스트 skill",
        encoding="utf-8",
    )
    action = PendingAction(
        file_path=pending_file,
        action_type="create_skill",
        name="routed",
        target=".claude/skills/routed.md",
        content="# 라우팅 테스트 skill",
    )
    multi_applier._apply_one(action)

    # project_b에 생성되어야 함
    assert (proj_b / ".claude" / "skills" / "routed.md").exists()
    # project_a에는 생성되지 않아야 함
    assert not (proj_a / ".claude" / "skills" / "routed.md").exists()


def test_routing_fallback_to_default(multi_applier, multi_projects, pending_dir):
    """target_project 미지정 시 기본 프로젝트(project_a)로 라우팅해야 한다."""
    proj_a, proj_b = multi_projects
    pending_file = pending_dir / "create_skill_default.md"
    pending_file.write_text(
        "---\n"
        "action_type: create_skill\n"
        "name: default_target\n"
        "target: .claude/skills/default_target.md\n"
        "---\n\n"
        "# 기본 라우팅 skill",
        encoding="utf-8",
    )
    action = PendingAction(
        file_path=pending_file,
        action_type="create_skill",
        name="default_target",
        target=".claude/skills/default_target.md",
        content="# 기본 라우팅 skill",
    )
    multi_applier._apply_one(action)

    # 기본 프로젝트(project_a)에 생성되어야 함
    assert (proj_a / ".claude" / "skills" / "default_target.md").exists()
    assert not (proj_b / ".claude" / "skills" / "default_target.md").exists()


def test_routing_rule_to_project_b(multi_applier, multi_projects, pending_dir):
    """add_rule도 target_project로 라우팅되어야 한다."""
    proj_a, proj_b = multi_projects
    pending_file = pending_dir / "add_rule_routed_rule.md"
    pending_file.write_text(
        "---\n"
        "action_type: add_rule\n"
        "name: routed_rule\n"
        "target: CLAUDE.md\n"
        "target_project: project_b\n"
        "---\n\n"
        "### 라우팅 규칙\n- 규칙 내용",
        encoding="utf-8",
    )
    action = PendingAction(
        file_path=pending_file,
        action_type="add_rule",
        name="routed_rule",
        target="CLAUDE.md",
        content="### 라우팅 규칙\n- 규칙 내용",
    )
    multi_applier._apply_one(action)

    # project_b의 CLAUDE.md에 생성되어야 함
    claude_md = proj_b / "CLAUDE.md"
    assert claude_md.exists()
    assert "라우팅 규칙" in claude_md.read_text(encoding="utf-8")


def test_routing_unknown_project_falls_back(
    multi_applier, multi_projects, pending_dir,
):
    """등록되지 않은 프로젝트명은 기본 프로젝트로 폴백해야 한다."""
    proj_a, proj_b = multi_projects
    pending_file = pending_dir / "create_skill_unknown.md"
    pending_file.write_text(
        "---\n"
        "action_type: create_skill\n"
        "name: unknown_proj\n"
        "target: .claude/skills/unknown_proj.md\n"
        "target_project: nonexistent\n"
        "---\n\n"
        "# 미등록 프로젝트 skill",
        encoding="utf-8",
    )
    action = PendingAction(
        file_path=pending_file,
        action_type="create_skill",
        name="unknown_proj",
        target=".claude/skills/unknown_proj.md",
        content="# 미등록 프로젝트 skill",
    )
    multi_applier._apply_one(action)

    # 기본 프로젝트(project_a)에 폴백
    assert (proj_a / ".claude" / "skills" / "unknown_proj.md").exists()
