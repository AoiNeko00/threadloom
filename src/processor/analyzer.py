"""Phase 2 분석(analysis) 모듈.

raw md를 AI CLI 1회 호출로 분석하여 analysis md로 저장한다.
"""

import re
from datetime import datetime, timezone
from pathlib import Path

from src.ai_adapter.base import BaseAIAdapter
from src.processor.context_builder import ContextBuilder
from src.utils.i18n import t
from src.utils.logger import get_logger
from src.utils.paths import ANALYSIS_DIR

_logger = get_logger("analyzer")

# 중앙 경로(centralized path) 모듈에서 가져옴
_ANALYSIS_DIR: Path = ANALYSIS_DIR

# 분석 결과에 반드시 포함되어야 하는 섹션(section) 패턴
# AI 응답 언어에 따라 영어/한국어 모두 허용
_REQUIRED_PATTERNS: list[list[str]] = [
    [r"##\s+post-[\w]+"],
    [r"Enhancement Proposal Summary", r"강화 제안 요약"],
]


class Analyzer:
    """raw md를 AI로 분석하여 analysis md를 생성한다."""

    def __init__(
        self,
        adapter: BaseAIAdapter,
        context_builder: ContextBuilder,
    ) -> None:
        self._adapter = adapter
        self._context = context_builder

    def analyze(self, raw_md_path: Path) -> Path:
        """Phase 2 실행: raw md -> analysis md 저장 -> 경로 반환."""
        summary = self._context.build_summary()
        _logger.info(t("processor.context_done"))

        content = self._call_ai(raw_md_path, summary)
        output_path = self._resolve_output_path(raw_md_path)
        self._save(output_path, content)
        _logger.info(t("processor.analysis_saved", path=str(output_path)))
        return output_path

    # ------------------------------------------------------------------
    # AI 호출 + 검증
    # ------------------------------------------------------------------

    def _call_ai(self, raw_md_path: Path, summary: str) -> str:
        """AI 어댑터(adapter) 호출 후 검증, 실패 시 폴백(fallback)."""
        try:
            result = self._adapter.analyze(raw_md_path, summary)
        except Exception:
            _logger.exception(t("analyzer.ai_call_failed"))
            return self._fallback_analysis(raw_md_path)

        if self._validate_analysis(result):
            return result

        _logger.warning(t("processor.analysis_verify_fail"))
        return self._fallback_analysis(raw_md_path)

    def _validate_analysis(self, content: str) -> bool:
        """분석 결과가 필수 섹션을 포함하는지 검증한다.

        각 그룹(group) 내 패턴 중 하나라도 매칭되면 통과.
        """
        for alternatives in _REQUIRED_PATTERNS:
            if not any(re.search(p, content) for p in alternatives):
                return False
        return True

    def _fallback_analysis(self, raw_md_path: Path) -> str:
        """AI 실패 시 모든 포스트를 category: 기타로 처리한다."""
        raw_text = raw_md_path.read_text(encoding="utf-8")
        posts = self._extract_post_ids(raw_text)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        lines = [
            "---",
            f"source: {raw_md_path.name}",
            f"analyzed_at: {now}",
            f"total: {len(posts)}",
            "actionable: 0",
            "enhance_candidates: 0",
            "---",
            "",
            f"# Analysis Results (fallback) — {now[:10]}",
            "",
        ]
        for pid in posts:
            lines.extend(self._fallback_post_block(pid))

        lines.extend(self._fallback_summary_table())
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 포스트 ID 추출 및 폴백 블록 생성
    # ------------------------------------------------------------------

    def _extract_post_ids(self, raw_text: str) -> list[str]:
        """raw md에서 `## post-NNN` 형식의 ID를 추출한다."""
        return re.findall(r"^##\s+(post-\d+)", raw_text, re.MULTILINE)

    def _fallback_post_block(self, post_id: str) -> list[str]:
        """폴백용 단일 포스트 분석 블록을 생성한다.

        AI 프롬프트 출력 형식(output format)과 동일한 영문 필드명 사용.
        """
        return [
            f"## {post_id}",
            "- **Classification**: other",
            "- **Tags**: [other]",
            "- **Summary**: Auto-classified due to AI analysis failure",
            "- **Relevance**: 0.0",
            "- **Actionable**: false",
            "- **Enhancement type**: none",
            "- **Proposed name**:",
            "- **Reasoning**: AI call failed or validation did not pass",
            "",
            "---",
            "",
        ]

    def _fallback_summary_table(self) -> list[str]:
        """폴백용 강화 제안 요약 테이블(빈 테이블)을 생성한다."""
        return [
            "## Enhancement Proposal Summary",
            "",
            "| # | Type | Name | Source Posts | Score |",
            "|---|------|------|-------------|-------|",
            "",
        ]

    # ------------------------------------------------------------------
    # 파일 저장
    # ------------------------------------------------------------------

    def _resolve_output_path(self, raw_md_path: Path) -> Path:
        """analysis 파일 경로를 결정한다. 중복 시 접미사(suffix) 추가."""
        _ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
        base_name = raw_md_path.stem
        candidate = _ANALYSIS_DIR / f"{base_name}.md"
        counter = 1
        while candidate.exists():
            candidate = _ANALYSIS_DIR / f"{base_name}_{counter}.md"
            counter += 1
        return candidate

    def _save(self, path: Path, content: str) -> None:
        """분석 결과를 UTF-8로 저장한다."""
        path.write_text(content, encoding="utf-8")
