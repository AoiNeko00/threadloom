"""action 적용 분기(dispatch) + CLAUDE.md 규칙 관리 모듈.

PendingAction의 action_type에 따라 파일 생성/수정/병합/규칙 추가를 수행한다.
"""

import re
import shutil
from datetime import datetime
from pathlib import Path

from src.enhancer.models import PendingAction
from src.utils.frontmatter import parse_frontmatter
from src.utils.i18n import t
from src.utils.logger import get_logger

_logger = get_logger("action_executor")

# threadloom-rules 섹션 경계(boundary) 마커
_RULES_HEADER = "## threadloom-rules"
_RULES_END_MARKER = "<!-- threadloom-rules-end -->"


def apply_one(
    action: PendingAction,
    target_root: Path,
    project_map: dict[str, str],
    default_root: Path,
) -> None:
    """단일 강화 항목을 action_type에 따라 적용한다."""
    resolved_root = resolve_target_root(action, project_map, default_root)
    dispatch = {
        "create_skill": _apply_create_file,
        "create_agent": _apply_create_file,
        "merge_skill": _apply_merge_file,
        "refine_skill": _apply_refine_file,
        "refine_agent": _apply_refine_file,
        "add_rule": _apply_rule,
        "reasoning_rule": _apply_rule,
    }
    handler = dispatch.get(action.action_type)
    if handler:
        handler(action, resolved_root)
    else:
        _logger.warning(
            t("enhancer.unknown_action", action_type=action.action_type),
        )


def resolve_target_root(
    action: PendingAction,
    project_map: dict[str, str],
    default_root: Path,
) -> Path:
    """action의 target_project 메타데이터를 기반으로 대상 프로젝트 루트를 결정한다."""
    target_name = extract_target_project(action)
    if target_name and target_name in project_map:
        return Path(project_map[target_name])
    return default_root


def extract_target_project(action: PendingAction) -> str:
    """pending 파일의 frontmatter에서 target_project 값을 추출한다."""
    try:
        text = action.file_path.read_text(encoding="utf-8")
    except OSError:
        return ""
    meta, _ = parse_frontmatter(text)
    return meta.get("target_project", "")


def resolve_target_path(
    action: PendingAction,
    project_map: dict[str, str],
    default_root: Path,
) -> Path | None:
    """action에서 실제 적용 대상 파일 경로를 도출한다."""
    root = resolve_target_root(action, project_map, default_root)
    if action.action_type in (
        "create_skill", "merge_skill", "refine_skill",
    ):
        return root / ".claude" / "skills" / f"{action.name}.md"
    if action.action_type in ("create_agent", "refine_agent"):
        return root / ".claude" / "agents" / f"{action.name}.md"
    if action.action_type in ("add_rule", "reasoning_rule"):
        return root / "CLAUDE.md"
    return None


# ------------------------------------------------------------------
# 파일 적용 핸들러
# ------------------------------------------------------------------

def _apply_create_file(
    action: PendingAction, target_root: Path,
) -> None:
    """skill 또는 agent 파일을 생성한다."""
    subdir = _resolve_subdir(action.action_type)
    target_dir = target_root / ".claude" / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{action.name}.md"
    _preserve_existing(target_path)
    target_path.write_text(action.content, encoding="utf-8")


def _apply_refine_file(
    action: PendingAction, target_root: Path,
) -> None:
    """기존 skill/agent를 진화(evolution)시킨다."""
    subdir = _resolve_subdir(action.action_type)
    target_path = target_root / ".claude" / subdir / f"{action.name}.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    _preserve_existing(target_path)
    target_path.write_text(action.content, encoding="utf-8")
    _logger.info(t("enhancer.skill_evolve", name=action.name))


