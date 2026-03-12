"""Threads 인증(authentication) 관리 모듈.

OS Keychain(keyring) 기반 세션 저장/로드/삭제.
Playwright 브라우저로 수동 로그인 후 쿠키(cookies)를 파일에 보존한다.
"""

import json
from pathlib import Path

import keyring
from playwright.sync_api import BrowserContext, sync_playwright

from src.utils.i18n import t
from src.utils.logger import get_logger
from src.utils.paths import PROJECT_ROOT

# 상수(constants)
_SERVICE_NAME: str = "threadloom"
_KEYRING_KEY: str = "session_path"
_THREADS_URL: str = "https://www.threads.com"

# 중앙 경로(centralized path) 모듈에서 가져옴
_AUTH_DIR: Path = PROJECT_ROOT / "auth"
_SESSION_FILE: Path = _AUTH_DIR / "session.json"

_logger = get_logger("collector.auth")


class AuthExpiredError(Exception):
    """세션(session) 만료 시 발생하는 예외."""


class AuthManager:
    """OS Keychain 기반 Threads 인증 관리자(manager)."""

    def __init__(self, account: str = "") -> None:
        # 계정별(account-specific) keyring 키 — 여러 계정 사용 시 충돌 방지
        suffix = f"_{account}" if account else ""
        self._keyring_key = f"{_KEYRING_KEY}{suffix}"
        self._session_file = (
            _AUTH_DIR / f"session{suffix}.json" if account
            else _SESSION_FILE
        )

    def setup_auth(self) -> bool:
        """최초 수동 로그인 후 세션을 저장한다.

        headless=False로 브라우저를 열어 사용자가 직접 로그인하도록 대기.
        로그인 성공 감지 후 쿠키를 auth/session.json에 저장.

        Returns:
            로그인 성공 여부
        """
        _AUTH_DIR.mkdir(parents=True, exist_ok=True)
        _logger.info(t("auth.open_browser"))

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto(_THREADS_URL)

            _logger.info(t("auth.login_prompt"))
            _logger.info(t("auth.press_enter"))
            input(t("auth.input_prompt"))

            self._save_cookies(context)
            browser.close()

        _logger.info(t("auth.saved", key=self._keyring_key))
        return True

    def load_session(self, context: BrowserContext) -> bool:
        """저장된 쿠키를 Playwright context에 로드한다.

        Args:
            context: Playwright BrowserContext

        Returns:
            로드 성공 여부
        """
        session_path = self._get_session_path()
        if session_path is None or not session_path.exists():
            _logger.warning(t("auth.no_session"))
            return False

        cookies = self._read_cookies(session_path)
        if not cookies:
            return False

        context.add_cookies(cookies)
        _logger.info(t("auth.cookies_loaded"))
        return True

    def is_session_valid(self) -> bool:
        """세션 파일 존재 여부를 확인한다."""
        session_path = self._get_session_path()
        return session_path is not None and session_path.exists()

    def clear_auth(self) -> None:
        """세션 파일과 keyring 항목을 모두 삭제한다."""
        if self._session_file.exists():
            self._session_file.unlink()
            _logger.info(t("auth.session_deleted", name=self._session_file.name))

        try:
            keyring.delete_password(_SERVICE_NAME, self._keyring_key)
            _logger.info(t("auth.keyring_deleted", key=self._keyring_key))
        except keyring.errors.PasswordDeleteError:
            _logger.debug(t("auth.keyring_empty"))

    # -- private --

    def _wait_for_login(self, page) -> bool:
        """로그인 완료를 감지한다 (최대 5분).

        여러 시그널(signal)을 폴링하여 판단:
        1. 로그인 폼 사라짐
        2. 프로필 아이콘/링크 등장
        3. URL에 login이 없어짐
        """
        import time
        deadline = time.time() + 300  # 5분
        while time.time() < deadline:
            try:
                url = page.url.lower()
                # 로그인 페이지가 아니고, 피드 요소가 있으면 성공
                if "login" not in url and "accounts" not in url:
                    # 프로필 링크나 네비게이션(navigation) 요소 감지
                    indicators = page.query_selector_all(
                        "a[href*='/@'], "
                        "[aria-label*='Profile'], "
                        "[aria-label*='프로필'], "
                        "nav, "
                        "[role='navigation']"
                    )
                    if indicators:
                        return True
            except Exception:
                pass
            page.wait_for_timeout(2000)
        return False

    def _save_cookies(self, context: BrowserContext) -> None:
        """context 쿠키를 JSON 파일로 저장하고 경로를 keyring에 등록."""
        cookies = context.cookies()
        self._session_file.write_text(
            json.dumps(cookies, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._session_file.chmod(0o600)
        keyring.set_password(
            _SERVICE_NAME, self._keyring_key, str(self._session_file),
        )
        _logger.info(t("auth.cookies_saved", n=len(cookies)))

    def _get_session_path(self) -> Path | None:
        """keyring에서 세션 파일 경로를 읽는다."""
        path_str = keyring.get_password(_SERVICE_NAME, self._keyring_key)
        if path_str is None:
            return None
        return Path(path_str)

    def _read_cookies(self, path: Path) -> list[dict]:
        """세션 파일에서 쿠키 목록을 읽는다."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError) as exc:
            _logger.error(t("auth.session_read_fail", err=type(exc).__name__))
            return []
