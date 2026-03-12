"""pending_manager 모듈 단위 테스트.

pending 파일 삭제, 정리, 승인, 거부 이동을 검증한다.
"""

import os
import sys
import time
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.enhancer.pending_manager import (
    clean_pending,
    mark_approved,
    move_to_rejected,
    remove_old_files,
    remove_pending,
)
from tests.conftest import make_pending_action as _make_action


# ------------------------------------------------------------------
# remove_pending
# ------------------------------------------------------------------

def test_remove_pending_deletes_file(tmp_path):
    """처리 완료 시 pending 파일이 삭제된다."""
    action = _make_action(tmp_path)
    assert action.file_path.exists()
    remove_pending(action)
    assert not action.file_path.exists()


def test_remove_pending_missing_file(tmp_path):
    """파일이 이미 없어도 에러 없이 통과한다."""
    action = _make_action(tmp_path)
    action.file_path.unlink()
    remove_pending(action)  # missing_ok=True


# ------------------------------------------------------------------
# remove_old_files
# ------------------------------------------------------------------

def test_remove_old_files(tmp_path, monkeypatch):
    """cutoff 이전 파일만 삭제한다."""
    monkeypatch.setattr("src.enhancer.pending_manager._PENDING_DIR", tmp_path)

    from datetime import datetime

    old = tmp_path / "old.md"
    old.write_text("old", encoding="utf-8")
    # mtime을 과거(past)로 설정
    past = time.time() - 86400 * 60  # 60일 전
    os.utime(old, (past, past))

    new = tmp_path / "new.md"
    new.write_text("new", encoding="utf-8")
    # new 파일은 미래(future)로 설정하여 cutoff보다 확실히 이후
    future = time.time() + 86400
    os.utime(new, (future, future))

    cutoff = datetime.now()
    removed = remove_old_files(cutoff)

    assert removed == 1
    assert not old.exists()
    assert new.exists()


# ------------------------------------------------------------------
# clean_pending
# ------------------------------------------------------------------

def test_clean_pending_no_dir(tmp_path, monkeypatch):
    """pending 디렉토리가 없으면 에러 없이 통과한다."""
    monkeypatch.setattr(
        "src.enhancer.pending_manager._PENDING_DIR",
        tmp_path / "nonexist",
    )
    clean_pending(days=30)  # 에러 없이 통과


def test_clean_pending_removes_old(tmp_path, monkeypatch):
    """오래된 파일만 정리한다."""
    monkeypatch.setattr("src.enhancer.pending_manager._PENDING_DIR", tmp_path)

    old = tmp_path / "old_action.md"
    old.write_text("old", encoding="utf-8")
    past = time.time() - 86400 * 60
    os.utime(old, (past, past))

    new = tmp_path / "new_action.md"
    new.write_text("new", encoding="utf-8")

    clean_pending(days=30)

    assert not old.exists()
    assert new.exists()


# ------------------------------------------------------------------
# mark_approved
# ------------------------------------------------------------------

def test_mark_approved_adds_status(tmp_path):
    """status: approved frontmatter가 추가된다."""
    action = _make_action(tmp_path)
    mark_approved(action)

    text = action.file_path.read_text(encoding="utf-8")
    assert "status: approved" in text


def test_mark_approved_missing_file(tmp_path):
    """파일이 없으면 에러 없이 통과한다."""
    action = _make_action(tmp_path)
    action.file_path.unlink()
    mark_approved(action)  # OSError 발생 시 조용히 반환(return)


# ------------------------------------------------------------------
# move_to_rejected
# ------------------------------------------------------------------

def test_move_to_rejected(tmp_path, monkeypatch):
    """pending 파일이 rejected 디렉토리로 이동한다."""
    rejected_dir = tmp_path / "rejected"
    monkeypatch.setattr(
        "src.enhancer.pending_manager._REJECTED_DIR", rejected_dir,
    )

    action = _make_action(tmp_path, name="rejected_action")
    move_to_rejected(action)

    # 원본(original) 삭제 확인
    assert not action.file_path.exists()
    # rejected 디렉토리에 파일 존재 확인
    rejected_file = rejected_dir / "rejected_action.md"
    assert rejected_file.exists()
    text = rejected_file.read_text(encoding="utf-8")
    assert "rejection_reason: user_rejected" in text


def test_move_to_rejected_missing_source(tmp_path, monkeypatch):
    """원본 파일이 없으면 삭제만 시도하고 통과한다."""
    rejected_dir = tmp_path / "rejected"
    monkeypatch.setattr(
        "src.enhancer.pending_manager._REJECTED_DIR", rejected_dir,
    )

    action = _make_action(tmp_path, name="ghost")
    action.file_path.unlink()
    move_to_rejected(action)  # 에러 없이 통과
