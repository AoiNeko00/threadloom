"""Gemini CLI 어댑터(adapter) 구현.

비대화형(non-interactive) 모드: `gemini -p "prompt"`
"""

from pathlib import Path

from .base import BaseAIAdapter
from .prompts import build_analyze_prompt, build_enhance_prompt


class GeminiAdapter(BaseAIAdapter):
    """gemini -p 명령어로 AI를 호출하는 어댑터.

    프롬프트 템플릿은 prompts 모듈의 공통 빌더를 사용한다.
    """

    _CLI_CMD = "gemini"
    _MIN_VERSION = (0, 30)

    def _build_cli_args(
        self, prompt: str, use_stdin: bool
    ) -> tuple[list[str], str | None]:
        """gemini -p 형식으로 인자 구성."""
        if use_stdin:
            return [self._CLI_CMD, "-p", "-"], prompt
        return [self._CLI_CMD, "-p", prompt], None

    def analyze(self, raw_md_path: Path, context_summary: str) -> str:
        """Phase 2: 수집 원문 + 기존 설정 요약 -> 분석 결과 반환."""
        raw_content = raw_md_path.read_text(encoding="utf-8")
        prompt = build_analyze_prompt(
            raw_content, context_summary, self._get_language(),
        )
        return self._call_cli(prompt)

    def generate_enhancements(
        self, analysis_md_path: Path, existing_files: dict[str, str]
    ) -> str:
        """Phase 3: 분석 결과 + 기존 파일 -> 강화 초안 반환."""
        analysis_content = analysis_md_path.read_text(encoding="utf-8")
        existing_summary = "\n\n".join(
            f"### {path}\n```\n{content}\n```"
            for path, content in existing_files.items()
        )
        prompt = build_enhance_prompt(
            analysis_content, existing_summary, self._get_language(),
            target_projects=self._get_target_projects(),
        )
        return self._call_cli(prompt)

    def is_available(self) -> bool:
        """CLI 존재 + 버전 확인(version check)으로 가용성 판단."""
        if not self._cli_exists():
            return False
        # gemini -p는 응답 생성에 시간이 걸려 timeout 초과 가능
        # --version으로 CLI 정상 동작만 확인 (인증은 실제 호출 시 검증)
        return self._check_auth([self._CLI_CMD, "--version"])
