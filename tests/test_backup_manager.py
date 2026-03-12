"""backup_manager 모듈 단위 테스트.

백업(backup), 복원(restore), 롤백(rollback), 이력(log) 관리를 검증한다.
"""

import json
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.enhancer.backup_manager import (
    backup,
    collect_backup_targets,
    find_latest_backup,
    log_enhancement,
    mark_rolled_back,
    read_log,
    restore_backup,
    rollback,
    safe_relative_to,
    write_log,
)
from src.enhancer.models import PendingAction
from tests.conftest import make_pending_action as _make_action


# ------------------------------------------------------------------
# collect_backup_targets
# ------------------------------------------------------------------

def test_collect_backup_targets_existing(target_project, tmp_path):
    """존재하는 대상 파일의 경로만 수집한다."""
    skill_file = target_project / ".claude" / "skills" / "existing.md"
    skill_file.write_text("# Existing", encoding="utf-8")

    action = _make_action(tmp_path, "create_skill", "existing")
    paths = collect_backup_targets([action], {}, target_project)
    assert len(paths) == 1
    assert paths[0] == str(skill_file)


def test_collect_backup_targets_no_existing(target_project, tmp_path):
    """파일이 없는 액션은 수집하지 않는다."""
    action = _make_action(tmp_path, "create_skill", "nonexist")
    paths = collect_backup_targets([action], {}, target_project)
    assert len(paths) == 0


# ------------------------------------------------------------------
# safe_relative_to
# ------------------------------------------------------------------

def test_safe_relative_to_default(tmp_path):
    """default_root 기준 상대경로를 반환한다."""
    full = tmp_path / "sub" / "file.md"
    result = safe_relative_to(full, {}, tmp_path)
    assert result == Path("sub") / "file.md"


def test_safe_relative_to_project_map(tmp_path):
    """project_map 내 프로젝트 기준 상대경로를 반환한다."""
    project_dir = tmp_path / "my_project"
    project_dir.mkdir()
    full = project_dir / "a" / "b.md"
    project_map = {"my_project": str(project_dir)}
    result = safe_relative_to(full, project_map, tmp_path / "other")
    assert result == Path("a") / "b.md"


def test_safe_relative_to_fallback_name(tmp_path):
    """어디에도 속하지 않으면 파일명만 반환한다."""
    full = Path("/completely/different/path/file.md")
    result = safe_relative_to(full, {}, tmp_path)
    assert result == Path("file.md")


# ------------------------------------------------------------------
# backup / restore
# ------------------------------------------------------------------

def test_backup_creates_copy(target_project, tmp_path, monkeypatch):
    """백업 시 파일이 backups 디렉토리에 복사된다."""
    backups_dir = tmp_path / "backups"
    monkeypatch.setattr("src.enhancer.backup_manager._BACKUPS_DIR", backups_dir)

    skill_file = target_project / ".claude" / "skills" / "backed.md"
    skill_file.write_text("# Backup Target", encoding="utf-8")

    backup_dir = backup([str(skill_file)], {}, target_project)
    assert backup_dir.exists()
    # 백업 내 파일 존재 확인(confirm)
    backed = list(backup_dir.rglob("*.md"))
    assert len(backed) == 1
    assert "# Backup Target" in backed[0].read_text()


def test_backup_skips_missing_files(tmp_path, monkeypatch):
    """존재하지 않는 파일은 건너뛴다."""
    backups_dir = tmp_path / "backups"
    monkeypatch.setattr("src.enhancer.backup_manager._BACKUPS_DIR", backups_dir)

    backup_dir = backup([str(tmp_path / "missing.md")], {}, tmp_path)
    backed = list(backup_dir.rglob("*.md"))
    assert len(backed) == 0


def test_restore_backup(tmp_path):
    """백업 디렉토리 파일이 대상 위치로 복원된다."""
    backup_dir = tmp_path / "backup"
    (backup_dir / "sub").mkdir(parents=True)
    (backup_dir / "sub" / "file.md").write_text("# Restored", encoding="utf-8")

    target = tmp_path / "target"
    target.mkdir()
    restore_backup(backup_dir, target)

    restored = target / "sub" / "file.md"
    assert restored.exists()
    assert "# Restored" in restored.read_text()


# ------------------------------------------------------------------
# find_latest_backup
# ------------------------------------------------------------------

def test_find_latest_backup_empty(tmp_path, monkeypatch):
    """백업 디렉토리가 비어 있으면 None을 반환한다."""
    monkeypatch.setattr("src.enhancer.backup_manager._BACKUPS_DIR", tmp_path)
    assert find_latest_backup() is None


