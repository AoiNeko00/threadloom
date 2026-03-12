"""기존 .claude/ 설정을 AI 컨텍스트(context)용 요약 텍스트로 빌드하는 모듈.

Phase 2에서 AI가 기존 설정을 인지하여 중복 없는 판단을 할 수 있도록 한다.
"""

import re
from pathlib import Path

from src.utils.i18n import t
from src.utils.logger import get_logger

_logger = get_logger("context_builder")


class ContextBuilder:
    """대상 프로젝트의 .claude/ 설정을 스캔하여 요약한다."""

    def __init__(self, target_project_path: str) -> None:
        self._root = Path(target_project_path)
        self._claude_dir = self._root / ".claude"

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def build_summary(self) -> str:
        """기존 skills, agents, rules를 요약 텍스트로 반환한다."""
        skills = self._scan_descriptions(self._claude_dir / "skills")
        agents = self._scan_descriptions(self._claude_dir / "agents")
        rules = self._extract_rules()

        parts: list[str] = [
            self._format_section("Skills", skills),
            self._format_section("Agents", agents),
            self._format_rules_section(rules),
        ]
        return "\n\n".join(parts)

    def collect_existing_files(self) -> dict[str, str]:
        """기존 파일 전문을 dict로 반환한다 (Phase 3 중복 검사용)."""
        files: dict[str, str] = {}
        self._collect_md_dir(self._claude_dir / "skills", files)
        self._collect_md_dir(self._claude_dir / "agents", files)
        self._collect_claude_md(files)
        return files

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _scan_descriptions(self, directory: Path) -> list[tuple[str, str]]:
        """디렉토리 내 .md 파일의 frontmatter(프론트매터)에서 description 추출."""
        if not directory.is_dir():
            return []
        results: list[tuple[str, str]] = []
        for md_file in sorted(directory.glob("*.md")):
            desc = self._extract_frontmatter_field(md_file, "description")
            name = md_file.stem
            results.append((name, desc or "(no description)"))
        return results

    def _extract_frontmatter_field(self, path: Path, field: str) -> str | None:
        """YAML frontmatter에서 특정 필드(field) 값을 추출한다."""
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            _logger.warning(t("processor.file_read_fail", path=str(path)))
            return None
        match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if not match:
            return None
        for line in match.group(1).splitlines():
            if line.startswith(f"{field}:"):
                return line.split(":", 1)[1].strip()
        return None

    def _extract_rules(self) -> list[str]:
        """CLAUDE.md에서 주요 규칙 항목(rule items)을 추출한다."""
        claude_md = self._root / "CLAUDE.md"
        if not claude_md.is_file():
            return []
        try:
            text = claude_md.read_text(encoding="utf-8")
        except OSError:
            _logger.warning(t("processor.claude_md_fail"))
            return []
        return self._parse_rule_lines(text)

    def _parse_rule_lines(self, text: str) -> list[str]:
        """마크다운 텍스트에서 규칙성 bullet 항목을 추출한다."""
        rules: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("- ") and len(stripped) > 4:
                rules.append(stripped[2:])
        return rules[:20]  # 상위 20개로 제한하여 컨텍스트 과적 방지

    def _format_section(
        self, label: str, items: list[tuple[str, str]]
    ) -> str:
        """## 기존 {label} 섹션 텍스트를 생성한다."""
        header = f"## Existing {label} ({len(items)})"
        if not items:
            return f"{header}\n(none)"
        lines = [f"- {name}: {desc}" for name, desc in items]
        return f"{header}\n" + "\n".join(lines)

    def _format_rules_section(self, rules: list[str]) -> str:
        """## 기존 Rules 섹션 텍스트를 생성한다."""
        header = "## Existing Rules (from CLAUDE.md)"
        if not rules:
            return f"{header}\n(none)"
        lines = [f"- {r}" for r in rules]
        return f"{header}\n" + "\n".join(lines)

    def _collect_md_dir(self, directory: Path, out: dict[str, str]) -> None:
        """디렉토리 내 .md 파일을 상대경로 키로 dict에 수집한다."""
        if not directory.is_dir():
            return
        for md_file in sorted(directory.glob("*.md")):
            rel = str(md_file.relative_to(self._root))
            try:
                out[rel] = md_file.read_text(encoding="utf-8")
            except OSError:
                _logger.warning(t("processor.file_read_fail", path=str(md_file)))

    def _collect_claude_md(self, out: dict[str, str]) -> None:
        """CLAUDE.md 전문을 dict에 추가한다."""
        claude_md = self._root / "CLAUDE.md"
        if not claude_md.is_file():
            return
        try:
            out["CLAUDE.md"] = claude_md.read_text(encoding="utf-8")
        except OSError:
            _logger.warning(t("processor.claude_md_fail"))
