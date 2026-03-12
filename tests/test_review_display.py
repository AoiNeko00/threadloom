"""review_display 모듈 및 applier review 흐름 테스트.

rich 기반 Diff 뷰 표시, 승인/거부 처리, rejected 이동을 검증한다.
"""

import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.enhancer.applier import Applier
from src.enhancer.models import PendingAction
from src.enhancer.pending_manager import mark_approved, move_to_rejected
from src.utils.frontmatter import set_frontmatter_field
from src.writer.review_display import (
    _add_delete_rows,
    _add_equal_rows,
    _add_insert_rows,
    _add_replace_rows,
    _extract_score,
    _read_existing,
    _resolve_target_file,
    display_summary,
)


# ------------------------------------------------------------------
# fixture
# ------------------------------------------------------------------

def _make_config(target_path: str, auto_apply: bool = False) -> MagicMock:
    """테스트용 Config mock."""
    config = MagicMock()
    config.target_project_path = target_path
    config.auto_apply = auto_apply
    return config


@pytest.fixture
def target_project(tmp_path) -> Path:
    """테스트용 대상 프로젝트 디렉토리."""
    project = tmp_path / "test_project"
    (project / ".claude" / "skills").mkdir(parents=True)
    (project / ".claude" / "agents").mkdir(parents=True)
    return project


@pytest.fixture
def pending_dir(tmp_path) -> Path:
    """테스트용 pending 디렉토리."""
    d = tmp_path / "pending"
    d.mkdir()
    return d


@pytest.fixture
def rejected_dir(tmp_path) -> Path:
    """테스트용 rejected 디렉토리."""
    d = tmp_path / "rejected"
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
def applier(
    target_project, pending_dir, rejected_dir,
    backups_dir, enhance_log_path, monkeypatch,
):
    """테스트용 Applier."""
    monkeypatch.setattr("src.enhancer.applier._PENDING_DIR", pending_dir)
    monkeypatch.setattr("src.enhancer.pending_manager._PENDING_DIR", pending_dir)
    monkeypatch.setattr("src.enhancer.pending_manager._REJECTED_DIR", rejected_dir)
    monkeypatch.setattr("src.enhancer.backup_manager._BACKUPS_DIR", backups_dir)
    monkeypatch.setattr("src.enhancer.backup_manager._ENHANCE_LOG", enhance_log_path)

    config = _make_config(str(target_project), auto_apply=False)
    return Applier(config)


def _make_pending_file(
    pending_dir: Path, name: str, action_type: str = "create_skill",
    score: float = 0.85, dup_check: str = "create_new",
) -> Path:
    """frontmatter 포함 pending 파일을 생성한다."""
    content = (
        f"---\n"
        f"action_type: {action_type}\n"
        f"name: {name}\n"
        f"target: .claude/skills/{name}.md\n"
        f"source_posts: [post-001]\n"
        f"relevance_score: {score}\n"
        f"duplicate_check: {dup_check}\n"
        f"status: pending\n"
        f"---\n\n"
        f"# {name}\n\n테스트 스킬 내용"
    )
    path = pending_dir / f"{action_type}_{name}.md"
    path.write_text(content, encoding="utf-8")
    return path


# ------------------------------------------------------------------
# _extract_score 테스트
# ------------------------------------------------------------------

def test_extract_score_returns_value(pending_dir):
    """frontmatter에 relevance_score가 있으면 값을 반환해야 한다."""
    path = _make_pending_file(pending_dir, "scored_skill", score=0.92)
    action = PendingAction(
        file_path=path, action_type="create_skill",
        name="scored_skill", target="", content="",
    )
    assert _extract_score(action) == "0.92"


def test_extract_score_missing_returns_na(tmp_path):
    """relevance_score가 없으면 N/A를 반환해야 한다."""
    path = tmp_path / "no_score.md"
    path.write_text("---\naction_type: create_skill\n---\ncontent", encoding="utf-8")
    action = PendingAction(
        file_path=path, action_type="create_skill",
        name="no_score", target="", content="",
    )
    assert _extract_score(action) == "N/A"


# ------------------------------------------------------------------
# _resolve_target_file 테스트
# ------------------------------------------------------------------

def test_resolve_target_skill(target_project):
    """create_skill은 .claude/skills/ 경로로 해석해야 한다."""
    action = PendingAction(
        file_path=Path("/tmp/dummy.md"), action_type="create_skill",
        name="my_skill", target=".claude/skills/my_skill.md", content="",
    )
    result = _resolve_target_file(action, target_project)
    assert result == target_project / ".claude" / "skills" / "my_skill.md"


