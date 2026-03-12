"""시스템 알림(notification) 유틸리티 테스트."""

from unittest.mock import patch

from src.utils.notify import send_notification


def test_send_notification_macos():
    """macOS에서 osascript 호출을 확인한다."""
    with patch("src.utils.notify.platform") as mock_platform, \
         patch("src.utils.notify.subprocess") as mock_sub:
        mock_platform.system.return_value = "Darwin"
        send_notification("제목", "내용")
        mock_sub.run.assert_called_once()
        args = mock_sub.run.call_args
        assert "osascript" in args[0][0][0]


def test_send_notification_non_macos():
    """macOS가 아니면 호출하지 않는다."""
    with patch("src.utils.notify.platform") as mock_platform, \
         patch("src.utils.notify.subprocess") as mock_sub:
        mock_platform.system.return_value = "Linux"
        send_notification("제목", "내용")
        mock_sub.run.assert_not_called()


def test_send_notification_failure_silent():
    """알림 실패 시 예외를 발생시키지 않는다."""
    with patch("src.utils.notify.platform") as mock_platform, \
         patch("src.utils.notify.subprocess") as mock_sub:
        mock_platform.system.return_value = "Darwin"
        mock_sub.run.side_effect = OSError("command not found")
        # 예외 없이 실행 완료
        send_notification("제목", "내용")