def test_find_latest_backup_no_dir(tmp_path, monkeypatch):
    """백업 디렉토리가 없으면 None을 반환한다."""
    monkeypatch.setattr(
        "src.enhancer.backup_manager._BACKUPS_DIR",
        tmp_path / "nonexist",
    )
    assert find_latest_backup() is None


def test_find_latest_backup_returns_newest(tmp_path, monkeypatch):
    """가장 최근(이름순) 디렉토리를 반환한다."""
    monkeypatch.setattr("src.enhancer.backup_manager._BACKUPS_DIR", tmp_path)
    (tmp_path / "2026-03-10T120000").mkdir()
    (tmp_path / "2026-03-12T120000").mkdir()
    (tmp_path / "2026-03-11T120000").mkdir()

    result = find_latest_backup()
    assert result.name == "2026-03-12T120000"


# ------------------------------------------------------------------
# rollback
# ------------------------------------------------------------------

def test_rollback_restores_latest(tmp_path, monkeypatch):
    """rollback 시 최신 백업에서 복원된다."""
    backups_dir = tmp_path / "backups"
    backup_dir = backups_dir / "2026-03-12T120000"
    backup_dir.mkdir(parents=True)
    (backup_dir / "file.md").write_text("# Rollback", encoding="utf-8")

    monkeypatch.setattr("src.enhancer.backup_manager._BACKUPS_DIR", backups_dir)
    # mark_rolled_back에 필요한 log 파일(file)
    monkeypatch.setattr(
        "src.enhancer.backup_manager._ENHANCE_LOG",
        tmp_path / "log.json",
    )

    target = tmp_path / "target"
    target.mkdir()
    rollback(target)

    assert (target / "file.md").exists()
    assert "# Rollback" in (target / "file.md").read_text()


def test_rollback_no_backup(tmp_path, monkeypatch):
    """백업이 없으면 경고만 출력하고 에러 없이 통과한다."""
    monkeypatch.setattr(
        "src.enhancer.backup_manager._BACKUPS_DIR",
        tmp_path / "empty",
    )
    rollback(tmp_path)  # 에러(error) 없이 통과


# ------------------------------------------------------------------
# read_log / write_log / log_enhancement
# ------------------------------------------------------------------

def test_read_log_empty(tmp_path, monkeypatch):
    """로그 파일이 없으면 빈 리스트를 반환한다."""
    monkeypatch.setattr(
        "src.enhancer.backup_manager._ENHANCE_LOG",
        tmp_path / "missing.json",
    )
    assert read_log() == []


def test_write_and_read_log(tmp_path, monkeypatch):
    """write_log로 기록한 데이터를 read_log로 읽을 수 있다."""
    log_file = tmp_path / "log.json"
    monkeypatch.setattr("src.enhancer.backup_manager._ENHANCE_LOG", log_file)

    entries = [{"action_type": "create_skill", "result": "ok"}]
    write_log(entries)

    assert read_log() == entries


def test_log_enhancement_appends(tmp_path, monkeypatch):
    """log_enhancement는 기존 로그에 항목을 추가한다."""
    log_file = tmp_path / "log.json"
    monkeypatch.setattr("src.enhancer.backup_manager._ENHANCE_LOG", log_file)

    action = PendingAction(
        file_path=tmp_path / "test.md",
        action_type="create_skill",
        name="test",
        target="default",
        content="# Test",
    )

    log_enhancement(action, "applied")
    log_enhancement(action, "applied")

    log = read_log()
    assert len(log) == 2
    assert log[0]["result"] == "applied"


def test_read_log_corrupted(tmp_path, monkeypatch):
    """JSON이 손상된 경우 빈 리스트를 반환한다."""
    log_file = tmp_path / "log.json"
    log_file.write_text("{invalid json", encoding="utf-8")
    monkeypatch.setattr("src.enhancer.backup_manager._ENHANCE_LOG", log_file)

    assert read_log() == []


# ------------------------------------------------------------------
# mark_rolled_back
# ------------------------------------------------------------------

def test_mark_rolled_back(tmp_path, monkeypatch):
    """해당 백업명 항목의 result를 rolled_back으로 변경한다."""
    log_file = tmp_path / "log.json"
    monkeypatch.setattr("src.enhancer.backup_manager._ENHANCE_LOG", log_file)

    entries = [
        {"backup": "data/backups/2026-03-12T120000/", "result": "applied"},
        {"backup": "data/backups/2026-03-11T120000/", "result": "applied"},
    ]
    write_log(entries)

    mark_rolled_back("2026-03-12T120000")

    log = read_log()
    assert log[0]["result"] == "rolled_back"
    assert log[1]["result"] == "applied"
