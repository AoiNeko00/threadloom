"""AI CLI 어댑터 추상 기본 클래스(abstract base class) 정의."""

import os
import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path

from src.utils.i18n import t
from src.utils.logger import get_logger

_logger = get_logger("ai_adapter")

# CLI 호출 제한 시간(timeout) (초)
_TIMEOUT_SEC = 300
# 인증 확인용 제한 시간 (초)
_AUTH_TIMEOUT_SEC = 15
# stdin pipe 사용 기준 글자 수 임계값(threshold)
_STDIN_THRESHOLD = 5000
# Rate limit 재시도(retry) 설정
_MAX_RETRIES = 3
_BACKOFF_BASE_SEC = 10  # 초기 대기: 10초, 20초, 40초 (exponential)

# 화이트리스트(whitelist) 환경변수 — CLI subprocess에 전달할 키만 허용
_ENV_WHITELIST_PREFIXES = ("PATH", "HOME", "USER", "LANG", "LC_", "TERM",
                           "SHELL", "TMPDIR", "XDG_", "SSH_AUTH_SOCK")
# 명시적 차단(blocklist) — 중첩 세션 방지 등
_ENV_BLOCKLIST = {"CLAUDECODE"}


def _build_clean_env(extra_keys: tuple[str, ...] = ()) -> dict[str, str]:
    """CLI subprocess용 최소 환경변수(environment)를 구성한다.

    Args:
        extra_keys: 어댑터별 추가 허용 키 (예: API 키)
    """
    env: dict[str, str] = {}
    for key, val in os.environ.items():
        if key in _ENV_BLOCKLIST:
            continue
        if any(key.startswith(p) for p in _ENV_WHITELIST_PREFIXES):
            env[key] = val
        elif key in extra_keys:
            env[key] = val
    return env


