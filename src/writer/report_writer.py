"""일일 리포트(daily report) 생성 모듈.

분석 결과와 강화 액션을 종합하여 Reports/threadloom/ 에 리포트를 저장한다.
"""

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from src.config import Config
from src.utils.i18n import t
from src.utils.logger import get_logger
from src.utils.paths import DATA_DIR
from src.utils.post_block_parser import parse_post_blocks
from src.utils.state import get_total_collected

_logger = get_logger("writer.report")


@dataclass(frozen=True)
class SummaryData:
    """리포트 요약(summary) 테이블 및 프론트매터(frontmatter) 생성에 필요한 데이터."""

    today: date
    run_at: str
    collected: int
    success: int
    fail: int
    new_count: int
    total: int


class ReportWriter:
    """일일 실행 리포트를 생성하는 작성기(writer)."""

    def __init__(self, config: Config) -> None:
        self._vault = Path(config.vault_path) if config.vault_path else None
        self._folders = config.obsidian_folders

    def write(
        self,
        analysis_md_path: Path,
        enhance_actions: list[dict] | None = None,
        obsidian_enabled: bool = False,
    ) -> Path:
        """리포트를 생성하고 저장 경로를 반환한다.

        Args:
            analysis_md_path: 분석 결과 md 경로
            enhance_actions: 강화(enhancement) 액션 목록
            obsidian_enabled: Obsidian vault에도 저장할지 여부
        """
        posts = self._parse_posts(analysis_md_path)
        enhance_actions = enhance_actions or []
        today = date.today()

        content = self._build_report(today, posts, enhance_actions)
        path = self._resolve_output_path(today, obsidian_enabled)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        _logger.info(t("writer.report_saved", name=path.name))
        return path

    # ------------------------------------------------------------------
    # 리포트 빌드(build)
    # ------------------------------------------------------------------

    def _build_report(
        self,
        today: date,
        posts: list[dict],
        enhance_actions: list[dict],
    ) -> str:
        """전체 리포트 콘텐츠를 조합한다."""
        now = datetime.now().strftime("%H:%M:%S")
        categories = self._count_categories(posts)
        success = sum(
            1 for p in posts if p.get("category", "other") != "other"
        )
        fail = len(posts) - success
        # 강화 액션(enhancement action) 필터: create_skill, create_agent, add_rule 등
        new_skills = [
            a for a in enhance_actions
            if a.get("action_type") != "raw_fallback"
        ]
        summary = SummaryData(
            today=today, run_at=now, collected=len(posts),
            success=success, fail=fail,
            new_count=len(new_skills), total=get_total_collected(),
        )

        lines = [
            self._build_frontmatter(summary),
            self._build_header(today),
            self._build_summary_table(summary),
            self._build_enhance_section(new_skills),
            self._build_category_table(categories),
            self._build_top_posts(posts),
            self._build_error_section(posts),
        ]
        return "\n".join(lines)

    def _build_frontmatter(self, data: SummaryData) -> str:
        """YAML frontmatter를 생성한다."""
        lines = [
            "---",
            f"date: {data.today.isoformat()}",
            f"run_at: {data.run_at}",
            f"collected: {data.collected}",
            f"new_enhancements: {data.new_count}",
            "---",
            "",
        ]
        return "\n".join(lines)

    def _build_header(self, today: date) -> str:
        """리포트 제목을 생성한다."""
        return f"# threadloom Report — {today.isoformat()}\n"

    def _build_summary_table(self, data: SummaryData) -> str:
        """실행 요약 테이블을 생성한다."""
        lines = [
            "## Summary",
            "",
            "| Item | Value |",
            "|------|-------|",
            f"| Collected posts | {data.collected} |",
            f"| Classified | {data.success} |",
            f"| Unclassified | {data.fail} (saved as other) |",
            f"| New enhancements | {data.new_count} |",
            f"| Total collected | {data.total} |",
            "",
        ]
        return "\n".join(lines)

    def _build_enhance_section(
        self, new_skills: list[dict],
    ) -> str:
        """신규 강화(enhancement) 등록 섹션을 생성한다."""
        if not new_skills:
            return "## New Enhancements\n\n(none)\n"

        lines = ["## New Enhancements", ""]
        for skill in new_skills:
            name = skill.get("name", "unknown")
            reason = skill.get("reason", "")
            lines.append(f"### {name}")
            lines.append(f"- **Reason**: {reason}")
            lines.append("")
        return "\n".join(lines)

    def _build_category_table(
        self, categories: dict[str, int],
    ) -> str:
        """카테고리 분포 테이블을 생성한다."""
        lines = [
            "## Category Distribution",
            "",
            "| Category | Count |",
            "|----------|-------|",
        ]
        for cat, count in sorted(
            categories.items(), key=lambda x: -x[1],
        ):
            lines.append(f"| {cat} | {count} |")
        lines.append("")
        return "\n".join(lines)

    def _build_top_posts(self, posts: list[dict]) -> str:
        """유용성(relevance) 기준 상위 3개 포스트를 표시한다."""
        scored = self._sort_by_relevance(posts)
        top3 = scored[:3]

        if not top3:
            return "## Top 3 Posts\n\n(none)\n"

        lines = ["## Top 3 Posts", ""]
        for i, post in enumerate(top3, 1):
            author = post.get("author", "unknown")
            summary = post.get("summary", "")[:60]
            post_id = post.get("post_id", "unknown")
            lines.append(
                f"{i}. [@{author}] {summary} "
                f"→ [[archive/{post_id}]]",
            )
        lines.append("")
        return "\n".join(lines)

    def _build_error_section(self, posts: list[dict]) -> str:
        """분류 실패(기타) 포스트의 에러 로그 섹션."""
        errors = [
            p for p in posts if p.get("category", "other") == "other"
        ]
        if not errors:
            return "## Error Log\n\n(no errors)\n"

        lines = ["## Error Log", ""]
        for post in errors:
            post_id = post.get("post_id", "unknown")
            reason = post.get("reason", "classification failed")
            lines.append(f"- {post_id}: {reason}")
        lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 파싱 및 유틸리티
    # ------------------------------------------------------------------

    def _parse_posts(self, path: Path) -> list[dict]:
        """analysis md에서 포스트 목록을 추출한다."""
        text = path.read_text(encoding="utf-8")
        return parse_post_blocks(text)

    def _count_categories(self, posts: list[dict]) -> dict[str, int]:
        """카테고리(category)별 포스트 수를 집계한다."""
        counts: dict[str, int] = {}
        for post in posts:
            cat = post.get("category", "other")
            counts[cat] = counts.get(cat, 0) + 1
        return counts

    def _sort_by_relevance(self, posts: list[dict]) -> list[dict]:
        """유용성 점수(relevance score) 내림차순 정렬."""
        def score(post: dict) -> float:
            try:
                return float(post.get("relevance", "0.0"))
            except (ValueError, TypeError):
                return 0.0
        return sorted(posts, key=score, reverse=True)

    def _resolve_output_path(
        self, today: date, obsidian_enabled: bool,
    ) -> Path:
        """리포트 저장 경로를 결정한다."""
        if obsidian_enabled and self._vault:
            report_dir = self._vault / self._folders.get(
                "reports", "Reports/threadloom",
            )
        else:
            # Obsidian 미사용 시 프로젝트 data/ 하위에 저장
            report_dir = DATA_DIR / "reports"

        report_dir.mkdir(parents=True, exist_ok=True)
        return report_dir / f"{today.isoformat()}-report.md"
