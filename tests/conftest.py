"""테스트 공통 설정 — playwright_stealth import 호환성(compatibility) 처리 및 공유 fixture."""

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from src.enhancer.models import PendingAction


def _ensure_stealth_sync():
    """playwright_stealth.stealth_sync이 없으면 mock으로 패치한다."""
    try:
        from playwright_stealth import stealth_sync  # noqa: F401
    except ImportError:
        # v2에서 이름이 변경된 경우 mock 삽입
        mod = sys.modules.get("playwright_stealth")
        if mod is None:
            mod = ModuleType("playwright_stealth")
            sys.modules["playwright_stealth"] = mod
        if not hasattr(mod, "stealth_sync"):
            mod.stealth_sync = MagicMock()


_ensure_stealth_sync()


# ------------------------------------------------------------------
# 공유 fixture
# ------------------------------------------------------------------

def make_pending_action(
    tmp_path: Path,
    action_type: str = "create_skill",
    name: str = "test_skill",
    content: str = "# Test Skill",
) -> PendingAction:
    """테스트용 PendingAction을 생성하는 공유 헬퍼(helper)."""
    file_path = tmp_path / f"{name}.md"
    file_path.write_text(
        f"---\naction_type: {action_type}\nname: {name}\n---\n{content}",
        encoding="utf-8",
    )
    return PendingAction(
        file_path=file_path,
        action_type=action_type,
        name=name,
        target="default",
        content=content,
    )


@pytest.fixture
def target_project(tmp_path) -> Path:
    """테스트용 대상 프로젝트를 생성한다."""
    project = tmp_path / "test_project"
    (project / ".claude" / "skills").mkdir(parents=True)
    (project / ".claude" / "agents").mkdir(parents=True)
    return project