def _apply_merge_file(
    action: PendingAction, target_root: Path,
) -> None:
    """기존 skill 파일에 내용을 추가(merge)한다."""
    target_path = target_root / ".claude" / "skills" / f"{action.name}.md"
    if not target_path.exists():
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(action.content, encoding="utf-8")
        return
    _preserve_existing(target_path)
    existing = target_path.read_text(encoding="utf-8")
    merged = existing.rstrip() + "\n\n" + action.content
    target_path.write_text(merged, encoding="utf-8")


def _apply_rule(
    action: PendingAction, target_root: Path,
) -> None:
    """CLAUDE.md의 ## threadloom-rules 섹션에 규칙을 추가한다."""
    claude_md = target_root / "CLAUDE.md"
    if not claude_md.exists():
        _create_claude_md_with_rule(claude_md, action.content)
        return

    _preserve_existing(claude_md)
    text = claude_md.read_text(encoding="utf-8")
    updated = _insert_rule(text, action.content)
    claude_md.write_text(updated, encoding="utf-8")


# ------------------------------------------------------------------
# 헬퍼 함수
# ------------------------------------------------------------------

def _resolve_subdir(action_type: str) -> str:
    """action_type에서 하위 디렉토리(subdirectory)명을 추출한다."""
    if "agent" in action_type:
        return "agents"
    return "skills"


def _preserve_existing(path: Path) -> Path | None:
    """기존 파일을 .prev.md로 이름 변경하여 보존(preserve)한다."""
    if not path.exists():
        return None
    prev_path = path.with_suffix(".prev.md")
    if prev_path.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        prev_path = path.with_suffix(f".prev_{ts}.md")
    shutil.copy2(str(path), str(prev_path))
    _logger.info(t("enhancer.file_preserved", name=prev_path.name))
    return prev_path


# ------------------------------------------------------------------
# CLAUDE.md 규칙 관리
# ------------------------------------------------------------------

def _create_claude_md_with_rule(path: Path, content: str) -> None:
    """CLAUDE.md가 없을 때 규칙 섹션과 함께 새로 생성한다."""
    text = (
        f"\n{_RULES_HEADER}\n\n"
        f"{content}\n\n"
        f"{_RULES_END_MARKER}\n"
    )
    path.write_text(text, encoding="utf-8")


def _insert_rule(text: str, rule_content: str) -> str:
    """기존 CLAUDE.md에 threadloom-rules 섹션을 관리한다."""
    header_idx = text.find(_RULES_HEADER)
    if header_idx < 0:
        return _append_rules_section(text, rule_content)
    return _insert_into_existing_section(text, header_idx, rule_content)


def _append_rules_section(text: str, rule_content: str) -> str:
    """CLAUDE.md 끝에 threadloom-rules 섹션을 추가한다."""
    return (
        text.rstrip() + "\n\n"
        f"{_RULES_HEADER}\n\n"
        f"{rule_content}\n\n"
        f"{_RULES_END_MARKER}\n"
    )


def _insert_into_existing_section(
    text: str, header_idx: int, rule_content: str,
) -> str:
    """기존 threadloom-rules 섹션의 끝 마커(end marker) 앞에 규칙을 삽입한다."""
    marker_idx = text.find(_RULES_END_MARKER, header_idx)
    if marker_idx >= 0:
        return (
            text[:marker_idx].rstrip() + "\n\n"
            f"{rule_content}\n\n"
            f"{text[marker_idx:]}"
        )
    # 마커 없으면 다음 ## 섹션 또는 EOF 직전에 삽입
    section_end = _find_section_end(text, header_idx)
    return (
        text[:section_end].rstrip() + "\n\n"
        f"{rule_content}\n\n"
        f"{_RULES_END_MARKER}\n"
        f"{text[section_end:]}"
    )


def _find_section_end(text: str, header_idx: int) -> int:
    """현재 섹션의 끝 위치(다음 ## 헤딩 또는 EOF)를 찾는다."""
    next_heading = re.search(
        r"\n## ", text[header_idx + len(_RULES_HEADER):]
    )
    if next_heading:
        return header_idx + len(_RULES_HEADER) + next_heading.start()
    return len(text)