class BaseAIAdapter(ABC):
    """AI CLI 호출을 추상화하는 기본 클래스.

    Phase 2(분석)와 Phase 3(강화 생성)에서 각 1회씩 호출된다.
    서브클래스는 _CLI_CMD와 _build_cli_args()를 정의해야 한다.
    """

    # 서브클래스에서 오버라이드(override)할 CLI 명령어
    _CLI_CMD: str = ""
    # 서브클래스에서 추가할 환경변수 키 (예: API 키)
    _EXTRA_ENV_KEYS: tuple[str, ...] = ()
    # 최소 호환 버전(minimum compatible version) — (major, minor)
    _MIN_VERSION: tuple[int, ...] = (0, 0)

    @abstractmethod
    def analyze(self, raw_md_path: Path, context_summary: str) -> str:
        """Phase 2: raw md + 기존 설정 요약 -> 분석 결과 텍스트 반환.

        AI CLI를 1회 호출하여 전체 포스트를 한번에 분석한다.
        반환값은 analysis md 파일에 그대로 저장된다.
        """

    @abstractmethod
    def generate_enhancements(
        self, analysis_md_path: Path, existing_files: dict[str, str]
    ) -> str:
        """Phase 3: 분석 결과 + 기존 파일 전문 -> 강화 초안 텍스트 반환.

        AI CLI를 1회 호출하여 skill/agent/rule 초안을 한번에 생성한다.
        existing_files: {"skills/foo.md": "내용...", "CLAUDE.md": "내용..."}
        반환값을 파싱하여 개별 pending md 파일로 분리 저장한다.
        """

    @abstractmethod
    def is_available(self) -> bool:
        """CLI가 시스템에 설치되어 있고 인증(authentication)이 유효한지 확인.

        1단계: CLI 바이너리(binary) 존재 여부 (shutil.which)
        2단계: 간단한 테스트 호출로 인증 유효성 확인
        인증 만료 시 명확한 에러 메시지 출력
        """

    # -- 공통 메서드(common methods) --

    @staticmethod
    def _get_language() -> str:
        """config에서 응답 언어(language) 설정을 읽는다."""
        from src.config import Config
        return Config().ai_language

    @staticmethod
    def _get_target_projects() -> list[dict]:
        """config에서 다중 프로젝트(multi-project) 목록을 읽는다."""
        from src.config import Config
        return Config().target_projects

    def call_raw(self, prompt: str) -> str:
        """임의의 프롬프트(prompt)를 CLI로 전달하고 응답을 반환한다."""
        return self._call_cli(prompt)

    def _call_cli(self, prompt: str) -> str:
        """subprocess로 CLI를 호출하고 결과를 반환한다.

        프롬프트가 길면 stdin pipe(파이프)를 사용한다.
        Rate limit(429) 감지 시 exponential backoff로 재시도한다.
        그 외 에러 시 1회 재시도한다.
        """
        for attempt in range(_MAX_RETRIES):
            try:
                return self._execute(prompt)
            except subprocess.CalledProcessError as exc:
                if self._is_rate_limited(exc):
                    wait = _BACKOFF_BASE_SEC * (2 ** attempt)
                    _logger.warning(
                        "Rate limit 감지. %d초 후 재시도 (%d/%d)",
                        wait, attempt + 1, _MAX_RETRIES,
                    )
                    time.sleep(wait)
                    continue
                # rate limit 아닌 에러: 1회만 재시도
                if attempt == 0:
                    continue
                raise
            except subprocess.TimeoutExpired:
                if attempt == 0:
                    continue
                raise

    @staticmethod
    def _is_rate_limited(exc: subprocess.CalledProcessError) -> bool:
        """stderr에서 rate limit 시그널을 감지한다."""
        err = (exc.stderr or "").lower()
        return any(kw in err for kw in ("429", "rate limit", "too many requests"))

    def _execute(self, prompt: str) -> str:
        """프롬프트 길이에 따라 호출 방식 분기."""
        use_stdin = len(prompt) > _STDIN_THRESHOLD
        args, stdin_input = self._build_cli_args(prompt, use_stdin)
        env = _build_clean_env(self._EXTRA_ENV_KEYS)
        result = subprocess.run(
            args,
            input=stdin_input,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SEC,
            check=True,
            env=env,
        )
        return result.stdout

    def _build_cli_args(
        self, prompt: str, use_stdin: bool
    ) -> tuple[list[str], str | None]:
        """CLI 명령어 인자와 stdin 입력을 반환한다.

        서브클래스에서 오버라이드하여 CLI별 인자 형식에 맞출 수 있다.
        Returns: (명령어 인자 리스트, stdin 입력 또는 None)
        """
        # 기본 구현: 프롬프트를 직접 인자로 전달
        if use_stdin:
            return [self._CLI_CMD], prompt
        return [self._CLI_CMD, prompt], None

    def _cli_exists(self) -> bool:
        """CLI 바이너리가 PATH에 존재하는지 확인."""
        return shutil.which(self._CLI_CMD) is not None

    def _check_auth(self, test_args: list[str]) -> bool:
        """테스트 호출로 인증 상태 확인."""
        try:
            result = subprocess.run(
                test_args,
                capture_output=True,
                text=True,
                timeout=_AUTH_TIMEOUT_SEC,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def check_version(self) -> bool:
        """CLI 버전이 최소 요구 버전 이상인지 확인한다.

        Returns:
            True면 호환, False면 경고 로그 출력 후 False
        """
        if self._MIN_VERSION == (0, 0):
            return True
        try:
            result = subprocess.run(
                [self._CLI_CMD, "--version"],
                capture_output=True, text=True,
                timeout=_AUTH_TIMEOUT_SEC,
            )
            version = self._parse_version(result.stdout.strip())
            if version and version < self._MIN_VERSION:
                _logger.warning(
                    "%s 버전 %s — 최소 %s 이상 필요. "
                    "업데이트를 권장합니다.",
                    self._CLI_CMD,
                    ".".join(str(v) for v in version),
                    ".".join(str(v) for v in self._MIN_VERSION),
                )
                return False
            if version:
                _logger.info(
                    "%s 버전 확인: %s",
                    self._CLI_CMD,
                    ".".join(str(v) for v in version),
                )
            return True
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            _logger.debug(t("util.version_check_fail", cmd=self._CLI_CMD))
            return True  # 버전 확인 실패 시 실행은 허용

    @staticmethod
    def _parse_version(text: str) -> tuple[int, ...] | None:
        """버전 문자열에서 숫자 튜플을 추출한다.

        '1.2.3', 'claude 1.0.8', '0.33.0' 등 다양한 형식을 처리한다.
        """
        import re
        match = re.search(r"(\d+(?:\.\d+)+)", text)
        if not match:
            return None
        return tuple(int(x) for x in match.group(1).split("."))