def test_resolve_target_agent(target_project):
    """create_agent는 .claude/agents/ 경로로 해석해야 한다."""
    action = PendingAction(
        file_path=Path("/tmp/dummy.md"), action_type="create_agent",
        name="my_agent", target=".claude/agents/my_agent.md", content="",
    )
    result = _resolve_target_file(action, target_project)
    assert result == target_project / ".claude" / "agents" / "my_agent.md"


def test_resolve_target_rule(target_project):
    """add_rule은 CLAUDE.md 경로로 해석해야 한다."""
    action = PendingAction(
        file_path=Path("/tmp/dummy.md"), action_type="add_rule",
        name="my_rule", target="CLAUDE.md", content="",
    )
    result = _resolve_target_file(action, target_project)
    assert result == target_project / "CLAUDE.md"


def test_resolve_target_unknown(target_project):
    """알 수 없는 action_type은 None을 반환해야 한다."""
    action = PendingAction(
        file_path=Path("/tmp/dummy.md"), action_type="unknown",
        name="x", target="", content="",
    )
    assert _resolve_target_file(action, target_project) is None


# ------------------------------------------------------------------
# _read_existing 테스트
# ------------------------------------------------------------------

def test_read_existing_returns_file_content(target_project):
    """기존 파일이 있으면 내용을 반환해야 한다."""
    skill_path = target_project / ".claude" / "skills" / "existing.md"
    skill_path.write_text("# 기존 스킬", encoding="utf-8")

    action = PendingAction(
        file_path=Path("/tmp/dummy.md"), action_type="create_skill",
        name="existing", target=".claude/skills/existing.md", content="",
    )
    result = _read_existing(action, target_project)
    assert "기존 스킬" in result


def test_read_existing_returns_empty_when_missing(target_project):
    """기존 파일이 없으면 빈 문자열을 반환해야 한다."""
    action = PendingAction(
        file_path=Path("/tmp/dummy.md"), action_type="create_skill",
        name="missing", target=".claude/skills/missing.md", content="",
    )
    assert _read_existing(action, target_project) == ""


# ------------------------------------------------------------------
# Side-by-Side diff 테이블 행(row) 추가 테스트
# ------------------------------------------------------------------

def test_add_equal_rows_adds_same_content():
    """equal 행은 좌우 동일 내용이어야 한다."""
    from rich.table import Table
    table = Table()
    table.add_column("기존")
    table.add_column("변경 후")
    _add_equal_rows(table, ["line1", "line2"])
    assert table.row_count == 2


def test_add_delete_rows_adds_only_left():
    """delete 행은 왼쪽만 채워져야 한다."""
    from rich.table import Table
    table = Table()
    table.add_column("기존")
    table.add_column("변경 후")
    _add_delete_rows(table, ["removed"])
    assert table.row_count == 1


def test_add_insert_rows_adds_only_right():
    """insert 행은 오른쪽만 채워져야 한다."""
    from rich.table import Table
    table = Table()
    table.add_column("기존")
    table.add_column("변경 후")
    _add_insert_rows(table, ["added"])
    assert table.row_count == 1


def test_add_replace_rows_handles_different_lengths():
    """replace는 좌우 줄 수가 다를 때도 처리해야 한다."""
    from rich.table import Table
    table = Table()
    table.add_column("기존")
    table.add_column("변경 후")
    _add_replace_rows(table, ["a", "b"], ["x", "y", "z"])
    assert table.row_count == 3


# ------------------------------------------------------------------
# display_summary 테스트
# ------------------------------------------------------------------

def test_display_summary_outputs_counts(capsys):
    """display_summary가 승인/거부/건너뛰기 건수를 출력해야 한다."""
    # rich는 stderr이 아닌 stdout에 출력하므로 Console 캡처
    from rich.console import Console
    buf = StringIO()
    console = Console(file=buf, force_terminal=True)
    # display_summary 내부의 _console을 패치
    with patch("src.writer.review_display._console", console):
        display_summary(3, 1, 2)
    output = buf.getvalue()
    assert "3" in output
    assert "1" in output
    assert "2" in output


# ------------------------------------------------------------------
# applier._mark_approved 테스트
# ------------------------------------------------------------------

def test_mark_approved_adds_status(applier, pending_dir):
    """승인 시 frontmatter에 status: approved가 추가되어야 한다."""
    path = _make_pending_file(pending_dir, "approve_test")
    action = PendingAction(
        file_path=path, action_type="create_skill",
        name="approve_test", target="", content="",
    )
    mark_approved(action)

    content = path.read_text(encoding="utf-8")
    assert "status: approved" in content


def test_mark_approved_replaces_existing_status(applier, pending_dir):
    """기존 status: pending이 status: approved로 교체되어야 한다."""
    path = _make_pending_file(pending_dir, "replace_test")
    action = PendingAction(
        file_path=path, action_type="create_skill",
        name="replace_test", target="", content="",
    )
    mark_approved(action)

    content = path.read_text(encoding="utf-8")
    assert "status: approved" in content
    assert "status: pending" not in content


