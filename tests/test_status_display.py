"""상태 표시(status display) 모듈 테스트.

build_enhancement_map 함수를 공개 API 수준에서 검증한다.
"""

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.cli.status_display import build_enhancement_map


# ------------------------------------------------------------------
# build_enhancement_map 테스트
# ------------------------------------------------------------------

class TestBuildEnhancementMap:
    """강화 맵(enhancement map) 집계를 검증한다."""

    def test_empty_project(self, target_project):
        """빈 프로젝트는 빈 dict를 반환해야 한다."""
        result = build_enhancement_map(target_project)
        assert result == {}

    def test_skills_with_tags(self, target_project):
        """태그(tag)가 있는 skill은 태그 기반으로 분류해야 한다."""
        skills_dir = target_project / ".claude" / "skills"
        (skills_dir / "error_handler.md").write_text(
            "---\ntags: [testing]\n---\n# Error Handler\n",
            encoding="utf-8",
        )

        result = build_enhancement_map(target_project)
        assert result["testing"]["skill"] == 1

    def test_skills_without_tags(self, target_project):
        """태그 없는 skill은 파일명 첫 단어(first word)로 분류해야 한다."""
        skills_dir = target_project / ".claude" / "skills"
        (skills_dir / "security_audit.md").write_text(
            "---\n---\n# Security Audit\n",
            encoding="utf-8",
        )

        result = build_enhancement_map(target_project)
        assert result["security"]["skill"] == 1

    def test_rules_from_claude_md(self, target_project):
        """CLAUDE.md threadloom-rules 섹션의 규칙을 집계해야 한다."""
        claude_md = target_project / "CLAUDE.md"
        claude_md.write_text(
            "# Project\n\n"
            "## threadloom-rules\n\n"
            "### error handling\n\n에러 처리 규칙\n\n"
            "### naming convention\n\n네이밍 규칙\n\n"
            "<!-- threadloom-rules-end -->\n",
            encoding="utf-8",
        )

        result = build_enhancement_map(target_project)
        assert result["error"]["rule"] == 1
        assert result["naming"]["rule"] == 1

    def test_prev_files_excluded(self, target_project):
        """.prev.md 백업 파일은 집계에서 제외되어야 한다."""
        skills_dir = target_project / ".claude" / "skills"
        (skills_dir / "test_skill.md").write_text(
            "---\n---\n# Skill\n", encoding="utf-8",
        )
        (skills_dir / "test_skill.prev.md").write_text(
            "---\n---\n# Old\n", encoding="utf-8",
        )
        (skills_dir / "test_skill.prev_20260312.md").write_text(
            "---\n---\n# Older\n", encoding="utf-8",
        )

        result = build_enhancement_map(target_project)
        assert result.get("test", {}).get("skill", 0) == 1
