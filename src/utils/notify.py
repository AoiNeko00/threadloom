"""macOS 데스크탑 알림(notification) 유틸리티."""

import platform
import subprocess

from src.utils.i18n import t
from src.utils.logger import get_logger

_logger = get_logger("notify")


def send_notification(title: str, message: str) -> None:
    """시스템 알림을 전송한다. macOS만 지원, 실패 시 무시."""
    if platform.system() != "Darwin":
        return
    try:
        subprocess.run(
            [
                "osascript", "-e",
                f'display notification "{message}" with title "{title}"',
            ],
            capture_output=True,
            timeout=5,
        )
    except Exception:
        _logger.debug(t("util.notify_fail"))
