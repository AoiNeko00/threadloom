"""Claude Code CLI 어댑터(adapter) 구현."""

from pathlib import Path

from .base import BaseAIAdapter
from .prompts import build_analyze_prompt, build_enhance_prompt


class ClaudeCodeAdapter(BaseAIAdapter):
    """claude -p 명령어로 AI를 호출하는 어댑터."""

    _CLI_CMD = "claude"
    _MIN_VERSION = (1, 0)
    # Claude Code 전용(specific) 지시 — 도구 호출 방지
    _CLAUDE_SUFFIX = (
        "\n\nIMPORTANT: Output text only. "
        "Do NOT create files, call tools, or request permissions. "
        "Return plain text only."
    )

    def analyze(self, raw_md_path: Path, context_summary: str) -> str:
        """Phase 2: 수집 원문 + 기존 설정 요약 -> 분석 결과 반환."""
        raw_content = raw_md_path.read_text(encoding="utf-8")
        prompt = build_analyze_prompt(
            raw_content, context_summary, self._get_language(),
        )
        return self._call_cli(prompt + self._CLAUDE_SUFFIX)

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
        return self._call_cli(prompt + self._CLAUDE_SUFFIX)

    def is_available(self) -> bool:
        """CLI 존재 확인. claude -p는 항상 인증된 상태로 가정."""
        return self._cli_exists()

    def _build_cli_args(
        self, prompt: str, use_stdin: bool
    ) -> tuple[list[str], str | None]:
        """claude -p 형식으로 인자 구성."""
        if use_stdin:
            return [self._CLI_CMD, "-p", "-"], prompt
        return [self._CLI_CMD, "-p", prompt], None