# ------------------------------------------------------------------
# applier._move_to_rejected 테스트
# ------------------------------------------------------------------

def test_move_to_rejected_creates_file(applier, pending_dir, rejected_dir):
    """거부 시 파일이 data/rejected/로 이동해야 한다."""
    path = _make_pending_file(pending_dir, "reject_test")
    action = PendingAction(
        file_path=path, action_type="create_skill",
        name="reject_test", target="", content="",
    )
    move_to_rejected(action)

    assert not path.exists()
    rejected_file = rejected_dir / path.name
    assert rejected_file.exists()


def test_move_to_rejected_adds_reason(applier, pending_dir, rejected_dir):
    """거부된 파일에 rejection_reason이 추가되어야 한다."""
    path = _make_pending_file(pending_dir, "reason_test")
    action = PendingAction(
        file_path=path, action_type="create_skill",
        name="reason_test", target="", content="",
    )
    move_to_rejected(action)

    rejected_file = rejected_dir / path.name
    content = rejected_file.read_text(encoding="utf-8")
    assert "rejection_reason: user_rejected" in content


# ------------------------------------------------------------------
# applier._set_frontmatter_field 테스트
# ------------------------------------------------------------------

def test_set_frontmatter_field_adds_new_key(applier):
    """존재하지 않는 키를 추가해야 한다."""
    text = "---\naction_type: create_skill\n---\ncontent"
    result = set_frontmatter_field(text, "new_key", "new_val")
    assert "new_key: new_val" in result


def test_set_frontmatter_field_replaces_existing(applier):
    """기존 키의 값을 교체해야 한다."""
    text = "---\nstatus: pending\n---\ncontent"
    result = set_frontmatter_field(text, "status", "approved")
    assert "status: approved" in result
    assert "status: pending" not in result


def test_set_frontmatter_field_no_frontmatter(applier):
    """frontmatter가 없으면 새로 생성해야 한다."""
    text = "plain content without frontmatter"
    result = set_frontmatter_field(text, "status", "approved")
    assert result.startswith("---\n")
    assert "status: approved" in result


# ------------------------------------------------------------------
# applier.count_pending_remaining 테스트
# ------------------------------------------------------------------

def test_count_pending_remaining(applier, pending_dir):
    """건너뛴 항목 수를 정확히 계산해야 한다."""
    _make_pending_file(pending_dir, "a")
    _make_pending_file(pending_dir, "b")
    _make_pending_file(pending_dir, "c")

    approved = [MagicMock()] * 1
    rejected = [MagicMock()] * 1
    result = applier.count_pending_remaining(approved, rejected)
    assert result == 1


# ------------------------------------------------------------------
# review() 전체 흐름 통합(integration) 테스트
# ------------------------------------------------------------------

def test_review_approve_flow(applier, pending_dir, monkeypatch):
    """review에서 y 입력 시 승인 리스트에 포함되어야 한다."""
    _make_pending_file(pending_dir, "flow_test")

    # rich 출력 및 입력을 mock
    monkeypatch.setattr(
        "src.writer.review_display._console",
        MagicMock(),
    )
    monkeypatch.setattr("builtins.input", lambda _="": "y")

    approved, rejected = applier.review()
    assert len(approved) == 1
    assert len(rejected) == 0


def test_review_reject_flow(applier, pending_dir, monkeypatch):
    """review에서 n 입력 시 거절 리스트에 포함되어야 한다."""
    _make_pending_file(pending_dir, "reject_flow")

    monkeypatch.setattr(
        "src.writer.review_display._console",
        MagicMock(),
    )
    monkeypatch.setattr("builtins.input", lambda _="": "n")

    approved, rejected = applier.review()
    assert len(approved) == 0
    assert len(rejected) == 1


def test_review_quit_stops_early(applier, pending_dir, monkeypatch):
    """review에서 q 입력 시 나머지 항목을 건너뛰어야 한다."""
    _make_pending_file(pending_dir, "q_first")
    _make_pending_file(pending_dir, "q_second")

    monkeypatch.setattr(
        "src.writer.review_display._console",
        MagicMock(),
    )
    monkeypatch.setattr("builtins.input", lambda _="": "q")

    approved, rejected = applier.review()
    assert len(approved) == 0
    assert len(rejected) == 0


def test_review_skip_keeps_in_pending(applier, pending_dir, monkeypatch):
    """review에서 s 입력 시 어느 리스트에도 포함되지 않아야 한다."""
    _make_pending_file(pending_dir, "skip_test")

    monkeypatch.setattr(
        "src.writer.review_display._console",
        MagicMock(),
    )
    monkeypatch.setattr("builtins.input", lambda _="": "s")

    approved, rejected = applier.review()
    assert len(approved) == 0
    assert len(rejected) == 0
