"""Phase 3→4 자동 심사(auto-review) 모듈.

AI 호출 없이 규칙 기반으로 pending 강화 항목을 심사한다.
냉철하고 보수적인 기준: 의심스러우면 거부한다.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from src.config import Config
from src.enhancer.reviewer_config import (
    META_RESPONSE_PATTERNS,
    STRONG_EXPRESSIONS,
    WEAK_EXPRESSIONS,
)
from src.enhancer.stack_detector import detect_stacks, extract_mentioned_stacks
from src.utils.frontmatter import parse_frontmatter, set_frontmatter_field
from src.utils.i18n import t
from src.utils.logger import get_logger
from src.utils.paths import PENDING_DIR, REJECTED_DIR

_logger = get_logger("reviewer")

# 중앙 경로(centralized path) 모듈에서 가져옴
_PENDING_DIR = PENDING_DIR
_REJECTED_DIR = REJECTED_DIR


@dataclass
class ReviewResult:
    """심사 결과."""

    approved: list[Path]
    rejected: list[tuple[Path, str]]  # (경로, 거부 사유)


class EnhancementReviewer:
    """규칙 기반 자동 심사(auto-review) 엔진."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._target_root = Path(config.target_project_path)
        self._reviewer_config = config.data.get("reviewer", {})
        self._min_relevance = self._reviewer_config.get(
            "min_relevance_score", 0.7,
        )
        self._max_pending = self._reviewer_config.get(
            "max_pending_items", 20,
        )
        self._reject_generic = self._reviewer_config.get(
            "reject_generic_advice", True,
        )

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def review(self, pending_paths: list[Path]) -> ReviewResult:
        """pending 파일들을 심사하여 통과/거부 분류한다."""
        _REJECTED_DIR.mkdir(parents=True, exist_ok=True)

        target_stacks = detect_stacks(self._target_root)
        existing_names = self._collect_existing_names()

        approved: list[Path] = []
        rejected: list[tuple[Path, str]] = []

        items = self._load_items(pending_paths)

        for path, meta, body in items:
            reason = self._evaluate(
                path, meta, body, target_stacks, existing_names,
            )
            if reason:
                self._reject_file(path, reason)
                rejected.append((path, reason))
            else:
                approved.append(path)

        # 배치 내 중복 제거(batch dedup)
        approved, batch_rejected = self._dedup_batch(approved)
        rejected.extend(batch_rejected)

        self._log_summary(approved, rejected)
        return ReviewResult(approved=approved, rejected=rejected)

    # ------------------------------------------------------------------
    # 내부: 파일 로드
    # ------------------------------------------------------------------

    def _load_items(
        self, paths: list[Path],
    ) -> list[tuple[Path, dict, str]]:
        """pending 파일들의 frontmatter와 본문(body)을 로드한다."""
        items: list[tuple[Path, dict, str]] = []
        for path in paths:
            meta, body = self._parse_file(path)
            items.append((path, meta, body))
        return items

    def _parse_file(self, path: Path) -> tuple[dict, str]:
        """pending md에서 frontmatter와 본문을 분리한다."""
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return {}, ""
        return parse_frontmatter(text)

    # ------------------------------------------------------------------
    # 내부: 종합 평가(evaluation)
    # ------------------------------------------------------------------

    def _evaluate(
        self,
        path: Path,
        meta: dict,
        body: str,
        target_stacks: set[str],
        existing_names: set[str],
    ) -> str | None:
        """단일 항목을 종합 심사한다. 거부 사유 또는 None(통과) 반환."""
        # Hard reject 검사
        reason = self._check_hard_reject(meta, body)
        if reason:
            return reason

        # 관련성 필터(relevance filter)
        reason = self._check_relevance(meta, body, target_stacks)
        if reason:
            return reason

        # 품질 게이트(quality gate)
        reason = self._check_quality(meta, body)
        if reason:
            return reason

        # 중복 검사(dedup) — 기존 파일 대비
        reason = self._check_duplicate(meta, existing_names)
        if reason:
            return reason

        return None

    # ------------------------------------------------------------------
    # 내부: Hard Reject
    # ------------------------------------------------------------------

    def _check_hard_reject(self, meta: dict, body: str) -> str | None:
        """즉시 거부(hard reject) 조건을 확인한다."""
        # raw_fallback 항목
        if meta.get("action_type") == "raw_fallback":
            return "hard_reject: raw_fallback 항목"

        # frontmatter 필수 필드 누락
        if "action_type" not in meta:
            return "hard_reject: action_type 누락"
        if "name" not in meta:
            return "hard_reject: name 누락"

        # 내용 100자 미만
        full_content = body.strip()
        if len(full_content) < 100:
            return f"hard_reject: 내용 {len(full_content)}자 (최소 100자)"

        # AI 메타 응답 감지
        if self._has_meta_response(body):
            return "hard_reject: AI 메타 응답 감지"

        return None

    def _has_meta_response(self, body: str) -> bool:
        """AI의 권한 요청/메타 응답 패턴을 감지한다."""
        for pattern in META_RESPONSE_PATTERNS:
            if re.search(pattern, body, re.IGNORECASE):
                return True
        return False

    # ------------------------------------------------------------------
    # 내부: 관련성 필터(relevance filter)
    # ------------------------------------------------------------------

    def _check_relevance(
        self, meta: dict, body: str, target_stacks: set[str],
    ) -> str | None:
        """대상 프로젝트 기술 스택과의 관련성을 검사한다."""
        if not target_stacks:
            # 기술 스택 감지 불가 시 필터 건너뜀
            return None

        content_lower = body.lower()
        name_lower = meta.get("name", "").lower()
        combined = f"{name_lower} {content_lower}"

        # 내용에서 언급된 기술 스택 추출
        mentioned_stacks = extract_mentioned_stacks(combined)

        # 언급된 스택이 없으면 통과 (범용 강화일 수 있음)
        if not mentioned_stacks:
            return None

        # 대상 스택과 교집합이 있으면 통과
        if mentioned_stacks & target_stacks:
            return None

        return (
            f"relevance_filter: 기술 스택 불일치 "
            f"(대상: {sorted(target_stacks)}, "
            f"내용: {sorted(mentioned_stacks)})"
        )

    # ------------------------------------------------------------------
    # 내부: 품질 게이트(quality gate)
    # ------------------------------------------------------------------

    def _check_quality(self, meta: dict, body: str) -> str | None:
        """품질 점수(quality score)를 계산하여 기준 미달 시 거부한다."""
        # frontmatter에 relevance_score가 있으면 기본 점수로 사용
        base_score = float(meta.get("relevance_score", 0.7))

        # 0.7 미만이면 즉시 거부
        if base_score < self._min_relevance:
            return (
                f"quality_gate: relevance_score {base_score:.2f} "
                f"(최소 {self._min_relevance})"
            )

        # 약한/강한 표현 가감점(bonus/penalty) 적용
        score = base_score
        score = self._apply_expression_scoring(body, score)

        # 최종 점수 0.6 미만 거부
        if score < 0.6:
            return f"quality_gate: 최종 점수 {score:.2f} (최소 0.6)"

        return None

    def _apply_expression_scoring(self, body: str, score: float) -> float:
        """약한/강한 표현 가감점을 적용한다."""
        for expr in WEAK_EXPRESSIONS:
            if expr in body:
                score -= 0.05
        for expr in STRONG_EXPRESSIONS:
            if expr in body:
                score += 0.05
        return score

    # ------------------------------------------------------------------
    # 내부: 중복 검사(dedup)
    # ------------------------------------------------------------------

    def _check_duplicate(
        self, meta: dict, existing_names: set[str],
    ) -> str | None:
        """기존 skill/agent/rule과의 중복을 검사한다.

        refine 액션은 기존 파일을 발전시키므로 중복 검사를 건너뛴다.
        """
        action_type = meta.get("action_type", "")
        if action_type.startswith("refine"):
            return None
        name = meta.get("name", "")
        if not name:
            return None
        if name in existing_names:
            return f"dedup: 동일 이름 '{name}' 이미 존재"
        return None

    def _collect_existing_names(self) -> set[str]:
        """대상 프로젝트의 기존 skill/agent 이름을 수집한다."""
        names: set[str] = set()
        for subdir in ("skills", "agents"):
            directory = self._target_root / ".claude" / subdir
            if not directory.is_dir():
                continue
            for md_file in directory.glob("*.md"):
                names.add(md_file.stem)

        # CLAUDE.md threadloom-rules에서 규칙 이름도 수집
        self._collect_rule_names(names)
        return names

    def _collect_rule_names(self, names: set[str]) -> None:
        """CLAUDE.md의 threadloom-rules 섹션에서 규칙 이름을 추출한다."""
        claude_md = self._target_root / "CLAUDE.md"
        if not claude_md.is_file():
            return
        try:
            text = claude_md.read_text(encoding="utf-8")
        except OSError:
            return
        # ### 규칙이름 패턴으로 추출
        for match in re.finditer(r"###\s+(.+)", text):
            rule_name = match.group(1).strip().lower()
            # snake_case 변환
            normalized = re.sub(r"[^a-z0-9가-힣]+", "_", rule_name).strip("_")
            if normalized:
                names.add(normalized)

    # ------------------------------------------------------------------
    # 내부: 배치 내 중복 제거(batch dedup)
    # ------------------------------------------------------------------

    def _dedup_batch(
        self, approved: list[Path],
    ) -> tuple[list[Path], list[tuple[Path, str]]]:
        """같은 배치 내에서 중복 주제(duplicate topic)를 제거한다.

        동일 이름이 있으면 relevance_score가 높은 것만 유지한다.
        """
        by_name: dict[str, list[tuple[Path, float]]] = {}
        for path in approved:
            meta, _ = self._parse_file(path)
            name = meta.get("name", path.stem)
            score = float(meta.get("relevance_score", 0.5))
            by_name.setdefault(name, []).append((path, score))

        kept: list[Path] = []
        rejected: list[tuple[Path, str]] = []
        for name, entries in by_name.items():
            if len(entries) <= 1:
                kept.append(entries[0][0])
                continue
            # 점수 내림차순(descending) 정렬, 최고점만 유지
            entries.sort(key=lambda x: x[1], reverse=True)
            kept.append(entries[0][0])
            for path, score in entries[1:]:
                reason = f"batch_dedup: 동일 이름 '{name}' 중복 (하위 점수)"
                self._reject_file(path, reason)
                rejected.append((path, reason))

        return kept, rejected

    # ------------------------------------------------------------------
    # 내부: 거부 처리
    # ------------------------------------------------------------------

    def _reject_file(self, path: Path, reason: str) -> None:
        """pending 파일을 rejected/ 로 이동하고 거부 사유를 frontmatter에 추가한다."""
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            _logger.warning(t("enhancer.reject_read_fail", name=path.name))
            return

        updated = self._add_rejection_to_frontmatter(text, reason)
        dest = _REJECTED_DIR / path.name
        dest.write_text(updated, encoding="utf-8")

        path.unlink(missing_ok=True)
        _logger.info(t("enhancer.reject_log", name=path.name, reason=reason))

    def _add_rejection_to_frontmatter(
        self, text: str, reason: str,
    ) -> str:
        """frontmatter에 rejection_reason 필드를 추가한다."""
        return set_frontmatter_field(text, "rejection_reason", f'"{reason}"')

    # ------------------------------------------------------------------
    # 내부: 요약 로그
    # ------------------------------------------------------------------

    def _log_summary(
        self,
        approved: list[Path],
        rejected: list[tuple[Path, str]],
    ) -> None:
        """심사 결과 요약을 로그에 출력한다."""
        total = len(approved) + len(rejected)
        _logger.info(
            t("enhancer.review_summary",
              total=total, approved=len(approved), rejected=len(rejected)),
        )
        for path, reason in rejected:
            _logger.info(
                t("enhancer.reject_detail", name=path.name, reason=reason),
            )
