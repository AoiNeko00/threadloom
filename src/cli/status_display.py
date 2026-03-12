"""상태 표시(status display) 모듈.

pending, applied, rejected 건수 조회 및 상태 출력을 담당한다.
강화 맵(enhancement map) 집계 및 출력도 담당한다.
"""

import json
import re
from pathlib import Path

from rich.console import Console
from rich.table import Table

from src.utils.frontmatter import normalize_name, parse_frontmatter
from src.utils.i18n import t
from src.utils.paths import ENHANCE_LOG, PENDING_DIR, REJECTED_DIR

# 중앙 경로(centralized path) 모듈에서 가져옴
_PENDING_DIR: Path = PENDING_DIR
_REJECTED_DIR: Path = REJECTED_DIR
_ENHANCE_LOG: Path = ENHANCE_LOG

_console = Console()


def count_pending() -> int:
    """pending 파일 개수를 반환한다."""
    if not _PENDING_DIR.is_dir():
        return 0
    return len(list(_PENDING_DIR.glob("*.md")))


def count_applied() -> int:
    """enhance_log.json에서 적용(applied) 건수를 반환한다."""
    if not _ENHANCE_LOG.exists():
        return 0
    try:
        data = json.loads(_ENHANCE_LOG.read_text(encoding="utf-8"))
        return sum(1 for e in data if e.get("result") == "applied")
    except (json.JSONDecodeError, OSError):
        return 0


def count_rejected() -> int:
    """rejected 파일 개수를 반환한다."""
    if not _REJECTED_DIR.is_dir():
        return 0
    return len(list(_REJECTED_DIR.glob("*.md")))


def print_pending_list() -> None:
    """대기 중인 pending 항목을 간략히 출력한다."""
    if not _PENDING_DIR.is_dir():
        return
    for md_file in sorted(_PENDING_DIR.glob("*.md")):
        name = md_file.stem
        # action_type과 name 분리: "create_skill_foo" -> "[create_skill] foo"
        parts = name.split("_", 2)
        if len(parts) >= 3:
            _console.print(f"  - [{parts[0]}_{parts[1]}] {parts[2]}")
        else:
            _console.print(f"  - {name}")


def _extract_domain(name: str, meta: dict) -> str:
    """파일명 또는 frontmatter에서 분야(domain)를 추출한다.

    tags가 있으면 첫 번째 태그를 사용하고,
    없으면 파일명의 첫 단어(언더스코어 기준)를 휴리스틱으로 사용한다.
    """
    tags = meta.get("tags", [])
    if isinstance(tags, list) and tags:
        return str(tags[0]).lower()
    # 파일명 첫 단어(first word) 휴리스틱
    first = name.split("_")[0] if "_" in name else name
    return first.lower()


def _scan_dir(
    directory: Path, kind: str, result: dict[str, dict[str, int]],
) -> None:
    """디렉토리 내 md 파일을 스캔하여 분야별 집계에 추가한다.

    .prev.md 백업(backup) 파일은 제외한다.
    """
    if not directory.is_dir():
        return
    for md in directory.glob("*.md"):
        if ".prev" in md.name:
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        meta, _ = parse_frontmatter(text)
        domain = _extract_domain(md.stem, meta)
        result.setdefault(domain, {})
        result[domain][kind] = result[domain].get(kind, 0) + 1


def _scan_rules(
    claude_md: Path, result: dict[str, dict[str, int]],
) -> None:
    """CLAUDE.md의 threadloom-rules 섹션에서 규칙을 집계한다."""
    try:
        text = claude_md.read_text(encoding="utf-8")
    except OSError:
        return
    section_match = re.search(
        r"^## threadloom-rules\s*\n(.*?)(?=\n## |\Z)",
        text,
        re.DOTALL | re.MULTILINE,
    )
    if not section_match:
        return
    section = section_match.group(1)
    for header in re.findall(r"^### (.+)", section, re.MULTILINE):
        # 전체 헤더를 정규화(normalize)하여 도메인 추출
        normalized = normalize_name(header)
        domain = normalized.split("_")[0]
        if domain:
            result.setdefault(domain, {})
            result[domain]["rule"] = result[domain].get("rule", 0) + 1


def build_enhancement_map(
    target_root: Path,
) -> dict[str, dict[str, int]]:
    """대상 프로젝트의 강화 분포(enhancement map)를 분야별로 집계한다.

    Returns: {"testing": {"skill": 2, "agent": 1}, "security": {"skill": 1}, ...}
    """
    result: dict[str, dict[str, int]] = {}
    claude_dir = target_root / ".claude"

    # skills 스캔(scan) — .prev.md 백업 파일 제외
    _scan_dir(claude_dir / "skills", "skill", result)

    # agents 스캔(scan) — .prev.md 백업 파일 제외
    _scan_dir(claude_dir / "agents", "agent", result)

    # CLAUDE.md threadloom-rules 섹션의 ### 헤더로 규칙(rule) 집계
    _scan_rules(target_root / "CLAUDE.md", result)

    return result


def print_enhancement_map(target_root: Path) -> None:
    """강화 맵(enhancement map)을 rich 테이블로 출력한다."""
    emap = build_enhancement_map(target_root)
    if not emap:
        return

    table = Table(title=t("status.enhancement_map_title"))
    table.add_column(t("status.col_domain"), style="cyan")
    table.add_column("Skills", justify="right")
    table.add_column("Agents", justify="right")
    table.add_column("Rules", justify="right")
    table.add_column(t("status.col_total"), justify="right", style="bold")

    # 합계(total) 내림차순 정렬
    sorted_domains = sorted(
        emap.items(),
        key=lambda x: sum(x[1].values()),
        reverse=True,
    )

    for domain, counts in sorted_domains:
        skills = counts.get("skill", 0)
        agents = counts.get("agent", 0)
        rules = counts.get("rule", 0)
        total = skills + agents + rules
        table.add_row(
            domain,
            str(skills) if skills else "-",
            str(agents) if agents else "-",
            str(rules) if rules else "-",
            str(total),
        )

    _console.print()
    _console.print(table)


def extract_rejected_meta(path: Path) -> tuple[str, str]:
    """rejected md의 frontmatter에서 name과 rejection_reason을 추출한다."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return path.stem, t("status.read_error")
    meta, _ = parse_frontmatter(text)
    if not meta:
        return path.stem, t("status.no_frontmatter")
    name = meta.get("name", path.stem)
    reason = meta.get("rejection_reason", t("status.no_reason"))
    return name, reason
