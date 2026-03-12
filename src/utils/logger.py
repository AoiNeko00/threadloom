"""threadloom 로깅(logging) 모듈.

rich 기반 컬러 콘솔 출력 + 파일 로그 저장.
민감정보(sensitive info) 마스킹 필수.
"""

import logging
import logging.handlers
import os
import re
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

# 프로젝트 루트(project root) 경로
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent

# 로그 디렉토리 자동 생성
_LOG_DIR: Path = _PROJECT_ROOT / "logs"
_LOG_DIR.mkdir(exist_ok=True)

_LOG_FILE: Path = _LOG_DIR / "threadloom.log"

# 마스킹(masking) 대상 패턴
_HOME_DIR: str = str(Path.home())
_USERNAME: str = Path.home().name


class _SensitiveMaskingFilter(logging.Filter):
    """로그 메시지에서 민감정보를 마스킹하는 필터(filter)."""

    def __init__(self, vault_path: str = "") -> None:
        super().__init__()
        self._vault_path = vault_path

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._mask(str(record.msg))
        if record.args:
            record.args = tuple(
                self._mask(str(a)) if isinstance(a, str) else a
                for a in record.args
            )
        return True

    def _mask(self, text: str) -> str:
        """절대경로와 사용자명을 마스킹 처리."""
        # Obsidian vault 경로(vault path) 치환
        if self._vault_path:
            text = text.replace(self._vault_path, "{vault}")
        # 홈 디렉토리(home directory) 치환
        text = text.replace(_HOME_DIR, "~")
        # 사용자명(username) 마스킹
        text = re.sub(
            re.escape(_USERNAME),
            "***",
            text,
        )
        return text


def get_logger(name: str, vault_path: str = "") -> logging.Logger:
    """이름 기반 로거(logger) 인스턴스를 반환한다.

    Args:
        name: 로거 이름 (보통 모듈명)
        vault_path: Obsidian vault 절대경로 (마스킹용, 선택)

    Returns:
        설정된 Logger 인스턴스
    """
    logger = logging.getLogger(f"threadloom.{name}")

    # 이미 핸들러(handler)가 있으면 중복 추가 방지
    if logger.handlers:
        return logger

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, log_level, logging.INFO))

    # 민감정보 마스킹 필터 등록
    masking_filter = _SensitiveMaskingFilter(vault_path)
    logger.addFilter(masking_filter)

    # 콘솔 핸들러 (rich 컬러 출력)
    console_handler = RichHandler(
        console=Console(stderr=True),
        show_time=True,
        show_path=False,
        markup=True,
    )
    console_handler.setLevel(logging.DEBUG)
    logger.addHandler(console_handler)

    # 파일 핸들러(file handler) — 5MB 자동 회전(rotation), 최대 3개 백업
    file_handler = logging.handlers.RotatingFileHandler(
        _LOG_FILE, encoding="utf-8",
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3,
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    file_handler.addFilter(masking_filter)
    logger.addHandler(file_handler)

    # 상위 로거(parent logger) 전파 방지
    logger.propagate = False

    return logger
