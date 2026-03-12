"""Phase 3: 분석 결과를 기반으로 강화(enhancement) 초안을 생성하는 모듈.

AI CLI를 1회 호출하여 skill/agent/rule 초안을 한번에 생성하고,
파싱하여 data/pending/ 에 개별 md 파일로 저장한다.
"""

import re
from datetime import datetime
from pathlib import Path

from src.ai_adapter.base import BaseAIAdapter
from src.config import Config
from src.enhancer.response_parser import parse_response
from src.processor.context_builder import ContextBuilder
from src.utils.i18n import t
from src.utils.logger import get_logger
from src.utils.paths import PENDING_DIR

_logger = get_logger("generator")

# 중앙 경로(centralized path) 모듈에서 가져옴
_PENDING_DIR = PENDING_DIR


class EnhancementGenerator:
    """Phase 3: 분석 결과 -> AI 1회 호출 -> 강화 초안 생성."""

    def __init__(
        self,
        adapter: BaseAIAdapter,
        context_builder: ContextBuilder,
        config: Config,
    ) -> None:
        self._adapter = adapter
        self._context_builder = context_builder
        self._config = config

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def generate(self, analysis_md_path: Path) -> list[Path]:
        """Phase 3 실행: 분석 md -> 강화 초안 생성 -> pending 파일 저장.

        Returns:
            저장된 pending 파일 경로 리스트 (강화 제안 없으면 빈 리스트)
        """
        if not self._has_enhancement_proposals(analysis_md_path):
            _logger.info(t("enhancer.no_proposals"))
            return []

        existing_files = self._context_builder.collect_existing_files()
        _logger.info(t("enhancer.existing_collected", n=len(existing_files)))

        response = self._call_ai(analysis_md_path, existing_files)
        if not response:
            return []

        return self._process_response(
            response, analysis_md_path, existing_files,
        )

    def generate_dry_run(self, analysis_md_path: Path) -> str:
        """dry-run용: 파일 저장 없이 콘솔 출력용 요약 문자열 반환."""
        parsed = self.generate_dry_run_parsed(analysis_md_path)
        if isinstance(parsed, str):
            return parsed
        return self._build_dry_run_summary(parsed)

    def generate_dry_run_parsed(
        self, analysis_md_path: Path,
    ) -> list[dict] | str:
        """dry-run용: 파싱된 결과 리스트를 반환한다.

        실패 시 에러 메시지 문자열(str)을 반환한다.
        """
        if not self._has_enhancement_proposals(analysis_md_path):
            return t("enhancer.no_proposals_short")

        existing_files = self._context_builder.collect_existing_files()
        response = self._call_ai(analysis_md_path, existing_files)
        if not response:
            return t("enhancer.ai_no_response")

        parsed = self._parse_response(response)
        if not parsed:
            corrected = self._retry_with_correction(response)
            if corrected:
                return corrected
            return t("enhancer.parse_fail_raw", n=len(response))

        return parsed

    # ------------------------------------------------------------------
    # 내부: 강화 제안 존재 확인
    # ------------------------------------------------------------------

    def _has_enhancement_proposals(self, analysis_md_path: Path) -> bool:
        """analysis md에 '강화 제안 요약' 섹션이 있고 내용이 있는지 확인."""
        try:
            text = analysis_md_path.read_text(encoding="utf-8")
        except OSError:
            _logger.error(
                t("enhancer.analysis_read_fail", path=analysis_md_path),
            )
            return False
        return self._check_proposal_section(text)

    def _check_proposal_section(self, text: str) -> bool:
        """'Enhancement Proposal Summary' 섹션에 테이블 행이 존재하는지 확인."""
        # 영어/한국어 프롬프트 모두 대응
        idx = -1
        for heading in ("Enhancement Proposal Summary", "강화 제안 요약"):
            idx = text.find(heading)
            if idx >= 0:
                break
        if idx < 0:
            return False
        section = text[idx:]
        # 테이블 데이터 행(data row) 확인: | 숫자 |
        return bool(re.search(r"\|\s*\d+\s*\|", section))

    # ------------------------------------------------------------------
    # 내부: AI 호출
    # ------------------------------------------------------------------

    def _call_ai(
        self, analysis_md_path: Path, existing_files: dict[str, str]
    ) -> str | None:
        """AI CLI를 호출하고 응답을 반환한다."""
        try:
            response = self._adapter.generate_enhancements(
                analysis_md_path, existing_files,
            )
            _logger.info(t("enhancer.ai_response", n=len(response)))
            return response
        except Exception:
            _logger.exception(t("enhancer.ai_call_fail"))
            return None

    # ------------------------------------------------------------------
    # 내부: 응답 처리
    # ------------------------------------------------------------------

    def _process_response(
        self,
        response: str,
        analysis_md_path: Path | None = None,
        existing_files: dict | None = None,
    ) -> list[Path]:
        """AI 응답을 파싱하고 pending 파일로 저장한다."""
        parsed = self._parse_response(response)
        if parsed:
            return self._write_pending(parsed)

        # 자기 수정(self-correction) 1회 시도
        corrected = self._retry_with_correction(response)
        if corrected:
            return self._write_pending(corrected)

        _logger.warning(t("enhancer.parse_fail_fallback"))
        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        return self._fallback_generation(response, timestamp)

    def _retry_with_correction(
        self, failed_response: str,
    ) -> list[dict] | None:
        """자기 수정(self-correction): 형식 오류 시 보정 프롬프트로 1회 재시도."""
        _logger.info(t("enhancer.self_correction"))
        # 원본 응답이 너무 길면 앞부분만 참고용으로 전달
        snippet = failed_response[:500]
        correction_prompt = (
            "Your previous response did not follow the required format.\n\n"
            "Problem: The ---THREADLOOM_FILE_START: xxx--- / "
            "---THREADLOOM_FILE_END--- delimiters were missing or "
            "malformed.\n\n"
            f"Previous response (for reference):\n{snippet}...\n\n"
            "Please regenerate the same analysis results in the correct format.\n"
            "Each file MUST start with "
            "---THREADLOOM_FILE_START: {action_type}_{name}--- "
            "and end with ---THREADLOOM_FILE_END---."
        )
        try:
            response = self._adapter.call_raw(correction_prompt)
        except Exception:
            _logger.warning(t("enhancer.self_correction_fail"))
            return None

        parsed = self._parse_response(response)
        if parsed:
            _logger.info(t("enhancer.self_correction_ok", n=len(parsed)))
            return parsed

        _logger.warning(t("enhancer.self_correction_final_fail"))
        return None

    def _parse_response(self, response: str) -> list[dict]:
        """AI 응답 파싱을 response_parser 모듈에 위임한다."""
        return parse_response(response)

    # ------------------------------------------------------------------
    # 내부: 파일 저장
    # ------------------------------------------------------------------

    def _write_pending(self, parsed_files: list[dict]) -> list[Path]:
        """파싱된 결과를 data/pending/ 에 개별 md 파일로 저장한다."""
        _PENDING_DIR.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for file_data in parsed_files:
            path = self._write_single_pending(file_data)
            paths.append(path)
            _logger.info(t("enhancer.pending_saved", name=path.name))
        return paths

    def _write_single_pending(self, file_data: dict) -> Path:
        """단일 pending 파일을 저장한다."""
        meta = file_data["metadata"]
        action_type = meta.get("action_type", "unknown")
        name = meta.get("name", "unnamed")
        filename = f"{action_type}_{name}.md"
        path = _PENDING_DIR / filename

        # 동일 파일명(filename) 충돌 방지
        path = self._resolve_conflict(path)
        path.write_text(file_data["content"], encoding="utf-8")
        return path

    def _resolve_conflict(self, path: Path) -> Path:
        """파일명 충돌 시 suffix(_1, _2 등)를 추가한다."""
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        counter = 1
        while path.exists():
            path = path.with_name(f"{stem}_{counter}{suffix}")
            counter += 1
        return path

    def _fallback_generation(self, response: str, timestamp: str) -> list[Path]:
        """파싱 실패 시 raw 응답을 fallback 파일로 저장한다.

        사용자가 --review에서 수동 검토 가능하도록 원문 보존.
        """
        _PENDING_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"raw_fallback_{timestamp}.md"
        path = _PENDING_DIR / filename

        fallback_content = (
            "---\n"
            f"action_type: raw_fallback\n"
            f"name: fallback_{timestamp}\n"
            f"created_at: {datetime.now().isoformat()}\n"
            f"status: pending\n"
            "---\n\n"
            "# AI 응답 원문 (자동 파싱 실패)\n\n"
            "아래 내용을 수동으로 검토하세요.\n\n"
            "---\n\n"
            f"{response}\n"
        )
        path.write_text(fallback_content, encoding="utf-8")
        _logger.warning(t("enhancer.fallback_saved", name=filename))
        return [path]

    # ------------------------------------------------------------------
    # 내부: dry-run 요약
    # ------------------------------------------------------------------

    def _build_dry_run_summary(self, parsed: list[dict]) -> str:
        """파싱 결과를 콘솔 출력용 요약 문자열로 변환한다."""
        lines: list[str] = [
            t("enhancer.dryrun_summary_title", n=len(parsed)),
        ]
        for i, file_data in enumerate(parsed, 1):
            meta = file_data["metadata"]
            action = meta.get("action_type", "unknown")
            name = meta.get("name", "unnamed")
            target = meta.get(
                "target", t("enhancer.dryrun_target_unset"),
            )
            dup = meta.get("duplicate_check", "create_new")
            lines.append(
                t("enhancer.dryrun_item",
                  i=i, action=action, name=name, target=target, dup=dup),
            )
        return "\n".join(lines)
